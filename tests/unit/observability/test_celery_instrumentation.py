"""Tests for Celery layer observability — schemas, heartbeat, queue depth."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from backend.observability.schema.celery_events import (
    BeatOutcome,
    BeatScheduleRunEvent,
    CeleryHeartbeatEvent,
    CeleryQueueDepthEvent,
    WorkerStatus,
)
from backend.observability.schema.v1 import EventType


def _base_fields() -> dict:
    """Return a valid base event payload."""
    return {
        "trace_id": uuid.uuid4(),
        "span_id": uuid.uuid4(),
        "parent_span_id": None,
        "ts": datetime.now(timezone.utc),
        "env": "dev",
        "git_sha": "abc123",
        "user_id": None,
        "session_id": None,
        "query_id": None,
    }


class TestCeleryHeartbeatEvent:
    """Tests for CeleryHeartbeatEvent schema."""

    def test_valid_event(self):
        """CeleryHeartbeatEvent should parse with required fields."""
        e = CeleryHeartbeatEvent(
            **_base_fields(),
            worker_name="celery@host1",
            hostname="host1",
            status=WorkerStatus.ALIVE,
            tasks_in_flight=3,
            queue_names=["celery"],
            uptime_seconds=120,
        )
        assert e.event_type == EventType.CELERY_HEARTBEAT
        assert e.worker_name == "celery@host1"
        assert e.tasks_in_flight == 3

    def test_shutdown_status(self):
        """CeleryHeartbeatEvent should accept shutdown status."""
        e = CeleryHeartbeatEvent(
            **_base_fields(),
            worker_name="celery@host2",
            hostname="host2",
            status=WorkerStatus.SHUTDOWN,
            tasks_in_flight=0,
            queue_names=["celery", "priority"],
            uptime_seconds=3600,
        )
        assert e.status == WorkerStatus.SHUTDOWN
        assert len(e.queue_names) == 2

    def test_all_statuses(self):
        """All WorkerStatus values should be valid."""
        for status in WorkerStatus:
            e = CeleryHeartbeatEvent(
                **_base_fields(),
                worker_name="w",
                hostname="h",
                status=status,
                tasks_in_flight=0,
                queue_names=[],
                uptime_seconds=0,
            )
            assert e.status == status


class TestBeatScheduleRunEvent:
    """Tests for BeatScheduleRunEvent schema."""

    def test_valid_dispatched_event(self):
        """BeatScheduleRunEvent should parse a dispatched task."""
        now = datetime.now(timezone.utc)
        e = BeatScheduleRunEvent(
            **_base_fields(),
            task_name="backend.tasks.market_data.nightly_pipeline_chain_task",
            scheduled_time=now,
            actual_start_time=now,
            drift_seconds=0.5,
            outcome=BeatOutcome.DISPATCHED,
        )
        assert e.event_type == EventType.BEAT_SCHEDULE_RUN
        assert e.drift_seconds == 0.5
        assert e.error_reason is None

    def test_error_with_reason(self):
        """BeatScheduleRunEvent should accept error_reason for error outcome."""
        now = datetime.now(timezone.utc)
        e = BeatScheduleRunEvent(
            **_base_fields(),
            task_name="backend.tasks.dq_scan.dq_scan_task",
            scheduled_time=now,
            actual_start_time=now,
            drift_seconds=120.0,
            outcome=BeatOutcome.ERROR,
            error_reason="worker_unavailable",
        )
        assert e.outcome == BeatOutcome.ERROR
        assert e.error_reason == "worker_unavailable"

    def test_all_outcomes(self):
        """All BeatOutcome values should be valid."""
        now = datetime.now(timezone.utc)
        for outcome in BeatOutcome:
            e = BeatScheduleRunEvent(
                **_base_fields(),
                task_name="task",
                scheduled_time=now,
                actual_start_time=now,
                drift_seconds=0,
                outcome=outcome,
            )
            assert e.outcome == outcome


class TestCeleryQueueDepthEvent:
    """Tests for CeleryQueueDepthEvent schema."""

    def test_valid_event(self):
        """CeleryQueueDepthEvent should parse with required fields."""
        e = CeleryQueueDepthEvent(
            **_base_fields(),
            queue_name="celery",
            depth=42,
        )
        assert e.event_type == EventType.CELERY_QUEUE_DEPTH
        assert e.queue_name == "celery"
        assert e.depth == 42

    def test_empty_queue(self):
        """CeleryQueueDepthEvent should accept depth=0."""
        e = CeleryQueueDepthEvent(
            **_base_fields(),
            queue_name="celery",
            depth=0,
        )
        assert e.depth == 0

    def test_missing_required(self):
        """CeleryQueueDepthEvent should reject missing queue_name."""
        with pytest.raises(ValidationError):
            CeleryQueueDepthEvent(
                **_base_fields(),
                depth=10,
            )


class TestHeartbeatMechanism:
    """Tests for the heartbeat start/stop mechanism."""

    def test_start_and_stop_heartbeat(self):
        """Heartbeat should start a daemon thread and stop cleanly."""
        from backend.observability.instrumentation.celery import (
            _heartbeat_stop_event,
            start_heartbeat,
            stop_heartbeat,
        )

        with patch("backend.observability.instrumentation.celery._emit_heartbeat") as mock_emit:
            start_heartbeat("test-worker")
            # Initial heartbeat should have been emitted
            mock_emit.assert_called_with("test-worker", "alive")

            stop_heartbeat("test-worker")
            assert _heartbeat_stop_event.is_set()
            # Shutdown heartbeat should have been emitted
            mock_emit.assert_called_with("test-worker", "shutdown")


class TestQueueDepthPolling:
    """Tests for queue depth polling."""

    @patch("backend.observability.bootstrap._maybe_get_obs_client", return_value=None)
    def test_noop_when_no_client(self, mock_client):
        """Should silently no-op when obs client is not available."""
        from backend.observability.instrumentation.celery import emit_queue_depth

        # Should not raise
        emit_queue_depth()

    @patch("backend.observability.bootstrap._maybe_get_obs_client")
    def test_emits_queue_depth(self, mock_get_client):
        """Should emit queue depth event with LLEN result."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_redis = MagicMock()
        mock_redis.llen.return_value = 5

        with patch("redis.from_url", return_value=mock_redis):
            from backend.observability.instrumentation.celery import emit_queue_depth

            emit_queue_depth()

        mock_client.emit_sync.assert_called_once()
        event = mock_client.emit_sync.call_args[0][0]
        assert event.queue_name == "celery"
        assert event.depth == 5
