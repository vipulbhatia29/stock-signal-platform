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
AUTH_EVENT_LOG_RETENTION_DAYS = 90
OAUTH_EVENT_LOG_RETENTION_DAYS = 90
EMAIL_SEND_LOG_RETENTION_DAYS = 90
SLOW_QUERY_LOG_RETENTION_DAYS = 30
CACHE_OPERATION_LOG_RETENTION_DAYS = 7
DB_POOL_EVENT_RETENTION_DAYS = 90
SCHEMA_MIGRATION_LOG_RETENTION_DAYS = 365
CELERY_HEARTBEAT_RETENTION_DAYS = 7
BEAT_SCHEDULE_RUN_RETENTION_DAYS = 90
CELERY_QUEUE_DEPTH_RETENTION_DAYS = 7
AGENT_INTENT_LOG_RETENTION_DAYS = 30
AGENT_REASONING_LOG_RETENTION_DAYS = 30
PROVIDER_HEALTH_SNAPSHOT_RETENTION_DAYS = 30
FRONTEND_ERROR_LOG_RETENTION_DAYS = 30
DEPLOY_EVENTS_RETENTION_DAYS = 365
FINDING_LOG_RETENTION_DAYS = 180


@celery_app.task(name="backend.tasks.retention.purge_old_forecasts_task")
@tracked_task("forecast_retention", trigger="scheduled")  # type: ignore[arg-type]
def purge_old_forecasts_task(run_id: uuid.UUID | None = None) -> dict:
    """Purge forecast results older than 30 days."""
    return asyncio.run(_purge_old_forecasts_async())


async def _purge_old_forecasts_async() -> dict:
    """Keep last 30 days of forecasts; hard delete older rows."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=FORECAST_RETENTION_DAYS)
    async with async_session_factory() as db:
        result = await db.execute(delete(ForecastResult).where(ForecastResult.created_at < cutoff))
        await db.commit()
        deleted = result.rowcount or 0  # type: ignore[union-attr]
    logger.info("Forecast retention: deleted %d rows older than %s", deleted, cutoff.date())
    return {"status": "ok", "deleted": deleted, "cutoff": cutoff.isoformat()}


@celery_app.task(name="backend.tasks.retention.purge_old_news_articles_task")
@tracked_task("news_retention", trigger="scheduled")  # type: ignore[arg-type]
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
@tracked_task("llm_call_log_retention", trigger="scheduled")  # type: ignore[arg-type]
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
@tracked_task("tool_execution_log_retention", trigger="scheduled")  # type: ignore[arg-type]
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
@tracked_task("pipeline_runs_retention", trigger="scheduled")  # type: ignore[arg-type]
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
        deleted = result.rowcount or 0  # type: ignore[union-attr]
    logger.info(
        "Pipeline runs retention: deleted %d rows older than %s",
        deleted,
        cutoff.date(),
    )
    return {"status": "ok", "deleted": deleted, "cutoff": cutoff.isoformat()}


@celery_app.task(name="backend.tasks.retention.purge_old_dq_check_history_task")
@tracked_task("dq_check_history_retention", trigger="scheduled")  # type: ignore[arg-type]
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
        deleted = result.rowcount or 0  # type: ignore[union-attr]
    logger.info(
        "DQ check history retention: deleted %d rows older than %s",
        deleted,
        cutoff.date(),
    )
    return {"status": "ok", "deleted": deleted, "cutoff": cutoff.isoformat()}


@celery_app.task(name="backend.tasks.retention.purge_old_request_logs_task")
@tracked_task("request_log_retention", trigger="scheduled")  # type: ignore[arg-type]
def purge_old_request_logs_task(run_id: uuid.UUID | None = None) -> dict:
    """Purge request_log older than 30 days using drop_chunks (hypertable)."""
    return asyncio.run(_purge_obs_table("observability.request_log", REQUEST_LOG_RETENTION_DAYS))


@celery_app.task(name="backend.tasks.retention.purge_old_api_error_logs_task")
@tracked_task("api_error_log_retention", trigger="scheduled")  # type: ignore[arg-type]
def purge_old_api_error_logs_task(run_id: uuid.UUID | None = None) -> dict:
    """Purge api_error_log older than 90 days using drop_chunks (hypertable)."""
    return asyncio.run(
        _purge_obs_table("observability.api_error_log", API_ERROR_LOG_RETENTION_DAYS)
    )


@celery_app.task(name="backend.tasks.retention.purge_old_auth_event_logs_task")
@tracked_task("auth_event_log_retention", trigger="scheduled")  # type: ignore[arg-type]
def purge_old_auth_event_logs_task(run_id: uuid.UUID | None = None) -> dict:
    """Purge auth_event_log older than 90 days using row-level DELETE (regular table)."""
    return asyncio.run(_purge_obs_regular_table("auth_event_log", AUTH_EVENT_LOG_RETENTION_DAYS))


@celery_app.task(name="backend.tasks.retention.purge_old_oauth_event_logs_task")
@tracked_task("oauth_event_log_retention", trigger="scheduled")  # type: ignore[arg-type]
def purge_old_oauth_event_logs_task(run_id: uuid.UUID | None = None) -> dict:
    """Purge oauth_event_log older than 90 days using row-level DELETE (regular table)."""
    return asyncio.run(_purge_obs_regular_table("oauth_event_log", OAUTH_EVENT_LOG_RETENTION_DAYS))


@celery_app.task(name="backend.tasks.retention.purge_old_email_send_logs_task")
@tracked_task("email_send_log_retention", trigger="scheduled")  # type: ignore[arg-type]
def purge_old_email_send_logs_task(run_id: uuid.UUID | None = None) -> dict:
    """Purge email_send_log older than 90 days using row-level DELETE (regular table)."""
    return asyncio.run(_purge_obs_regular_table("email_send_log", EMAIL_SEND_LOG_RETENTION_DAYS))


@celery_app.task(name="backend.tasks.retention.purge_old_slow_query_logs_task")
@tracked_task("slow_query_log_retention", trigger="scheduled")  # type: ignore[arg-type]
def purge_old_slow_query_logs_task(run_id: uuid.UUID | None = None) -> dict:
    """Purge slow_query_log older than 30 days using drop_chunks (hypertable)."""
    return asyncio.run(
        _purge_obs_table("observability.slow_query_log", SLOW_QUERY_LOG_RETENTION_DAYS)
    )


@celery_app.task(name="backend.tasks.retention.purge_old_cache_operation_logs_task")
@tracked_task("cache_operation_log_retention", trigger="scheduled")  # type: ignore[arg-type]
def purge_old_cache_operation_logs_task(run_id: uuid.UUID | None = None) -> dict:
    """Purge cache_operation_log older than 7 days using drop_chunks (hypertable)."""
    return asyncio.run(
        _purge_obs_table("observability.cache_operation_log", CACHE_OPERATION_LOG_RETENTION_DAYS)
    )


@celery_app.task(name="backend.tasks.retention.purge_old_db_pool_events_task")
@tracked_task("db_pool_event_retention", trigger="scheduled")  # type: ignore[arg-type]
def purge_old_db_pool_events_task(run_id: uuid.UUID | None = None) -> dict:
    """Purge db_pool_event older than 90 days using row-level DELETE (regular table)."""
    return asyncio.run(_purge_obs_regular_table("db_pool_event", DB_POOL_EVENT_RETENTION_DAYS))


@celery_app.task(name="backend.tasks.retention.purge_old_schema_migration_logs_task")
@tracked_task("schema_migration_log_retention", trigger="scheduled")  # type: ignore[arg-type]
def purge_old_schema_migration_logs_task(run_id: uuid.UUID | None = None) -> dict:
    """Purge schema_migration_log older than 365 days using row-level DELETE (regular table)."""
    return asyncio.run(
        _purge_obs_regular_table("schema_migration_log", SCHEMA_MIGRATION_LOG_RETENTION_DAYS)
    )


@celery_app.task(name="backend.tasks.retention.purge_old_celery_heartbeats_task")
@tracked_task("celery_heartbeat_retention", trigger="scheduled")  # type: ignore[arg-type]
def purge_old_celery_heartbeats_task(run_id: uuid.UUID | None = None) -> dict:
    """Purge celery_worker_heartbeat older than 7 days using drop_chunks (hypertable)."""
    return asyncio.run(
        _purge_obs_table("observability.celery_worker_heartbeat", CELERY_HEARTBEAT_RETENTION_DAYS)
    )


@celery_app.task(name="backend.tasks.retention.purge_old_beat_schedule_runs_task")
@tracked_task("beat_schedule_run_retention", trigger="scheduled")  # type: ignore[arg-type]
def purge_old_beat_schedule_runs_task(run_id: uuid.UUID | None = None) -> dict:
    """Purge beat_schedule_run older than 90 days using row-level DELETE (regular table)."""
    return asyncio.run(
        _purge_obs_regular_table("beat_schedule_run", BEAT_SCHEDULE_RUN_RETENTION_DAYS)
    )


@celery_app.task(name="backend.tasks.retention.purge_old_celery_queue_depths_task")
@tracked_task("celery_queue_depth_retention", trigger="scheduled")  # type: ignore[arg-type]
def purge_old_celery_queue_depths_task(run_id: uuid.UUID | None = None) -> dict:
    """Purge celery_queue_depth older than 7 days using drop_chunks (hypertable)."""
    return asyncio.run(
        _purge_obs_table("observability.celery_queue_depth", CELERY_QUEUE_DEPTH_RETENTION_DAYS)
    )


@celery_app.task(name="backend.tasks.retention.purge_old_agent_intent_logs_task")
@tracked_task("agent_intent_log_retention", trigger="scheduled")  # type: ignore[arg-type]
def purge_old_agent_intent_logs_task(run_id: uuid.UUID | None = None) -> dict:
    """Purge agent_intent_log older than 30 days using row-level DELETE."""
    return asyncio.run(
        _purge_obs_regular_table("agent_intent_log", AGENT_INTENT_LOG_RETENTION_DAYS)
    )


@celery_app.task(name="backend.tasks.retention.purge_old_agent_reasoning_logs_task")
@tracked_task("agent_reasoning_log_retention", trigger="scheduled")  # type: ignore[arg-type]
def purge_old_agent_reasoning_logs_task(run_id: uuid.UUID | None = None) -> dict:
    """Purge agent_reasoning_log older than 30 days using row-level DELETE."""
    return asyncio.run(
        _purge_obs_regular_table("agent_reasoning_log", AGENT_REASONING_LOG_RETENTION_DAYS)
    )


@celery_app.task(name="backend.tasks.retention.purge_old_provider_health_snapshots_task")
@tracked_task("provider_health_snapshot_retention", trigger="scheduled")  # type: ignore[arg-type]
def purge_old_provider_health_snapshots_task(run_id: uuid.UUID | None = None) -> dict:
    """Purge provider_health_snapshot older than 30 days using drop_chunks."""
    return asyncio.run(
        _purge_obs_table(
            "observability.provider_health_snapshot",
            PROVIDER_HEALTH_SNAPSHOT_RETENTION_DAYS,
        )
    )


@celery_app.task(name="backend.tasks.retention.purge_old_frontend_error_logs_task")
@tracked_task("frontend_error_log_retention", trigger="scheduled")  # type: ignore[arg-type]
def purge_old_frontend_error_logs_task(run_id: uuid.UUID | None = None) -> dict:
    """Purge frontend_error_log older than 30 days using row-level DELETE (regular table)."""
    return asyncio.run(
        _purge_obs_regular_table("frontend_error_log", FRONTEND_ERROR_LOG_RETENTION_DAYS)
    )


@celery_app.task(name="backend.tasks.retention.purge_old_deploy_events_task")
@tracked_task("deploy_events_retention", trigger="scheduled")  # type: ignore[arg-type]
def purge_old_deploy_events_task(run_id: uuid.UUID | None = None) -> dict:
    """Purge deploy_events older than 365 days using row-level DELETE (regular table)."""
    return asyncio.run(_purge_obs_regular_table("deploy_events", DEPLOY_EVENTS_RETENTION_DAYS))


@celery_app.task(name="backend.tasks.retention.purge_old_findings_task")
@tracked_task("finding_log_retention", trigger="scheduled")  # type: ignore[arg-type]
def purge_old_findings_task(run_id: uuid.UUID | None = None) -> dict:
    """Purge findings older than 180 days using row-level DELETE (regular table)."""
    return asyncio.run(_purge_old_findings_async())


async def _purge_old_findings_async() -> dict:
    """Delete observability.finding_log rows with created_at older than 180 days.

    Uses raw SQL DELETE (not ORM) to avoid importing FindingLog into the retention
    module (observability schema models must not be imported at module level).
    finding_log is a regular table — drop_chunks() does not apply.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=FINDING_LOG_RETENTION_DAYS)
    async with async_session_factory() as db:
        result = await db.execute(
            text(  # noqa: S608 — table name is a constant, not user input
                "DELETE FROM observability.finding_log WHERE created_at < :cutoff"
            ),
            {"cutoff": cutoff},
        )
        deleted = result.rowcount or 0  # type: ignore[union-attr]
        await db.commit()
    logger.info(
        "observability.finding_log retention: deleted %d rows older than %s",
        deleted,
        cutoff.date(),
    )
    return {"status": "ok", "deleted": deleted, "cutoff": cutoff.isoformat()}


async def _purge_obs_regular_table(table: str, retention_days: int) -> dict:
    """Row-level DELETE helper for regular (non-hypertable) observability tables.

    Auth-layer tables (auth_event_log, oauth_event_log, email_send_log) are low-volume
    regular tables. drop_chunks() does not apply — use row-level DELETE instead.

    Args:
        table: Unqualified table name within the observability schema.
        retention_days: Rows older than this many days are deleted.

    Returns:
        Dict with status, deleted_rows count, and retention_days.
    """
    _ALLOWED_TABLES = {
        "auth_event_log",
        "oauth_event_log",
        "email_send_log",
        "db_pool_event",
        "schema_migration_log",
        "beat_schedule_run",
        "agent_intent_log",
        "agent_reasoning_log",
        "frontend_error_log",
        "deploy_events",
    }
    if table not in _ALLOWED_TABLES:
        raise ValueError(f"Table {table!r} not in allowlist for regular-table retention")

    async with async_session_factory() as db:
        result = await db.execute(
            text(  # noqa: S608 — table name is a constant, not user input
                f"DELETE FROM observability.{table} WHERE ts < now() - INTERVAL :interval"
            ),
            {"interval": f"{retention_days} days"},
        )
        deleted = result.rowcount or 0  # type: ignore[union-attr]
        await db.commit()
    logger.info(
        "observability.%s retention: deleted %d rows older than %d days",
        table,
        deleted,
        retention_days,
    )
    return {"status": "ok", "deleted_rows": deleted, "retention_days": retention_days}


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
