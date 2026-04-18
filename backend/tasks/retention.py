"""Nightly retention enforcement — purge old data across observability-adjacent tables.

news_articles, llm_call_log, and tool_execution_log use TimescaleDB drop_chunks()
instead of row-level DELETE because they are hypertables. Compressed chunks cannot
be deleted row-by-row; drop_chunks() handles both compressed and uncompressed chunks
transparently.

pipeline_runs and dq_check_history are regular tables and use raw SQL DELETE.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, text

from backend.database import async_session_factory
from backend.models.forecast import ForecastResult
from backend.tasks import celery_app
from backend.tasks.pipeline import tracked_task

logger = logging.getLogger(__name__)

FORECAST_RETENTION_DAYS = 30
NEWS_RETENTION_DAYS = 90
LLM_CALL_LOG_RETENTION_DAYS = 30
TOOL_EXECUTION_LOG_RETENTION_DAYS = 30
PIPELINE_RUNS_RETENTION_DAYS = 90
DQ_CHECK_HISTORY_RETENTION_DAYS = 90
REQUEST_LOG_RETENTION_DAYS = 30
API_ERROR_LOG_RETENTION_DAYS = 90


@celery_app.task(name="backend.tasks.retention.purge_old_forecasts_task")
@tracked_task("forecast_retention", trigger="scheduled")
def purge_old_forecasts_task(run_id: uuid.UUID | None = None) -> dict:
    """Purge forecast results older than 30 days."""
    return asyncio.run(_purge_old_forecasts_async())


async def _purge_old_forecasts_async() -> dict:
    """Keep last 30 days of forecasts; hard delete older rows."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=FORECAST_RETENTION_DAYS)
    async with async_session_factory() as db:
        result = await db.execute(delete(ForecastResult).where(ForecastResult.created_at < cutoff))
        await db.commit()
        deleted = result.rowcount or 0
    logger.info("Forecast retention: deleted %d rows older than %s", deleted, cutoff.date())
    return {"status": "ok", "deleted": deleted, "cutoff": cutoff.isoformat()}


@celery_app.task(name="backend.tasks.retention.purge_old_news_articles_task")
@tracked_task("news_retention", trigger="scheduled")
def purge_old_news_articles_task(run_id: uuid.UUID | None = None) -> dict:
    """Purge news articles older than 90 days."""
    return asyncio.run(_purge_old_news_articles_async())


async def _purge_old_news_articles_async() -> dict:
    """Drop TimescaleDB chunks older than 90 days from news_articles.

    Uses drop_chunks() instead of row-level DELETE because the table has a
    compression policy. drop_chunks() handles compressed chunks transparently
    and is significantly faster than row-level deletion on large tables.
    Daily aggregates (news_sentiment_daily) are retained forever.
    """
    async with async_session_factory() as db:
        result = await db.execute(
            text("SELECT drop_chunks('news_articles', older_than => INTERVAL :interval)"),
            {"interval": f"{NEWS_RETENTION_DAYS} days"},
        )
        rows = result.fetchall()
        dropped = len(rows)
        await db.commit()
    logger.info(
        "News retention: dropped %s chunks older than %d days",
        dropped,
        NEWS_RETENTION_DAYS,
    )
    return {"status": "ok", "dropped_chunks": dropped, "retention_days": NEWS_RETENTION_DAYS}


@celery_app.task(name="backend.tasks.retention.purge_old_llm_call_log_task")
@tracked_task("llm_call_log_retention", trigger="scheduled")
def purge_old_llm_call_log_task(run_id: uuid.UUID | None = None) -> dict:
    """Purge LLM call log chunks older than 30 days."""
    return asyncio.run(_purge_old_llm_call_log_async())


async def _purge_old_llm_call_log_async() -> dict:
    """Drop TimescaleDB chunks older than 30 days from llm_call_log.

    Uses drop_chunks() because llm_call_log is a hypertable (created in migration 008).
    drop_chunks() handles both compressed and uncompressed chunks transparently.
    """
    async with async_session_factory() as db:
        result = await db.execute(
            text("SELECT drop_chunks('llm_call_log', older_than => INTERVAL :interval)"),
            {"interval": f"{LLM_CALL_LOG_RETENTION_DAYS} days"},
        )
        rows = result.fetchall()
        dropped = len(rows)
        await db.commit()
    logger.info(
        "LLM call log retention: dropped %d chunks older than %d days",
        dropped,
        LLM_CALL_LOG_RETENTION_DAYS,
    )
    return {
        "status": "ok",
        "dropped_chunks": dropped,
        "retention_days": LLM_CALL_LOG_RETENTION_DAYS,
    }


@celery_app.task(name="backend.tasks.retention.purge_old_tool_execution_log_task")
@tracked_task("tool_execution_log_retention", trigger="scheduled")
def purge_old_tool_execution_log_task(run_id: uuid.UUID | None = None) -> dict:
    """Purge tool execution log chunks older than 30 days."""
    return asyncio.run(_purge_old_tool_execution_log_async())


async def _purge_old_tool_execution_log_async() -> dict:
    """Drop TimescaleDB chunks older than 30 days from tool_execution_log.

    Uses drop_chunks() because tool_execution_log is a hypertable (created in migration 008).
    drop_chunks() handles both compressed and uncompressed chunks transparently.
    """
    async with async_session_factory() as db:
        result = await db.execute(
            text("SELECT drop_chunks('tool_execution_log', older_than => INTERVAL :interval)"),
            {"interval": f"{TOOL_EXECUTION_LOG_RETENTION_DAYS} days"},
        )
        rows = result.fetchall()
        dropped = len(rows)
        await db.commit()
    logger.info(
        "Tool execution log retention: dropped %d chunks older than %d days",
        dropped,
        TOOL_EXECUTION_LOG_RETENTION_DAYS,
    )
    return {
        "status": "ok",
        "dropped_chunks": dropped,
        "retention_days": TOOL_EXECUTION_LOG_RETENTION_DAYS,
    }


@celery_app.task(name="backend.tasks.retention.purge_old_pipeline_runs_task")
@tracked_task("pipeline_runs_retention", trigger="scheduled")
def purge_old_pipeline_runs_task(run_id: uuid.UUID | None = None) -> dict:
    """Purge pipeline runs older than 90 days."""
    return asyncio.run(_purge_old_pipeline_runs_async())


async def _purge_old_pipeline_runs_async() -> dict:
    """Delete pipeline_runs rows with started_at older than 90 days.

    Uses raw SQL DELETE (not ORM) because pipeline_runs is a regular table
    and this avoids importing the PipelineRun model into the retention module.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=PIPELINE_RUNS_RETENTION_DAYS)
    async with async_session_factory() as db:
        result = await db.execute(
            text("DELETE FROM pipeline_runs WHERE started_at < :cutoff"),
            {"cutoff": cutoff},
        )
        await db.commit()
        deleted = result.rowcount or 0
    logger.info(
        "Pipeline runs retention: deleted %d rows older than %s",
        deleted,
        cutoff.date(),
    )
    return {"status": "ok", "deleted": deleted, "cutoff": cutoff.isoformat()}


@celery_app.task(name="backend.tasks.retention.purge_old_dq_check_history_task")
@tracked_task("dq_check_history_retention", trigger="scheduled")
def purge_old_dq_check_history_task(run_id: uuid.UUID | None = None) -> dict:
    """Purge DQ check history older than 90 days."""
    return asyncio.run(_purge_old_dq_check_history_async())


async def _purge_old_dq_check_history_async() -> dict:
    """Delete dq_check_history rows with detected_at older than 90 days.

    Uses raw SQL DELETE (not ORM) because dq_check_history is a regular table
    and this avoids importing the DqCheckHistory model into the retention module.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=DQ_CHECK_HISTORY_RETENTION_DAYS)
    async with async_session_factory() as db:
        result = await db.execute(
            text("DELETE FROM dq_check_history WHERE detected_at < :cutoff"),
            {"cutoff": cutoff},
        )
        await db.commit()
        deleted = result.rowcount or 0
    logger.info(
        "DQ check history retention: deleted %d rows older than %s",
        deleted,
        cutoff.date(),
    )
    return {"status": "ok", "deleted": deleted, "cutoff": cutoff.isoformat()}


@celery_app.task(name="backend.tasks.retention.purge_old_request_logs_task")
@tracked_task("request_log_retention", trigger="scheduled")
def purge_old_request_logs_task(run_id: uuid.UUID | None = None) -> dict:
    """Purge request_log older than 30 days using drop_chunks (hypertable)."""
    return asyncio.run(_purge_obs_table("observability.request_log", REQUEST_LOG_RETENTION_DAYS))


@celery_app.task(name="backend.tasks.retention.purge_old_api_error_logs_task")
@tracked_task("api_error_log_retention", trigger="scheduled")
def purge_old_api_error_logs_task(run_id: uuid.UUID | None = None) -> dict:
    """Purge api_error_log older than 90 days using drop_chunks (hypertable)."""
    return asyncio.run(
        _purge_obs_table("observability.api_error_log", API_ERROR_LOG_RETENTION_DAYS)
    )


async def _purge_obs_table(table: str, retention_days: int) -> dict:
    """Generic drop_chunks helper for observability hypertables.

    Args:
        table: Fully-qualified table name (e.g. "observability.request_log").
        retention_days: Number of days to retain data; older chunks are dropped.

    Returns:
        Dict with status, dropped_chunks count, and retention_days.
    """
    async with async_session_factory() as db:
        result = await db.execute(
            text(f"SELECT drop_chunks('{table}', older_than => INTERVAL :interval)"),  # noqa: S608
            {"interval": f"{retention_days} days"},
        )
        rows = result.fetchall()
        dropped = len(rows)
        await db.commit()
    logger.info(
        "%s retention: dropped %s chunks older than %d days", table, dropped, retention_days
    )
    return {"status": "ok", "dropped_chunks": dropped, "retention_days": retention_days}
