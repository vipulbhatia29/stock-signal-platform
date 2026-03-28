"""Async sliding-window token and request budget tracker (Redis-backed).

Tracks tokens-per-minute (TPM), requests-per-minute (RPM),
tokens-per-day (TPD), and requests-per-day (RPD) per model.
Uses Redis sorted sets for multi-worker safety.

Usage:
    redis = await get_redis()
    budget = TokenBudget(redis=redis, limits={"model": ModelLimits(...)})
    if await budget.can_afford("model", estimated_tokens):
        response = await provider.chat(...)
        await budget.record("model", actual_tokens)
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

_MINUTE = 60
_DAY = 86_400
_THRESHOLD = 0.80
_KEY_PREFIX = "budget"

# Lua: prune expired entries, return sum of values still in set.
# Members are stored as "uuid:count" strings; score = wall-clock timestamp.
_LUA_PRUNE_AND_SUM = """
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', ARGV[1])
local members = redis.call('ZRANGEBYSCORE', KEYS[1], '-inf', '+inf')
local total = 0
for _, v in ipairs(members) do
    local count = tonumber(string.match(v, ':(%d+)$'))
    if count then total = total + count end
end
return total
"""

# Lua: add a member and set TTL on the key.
_LUA_RECORD = """
redis.call('ZADD', KEYS[1], ARGV[1], ARGV[2])
redis.call('EXPIRE', KEYS[1], tonumber(ARGV[3]))
return 1
"""


@dataclass(frozen=True)
class ModelLimits:
    """Rate limits for a single model."""

    tpm: int
    rpm: int
    tpd: int
    rpd: int


class TokenBudget:
    """Async sliding-window rate tracker for multiple models (Redis-backed).

    Fail-open: if Redis is unavailable the request is allowed.
    """

    def __init__(
        self,
        redis: aioredis.Redis | None = None,
        limits: dict[str, ModelLimits] | None = None,
    ) -> None:
        self._redis = redis
        self._limits: dict[str, ModelLimits] = dict(limits or {})
        self._prune_sha: str | None = None
        self._record_sha: str | None = None

    def set_redis(self, redis: aioredis.Redis) -> None:
        """Inject Redis client (called during app lifespan)."""
        self._redis = redis

    def load_limits(self, models: list[Any]) -> None:
        """Populate limits from ModelConfig list."""
        for m in models:
            if m.tpm_limit is not None:
                self._limits[m.model_name] = ModelLimits(
                    tpm=m.tpm_limit,
                    rpm=m.rpm_limit or 30,
                    tpd=m.tpd_limit or 100_000,
                    rpd=m.rpd_limit or 1_000,
                )

    @staticmethod
    def estimate_tokens(messages: list[dict[str, Any] | Any]) -> int:
        """Estimate token count. Heuristic: len(text) // 4 * 1.2."""
        total_chars = 0
        for msg in messages:
            content = (
                msg.get("content", "") if isinstance(msg, dict) else getattr(msg, "content", "")
            )
            if isinstance(content, str):
                total_chars += len(content)
        raw = total_chars // 4
        return int(raw * 1.20)

    async def can_afford(self, model: str, estimated_tokens: int) -> bool:
        """Check whether model has budget. Uses 80% threshold."""
        lim = self._limits.get(model)
        if lim is None:
            return True

        if self._redis is None:
            return True

        try:
            now = time.time()
            prune_sha = await self._ensure_prune_script()

            tpm_used = int(
                await self._redis.evalsha(
                    prune_sha, 1, self._key(model, "minute_tokens"), str(now - _MINUTE)
                )
            )
            rpm_used = int(
                await self._redis.evalsha(
                    prune_sha, 1, self._key(model, "minute_requests"), str(now - _MINUTE)
                )
            )
            tpd_used = int(
                await self._redis.evalsha(
                    prune_sha, 1, self._key(model, "day_tokens"), str(now - _DAY)
                )
            )
            rpd_used = int(
                await self._redis.evalsha(
                    prune_sha, 1, self._key(model, "day_requests"), str(now - _DAY)
                )
            )

            if tpm_used + estimated_tokens > lim.tpm * _THRESHOLD:
                return False
            if rpm_used + 1 > lim.rpm * _THRESHOLD:
                return False
            if tpd_used + estimated_tokens > lim.tpd * _THRESHOLD:
                return False
            if rpd_used + 1 > lim.rpd * _THRESHOLD:
                return False
            return True
        except Exception:
            self._invalidate_scripts()
            logger.warning("Redis error in can_afford — failing open", exc_info=True)
            return True

    async def record(self, model: str, tokens_used: int) -> None:
        """Record a completed request to Redis sorted sets."""
        if self._redis is None:
            return

        try:
            now = time.time()
            now_str = str(now)
            entry_id = uuid.uuid4().hex[:12]
            record_sha = await self._ensure_record_script()

            token_member = f"{entry_id}:{tokens_used}"
            request_member = f"{entry_id}:1"

            await self._redis.evalsha(
                record_sha,
                1,
                self._key(model, "minute_tokens"),
                now_str,
                token_member,
                str(_MINUTE + 10),
            )
            await self._redis.evalsha(
                record_sha,
                1,
                self._key(model, "minute_requests"),
                now_str,
                request_member,
                str(_MINUTE + 10),
            )
            await self._redis.evalsha(
                record_sha,
                1,
                self._key(model, "day_tokens"),
                now_str,
                token_member,
                str(_DAY + 60),
            )
            await self._redis.evalsha(
                record_sha,
                1,
                self._key(model, "day_requests"),
                now_str,
                request_member,
                str(_DAY + 60),
            )
        except Exception:
            self._invalidate_scripts()
            logger.warning("Redis error in record — usage may be under-counted", exc_info=True)

    def _invalidate_scripts(self) -> None:
        """Clear cached Lua script SHAs so they are re-registered on next call.

        Handles NOSCRIPT errors after a Redis restart.
        """
        self._prune_sha = None
        self._record_sha = None

    async def _ensure_prune_script(self) -> str:
        """Load and cache the prune-and-sum Lua script SHA."""
        if self._prune_sha is None:
            self._prune_sha = await self._redis.script_load(_LUA_PRUNE_AND_SUM)  # type: ignore[union-attr]
        return self._prune_sha

    async def _ensure_record_script(self) -> str:
        """Load and cache the record Lua script SHA."""
        if self._record_sha is None:
            self._record_sha = await self._redis.script_load(_LUA_RECORD)  # type: ignore[union-attr]
        return self._record_sha

    @staticmethod
    def _key(model: str, window: str) -> str:
        """Build Redis key for a model's sliding window."""
        return f"{_KEY_PREFIX}:{model}:{window}"
