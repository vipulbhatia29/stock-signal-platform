"""Tests for the frontend error beacon endpoint and schemas.

Covers: schema validation, endpoint auth (optional user), rate limiting bypass,
CSRF exemption, batch size limits, and SDK emission.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from backend.observability.schema.frontend_deploy_events import (
    FrontendErrorEvent,
    FrontendErrorType,
)
from backend.observability.schema.v1 import EventType


def _base_fields() -> dict:
    """Return valid ObsEventBase fields."""
    return {
        "trace_id": uuid.uuid4(),
        "span_id": uuid.uuid4(),
        "parent_span_id": None,
        "ts": datetime.now(timezone.utc),
        "env": "dev",
        "git_sha": None,
        "user_id": None,
        "session_id": None,
        "query_id": None,
    }


class TestFrontendErrorEventSchema:
    """Schema-level validation for FrontendErrorEvent."""

    def test_valid_event(self):
        """FrontendErrorEvent should parse with required fields."""
        e = FrontendErrorEvent(
            **_base_fields(),
            event_type=EventType.FRONTEND_ERROR,
            error_type=FrontendErrorType.UNHANDLED_REJECTION,
            error_message="TypeError: Cannot read properties of null",
        )
        assert e.event_type == EventType.FRONTEND_ERROR
        assert e.error_type == FrontendErrorType.UNHANDLED_REJECTION
        assert e.error_message == "TypeError: Cannot read properties of null"

    def test_all_optional_fields(self):
        """FrontendErrorEvent should accept all optional fields."""
        e = FrontendErrorEvent(
            **_base_fields(),
            event_type=EventType.FRONTEND_ERROR,
            error_type=FrontendErrorType.REACT_ERROR_BOUNDARY,
            error_message="Component crashed",
            error_stack="at MyComponent (app.js:42)",
            page_route="/dashboard",
            component_name="MyComponent",
            user_agent="Mozilla/5.0",
            url="https://app.example.com/dashboard",
            frontend_metadata={"version": "1.2.3"},
        )
        assert e.page_route == "/dashboard"
        assert e.frontend_metadata == {"version": "1.2.3"}

    def test_error_message_max_length(self):
        """FrontendErrorEvent should reject error_message > 1024 chars."""
        with pytest.raises(ValidationError):
            FrontendErrorEvent(
                **_base_fields(),
                event_type=EventType.FRONTEND_ERROR,
                error_type=FrontendErrorType.NETWORK_ERROR,
                error_message="x" * 1025,
            )

    def test_error_stack_max_length(self):
        """FrontendErrorEvent should reject error_stack > 5120 chars."""
        with pytest.raises(ValidationError):
            FrontendErrorEvent(
                **_base_fields(),
                event_type=EventType.FRONTEND_ERROR,
                error_type=FrontendErrorType.QUERY_ERROR,
                error_stack="x" * 5121,
            )

    def test_all_error_types(self):
        """All FrontendErrorType enum values should be valid."""
        for error_type in FrontendErrorType:
            e = FrontendErrorEvent(
                **_base_fields(),
                event_type=EventType.FRONTEND_ERROR,
                error_type=error_type,
            )
            assert e.error_type == error_type

    def test_minimal_fields(self):
        """FrontendErrorEvent with only required fields should be valid."""
        e = FrontendErrorEvent(
            **_base_fields(),
            event_type=EventType.FRONTEND_ERROR,
            error_type=FrontendErrorType.MUTATION_ERROR,
        )
        assert e.error_message is None
        assert e.error_stack is None
        assert e.page_route is None


class TestFrontendErrorEndpoint:
    """Endpoint-level tests for POST /api/v1/observability/frontend-error."""

    def test_valid_payload_parses(self):
        """Valid error batch should parse via Pydantic model."""
        from backend.observability.routers.frontend_errors import (
            FrontendErrorItem,
            FrontendErrorPayload,
        )

        payload = FrontendErrorPayload(
            errors=[
                FrontendErrorItem(
                    error_type="unhandled_rejection",
                    error_message="test error",
                )
            ]
        )
        assert len(payload.errors) == 1
        assert payload.errors[0].error_type == "unhandled_rejection"

    def test_batch_max_10_items(self):
        """Payload should reject more than 10 errors."""
        from backend.observability.routers.frontend_errors import (
            FrontendErrorItem,
            FrontendErrorPayload,
        )

        items = [FrontendErrorItem(error_type="query_error") for _ in range(11)]
        with pytest.raises(ValidationError):
            FrontendErrorPayload(errors=items)

    def test_empty_batch_accepted(self):
        """Empty errors list should be accepted (endpoint handles gracefully)."""
        from backend.observability.routers.frontend_errors import FrontendErrorPayload

        payload = FrontendErrorPayload(errors=[])
        assert len(payload.errors) == 0

    def test_try_extract_user_id_no_cookie(self):
        """_try_extract_user_id should return None when no JWT cookie."""
        from backend.observability.routers.frontend_errors import _try_extract_user_id

        request = MagicMock()
        request.cookies = {}
        result = _try_extract_user_id(request)
        assert result is None

    def test_try_extract_user_id_invalid_token(self):
        """_try_extract_user_id should return None on invalid JWT."""
        from backend.observability.routers.frontend_errors import _try_extract_user_id

        request = MagicMock()
        request.cookies = {"access_token": "invalid-jwt"}
        result = _try_extract_user_id(request)
        assert result is None

    @pytest.mark.asyncio
    async def test_emit_via_sdk(self):
        """Endpoint should emit events via the observability SDK."""
        from backend.observability.routers.frontend_errors import (
            FrontendErrorItem,
            FrontendErrorPayload,
            report_frontend_errors,
        )

        mock_request = MagicMock()
        mock_request.cookies = {}
        mock_request.headers = {"User-Agent": "TestBrowser/1.0"}

        mock_obs_client = AsyncMock()

        payload = FrontendErrorPayload(
            errors=[
                FrontendErrorItem(
                    error_type="react_error_boundary",
                    error_message="Test error",
                    page_route="/dashboard",
                ),
                FrontendErrorItem(
                    error_type="query_error",
                    error_message="Network timeout",
                ),
            ]
        )

        # Access the underlying function, bypassing the limiter decorator
        inner_fn = report_frontend_errors.__wrapped__  # type: ignore[attr-defined]

        with patch(
            "backend.observability.bootstrap._maybe_get_obs_client",
            return_value=mock_obs_client,
        ):
            result = await inner_fn(mock_request, payload)

        assert result == {"accepted": 2}
        assert mock_obs_client.emit.await_count == 2

    @pytest.mark.asyncio
    async def test_emit_failure_still_returns_accepted(self):
        """SDK emit failure should not block the response."""
        from backend.observability.routers.frontend_errors import (
            FrontendErrorItem,
            FrontendErrorPayload,
            report_frontend_errors,
        )

        mock_request = MagicMock()
        mock_request.cookies = {}
        mock_request.headers = {}

        payload = FrontendErrorPayload(errors=[FrontendErrorItem(error_type="network_error")])

        inner_fn = report_frontend_errors.__wrapped__  # type: ignore[attr-defined]

        with patch(
            "backend.observability.bootstrap._maybe_get_obs_client",
            side_effect=RuntimeError("SDK unavailable"),
        ):
            result = await inner_fn(mock_request, payload)

        assert result == {"accepted": 1}


class TestFrontendErrorWriter:
    """Tests for the frontend error batch writer."""

    @pytest.mark.asyncio
    async def test_persist_frontend_errors_empty_list(self):
        """Writer should no-op on empty list."""
        from backend.observability.service.frontend_deploy_writer import (
            persist_frontend_errors,
        )

        await persist_frontend_errors([])  # should not raise

    @pytest.mark.asyncio
    async def test_persist_frontend_errors_batch(self):
        """Writer should persist events via async session."""
        from backend.observability.service.frontend_deploy_writer import (
            persist_frontend_errors,
        )

        events = [
            FrontendErrorEvent(
                **_base_fields(),
                event_type=EventType.FRONTEND_ERROR,
                error_type=FrontendErrorType.UNHANDLED_REJECTION,
                error_message="test",
            )
        ]

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "backend.observability.service.frontend_deploy_writer.async_session_factory",
            return_value=mock_session,
        ):
            await persist_frontend_errors(events)

        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()
