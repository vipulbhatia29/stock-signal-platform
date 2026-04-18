"""ObservabilityCollector — DB-backed metrics for agent pipeline.

Write path: fire-and-forget async inserts into LLMCallLog / ToolExecutionLog
(unchanged from the original in-memory design).

Read path (get_stats, get_tier_health, fallback_rate): queries the
llm_call_log table — the single source of truth across all workers.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from uuid_utils import uuid7

from backend.config import settings
from backend.models.logs import LLMCallLog
from backend.observability.bootstrap import _maybe_get_obs_client
from backend.observability.context import current_span_id, current_trace_id
from backend.observability.schema.legacy_events import LLMCallEvent

logger = logging.getLogger(__name__)

_CASCADE_LOG_MAXLEN = 1000
_HEALTH_WINDOW_S = 300  # 5 minutes
_RPM_WINDOW_S = 60


class ObservabilityCollector:
    """Metrics collector for LLM and tool events.

    Writes are fire-and-forget (unchanged).
    Reads query the llm_call_log table for cross-worker accuracy.
    """

    def __init__(self) -> None:
        self._disabled_models: set[str] = set()
        self._db_writer: Any = None
        # In-memory cascade log kept for quick admin debugging (bounded deque)
        self._cascade_log: deque[dict[str, Any]] = deque(maxlen=_CASCADE_LOG_MAXLEN)

    def set_db_writer(self, writer: Any) -> None:
        """Inject the async DB write function (set during app lifespan)."""
        self._db_writer = writer

    # ------------------------------------------------------------------
    # Write path — fire-and-forget (unchanged)
    # ------------------------------------------------------------------

    async def record_request(
        self,
        model: str,
        provider: str,
        tier: str,
        latency_ms: int,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: float | None = None,
        loop_step: int | None = None,
        status: str = "completed",
        langfuse_trace_id: uuid.UUID | str | None = None,
    ) -> None:
        """Record a successful LLM request."""
        wrote_via_legacy = settings.OBS_LEGACY_DIRECT_WRITES  # snapshot NOW
        if wrote_via_legacy and self._db_writer:
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
                        "cost_usd": cost_usd,
                        "loop_step": loop_step,
                        "status": status,
                        "langfuse_trace_id": langfuse_trace_id,
                    },
                )
            )

        # SDK emission — always (no-op when OBS_ENABLED=false)
        obs_client = _maybe_get_obs_client()
        if obs_client is not None:
            event = LLMCallEvent(
                trace_id=current_trace_id() or UUID(bytes=uuid7().bytes),
                span_id=UUID(bytes=uuid7().bytes),
                parent_span_id=current_span_id(),
                ts=datetime.now(timezone.utc),
                env=getattr(settings, "APP_ENV", "dev"),
                git_sha=None,
                user_id=None,
                session_id=None,
                query_id=None,
                wrote_via_legacy=wrote_via_legacy,
                model=model,
                provider=provider,
                tier=tier,
                latency_ms=latency_ms,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_usd=cost_usd,
                loop_step=loop_step,
                status=status,
                langfuse_trace_id=langfuse_trace_id,
            )
            await obs_client.emit(event)

    async def record_cascade(
        self,
        from_model: str,
        reason: str,
        provider: str,
        tier: str,
    ) -> None:
        """Record a cascade event (model skipped)."""
        self._cascade_log.append(
            {
                "model": from_model,
                "reason": reason,
                "provider": provider,
                "tier": tier,
                "timestamp": time.time(),
            }
        )

        wrote_via_legacy = settings.OBS_LEGACY_DIRECT_WRITES  # snapshot NOW
        if wrote_via_legacy and self._db_writer:
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
                        "status": "error",
                    },
                )
            )

        # SDK emission — always (no-op when OBS_ENABLED=false)
        obs_client = _maybe_get_obs_client()
        if obs_client is not None:
            event = LLMCallEvent(
                trace_id=current_trace_id() or UUID(bytes=uuid7().bytes),
                span_id=UUID(bytes=uuid7().bytes),
                parent_span_id=current_span_id(),
                ts=datetime.now(timezone.utc),
                env=getattr(settings, "APP_ENV", "dev"),
                git_sha=None,
                user_id=None,
                session_id=None,
                query_id=None,
                wrote_via_legacy=wrote_via_legacy,
                model=from_model,
                provider=provider,
                tier=tier,
                latency_ms=None,
                prompt_tokens=None,
                completion_tokens=None,
                error=reason,
                status="error",
            )
            await obs_client.emit(event)

    async def record_tool_execution(
        self,
        tool_name: str,
        latency_ms: int,
        status: str,
        result_size_bytes: int | None = None,
        params: dict | None = None,
        error: str | None = None,
        cache_hit: bool = False,
        loop_step: int | None = None,
        result: Any = None,
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
                        "cache_hit": cache_hit,
                        "loop_step": loop_step,
                        "result": result,
                    },
                )
            )

    def toggle_model(self, model: str, *, enabled: bool) -> None:
        """Enable or disable a model at runtime (admin action, in-memory)."""
        if enabled:
            self._disabled_models.discard(model)
        else:
            self._disabled_models.add(model)

    # ------------------------------------------------------------------
    # Read path — queries llm_call_log (cross-worker ground truth)
    # ------------------------------------------------------------------

    async def get_stats(self, db: AsyncSession) -> dict[str, Any]:
        """Return metrics snapshot from the llm_call_log table."""
        cutoff_60s = text("now() - interval '60 seconds'")

        # Total requests by model (all time)
        req_stmt = (
            select(LLMCallLog.model, func.count().label("cnt"))
            .where(LLMCallLog.error.is_(None))
            .group_by(LLMCallLog.model)
        )
        req_result = await db.execute(req_stmt)
        requests_by_model = {r.model: r.cnt for r in req_result.all()}

        # Total cascade count + per-model
        casc_stmt = (
            select(LLMCallLog.model, func.count().label("cnt"))
            .where(LLMCallLog.error.is_not(None))
            .group_by(LLMCallLog.model)
        )
        casc_result = await db.execute(casc_stmt)
        cascades_by_model = {r.model: r.cnt for r in casc_result.all()}
        cascade_count = sum(cascades_by_model.values())

        # RPM by model (last 60s, successes only)
        rpm_stmt = (
            select(LLMCallLog.model, func.count().label("cnt"))
            .where(LLMCallLog.error.is_(None), LLMCallLog.created_at >= cutoff_60s)
            .group_by(LLMCallLog.model)
        )
        rpm_result = await db.execute(rpm_stmt)
        rpm_by_model = {r.model: r.cnt for r in rpm_result.all()}

        return {
            "requests_by_model": requests_by_model,
            "cascade_count": cascade_count,
            "cascades_by_model": cascades_by_model,
            "rpm_by_model": rpm_by_model,
            "cascade_log": list(self._cascade_log)[-50:],
        }

    async def get_tier_health(self, db: AsyncSession) -> dict[str, Any]:
        """Return per-model health classification from the DB."""
        cutoff_5m = text("now() - interval '5 minutes'")

        # Failures in last 5 min by model
        fail_stmt = (
            select(LLMCallLog.model, func.count().label("cnt"))
            .where(LLMCallLog.error.is_not(None), LLMCallLog.created_at >= cutoff_5m)
            .group_by(LLMCallLog.model)
        )
        fail_result = await db.execute(fail_stmt)
        failures_5m = {r.model: r.cnt for r in fail_result.all()}

        # Successes in last 5 min by model
        succ_stmt = (
            select(LLMCallLog.model, func.count().label("cnt"))
            .where(LLMCallLog.error.is_(None), LLMCallLog.created_at >= cutoff_5m)
            .group_by(LLMCallLog.model)
        )
        succ_result = await db.execute(succ_stmt)
        successes_5m = {r.model: r.cnt for r in succ_result.all()}

        # Latency stats (last 100 per model)
        latency_stmt = (
            select(
                LLMCallLog.model,
                func.avg(LLMCallLog.latency_ms).label("avg_ms"),
                func.percentile_cont(0.95).within_group(LLMCallLog.latency_ms).label("p95_ms"),
            )
            .where(LLMCallLog.error.is_(None), LLMCallLog.latency_ms.is_not(None))
            .group_by(LLMCallLog.model)
        )
        lat_result = await db.execute(latency_stmt)
        latency_map: dict[str, dict[str, int]] = {}
        for r in lat_result.all():
            latency_map[r.model] = {
                "avg_ms": round(r.avg_ms) if r.avg_ms else 0,
                "p95_ms": round(r.p95_ms) if r.p95_ms else 0,
            }

        # All-time cascade count by model (for the cascade_count field)
        all_casc_stmt = (
            select(LLMCallLog.model, func.count().label("cnt"))
            .where(LLMCallLog.error.is_not(None))
            .group_by(LLMCallLog.model)
        )
        all_casc_result = await db.execute(all_casc_stmt)
        all_cascades = {r.model: r.cnt for r in all_casc_result.all()}

        all_models = set(failures_5m) | set(successes_5m) | set(latency_map) | self._disabled_models
        tiers: list[dict[str, Any]] = []
        for model in sorted(all_models):
            fail_count = failures_5m.get(model, 0)
            if model in self._disabled_models:
                status = "disabled"
            elif fail_count >= 4:
                status = "down"
            elif fail_count >= 1:
                status = "degraded"
            else:
                status = "healthy"
            tiers.append(
                {
                    "model": model,
                    "status": status,
                    "failures_5m": fail_count,
                    "successes_5m": successes_5m.get(model, 0),
                    "cascade_count": all_cascades.get(model, 0),
                    "latency": latency_map.get(model, {"avg_ms": 0, "p95_ms": 0}),
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

    async def fallback_rate_last_60s(self, db: AsyncSession) -> float:
        """Fraction of LLM calls that cascaded in the last 60 seconds."""
        cutoff = text("now() - interval '60 seconds'")

        stmt = select(
            func.count().label("total"),
            func.count().filter(LLMCallLog.error.is_not(None)).label("failures"),
        ).where(LLMCallLog.created_at >= cutoff)

        result = await db.execute(stmt)
        row = result.one()
        total = row.total or 0
        if total == 0:
            return 0.0
        return (row.failures or 0) / total

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _safe_db_write(self, event_type: str, data: dict) -> None:
        """Write to DB, swallowing all errors."""
        try:
            await self._db_writer(event_type, data)
        except Exception:
            logger.warning("Failed to write %s event to DB", event_type, exc_info=True)
