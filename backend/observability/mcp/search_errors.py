"""MCP tool: search_errors.

Full-text search across all error-bearing observability tables using SQL ILIKE.
Queries ApiErrorLog, ExternalApiCallLog, FrontendErrorLog, and FindingLog in
parallel and returns a merged, sorted result set.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

from sqlalchemy import or_, select

from backend.database import async_session_factory
from backend.observability.mcp._helpers import build_envelope, clamp_limit, parse_since
from backend.observability.models import (
    ApiErrorLog,
    ExternalApiCallLog,
    FindingLog,
    FrontendErrorLog,
)

logger = logging.getLogger(__name__)


def _escape_like(query: str) -> str:
    """Escape LIKE wildcard characters in user-supplied search query.

    Prevents user input from injecting extra LIKE wildcards. SQLAlchemy's
    .ilike() still parameterizes the final value; this only escapes the
    literal ``%`` and ``_`` metacharacters so they match as literals.

    Args:
        query: Raw search string from the caller.

    Returns:
        Escaped string safe to embed inside a ``%…%`` LIKE pattern.
    """
    return query.replace("%", r"\%").replace("_", r"\_")


async def _search_api_errors(
    pattern: str,
    cutoff: datetime,
) -> list[dict[str, Any]]:
    """Search ApiErrorLog for the given ILIKE pattern.

    Args:
        pattern: LIKE pattern (already escaped, surrounded by ``%``).
        cutoff: Lower bound for ``ts`` filter.

    Returns:
        Normalized result dicts from ApiErrorLog.
    """
    async with async_session_factory() as db:
        stmt = (
            select(ApiErrorLog)
            .where(
                ApiErrorLog.ts >= cutoff,
                or_(
                    ApiErrorLog.error_message.ilike(pattern),
                    ApiErrorLog.stack_signature.ilike(pattern),
                    ApiErrorLog.stack_trace.ilike(pattern),
                ),
            )
            .order_by(ApiErrorLog.ts.desc())
        )
        rows = (await db.execute(stmt)).scalars().all()

    return [
        {
            "source": "api_error",
            "ts": r.ts.isoformat() if isinstance(r.ts, datetime) else r.ts,
            "matched_text": r.error_message or r.stack_signature or "",
            "trace_id": r.trace_id,
            "details": {
                "error_type": r.error_type,
                "status_code": r.status_code,
                "stack_signature": r.stack_signature,
            },
        }
        for r in rows
    ]


async def _search_external_api_errors(
    pattern: str,
    cutoff: datetime,
) -> list[dict[str, Any]]:
    """Search ExternalApiCallLog for the given ILIKE pattern.

    Args:
        pattern: LIKE pattern (already escaped, surrounded by ``%``).
        cutoff: Lower bound for ``ts`` filter.

    Returns:
        Normalized result dicts from ExternalApiCallLog.
    """
    async with async_session_factory() as db:
        stmt = (
            select(ExternalApiCallLog)
            .where(
                ExternalApiCallLog.ts >= cutoff,
                ExternalApiCallLog.error_reason.isnot(None),
                or_(
                    ExternalApiCallLog.error_reason.ilike(pattern),
                    ExternalApiCallLog.stack_signature.ilike(pattern),
                ),
            )
            .order_by(ExternalApiCallLog.ts.desc())
        )
        rows = (await db.execute(stmt)).scalars().all()

    return [
        {
            "source": "external_api",
            "ts": r.ts.isoformat() if isinstance(r.ts, datetime) else r.ts,
            "matched_text": r.error_reason or "",
            "trace_id": r.trace_id,
            "details": {
                "provider": r.provider,
                "endpoint": r.endpoint,
                "stack_signature": r.stack_signature,
            },
        }
        for r in rows
    ]


async def _search_frontend_errors(
    pattern: str,
    cutoff: datetime,
) -> list[dict[str, Any]]:
    """Search FrontendErrorLog for the given ILIKE pattern.

    Args:
        pattern: LIKE pattern (already escaped, surrounded by ``%``).
        cutoff: Lower bound for ``ts`` filter.

    Returns:
        Normalized result dicts from FrontendErrorLog.
    """
    async with async_session_factory() as db:
        stmt = (
            select(FrontendErrorLog)
            .where(
                FrontendErrorLog.ts >= cutoff,
                or_(
                    FrontendErrorLog.error_message.ilike(pattern),
                    FrontendErrorLog.error_stack.ilike(pattern),
                ),
            )
            .order_by(FrontendErrorLog.ts.desc())
        )
        rows = (await db.execute(stmt)).scalars().all()

    return [
        {
            "source": "frontend",
            "ts": r.ts.isoformat() if isinstance(r.ts, datetime) else r.ts,
            "matched_text": r.error_message or r.error_type or "",
            "trace_id": r.trace_id,
            "details": {
                "error_type": r.error_type,
                "page_route": r.page_route,
                "component_name": r.component_name,
            },
        }
        for r in rows
    ]


async def _search_finding_log(
    pattern: str,
    cutoff: datetime,
) -> list[dict[str, Any]]:
    """Search FindingLog for the given ILIKE pattern.

    Args:
        pattern: LIKE pattern (already escaped, surrounded by ``%``).
        cutoff: Lower bound for ``opened_at`` filter.

    Returns:
        Normalized result dicts from FindingLog.
    """
    async with async_session_factory() as db:
        stmt = (
            select(FindingLog)
            .where(
                FindingLog.opened_at >= cutoff,
                or_(
                    FindingLog.title.ilike(pattern),
                    FindingLog.remediation_hint.ilike(pattern),
                ),
            )
            .order_by(FindingLog.opened_at.desc())
        )
        rows = (await db.execute(stmt)).scalars().all()

    return [
        {
            "source": "finding",
            "ts": r.opened_at.isoformat() if isinstance(r.opened_at, datetime) else r.opened_at,
            "matched_text": r.title or "",
            "trace_id": None,
            "details": {
                "kind": r.kind,
                "severity": r.severity,
                "status": r.status,
                "remediation_hint": r.remediation_hint,
            },
        }
        for r in rows
    ]


async def search_errors(
    query: str,
    since: str = "24h",
    limit: int = 50,
) -> dict[str, Any]:
    """Search across all error-bearing observability tables via SQL ILIKE.

    Runs four parallel queries (ApiErrorLog, ExternalApiCallLog,
    FrontendErrorLog, FindingLog), merges their results, sorts by
    timestamp descending, and returns up to ``limit`` matches.

    SQL injection safety: user input is escaped via ``_escape_like``
    before being passed to SQLAlchemy's ``.ilike()`` method, which
    additionally parameterizes the query at the database level.

    Args:
        query: Free-text search string. Matched case-insensitively via
            SQL ILIKE. ``%`` and ``_`` are escaped to prevent wildcard abuse.
        since: Relative time window (e.g. "24h", "7d"). Defaults to "24h".
        limit: Maximum number of results to return (clamped to 500).

    Returns:
        Standard MCP envelope with matches list sorted by ts DESC.
    """
    cutoff = parse_since(since, default="24h")
    clamped_limit = clamp_limit(limit)

    safe_q = _escape_like(query)
    pattern = f"%{safe_q}%"

    all_results_lists = await asyncio.gather(
        _search_api_errors(pattern, cutoff),
        _search_external_api_errors(pattern, cutoff),
        _search_frontend_errors(pattern, cutoff),
        _search_finding_log(pattern, cutoff),
    )

    merged: list[dict[str, Any]] = []
    for result_list in all_results_lists:
        merged.extend(result_list)

    # Sort by ts DESC — ts is already an ISO string at this point
    merged.sort(key=lambda r: r["ts"] or "", reverse=True)

    total_count = len(merged)
    matches = merged[:clamped_limit]

    return build_envelope(
        "search_errors",
        {"query": query, "matches": matches},
        total_count=total_count,
        limit=clamped_limit,
        since=cutoff,
    )
