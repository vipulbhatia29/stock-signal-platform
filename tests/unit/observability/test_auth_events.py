"""Tests for auth event schemas."""

import uuid
from datetime import datetime, timezone

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


def _base() -> dict:
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


class TestAuthEventLogEvent:
    def test_jwt_failure(self):
        e = AuthEventLogEvent(
            **_base(),
            auth_event_type=AuthEventType.JWT_VERIFY_FAILURE,
            outcome=AuthOutcome.FAILURE,
            failure_reason="expired",
        )
        assert e.event_type == EventType.AUTH_EVENT
        assert e.auth_event_type == AuthEventType.JWT_VERIFY_FAILURE

    def test_logout_success(self):
        base = {**_base(), "user_id": uuid.uuid4()}
        e = AuthEventLogEvent(
            **base,
            auth_event_type=AuthEventType.LOGOUT,
            outcome=AuthOutcome.SUCCESS,
        )
        assert e.outcome == AuthOutcome.SUCCESS

    def test_default_event_type_is_auth_event(self):
        e = AuthEventLogEvent(
            **_base(),
            auth_event_type=AuthEventType.TOKEN_REFRESH,
            outcome=AuthOutcome.SUCCESS,
        )
        assert e.event_type == EventType.AUTH_EVENT

    def test_optional_fields_default_to_none(self):
        e = AuthEventLogEvent(
            **_base(),
            auth_event_type=AuthEventType.LOGOUT,
            outcome=AuthOutcome.SUCCESS,
        )
        assert e.failure_reason is None
        assert e.ip_address is None
        assert e.user_agent is None


class TestOAuthEventLogEvent:
    def test_code_exchange_success(self):
        e = OAuthEventLogEvent(
            **_base(),
            provider="google",
            action=OAuthAction.CODE_EXCHANGE,
            status="success",
        )
        assert e.event_type == EventType.OAUTH_EVENT
        assert e.action == OAuthAction.CODE_EXCHANGE

    def test_with_error(self):
        e = OAuthEventLogEvent(
            **_base(),
            provider="google",
            action=OAuthAction.CODE_EXCHANGE,
            status="failure",
            error_reason="invalid_code",
        )
        assert e.error_reason == "invalid_code"

    def test_auth_start(self):
        e = OAuthEventLogEvent(
            **_base(),
            provider="google",
            action=OAuthAction.AUTH_START,
            status="success",
        )
        assert e.event_type == EventType.OAUTH_EVENT


class TestEmailSendEvent:
    def test_valid_send(self):
        e = EmailSendEvent(
            **_base(),
            recipient_hash="a" * 64,
            email_type=EmailType.VERIFICATION,
            status="sent",
        )
        assert e.event_type == EventType.EMAIL_SEND
        assert len(e.recipient_hash) == 64

    def test_failed_send(self):
        e = EmailSendEvent(
            **_base(),
            recipient_hash="b" * 64,
            email_type=EmailType.PASSWORD_RESET,
            status="failed",
            error_reason="provider_down",
        )
        assert e.status == "failed"

    def test_optional_resend_id(self):
        e = EmailSendEvent(
            **_base(),
            recipient_hash="c" * 64,
            email_type=EmailType.WELCOME,
            status="sent",
            resend_message_id="msg_abc123",
        )
        assert e.resend_message_id == "msg_abc123"
