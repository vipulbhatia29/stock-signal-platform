"""Collect environment snapshot for request_log rows.

Captures feature flags, active LLM model config, and rate limiter state.
Output capped at ~1KB to prevent JSONB bloat.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from backend.config import settings

logger = logging.getLogger(__name__)

# Max serialized size for environment_snapshot JSONB
_MAX_SNAPSHOT_BYTES = 1024


def collect_env_snapshot() -> dict[str, Any] | None:
    """Build environment snapshot dict from current settings.

    Returns None if OBS_ENABLED is False.

    Returns:
        Dict with feature flags and obs config, or None if obs is disabled.
        Automatically trimmed to fit within 1KB JSONB limit.
    """
    if not settings.OBS_ENABLED:
        return None

    snapshot: dict[str, Any] = {
        "flags": {
            "CONVERGENCE_SNAPSHOT_ENABLED": settings.CONVERGENCE_SNAPSHOT_ENABLED,
            "BACKTEST_ENABLED": settings.BACKTEST_ENABLED,
            "DEFAULT_FORECAST_HORIZONS": settings.DEFAULT_FORECAST_HORIZONS,
            "WATCHLIST_AUTO_INGEST": settings.WATCHLIST_AUTO_INGEST,
            "OBS_LEGACY_DIRECT_WRITES": settings.OBS_LEGACY_DIRECT_WRITES,
        },
        "obs": {
            "target_type": settings.OBS_TARGET_TYPE,
            "spool_enabled": settings.OBS_SPOOL_ENABLED,
        },
    }

    # Cap at 1KB
    serialized = json.dumps(snapshot, default=str)
    if len(serialized) > _MAX_SNAPSHOT_BYTES:
        snapshot.pop("obs", None)
        serialized = json.dumps(snapshot, default=str)
        if len(serialized) > _MAX_SNAPSHOT_BYTES:
            logger.warning("env_snapshot exceeds 1KB even after trimming")
            return None

    return snapshot
