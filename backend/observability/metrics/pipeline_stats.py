"""Pipeline run and watermark query service (read-only)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.pipeline import PipelineRun, PipelineWatermark

logger = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")
NIGHTLY_HOUR = 21
NIGHTLY_MINUTE = 30


async def get_latest_run(db: AsyncSession) -> dict | None:
    """Return the most recent PipelineRun as a dict, or None if no runs exist.

    Includes status, ticker counts, duration, and trigger.
    """
    try:
        stmt = select(PipelineRun).order_by(PipelineRun.started_at.desc()).limit(1)
        result = await db.execute(stmt)
        run = result.scalar_one_or_none()
        if run is None:
            return None

        duration_seconds: float | None = None
        if run.completed_at and run.started_at:
            duration_seconds = (run.completed_at - run.started_at).total_seconds()

        return {
            "id": str(run.id),
            "pipeline_name": run.pipeline_name,
            "status": run.status,
            "started_at": run.started_at.isoformat(),
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            "total_duration_seconds": duration_seconds,
            "tickers_total": run.tickers_total,
            "tickers_succeeded": run.tickers_succeeded,
            "tickers_failed": run.tickers_failed,
            "step_durations": run.step_durations,
            "trigger": run.trigger,
            "retry_count": run.retry_count,
        }
    except Exception:
        logger.warning("Failed to fetch latest pipeline run", exc_info=True)
        return None


async def get_watermarks(db: AsyncSession) -> list[dict]:
    """Return all pipeline watermarks with gap detection.

    Each watermark includes a `days_since_last` field indicating how many
    days have elapsed since the last completed date.
    """
    try:
        stmt = select(PipelineWatermark).order_by(PipelineWatermark.pipeline_name)
        result = await db.execute(stmt)
        watermarks = result.scalars().all()

        now = datetime.now(tz=ET).date()
        out: list[dict] = []
        for wm in watermarks:
            days_gap = (now - wm.last_completed_date).days
            out.append(
                {
                    "pipeline_name": wm.pipeline_name,
                    "last_completed_date": wm.last_completed_date.isoformat(),
                    "last_completed_at": wm.last_completed_at.isoformat(),
                    "status": wm.status,
                    "days_since_last": days_gap,
                    "has_gap": days_gap > 1,
                }
            )
        return out
    except Exception:
        logger.warning("Failed to fetch pipeline watermarks", exc_info=True)
        return []


def get_next_run_time() -> str:
    """Calculate the next nightly pipeline run time (21:30 ET).

    Returns:
        ISO-formatted datetime string in ET timezone.
    """
    now = datetime.now(tz=ET)
    today_run = now.replace(hour=NIGHTLY_HOUR, minute=NIGHTLY_MINUTE, second=0, microsecond=0)

    if now < today_run:
        return today_run.isoformat()
    # Already past today's run time -- next run is tomorrow
    return (today_run + timedelta(days=1)).isoformat()


async def get_run_history(db: AsyncSession, days: int = 7) -> list[dict]:
    """Return pipeline runs from the last N days for drill-down.

    Args:
        db: Async database session.
        days: Number of days of history to retrieve (default 7).

    Returns:
        List of run dicts ordered by started_at descending.
    """
    try:
        cutoff = datetime.now(tz=ET) - timedelta(days=days)
        stmt = (
            select(PipelineRun)
            .where(PipelineRun.started_at >= cutoff)
            .order_by(PipelineRun.started_at.desc())
        )
        result = await db.execute(stmt)
        runs = result.scalars().all()

        out: list[dict] = []
        for run in runs:
            duration_seconds: float | None = None
            if run.completed_at and run.started_at:
                duration_seconds = (run.completed_at - run.started_at).total_seconds()
            out.append(
                {
                    "id": str(run.id),
                    "pipeline_name": run.pipeline_name,
                    "status": run.status,
                    "started_at": run.started_at.isoformat(),
                    "completed_at": (run.completed_at.isoformat() if run.completed_at else None),
                    "total_duration_seconds": duration_seconds,
                    "tickers_total": run.tickers_total,
                    "tickers_succeeded": run.tickers_succeeded,
                    "tickers_failed": run.tickers_failed,
                    "step_durations": run.step_durations,
                    "error_summary": run.error_summary,
                    "trigger": run.trigger,
                }
            )
        return out
    except Exception:
        logger.warning("Failed to fetch pipeline run history", exc_info=True)
        return []


async def get_failed_tickers(db: AsyncSession, run_id: str) -> dict | None:
    """Return error details for a specific pipeline run.

    Args:
        db: Async database session.
        run_id: UUID of the PipelineRun.

    Returns:
        Dict with run metadata and error_summary, or None if not found.
    """
    try:
        stmt = select(PipelineRun).where(PipelineRun.id == run_id)
        result = await db.execute(stmt)
        run = result.scalar_one_or_none()
        if run is None:
            return None

        return {
            "id": str(run.id),
            "pipeline_name": run.pipeline_name,
            "status": run.status,
            "tickers_failed": run.tickers_failed,
            "error_summary": run.error_summary,
        }
    except Exception:
        logger.warning("Failed to fetch failed tickers for run %s", run_id, exc_info=True)
        return None
