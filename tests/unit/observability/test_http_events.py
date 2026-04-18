"""Tests for HTTP event schemas."""

import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from backend.observability.schema.http_events import (
    ApiErrorLogEvent,
    ErrorType,
    RequestLogEvent,
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


class TestRequestLogEvent:
    def test_valid_event(self):
        """RequestLogEvent should parse with required fields and default event_type."""
        e = RequestLogEvent(
            **_base_fields(),
            method="GET",
            path="/api/v1/stocks/{param}",
            raw_path="/api/v1/stocks/AAPL",
            status_code=200,
            latency_ms=42,
        )
        assert e.event_type == EventType.REQUEST_LOG
        assert e.method == "GET"
        assert e.latency_ms == 42

    def test_with_optional_fields(self):
        """RequestLogEvent should accept optional metadata fields."""
        base = _base_fields()
        base["user_id"] = uuid.uuid4()  # override None with real user_id
        e = RequestLogEvent(
            **base,
            method="POST",
            path="/api/v1/auth/login",
            raw_path="/api/v1/auth/login",
            status_code=200,
            latency_ms=150,
            request_bytes=512,
            response_bytes=1024,
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0",
            environment_snapshot={"flags": {"BACKTEST_ENABLED": True}},
        )
        assert e.request_bytes == 512
        assert e.environment_snapshot["flags"]["BACKTEST_ENABLED"] is True

    def test_rejects_negative_latency(self):
        """RequestLogEvent should reject negative latency_ms values."""
        with pytest.raises(ValidationError):
            RequestLogEvent(
                **_base_fields(),
                method="GET",
                path="/test",
                raw_path="/test",
                status_code=200,
                latency_ms=-1,
            )


class TestApiErrorLogEvent:
    def test_valid_error_event(self):
        """ApiErrorLogEvent should parse with required fields and default event_type."""
        e = ApiErrorLogEvent(
            **_base_fields(),
            status_code=500,
            error_type=ErrorType.INTERNAL_SERVER,
            error_message="Internal server error",
            exception_class="ValueError",
        )
        assert e.event_type == EventType.API_ERROR_LOG
        assert e.error_type == ErrorType.INTERNAL_SERVER

    def test_4xx_error(self):
        """ApiErrorLogEvent should accept 4xx status codes."""
        e = ApiErrorLogEvent(
            **_base_fields(),
            status_code=404,
            error_type=ErrorType.NOT_FOUND,
        )
        assert e.status_code == 404

    def test_5xx_with_stack(self):
        """ApiErrorLogEvent should store stack_trace and stack_hash for 5xx errors."""
        e = ApiErrorLogEvent(
            **_base_fields(),
            status_code=500,
            error_type=ErrorType.INTERNAL_SERVER,
            stack_trace="Traceback ...",
            stack_hash="a" * 64,
        )
        assert e.stack_trace == "Traceback ..."
