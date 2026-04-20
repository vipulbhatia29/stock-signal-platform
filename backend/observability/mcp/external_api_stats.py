"""MCP tool: get_external_api_stats.

Returns aggregated statistics for outbound API calls to a specific provider,
including call counts, success rate, latency percentiles, cost totals,
error breakdowns, and rate-limit event counts. Optionally compares against
the prior window of equal duration.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from sqlalchemy import Integer, case, func, select

from backend.database import async_session_factory
from backend.observability.mcp._helpers import build_envelope, parse_since
from backend.observability.models import ExternalApiCallLog, RateLimiterEvent

logger = logging.getLogger(__name__)


async def get_external_api_stats(
    provider: str,
    window_min: int = 60,
    compare_to: str | None = None,
) -> dict[str, Any]:
    """Return aggregated statistics for a specific external API provider.

    Queries ExternalApiCallLog for the given provider and window. Computes
    call volume, success/error rates, latency percentiles, cost, and error
    breakdown. Optionally includes comparison against the prior equal window.

    Args:
        provider: Provider name to filter on (exact match, e.g. "openai").
        window_min: Window size in minutes to look back. Defaults to 60.
        compare_to: Optional comparison mode. "prior_window" computes stats
            for the preceding equal-duration window and returns deltas.

    Returns:
        Standard MCP envelope with provider stats, error breakdown,
        rate-limit event count, and optional prior window comparison.
    """
    cutoff = parse_since(f"{window_min}m")

    async with async_session_factory() as db:
        stats = await _fetch_stats(db, provider, cutoff)
        error_breakdown = await _fetch_error_breakdown(db, provider, cutoff)
        rate_limit_count = await _fetch_rate_limit_count(db, provider, cutoff)

    result: dict[str, Any] = {
        "provider": provider,
        "window_min": window_min,
        "stats": stats,
        "error_breakdown": error_breakdown,
        "rate_limit_events": rate_limit_count,
    }

    if compare_to == "prior_window":
        prior_end = cutoff
        prior_start = cutoff - timedelta(minutes=window_min)
        async with async_session_factory() as db:
            prior_stats = await _fetch_stats(db, provider, prior_start, upper=prior_end)
        result["prior_window"] = prior_stats
        result["deltas"] = _compute_deltas(stats, prior_stats)

    return build_envelope(
        "get_external_api_stats",
        result,
        since=cutoff,
    )


async def _fetch_stats(
    db: Any,
    provider: str,
    lower: Any,
    upper: Any = None,
) -> dict[str, Any]:
    """Fetch aggregated call statistics for a provider in a time range.

    Args:
        db: Active AsyncSession.
        provider: Provider name to filter.
        lower: Lower bound for ts filter (inclusive).
        upper: Optional upper bound for ts filter (exclusive). None = open ended.

    Returns:
        Dict with call_count, success_count, error_count, success_rate,
        p50_latency_ms, p95_latency_ms, total_cost_usd.
    """
    stmt = select(
        func.count().label("call_count"),
        func.sum(
            case(
                (ExternalApiCallLog.error_reason.is_(None), 1),
                else_=0,
            ).cast(Integer)
        ).label("success_count"),
        func.percentile_cont(0.5).within_group(ExternalApiCallLog.latency_ms).label("p50"),
        func.percentile_cont(0.95).within_group(ExternalApiCallLog.latency_ms).label("p95"),
        func.sum(ExternalApiCallLog.cost_usd).label("total_cost_usd"),
    ).where(
        ExternalApiCallLog.provider == provider,
        ExternalApiCallLog.ts >= lower,
    )
    if upper is not None:
        stmt = stmt.where(ExternalApiCallLog.ts < upper)

    row = (await db.execute(stmt)).one()

    call_count: int = row.call_count or 0
    success_count: int = int(row.success_count or 0)
    error_count = call_count - success_count
    success_rate = round(success_count / call_count, 4) if call_count > 0 else None

    return {
        "call_count": call_count,
        "success_count": success_count,
        "error_count": error_count,
        "success_rate": success_rate,
        "p50_latency_ms": float(row.p50) if row.p50 is not None else None,
        "p95_latency_ms": float(row.p95) if row.p95 is not None else None,
        "total_cost_usd": float(row.total_cost_usd) if row.total_cost_usd is not None else None,
    }


async def _fetch_error_breakdown(
    db: Any,
    provider: str,
    cutoff: Any,
) -> list[dict[str, Any]]:
    """Fetch per-error-reason counts for a provider since cutoff.

    Args:
        db: Active AsyncSession.
        provider: Provider name to filter.
        cutoff: Lower bound for ts filter.

    Returns:
        List of dicts with error_reason and count, ordered by count DESC.
    """
    stmt = (
        select(
            ExternalApiCallLog.error_reason,
            func.count().label("count"),
        )
        .where(
            ExternalApiCallLog.provider == provider,
            ExternalApiCallLog.ts >= cutoff,
            ExternalApiCallLog.error_reason.isnot(None),
        )
        .group_by(ExternalApiCallLog.error_reason)
        .order_by(func.count().desc())
    )
    rows = (await db.execute(stmt)).all()
    return [{"error_reason": r.error_reason, "count": r.count} for r in rows]


async def _fetch_rate_limit_count(
    db: Any,
    provider: str,
    cutoff: Any,
) -> int:
    """Fetch rate-limit event count for a provider since cutoff.

    Uses ILIKE match on limiter_name so "openai_chat" matches provider "openai".

    Args:
        db: Active AsyncSession.
        provider: Provider name pattern to match with ILIKE.
        cutoff: Lower bound for ts filter.

    Returns:
        Integer count of rate-limiter events matching the provider.
    """
    stmt = select(func.count()).where(
        RateLimiterEvent.ts >= cutoff,
        RateLimiterEvent.limiter_name.ilike(f"%{provider}%"),
    )
    result = (await db.execute(stmt)).scalar()
    return int(result or 0)


def _compute_deltas(
    current: dict[str, Any],
    prior: dict[str, Any],
) -> dict[str, Any]:
    """Compute absolute deltas between current and prior window stats.

    Args:
        current: Current window stats dict.
        prior: Prior window stats dict.

    Returns:
        Dict of delta values for numeric fields. None when either value is None.
    """
    numeric_fields = [
        "call_count",
        "success_count",
        "error_count",
        "success_rate",
        "p50_latency_ms",
        "p95_latency_ms",
        "total_cost_usd",
    ]
    deltas: dict[str, Any] = {}
    for field in numeric_fields:
        c = current.get(field)
        p = prior.get(field)
        if c is not None and p is not None:
            deltas[field] = round(c - p, 6)
        else:
            deltas[field] = None
    return deltas
