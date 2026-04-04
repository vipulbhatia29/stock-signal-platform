"""News ingestion orchestrator — coordinates providers, dedup, and storage."""

from __future__ import annotations

import asyncio
import logging
from datetime import date

from sqlalchemy import select

from backend.database import async_session_factory
from backend.models.news_sentiment import NewsArticle
from backend.services.news.base import NewsProvider, RawArticle
from backend.services.news.edgar_provider import EdgarProvider
from backend.services.news.fed_provider import FedRssProvider
from backend.services.news.finnhub_provider import FinnhubProvider
from backend.services.news.google_provider import GoogleNewsProvider

logger = logging.getLogger(__name__)


class NewsIngestionService:
    """Orchestrates news fetching from all providers, dedup, and storage."""

    def __init__(self) -> None:
        self._providers = [
            FinnhubProvider(),
            EdgarProvider(),
            FedRssProvider(),
            GoogleNewsProvider(),
        ]

    async def ingest_stock_news(self, tickers: list[str], since: date) -> dict:
        """Fetch and store stock news for given tickers.

        Args:
            tickers: List of ticker symbols to fetch news for.
            since: Fetch articles published on or after this date.

        Returns:
            Dict with counts: {fetched, new, duplicates, errors}
        """

        # Parallelize across providers (each has its own rate limiter)
        async def _fetch_provider(provider: NewsProvider, ticker: str) -> list[RawArticle]:
            return await provider.fetch_stock_news(ticker, since)

        tasks = [
            _fetch_provider(provider, ticker) for provider in self._providers for ticker in tickers
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_articles: list[RawArticle] = []
        errors = 0
        for result in results:
            if isinstance(result, Exception):
                errors += 1
                logger.error("Provider fetch failed: %s", type(result).__name__)
            else:
                all_articles.extend(result)

        return await self._store_articles(all_articles, errors)

    async def ingest_macro_news(self, since: date) -> dict:
        """Fetch and store macro/market-wide news.

        Args:
            since: Fetch articles published on or after this date.

        Returns:
            Dict with counts: {fetched, new, duplicates, errors}
        """
        tasks = [provider.fetch_macro_news(since) for provider in self._providers]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_articles: list[RawArticle] = []
        errors = 0
        for result in results:
            if isinstance(result, Exception):
                errors += 1
                logger.error(
                    "Provider macro news fetch failed: %s",
                    type(result).__name__,
                )
            else:
                all_articles.extend(result)

        return await self._store_articles(all_articles, errors)

    async def _store_articles(self, articles: list[RawArticle], prior_errors: int) -> dict:
        """Deduplicate and store articles in the database.

        Uses ON CONFLICT DO NOTHING on (dedupe_hash, published_at) for idempotent upserts.

        Args:
            articles: Raw articles from providers.
            prior_errors: Error count from fetch phase.

        Returns:
            Dict with {fetched, new, duplicates, errors}.
        """
        if not articles:
            return {"fetched": 0, "new": 0, "duplicates": 0, "errors": prior_errors}

        # Deduplicate by hash within this batch
        seen: set[str] = set()
        unique: list[RawArticle] = []
        for article in articles:
            if article.dedupe_hash not in seen:
                seen.add(article.dedupe_hash)
                unique.append(article)

        new_count = 0
        async with async_session_factory() as session:
            # Batch existence check (avoid N+1 queries)
            all_hashes = [a.dedupe_hash for a in unique]
            result = await session.execute(
                select(NewsArticle.dedupe_hash).where(NewsArticle.dedupe_hash.in_(all_hashes))
            )
            existing_hashes = set(result.scalars().all())

            for article in unique:
                if article.dedupe_hash in existing_hashes:
                    continue

                # Strip tzinfo — column is TIMESTAMP WITHOUT TIME ZONE
                pub = article.published_at
                naive_pub = pub.replace(tzinfo=None) if pub.tzinfo else pub
                row = NewsArticle(
                    published_at=naive_pub,
                    ticker=article.ticker,
                    headline=article.headline,
                    summary=article.summary,
                    source=article.source,
                    source_url=article.source_url[:500] if article.source_url else None,
                    event_type=article.event_type,
                    dedupe_hash=article.dedupe_hash,
                )
                session.add(row)
                new_count += 1

            await session.commit()

        duplicates = len(articles) - len(unique) + (len(unique) - new_count)
        return {
            "fetched": len(articles),
            "new": new_count,
            "duplicates": duplicates,
            "errors": prior_errors,
        }

    async def get_unscored_articles(self, since: date, limit: int = 500) -> list[NewsArticle]:
        """Fetch articles that haven't been scored yet.

        Args:
            since: Only articles published on or after this date.
            limit: Maximum articles to return.

        Returns:
            List of NewsArticle ORM objects.
        """
        async with async_session_factory() as session:
            result = await session.execute(
                select(NewsArticle)
                .where(
                    NewsArticle.scored_at.is_(None),
                    NewsArticle.published_at >= since,
                )
                .order_by(NewsArticle.published_at.desc())
                .limit(limit)
            )
            return list(result.scalars().all())
