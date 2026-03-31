"""Health checks for Celery, Langfuse, and TokenBudget.

All functions are safe — they never raise, returning degraded defaults on error.
Results are cached at module level with configurable TTL.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select

from backend.models.logs import LLMCallLog, ToolExecutionLog
from backend.models.pipeline import PipelineRun

logger = logging.getLogger(__name__)

# ── Module-level cache ────────────────────────────────────────────────────────

_cache: dict[str, tuple[float, Any]] = {}


def _get_cached(key: str, ttl: float) -> Any | None:
    """Return cached value if within TTL, else None."""
    entry = _cache.get(key)
    if entry is None:
        return None
    ts, value = entry
    if time.monotonic() - ts > ttl:
        return None
    return value


def _set_cached(key: str, value: Any) -> None:
    """Store value in cache with current timestamp."""
    _cache[key] = (time.monotonic(), value)


# ── Celery health ─────────────────────────────────────────────────────────────

_CELERY_CACHE_TTL = 30.0


async def get_celery_health(
    redis: Any,
    *,
    celery_app: Any | None = None,
    session_factory: Any | None = None,
) -> dict[str, Any]:
    """Check Celery worker count, queue depth, and beat status.

    Args:
        redis: An async Redis client instance.
        celery_app: Optional Celery app (falls back to lazy import).
        session_factory: Optional async session factory (falls back to lazy import).

    Returns:
        Dict with workers (int|None), queued (int), beat_active (bool|None).
    """
    cached = _get_cached("celery", _CELERY_CACHE_TTL)
    if cached is not None:
        return cached

    result: dict[str, Any] = {"workers": None, "queued": 0, "beat_active": None}

    # Queue depth
    try:
        result["queued"] = await redis.llen("celery")
    except Exception:
        logger.warning("Failed to read Celery queue depth", exc_info=True)

    # Worker count via celery inspect ping
    try:
        if celery_app is None:
            from backend.tasks import celery_app  # type: ignore[assignment]

        ping_result = await asyncio.wait_for(
            asyncio.to_thread(lambda: celery_app.control.inspect(timeout=2).ping()),
            timeout=3.0,
        )
        if ping_result is not None:
            result["workers"] = len(ping_result)
        else:
            result["workers"] = 0
    except (TimeoutError, asyncio.TimeoutError):
        logger.warning("Celery worker ping timed out")
    except Exception:
        logger.warning("Failed to ping Celery workers", exc_info=True)

    # Beat status: infer from last PipelineRun recency (< 26h = active)
    try:
        sf = session_factory
        if sf is None:
            from backend.database import async_session_factory

            sf = async_session_factory

        async with sf() as session:
            stmt = select(func.max(PipelineRun.started_at)).where(
                PipelineRun.trigger == "scheduled"
            )
            last_run = (await session.execute(stmt)).scalar_one_or_none()
            if last_run is not None:
                cutoff = datetime.now(timezone.utc) - timedelta(hours=26)
                result["beat_active"] = last_run >= cutoff
            else:
                result["beat_active"] = False
    except Exception:
        logger.warning("Failed to check Celery beat status", exc_info=True)

    _set_cached("celery", result)
    return result


# ── Langfuse health ───────────────────────────────────────────────────────────

_LANGFUSE_CACHE_TTL = 60.0


async def get_langfuse_health(
    langfuse_service: Any,
    *,
    session_factory: Any | None = None,
) -> dict[str, Any]:
    """Check Langfuse connectivity and today's trace/span counts.

    Args:
        langfuse_service: A LangfuseService instance.
        session_factory: Optional async session factory (falls back to lazy import).

    Returns:
        Dict with connected (bool), traces_today (int), spans_today (int).
    """
    cached = _get_cached("langfuse", _LANGFUSE_CACHE_TTL)
    if cached is not None:
        return cached

    result: dict[str, Any] = {"connected": False, "traces_today": 0, "spans_today": 0}

    if not getattr(langfuse_service, "enabled", False):
        _set_cached("langfuse", result)
        return result

    # Auth check
    try:
        client = getattr(langfuse_service, "_client", None)
        if client is not None:
            auth_ok = await asyncio.wait_for(
                asyncio.to_thread(client.auth_check),
                timeout=2.0,
            )
            result["connected"] = bool(auth_ok)
    except (TimeoutError, asyncio.TimeoutError):
        logger.warning("Langfuse auth check timed out")
    except Exception:
        logger.warning("Langfuse auth check failed", exc_info=True)

    # Count traces and spans today from DB
    try:
        sf = session_factory
        if sf is None:
            from backend.database import async_session_factory

            sf = async_session_factory

        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

        async with sf() as session:
            # Traces today: LLMCallLog rows with langfuse_trace_id set
            traces_stmt = (
                select(func.count())
                .select_from(LLMCallLog)
                .where(
                    LLMCallLog.created_at >= today_start,
                    LLMCallLog.langfuse_trace_id.isnot(None),
                )
            )
            result["traces_today"] = (await session.execute(traces_stmt)).scalar_one()

            # Spans today: ToolExecutionLog rows
            spans_stmt = (
                select(func.count())
                .select_from(ToolExecutionLog)
                .where(ToolExecutionLog.created_at >= today_start)
            )
            result["spans_today"] = (await session.execute(spans_stmt)).scalar_one()
    except Exception:
        logger.warning("Failed to count Langfuse traces/spans from DB", exc_info=True)

    _set_cached("langfuse", result)
    return result


# ── TokenBudget status ────────────────────────────────────────────────────────


async def get_token_budget_status(token_budget: Any) -> list[dict[str, Any]]:
    """Read current TPM/RPM usage percentages for each configured model.

    Args:
        token_budget: A TokenBudget instance, or None.

    Returns:
        List of dicts with model, tpm_used_pct, rpm_used_pct.
    """
    if token_budget is None:
        return []

    limits: dict = getattr(token_budget, "_limits", {})
    if not limits:
        return []

    redis = getattr(token_budget, "_redis", None)
    if redis is None:
        return []

    results: list[dict[str, Any]] = []

    try:
        prune_sha = await token_budget._ensure_prune_script()
        now = time.time()
        minute_cutoff = str(now - 60)

        for model_name, model_limits in limits.items():
            try:
                tpm_key = f"budget:{model_name}:minute_tokens"
                rpm_key = f"budget:{model_name}:minute_requests"

                tpm_used = int(await redis.evalsha(prune_sha, 1, tpm_key, minute_cutoff))
                rpm_used = int(await redis.evalsha(prune_sha, 1, rpm_key, minute_cutoff))

                tpm_pct = (tpm_used / model_limits.tpm * 100) if model_limits.tpm else 0.0
                rpm_pct = (rpm_used / model_limits.rpm * 100) if model_limits.rpm else 0.0

                results.append(
                    {
                        "model": model_name,
                        "tpm_used_pct": round(tpm_pct, 1),
                        "rpm_used_pct": round(rpm_pct, 1),
                    }
                )
            except Exception:
                logger.warning("Failed to read budget for model %s", model_name, exc_info=True)
                results.append(
                    {
                        "model": model_name,
                        "tpm_used_pct": 0.0,
                        "rpm_used_pct": 0.0,
                    }
                )
    except Exception:
        logger.warning("Failed to load prune script for token budget", exc_info=True)

    return results
