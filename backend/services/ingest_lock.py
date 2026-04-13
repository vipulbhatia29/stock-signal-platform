"""Redis-backed ingest dedup lock (Spec C.6)."""

from __future__ import annotations

import logging

from backend.services.redis_pool import get_redis

logger = logging.getLogger(__name__)

IN_FLIGHT_KEY = "ingest:in_flight:{ticker}"
LOCK_TTL_SECONDS = 60


async def acquire_ingest_lock(ticker: str) -> bool:
    """SETNX with 60s TTL. Returns True if lock acquired.

    Fail-open: returns True if Redis is unavailable (dedup is an optimisation,
    not a correctness requirement).

    Args:
        ticker: Stock ticker symbol (uppercased internally).

    Returns:
        True if the lock was acquired (or Redis is unavailable), False if the
        lock is already held by another caller.
    """
    try:
        redis = await get_redis()
        return bool(
            await redis.set(
                IN_FLIGHT_KEY.format(ticker=ticker.upper()),
                "1",
                ex=LOCK_TTL_SECONDS,
                nx=True,
            )
        )
    except Exception:
        logger.warning("Redis unavailable for ingest lock %s", ticker, exc_info=True)
        return True  # fail-open


async def release_ingest_lock(ticker: str) -> None:
    """Delete the lock key after ingest completes or fails.

    Silently ignores Redis errors — a TTL of 60 s ensures the key
    self-expires even if the explicit delete is skipped.

    Args:
        ticker: Stock ticker symbol (uppercased internally).
    """
    try:
        redis = await get_redis()
        await redis.delete(IN_FLIGHT_KEY.format(ticker=ticker.upper()))
    except Exception:
        logger.warning("Redis unavailable for lock release %s", ticker, exc_info=True)
