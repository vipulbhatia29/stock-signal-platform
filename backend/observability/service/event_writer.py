"""Routes events by event_type to the right repository.

PR2a ships a no-op DEBUG logger — validates SDK end-to-end. PR4 adds external_api_call_log +
rate_limiter_event writers. PR5 adds writers for refactored legacy emitters.
"""

from __future__ import annotations

import logging

from backend.observability.schema.v1 import EventType, ObsEventBase

logger = logging.getLogger(__name__)


async def write_batch(events: list[ObsEventBase]) -> None:
    """Write a batch of events to their respective stores.

    Groups events by event_type and delegates each group to its dedicated
    batch writer for efficient DB persistence (single session per group).
    Writers are imported lazily to avoid circular imports.
    Unrecognised event types are logged at DEBUG level.

    Args:
        events: Batch of events to persist. Typically drained from the in-memory
            buffer by the flush loop in ObservabilityClient.
    """
    # Group events by type for batch persistence.
    external_api_events: list = []
    rate_limiter_events: list = []
    llm_call_events: list = []
    tool_execution_events: list = []
    login_attempt_events: list = []
    dq_finding_events: list = []
    pipeline_lifecycle_events: list = []
    request_log_events: list = []
    api_error_log_events: list = []
    auth_event_events: list = []
    oauth_event_events: list = []
    email_send_events: list = []
    slow_query_events: list = []
    db_pool_events: list = []
    schema_migration_events: list = []
    cache_operation_events: list = []
    celery_heartbeat_events: list = []
    beat_schedule_run_events: list = []
    celery_queue_depth_events: list = []

    for event in events:
        try:
            if event.event_type == EventType.EXTERNAL_API_CALL:
                external_api_events.append(event)
            elif event.event_type == EventType.RATE_LIMITER_EVENT:
                rate_limiter_events.append(event)
            elif event.event_type == EventType.LLM_CALL:
                llm_call_events.append(event)
            elif event.event_type == EventType.TOOL_EXECUTION:
                tool_execution_events.append(event)
            elif event.event_type == EventType.LOGIN_ATTEMPT:
                login_attempt_events.append(event)
            elif event.event_type == EventType.DQ_FINDING:
                dq_finding_events.append(event)
            elif event.event_type == EventType.PIPELINE_LIFECYCLE:
                pipeline_lifecycle_events.append(event)
            elif event.event_type == EventType.REQUEST_LOG:
                request_log_events.append(event)
            elif event.event_type == EventType.API_ERROR_LOG:
                api_error_log_events.append(event)
            elif event.event_type == EventType.AUTH_EVENT:
                auth_event_events.append(event)
            elif event.event_type == EventType.OAUTH_EVENT:
                oauth_event_events.append(event)
            elif event.event_type == EventType.EMAIL_SEND:
                email_send_events.append(event)
            elif event.event_type == EventType.SLOW_QUERY:
                slow_query_events.append(event)
            elif event.event_type == EventType.DB_POOL_EVENT:
                db_pool_events.append(event)
            elif event.event_type == EventType.SCHEMA_MIGRATION:
                schema_migration_events.append(event)
            elif event.event_type == EventType.CACHE_OPERATION:
                cache_operation_events.append(event)
            elif event.event_type == EventType.CELERY_HEARTBEAT:
                celery_heartbeat_events.append(event)
            elif event.event_type == EventType.BEAT_SCHEDULE_RUN:
                beat_schedule_run_events.append(event)
            elif event.event_type == EventType.CELERY_QUEUE_DEPTH:
                celery_queue_depth_events.append(event)
            else:
                logger.debug("obs.event.unhandled", extra={"event_type": event.event_type.value})
        except Exception:  # noqa: BLE001 — per-event error isolation
            logger.warning("obs.event.classify_failed", exc_info=True)

    if external_api_events:
        try:
            from backend.observability.service.external_api_writer import (
                persist_external_api_calls,
            )

            await persist_external_api_calls(external_api_events)
        except Exception:  # noqa: BLE001 — writer errors must not propagate
            logger.warning("obs.writer.external_api_batch.failed", exc_info=True)

    if rate_limiter_events:
        try:
            from backend.observability.service.rate_limiter_writer import (
                persist_rate_limiter_events,
            )

            await persist_rate_limiter_events(rate_limiter_events)
        except Exception:  # noqa: BLE001 — writer errors must not propagate
            logger.warning("obs.writer.rate_limiter_batch.failed", exc_info=True)

    # Legacy emitter writers (PR5)
    if llm_call_events:
        try:
            from backend.observability.service.legacy_emitters_writer import persist_llm_calls

            await persist_llm_calls(llm_call_events)
        except Exception:  # noqa: BLE001 — writer errors must not propagate
            logger.warning("obs.writer.llm_call_batch.failed", exc_info=True)

    if tool_execution_events:
        try:
            from backend.observability.service.legacy_emitters_writer import (
                persist_tool_executions,
            )

            await persist_tool_executions(tool_execution_events)
        except Exception:  # noqa: BLE001 — writer errors must not propagate
            logger.warning("obs.writer.tool_execution_batch.failed", exc_info=True)

    if login_attempt_events:
        try:
            from backend.observability.service.legacy_emitters_writer import (
                persist_login_attempts,
            )

            await persist_login_attempts(login_attempt_events)
        except Exception:  # noqa: BLE001 — writer errors must not propagate
            logger.warning("obs.writer.login_attempt_batch.failed", exc_info=True)

    if dq_finding_events:
        try:
            from backend.observability.service.legacy_emitters_writer import persist_dq_findings

            await persist_dq_findings(dq_finding_events)
        except Exception:  # noqa: BLE001 — writer errors must not propagate
            logger.warning("obs.writer.dq_finding_batch.failed", exc_info=True)

    if pipeline_lifecycle_events:
        try:
            from backend.observability.service.legacy_emitters_writer import (
                persist_pipeline_lifecycle,
            )

            await persist_pipeline_lifecycle(pipeline_lifecycle_events)
        except Exception:  # noqa: BLE001 — writer errors must not propagate
            logger.warning("obs.writer.pipeline_lifecycle_batch.failed", exc_info=True)

    if request_log_events:
        try:
            from backend.observability.service.request_log_writer import persist_request_logs

            await persist_request_logs(request_log_events)
        except Exception:  # noqa: BLE001 — writer errors must not propagate
            logger.warning("obs.writer.request_log_batch.failed", exc_info=True)

    if api_error_log_events:
        try:
            from backend.observability.service.api_error_writer import persist_api_error_logs

            await persist_api_error_logs(api_error_log_events)
        except Exception:  # noqa: BLE001 — writer errors must not propagate
            logger.warning("obs.writer.api_error_log_batch.failed", exc_info=True)

    if auth_event_events:
        try:
            from backend.observability.service.auth_event_writer import persist_auth_events

            await persist_auth_events(auth_event_events)
        except Exception:  # noqa: BLE001 — writer errors must not propagate
            logger.warning("obs.writer.auth_event_batch.failed", exc_info=True)

    if oauth_event_events:
        try:
            from backend.observability.service.auth_event_writer import persist_oauth_events

            await persist_oauth_events(oauth_event_events)
        except Exception:  # noqa: BLE001 — writer errors must not propagate
            logger.warning("obs.writer.oauth_event_batch.failed", exc_info=True)

    if email_send_events:
        try:
            from backend.observability.service.auth_event_writer import persist_email_sends

            await persist_email_sends(email_send_events)
        except Exception:  # noqa: BLE001 — writer errors must not propagate
            logger.warning("obs.writer.email_send_batch.failed", exc_info=True)

    # DB + Cache layer writers (PR3)
    if slow_query_events:
        try:
            from backend.observability.service.db_cache_writer import persist_slow_queries

            await persist_slow_queries(slow_query_events)
        except Exception:  # noqa: BLE001 — writer errors must not propagate
            logger.warning("obs.writer.slow_query_batch.failed", exc_info=True)

    if db_pool_events:
        try:
            from backend.observability.service.db_cache_writer import persist_db_pool_events

            await persist_db_pool_events(db_pool_events)
        except Exception:  # noqa: BLE001 — writer errors must not propagate
            logger.warning("obs.writer.db_pool_event_batch.failed", exc_info=True)

    if schema_migration_events:
        try:
            from backend.observability.service.db_cache_writer import persist_schema_migrations

            await persist_schema_migrations(schema_migration_events)
        except Exception:  # noqa: BLE001 — writer errors must not propagate
            logger.warning("obs.writer.schema_migration_batch.failed", exc_info=True)

    if cache_operation_events:
        try:
            from backend.observability.service.db_cache_writer import persist_cache_operations

            await persist_cache_operations(cache_operation_events)
        except Exception:  # noqa: BLE001 — writer errors must not propagate
            logger.warning("obs.writer.cache_operation_batch.failed", exc_info=True)

    # Celery layer writers (PR4)
    if celery_heartbeat_events:
        try:
            from backend.observability.service.celery_writer import persist_celery_heartbeats

            await persist_celery_heartbeats(celery_heartbeat_events)
        except Exception:  # noqa: BLE001 — writer errors must not propagate
            logger.warning("obs.writer.celery_heartbeat_batch.failed", exc_info=True)

    if beat_schedule_run_events:
        try:
            from backend.observability.service.celery_writer import persist_beat_schedule_runs

            await persist_beat_schedule_runs(beat_schedule_run_events)
        except Exception:  # noqa: BLE001 — writer errors must not propagate
            logger.warning("obs.writer.beat_schedule_run_batch.failed", exc_info=True)

    if celery_queue_depth_events:
        try:
            from backend.observability.service.celery_writer import persist_celery_queue_depths

            await persist_celery_queue_depths(celery_queue_depth_events)
        except Exception:  # noqa: BLE001 — writer errors must not propagate
            logger.warning("obs.writer.celery_queue_depth_batch.failed", exc_info=True)
