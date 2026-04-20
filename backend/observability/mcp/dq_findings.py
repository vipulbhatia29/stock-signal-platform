"""MCP tool: get_dq_findings.

Returns data quality check findings from DqCheckHistory (public schema),
filtered by severity, check name, ticker, and time window.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select

from backend.database import async_session_factory
from backend.models.dq_check_history import DqCheckHistory
from backend.observability.mcp._helpers import build_envelope, clamp_limit, parse_since

logger = logging.getLogger(__name__)


async def get_dq_findings(
    severity: str | None = None,
    check: str | None = None,
    ticker: str | None = None,
    since: str = "24h",
    limit: int = 50,
) -> dict[str, Any]:
    """Return data quality check findings from DqCheckHistory.

    Queries the public dq_check_history table for DQ violations, filtered
    by severity, check_name, ticker, and a time window. Results are ordered
    by detected_at descending (most recent first).

    Args:
        severity: Optional severity filter (e.g. "critical", "warning", "info").
            None returns all severities.
        check: Optional check_name to filter on (exact match).
        ticker: Optional ticker symbol to filter on (exact match).
        since: Relative time window string (e.g. "24h", "7d"). Defaults to "24h".
        limit: Maximum number of results to return (clamped to 500).
            Defaults to 50.

    Returns:
        Standard MCP envelope with findings list and total_count.
    """
    cutoff = parse_since(since)
    clamped_limit = clamp_limit(limit)

    async with async_session_factory() as db:
        stmt = select(DqCheckHistory).where(DqCheckHistory.detected_at >= cutoff)

        if severity is not None:
            stmt = stmt.where(DqCheckHistory.severity == severity)

        if check is not None:
            stmt = stmt.where(DqCheckHistory.check_name == check)

        if ticker is not None:
            stmt = stmt.where(DqCheckHistory.ticker == ticker)

        stmt = stmt.order_by(DqCheckHistory.detected_at.desc())

        all_rows = (await db.execute(stmt)).scalars().all()

    total_count = len(all_rows)
    findings = [_row_to_dict(r) for r in all_rows[:clamped_limit]]

    return build_envelope(
        "get_dq_findings",
        {"findings": findings},
        total_count=total_count,
        limit=clamped_limit,
        since=cutoff,
    )


def _row_to_dict(r: DqCheckHistory) -> dict[str, Any]:
    """Serialize a DqCheckHistory row to a JSON-safe dict.

    Args:
        r: DqCheckHistory ORM instance.

    Returns:
        Dict with check_name, severity, ticker, message, metadata, detected_at.
    """
    return {
        "check_name": r.check_name,
        "severity": r.severity,
        "ticker": r.ticker,
        "message": r.message,
        "metadata": r.metadata_,
        "detected_at": r.detected_at.isoformat() if r.detected_at else None,
    }
