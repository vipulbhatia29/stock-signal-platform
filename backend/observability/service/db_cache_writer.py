"""Batch writers for DB + Cache layer observability events (1b PR3).

Four persist functions for slow queries, pool events, schema migrations,
and cache operations. Each follows the 2-phase pattern: iterate events,
add model instances, commit once.

All writers set ``_in_obs_write`` ContextVar to ``True`` before
``session.commit()`` to prevent the ``after_execute`` slow query hook
from re-emitting events for the INSERT statements produced by these writers.
"""

from __future__ import annotations

import logging

from backend.database import async_session_factory
from backend.observability.instrumentation.db import _in_obs_write
from backend.observability.models.cache_operation_log import CacheOperationLog
from backend.observability.models.db_pool_event import DbPoolEvent as DbPoolEventModel
from backend.observability.models.schema_migration_log import SchemaMigrationLog
from backend.observability.models.slow_query_log import SlowQueryLog
from backend.observability.schema.db_cache_events import (
    CacheOperationEvent,
    DbPoolEvent,
    SchemaMigrationEvent,
    SlowQueryEvent,
)

logger = logging.getLogger(__name__)


async def persist_slow_queries(events: list[SlowQueryEvent]) -> None:
    """Persist slow query events to observability.slow_query_log.

    Args:
        events: List of SlowQueryEvent instances to persist. No-op for empty list.
    """
    if not events:
        return

    async with async_session_factory() as session:
        for event in events:
            session.add(
                SlowQueryLog(
                    ts=event.ts,
                    trace_id=str(event.trace_id),
                    span_id=str(event.span_id),
                    parent_span_id=(str(event.parent_span_id) if event.parent_span_id else None),
                    user_id=str(event.user_id) if event.user_id else None,
                    session_id=str(event.session_id) if event.session_id else None,
                    query_text=event.query_text,
                    query_hash=event.query_hash,
                    duration_ms=event.duration_ms,
                    rows_affected=event.rows_affected,
                    source_file=event.source_file,
                    source_line=event.source_line,
                    env=event.env,
                    git_sha=event.git_sha,
                )
            )
        token = _in_obs_write.set(True)
        try:
            await session.commit()
        finally:
            _in_obs_write.reset(token)
    logger.debug("Persisted %d slow_query_log rows", len(events))


async def persist_db_pool_events(events: list[DbPoolEvent]) -> None:
    """Persist DB pool events to observability.db_pool_event.

    Args:
        events: List of DbPoolEvent instances to persist. No-op for empty list.
    """
    if not events:
        return

    async with async_session_factory() as session:
        for event in events:
            session.add(
                DbPoolEventModel(
                    ts=event.ts,
                    trace_id=str(event.trace_id),
                    span_id=str(event.span_id),
                    user_id=str(event.user_id) if event.user_id else None,
                    session_id=str(event.session_id) if event.session_id else None,
                    pool_event_type=event.pool_event_type.value,
                    pool_size=event.pool_size,
                    checked_out=event.checked_out,
                    overflow=event.overflow,
                    duration_ms=event.duration_ms,
                    env=event.env,
                    git_sha=event.git_sha,
                )
            )
        token = _in_obs_write.set(True)
        try:
            await session.commit()
        finally:
            _in_obs_write.reset(token)
    logger.debug("Persisted %d db_pool_event rows", len(events))


async def persist_schema_migrations(events: list[SchemaMigrationEvent]) -> None:
    """Persist schema migration events to observability.schema_migration_log.

    Args:
        events: List of SchemaMigrationEvent instances to persist. No-op for empty list.
    """
    if not events:
        return

    async with async_session_factory() as session:
        for event in events:
            session.add(
                SchemaMigrationLog(
                    ts=event.ts,
                    trace_id=str(event.trace_id),
                    span_id=str(event.span_id),
                    migration_id=event.migration_id,
                    version=event.version,
                    status=event.status.value,
                    duration_ms=event.duration_ms,
                    error_message=event.error_message,
                    env=event.env,
                    git_sha=event.git_sha,
                )
            )
        token = _in_obs_write.set(True)
        try:
            await session.commit()
        finally:
            _in_obs_write.reset(token)
    logger.debug("Persisted %d schema_migration_log rows", len(events))


async def persist_cache_operations(events: list[CacheOperationEvent]) -> None:
    """Persist cache operation events to observability.cache_operation_log.

    Args:
        events: List of CacheOperationEvent instances to persist. No-op for empty list.
    """
    if not events:
        return

    async with async_session_factory() as session:
        for event in events:
            session.add(
                CacheOperationLog(
                    ts=event.ts,
                    trace_id=str(event.trace_id),
                    span_id=str(event.span_id),
                    user_id=str(event.user_id) if event.user_id else None,
                    session_id=str(event.session_id) if event.session_id else None,
                    operation=event.operation.value,
                    key_pattern=event.key_pattern,
                    hit=event.hit,
                    latency_ms=event.latency_ms,
                    value_bytes=event.value_bytes,
                    ttl_seconds=event.ttl_seconds,
                    error_reason=event.error_reason,
                    env=event.env,
                    git_sha=event.git_sha,
                )
            )
        token = _in_obs_write.set(True)
        try:
            await session.commit()
        finally:
            _in_obs_write.reset(token)
    logger.debug("Persisted %d cache_operation_log rows", len(events))
