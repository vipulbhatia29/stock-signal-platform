"""Celery tasks for news ingestion and sentiment scoring pipeline."""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone

from backend.tasks import celery_app

logger = logging.getLogger(__name__)

# Default lookback for news ingestion (7 days)
NEWS_LOOKBACK_DAYS = 7


@celery_app.task(
    bind=True,
    name="backend.tasks.news_sentiment.news_ingest_task",
)
def news_ingest_task(self, lookback_days: int = NEWS_LOOKBACK_DAYS) -> dict:
    """Ingest stock and macro news from all providers.

    Fetches news for all active tickers (from the stock universe) and
    macro news. Deduplicates and stores in the database.

    Args:
        lookback_days: How many days back to fetch.

    Returns:
        Dict with stock and macro ingestion stats.
    """
    self.update_state(state="PROGRESS", meta={"step": "ingesting_news"})
    return asyncio.run(_ingest_news(lookback_days))


async def _ingest_news(lookback_days: int) -> dict:
    """Async implementation of news ingestion."""
    from sqlalchemy import select

    from backend.database import async_session_factory
    from backend.models.stock import Stock
    from backend.services.news.ingestion import NewsIngestionService

    since = date.today() - timedelta(days=lookback_days)
    service = NewsIngestionService()

    # Get active tickers from the universe
    async with async_session_factory() as session:
        result = await session.execute(
            select(Stock.ticker).where(Stock.is_active.is_(True)).limit(50)
        )
        tickers = [row[0] for row in result.all()]

    # Ingest stock news
    stock_result = await service.ingest_stock_news(tickers, since)
    logger.info("Stock news ingested: %s", stock_result)

    # Ingest macro news
    macro_result = await service.ingest_macro_news(since)
    logger.info("Macro news ingested: %s", macro_result)

    return {
        "status": "complete",
        "stock": stock_result,
        "macro": macro_result,
        "tickers_processed": len(tickers),
    }


@celery_app.task(
    bind=True,
    name="backend.tasks.news_sentiment.news_sentiment_scoring_task",
)
def news_sentiment_scoring_task(self, lookback_days: int = NEWS_LOOKBACK_DAYS) -> dict:
    """Score unscored news articles and aggregate daily sentiment.

    Args:
        lookback_days: How many days back to look for unscored articles.

    Returns:
        Dict with scoring stats.
    """
    self.update_state(state="PROGRESS", meta={"step": "scoring_sentiment"})
    return asyncio.run(_score_sentiment(lookback_days))


async def _score_sentiment(lookback_days: int) -> dict:
    """Async implementation of sentiment scoring."""
    from sqlalchemy import update
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from backend.database import async_session_factory
    from backend.models.news_sentiment import NewsArticle, NewsSentimentDaily
    from backend.services.news.base import RawArticle
    from backend.services.news.ingestion import NewsIngestionService
    from backend.services.news.sentiment_scorer import SentimentScorer

    since = date.today() - timedelta(days=lookback_days)
    ingestion_svc = NewsIngestionService()
    scorer = SentimentScorer()

    # Get unscored articles
    unscored = await ingestion_svc.get_unscored_articles(since)
    if not unscored:
        return {"status": "complete", "scored": 0, "aggregated": 0}

    # Convert ORM objects to RawArticle for the scorer
    raw_articles = [
        RawArticle(
            headline=a.headline,
            summary=a.summary,
            source=a.source,
            source_url=a.source_url,
            ticker=a.ticker,
            published_at=a.published_at,
            event_type=a.event_type,
            dedupe_hash=a.dedupe_hash,
        )
        for a in unscored
    ]

    # Score via LLM
    scores = await scorer.score_batch(raw_articles)
    if not scores:
        return {
            "status": "complete",
            "scored": 0,
            "aggregated": 0,
            "note": "No scores returned (API key missing or error)",
        }

    # Aggregate daily sentiment
    today = date.today()
    daily = scorer.aggregate_daily(scores, raw_articles, today)

    # Single transaction: mark articles as scored + upsert daily sentiment
    scored_hashes = {s.dedupe_hash for s in scores}
    now = datetime.now(timezone.utc)
    async with async_session_factory() as session:
        # Mark articles as scored
        await session.execute(
            update(NewsArticle)
            .where(NewsArticle.dedupe_hash.in_(scored_hashes))
            .values(scored_at=now)
        )

        # Upsert daily sentiment rows
        for ticker, sentiment in daily.items():
            stmt = (
                pg_insert(NewsSentimentDaily)
                .values(
                    date=sentiment.date,
                    ticker=sentiment.ticker,
                    stock_sentiment=sentiment.stock_sentiment,
                    sector_sentiment=sentiment.sector_sentiment,
                    macro_sentiment=sentiment.macro_sentiment,
                    article_count=sentiment.article_count,
                    confidence=sentiment.confidence,
                    dominant_event_type=sentiment.dominant_event_type,
                    rationale_summary=sentiment.rationale_summary,
                )
                .on_conflict_do_update(
                    index_elements=["date", "ticker"],
                    set_={
                        "stock_sentiment": sentiment.stock_sentiment,
                        "sector_sentiment": sentiment.sector_sentiment,
                        "macro_sentiment": sentiment.macro_sentiment,
                        "article_count": sentiment.article_count,
                        "confidence": sentiment.confidence,
                        "dominant_event_type": sentiment.dominant_event_type,
                        "rationale_summary": sentiment.rationale_summary,
                    },
                )
            )
            await session.execute(stmt)

        await session.commit()

    # Invalidate cached sentiment for affected tickers
    try:
        from backend.services.cache_invalidator import CacheInvalidator
        from backend.services.redis_pool import get_redis

        redis_client = await get_redis()
        invalidator = CacheInvalidator(redis_client)
        affected_tickers = [t for t in daily if t != "__MACRO__"]
        if affected_tickers:
            await invalidator.on_sentiment_scored(affected_tickers)
    except Exception:
        logger.warning("Cache invalidation after scoring failed", exc_info=True)

    return {
        "status": "complete",
        "scored": len(scores),
        "aggregated": len(daily),
        "tickers": list(daily.keys()),
    }
