"""ObservabilityCollector — in-memory real-time metrics for agent pipeline.

Tracks LLM request counts, cascade events, per-model latency, and
health classification. Optionally writes events to LLMCallLog and
ToolExecutionLog tables asynchronously (fire-and-forget).
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from typing import Any

logger = logging.getLogger(__name__)

_RPM_WINDOW_S = 60
_HEALTH_WINDOW_S = 300  # 5 minutes
_LATENCY_MAXLEN = 100
_CASCADE_LOG_MAXLEN = 1000


class ObservabilityCollector:
    """Async-safe in-memory metrics collector for LLM and tool events."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._requests_by_model: dict[str, int] = {}
        self._cascade_count: int = 0
        self._cascades_by_model: dict[str, int] = {}
        self._rpm_windows: dict[str, deque[float]] = {}
        self._failures_windows: dict[str, deque[float]] = {}
        self._successes_windows: dict[str, deque[float]] = {}
        self._latency_by_model: dict[str, deque[int]] = {}
        self._cascade_log: deque[dict[str, Any]] = deque(maxlen=_CASCADE_LOG_MAXLEN)
        self._disabled_models: set[str] = set()
        self._db_writer: Any = None

    def set_db_writer(self, writer: Any) -> None:
        """Inject the async DB write function (set during app lifespan)."""
        self._db_writer = writer

    async def record_request(
        self,
        model: str,
        provider: str,
        tier: str,
        latency_ms: int,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> None:
        """Record a successful LLM request."""
        now = time.monotonic()
        async with self._lock:
            self._requests_by_model[model] = self._requests_by_model.get(model, 0) + 1
            if model not in self._rpm_windows:
                self._rpm_windows[model] = deque()
            self._rpm_windows[model].append(now)
            if model not in self._successes_windows:
                self._successes_windows[model] = deque()
            self._successes_windows[model].append(now)
            if model not in self._latency_by_model:
                self._latency_by_model[model] = deque(maxlen=_LATENCY_MAXLEN)
            self._latency_by_model[model].append(latency_ms)

        if self._db_writer:
            asyncio.create_task(
                self._safe_db_write(
                    "llm_call",
                    {
                        "provider": provider,
                        "model": model,
                        "tier": tier,
                        "latency_ms": latency_ms,
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "error": None,
                    },
                )
            )

    async def record_cascade(
        self,
        from_model: str,
        reason: str,
        provider: str,
        tier: str,
    ) -> None:
        """Record a cascade event (model skipped)."""
        now = time.monotonic()
        async with self._lock:
            self._cascade_count += 1
            self._cascades_by_model[from_model] = self._cascades_by_model.get(from_model, 0) + 1
            if from_model not in self._failures_windows:
                self._failures_windows[from_model] = deque()
            self._failures_windows[from_model].append(now)
            self._cascade_log.append(
                {
                    "model": from_model,
                    "reason": reason,
                    "provider": provider,
                    "tier": tier,
                    "timestamp": now,
                }
            )

        if self._db_writer:
            asyncio.create_task(
                self._safe_db_write(
                    "llm_call",
                    {
                        "provider": provider,
                        "model": from_model,
                        "tier": tier,
                        "latency_ms": None,
                        "prompt_tokens": None,
                        "completion_tokens": None,
                        "error": reason,
                    },
                )
            )

    async def record_tool_execution(
        self,
        tool_name: str,
        latency_ms: int,
        status: str,
        result_size_bytes: int | None = None,
        params: dict | None = None,
        error: str | None = None,
    ) -> None:
        """Record a tool execution event (fire-and-forget DB write only)."""
        if self._db_writer:
            asyncio.create_task(
                self._safe_db_write(
                    "tool_execution",
                    {
                        "tool_name": tool_name,
                        "latency_ms": latency_ms,
                        "status": status,
                        "result_size_bytes": result_size_bytes,
                        "params": params,
                        "error": error,
                    },
                )
            )

    def toggle_model(self, model: str, *, enabled: bool) -> None:
        """Enable or disable a model at runtime (admin action)."""
        if enabled:
            self._disabled_models.discard(model)
        else:
            self._disabled_models.add(model)

    def get_stats(self) -> dict[str, Any]:
        """Return current in-memory metrics snapshot."""
        now = time.monotonic()
        rpm: dict[str, int] = {}
        for model, window in self._rpm_windows.items():
            self._prune_window(window, now, _RPM_WINDOW_S)
            rpm[model] = len(window)
        return {
            "requests_by_model": dict(self._requests_by_model),
            "cascade_count": self._cascade_count,
            "cascades_by_model": dict(self._cascades_by_model),
            "rpm_by_model": rpm,
            "cascade_log": list(self._cascade_log)[-50:],
        }

    def get_tier_health(self) -> dict[str, Any]:
        """Return per-model health classification with latency stats."""
        now = time.monotonic()
        tiers: list[dict[str, Any]] = []
        all_models = (
            set(self._requests_by_model.keys())
            | set(self._cascades_by_model.keys())
            | self._disabled_models
        )
        for model in sorted(all_models):
            failures = self._failures_windows.get(model, deque())
            self._prune_window(failures, now, _HEALTH_WINDOW_S)
            successes = self._successes_windows.get(model, deque())
            self._prune_window(successes, now, _HEALTH_WINDOW_S)
            if model in self._disabled_models:
                status = "disabled"
            elif len(failures) >= 4:
                status = "down"
            elif len(failures) >= 1:
                status = "degraded"
            else:
                status = "healthy"
            latencies = list(self._latency_by_model.get(model, []))
            if latencies:
                avg_ms = sum(latencies) // len(latencies)
                sorted_lat = sorted(latencies)
                p95_idx = int(len(sorted_lat) * 0.95)
                p95_ms = sorted_lat[min(p95_idx, len(sorted_lat) - 1)]
            else:
                avg_ms = 0
                p95_ms = 0
            tiers.append(
                {
                    "model": model,
                    "status": status,
                    "failures_5m": len(failures),
                    "successes_5m": len(successes),
                    "cascade_count": self._cascades_by_model.get(model, 0),
                    "latency": {"avg_ms": avg_ms, "p95_ms": p95_ms},
                }
            )
        summary = {
            "total": len(tiers),
            "healthy": sum(1 for t in tiers if t["status"] == "healthy"),
            "degraded": sum(1 for t in tiers if t["status"] == "degraded"),
            "down": sum(1 for t in tiers if t["status"] == "down"),
            "disabled": sum(1 for t in tiers if t["status"] == "disabled"),
        }
        return {"tiers": tiers, "summary": summary}

    async def _safe_db_write(self, event_type: str, data: dict) -> None:
        """Write to DB, swallowing all errors."""
        try:
            await self._db_writer(event_type, data)
        except Exception:
            logger.warning("Failed to write %s event to DB", event_type, exc_info=True)

    @staticmethod
    def _prune_window(window: deque, now: float, max_age_s: float) -> None:
        """Remove entries older than max_age_s from a timestamp deque."""
        cutoff = now - max_age_s
        while window and window[0] < cutoff:
            window.popleft()
