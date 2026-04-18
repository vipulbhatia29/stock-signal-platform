"""Tests for auth observability instrumentation helpers.

Tests verify: correct event types are created, email is SHA256-hashed,
OBS_ENABLED=False is respected, missing obs_client is handled gracefully,
and the ContextVar recursion guard prevents re-entrant calls.
"""

from __future__ import annotations

import hashlib
import uuid
from unittest.mock import MagicMock, patch

from backend.observability.schema.auth_events import (
    AuthEventLogEvent,
    AuthEventType,
    AuthOutcome,
    EmailSendEvent,
    EmailType,
    OAuthAction,
    OAuthEventLogEvent,
)
from backend.observability.schema.v1 import EventType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_client():
    """Build a minimal mock ObservabilityClient."""
    client = MagicMock()
    client.emit_sync = MagicMock()
    return client


# ---------------------------------------------------------------------------
# emit_auth_event
# ---------------------------------------------------------------------------


class TestEmitAuthEvent:
    """Tests for emit_auth_event helper."""

    def test_emits_correct_event_type_when_obs_enabled(self):
        """Should call client.emit_sync with an AuthEventLogEvent when OBS_ENABLED=True."""
        from backend.observability.instrumentation.auth import emit_auth_event

        client = _make_client()
        with (
            patch("backend.observability.instrumentation.auth.settings") as mock_settings,
            patch(
                "backend.observability.instrumentation.auth._get_obs_client",
                return_value=client,
            ),
        ):
            mock_settings.OBS_ENABLED = True
            mock_settings.APP_ENV = "dev"
            mock_settings.GIT_SHA = None
            emit_auth_event(
                auth_event_type=AuthEventType.JWT_VERIFY_FAILURE,
                outcome=AuthOutcome.FAILURE,
                failure_reason="expired",
            )

        client.emit_sync.assert_called_once()
        event = client.emit_sync.call_args[0][0]
        assert isinstance(event, AuthEventLogEvent)
        assert event.event_type == EventType.AUTH_EVENT
        assert event.auth_event_type == AuthEventType.JWT_VERIFY_FAILURE
        assert event.outcome == AuthOutcome.FAILURE
        assert event.failure_reason == "expired"

    def test_no_emit_when_obs_disabled(self):
        """Should be a no-op when OBS_ENABLED=False."""
        from backend.observability.instrumentation.auth import emit_auth_event

        client = _make_client()
        with (
            patch("backend.observability.instrumentation.auth.settings") as mock_settings,
            patch(
                "backend.observability.instrumentation.auth._get_obs_client",
                return_value=client,
            ),
        ):
            mock_settings.OBS_ENABLED = False
            emit_auth_event(
                auth_event_type=AuthEventType.LOGOUT,
                outcome=AuthOutcome.SUCCESS,
            )

        client.emit_sync.assert_not_called()

    def test_no_emit_when_client_none(self):
        """Should silently skip when obs client is unavailable."""
        from backend.observability.instrumentation.auth import emit_auth_event

        with (
            patch("backend.observability.instrumentation.auth.settings") as mock_settings,
            patch(
                "backend.observability.instrumentation.auth._get_obs_client",
                return_value=None,
            ),
        ):
            mock_settings.OBS_ENABLED = True
            # Should not raise
            emit_auth_event(
                auth_event_type=AuthEventType.TOKEN_REFRESH,
                outcome=AuthOutcome.SUCCESS,
            )

    def test_recursion_guard_prevents_reentry(self):
        """Should not emit if _emitting_auth_event ContextVar is already True."""

        from backend.observability.instrumentation.auth import (
            _emitting_auth_event,
            emit_auth_event,
        )

        client = _make_client()
        _token = _emitting_auth_event.set(True)
        try:
            with (
                patch("backend.observability.instrumentation.auth.settings") as mock_settings,
                patch(
                    "backend.observability.instrumentation.auth._get_obs_client",
                    return_value=client,
                ),
            ):
                mock_settings.OBS_ENABLED = True
                emit_auth_event(
                    auth_event_type=AuthEventType.JWT_VERIFY_FAILURE,
                    outcome=AuthOutcome.FAILURE,
                )
        finally:
            _emitting_auth_event.reset(_token)

        client.emit_sync.assert_not_called()

    def test_emit_with_user_id(self):
        """Should pass user_id to event when provided."""
        from backend.observability.instrumentation.auth import emit_auth_event

        client = _make_client()
        uid = uuid.uuid4()
        with (
            patch("backend.observability.instrumentation.auth.settings") as mock_settings,
            patch(
                "backend.observability.instrumentation.auth._get_obs_client",
                return_value=client,
            ),
        ):
            mock_settings.OBS_ENABLED = True
            mock_settings.APP_ENV = "dev"
            mock_settings.GIT_SHA = None
            emit_auth_event(
                auth_event_type=AuthEventType.LOGOUT,
                outcome=AuthOutcome.SUCCESS,
                user_id=uid,
            )

        event = client.emit_sync.call_args[0][0]
        assert event.user_id == uid


# ---------------------------------------------------------------------------
# emit_oauth_event
# ---------------------------------------------------------------------------


class TestEmitOAuthEvent:
    """Tests for emit_oauth_event helper."""

    def test_emits_correct_event_type(self):
        """Should call client.emit_sync with an OAuthEventLogEvent."""
        from backend.observability.instrumentation.auth import emit_oauth_event

        client = _make_client()
        with (
            patch("backend.observability.instrumentation.auth.settings") as mock_settings,
            patch(
                "backend.observability.instrumentation.auth._get_obs_client",
                return_value=client,
            ),
        ):
            mock_settings.OBS_ENABLED = True
            mock_settings.APP_ENV = "dev"
            mock_settings.GIT_SHA = None
            emit_oauth_event(
                provider="google",
                action=OAuthAction.CODE_EXCHANGE,
                status="success",
            )

        client.emit_sync.assert_called_once()
        event = client.emit_sync.call_args[0][0]
        assert isinstance(event, OAuthEventLogEvent)
        assert event.event_type == EventType.OAUTH_EVENT
        assert event.provider == "google"
        assert event.action == OAuthAction.CODE_EXCHANGE

    def test_no_emit_when_obs_disabled(self):
        """Should be a no-op when OBS_ENABLED=False."""
        from backend.observability.instrumentation.auth import emit_oauth_event

        client = _make_client()
        with (
            patch("backend.observability.instrumentation.auth.settings") as mock_settings,
            patch(
                "backend.observability.instrumentation.auth._get_obs_client",
                return_value=client,
            ),
        ):
            mock_settings.OBS_ENABLED = False
            emit_oauth_event(
                provider="google",
                action=OAuthAction.AUTH_START,
                status="success",
            )

        client.emit_sync.assert_not_called()


# ---------------------------------------------------------------------------
# emit_email_send
# ---------------------------------------------------------------------------


class TestEmitEmailSend:
    """Tests for emit_email_send helper."""

    def test_hashes_email_before_emission(self):
        """Should SHA256-hash the email before putting it in the event."""
        from backend.observability.instrumentation.auth import emit_email_send

        client = _make_client()
        with (
            patch("backend.observability.instrumentation.auth.settings") as mock_settings,
            patch(
                "backend.observability.instrumentation.auth._get_obs_client",
                return_value=client,
            ),
        ):
            mock_settings.OBS_ENABLED = True
            mock_settings.APP_ENV = "dev"
            mock_settings.GIT_SHA = None
            emit_email_send(
                email="User@Example.COM",
                email_type=EmailType.VERIFICATION,
                status="sent",
            )

        client.emit_sync.assert_called_once()
        event = client.emit_sync.call_args[0][0]
        assert isinstance(event, EmailSendEvent)
        expected_hash = hashlib.sha256("user@example.com".encode()).hexdigest()
        assert event.recipient_hash == expected_hash
        assert len(event.recipient_hash) == 64

    def test_emits_correct_event_type(self):
        """Event type should be EMAIL_SEND."""
        from backend.observability.instrumentation.auth import emit_email_send

        client = _make_client()
        with (
            patch("backend.observability.instrumentation.auth.settings") as mock_settings,
            patch(
                "backend.observability.instrumentation.auth._get_obs_client",
                return_value=client,
            ),
        ):
            mock_settings.OBS_ENABLED = True
            mock_settings.APP_ENV = "dev"
            mock_settings.GIT_SHA = None
            emit_email_send(
                email="test@example.com",
                email_type=EmailType.PASSWORD_RESET,
                status="failed",
                error_reason="provider_down",
            )

        event = client.emit_sync.call_args[0][0]
        assert event.event_type == EventType.EMAIL_SEND
        assert event.status == "failed"
        assert event.error_reason == "provider_down"

    def test_no_emit_when_obs_disabled(self):
        """Should be a no-op when OBS_ENABLED=False."""
        from backend.observability.instrumentation.auth import emit_email_send

        client = _make_client()
        with (
            patch("backend.observability.instrumentation.auth.settings") as mock_settings,
            patch(
                "backend.observability.instrumentation.auth._get_obs_client",
                return_value=client,
            ),
        ):
            mock_settings.OBS_ENABLED = False
            emit_email_send(
                email="test@example.com",
                email_type=EmailType.VERIFICATION,
                status="sent",
            )

        client.emit_sync.assert_not_called()

    def test_no_emit_when_client_none(self):
        """Should silently skip when obs client is unavailable."""
        from backend.observability.instrumentation.auth import emit_email_send

        with (
            patch("backend.observability.instrumentation.auth.settings") as mock_settings,
            patch(
                "backend.observability.instrumentation.auth._get_obs_client",
                return_value=None,
            ),
        ):
            mock_settings.OBS_ENABLED = True
            # Should not raise
            emit_email_send(
                email="test@example.com",
                email_type=EmailType.DELETION_CONFIRMATION,
                status="sent",
            )

    def test_resend_message_id_passed_through(self):
        """Should pass resend_message_id to the event when provided."""
        from backend.observability.instrumentation.auth import emit_email_send

        client = _make_client()
        with (
            patch("backend.observability.instrumentation.auth.settings") as mock_settings,
            patch(
                "backend.observability.instrumentation.auth._get_obs_client",
                return_value=client,
            ),
        ):
            mock_settings.OBS_ENABLED = True
            mock_settings.APP_ENV = "dev"
            mock_settings.GIT_SHA = None
            emit_email_send(
                email="test@example.com",
                email_type=EmailType.VERIFICATION,
                status="sent",
                resend_message_id="msg_abc123",
            )

        event = client.emit_sync.call_args[0][0]
        assert event.resend_message_id == "msg_abc123"
