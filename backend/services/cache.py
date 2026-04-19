"""Redis cache service with namespaced keys and TTL tiers.

Cache-aside pattern: check Redis → miss → query DB → store → return.
Three key namespaces: app (shared), user (per-user), session (per-chat).
"""

from __future__ import annotations

import logging
import random
import time
from enum import Enum

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)


class CacheTier(str, Enum):
    """TTL tiers for different data volatility levels."""

    VOLATILE = "volatile"
    STANDARD = "standard"
    STABLE = "stable"
    SESSION = "session"

    @property
    def base_ttl(self) -> int:
        """Base TTL in seconds for this tier."""
        return {
            CacheTier.VOLATILE: 300,
            CacheTier.STANDARD: 1800,
            CacheTier.STABLE: 86400,
            CacheTier.SESSION: 7200,
        }[self]

    @property
    def ttl(self) -> int:
        """TTL with ±10% jitter (except SESSION which is fixed)."""
        base = self.base_ttl
        if self == CacheTier.SESSION:
            return base
        jitter = int(base * 0.1)
        return base + random.randint(-jitter, jitter)


class CacheService:
    """Async Redis cache with namespaced keys and TTL tiers."""

    def __init__(self, redis: aioredis.Redis) -> None:
        self._redis = redis

    async def get(self, key: str) -> str | None:
        """Get a value from cache. Returns None on miss."""
        start = time.monotonic()
        try:
            result = await self._redis.get(key)
            latency_ms = int((time.monotonic() - start) * 1000)
            try:
                from backend.observability.instrumentation.cache import observe_cache_get

                observe_cache_get(key, result, latency_ms)
            except Exception:  # noqa: BLE001
                pass
            return result
        except Exception:
            latency_ms = int((time.monotonic() - start) * 1000)
            try:
                from backend.observability.instrumentation.cache import observe_cache_error

                observe_cache_error("get", key, latency_ms)
            except Exception:  # noqa: BLE001
                pass
            logger.warning("Cache get failed for key=%s", key, exc_info=True)
            return None

    async def set(self, key: str, value: str, tier: CacheTier) -> None:
        """Set a value with TTL from the specified tier."""
        start = time.monotonic()
        ttl = tier.ttl
        try:
            await self._redis.set(key, value, ex=ttl)
            latency_ms = int((time.monotonic() - start) * 1000)
            try:
                from backend.observability.instrumentation.cache import observe_cache_set

                observe_cache_set(key, value, ttl, latency_ms)
            except Exception:  # noqa: BLE001
                pass
        except Exception:
            latency_ms = int((time.monotonic() - start) * 1000)
            try:
                from backend.observability.instrumentation.cache import observe_cache_error

                observe_cache_error("set", key, latency_ms)
            except Exception:  # noqa: BLE001
                pass
            logger.warning("Cache set failed for key=%s", key, exc_info=True)

    async def delete(self, key: str) -> None:
        """Delete a single cache key."""
        start = time.monotonic()
        try:
            await self._redis.delete(key)
            latency_ms = int((time.monotonic() - start) * 1000)
            try:
                from backend.observability.instrumentation.cache import observe_cache_delete

                observe_cache_delete(key, latency_ms)
            except Exception:  # noqa: BLE001
                pass
        except Exception:
            latency_ms = int((time.monotonic() - start) * 1000)
            try:
                from backend.observability.instrumentation.cache import observe_cache_error

                observe_cache_error("delete", key, latency_ms)
            except Exception:  # noqa: BLE001
                pass
            logger.warning("Cache delete failed for key=%s", key, exc_info=True)

    async def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching a pattern using SCAN (production-safe)."""
        deleted = 0
        try:
            cursor = 0
            while True:
                cursor, keys = await self._redis.scan(cursor=cursor, match=pattern, count=100)
                if keys:
                    await self._redis.delete(*keys)
                    deleted += len(keys)
                if cursor == 0:
                    break
        except Exception:
            logger.warning("Cache delete_pattern failed for %s", pattern, exc_info=True)
        return deleted

    async def invalidate_ticker(self, ticker: str) -> int:
        """Invalidate all cached data for a ticker."""
        t = ticker.upper()
        total = 0
        for prefix in ("app:signals:", "app:price:", "app:fundamentals:", "app:forecast:"):
            await self.delete(f"{prefix}{t}")
            total += 1
        extra = await self.delete_pattern(f"app:*:{t}")
        return total + extra

    async def invalidate_user(self, user_id: str) -> int:
        """Invalidate all cached data for a user."""
        return await self.delete_pattern(f"user:{user_id}:*")
