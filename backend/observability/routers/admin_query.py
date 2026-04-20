"""Admin observability query endpoints — data layer for the admin dashboard.

All 8 endpoints delegate to the same MCP tool query functions, gated to admin
role via ``require_admin()``. These serve the 8-zone admin UI at
``/admin/observability``.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query

from backend.dependencies import get_current_user, require_admin
from backend.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/observability/admin",
    tags=["observability-admin"],
)


@router.get(
    "/kpis",
    summary="Zone 1: System health KPIs",
    description="Per-subsystem health snapshot with status pills and open anomaly counts.",
    responses={401: {"description": "Not authenticated"}, 403: {"description": "Not admin"}},
)
async def get_admin_kpis(
    user: User = Depends(get_current_user),
    window_min: int = Query(default=60, ge=1, le=1440, description="Lookback window in minutes"),
) -> dict:
    """Return system-wide health KPIs for the admin dashboard."""
    require_admin(user)
    from backend.observability.mcp.platform_health import get_platform_health

    return await get_platform_health(window_min=window_min)


@router.get(
    "/errors",
    summary="Zone 2: Live error stream",
    description="Filtered error stream across all subsystems for the error ticker.",
    responses={401: {"description": "Not authenticated"}, 403: {"description": "Not admin"}},
)
async def get_admin_errors(
    user: User = Depends(get_current_user),
    subsystem: str | None = Query(default=None, description="Filter by subsystem"),
    severity: str | None = Query(default=None, description="Filter by severity"),
    user_id: str | None = Query(default=None, description="Filter by user ID"),
    ticker: str | None = Query(default=None, description="Filter by ticker"),
    since: str = Query(default="1h", description="Relative time window (e.g. 1h, 24h)"),
    limit: int = Query(default=50, ge=1, le=500, description="Max results"),
) -> dict:
    """Return filtered error stream for the admin dashboard."""
    require_admin(user)
    from backend.observability.mcp.recent_errors import get_recent_errors

    return await get_recent_errors(
        subsystem=subsystem,
        severity=severity,
        user_id=user_id,
        ticker=ticker,
        since=since,
        limit=limit,
    )


@router.get(
    "/findings",
    summary="Zone 3: Anomaly findings",
    description="Open anomaly findings ranked by severity for the findings panel.",
    responses={401: {"description": "Not authenticated"}, 403: {"description": "Not admin"}},
)
async def get_admin_findings(
    user: User = Depends(get_current_user),
    status: str = Query(default="open", description="Finding status filter"),
    since: str | None = Query(default=None, description="Relative time window"),
    severity: str | None = Query(default=None, description="Severity filter"),
    attribution_layer: str | None = Query(default=None, description="Layer filter"),
    limit: int = Query(default=50, ge=1, le=500, description="Max results"),
) -> dict:
    """Return anomaly findings for the admin dashboard."""
    require_admin(user)
    from backend.observability.mcp.anomalies import get_anomalies

    return await get_anomalies(
        status=status,
        since=since,
        severity=severity,
        attribution_layer=attribution_layer,
        limit=limit,
    )


@router.get(
    "/trace/{trace_id}",
    summary="Zone 4: Trace explorer",
    description="Full cross-layer trace reconstruction as a span tree.",
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Not admin"},
    },
)
async def get_admin_trace(
    trace_id: str,
    user: User = Depends(get_current_user),
) -> dict:
    """Return a full trace span tree for the trace explorer."""
    require_admin(user)
    from backend.observability.mcp.trace import get_trace

    return await get_trace(trace_id=trace_id)


@router.get(
    "/externals",
    summary="Zone 5: External API dashboard",
    description="Per-provider call stats with optional comparison window.",
    responses={401: {"description": "Not authenticated"}, 403: {"description": "Not admin"}},
)
async def get_admin_externals(
    user: User = Depends(get_current_user),
    provider: str = Query(description="Provider name (e.g. yfinance, openai)"),
    window_min: int = Query(default=60, ge=1, le=1440, description="Lookback window in minutes"),
    compare_to: str | None = Query(
        default=None, description="Comparison window (e.g. 'prior_window')"
    ),
) -> dict:
    """Return external API stats for a specific provider."""
    require_admin(user)
    from backend.observability.mcp.external_api_stats import get_external_api_stats

    return await get_external_api_stats(
        provider=provider,
        window_min=window_min,
        compare_to=compare_to,
    )


@router.get(
    "/costs",
    summary="Zone 6: Cost + budget",
    description="LLM cost breakdown by provider/model/tier/user with comparison.",
    responses={401: {"description": "Not authenticated"}, 403: {"description": "Not admin"}},
)
async def get_admin_costs(
    user: User = Depends(get_current_user),
    window: str = Query(default="7d", description="Time window (e.g. 7d, 30d)"),
    by: str = Query(default="provider", description="Group by dimension"),
    compare_to: str | None = Query(default=None, description="Comparison window"),
    limit: int = Query(default=50, ge=1, le=500, description="Max results"),
) -> dict:
    """Return LLM cost breakdown for the admin dashboard."""
    require_admin(user)
    from backend.observability.mcp.cost_breakdown import get_cost_breakdown

    return await get_cost_breakdown(
        window=window,
        by=by,
        compare_to=compare_to,
        limit=limit,
    )


@router.get(
    "/pipelines",
    summary="Zone 7: Pipeline health",
    description="Pipeline deep-dive — recent runs, failure patterns, watermarks.",
    responses={401: {"description": "Not authenticated"}, 403: {"description": "Not admin"}},
)
async def get_admin_pipelines(
    user: User = Depends(get_current_user),
    pipeline_name: str = Query(description="Pipeline name to diagnose"),
    recent_n: int = Query(default=5, ge=1, le=50, description="Number of recent runs"),
) -> dict:
    """Return pipeline diagnostic data for the admin dashboard."""
    require_admin(user)
    from backend.observability.mcp.diagnose_pipeline import diagnose_pipeline

    return await diagnose_pipeline(
        pipeline_name=pipeline_name,
        recent_n=recent_n,
    )


@router.get(
    "/dq",
    summary="Zone 8: DQ scanner",
    description="Data quality check findings, historical and filterable.",
    responses={401: {"description": "Not authenticated"}, 403: {"description": "Not admin"}},
)
async def get_admin_dq(
    user: User = Depends(get_current_user),
    severity: str | None = Query(default=None, description="Severity filter"),
    check: str | None = Query(default=None, description="Check name filter"),
    ticker: str | None = Query(default=None, description="Ticker filter"),
    since: str = Query(default="24h", description="Relative time window"),
    limit: int = Query(default=50, ge=1, le=500, description="Max results"),
) -> dict:
    """Return DQ findings for the admin dashboard."""
    require_admin(user)
    from backend.observability.mcp.dq_findings import get_dq_findings

    return await get_dq_findings(
        severity=severity,
        check=check,
        ticker=ticker,
        since=since,
        limit=limit,
    )
