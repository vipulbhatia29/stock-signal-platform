"""Shared async Redis connection pool.

Single pool used by CacheService, token_blocklist, rate_limiter.
"""

from __future__ import annotations

import redis.asyncio as aioredis

from backend.config import settings

_pool: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    """Get or create the shared async Redis client."""
    global _pool  # noqa: PLW0603
    if _pool is None:
        _pool = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _pool


async def close_redis() -> None:
    """Close Redis pool on shutdown."""
    global _pool  # noqa: PLW0603
    if _pool is not None:
        await _pool.aclose()
        _pool = None
