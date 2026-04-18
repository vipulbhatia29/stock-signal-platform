"""Tests for request_log_writer and api_error_writer."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from backend.observability.schema.http_events import ApiErrorLogEvent, ErrorType, RequestLogEvent


@pytest.fixture
def sample_request_event() -> RequestLogEvent:
    """Build a sample RequestLogEvent for testing."""
    return RequestLogEvent(
        trace_id=uuid.uuid4(),
        span_id=uuid.uuid4(),
        parent_span_id=None,
        ts=datetime.now(timezone.utc),
        env="dev",
        git_sha="abc123",
        user_id=None,
        session_id=None,
        query_id=None,
        method="GET",
        path="/api/v1/stocks/{param}",
        raw_path="/api/v1/stocks/AAPL",
        status_code=200,
        latency_ms=42,
    )


@pytest.fixture
def sample_error_event() -> ApiErrorLogEvent:
    """Build a sample ApiErrorLogEvent for testing."""
    return ApiErrorLogEvent(
        trace_id=uuid.uuid4(),
        span_id=uuid.uuid4(),
        parent_span_id=None,
        ts=datetime.now(timezone.utc),
        env="dev",
        git_sha="abc123",
        user_id=None,
        session_id=None,
        query_id=None,
        status_code=500,
        error_type=ErrorType.INTERNAL_SERVER,
        error_message="An error occurred",
    )


@pytest.mark.asyncio
async def test_persist_request_logs_inserts_rows(sample_request_event: RequestLogEvent) -> None:
    """persist_request_logs should call session.add and commit for each event."""
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "backend.observability.service.request_log_writer.async_session_factory",
        return_value=mock_session,
    ):
        from backend.observability.service.request_log_writer import persist_request_logs

        await persist_request_logs([sample_request_event])

    mock_session.add.assert_called_once()
    mock_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_persist_request_logs_empty_list() -> None:
    """persist_request_logs should return immediately without DB call for empty list."""
    from backend.observability.service.request_log_writer import persist_request_logs

    # Should return immediately without DB call
    await persist_request_logs([])


@pytest.mark.asyncio
async def test_persist_api_error_logs_inserts_rows(sample_error_event: ApiErrorLogEvent) -> None:
    """persist_api_error_logs should call session.add and commit for each event."""
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "backend.observability.service.api_error_writer.async_session_factory",
        return_value=mock_session,
    ):
        from backend.observability.service.api_error_writer import persist_api_error_logs

        await persist_api_error_logs([sample_error_event])

    mock_session.add.assert_called_once()
    mock_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_persist_api_error_logs_empty_list() -> None:
    """persist_api_error_logs should return immediately without DB call for empty list."""
    from backend.observability.service.api_error_writer import persist_api_error_logs

    await persist_api_error_logs([])
