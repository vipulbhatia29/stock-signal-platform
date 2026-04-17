"""Tests for structured logging configuration."""

from __future__ import annotations

import io
import json
from uuid import UUID

import pytest
import structlog

from backend.core.logging import configure_structlog
from backend.observability.context import span_id_var, trace_id_var


@pytest.fixture(autouse=True)
def _reset_structlog():
    """Reset structlog config between tests to avoid cache_logger_on_first_use issues."""
    structlog.reset_defaults()
    yield
    structlog.reset_defaults()


@pytest.fixture
def log_capture(monkeypatch) -> io.StringIO:
    """Configure structlog to write to a capturable buffer."""
    buf = io.StringIO()
    configure_structlog(output=buf)
    return buf


def test_log_line_is_json_with_trace_id(log_capture):
    """Log lines include trace_id when ContextVar is set."""
    trace = UUID("01234567-89ab-7def-8123-456789abcdef")
    trace_id_var.set(trace)
    try:
        structlog.get_logger("test").info("hello", foo=1)
        line = log_capture.getvalue().strip().splitlines()[-1]
        payload = json.loads(line)
        assert payload["event"] == "hello"
        assert payload["foo"] == 1
        assert payload["trace_id"] == str(trace)
        assert "timestamp" in payload
        assert payload["level"] == "info"
    finally:
        trace_id_var.set(None)


def test_log_line_omits_trace_id_when_absent(log_capture):
    """trace_id key is omitted (not null) when ContextVar is None."""
    structlog.get_logger("test").info("no-trace")
    line = log_capture.getvalue().strip().splitlines()[-1]
    payload = json.loads(line)
    assert "trace_id" not in payload
    assert payload["event"] == "no-trace"


def test_span_id_included_when_set(log_capture):
    """span_id appears in log when ContextVar is set."""
    span = UUID("01234567-89ab-7def-8123-000000000001")
    span_id_var.set(span)
    try:
        structlog.get_logger("test").info("with-span")
        line = log_capture.getvalue().strip().splitlines()[-1]
        payload = json.loads(line)
        assert payload["span_id"] == str(span)
    finally:
        span_id_var.set(None)
