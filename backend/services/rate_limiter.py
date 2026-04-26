"""Redis-backed token bucket rate limiter for outbound API calls.

Uses an atomic Lua script for correctness across concurrent workers.
Falls back to permissive (allow all) when Redis is unavailable or errors.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone

from redis.exceptions import ResponseError

from backend.services.redis_pool import get_redis

logger = logging.getLogger(__name__)


def _emit_rate_limiter_event(
    limiter_name: str,
    action: str,
    reason_if_fallback: str | None = None,
    wait_time_ms: int | None = None,
) -> None:
    """Emit a rate_limiter_event — never raises.

    All imports are done lazily to avoid circular imports at module load time
    (rate_limiter is imported early in the backend startup chain).

    Args:
        limiter_name: The name of the TokenBucketLimiter (e.g. ``"yfinance"``).
        action: One of ``"fallback_permissive"``, ``"timeout"``, ``"acquired"``.
        reason_if_fallback: Populated when ``action == "fallback_permissive"``; one of
            ``"redis_down"``, ``"script_load_failed"``, ``"redis_error"``, ``"unknown"``.
        wait_time_ms: How long the caller waited before this event (None for immediate fallbacks).
    """
    try:
        from backend.observability.bootstrap import _maybe_get_obs_client

        obs_client = _maybe_get_obs_client()
        if obs_client is None:
            return

        from uuid_utils import uuid7

        from backend.config import settings
        from backend.observability.context import current_span_id, current_trace_id
        from backend.observability.instrumentation.external_api import _map_env
        from backend.observability.schema.rate_limiter_events import RateLimiterEventPayload

        ambient_trace = current_trace_id()
        trace_id: uuid.UUID = (
            ambient_trace if ambient_trace is not None else uuid.UUID(bytes=uuid7().bytes)
        )
        span_id: uuid.UUID = uuid.UUID(bytes=uuid7().bytes)
        parent_span_id: uuid.UUID | None = current_span_id()

        event = RateLimiterEventPayload(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            ts=datetime.now(timezone.utc),
            env=_map_env(settings.ENVIRONMENT),  # type: ignore[arg-type]
            git_sha=getattr(settings, "GIT_SHA", None),
            user_id=None,
            session_id=None,
            query_id=None,
            limiter_name=limiter_name,
            action=action,  # type: ignore[arg-type]
            reason_if_fallback=reason_if_fallback,  # type: ignore[arg-type]
            wait_time_ms=wait_time_ms,
        )
        obs_client.emit_sync(event)
    except Exception:  # noqa: BLE001 — emission MUST NOT affect the rate limiter
        logger.warning("obs.rate_limiter.emit_failed", exc_info=True)


_LUA_TOKEN_BUCKET = """\
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
            _emit_rate_limiter_event(self.name, "fallback_permissive", "redis_down")
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
                    _emit_rate_limiter_event(self.name, "fallback_permissive", "script_load_failed")
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
                _emit_rate_limiter_event(self.name, "fallback_permissive", "redis_error")
                return True
            except Exception:
                logger.warning("Rate limiter Redis error for %s", self.name, exc_info=True)
                _emit_rate_limiter_event(self.name, "fallback_permissive", "redis_error")
                return True  # Permissive on error

            sleep_dur = max(0.0, min(backoff, deadline - time.monotonic()))
            await asyncio.sleep(sleep_dur)

        logger.warning("Rate limiter timeout for %s after %.1fs", self.name, timeout)
        _emit_rate_limiter_event(self.name, "timeout", wait_time_ms=int(timeout * 1000))
        return False


# ── Named singleton instances ─────────────────────────────────────────────────

yfinance_limiter = TokenBucketLimiter("yfinance", capacity=30, refill_per_sec=0.5)
finnhub_limiter = TokenBucketLimiter("finnhub", capacity=60, refill_per_sec=1.0)
edgar_limiter = TokenBucketLimiter("edgar", capacity=10, refill_per_sec=10.0)
google_news_limiter = TokenBucketLimiter("google_news", capacity=20, refill_per_sec=0.33)
fed_limiter = TokenBucketLimiter("fed", capacity=5, refill_per_sec=0.5)
