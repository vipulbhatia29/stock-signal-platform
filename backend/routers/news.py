"""Dashboard news aggregation — per-user, cached."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_async_session
from backend.dependencies import get_current_user
from backend.models.portfolio import Portfolio, Position
from backend.models.recommendation import RecommendationSnapshot
from backend.models.user import User
from backend.tools.news import fetch_google_news_rss, merge_and_deduplicate

logger = logging.getLogger(__name__)


class DashboardNewsArticle(BaseModel):
    """A single news article for the dashboard."""

    title: str
    link: str
    publisher: str | None = None
    published: str | None = None
    source: str = "google_news"
    portfolio_ticker: str | None = None


class DashboardNewsResponse(BaseModel):
    """Response from the dashboard news endpoint."""

    articles: list[DashboardNewsArticle]
    ticker_count: int


router = APIRouter(prefix="/news", tags=["news"])


async def _get_portfolio_tickers(
    db: AsyncSession,
    user_id: int,
    limit: int = 3,
) -> list[str]:
    """Return top portfolio tickers ordered by share count (descending).

    Args:
        db: Async database session.
        user_id: UUID of the current user.
        limit: Maximum tickers to return.

    Returns:
        List of ticker strings.
    """
    portfolio_q = select(Portfolio.id).where(Portfolio.user_id == user_id)
    portfolio_result = await db.execute(portfolio_q)
    portfolio_id = portfolio_result.scalar_one_or_none()

    if not portfolio_id:
        return []

    pos_q = (
        select(Position.ticker)
        .where(Position.portfolio_id == portfolio_id, Position.shares > 0)
        .order_by(Position.shares.desc())
        .limit(limit)
    )
    pos_result = await db.execute(pos_q)
    return [row[0] for row in pos_result.all()]


async def _get_recommendation_tickers(
    db: AsyncSession,
    user_id: int,
    limit: int = 3,
) -> list[str]:
    """Return top recent BUY/STRONG_BUY recommendation tickers.

    Args:
        db: Async database session.
        user_id: UUID of the current user.
        limit: Maximum tickers to return.

    Returns:
        List of ticker strings.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
    rec_q = (
        select(RecommendationSnapshot.ticker)
        .where(
            RecommendationSnapshot.user_id == user_id,
            RecommendationSnapshot.generated_at >= cutoff,
            RecommendationSnapshot.action.in_(["BUY", "STRONG_BUY"]),
        )
        .order_by(RecommendationSnapshot.composite_score.desc())
        .limit(limit)
    )
    rec_result = await db.execute(rec_q)
    return [row[0] for row in rec_result.all()]


async def _fetch_for_ticker(ticker: str) -> list[dict]:
    """Fetch news articles for a single ticker, tagging each with the ticker.

    Args:
        ticker: Stock symbol.

    Returns:
        List of article dicts with added ``portfolio_ticker`` field.
    """
    try:
        articles = await fetch_google_news_rss(ticker)
        return [{**a, "portfolio_ticker": ticker} for a in articles[:3]]
    except Exception:
        # Fire-and-forget: broad catch intentional — news fetch must not crash dashboard
        logger.warning("News fetch failed for %s", ticker, exc_info=True)
        return []


@router.get("/dashboard", response_model=DashboardNewsResponse)
async def get_dashboard_news(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> DashboardNewsResponse:
    """Aggregated news for user's portfolio + recommendation tickers.

    Returns the 15 most recent articles across portfolio and
    recommendation tickers, with per-user Redis cache (5 min TTL).
    """
    # --- Cache check (optional — CacheService may not be wired) ---
    cache = getattr(request.app.state, "cache", None)
    cache_key = f"user:{current_user.id}:dashboard_news"

    if cache:
        cached = await cache.get(cache_key)
        if cached:
            return DashboardNewsResponse.model_validate_json(cached)

    # --- Gather tickers from portfolio + recommendations ---
    portfolio_tickers = await _get_portfolio_tickers(db, current_user.id)
    rec_tickers = await _get_recommendation_tickers(db, current_user.id)

    # Deduplicate preserving order, cap at 6
    all_tickers = list(dict.fromkeys(portfolio_tickers + rec_tickers))[:6]

    if not all_tickers:
        return DashboardNewsResponse(articles=[], ticker_count=0)

    # --- Fetch news in parallel ---
    results = await asyncio.gather(*[_fetch_for_ticker(t) for t in all_tickers])
    all_articles = [a for batch in results for a in batch]

    # Deduplicate + sort by date, limit to 15
    all_articles = merge_and_deduplicate(all_articles, max_results=15)

    response = DashboardNewsResponse(
        articles=[DashboardNewsArticle(**a) for a in all_articles],
        ticker_count=len(all_tickers),
    )

    # --- Cache result ---
    if cache:
        try:
            from backend.services.cache import CacheTier

            await cache.set(cache_key, response.model_dump_json(), CacheTier.VOLATILE)
        except Exception:
            # Fire-and-forget: broad catch intentional — cache write must not crash response
            logger.warning(
                "Failed to cache dashboard news for user %s", current_user.id, exc_info=True
            )

    return response
