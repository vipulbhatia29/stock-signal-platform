"""Admin observability query endpoints — data layer for the admin dashboard.

All 8 endpoints delegate to the same MCP tool query functions, gated to admin
role via ``require_admin()``. These serve the 8-zone admin UI at
``/admin/observability``.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from backend.database import async_session_factory
from backend.dependencies import get_current_user, require_admin
from backend.models.user import User
from backend.observability.models.finding_log import FindingLog

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
    kind: str | None = Query(default=None, description="Kind filter"),
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
        kind=kind,
        limit=limit,
    )


_DURATION_MAP: dict[str, timedelta] = {
    "1h": timedelta(hours=1),
    "4h": timedelta(hours=4),
    "24h": timedelta(hours=24),
}


def _serialize_finding(finding: FindingLog) -> dict:
    """Serialize a FindingLog ORM instance to a JSON-safe dict.

    Args:
        finding: A FindingLog ORM instance.

    Returns:
        Dict with all column values; datetime fields converted to ISO 8601.
    """
    result: dict = {}
    for col in FindingLog.__table__.columns:
        value = getattr(finding, col.name)
        if hasattr(value, "isoformat"):
            value = value.isoformat()
        result[col.name] = value
    return result


@router.patch(
    "/findings/{finding_id}/acknowledge",
    summary="Zone 3: Acknowledge a finding",
    description="Mark a finding as acknowledged by the current admin user.",
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Not admin"},
        404: {"description": "Finding not found"},
    },
)
async def acknowledge_finding(
    finding_id: str,
    user: User = Depends(get_current_user),
) -> dict:
    """Acknowledge an anomaly finding.

    Args:
        finding_id: UUID of the finding to acknowledge.
        user: Authenticated admin user (injected by FastAPI).

    Returns:
        The updated finding as a serialized dict.

    Raises:
        HTTPException: 404 if the finding does not exist.
    """
    require_admin(user)
    from sqlalchemy import func

    async with async_session_factory() as db:
        result = await db.execute(select(FindingLog).where(FindingLog.id == finding_id))
        finding = result.scalar_one_or_none()
        if finding is None:
            raise HTTPException(status_code=404, detail="Finding not found")

        finding.status = "acknowledged"
        finding.acknowledged_by = str(user.id)
        finding.acknowledged_at = func.now()
        await db.commit()
        await db.refresh(finding)

    return _serialize_finding(finding)


@router.patch(
    "/findings/{finding_id}/suppress",
    summary="Zone 3: Suppress a finding",
    description="Suppress a finding for a specified duration.",
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Not admin"},
        404: {"description": "Finding not found"},
    },
)
async def suppress_finding(
    finding_id: str,
    user: User = Depends(get_current_user),
    duration: str = Query(default="1h", description="Suppression duration (1h, 4h, 24h)"),
) -> dict:
    """Suppress an anomaly finding for a given duration.

    Args:
        finding_id: UUID of the finding to suppress.
        user: Authenticated admin user (injected by FastAPI).
        duration: Suppression window string. Supported values: "1h", "4h", "24h".
            Defaults to "1h".

    Returns:
        The updated finding as a serialized dict.

    Raises:
        HTTPException: 404 if the finding does not exist.
    """
    require_admin(user)
    from sqlalchemy import func

    td = _DURATION_MAP.get(duration, timedelta(hours=1))

    async with async_session_factory() as db:
        result = await db.execute(select(FindingLog).where(FindingLog.id == finding_id))
        finding = result.scalar_one_or_none()
        if finding is None:
            raise HTTPException(status_code=404, detail="Finding not found")

        finding.status = "suppressed"
        finding.suppressed_until = func.now() + td
        finding.suppression_reason = "Manual suppression from admin UI"
        await db.commit()
        await db.refresh(finding)

    return _serialize_finding(finding)


_SEVERITY_TO_JIRA_PRIORITY: dict[str, str] = {
    "critical": "Highest",
    "error": "High",
    "warning": "Medium",
    "info": "Low",
}


@router.post(
    "/findings/{finding_id}/jira-draft",
    summary="Zone 3: Create JIRA draft from finding",
    description="Create a JIRA issue pre-filled with finding details.",
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Not admin"},
        404: {"description": "Finding not found"},
        503: {"description": "JIRA not configured"},
    },
)
async def create_jira_draft(
    finding_id: str,
    user: User = Depends(get_current_user),
) -> dict:
    """Create a JIRA issue from an anomaly finding.

    Fetches the finding, builds an issue payload, and creates it in JIRA
    via REST API v3. Updates the finding's jira_ticket_key on success.

    Args:
        finding_id: UUID of the finding to create a JIRA draft for.
        user: Authenticated admin user (injected by FastAPI).

    Returns:
        Dict with jira_key, jira_url, and the finding draft fields.

    Raises:
        HTTPException: 404 if the finding does not exist.
        HTTPException: 503 if JIRA credentials are not configured.
    """
    require_admin(user)
    import json

    import httpx

    from backend.config import settings

    if not settings.JIRA_API_EMAIL or not settings.JIRA_API_TOKEN:
        raise HTTPException(status_code=503, detail="JIRA integration not configured")

    async with async_session_factory() as db:
        result = await db.execute(select(FindingLog).where(FindingLog.id == finding_id))
        finding = result.scalar_one_or_none()
        if finding is None:
            raise HTTPException(status_code=404, detail="Finding not found")

        if finding.jira_ticket_key:
            return {
                "jira_key": finding.jira_ticket_key,
                "jira_url": (f"{settings.JIRA_SITE_URL}/browse/{finding.jira_ticket_key}"),
                "already_exists": True,
            }

        # Build description
        evidence_str = json.dumps(finding.evidence, indent=2, default=str)
        traces_str = ""
        if finding.related_traces:
            traces_str = "\n".join(f"- {tid}" for tid in finding.related_traces)
        description = (
            f"*Auto-generated from observability finding*\n\n"
            f"h3. Evidence\n{{code:json}}\n{evidence_str}\n{{code}}\n\n"
        )
        if finding.remediation_hint:
            description += f"h3. Remediation\n{finding.remediation_hint}\n\n"
        if traces_str:
            description += f"h3. Related Traces\n{traces_str}\n\n"
        description += (
            f"h3. Metadata\n"
            f"- *Layer:* {finding.attribution_layer}\n"
            f"- *Kind:* {finding.kind}\n"
            f"- *Severity:* {finding.severity}\n"
            f"- *Opened:* {finding.opened_at.isoformat() if finding.opened_at else 'N/A'}\n"
        )

        # Create via JIRA REST API v3
        jira_payload = {
            "fields": {
                "project": {"key": settings.JIRA_PROJECT_KEY},
                "summary": f"[obs] {finding.title}",
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": description}],
                        }
                    ],
                },
                "issuetype": {"name": "Bug"},
                "labels": ["obs-generated", finding.attribution_layer],
            }
        }

        api_url = f"{settings.JIRA_SITE_URL}/rest/api/3/issue"
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    api_url,
                    json=jira_payload,
                    auth=(settings.JIRA_API_EMAIL, settings.JIRA_API_TOKEN),
                    headers={"Accept": "application/json"},
                    timeout=15.0,
                )
                resp.raise_for_status()
                jira_data = resp.json()
        except httpx.HTTPError:
            logger.exception("Failed to create JIRA issue for finding %s", finding_id)
            raise HTTPException(status_code=502, detail="Failed to create JIRA issue")

        jira_key = jira_data.get("key", "")
        finding.jira_ticket_key = jira_key
        await db.commit()

    return {
        "jira_key": jira_key,
        "jira_url": f"{settings.JIRA_SITE_URL}/browse/{jira_key}",
        "already_exists": False,
    }


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
