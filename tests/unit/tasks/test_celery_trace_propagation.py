"""Tests for Celery trace_id propagation signal handlers."""
from __future__ import annotations

from unittest.mock import MagicMock
from uuid import UUID

from backend.observability.context import (
    current_parent_span_id,
    current_span_id,
    current_trace_id,
    span_id_var,
    trace_id_var,
)
from backend.tasks.celery_trace_propagation import (
    _adopt_trace_headers,
    _clear_trace,
    _inject_trace_headers,
)


class TestInjectTraceHeaders:
    """before_task_publish signal handler."""

    def test_injects_trace_id_from_contextvar(self):
        """Publisher with ambient trace_id writes it to headers dict."""
        trace = UUID("01234567-89ab-7def-8123-456789abcdef")
        trace_id_var.set(trace)
        try:
            headers: dict = {}
            _inject_trace_headers(sender="test.task", headers=headers)
            assert headers["obs_trace_id"] == str(trace)
        finally:
            trace_id_var.set(None)

    def test_injects_span_id_as_parent(self):
        """Publisher's current span_id becomes parent_span_id in headers."""
        trace = UUID("01234567-89ab-7def-8123-456789abcdef")
        span = UUID("01234567-89ab-7def-8123-000000000001")
        trace_id_var.set(trace)
        span_id_var.set(span)
        try:
            headers: dict = {}
            _inject_trace_headers(sender="test.task", headers=headers)
            assert headers["obs_parent_span_id"] == str(span)
        finally:
            trace_id_var.set(None)
            span_id_var.set(None)

    def test_skips_when_no_trace(self):
        """No ambient trace_id → no header injection."""
        trace_id_var.set(None)
        headers: dict = {}
        _inject_trace_headers(sender="test.task", headers=headers)
        assert "obs_trace_id" not in headers

    def test_skips_when_headers_none(self):
        """headers=None → no crash."""
        _inject_trace_headers(sender="test.task", headers=None)


class TestAdoptTraceHeaders:
    """task_prerun signal handler."""

    def test_adopts_incoming_trace_id(self):
        """Worker picks up trace_id from task headers."""
        task = MagicMock()
        task.request.headers = {
            "obs_trace_id": "01234567-89ab-7def-8123-456789abcdef",
        }
        _adopt_trace_headers(task_id="test-1", task=task)
        try:
            assert str(current_trace_id()) == "01234567-89ab-7def-8123-456789abcdef"
            # span_id is a new UUIDv7
            assert current_span_id() is not None
        finally:
            _clear_trace(task_id="test-1")

    def test_adopts_parent_span_id(self):
        """Worker picks up parent_span_id from task headers."""
        task = MagicMock()
        task.request.headers = {
            "obs_trace_id": "01234567-89ab-7def-8123-456789abcdef",
            "obs_parent_span_id": "01234567-89ab-7def-8123-000000000001",
        }
        _adopt_trace_headers(task_id="test-2", task=task)
        try:
            assert str(current_parent_span_id()) == "01234567-89ab-7def-8123-000000000001"
        finally:
            _clear_trace(task_id="test-2")

    def test_generates_new_trace_when_missing(self):
        """Beat-triggered task with no trace headers gets a new root trace_id."""
        task = MagicMock()
        task.request.headers = {}
        _adopt_trace_headers(task_id="test-3", task=task)
        try:
            tid = current_trace_id()
            assert tid is not None
            # UUIDv7 check: version nibble at position 6 (4 bits) = 7
            assert tid.version == 7 or str(tid)[14] == "7"
        finally:
            _clear_trace(task_id="test-3")

    def test_no_request_is_safe(self):
        """Task with no request attribute doesn't crash."""
        task = MagicMock(spec=[])  # no request attribute
        _adopt_trace_headers(task_id="test-4", task=task)


class TestClearTrace:
    """task_postrun signal handler."""

    def test_clears_contextvars_after_task(self):
        """ContextVars reset to None after task completes."""
        task = MagicMock()
        task.request.headers = {
            "obs_trace_id": "01234567-89ab-7def-8123-456789abcdef",
        }
        _adopt_trace_headers(task_id="test-5", task=task)
        assert current_trace_id() is not None
        _clear_trace(task_id="test-5")
        assert current_trace_id() is None
        assert current_span_id() is None
        assert current_parent_span_id() is None

    def test_clear_unknown_task_id_safe(self):
        """Clearing a task_id that was never adopted doesn't crash."""
        _clear_trace(task_id="unknown-task")
        assert current_trace_id() is None
