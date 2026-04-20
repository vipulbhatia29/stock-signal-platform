"""MCP tool: get_recent_errors.

Returns a unified error stream across all subsystems — HTTP errors,
external API failures, tool execution failures, pipeline failures, and
frontend errors — sorted by timestamp descending and filtered by optional
subsystem, severity, user_id, or ticker.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select

from backend.database import async_session_factory
from backend.models.logs import ToolExecutionLog
from backend.models.pipeline import PipelineRun
from backend.observability.mcp._helpers import build_envelope, clamp_limit, parse_since
from backend.observability.models import (
    ApiErrorLog,
    ExternalApiCallLog,
    FrontendErrorLog,
)

logger = logging.getLogger(__name__)

# Subsystem name constants
_SRC_HTTP = "http"
_SRC_EXTERNAL_API = "external_api"
_SRC_TOOL = "tool"
_SRC_CELERY = "celery"
_SRC_FRONTEND = "frontend"

_ALL_SOURCES = {_SRC_HTTP, _SRC_EXTERNAL_API, _SRC_TOOL, _SRC_CELERY, _SRC_FRONTEND}


def _http_severity(status_code: int | None) -> str:
    """Derive severity from HTTP status code."""
    if status_code is not None and status_code >= 500:
        return "error"
    return "warning"


async def _fetch_http_errors(cutoff: datetime, user_id: str | None) -> list[dict[str, Any]]:
    """Fetch HTTP errors from ApiErrorLog."""
    async with async_session_factory() as db:
        stmt = select(ApiErrorLog).where(ApiErrorLog.ts >= cutoff)
        if user_id:
            stmt = stmt.where(ApiErrorLog.user_id == user_id)
        rows = (await db.execute(stmt)).scalars().all()
    return [
        {
            "source": _SRC_HTTP,
            "ts": r.ts,
            "message": r.error_message or r.error_type,
            "severity": _http_severity(r.status_code),
            "trace_id": r.trace_id,
            "stack_signature": r.stack_signature,
            "details": {
                "status_code": r.status_code,
                "error_type": r.error_type,
                "stack_trace": r.stack_trace,
            },
        }
        for r in rows
    ]


async def _fetch_external_api_errors(cutoff: datetime, user_id: str | None) -> list[dict[str, Any]]:
    """Fetch failed external API calls from ExternalApiCallLog."""
    async with async_session_factory() as db:
        stmt = select(ExternalApiCallLog).where(
            ExternalApiCallLog.ts >= cutoff,
            ExternalApiCallLog.error_reason.isnot(None),
        )
        if user_id:
            stmt = stmt.where(ExternalApiCallLog.user_id == user_id)
        rows = (await db.execute(stmt)).scalars().all()
    return [
        {
            "source": _SRC_EXTERNAL_API,
            "ts": r.ts,
            "message": r.error_reason,
            "severity": "error",
            "trace_id": r.trace_id,
            "stack_signature": r.stack_signature,
            "details": {
                "provider": r.provider,
                "endpoint": r.endpoint,
                "status_code": r.status_code,
            },
        }
        for r in rows
    ]


async def _fetch_tool_errors(cutoff: datetime) -> list[dict[str, Any]]:
    """Fetch failed tool executions from ToolExecutionLog."""
    async with async_session_factory() as db:
        stmt = select(ToolExecutionLog).where(
            ToolExecutionLog.created_at >= cutoff,
            ToolExecutionLog.status != "ok",
        )
        rows = (await db.execute(stmt)).scalars().all()
    return [
        {
            "source": _SRC_TOOL,
            "ts": r.created_at,
            "message": r.output_summary or r.error or r.status,
            "severity": "warning",
            "trace_id": None,
            "stack_signature": None,
            "details": {
                "tool_name": r.tool_name,
                "status": r.status,
                "latency_ms": r.latency_ms,
            },
        }
        for r in rows
    ]


async def _fetch_pipeline_errors(cutoff: datetime, ticker: str | None) -> list[dict[str, Any]]:
    """Fetch failed pipeline runs from PipelineRun."""
    async with async_session_factory() as db:
        stmt = select(PipelineRun).where(
            PipelineRun.started_at >= cutoff,
            PipelineRun.status == "failed",
        )
        rows = (await db.execute(stmt)).scalars().all()
    _ = ticker  # PipelineRun has no per-ticker column at the run level
    return [
        {
            "source": _SRC_CELERY,
            "ts": r.started_at,
            "message": (
                r.error_summary.get("error", "Pipeline failed")
                if isinstance(r.error_summary, dict)
                else "Pipeline failed"
            ),
            "severity": "error",
            "trace_id": None,
            "stack_signature": None,
            "details": {
                "pipeline_name": r.pipeline_name,
                "tickers_total": r.tickers_total,
                "tickers_failed": r.tickers_failed,
                "error_summary": r.error_summary,
            },
        }
        for r in rows
    ]


async def _fetch_frontend_errors(cutoff: datetime, user_id: str | None) -> list[dict[str, Any]]:
    """Fetch frontend JavaScript errors from FrontendErrorLog."""
    async with async_session_factory() as db:
        stmt = select(FrontendErrorLog).where(FrontendErrorLog.ts >= cutoff)
        if user_id:
            stmt = stmt.where(FrontendErrorLog.user_id == user_id)
        rows = (await db.execute(stmt)).scalars().all()
    return [
        {
            "source": _SRC_FRONTEND,
            "ts": r.ts,
            "message": r.error_message or r.error_type,
            "severity": "warning",
            "trace_id": r.trace_id,
            "stack_signature": None,
            "details": {
                "error_type": r.error_type,
                "error_stack": r.error_stack,
                "page_route": r.page_route,
                "component_name": r.component_name,
            },
        }
        for r in rows
    ]


async def get_recent_errors(
    subsystem: str | None = None,
    severity: str | None = None,
    user_id: str | None = None,
    ticker: str | None = None,
    since: str = "1h",
    limit: int = 50,
) -> dict[str, Any]:
    """Return a unified filtered error stream across all subsystems.

    Fetches errors from HTTP, external API, tool execution, pipeline,
    and frontend sources, then merges, filters, sorts, and truncates.

    Args:
        subsystem: Filter to a specific source (http, external_api, tool,
            celery, frontend). None returns all sources.
        severity: Filter by severity (error, warning). None returns all.
        user_id: Filter by user UUID. Only applies to sources with user_id.
        ticker: Reserved for future use — currently only logs that concept.
        since: Relative time window string like "1h", "24h", "7d".
        limit: Maximum number of results to return (clamped to 500).

    Returns:
        Standard MCP envelope with errors list and total_count.
    """
    cutoff = parse_since(since)
    clamped_limit = clamp_limit(limit)

    # Determine which sources to query
    active_sources = _ALL_SOURCES if subsystem is None else {subsystem}

    fetch_tasks = []
    task_labels: list[str] = []

    if _SRC_HTTP in active_sources:
        fetch_tasks.append(_fetch_http_errors(cutoff, user_id))
        task_labels.append(_SRC_HTTP)
    if _SRC_EXTERNAL_API in active_sources:
        fetch_tasks.append(_fetch_external_api_errors(cutoff, user_id))
        task_labels.append(_SRC_EXTERNAL_API)
    if _SRC_TOOL in active_sources:
        fetch_tasks.append(_fetch_tool_errors(cutoff))
        task_labels.append(_SRC_TOOL)
    if _SRC_CELERY in active_sources:
        fetch_tasks.append(_fetch_pipeline_errors(cutoff, ticker))
        task_labels.append(_SRC_CELERY)
    if _SRC_FRONTEND in active_sources:
        fetch_tasks.append(_fetch_frontend_errors(cutoff, user_id))
        task_labels.append(_SRC_FRONTEND)

    results = await asyncio.gather(*fetch_tasks)

    all_errors: list[dict[str, Any]] = []
    for rows in results:
        all_errors.extend(rows)

    # Apply severity filter
    if severity:
        all_errors = [e for e in all_errors if e["severity"] == severity]

    # Sort by ts DESC (handle both datetime objects and None)
    all_errors.sort(key=lambda e: e["ts"] or datetime.min, reverse=True)

    total_count = len(all_errors)
    errors = all_errors[:clamped_limit]

    # Serialize ts to ISO string for JSON safety
    for err in errors:
        if isinstance(err["ts"], datetime):
            err["ts"] = err["ts"].isoformat()

    return build_envelope(
        "get_recent_errors",
        {"errors": errors},
        total_count=total_count,
        limit=clamped_limit,
        since=cutoff,
    )
