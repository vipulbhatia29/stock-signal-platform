"""Celery observability instrumentation — heartbeat, queue depth, beat drift.

Heartbeat: background daemon thread emits CELERY_HEARTBEAT every 30s.
Queue depth: periodic Celery task polls Redis LLEN (O(1)).
Beat drift: not yet wired (requires celery-beat integration, deferred to 1c).

CRITICAL: Heartbeat thread MUST be daemon=True — otherwise worker shutdown hangs.
CRITICAL: Queue depth task must NOT be a @tracked_task (infinite recursion).
"""

from __future__ import annotations

import logging
import platform
import threading
import time
import uuid
from datetime import datetime, timezone

from backend.config import settings

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────
HEARTBEAT_INTERVAL_S = getattr(settings, "OBS_CELERY_HEARTBEAT_INTERVAL_S", 30)

# ── Worker state ──────────────────────────────────────────────────────────
_worker_start_time: float | None = None
_heartbeat_thread: threading.Thread | None = None
_heartbeat_stop_event = threading.Event()


def _emit_heartbeat(
    worker_name: str,
    status: str,
    tasks_in_flight: int = 0,
    queue_names: list[str] | None = None,
) -> None:
    """Emit a CELERY_HEARTBEAT event via the obs SDK (sync).

    Args:
        worker_name: Celery worker name.
        status: Worker status (alive, draining, shutdown).
        tasks_in_flight: Number of currently executing tasks.
        queue_names: List of queues consumed by this worker.
    """
    try:
        from backend.observability.bootstrap import _maybe_get_obs_client
        from backend.observability.schema.celery_events import (
            CeleryHeartbeatEvent,
            WorkerStatus,
        )

        client = _maybe_get_obs_client()
        if client is None:
            return

        uptime = int(time.monotonic() - _worker_start_time) if _worker_start_time else 0

        event = CeleryHeartbeatEvent(
            trace_id=uuid.uuid4(),
            span_id=uuid.uuid4(),
            parent_span_id=None,
            ts=datetime.now(timezone.utc),
            env=getattr(settings, "APP_ENV", "dev"),
            git_sha=getattr(settings, "GIT_SHA", None),
            user_id=None,
            session_id=None,
            query_id=None,
            worker_name=worker_name,
            hostname=platform.node(),
            status=WorkerStatus(status),
            tasks_in_flight=tasks_in_flight,
            queue_names=queue_names or ["celery"],
            uptime_seconds=uptime,
        )
        client.emit_sync(event)
    except Exception:  # noqa: BLE001 — heartbeat emission must not crash worker
        logger.debug("obs.celery_heartbeat.emit_failed", exc_info=True)


def _heartbeat_loop(worker_name: str) -> None:
    """Background loop emitting heartbeats every HEARTBEAT_INTERVAL_S seconds.

    Runs on a daemon thread — terminates automatically when worker exits.

    Args:
        worker_name: Celery worker name for identification.
    """
    while not _heartbeat_stop_event.is_set():
        _emit_heartbeat(worker_name, "alive")
        _heartbeat_stop_event.wait(timeout=HEARTBEAT_INTERVAL_S)


def start_heartbeat(worker_name: str) -> None:
    """Start the heartbeat background thread.

    Called from worker_ready signal handler. Emits initial heartbeat
    immediately, then starts periodic loop.

    Args:
        worker_name: Celery worker name.
    """
    global _worker_start_time, _heartbeat_thread  # noqa: PLW0603

    _worker_start_time = time.monotonic()
    _heartbeat_stop_event.clear()

    # Emit initial heartbeat
    _emit_heartbeat(worker_name, "alive")

    # Start background thread
    _heartbeat_thread = threading.Thread(
        target=_heartbeat_loop,
        args=(worker_name,),
        daemon=True,
        name="obs-celery-heartbeat",
    )
    _heartbeat_thread.start()
    logger.info(
        "obs.celery_heartbeat.started worker=%s interval=%ds",
        worker_name,
        HEARTBEAT_INTERVAL_S,
    )


def stop_heartbeat(worker_name: str) -> None:
    """Stop the heartbeat thread and emit shutdown heartbeat.

    Called from worker_shutting_down signal handler.

    Args:
        worker_name: Celery worker name.
    """
    global _heartbeat_thread  # noqa: PLW0603

    _heartbeat_stop_event.set()
    if _heartbeat_thread is not None:
        _heartbeat_thread.join(timeout=5.0)
        _heartbeat_thread = None

    # Emit final shutdown heartbeat
    _emit_heartbeat(worker_name, "shutdown")
    logger.info("obs.celery_heartbeat.stopped worker=%s", worker_name)


def emit_queue_depth() -> None:
    """Poll Redis queue depths and emit CELERY_QUEUE_DEPTH events.

    Uses Redis LLEN (O(1)) to check queue backlog. Called by a periodic
    Celery task (NOT @tracked_task to avoid recursion).
    """
    try:
        import redis as redis_lib

        from backend.observability.bootstrap import _maybe_get_obs_client
        from backend.observability.schema.celery_events import CeleryQueueDepthEvent

        client = _maybe_get_obs_client()
        if client is None:
            return

        r = redis_lib.from_url(settings.REDIS_URL)
        try:
            for queue_name in ["celery"]:
                try:
                    depth = r.llen(queue_name)
                except Exception:  # noqa: BLE001
                    depth = -1  # indicates poll failure

                event = CeleryQueueDepthEvent(
                    trace_id=uuid.uuid4(),
                    span_id=uuid.uuid4(),
                    parent_span_id=None,
                    ts=datetime.now(timezone.utc),
                    env=getattr(settings, "APP_ENV", "dev"),
                    git_sha=getattr(settings, "GIT_SHA", None),
                    user_id=None,
                    session_id=None,
                    query_id=None,
                    queue_name=queue_name,
                    depth=depth,  # type: ignore[arg-type]  # sync redis returns int
                )
                client.emit_sync(event)
        finally:
            r.close()
    except Exception:  # noqa: BLE001 — queue depth polling must not crash
        logger.debug("obs.celery_queue_depth.emit_failed", exc_info=True)
