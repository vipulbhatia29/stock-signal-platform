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
    sentiment: float | None = None  # -1.0 (bearish) to 1.0 (bullish)
    sentiment_label: str | None = None  # "bullish" | "bearish" | "neutral"
    category: str | None = None  # "general" | "stock" | "sector" | "macro"


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

    # --- Score sentiment via LLM (best effort) ---
    articles = [DashboardNewsArticle(**a) for a in all_articles]
    articles = await _score_article_sentiment(articles)

    response = DashboardNewsResponse(
        articles=articles,
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


# ── Inline sentiment scoring ──────────────────────────────────────────────────

_SENTIMENT_SYSTEM = (
    "You are a financial news sentiment classifier. For each headline, return JSON.\n"
    'Output: {"results": [{"index": 0, "sentiment": 0.5, "label": "bullish", '
    '"category": "stock", "rationale": "Strong earnings"}, ...]}\n\n'
    "Fields:\n"
    "- sentiment: float -1.0 (very bearish) to 1.0 (very bullish), 0.0 = neutral\n"
    "- label: one of [bullish, bearish, neutral]\n"
    "- category: one of [stock, sector, macro, general]\n"
    '  - "stock" = news about a specific company\n'
    '  - "sector" = news about an industry/sector\n'
    '  - "macro" = macro-economic (fed, CPI, employment, geopolitics)\n'
    '  - "general" = market commentary, opinion, not actionable\n'
    "- rationale: 1-sentence explanation (brief)\n"
    "IMPORTANT: The headline's primary subject determines sentiment. "
    '"Stock futures fall as oil rises" is BEARISH because the '
    "main subject is stock futures falling."
)


async def _score_article_sentiment(
    articles: list[DashboardNewsArticle],
) -> list[DashboardNewsArticle]:
    """Score a batch of articles using LLM. Best-effort — returns unscored on failure."""
    if not articles:
        return articles

    from backend.config import settings

    api_key = settings.OPENAI_API_KEY
    if not api_key:
        return articles

    model = getattr(settings, "NEWS_SCORING_MODEL", "gpt-4o-mini")

    lines = ["Score these news headlines:\n"]
    for i, a in enumerate(articles):
        ticker_label = f"[{a.portfolio_ticker}]" if a.portfolio_ticker else "[MARKET]"
        lines.append(f"{i}. {ticker_label} {a.title}")
    prompt = "\n".join(lines)

    from backend.services.http_client import get_http_client

    payload = {
        "model": model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": _SENTIMENT_SYSTEM},
            {"role": "user", "content": prompt},
        ],
    }

    try:
        client = get_http_client()
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            json=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=15,
        )
        resp.raise_for_status()
        import json

        content = resp.json()["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        results = parsed.get("results", [])

        for item in results:
            idx = item.get("index")
            if idx is not None and 0 <= idx < len(articles):
                articles[idx].sentiment = item.get("sentiment")
                articles[idx].sentiment_label = item.get("label")
                articles[idx].category = item.get("category")
    except Exception:
        logger.warning("Sentiment scoring failed — returning unscored", exc_info=True)

    return articles
