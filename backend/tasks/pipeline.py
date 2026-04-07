"""Pipeline infrastructure — run tracking, watermark management, gap detection.

All methods are async and should be called via asyncio.run() from Celery tasks.
"""

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import date, datetime, timedelta, timezone
from functools import wraps
from typing import Any, Literal, ParamSpec, TypeVar

import pandas as pd
from sqlalchemy import select, update

from backend.database import async_session_factory
from backend.models.pipeline import PipelineRun, PipelineWatermark

logger = logging.getLogger(__name__)

# Stale run threshold: if a run has been "running" for > 1 hour, mark it failed
STALE_RUN_THRESHOLD = timedelta(hours=1)

# ---------------------------------------------------------------------------
# Hard Rule #10: never pass str(e) or repr(e) as an error code.
# TickerFailureReason is an exhaustive Literal of safe, static strings.
# Add new values here via PR — do NOT add dynamic runtime strings.
# ---------------------------------------------------------------------------
TickerFailureReason = Literal[
    "fetch_failed",
    "score_failed",
    "timeout",
    "rate_limit",
    "unknown_error",
    "retrain failed",
    "refresh failed",
]


class PipelineRunner:
    """Manages pipeline execution lifecycle — start, track, complete, watermark."""

    async def start_run(
        self,
        pipeline_name: str,
        trigger: str = "scheduled",
        tickers_total: int = 0,
    ) -> uuid.UUID:
        """Create a PipelineRun row and return the run_id.

        Args:
            pipeline_name: Name of the pipeline (e.g., "price_refresh").
            trigger: How the run was triggered ("scheduled", "backfill", "manual").
            tickers_total: Expected number of tickers to process.

        Returns:
            UUID of the new PipelineRun row.
        """
        run_id = uuid.uuid4()
        async with async_session_factory() as session:
            run = PipelineRun(
                id=run_id,
                pipeline_name=pipeline_name,
                started_at=datetime.now(timezone.utc),
                status="running",
                tickers_total=tickers_total,
                tickers_succeeded=0,
                tickers_failed=0,
                trigger=trigger,
            )
            session.add(run)
            await session.commit()
            logger.info(
                "Pipeline run started: %s [%s] (%d tickers)",
                pipeline_name,
                run_id,
                tickers_total,
            )
        return run_id

    async def record_ticker_success(self, run_id: uuid.UUID, ticker: str) -> None:
        """Increment tickers_succeeded for a pipeline run.

        Args:
            run_id: The PipelineRun UUID.
            ticker: Ticker symbol that succeeded.
        """
        async with async_session_factory() as session:
            result = await session.execute(select(PipelineRun).where(PipelineRun.id == run_id))
            run = result.scalar_one()
            run.tickers_succeeded += 1
            await session.commit()
        logger.debug("Pipeline %s: %s succeeded", run_id, ticker)

    async def record_ticker_failure(
        self, run_id: uuid.UUID, ticker: str, error: TickerFailureReason
    ) -> None:
        """Increment tickers_failed and add error to error_summary.

        Hard Rule #10: ``error`` must be a static :data:`TickerFailureReason`
        string — never ``str(e)`` or ``repr(e)``. Pyright enforces this at
        type-check time; add new values to the ``TickerFailureReason`` union
        via PR, never inline at the call site.

        Args:
            run_id: The PipelineRun UUID.
            ticker: Ticker symbol that failed.
            error: Static error code from :data:`TickerFailureReason`.
        """
        async with async_session_factory() as session:
            result = await session.execute(select(PipelineRun).where(PipelineRun.id == run_id))
            run = result.scalar_one()
            run.tickers_failed += 1
            if run.error_summary is None:
                run.error_summary = {}
            run.error_summary[ticker] = error
            await session.commit()
        logger.warning("Pipeline %s: %s failed — %s", run_id, ticker, error)

    async def record_step_duration(
        self, run_id: uuid.UUID, step_name: str, duration_seconds: float
    ) -> None:
        """Atomic JSONB merge — safe for concurrent step writes.

        Args:
            run_id: The PipelineRun UUID.
            step_name: Name of the pipeline step (e.g., "price_refresh").
            duration_seconds: How long the step took.
        """
        import json as json_mod

        from sqlalchemy import text

        try:
            step_json = json_mod.dumps({step_name: round(duration_seconds, 1)})
            async with async_session_factory() as session:
                await session.execute(
                    text("""
                        UPDATE pipeline_runs
                        SET step_durations = COALESCE(step_durations, '{}'::jsonb)
                            || :step_json::jsonb
                        WHERE id = :run_id
                    """),
                    {
                        "step_json": step_json,
                        "run_id": str(run_id),
                    },
                )
                await session.commit()
        except Exception:
            logger.warning(
                "Failed to record step duration for %s/%s", run_id, step_name, exc_info=True
            )

    async def complete_run(self, run_id: uuid.UUID) -> str:
        """Complete a pipeline run — set status based on success/failure ratio.

        Args:
            run_id: The PipelineRun UUID.

        Returns:
            Final status string ("success", "partial", or "failed").
        """
        async with async_session_factory() as session:
            result = await session.execute(select(PipelineRun).where(PipelineRun.id == run_id))
            run = result.scalar_one()
            run.completed_at = datetime.now(timezone.utc)

            # Compute total duration
            if run.started_at:
                run.total_duration_seconds = (run.completed_at - run.started_at).total_seconds()

            if run.tickers_failed == 0:
                run.status = "success"
            elif run.tickers_succeeded == 0:
                run.status = "failed"
            else:
                run.status = "partial"

            await session.commit()
            logger.info(
                "Pipeline run completed: %s — %s (%d/%d succeeded)",
                run.pipeline_name,
                run.status,
                run.tickers_succeeded,
                run.tickers_total,
            )
            return run.status

    async def update_watermark(self, pipeline_name: str, completed_date: date) -> None:
        """Update or create a PipelineWatermark atomically.

        Args:
            pipeline_name: Name of the pipeline.
            completed_date: The date that was just completed.
        """
        now = datetime.now(timezone.utc)
        async with async_session_factory() as session:
            result = await session.execute(
                select(PipelineWatermark).where(PipelineWatermark.pipeline_name == pipeline_name)
            )
            watermark = result.scalar_one_or_none()

            if watermark is None:
                watermark = PipelineWatermark(
                    pipeline_name=pipeline_name,
                    last_completed_date=completed_date,
                    last_completed_at=now,
                    status="ok",
                )
                session.add(watermark)
            else:
                watermark.last_completed_date = completed_date
                watermark.last_completed_at = now
                watermark.status = "ok"

            await session.commit()
            logger.info(
                "Watermark updated: %s → %s",
                pipeline_name,
                completed_date,
            )

    async def detect_stale_runs(self) -> list[uuid.UUID]:
        """Detect pipeline runs stuck in 'running' for > 1 hour. Mark them failed.

        Returns:
            List of stale run IDs that were marked failed.
        """
        cutoff = datetime.now(timezone.utc) - STALE_RUN_THRESHOLD
        stale_ids: list[uuid.UUID] = []

        async with async_session_factory() as session:
            result = await session.execute(
                select(PipelineRun).where(
                    PipelineRun.status == "running",
                    PipelineRun.started_at < cutoff,
                )
            )
            stale_runs = result.scalars().all()

            for run in stale_runs:
                run.status = "failed"
                run.completed_at = datetime.now(timezone.utc)
                if run.error_summary is None:
                    run.error_summary = {}
                run.error_summary["_stale"] = "Run exceeded 1-hour threshold"
                stale_ids.append(run.id)
                logger.warning(
                    "Stale run detected and marked failed: %s [%s]",
                    run.pipeline_name,
                    run.id,
                )

            await session.commit()

        return stale_ids


# ---------------------------------------------------------------------------
# Gap detection and recovery
# ---------------------------------------------------------------------------


async def detect_gap(pipeline_name: str) -> list[date]:
    """Detect missing trading days since the last watermark.

    Args:
        pipeline_name: Name of the pipeline to check.

    Returns:
        List of missing trading dates in chronological order.
        Empty list if no gap or no watermark exists.
    """
    async with async_session_factory() as session:
        result = await session.execute(
            select(PipelineWatermark).where(PipelineWatermark.pipeline_name == pipeline_name)
        )
        watermark = result.scalar_one_or_none()

    if watermark is None:
        logger.info("No watermark for %s — no gap to detect", pipeline_name)
        return []

    last_date = watermark.last_completed_date
    today = datetime.now(timezone.utc).date()

    # Generate all business days between last_completed_date and yesterday
    # (today's data may not be available yet)
    yesterday = today - timedelta(days=1)
    if last_date >= yesterday:
        return []

    # Business day range (excludes weekends)
    bday_range = pd.bdate_range(
        start=last_date + timedelta(days=1),
        end=yesterday,
    )
    missing_days = [d.date() for d in bday_range]

    if missing_days:
        logger.info(
            "Gap detected for %s: %d missing days (%s to %s)",
            pipeline_name,
            len(missing_days),
            missing_days[0],
            missing_days[-1],
        )

    return missing_days


async def set_watermark_status(pipeline_name: str, status: str) -> None:
    """Set the watermark status (e.g., 'backfilling', 'ok', 'failed').

    Args:
        pipeline_name: Name of the pipeline.
        status: New status string.
    """
    async with async_session_factory() as session:
        await session.execute(
            update(PipelineWatermark)
            .where(PipelineWatermark.pipeline_name == pipeline_name)
            .values(status=status)
        )
        await session.commit()


# ---------------------------------------------------------------------------
# Exponential backoff helper
# ---------------------------------------------------------------------------


async def with_retry(
    coro_factory: Any,
    max_retries: int = 3,
    base_delay: float = 1.0,
) -> Any:
    """Retry an async operation with exponential backoff.

    Args:
        coro_factory: A callable that returns a coroutine (called each retry).
        max_retries: Maximum number of retry attempts.
        base_delay: Base delay in seconds (doubled each retry).

    Returns:
        The result of the coroutine on success.

    Raises:
        The last exception if all retries are exhausted.
    """
    last_exception: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return await coro_factory()
        except Exception as e:
            last_exception = e
            if attempt < max_retries:
                delay = base_delay * (2**attempt)
                logger.warning(
                    "Retry %d/%d failed: %s. Retrying in %.1fs...",
                    attempt + 1,
                    max_retries,
                    e,
                    delay,
                )
                await asyncio.sleep(delay)
            else:
                logger.error(
                    "All %d retries exhausted: %s",
                    max_retries + 1,
                    e,
                )
    raise last_exception  # type: ignore[misc]


# ---------------------------------------------------------------------------
# @tracked_task decorator — wraps an async function in the PipelineRunner lifecycle
# ---------------------------------------------------------------------------

P = ParamSpec("P")
R = TypeVar("R")


def tracked_task(
    pipeline_name: str,
    *,
    trigger: str = "scheduled",
) -> Callable[[Callable[..., Awaitable[R]]], Callable[..., Awaitable[R]]]:
    """Decorate an async task function with the PipelineRunner lifecycle.

    The decorated function is called with ``run_id: uuid.UUID`` as an
    extra keyword argument. On success, the pipeline run is marked
    completed; on exception the run is marked failed (with a generic
    error_summary — never the raw exception text, per Hard Rule #10) and
    the exception re-raises so Celery retry policy still triggers.

    Callers may pass ``tickers_total`` as a kwarg — it is consumed by the
    decorator (not forwarded to the wrapped function) and recorded on the
    pipeline_runs row.

    Usage (adopted in Spec D, not this spec)::

        @shared_task(name="tasks.news_sentiment")
        def nightly_news_sentiment_task() -> dict:
            return asyncio.run(_run())

        @tracked_task("news_sentiment")
        async def _run(*, run_id: uuid.UUID) -> dict:
            tickers = await _load_universe()
            for t in tickers:
                try:
                    await _score_one(t)
                    await _runner.record_ticker_success(run_id, t)
                except Exception:
                    # Hard Rule #10: never pass str(e) / repr(e) — use a
                    # static TickerFailureReason string instead.
                    await _runner.record_ticker_failure(run_id, t, "score_failed")
            return {"tickers": len(tickers)}

    Args:
        pipeline_name: Name recorded in pipeline_runs.pipeline_name.
        trigger: "scheduled" | "backfill" | "manual".

    Returns:
        A decorator that wraps an async function with the runner lifecycle.
    """

    def decorator(fn: Callable[..., Awaitable[R]]) -> Callable[..., Awaitable[R]]:
        """Inner decorator that binds the PipelineRunner to the function."""
        runner = PipelineRunner()

        @wraps(fn)
        async def wrapper(*args: object, **kwargs: object) -> R:
            """Wrapper that runs the full PipelineRunner lifecycle."""
            tickers_total_raw = kwargs.pop("tickers_total", 0)
            tickers_total = int(tickers_total_raw)  # type: ignore[arg-type]
            run_id = await runner.start_run(
                pipeline_name=pipeline_name,
                trigger=trigger,
                tickers_total=tickers_total,
            )
            try:
                result = await fn(*args, run_id=run_id, **kwargs)
            except Exception:
                logger.exception(
                    "Tracked task %s crashed — marking run %s failed",
                    pipeline_name,
                    run_id,
                )
                try:
                    async with async_session_factory() as session:
                        stmt = (
                            update(PipelineRun)
                            .where(PipelineRun.id == run_id)
                            .values(
                                status="failed",
                                completed_at=datetime.now(timezone.utc),
                                error_summary={"_exception": "see logs"},
                            )
                        )
                        await session.execute(stmt)
                        await session.commit()
                except Exception:
                    logger.warning("Failed to mark run %s as failed", run_id, exc_info=True)
                raise
            else:
                await runner.complete_run(run_id)
                return result  # type: ignore[return-value]

        return wrapper

    return decorator
