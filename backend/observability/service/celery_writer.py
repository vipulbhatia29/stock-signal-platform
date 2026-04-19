"""Batch writers for Celery layer observability events (1b PR4).

Three persist functions for heartbeats, beat schedule runs, and queue depth
snapshots. All writers set ``_in_obs_write`` ContextVar guard before commit.
"""

from __future__ import annotations

import logging

from backend.database import async_session_factory
from backend.observability.instrumentation.db import _in_obs_write
from backend.observability.models.beat_schedule_run import BeatScheduleRun
from backend.observability.models.celery_queue_depth import CeleryQueueDepth
from backend.observability.models.celery_worker_heartbeat import CeleryWorkerHeartbeat
from backend.observability.schema.celery_events import (
    BeatScheduleRunEvent,
    CeleryHeartbeatEvent,
    CeleryQueueDepthEvent,
)

logger = logging.getLogger(__name__)


async def persist_celery_heartbeats(events: list[CeleryHeartbeatEvent]) -> None:
    """Persist heartbeat events to observability.celery_worker_heartbeat.

    Args:
        events: List of CeleryHeartbeatEvent instances. No-op for empty list.
    """
    if not events:
        return

    async with async_session_factory() as session:
        for event in events:
            session.add(
                CeleryWorkerHeartbeat(
                    ts=event.ts,
                    trace_id=str(event.trace_id),
                    span_id=str(event.span_id),
                    worker_name=event.worker_name,
                    hostname=event.hostname,
                    status=event.status.value,
                    tasks_in_flight=event.tasks_in_flight,
                    queue_names=event.queue_names,
                    uptime_seconds=event.uptime_seconds,
                    env=event.env,
                    git_sha=event.git_sha,
                )
            )
        token = _in_obs_write.set(True)
        try:
            await session.commit()
        finally:
            _in_obs_write.reset(token)
    logger.debug("Persisted %d celery_worker_heartbeat rows", len(events))


async def persist_beat_schedule_runs(events: list[BeatScheduleRunEvent]) -> None:
    """Persist beat schedule run events to observability.beat_schedule_run.

    Args:
        events: List of BeatScheduleRunEvent instances. No-op for empty list.
    """
    if not events:
        return

    async with async_session_factory() as session:
        for event in events:
            session.add(
                BeatScheduleRun(
                    ts=event.ts,
                    trace_id=str(event.trace_id),
                    span_id=str(event.span_id),
                    task_name=event.task_name,
                    scheduled_time=event.scheduled_time,
                    actual_start_time=event.actual_start_time,
                    drift_seconds=event.drift_seconds,
                    outcome=event.outcome.value,
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
    logger.debug("Persisted %d beat_schedule_run rows", len(events))


async def persist_celery_queue_depths(events: list[CeleryQueueDepthEvent]) -> None:
    """Persist queue depth events to observability.celery_queue_depth.

    Args:
        events: List of CeleryQueueDepthEvent instances. No-op for empty list.
    """
    if not events:
        return

    async with async_session_factory() as session:
        for event in events:
            session.add(
                CeleryQueueDepth(
                    ts=event.ts,
                    trace_id=str(event.trace_id),
                    span_id=str(event.span_id),
                    queue_name=event.queue_name,
                    depth=event.depth,
                    env=event.env,
                    git_sha=event.git_sha,
                )
            )
        token = _in_obs_write.set(True)
        try:
            await session.commit()
        finally:
            _in_obs_write.reset(token)
    logger.debug("Persisted %d celery_queue_depth rows", len(events))
