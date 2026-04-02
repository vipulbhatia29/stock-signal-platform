"""Event-driven cache invalidation. Trigger-agnostic — same logic whether
called from nightly pipeline, admin dashboard, or user action."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = logging.getLogger(__name__)


class CacheInvalidator:
    """Single source of truth for cache invalidation rules.

    Injected as FastAPI dependency for request lifecycle.
    Imported directly in Celery tasks.

    All methods are fire-and-forget: Redis failures log a warning
    but never propagate exceptions to callers.
    """

    def __init__(self, redis: Redis) -> None:
        """Initialize with Redis client.

        Args:
            redis: Async Redis client.
        """
        self._redis = redis

    async def on_prices_updated(self, tickers: list[str]) -> None:
        """Price data changed. Clear convergence + forecast + sector caches.

        Does NOT clear BL/MC/CVaR — those have 1hr TTL (natural expiry).
        """
        try:
            keys = []
            for t in tickers:
                keys.extend(
                    [
                        f"app:convergence:{t}",
                        f"app:convergence:rationale:{t}",
                        f"app:forecast:{t}",
                    ]
                )
            if keys:
                await self._redis.delete(*keys)
            await self._clear_pattern("app:sector-forecast:*")
            logger.info("Cache invalidated for %d tickers (prices)", len(tickers))
        except Exception:
            logger.warning("Cache invalidation failed (prices)", exc_info=True)

    async def on_signals_updated(self, tickers: list[str]) -> None:
        """Signal snapshots recomputed."""
        try:
            keys = []
            for t in tickers:
                keys.extend(
                    [
                        f"app:convergence:{t}",
                        f"app:convergence:rationale:{t}",
                    ]
                )
            if keys:
                await self._redis.delete(*keys)
            logger.info("Cache invalidated for %d tickers (signals)", len(tickers))
        except Exception:
            logger.warning("Cache invalidation failed (signals)", exc_info=True)

    async def on_stock_ingested(self, ticker: str) -> None:
        """Brand new stock added. Nothing to invalidate — warm proactively."""
        logger.info("New stock ingested: %s — cache warming deferred", ticker)

    async def on_forecast_updated(self, tickers: list[str]) -> None:
        """Forecasts regenerated. Clears forecast, convergence, sector, and BL caches."""
        try:
            keys = []
            for t in tickers:
                keys.extend(
                    [
                        f"app:forecast:{t}",
                        f"app:convergence:{t}",
                        f"app:convergence:rationale:{t}",
                    ]
                )
            if keys:
                await self._redis.delete(*keys)
            # Sector + BL caches — clear all (can't map ticker→sector/user here)
            await self._clear_pattern("app:sector-forecast:*")
            await self._clear_pattern("app:bl-forecast:*")
            logger.info("Cache invalidated for %d tickers (forecasts)", len(tickers))
        except Exception:
            logger.warning("Cache invalidation failed (forecasts)", exc_info=True)

    async def on_backtest_completed(self, tickers: list[str]) -> None:
        """Backtest results updated."""
        try:
            keys = [f"app:backtest:{t}" for t in tickers]
            if keys:
                await self._redis.delete(*keys)
            logger.info("Cache invalidated for %d tickers (backtest)", len(tickers))
        except Exception:
            logger.warning("Cache invalidation failed (backtest)", exc_info=True)

    async def on_sentiment_scored(self, tickers: list[str]) -> None:
        """New sentiment scores available."""
        try:
            keys = []
            for t in tickers:
                keys.extend(
                    [
                        f"app:sentiment:{t}",
                        f"app:convergence:{t}",
                        f"app:convergence:rationale:{t}",
                    ]
                )
            if keys:
                await self._redis.delete(*keys)
            logger.info("Cache invalidated for %d tickers (sentiment)", len(tickers))
        except Exception:
            logger.warning("Cache invalidation failed (sentiment)", exc_info=True)

    async def on_portfolio_changed(self, user_id: str) -> None:
        """User added/removed positions."""
        try:
            await self._redis.delete(
                f"app:bl-forecast:{user_id}",
                f"app:monte-carlo:{user_id}",
                f"app:cvar:{user_id}",
            )
            logger.info("Cache invalidated for user %s (portfolio)", user_id)
        except Exception:
            logger.warning("Cache invalidation failed (portfolio)", exc_info=True)

    async def _clear_pattern(self, pattern: str) -> int:
        """Clear keys matching pattern using SCAN (never KEYS).

        Args:
            pattern: Redis glob pattern to match.

        Returns:
            Number of keys deleted.
        """
        deleted = 0
        cursor = 0
        while True:
            cursor, keys = await self._redis.scan(cursor, match=pattern, count=100)
            if keys:
                await self._redis.delete(*keys)
                deleted += len(keys)
            if cursor == 0:
                break
        return deleted
