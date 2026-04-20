"""MCP tool: get_slow_queries.

Returns aggregated slow-query statistics from SlowQueryLog (observability schema),
grouped by query_hash, with optional baseline comparison for trend detection.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select

from backend.database import async_session_factory
from backend.observability.mcp._helpers import build_envelope, clamp_limit, parse_since
from backend.observability.models import SlowQueryLog

logger = logging.getLogger(__name__)


async def get_slow_queries(
    since: str = "1h",
    min_duration_ms: int = 500,
    query_hash: str | None = None,
    compare_to: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Return aggregated slow-query statistics grouped by query_hash.

    Queries SlowQueryLog for queries exceeding ``min_duration_ms`` within
    the given time window, grouped by hash to surface the most expensive
    query shapes. Optionally compares against a 7-day baseline window.

    Args:
        since: Relative time window string (e.g. "1h", "24h"). Defaults to "1h".
        min_duration_ms: Minimum duration threshold in milliseconds. Only
            queries at or above this value are included. Defaults to 500.
        query_hash: Optional SHA256 hash to filter to a single query shape.
        compare_to: Optional comparison mode. "7d_baseline" computes p95 for
            the same query hashes over the prior 7 days and includes delta.
        limit: Maximum number of grouped results to return (clamped to 500).

    Returns:
        Standard MCP envelope with queries list ordered by p95 DESC.
    """
    cutoff = parse_since(since)
    clamped_limit = clamp_limit(limit)

    async with async_session_factory() as db:
        grouped = await _fetch_grouped(db, cutoff, min_duration_ms, query_hash)

    grouped.sort(key=lambda r: r["p95_ms"] or 0, reverse=True)
    total_count = len(grouped)
    page = grouped[:clamped_limit]

    if compare_to == "7d_baseline":
        baseline_end = cutoff
        baseline_start = cutoff - timedelta(days=7)
        async with async_session_factory() as db:
            baseline = await _fetch_baseline(db, baseline_start, baseline_end, min_duration_ms)
        # Merge baseline p95 into each row
        for row in page:
            brow = baseline.get(row["query_hash"])
            row["baseline_p95_ms"] = brow["p95_ms"] if brow else None
            row["p95_delta_ms"] = (
                round(row["p95_ms"] - brow["p95_ms"], 1)
                if row["p95_ms"] is not None and brow and brow["p95_ms"] is not None
                else None
            )

    return build_envelope(
        "get_slow_queries",
        {"queries": page},
        total_count=total_count,
        limit=clamped_limit,
        since=cutoff,
    )


async def _fetch_grouped(
    db: Any,
    lower: Any,
    min_duration_ms: int,
    query_hash: str | None,
) -> list[dict[str, Any]]:
    """Fetch slow-query rows grouped by query_hash.

    Args:
        db: Active AsyncSession.
        lower: Lower bound for ts filter (inclusive).
        min_duration_ms: Minimum duration threshold in milliseconds.
        query_hash: Optional hash to restrict to a single query shape.

    Returns:
        List of dicts: query_hash, count, p50_ms, p95_ms, max_ms, source_file.
    """
    stmt = (
        select(
            SlowQueryLog.query_hash,
            func.count().label("count"),
            func.percentile_cont(0.5).within_group(SlowQueryLog.duration_ms).label("p50"),
            func.percentile_cont(0.95).within_group(SlowQueryLog.duration_ms).label("p95"),
            func.max(SlowQueryLog.duration_ms).label("max_ms"),
            func.max(SlowQueryLog.source_file).label("source_file"),
        )
        .where(
            SlowQueryLog.ts >= lower,
            SlowQueryLog.duration_ms >= min_duration_ms,
        )
        .group_by(SlowQueryLog.query_hash)
    )
    if query_hash is not None:
        # nosemgrep: no-timing-unsafe-compare — DB filter, not secret
        stmt = stmt.where(SlowQueryLog.query_hash == query_hash)

    rows = (await db.execute(stmt)).all()
    return [
        {
            "query_hash": r.query_hash,
            "count": r.count,
            "p50_ms": float(r.p50) if r.p50 is not None else None,
            "p95_ms": float(r.p95) if r.p95 is not None else None,
            "max_ms": r.max_ms,
            "source_file": r.source_file,
        }
        for r in rows
    ]


async def _fetch_baseline(
    db: Any,
    lower: Any,
    upper: Any,
    min_duration_ms: int,
) -> dict[str, dict[str, Any]]:
    """Fetch baseline p95 grouped by query_hash for a historical window.

    Args:
        db: Active AsyncSession.
        lower: Lower bound for ts filter (inclusive).
        upper: Upper bound for ts filter (exclusive).
        min_duration_ms: Minimum duration threshold in milliseconds.

    Returns:
        Dict mapping query_hash to {query_hash, p95_ms}.
    """
    stmt = (
        select(
            SlowQueryLog.query_hash,
            func.percentile_cont(0.95).within_group(SlowQueryLog.duration_ms).label("p95"),
        )
        .where(
            SlowQueryLog.ts >= lower,
            SlowQueryLog.ts < upper,
            SlowQueryLog.duration_ms >= min_duration_ms,
        )
        .group_by(SlowQueryLog.query_hash)
    )
    rows = (await db.execute(stmt)).all()
    return {
        r.query_hash: {
            "query_hash": r.query_hash,
            "p95_ms": float(r.p95) if r.p95 is not None else None,
        }
        for r in rows
    }
