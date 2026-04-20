"""MCP tool: get_platform_health.

Returns a system-wide health snapshot for all subsystems — HTTP, DB, Cache,
External API, Celery, Agent, and Frontend — plus open anomaly counts.
Subsystem queries are executed in parallel via asyncio.gather.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import case, distinct, func, select

from backend.database import async_session_factory
from backend.observability.mcp._helpers import build_envelope
from backend.observability.models import (
    AgentIntentLog,
    CacheOperationLog,
    CeleryQueueDepth,
    CeleryWorkerHeartbeat,
    DbPoolEventModel,
    ExternalApiCallLog,
    FindingLog,
    FrontendErrorLog,
    RequestLog,
    SlowQueryLog,
)

logger = logging.getLogger(__name__)

# Thresholds for status derivation
_HTTP_ERROR_RATE_DEGRADED = 0.05  # 5% errors → degraded
_HTTP_ERROR_RATE_FAILING = 0.20  # 20% errors → failing
_HTTP_P95_DEGRADED_MS = 1000  # 1s p95 → degraded
_HTTP_P95_FAILING_MS = 5000  # 5s p95 → failing
_DB_POOL_EXHAUSTION_DEGRADED = 3  # 3+ exhaustion events → degraded
_DB_POOL_EXHAUSTION_FAILING = 10
_DB_P95_DEGRADED_MS = 2000
_DB_P95_FAILING_MS = 8000
_CACHE_HIT_RATE_DEGRADED = 0.60  # below 60% → degraded
_CACHE_HIT_RATE_FAILING = 0.30
_EXT_ERROR_RATE_DEGRADED = 0.10
_EXT_ERROR_RATE_FAILING = 0.30
_AGENT_DECLINE_RATE_DEGRADED = 0.10
_AGENT_DECLINE_RATE_FAILING = 0.30

_STATUS_RANK = {"healthy": 0, "degraded": 1, "failing": 2}


def _worst(statuses: list[str]) -> str:
    """Return the worst status from a list of status strings."""
    return max(statuses, key=lambda s: _STATUS_RANK.get(s, 0), default="healthy")


def _http_status(count: int, errors: int, p95: float | None) -> str:
    """Derive HTTP subsystem status from error rate and p95 latency."""
    if count == 0:
        return "healthy"
    error_rate = errors / count
    if error_rate >= _HTTP_ERROR_RATE_FAILING or (p95 is not None and p95 >= _HTTP_P95_FAILING_MS):
        return "failing"
    if error_rate >= _HTTP_ERROR_RATE_DEGRADED or (
        p95 is not None and p95 >= _HTTP_P95_DEGRADED_MS
    ):
        return "degraded"
    return "healthy"


async def _query_http(cutoff: datetime) -> dict[str, Any]:
    """Query HTTP subsystem stats from RequestLog."""
    async with async_session_factory() as db:
        stmt = select(
            func.count().label("total"),
            func.sum(case((RequestLog.status_code >= 400, 1), else_=0)).label("errors"),
            func.percentile_cont(0.95).within_group(RequestLog.latency_ms).label("p95_ms"),
        ).where(RequestLog.ts >= cutoff)
        row = (await db.execute(stmt)).one()
    total = row.total or 0
    errors = int(row.errors or 0)
    p95 = float(row.p95_ms) if row.p95_ms is not None else None
    error_rate = (errors / total) if total else 0.0
    return {
        "subsystem": "http",
        "request_count": total,
        "error_count": errors,
        "error_rate": round(error_rate, 4),
        "p95_latency_ms": p95,
        "status": _http_status(total, errors, p95),
    }


async def _query_db(cutoff: datetime) -> dict[str, Any]:
    """Query DB subsystem stats from SlowQueryLog and DbPoolEventModel."""
    async with async_session_factory() as db:
        slow_stmt = select(
            func.count().label("slow_count"),
            func.percentile_cont(0.95).within_group(SlowQueryLog.duration_ms).label("p95_ms"),
        ).where(SlowQueryLog.ts >= cutoff)
        pool_stmt = select(func.count()).where(
            DbPoolEventModel.ts >= cutoff,
            DbPoolEventModel.pool_event_type == "exhausted",
        )
        # Sequential — AsyncSession is not concurrency-safe
        slow_row = await db.execute(slow_stmt)
        pool_count = await db.execute(pool_stmt)
    slow = slow_row.one()
    slow_count = slow.slow_count or 0
    p95 = float(slow.p95_ms) if slow.p95_ms is not None else None
    exhaustions = pool_count.scalar() or 0

    if exhaustions >= _DB_POOL_EXHAUSTION_FAILING or (
        p95 is not None and p95 >= _DB_P95_FAILING_MS
    ):
        status = "failing"
    elif exhaustions >= _DB_POOL_EXHAUSTION_DEGRADED or (
        p95 is not None and p95 >= _DB_P95_DEGRADED_MS
    ):
        status = "degraded"
    else:
        status = "healthy"

    return {
        "subsystem": "db",
        "slow_query_count": slow_count,
        "p95_duration_ms": p95,
        "pool_exhaustion_events": exhaustions,
        "status": status,
    }


async def _query_cache(cutoff: datetime) -> dict[str, Any]:
    """Query Cache subsystem hit rate from CacheOperationLog."""
    async with async_session_factory() as db:
        stmt = select(
            func.count().label("total"),
            func.sum(case((CacheOperationLog.hit.is_(True), 1), else_=0)).label("hits"),
        ).where(
            CacheOperationLog.ts >= cutoff,
            CacheOperationLog.operation == "get",
        )
        row = (await db.execute(stmt)).one()
    total = row.total or 0
    hits = int(row.hits or 0)
    hit_rate = (hits / total) if total else 1.0

    if total > 0 and hit_rate < _CACHE_HIT_RATE_FAILING:
        status = "failing"
    elif total > 0 and hit_rate < _CACHE_HIT_RATE_DEGRADED:
        status = "degraded"
    else:
        status = "healthy"

    return {
        "subsystem": "cache",
        "get_count": total,
        "hit_count": hits,
        "hit_rate": round(hit_rate, 4),
        "status": status,
    }


async def _query_external_api(cutoff: datetime) -> dict[str, Any]:
    """Query External API subsystem stats from ExternalApiCallLog."""
    async with async_session_factory() as db:
        stmt = select(
            func.count().label("total"),
            func.sum(case((ExternalApiCallLog.error_reason.isnot(None), 1), else_=0)).label(
                "errors"
            ),
        ).where(ExternalApiCallLog.ts >= cutoff)
        row = (await db.execute(stmt)).one()
    total = row.total or 0
    errors = int(row.errors or 0)
    error_rate = (errors / total) if total else 0.0

    if error_rate >= _EXT_ERROR_RATE_FAILING:
        status = "failing"
    elif error_rate >= _EXT_ERROR_RATE_DEGRADED:
        status = "degraded"
    else:
        status = "healthy"

    return {
        "subsystem": "external_api",
        "call_count": total,
        "error_count": errors,
        "error_rate": round(error_rate, 4),
        "status": status,
    }


async def _query_celery(cutoff: datetime) -> dict[str, Any]:
    """Query Celery subsystem — active workers and queue depths."""
    async with async_session_factory() as db:
        worker_stmt = select(func.count(distinct(CeleryWorkerHeartbeat.worker_name))).where(
            CeleryWorkerHeartbeat.ts >= cutoff
        )
        # Latest depth per queue: subquery to get max ts per queue_name
        subq = (
            select(
                CeleryQueueDepth.queue_name,
                func.max(CeleryQueueDepth.ts).label("latest_ts"),
            )
            .group_by(CeleryQueueDepth.queue_name)
            .subquery()
        )
        depth_stmt = select(
            CeleryQueueDepth.queue_name,
            CeleryQueueDepth.depth,
        ).join(
            subq,
            (CeleryQueueDepth.queue_name == subq.c.queue_name)
            & (CeleryQueueDepth.ts == subq.c.latest_ts),
        )
        # Sequential — AsyncSession is not concurrency-safe
        worker_count_res = await db.execute(worker_stmt)
        depth_rows = await db.execute(depth_stmt)
    active_workers = worker_count_res.scalar() or 0
    queue_depths = {row.queue_name: row.depth for row in depth_rows.all()}
    total_depth = sum(queue_depths.values())

    status = "healthy"
    if active_workers == 0 and total_depth > 0:
        status = "failing"
    elif active_workers == 0:
        status = "degraded"

    return {
        "subsystem": "celery",
        "active_workers": active_workers,
        "queue_depths": queue_depths,
        "total_queue_depth": total_depth,
        "status": status,
    }


async def _query_agent(cutoff: datetime) -> dict[str, Any]:
    """Query Agent subsystem — intent count and decline rate."""
    async with async_session_factory() as db:
        stmt = select(
            func.count().label("total"),
            func.sum(case((AgentIntentLog.decline_reason.isnot(None), 1), else_=0)).label(
                "declines"
            ),
        ).where(AgentIntentLog.ts >= cutoff)
        row = (await db.execute(stmt)).one()
    total = row.total or 0
    declines = int(row.declines or 0)
    decline_rate = (declines / total) if total else 0.0

    if decline_rate >= _AGENT_DECLINE_RATE_FAILING:
        status = "failing"
    elif decline_rate >= _AGENT_DECLINE_RATE_DEGRADED:
        status = "degraded"
    else:
        status = "healthy"

    return {
        "subsystem": "agent",
        "query_count": total,
        "decline_count": declines,
        "decline_rate": round(decline_rate, 4),
        "status": status,
    }


async def _query_frontend(cutoff: datetime) -> dict[str, Any]:
    """Query Frontend subsystem error count from FrontendErrorLog."""
    async with async_session_factory() as db:
        stmt = select(func.count()).where(FrontendErrorLog.ts >= cutoff)
        count = (await db.execute(stmt)).scalar() or 0
    status = "healthy" if count == 0 else "degraded"
    return {
        "subsystem": "frontend",
        "error_count": count,
        "status": status,
    }


async def _query_anomalies() -> int:
    """Count open and acknowledged findings from FindingLog."""
    async with async_session_factory() as db:
        stmt = select(func.count()).where(FindingLog.status.in_(["open", "acknowledged"]))
        return (await db.execute(stmt)).scalar() or 0


async def get_platform_health(window_min: int = 60) -> dict[str, Any]:
    """Return a system-wide health snapshot for all subsystems.

    Queries each subsystem in parallel for the last ``window_min`` minutes
    and derives per-subsystem status (healthy / degraded / failing).
    Overall status is the worst subsystem status.

    Args:
        window_min: Look-back window in minutes. Defaults to 60.

    Returns:
        Standard MCP envelope with subsystem stats and overall status.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=window_min)

    (
        http_stats,
        db_stats,
        cache_stats,
        ext_stats,
        celery_stats,
        agent_stats,
        frontend_stats,
        open_anomalies,
    ) = await asyncio.gather(
        _query_http(cutoff),
        _query_db(cutoff),
        _query_cache(cutoff),
        _query_external_api(cutoff),
        _query_celery(cutoff),
        _query_agent(cutoff),
        _query_frontend(cutoff),
        _query_anomalies(),
    )

    subsystems: list[dict[str, Any]] = [
        http_stats,  # type: ignore[list-item]
        db_stats,  # type: ignore[list-item]
        cache_stats,  # type: ignore[list-item]
        ext_stats,  # type: ignore[list-item]
        celery_stats,  # type: ignore[list-item]
        agent_stats,  # type: ignore[list-item]
        frontend_stats,  # type: ignore[list-item]
    ]
    overall_status = _worst([s["status"] for s in subsystems])

    result: dict[str, Any] = {
        "overall_status": overall_status,
        "window_min": window_min,
        "subsystems": {s["subsystem"]: s for s in subsystems},
        "open_anomaly_count": open_anomalies,
    }

    return build_envelope("get_platform_health", result, since=cutoff)
