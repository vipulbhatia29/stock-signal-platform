"""Pydantic event schemas for Celery layer observability (1b PR4).

Three event types:
- CeleryHeartbeatEvent — worker health status every 30s
- BeatScheduleRunEvent — beat task dispatch with drift detection
- CeleryQueueDepthEvent — queue backlog depth via Redis LLEN
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from backend.observability.schema.v1 import ObsEventBase


class WorkerStatus(str, Enum):
    """Status of a Celery worker."""

    ALIVE = "alive"
    DRAINING = "draining"
    SHUTDOWN = "shutdown"


class BeatOutcome(str, Enum):
    """Outcome of a beat schedule dispatch."""

    DISPATCHED = "dispatched"
    SKIPPED = "skipped"
    ERROR = "error"


class CeleryHeartbeatEvent(ObsEventBase):
    """Periodic heartbeat from a Celery worker (every 30s).

    Attributes:
        event_type: Always CELERY_HEARTBEAT.
        worker_name: Celery worker name (e.g. "celery@hostname").
        hostname: Machine hostname.
        status: Worker lifecycle status (alive, draining, shutdown).
        tasks_in_flight: Number of tasks currently executing.
        queue_names: List of queues this worker consumes from.
        uptime_seconds: Worker uptime in seconds since ready signal.
    """

    event_type: Literal["celery_heartbeat"] = "celery_heartbeat"  # type: ignore[assignment]
    worker_name: str
    hostname: str
    status: WorkerStatus
    tasks_in_flight: int
    queue_names: list[str]
    uptime_seconds: int


class BeatScheduleRunEvent(ObsEventBase):
    """Event emitted when a beat-scheduled task is dispatched.

    Attributes:
        event_type: Always BEAT_SCHEDULE_RUN.
        task_name: Fully qualified task name.
        scheduled_time: When the task was expected to run.
        actual_start_time: When the task was actually dispatched.
        drift_seconds: Difference between actual and scheduled (positive = late).
        outcome: Dispatch outcome (dispatched, skipped, error).
        error_reason: Error message if outcome is error.
    """

    event_type: Literal["beat_schedule_run"] = "beat_schedule_run"  # type: ignore[assignment]
    task_name: str
    scheduled_time: datetime
    actual_start_time: datetime
    drift_seconds: float
    outcome: BeatOutcome
    error_reason: str | None = None


class CeleryQueueDepthEvent(ObsEventBase):
    """Periodic snapshot of Celery queue depth via Redis LLEN.

    Attributes:
        event_type: Always CELERY_QUEUE_DEPTH.
        queue_name: Name of the Redis queue (e.g. "celery").
        depth: Number of pending tasks in the queue.
    """

    event_type: Literal["celery_queue_depth"] = "celery_queue_depth"  # type: ignore[assignment]
    queue_name: str
    depth: int
