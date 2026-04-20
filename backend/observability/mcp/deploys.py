"""MCP tool: get_deploys.

Returns recent deployment events from the observability.deploy_events table,
ordered by timestamp descending with optional time-window filtering.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import func, select

from backend.database import async_session_factory
from backend.observability.mcp._helpers import build_envelope, clamp_limit, parse_since
from backend.observability.models import DeployEvent

logger = logging.getLogger(__name__)


async def get_deploys(
    since: str = "30d",
    limit: int = 50,
) -> dict[str, Any]:
    """Return recent deployment events from observability.deploy_events.

    Queries all deploy events within the given time window, ordered by
    timestamp descending. Each row exposes git metadata, migration list,
    duration, and status for correlation with incidents and anomalies.

    Args:
        since: Relative time window (e.g. "30d", "7d"). Defaults to "30d".
        limit: Maximum number of results to return (clamped to 500).

    Returns:
        Standard MCP envelope with deploys list ordered by ts DESC.
    """
    cutoff = parse_since(since, default="30d")
    clamped_limit = clamp_limit(limit)

    async with async_session_factory() as db:
        count_stmt = select(func.count()).where(DeployEvent.ts >= cutoff)
        total = (await db.execute(count_stmt)).scalar() or 0
        stmt = (
            select(DeployEvent)
            .where(DeployEvent.ts >= cutoff)
            .order_by(DeployEvent.ts.desc())
            .limit(clamped_limit)
        )
        rows = (await db.execute(stmt)).scalars().all()

    deploys = [
        {
            "ts": r.ts.isoformat() if r.ts is not None else None,
            "git_sha": r.git_sha,
            "branch": r.branch,
            "pr_number": r.pr_number,
            "author": r.author,
            "commit_message": r.commit_message,
            "migrations_applied": r.migrations_applied,
            "env": r.env,
            "deploy_duration_seconds": r.deploy_duration_seconds,
            "status": r.status,
        }
        for r in rows
    ]

    return build_envelope(
        "get_deploys",
        {"deploys": deploys},
        total_count=total,
        limit=clamped_limit,
        since=cutoff,
    )
