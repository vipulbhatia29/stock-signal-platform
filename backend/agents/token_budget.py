"""Async sliding-window token and request budget tracker.

Tracks tokens-per-minute (TPM), requests-per-minute (RPM),
tokens-per-day (TPD), and requests-per-day (RPD) per model.
Uses asyncio.Lock for async safety.

Usage:
    budget = TokenBudget(limits={"model": ModelLimits(...)})
    if await budget.can_afford("model", estimated_tokens):
        response = await provider.chat(...)
        await budget.record("model", actual_tokens)
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

_MINUTE = 60
_DAY = 86_400
_THRESHOLD = 0.80


@dataclass(frozen=True)
class ModelLimits:
    """Rate limits for a single model."""

    tpm: int
    rpm: int
    tpd: int
    rpd: int


@dataclass
class _ModelState:
    """Per-model sliding-window state."""

    minute_tokens: deque = field(default_factory=deque)
    minute_tokens_total: int = 0
    minute_requests: deque = field(default_factory=deque)
    minute_requests_total: int = 0
    day_tokens: deque = field(default_factory=deque)
    day_tokens_total: int = 0
    day_requests: deque = field(default_factory=deque)
    day_requests_total: int = 0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class TokenBudget:
    """Async sliding-window rate tracker for multiple models."""

    def __init__(self, limits: dict[str, ModelLimits] | None = None) -> None:
        self._limits: dict[str, ModelLimits] = dict(limits or {})
        self._state: dict[str, _ModelState] = {model: _ModelState() for model in self._limits}

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

        state = self._get_state(model)
        async with state.lock:
            now = time.monotonic()
            tpm_used = self._prune_window(state.minute_tokens, _MINUTE, now)
            state.minute_tokens_total = tpm_used
            rpm_used = self._prune_window(state.minute_requests, _MINUTE, now)
            state.minute_requests_total = rpm_used
            tpd_used = self._prune_window(state.day_tokens, _DAY, now)
            state.day_tokens_total = tpd_used
            rpd_used = self._prune_window(state.day_requests, _DAY, now)
            state.day_requests_total = rpd_used

            if tpm_used + estimated_tokens > lim.tpm * _THRESHOLD:
                return False
            if rpm_used + 1 > lim.rpm * _THRESHOLD:
                return False
            if tpd_used + estimated_tokens > lim.tpd * _THRESHOLD:
                return False
            if rpd_used + 1 > lim.rpd * _THRESHOLD:
                return False
            return True

    async def record(self, model: str, tokens_used: int) -> None:
        """Record a completed request."""
        state = self._get_state(model)
        now = time.monotonic()
        async with state.lock:
            state.minute_tokens.append((now, tokens_used))
            state.minute_tokens_total += tokens_used
            state.minute_requests.append((now, 1))
            state.minute_requests_total += 1
            state.day_tokens.append((now, tokens_used))
            state.day_tokens_total += tokens_used
            state.day_requests.append((now, 1))
            state.day_requests_total += 1

    def _get_state(self, model: str) -> _ModelState:
        """Get or create per-model state."""
        if model not in self._state:
            self._state[model] = _ModelState()
        return self._state[model]

    @staticmethod
    def _prune_window(log: deque, window_seconds: int, now: float) -> int:
        """Prune expired entries and return running total."""
        cutoff = now - window_seconds
        total = sum(count for _, count in log)
        while log and log[0][0] < cutoff:
            _, count = log.popleft()
            total -= count
        return total
