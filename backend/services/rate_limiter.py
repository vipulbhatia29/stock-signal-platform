"""Redis-backed token bucket rate limiter for outbound API calls.

Uses an atomic Lua script for correctness across concurrent workers.
Falls back to permissive (allow all) when Redis is unavailable or errors.
"""

from __future__ import annotations

import asyncio
import logging
import time

from redis.exceptions import ResponseError

from backend.services.redis_pool import get_redis

logger = logging.getLogger(__name__)

_LUA_TOKEN_BUCKET = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])

local data = redis.call("HMGET", key, "tokens", "last_refill")
local tokens = tonumber(data[1]) or capacity
local last = tonumber(data[2]) or now

local elapsed = math.max(0, now - last)
tokens = math.min(capacity, tokens + elapsed * refill_rate)

if tokens >= 1 then
    tokens = tokens - 1
    redis.call("HMSET", key, "tokens", tokens, "last_refill", now)
    redis.call("EXPIRE", key, math.ceil(capacity / refill_rate) + 60)
    return 1
else
    return 0
end
"""


class TokenBucketLimiter:
    """Atomic Redis token bucket rate limiter.

    This is a **best-effort throttler**. Callers do not need to check the return
    value of ``acquire()`` — the purpose is to slow down outbound calls, not to
    hard-block them. If Redis is down or the bucket is exhausted, the call
    proceeds anyway (permissive fallback).

    Args:
        name: Unique limiter name (used as Redis key suffix).
        capacity: Maximum burst size (tokens).
        refill_per_sec: Tokens added per second.
    """

    def __init__(self, name: str, capacity: int, refill_per_sec: float) -> None:
        self.name = name
        self.capacity = capacity
        self.refill_per_sec = refill_per_sec
        self._sha: str | None = None

    async def acquire(self, timeout: float = 30.0) -> bool:
        """Acquire a token, blocking up to timeout seconds.

        Returns:
            True if token acquired or Redis unavailable (permissive fallback).
            False if timed out waiting for a token.
        """
        try:
            redis = await get_redis()
        except Exception:
            logger.warning("Rate limiter cannot reach Redis for %s", self.name, exc_info=True)
            return True

        key = f"ratelimit:{self.name}"
        deadline = time.monotonic() + timeout
        backoff = 1.0 / self.refill_per_sec

        while time.monotonic() < deadline:
            # Load/reload Lua script if needed (e.g. after Redis restart)
            if self._sha is None:
                try:
                    self._sha = await redis.script_load(_LUA_TOKEN_BUCKET)
                except Exception:
                    logger.warning(
                        "Rate limiter script_load failed for %s", self.name, exc_info=True
                    )
                    return True

            try:
                ok = await redis.evalsha(
                    self._sha,
                    1,
                    key,
                    str(self.capacity),
                    str(self.refill_per_sec),
                    str(time.time()),
                )
                if int(ok) == 1:
                    return True
            except ResponseError as exc:
                if "NOSCRIPT" in str(exc):
                    self._sha = None  # Force reload on next iteration
                    continue
                logger.warning("Rate limiter Redis error for %s", self.name, exc_info=True)
                return True
            except Exception:
                logger.warning("Rate limiter Redis error for %s", self.name, exc_info=True)
                return True  # Permissive on error

            sleep_dur = max(0.0, min(backoff, deadline - time.monotonic()))
            await asyncio.sleep(sleep_dur)

        logger.warning("Rate limiter timeout for %s after %.1fs", self.name, timeout)
        return False


# ── Named singleton instances ─────────────────────────────────────────────────

yfinance_limiter = TokenBucketLimiter("yfinance", capacity=30, refill_per_sec=0.5)
finnhub_limiter = TokenBucketLimiter("finnhub", capacity=60, refill_per_sec=1.0)
edgar_limiter = TokenBucketLimiter("edgar", capacity=10, refill_per_sec=10.0)
google_news_limiter = TokenBucketLimiter("google_news", capacity=20, refill_per_sec=0.33)
fed_limiter = TokenBucketLimiter("fed", capacity=5, refill_per_sec=0.5)
