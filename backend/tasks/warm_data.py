"""Warm data pipeline — Celery tasks that pre-fetch external data into Redis.

These tasks run on a schedule (Celery Beat) to keep commonly-accessed
external data warm in cache, reducing latency for agent tool calls.
"""

from __future__ import annotations

import asyncio
import json
import logging

import redis

from backend.config import settings
from backend.tasks import celery_app

logger = logging.getLogger(__name__)

# FRED series to track
_FRED_SERIES = ["DFF", "CPIAUCSL", "DGS10", "UNRATE", "DCOILWTICO"]

# Cache TTLs
_ANALYST_TTL = 86400  # 24 hours
_FRED_TTL = 86400  # 24 hours
_HOLDERS_TTL = 604800  # 7 days


def _get_redis_client() -> redis.Redis:
    """Create a synchronous Redis client."""
    return redis.from_url(settings.REDIS_URL, decode_responses=True)


def _get_watched_tickers() -> list[str]:
    """Get all unique tickers across user watchlists.

    Uses the same async DB query pattern as market_data tasks,
    but returns a flat list of ticker strings.
    """
    from backend.database import async_session_factory
    from backend.models.stock import WatchlistItem

    async def _query() -> list[str]:
        from sqlalchemy import select

        async with async_session_factory() as session:
            result = await session.execute(select(WatchlistItem.ticker).distinct())
            return [row[0] for row in result.all()]

    return asyncio.run(_query())


async def _fetch_and_cache_analyst(ticker: str, r: redis.Redis) -> None:
    """Fetch analyst ratings for a ticker and cache in Redis."""
    from backend.tools.adapters.finnhub import FinnhubAdapter

    adapter = FinnhubAdapter(api_key=settings.FINNHUB_API_KEY)
    result = await adapter.execute("get_analyst_ratings", {"ticker": ticker})
    if result.status == "ok":
        r.setex(
            f"warm:analyst:{ticker}",
            _ANALYST_TTL,
            json.dumps(result.data),
        )
        logger.info("Cached analyst ratings for %s", ticker)
    else:
        logger.warning("Failed to fetch analyst ratings for %s: %s", ticker, result.error)


async def _fetch_and_cache_fred(r: redis.Redis) -> None:
    """Fetch key FRED economic series and cache in Redis."""
    from backend.tools.adapters.fred import FredAdapter

    adapter = FredAdapter(api_key=settings.FRED_API_KEY)
    result = await adapter.execute("get_economic_series", {"series_ids": _FRED_SERIES, "limit": 5})
    if result.status == "ok":
        r.setex("warm:fred:indicators", _FRED_TTL, json.dumps(result.data))
        logger.info("Cached FRED indicators for %d series", len(_FRED_SERIES))
    else:
        logger.warning("Failed to fetch FRED indicators: %s", result.error)


async def _fetch_and_cache_holders(ticker: str, r: redis.Redis) -> None:
    """Fetch 13F institutional holders for a ticker and cache in Redis."""
    from backend.tools.adapters.edgar import EdgarAdapter

    adapter = EdgarAdapter()
    result = await adapter.execute("get_13f_holdings", {"ticker": ticker})
    if result.status == "ok":
        r.setex(
            f"warm:holders:{ticker}",
            _HOLDERS_TTL,
            json.dumps(result.data),
        )
        logger.info("Cached institutional holders for %s", ticker)
    else:
        logger.warning("Failed to fetch holders for %s: %s", ticker, result.error)


# ── Celery Tasks ──────────────────────────────────────────────────────────────


@celery_app.task(
    name="backend.tasks.warm_data.sync_analyst_consensus_task",
)
def sync_analyst_consensus_task() -> dict:
    """Fetch analyst consensus ratings for all watched tickers.

    Runs daily at 6 AM ET via Celery Beat. Caches results in Redis
    with a 24-hour TTL for fast agent tool lookups.

    Returns:
        Dict with count of tickers processed.
    """
    tickers = _get_watched_tickers()
    r = _get_redis_client()

    async def _run() -> None:
        for ticker in tickers:
            await _fetch_and_cache_analyst(ticker, r)

    asyncio.run(_run())
    logger.info("Synced analyst consensus for %d tickers", len(tickers))
    return {"tickers_processed": len(tickers), "tickers": tickers}


@celery_app.task(
    name="backend.tasks.warm_data.sync_fred_indicators_task",
)
def sync_fred_indicators_task() -> dict:
    """Fetch key FRED economic indicators.

    Runs daily at 7 AM ET via Celery Beat. Caches Fed rate, CPI,
    10Y yield, unemployment, and oil price in Redis with 24h TTL.

    Returns:
        Dict with status.
    """
    r = _get_redis_client()
    asyncio.run(_fetch_and_cache_fred(r))
    logger.info("Synced FRED indicators")
    return {"status": "ok", "series": _FRED_SERIES}


@celery_app.task(
    name="backend.tasks.warm_data.sync_institutional_holders_task",
)
def sync_institutional_holders_task() -> dict:
    """Fetch 13F institutional holders for all watched tickers.

    Runs weekly on Sunday at 2 AM ET via Celery Beat. Caches results
    in Redis with a 7-day TTL.

    Returns:
        Dict with count of tickers processed.
    """
    tickers = _get_watched_tickers()
    r = _get_redis_client()

    async def _run() -> None:
        for ticker in tickers:
            await _fetch_and_cache_holders(ticker, r)

    asyncio.run(_run())
    logger.info("Synced institutional holders for %d tickers", len(tickers))
    return {"tickers_processed": len(tickers), "tickers": tickers}
