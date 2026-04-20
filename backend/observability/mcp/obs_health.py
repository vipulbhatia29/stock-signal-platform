"""MCP tool: get_observability_health.

Self-observability check — reports the health of the observability system itself:
last-write timestamps across key tables, spool directory size, buffer stats, and
the active OBS config snapshot.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from typing import Any

from sqlalchemy import func, select

from backend.config import settings
from backend.database import async_session_factory
from backend.observability.bootstrap import obs_client_var
from backend.observability.mcp._helpers import build_envelope
from backend.observability.models import (
    DeployEvent,
    ExternalApiCallLog,
    FindingLog,
    RequestLog,
    SlowQueryLog,
)

logger = logging.getLogger(__name__)


def _get_spool_size_bytes() -> int | None:
    """Sum the sizes of all files in the OBS spool directory.

    Args:
        (none — reads ``settings.OBS_SPOOL_DIR`` directly)

    Returns:
        Total size in bytes, or None if the directory is absent or unreadable.
    """
    spool_dir = settings.OBS_SPOOL_DIR
    try:
        total = 0
        for entry in os.scandir(spool_dir):
            if entry.is_file():
                total += entry.stat().st_size
        return total
    except (OSError, FileNotFoundError):
        return None


def _get_buffer_stats() -> dict[str, Any] | None:
    """Read queue depth and drop count from the ambient ObservabilityClient.

    Returns None if the client has not been initialized (e.g. during tests
    or when OBS is disabled).

    Returns:
        Dict with ``queue_depth`` and ``drops``, or None.
    """
    client = obs_client_var.get(None)
    if client is None:
        return None
    try:
        buf_stats = client._buffer.stats()
        return {
            "queue_depth": buf_stats.depth,
            "drops": buf_stats.drops,
        }
    except AttributeError:
        return None


async def _max_ts(model: Any, ts_col: Any) -> str | None:
    """Query MAX of a timestamp column from the given model.

    Args:
        model: SQLAlchemy ORM model class.
        ts_col: The mapped column to aggregate.

    Returns:
        ISO-formatted string of the max timestamp, or None if no rows.
    """
    async with async_session_factory() as db:
        result = await db.execute(select(func.max(ts_col)))
        val = result.scalar()
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.isoformat()
    return str(val)


async def get_observability_health() -> dict[str, Any]:
    """Return a self-health snapshot of the observability subsystem.

    Runs five MAX-timestamp queries in parallel (RequestLog,
    ExternalApiCallLog, SlowQueryLog, FindingLog, DeployEvent), reads
    the spool directory size, and samples the in-process event buffer.

    Args:
        (none)

    Returns:
        Standard MCP envelope with:
        - ``last_writes``: per-table ISO timestamp of most recent write.
        - ``spool_size_bytes``: total spool file size, or None.
        - ``buffer``: queue_depth + drops from ObservabilityClient, or None.
        - ``config``: OBS_ENABLED, OBS_SPOOL_ENABLED, OBS_TARGET_TYPE,
          OBS_LEGACY_DIRECT_WRITES settings snapshot.
    """
    (
        last_request,
        last_external_api,
        last_slow_query,
        last_finding,
        last_deploy,
    ) = await asyncio.gather(
        _max_ts(RequestLog, RequestLog.ts),
        _max_ts(ExternalApiCallLog, ExternalApiCallLog.ts),
        _max_ts(SlowQueryLog, SlowQueryLog.ts),
        _max_ts(FindingLog, FindingLog.opened_at),
        _max_ts(DeployEvent, DeployEvent.ts),
    )

    spool_size = _get_spool_size_bytes()
    buffer_stats = _get_buffer_stats()

    config = {
        "OBS_ENABLED": settings.OBS_ENABLED,
        "OBS_SPOOL_ENABLED": settings.OBS_SPOOL_ENABLED,
        "OBS_TARGET_TYPE": settings.OBS_TARGET_TYPE,
        "OBS_LEGACY_DIRECT_WRITES": settings.OBS_LEGACY_DIRECT_WRITES,
    }

    return build_envelope(
        "get_observability_health",
        {
            "last_writes": {
                "request_log": last_request,
                "external_api_call_log": last_external_api,
                "slow_query_log": last_slow_query,
                "finding_log": last_finding,
                "deploy_events": last_deploy,
            },
            "spool_size_bytes": spool_size,
            "buffer": buffer_stats,
            "config": config,
        },
    )
