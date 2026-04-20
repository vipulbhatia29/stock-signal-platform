"""MCP tool: get_anomalies.

Returns anomaly findings from the FindingLog table, ranked by severity
and filtered by status, since, severity, and attribution_layer.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import case, select

from backend.database import async_session_factory
from backend.observability.mcp._helpers import build_envelope, clamp_limit, parse_since
from backend.observability.models import FindingLog

logger = logging.getLogger(__name__)

# Severity rank mapping for ORDER BY
_SEVERITY_RANK = case(
    (FindingLog.severity == "critical", 0),
    (FindingLog.severity == "error", 1),
    (FindingLog.severity == "warning", 2),
    (FindingLog.severity == "info", 3),
    else_=4,
)


def _finding_to_dict(f: FindingLog) -> dict[str, Any]:
    """Convert a FindingLog ORM row to a serialisable dict.

    Args:
        f: FindingLog ORM instance.

    Returns:
        Dict with all public finding fields.
    """
    return {
        "id": f.id,
        "kind": f.kind,
        "attribution_layer": f.attribution_layer,
        "severity": f.severity,
        "status": f.status,
        "title": f.title,
        "evidence": f.evidence,
        "suggested_jira_fields": f.evidence.get("suggested_jira_fields") if isinstance(f.evidence, dict) else None,
        "remediation_hint": f.remediation_hint,
        "related_traces": f.related_traces,
        "opened_at": f.opened_at.isoformat() if f.opened_at else None,
        "closed_at": f.closed_at.isoformat() if f.closed_at else None,
        "dedup_key": f.dedup_key,
        "jira_ticket_key": f.jira_ticket_key,
        "negative_check_count": f.negative_check_count,
    }


async def get_anomalies(
    status: str = "open",
    since: str | None = None,
    severity: str | None = None,
    attribution_layer: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Return anomaly findings from FindingLog, ranked by severity.

    Args:
        status: Finding status to filter on. Defaults to "open".
        since: Optional relative time string (e.g. "24h", "7d") to filter
            by opened_at. None returns all time.
        severity: Optional severity filter (critical, error, warning, info).
        attribution_layer: Optional attribution layer filter (http, db, cache,
            external_api, celery, agent, frontend).
        limit: Maximum number of results to return (clamped to 500).

    Returns:
        Standard MCP envelope with findings list and total_count.
    """
    clamped_limit = clamp_limit(limit)

    async with async_session_factory() as db:
        stmt = select(FindingLog).where(FindingLog.status == status)

        if since is not None:
            cutoff = parse_since(since)
            stmt = stmt.where(FindingLog.opened_at >= cutoff)

        if severity is not None:
            stmt = stmt.where(FindingLog.severity == severity)

        if attribution_layer is not None:
            stmt = stmt.where(FindingLog.attribution_layer == attribution_layer)

        stmt = stmt.order_by(_SEVERITY_RANK, FindingLog.opened_at.desc())

        all_rows = (await db.execute(stmt)).scalars().all()

    total_count = len(all_rows)
    findings = [_finding_to_dict(f) for f in all_rows[:clamped_limit]]

    return build_envelope(
        "get_anomalies",
        {"findings": findings},
        total_count=total_count,
        limit=clamped_limit,
    )
