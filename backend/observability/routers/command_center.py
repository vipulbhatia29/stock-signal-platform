"""Command Center aggregate endpoint — 4-zone admin dashboard.

Collects system health, API traffic, LLM operations, and pipeline status
into a single response with per-zone timeouts and Redis caching.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_async_session
from backend.dependencies import get_current_user, require_admin
from backend.models.logs import LLMCallLog
from backend.observability.metrics.db_pool import get_pool_stats
from backend.observability.metrics.health_checks import (
    get_celery_health,
    get_langfuse_health,
    get_token_budget_status,
)
from backend.observability.metrics.pipeline_stats import (
    get_latest_run,
    get_next_run_time,
    get_run_history,
    get_watermarks,
)
from backend.schemas.command_center import (
    ApiTrafficZone,
    CeleryHealth,
    CommandCenterMeta,
    CommandCenterResponse,
    DatabaseHealth,
    LangfuseHealth,
    LlmOperationsZone,
    McpHealth,
    PipelineLastRun,
    PipelineWatermarkStatus,
    PipelineZone,
    RedisHealth,
    SystemHealthZone,
    TierHealth,
    TokenBudgetStatus,
)

router = APIRouter(prefix="/admin/command-center", tags=["command-center"])
logger = logging.getLogger(__name__)

_CACHE_KEY = "admin:command_center:aggregate"
_CACHE_TTL_S = 10

# Known safe error prefixes for cascade log display.
# Raw LLM errors may contain API keys or internal paths — truncate and sanitize.
_MAX_ERROR_LEN = 200


def _sanitize_error(error: str | None) -> str:
    """Truncate and sanitize LLM error strings for admin display."""
    if not error:
        return ""
    # Strip potential API key patterns (sk-..., gsk_...)
    import re

    sanitized = re.sub(r"(sk-|gsk_|key-)[A-Za-z0-9]{10,}", "[REDACTED]", error)
    return sanitized[:_MAX_ERROR_LEN]


# ---------------------------------------------------------------------------
# Zone collection helper
# ---------------------------------------------------------------------------


async def _collect_zone(
    name: str,
    coro: Any,
    timeout: float = 3.0,
) -> tuple[str, Any | None]:
    """Run a zone collector with a timeout.

    Returns:
        (name, data) on success, (name, None) on timeout or exception.
    """
    try:
        result = await asyncio.wait_for(coro, timeout=timeout)
        return (name, result)
    except asyncio.TimeoutError:
        logger.warning("Zone '%s' timed out after %.1fs", name, timeout)
        return (name, None)
    except Exception:
        logger.warning("Zone '%s' failed", name, exc_info=True)
        return (name, None)


# ---------------------------------------------------------------------------
# Zone collectors (private)
# ---------------------------------------------------------------------------


async def _get_system_health(request: Request, db: AsyncSession) -> SystemHealthZone:
    """Collect Zone 1: system health from DB, Redis, MCP, Celery, Langfuse."""
    # --- Database ---
    db_healthy = True
    db_latency = 0.0
    pool_active = 0
    pool_size = 0
    pool_overflow = 0

    try:
        from backend.database import engine

        start = time.monotonic()
        await db.execute(text("SELECT 1"))
        db_latency = round((time.monotonic() - start) * 1000, 2)

        pool_stats = await get_pool_stats(engine)
        pool_active = pool_stats.get("checked_out", 0)
        pool_size = pool_stats.get("pool_size", 0)
        pool_overflow = pool_stats.get("overflow", 0)
    except Exception:
        logger.warning("DB health check failed in command center", exc_info=True)
        db_healthy = False

    database = DatabaseHealth(
        healthy=db_healthy,
        latency_ms=db_latency,
        pool_active=pool_active,
        pool_size=pool_size,
        pool_overflow=pool_overflow,
    )

    # --- Redis ---
    redis_healthy = True
    redis_latency = 0.0
    memory_used_mb: float | None = None
    memory_max_mb: float | None = None
    total_keys: int | None = None

    cache_redis = getattr(request.app.state, "cache_redis", None)
    if cache_redis is not None:
        try:
            start = time.monotonic()
            await cache_redis.ping()
            redis_latency = round((time.monotonic() - start) * 1000, 2)

            info = await cache_redis.info("memory")
            memory_used_mb = round(info.get("used_memory", 0) / (1024 * 1024), 2)
            maxmem = info.get("maxmemory", 0)
            memory_max_mb = round(maxmem / (1024 * 1024), 2) if maxmem else None

            total_keys = await cache_redis.dbsize()
        except Exception:
            logger.warning("Redis health check failed in command center", exc_info=True)
            redis_healthy = False
    else:
        redis_healthy = False

    redis = RedisHealth(
        healthy=redis_healthy,
        latency_ms=redis_latency,
        memory_used_mb=memory_used_mb,
        memory_max_mb=memory_max_mb,
        total_keys=total_keys,
    )

    # --- MCP ---
    mcp_manager = getattr(request.app.state, "mcp_manager", None)
    registry = getattr(request.app.state, "registry", None)
    tool_count = len(registry.discover()) if registry else 0

    if mcp_manager is not None:
        mcp = McpHealth(
            healthy=mcp_manager.healthy,
            mode=mcp_manager.mode,
            tool_count=tool_count,
            restarts=mcp_manager.restart_count,
            uptime_seconds=(
                round(mcp_manager.uptime_seconds) if mcp_manager.uptime_seconds else None
            ),
        )
    else:
        mcp = McpHealth(
            healthy=False,
            mode="disabled",
            tool_count=tool_count,
            restarts=0,
        )

    # --- Celery ---
    celery_data = await get_celery_health(cache_redis) if cache_redis else {}
    celery = CeleryHealth(
        workers=celery_data.get("workers"),
        queued=celery_data.get("queued"),
        beat_active=celery_data.get("beat_active"),
    )

    # --- Langfuse ---
    langfuse_service = getattr(request.app.state, "langfuse", None)
    if langfuse_service is not None:
        langfuse_data = await get_langfuse_health(langfuse_service)
        langfuse = LangfuseHealth(
            connected=langfuse_data.get("connected", False),
            traces_today=langfuse_data.get("traces_today", 0),
            spans_today=langfuse_data.get("spans_today", 0),
        )
    else:
        langfuse = LangfuseHealth()

    # --- Overall status ---
    critical_healthy = db_healthy and redis_healthy
    status = "ok" if critical_healthy else "degraded"

    return SystemHealthZone(
        status=status,
        database=database,
        redis=redis,
        mcp=mcp,
        celery=celery,
        langfuse=langfuse,
    )


async def _get_api_traffic(request: Request) -> ApiTrafficZone:
    """Collect Zone 2: HTTP API traffic from HttpMetricsCollector."""
    http_metrics = getattr(request.app.state, "http_metrics", None)
    if http_metrics is None:
        return ApiTrafficZone()

    stats = await http_metrics.get_stats()

    return ApiTrafficZone(
        window_seconds=stats.get("window_seconds", 300),
        sample_count=stats.get("sample_count", 0),
        rps_avg=stats.get("rps_avg", 0),
        latency_p50_ms=stats.get("latency_p50_ms"),
        latency_p95_ms=stats.get("latency_p95_ms"),
        latency_p99_ms=stats.get("latency_p99_ms"),
        error_rate_pct=stats.get("error_rate_pct"),
        total_requests_today=stats.get("total_requests_today", 0),
        total_errors_today=stats.get("total_errors_today", 0),
        top_endpoints=stats.get("top_endpoints", []),
    )


async def _get_llm_operations(request: Request, db: AsyncSession) -> LlmOperationsZone:
    """Collect Zone 3: LLM tier health, costs, cascade rate, token budgets."""
    collector = getattr(request.app.state, "collector", None)

    # --- Tier health ---
    tiers: list[TierHealth] = []
    if collector is not None:
        tier_data = await collector.get_tier_health(db)
        for t in tier_data.get("tiers", []):
            tiers.append(
                TierHealth(
                    model=t["model"],
                    status=t["status"],
                    failures_5m=t.get("failures_5m", 0),
                    successes_5m=t.get("successes_5m", 0),
                    cascade_count=t.get("cascade_count", 0),
                    latency=t.get("latency", {}),
                )
            )

    # --- Costs (today, yesterday, this week) ---
    now_utc = datetime.now(timezone.utc)
    today_start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start = today_start - timedelta(days=1)
    week_start = today_start - timedelta(days=7)

    cost_today = 0.0
    cost_yesterday = 0.0
    cost_week = 0.0

    try:
        # Today's cost
        stmt_today = select(func.coalesce(func.sum(LLMCallLog.cost_usd), 0)).where(
            LLMCallLog.created_at >= today_start,
            LLMCallLog.cost_usd.is_not(None),
        )
        cost_today = float((await db.execute(stmt_today)).scalar_one())

        # Yesterday's cost
        stmt_yesterday = select(func.coalesce(func.sum(LLMCallLog.cost_usd), 0)).where(
            LLMCallLog.created_at >= yesterday_start,
            LLMCallLog.created_at < today_start,
            LLMCallLog.cost_usd.is_not(None),
        )
        cost_yesterday = float((await db.execute(stmt_yesterday)).scalar_one())

        # Week's cost
        stmt_week = select(func.coalesce(func.sum(LLMCallLog.cost_usd), 0)).where(
            LLMCallLog.created_at >= week_start,
            LLMCallLog.cost_usd.is_not(None),
        )
        cost_week = float((await db.execute(stmt_week)).scalar_one())
    except Exception:
        logger.warning("Failed to compute LLM costs", exc_info=True)

    # --- Cascade rate ---
    cascade_rate = 0.0
    if collector is not None:
        try:
            cascade_rate = round(await collector.fallback_rate_last_60s(db) * 100, 2)
        except Exception:
            logger.warning("Failed to compute cascade rate", exc_info=True)

    # --- Token budgets ---
    token_budget = getattr(request.app.state, "token_budget", None)
    budget_data = await get_token_budget_status(token_budget)
    token_budgets = [
        TokenBudgetStatus(
            model=b["model"],
            tpm_used_pct=b.get("tpm_used_pct", 0),
            rpm_used_pct=b.get("rpm_used_pct", 0),
        )
        for b in budget_data
    ]

    return LlmOperationsZone(
        tiers=tiers,
        cost_today_usd=round(cost_today, 6),
        cost_yesterday_usd=round(cost_yesterday, 6),
        cost_week_usd=round(cost_week, 6),
        cascade_rate_pct=cascade_rate,
        token_budgets=token_budgets,
    )


async def _get_pipeline(db: AsyncSession) -> PipelineZone:
    """Collect Zone 4: latest pipeline run, watermarks, next run time."""
    # --- Last run ---
    last_run_data = await get_latest_run(db)
    last_run: PipelineLastRun | None = None
    if last_run_data is not None:
        last_run = PipelineLastRun(
            started_at=last_run_data["started_at"],
            status=last_run_data["status"],
            total_duration_seconds=last_run_data.get("duration_seconds"),
            tickers_succeeded=last_run_data.get("tickers_succeeded", 0),
            tickers_failed=last_run_data.get("tickers_failed", 0),
            tickers_total=last_run_data.get("tickers_total", 0),
            step_durations=None,  # Not in get_latest_run output
        )

    # --- Watermarks ---
    watermark_data = await get_watermarks(db)
    watermarks = [
        PipelineWatermarkStatus(
            pipeline=wm["pipeline_name"],
            last_date=wm["last_completed_date"],
            status=wm["status"],
        )
        for wm in watermark_data
    ]

    # --- Next run ---
    next_run_at = get_next_run_time()

    return PipelineZone(
        last_run=last_run,
        watermarks=watermarks,
        next_run_at=next_run_at,
    )


# ---------------------------------------------------------------------------
# Safe wrappers — each opens its own DB session for concurrent gather
# ---------------------------------------------------------------------------


async def _get_system_health_safe(request: Request) -> SystemHealthZone:
    """Wrapper that opens its own session for concurrent use in gather."""
    from backend.database import async_session_factory

    async with async_session_factory() as db:
        return await _get_system_health(request, db)


async def _get_llm_operations_safe(request: Request) -> LlmOperationsZone:
    """Wrapper that opens its own session for concurrent use in gather."""
    from backend.database import async_session_factory

    async with async_session_factory() as db:
        return await _get_llm_operations(request, db)


async def _get_pipeline_safe() -> PipelineZone:
    """Wrapper that opens its own session for concurrent use in gather."""
    from backend.database import async_session_factory

    async with async_session_factory() as db:
        return await _get_pipeline(db)


# ---------------------------------------------------------------------------
# Aggregate endpoint
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=CommandCenterResponse,
    summary="Command Center aggregate",
    description="Returns all 4 dashboard zones in a single call with per-zone timeouts.",
)
async def get_command_center(
    request: Request,
    user: Any = Depends(get_current_user),
) -> CommandCenterResponse:
    """Aggregate endpoint for the Command Center dashboard.

    Requires admin role. Results are cached in Redis for 10 seconds.
    Each zone is collected with an independent 3-second timeout.
    """
    require_admin(user)

    # --- Check Redis cache ---
    cache_redis = getattr(request.app.state, "cache_redis", None)
    if cache_redis is not None:
        try:
            cached = await cache_redis.get(_CACHE_KEY)
            if cached is not None:
                raw = cached if isinstance(cached, str) else cached.decode()
                return CommandCenterResponse.model_validate_json(raw)
        except Exception:
            logger.debug("Command center cache read failed", exc_info=True)

    # --- Collect zones in parallel ---
    start_ms = time.monotonic()

    # Each zone that queries DB gets its own session to avoid sharing
    # a single AsyncSession across concurrent coroutines (unsafe).

    results = await asyncio.gather(
        _collect_zone("system_health", _get_system_health_safe(request)),
        _collect_zone("api_traffic", _get_api_traffic(request)),
        _collect_zone("llm_operations", _get_llm_operations_safe(request)),
        _collect_zone("pipeline", _get_pipeline_safe()),
        return_exceptions=True,
    )

    assembly_ms = round((time.monotonic() - start_ms) * 1000)

    # --- Build response ---
    zone_data: dict[str, Any] = {}
    degraded_zones: list[str] = []
    for item in results:
        if isinstance(item, Exception):
            logger.error("Zone collection raised: %s", item)
            continue
        name, data = item
        if data is None:
            degraded_zones.append(name)
        zone_data[name] = data

    response = CommandCenterResponse(
        timestamp=datetime.now(timezone.utc).isoformat(),
        meta=CommandCenterMeta(
            assembly_ms=assembly_ms,
            degraded_zones=degraded_zones,
        ),
        system_health=zone_data.get("system_health"),
        api_traffic=zone_data.get("api_traffic"),
        llm_operations=zone_data.get("llm_operations"),
        pipeline=zone_data.get("pipeline"),
    )

    # --- Cache result (skip if any zones degraded — don't cache partial data) ---
    if cache_redis is not None and not degraded_zones:
        try:
            await cache_redis.set(
                _CACHE_KEY,
                response.model_dump_json(),
                ex=_CACHE_TTL_S,
            )
        except Exception:
            logger.debug("Command center cache write failed", exc_info=True)

    return response


# ---------------------------------------------------------------------------
# Drill-down endpoints
# ---------------------------------------------------------------------------


@router.get("/api-traffic", summary="API traffic drill-down")
async def get_api_traffic_detail(
    request: Request,
    user: Any = Depends(get_current_user),
) -> dict:
    """Full endpoint breakdown with per-endpoint counts, error rates, latencies.

    Returns the same sliding-window metrics as the aggregate endpoint but
    with the full top-endpoints list. The window is fixed at 300s (configured
    on the HttpMetricsCollector).
    """
    require_admin(user)

    http_metrics = getattr(request.app.state, "http_metrics", None)
    if http_metrics is None:
        return {"status": "unavailable", "endpoints": [], "total": 0}

    stats = await http_metrics.get_stats()
    return {
        "window_seconds": stats.get("window_seconds", 300),
        "endpoints": stats.get("top_endpoints", []),
        "total_requests_today": stats.get("total_requests_today", 0),
        "total_errors_today": stats.get("total_errors_today", 0),
        "latency_p50_ms": stats.get("latency_p50_ms"),
        "latency_p95_ms": stats.get("latency_p95_ms"),
        "latency_p99_ms": stats.get("latency_p99_ms"),
        "error_rate_pct": stats.get("error_rate_pct"),
        "sample_count": stats.get("sample_count", 0),
    }


@router.get("/llm", summary="LLM operations drill-down")
async def get_llm_detail(
    hours: int = Query(24, ge=1, le=168),
    user: Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> dict:
    """Per-model cost breakdown, cascade log, token consumption."""
    require_admin(user)

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    # Per-model breakdown
    model_stmt = (
        select(
            LLMCallLog.model,
            LLMCallLog.provider,
            func.count().label("call_count"),
            func.coalesce(func.sum(LLMCallLog.cost_usd), 0).label("total_cost"),
            func.coalesce(func.avg(LLMCallLog.latency_ms), 0).label("avg_latency_ms"),
            func.count().filter(LLMCallLog.error.is_not(None)).label("error_count"),
            func.coalesce(func.sum(LLMCallLog.prompt_tokens), 0).label("total_prompt_tokens"),
            func.coalesce(func.sum(LLMCallLog.completion_tokens), 0).label(
                "total_completion_tokens"
            ),
        )
        .where(LLMCallLog.created_at >= cutoff)
        .group_by(LLMCallLog.model, LLMCallLog.provider)
        .order_by(func.count().desc())
    )
    model_rows = (await db.execute(model_stmt)).all()

    models = []
    for row in model_rows:
        models.append(
            {
                "model": row.model,
                "provider": row.provider,
                "call_count": row.call_count,
                "total_cost_usd": round(float(row.total_cost), 4),
                "avg_latency_ms": round(float(row.avg_latency_ms), 1),
                "error_count": row.error_count,
                "total_prompt_tokens": int(row.total_prompt_tokens),
                "total_completion_tokens": int(row.total_completion_tokens),
            }
        )

    # Cascade log (last 50 errors)
    cascade_stmt = (
        select(LLMCallLog.model, LLMCallLog.error, LLMCallLog.created_at)
        .where(LLMCallLog.error.is_not(None), LLMCallLog.created_at >= cutoff)
        .order_by(LLMCallLog.created_at.desc())
        .limit(50)
    )
    cascade_rows = (await db.execute(cascade_stmt)).all()
    cascades = [
        {
            "model": r.model,
            "error": _sanitize_error(r.error),
            "timestamp": r.created_at.isoformat(),
        }
        for r in cascade_rows
    ]

    return {
        "hours": hours,
        "models": models,
        "cascades": cascades,
        "total_models": len(models),
    }


@router.get("/pipeline", summary="Pipeline drill-down")
async def get_pipeline_detail(
    days: int = Query(7, ge=1, le=30),
    user: Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> dict:
    """Run history, failed tickers, step duration trends."""
    require_admin(user)

    runs = await get_run_history(db, days=days)
    return {"runs": runs, "total": len(runs), "days": days}
