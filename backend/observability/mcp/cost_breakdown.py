"""MCP tool: get_cost_breakdown.

Returns LLM cost and latency statistics grouped by provider, model, tier, or user,
with optional comparison to the prior window for trend analysis.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

from sqlalchemy import func, select

from backend.database import async_session_factory
from backend.models.chat import ChatSession
from backend.models.logs import LLMCallLog
from backend.observability.mcp._helpers import build_envelope, clamp_limit, parse_since

logger = logging.getLogger(__name__)

_VALID_BY_DIMS = {"provider", "model", "tier", "user"}


async def _fetch_stats(
    cutoff_start: datetime,
    cutoff_end: datetime | None,
    by: str,
    limit: int,
) -> list[dict[str, Any]]:
    """Fetch cost and latency stats grouped by the given dimension.

    Args:
        cutoff_start: Lower bound of the window (inclusive).
        cutoff_end: Upper bound of the window (exclusive). None = now.
        by: Grouping dimension — provider, model, tier, or user.
        limit: Maximum number of groups to return.

    Returns:
        List of dicts with group key and aggregated stats.
    """
    async with async_session_factory() as db:
        if by == "user":
            group_col = ChatSession.user_id
            stmt = (
                select(
                    group_col.label("group_key"),
                    func.sum(LLMCallLog.cost_usd).label("total_cost_usd"),
                    func.count().label("call_count"),
                    func.avg(LLMCallLog.cost_usd).label("avg_cost_per_call"),
                    func.percentile_cont(0.95)
                    .within_group(LLMCallLog.latency_ms)
                    .label("p95_latency_ms"),
                )
                .join(ChatSession, LLMCallLog.session_id == ChatSession.id, isouter=True)
                .where(LLMCallLog.created_at >= cutoff_start)
                .group_by(group_col)
                .order_by(func.sum(LLMCallLog.cost_usd).desc().nullslast())
                .limit(limit)
            )
        else:
            if by == "provider":
                group_col = LLMCallLog.provider
            elif by == "model":
                group_col = LLMCallLog.model
            else:  # tier
                group_col = LLMCallLog.tier

            stmt = (
                select(
                    group_col.label("group_key"),
                    func.sum(LLMCallLog.cost_usd).label("total_cost_usd"),
                    func.count().label("call_count"),
                    func.avg(LLMCallLog.cost_usd).label("avg_cost_per_call"),
                    func.percentile_cont(0.95)
                    .within_group(LLMCallLog.latency_ms)
                    .label("p95_latency_ms"),
                )
                .where(LLMCallLog.created_at >= cutoff_start)
                .group_by(group_col)
                .order_by(func.sum(LLMCallLog.cost_usd).desc().nullslast())
                .limit(limit)
            )

        if cutoff_end is not None:
            stmt = stmt.where(LLMCallLog.created_at < cutoff_end)

        rows = (await db.execute(stmt)).all()

    return [
        {
            by: str(r.group_key) if r.group_key is not None else None,
            "total_cost_usd": float(r.total_cost_usd) if r.total_cost_usd is not None else None,
            "call_count": r.call_count,
            "avg_cost_per_call": (
                float(r.avg_cost_per_call) if r.avg_cost_per_call is not None else None
            ),
            "p95_latency_ms": float(r.p95_latency_ms) if r.p95_latency_ms is not None else None,
        }
        for r in rows
    ]


async def get_cost_breakdown(
    window: str = "7d",
    by: str = "provider",
    compare_to: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Return LLM cost breakdown grouped by a single dimension.

    Queries LLMCallLog (public schema) and aggregates total_cost_usd,
    call_count, avg_cost_per_call, and p95_latency_ms per group.

    For ``by="user"``, joins ChatSession to resolve user_id. For all
    other dimensions (provider, model, tier), groups directly on the
    LLMCallLog column.

    Args:
        window: Relative time window (e.g. "7d", "24h"). Defaults to "7d".
        by: Grouping dimension. One of: provider, model, tier, user.
            Defaults to "provider".
        compare_to: Optional comparison mode. ``"prior_window"`` computes
            the same stats for the preceding equal-length window and adds
            delta fields to each group row.
        limit: Maximum number of groups to return (clamped to 500).

    Returns:
        Standard MCP envelope with groups list and optional prior_window.
    """
    if by not in _VALID_BY_DIMS:
        logger.warning("Invalid by=%r, falling back to 'provider'", by)
        by = "provider"

    cutoff = parse_since(window, default="7d")
    clamped_limit = clamp_limit(limit)

    if compare_to == "prior_window":
        window_duration = datetime.now().replace(tzinfo=cutoff.tzinfo) - cutoff
        prior_end = cutoff
        prior_start = cutoff - window_duration

        current_groups, prior_groups_list = await asyncio.gather(
            _fetch_stats(cutoff, None, by, clamped_limit),
            _fetch_stats(prior_start, prior_end, by, clamped_limit),
        )

        prior_by_key = {g[by]: g for g in prior_groups_list}

        for group in current_groups:
            key = group[by]
            prior = prior_by_key.get(key)
            group["prior_total_cost_usd"] = prior["total_cost_usd"] if prior else None
            group["prior_call_count"] = prior["call_count"] if prior else None
            group["delta_cost_usd"] = (
                round(
                    (group["total_cost_usd"] or 0) - (prior["total_cost_usd"] or 0),
                    6,
                )
                if group["total_cost_usd"] is not None and prior is not None
                else None
            )
            group["delta_call_count"] = (
                group["call_count"] - prior["call_count"] if prior is not None else None
            )
    else:
        current_groups = await _fetch_stats(cutoff, None, by, clamped_limit)

    return build_envelope(
        "get_cost_breakdown",
        {"by": by, "groups": current_groups},
        total_count=len(current_groups),
        limit=clamped_limit,
        since=cutoff,
    )
