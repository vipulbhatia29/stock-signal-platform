"""Unit tests for event_writer, external_api_writer, and rate_limiter_writer.

Covers:
- write_batch routing for EXTERNAL_API_CALL and RATE_LIMITER_EVENT
- write_batch DEBUG-logs and does not raise for unhandled event types
- persist_external_api_call creates the correct ExternalApiCallLog row
- persist_external_api_call swallows DB errors without re-raising
- persist_rate_limiter_event creates the correct RateLimiterEvent row
- persist_rate_limiter_event swallows DB errors without re-raising

No real database is used — async_session_factory is monkeypatched with an
async context manager mock that captures the added row.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from backend.observability.schema.external_api_events import ExternalApiCallEvent
from backend.observability.schema.rate_limiter_events import RateLimiterEventPayload
from backend.observability.schema.v1 import EventType, ObsEventBase

# ---------------------------------------------------------------------------
# Helpers — build minimal valid events
# ---------------------------------------------------------------------------


def _make_trace_id() -> UUID:
    """Return a deterministic UUID for test use."""
    return UUID("00000000-0000-0000-0000-000000000001")


def _make_span_id() -> UUID:
    """Return a deterministic UUID for test use."""
    return UUID("00000000-0000-0000-0000-000000000002")


def _make_ext_api_event(**overrides: Any) -> ExternalApiCallEvent:
    """Build a minimal valid ExternalApiCallEvent.

    Args:
        **overrides: Field overrides applied on top of sensible defaults.

    Returns:
        A ready-to-use ExternalApiCallEvent instance.
    """
    defaults: dict[str, Any] = dict(
        trace_id=_make_trace_id(),
        span_id=_make_span_id(),
        parent_span_id=None,
        ts=datetime.now(timezone.utc),
        env="dev",
        git_sha=None,
        user_id=None,
        session_id=None,
        query_id=None,
        provider="finnhub",
        endpoint="/api/v1/company-news",
        method="GET",
        status_code=200,
        error_reason=None,
        latency_ms=150,
    )
    defaults.update(overrides)
    return ExternalApiCallEvent(**defaults)


def _make_rate_limiter_event(**overrides: Any) -> RateLimiterEventPayload:
    """Build a minimal valid RateLimiterEventPayload.

    Args:
        **overrides: Field overrides applied on top of sensible defaults.

    Returns:
        A ready-to-use RateLimiterEventPayload instance.
    """
    defaults: dict[str, Any] = dict(
        trace_id=_make_trace_id(),
        span_id=_make_span_id(),
        parent_span_id=None,
        ts=datetime.now(timezone.utc),
        env="dev",
        git_sha=None,
        user_id=None,
        session_id=None,
        query_id=None,
        limiter_name="yfinance",
        action="fallback_permissive",
        wait_time_ms=None,
        tokens_remaining=None,
        reason_if_fallback="redis_down",
    )
    defaults.update(overrides)
    return RateLimiterEventPayload(**defaults)


def _make_session_mock() -> tuple[MagicMock, list[Any]]:
    """Build an async_session_factory mock that records rows passed to db.add().

    Returns:
        Tuple of (factory_mock, added_rows) where added_rows accumulates every
        object passed to db.add() across all sessions opened via the factory.
    """
    added_rows: list[Any] = []

    mock_db = MagicMock()
    mock_db.add = MagicMock(side_effect=lambda row: added_rows.append(row))
    mock_db.commit = AsyncMock()

    @asynccontextmanager
    async def _factory():
        yield mock_db

    factory_mock = MagicMock(side_effect=_factory)
    return factory_mock, added_rows


# ---------------------------------------------------------------------------
# write_batch routing tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_write_batch_routes_external_api_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """EXTERNAL_API_CALL events are forwarded to persist_external_api_call."""
    persisted: list[ObsEventBase] = []

    async def _fake_persist(event: ObsEventBase) -> None:
        persisted.append(event)

    monkeypatch.setattr(
        "backend.observability.service.external_api_writer.persist_external_api_call",
        _fake_persist,
    )

    from backend.observability.service import event_writer

    # Force re-import of the lazy import path by patching in the module namespace
    with patch(
        "backend.observability.service.event_writer." + "write_batch.__module__",
        create=True,
    ):
        pass  # patching not required — we patch the writer module directly

    event = _make_ext_api_event()

    # Patch the lazy import inside write_batch
    with patch(
        "backend.observability.service.external_api_writer.persist_external_api_call",
        side_effect=_fake_persist,
    ):
        await event_writer.write_batch([event])

    # The event was handed off (our side_effect captured it)
    assert len(persisted) == 1
    assert persisted[0] is event


@pytest.mark.asyncio
async def test_write_batch_routes_rate_limiter_event(monkeypatch: pytest.MonkeyPatch) -> None:
    """RATE_LIMITER_EVENT events are forwarded to persist_rate_limiter_event."""
    persisted: list[ObsEventBase] = []

    async def _fake_persist(event: ObsEventBase) -> None:
        persisted.append(event)

    from backend.observability.service import event_writer

    event = _make_rate_limiter_event()

    with patch(
        "backend.observability.service.rate_limiter_writer.persist_rate_limiter_event",
        side_effect=_fake_persist,
    ):
        await event_writer.write_batch([event])

    assert len(persisted) == 1
    assert persisted[0] is event


@pytest.mark.asyncio
async def test_write_batch_logs_unhandled_event_type(caplog: pytest.LogCaptureFixture) -> None:
    """Unhandled event types are logged at DEBUG level and do not raise."""
    import logging

    from backend.observability.service import event_writer

    # Build a bare ObsEventBase with an event_type that has no writer yet.
    # Use LLM_CALL — not yet handled in PR4.
    event = ObsEventBase(
        event_type=EventType.LLM_CALL,
        trace_id=_make_trace_id(),
        span_id=_make_span_id(),
        parent_span_id=None,
        ts=datetime.now(timezone.utc),
        env="dev",
        git_sha=None,
        user_id=None,
        session_id=None,
        query_id=None,
    )

    with caplog.at_level(logging.DEBUG, logger="backend.observability.service.event_writer"):
        await event_writer.write_batch([event])  # must not raise

    assert any("obs.event.unhandled" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_write_batch_empty_list_is_noop() -> None:
    """write_batch with an empty list completes without error."""
    from backend.observability.service import event_writer

    # Should not raise
    await event_writer.write_batch([])


# ---------------------------------------------------------------------------
# persist_external_api_call tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_persist_external_api_call_creates_row() -> None:
    """persist_external_api_call adds an ExternalApiCallLog row with correct fields."""
    from backend.observability.models.external_api_call import ExternalApiCallLog
    from backend.observability.service.external_api_writer import persist_external_api_call

    factory_mock, added_rows = _make_session_mock()

    with patch(
        "backend.observability.service.external_api_writer.async_session_factory",
        factory_mock,
    ):
        event = _make_ext_api_event(
            provider="openai",
            endpoint="/v1/chat/completions",
            method="POST",
            status_code=200,
            latency_ms=300,
            retry_count=1,
            request_bytes=512,
            response_bytes=1024,
        )
        await persist_external_api_call(event)

    assert len(added_rows) == 1
    row = added_rows[0]
    assert isinstance(row, ExternalApiCallLog)
    assert row.provider == "openai"
    assert row.endpoint == "/v1/chat/completions"
    assert row.method == "POST"
    assert row.status_code == 200
    assert row.latency_ms == 300
    assert row.retry_count == 1
    assert row.request_bytes == 512
    assert row.response_bytes == 1024
    assert row.trace_id == str(_make_trace_id())
    assert row.span_id == str(_make_span_id())
    assert row.parent_span_id is None
    assert row.user_id is None
    assert row.env == "dev"
    assert row.git_sha is None


@pytest.mark.asyncio
async def test_persist_external_api_call_maps_user_id() -> None:
    """persist_external_api_call converts UUID user_id to str for the model."""
    from backend.observability.models.external_api_call import ExternalApiCallLog
    from backend.observability.service.external_api_writer import persist_external_api_call

    user_uuid = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    factory_mock, added_rows = _make_session_mock()

    with patch(
        "backend.observability.service.external_api_writer.async_session_factory",
        factory_mock,
    ):
        event = _make_ext_api_event(user_id=user_uuid)
        await persist_external_api_call(event)

    assert len(added_rows) == 1
    row = added_rows[0]
    assert isinstance(row, ExternalApiCallLog)
    assert row.user_id == str(user_uuid)


@pytest.mark.asyncio
async def test_persist_external_api_call_swallows_db_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """DB commit errors are logged and not re-raised."""
    import logging

    from backend.observability.service.external_api_writer import persist_external_api_call

    mock_db = MagicMock()
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock(side_effect=RuntimeError("DB exploded"))

    @asynccontextmanager
    async def _broken_factory():
        yield mock_db

    factory_mock = MagicMock(side_effect=_broken_factory)
    event = _make_ext_api_event()

    with patch(
        "backend.observability.service.external_api_writer.async_session_factory",
        factory_mock,
    ):
        with caplog.at_level(
            logging.ERROR,
            logger="backend.observability.service.external_api_writer",
        ):
            await persist_external_api_call(event)  # must not raise

    assert any("obs.writer.external_api_call.failed" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# persist_rate_limiter_event tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_persist_rate_limiter_event_creates_row() -> None:
    """persist_rate_limiter_event adds a RateLimiterEvent row with correct fields."""
    from backend.observability.models.rate_limiter_event import (
        RateLimiterEvent as RateLimiterEventModel,
    )
    from backend.observability.service.rate_limiter_writer import persist_rate_limiter_event

    factory_mock, added_rows = _make_session_mock()

    with patch(
        "backend.observability.service.rate_limiter_writer.async_session_factory",
        factory_mock,
    ):
        event = _make_rate_limiter_event(
            limiter_name="openai_chat",
            action="timeout",
            wait_time_ms=250,
            tokens_remaining=None,
            reason_if_fallback=None,
        )
        await persist_rate_limiter_event(event)

    assert len(added_rows) == 1
    row = added_rows[0]
    assert isinstance(row, RateLimiterEventModel)
    assert row.limiter_name == "openai_chat"
    assert row.action == "timeout"
    assert row.wait_time_ms == 250
    assert row.tokens_remaining is None
    assert row.reason_if_fallback is None
    assert row.trace_id == str(_make_trace_id())
    assert row.span_id == str(_make_span_id())
    assert row.env == "dev"
    assert row.git_sha is None


@pytest.mark.asyncio
async def test_persist_rate_limiter_event_fallback_fields() -> None:
    """persist_rate_limiter_event persists reason_if_fallback when action is fallback_permissive."""
    from backend.observability.models.rate_limiter_event import (
        RateLimiterEvent as RateLimiterEventModel,
    )
    from backend.observability.service.rate_limiter_writer import persist_rate_limiter_event

    factory_mock, added_rows = _make_session_mock()

    with patch(
        "backend.observability.service.rate_limiter_writer.async_session_factory",
        factory_mock,
    ):
        event = _make_rate_limiter_event(
            action="fallback_permissive",
            reason_if_fallback="redis_down",
        )
        await persist_rate_limiter_event(event)

    assert len(added_rows) == 1
    row = added_rows[0]
    assert isinstance(row, RateLimiterEventModel)
    assert row.action == "fallback_permissive"
    assert row.reason_if_fallback == "redis_down"


@pytest.mark.asyncio
async def test_persist_rate_limiter_event_swallows_db_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """DB commit errors are logged and not re-raised."""
    import logging

    from backend.observability.service.rate_limiter_writer import persist_rate_limiter_event

    mock_db = MagicMock()
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock(side_effect=RuntimeError("rate limiter DB exploded"))

    @asynccontextmanager
    async def _broken_factory():
        yield mock_db

    factory_mock = MagicMock(side_effect=_broken_factory)
    event = _make_rate_limiter_event()

    with patch(
        "backend.observability.service.rate_limiter_writer.async_session_factory",
        factory_mock,
    ):
        with caplog.at_level(
            logging.ERROR, logger="backend.observability.service.rate_limiter_writer"
        ):
            await persist_rate_limiter_event(event)  # must not raise

    assert any("obs.writer.rate_limiter_event.failed" in r.message for r in caplog.records)
