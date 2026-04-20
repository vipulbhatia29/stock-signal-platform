"""MCP tool: diagnose_pipeline.

Returns a diagnostic summary for a named pipeline, including recent run
history, watermark state, consecutive failure count, and ticker success rate.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select

from backend.database import async_session_factory
from backend.models.pipeline import PipelineRun, PipelineWatermark
from backend.observability.mcp._helpers import build_envelope

logger = logging.getLogger(__name__)


async def diagnose_pipeline(
    pipeline_name: str,
    recent_n: int = 5,
) -> dict[str, Any]:
    """Return a diagnostic summary for a named pipeline.

    Fetches the last ``recent_n`` PipelineRun rows and the current
    PipelineWatermark, then derives failure patterns and ticker success rates.

    Args:
        pipeline_name: The exact name of the pipeline to diagnose.
        recent_n: Number of recent runs to fetch. Defaults to 5.

    Returns:
        Standard MCP envelope with runs, watermark, failure_pattern,
        and ticker_success_rate.
    """
    n = max(1, recent_n)

    async with async_session_factory() as db:
        # Fetch recent runs
        runs_stmt = (
            select(PipelineRun)
            .where(PipelineRun.pipeline_name == pipeline_name)
            .order_by(PipelineRun.started_at.desc())
            .limit(n)
        )
        runs = (await db.execute(runs_stmt)).scalars().all()

        # Fetch watermark
        wm_stmt = select(PipelineWatermark).where(PipelineWatermark.pipeline_name == pipeline_name)
        watermark = (await db.execute(wm_stmt)).scalar_one_or_none()

    # Derive consecutive failure count (most-recent first)
    consecutive_failures = 0
    for run in runs:
        if run.status == "failed":
            consecutive_failures += 1
        else:
            break

    # Aggregate ticker success rate across all fetched runs
    total_tickers = sum(r.tickers_total for r in runs)
    total_succeeded = sum(r.tickers_succeeded for r in runs)
    ticker_success_rate = round(total_succeeded / total_tickers, 4) if total_tickers > 0 else None

    result: dict[str, Any] = {
        "pipeline_name": pipeline_name,
        "runs": [_run_to_dict(r) for r in runs],
        "watermark": _watermark_to_dict(watermark),
        "failure_pattern": {
            "consecutive_failures": consecutive_failures,
            "is_currently_failing": consecutive_failures > 0,
        },
        "ticker_success_rate": ticker_success_rate,
    }

    return build_envelope("diagnose_pipeline", result)


def _run_to_dict(r: PipelineRun) -> dict[str, Any]:
    """Serialize a PipelineRun ORM row to a JSON-safe dict.

    Args:
        r: PipelineRun ORM instance.

    Returns:
        Dict with all diagnostic-relevant fields.
    """
    return {
        "id": str(r.id),
        "pipeline_name": r.pipeline_name,
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        "status": r.status,
        "tickers_total": r.tickers_total,
        "tickers_succeeded": r.tickers_succeeded,
        "tickers_failed": r.tickers_failed,
        "error_summary": r.error_summary,
        "step_durations": r.step_durations,
        "total_duration_seconds": r.total_duration_seconds,
        "retry_count": r.retry_count,
    }


def _watermark_to_dict(wm: PipelineWatermark | None) -> dict[str, Any] | None:
    """Serialize a PipelineWatermark to a JSON-safe dict.

    Args:
        wm: PipelineWatermark ORM instance, or None if not found.

    Returns:
        Dict with watermark fields, or None if watermark is absent.
    """
    if wm is None:
        return None
    return {
        "pipeline_name": wm.pipeline_name,
        "last_completed_date": wm.last_completed_date.isoformat()
        if wm.last_completed_date
        else None,
        "last_completed_at": wm.last_completed_at.isoformat() if wm.last_completed_at else None,
        "status": wm.status,
    }
