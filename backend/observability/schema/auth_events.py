"""Pydantic event schemas for auth layer observability.

Three event types:
- AuthEventLogEvent: JWT failures, token refresh, logout, session revocation.
- OAuthEventLogEvent: OAuth provider flow events (Google authorize/callback/unlink).
- EmailSendEvent: Email send attempt/outcome (with SHA256-hashed PII).
"""

from __future__ import annotations

from enum import Enum

from pydantic import Field

from backend.observability.schema.v1 import EventType, ObsEventBase


class AuthEventType(str, Enum):
    """Discriminator for auth event subtypes."""

    JWT_VERIFY_FAILURE = "jwt_verify_failure"
    TOKEN_REFRESH = "token_refresh"  # nosemgrep
    LOGOUT = "logout"
    EMAIL_VERIFY_ATTEMPT = "email_verify_attempt"
    PASSWORD_RESET_REQUEST = "password_reset_request"  # nosemgrep
    PASSWORD_RESET_COMPLETE = "password_reset_complete"  # nosemgrep
    SESSION_TERMINATED = "session_terminated"
    REVOCATION_APPLIED = "revocation_applied"


class AuthOutcome(str, Enum):
    """Binary outcome for auth events."""

    SUCCESS = "success"
    FAILURE = "failure"


class OAuthAction(str, Enum):
    """OAuth flow step discriminator."""

    AUTH_START = "auth_start"
    CODE_EXCHANGE = "code_exchange"
    TOKEN_REFRESH = "token_refresh"  # nosemgrep
    REVOKE = "revoke"
    LINK_EXISTING = "link_existing"
    CONFLICT_DETECTED = "conflict_detected"
    UNLINK = "unlink"


class EmailType(str, Enum):
    """Email category discriminator."""

    VERIFICATION = "verification"
    PASSWORD_RESET = "password_reset"  # nosemgrep
    DELETION_CONFIRMATION = "deletion_confirmation"
    WELCOME = "welcome"
    DIGEST = "digest"


class AuthEventLogEvent(ObsEventBase):
    """JWT, token refresh, logout, and session events.

    Attributes:
        event_type: Always EventType.AUTH_EVENT (frozen default).
        auth_event_type: Specific auth event subtype.
        outcome: SUCCESS or FAILURE.
        failure_reason: Structured reason string on failure (optional).
        ip_address: Client IP address (optional).
        user_agent: User-Agent header (optional).
        method: HTTP method of the triggering request (optional).
        path: Normalized path of the triggering request (optional).
        extra_data: Additional structured context (optional JSONB).
    """

    event_type: EventType = Field(default=EventType.AUTH_EVENT, frozen=True)

    auth_event_type: AuthEventType
    outcome: AuthOutcome
    failure_reason: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    method: str | None = None
    path: str | None = None
    extra_data: dict | None = None


class OAuthEventLogEvent(ObsEventBase):
    """OAuth provider flow events.

    Attributes:
        event_type: Always EventType.OAUTH_EVENT (frozen default).
        provider: Provider name (e.g. "google").
        action: OAuth flow step (e.g. CODE_EXCHANGE).
        status: "success" or "failure".
        error_reason: Structured reason on failure (optional).
        attempt_number: Retry count (optional).
        extra_data: Additional structured context (optional JSONB).
    """

    event_type: EventType = Field(default=EventType.OAUTH_EVENT, frozen=True)

    provider: str
    action: OAuthAction
    status: str  # success | failure
    error_reason: str | None = None
    attempt_number: int | None = None
    extra_data: dict | None = None


class EmailSendEvent(ObsEventBase):
    """Email send attempt/outcome events.

    Email address is SHA256-hashed for PII protection before storage.

    Attributes:
        event_type: Always EventType.EMAIL_SEND (frozen default).
        recipient_hash: SHA256 hex digest of lowercased email (64 chars).
        email_type: Category of email sent.
        status: "sent", "failed", or "bounced".
        error_reason: Provider error description on failure (optional).
        resend_message_id: Resend API message ID for tracking (optional).
    """

    event_type: EventType = Field(default=EventType.EMAIL_SEND, frozen=True)

    recipient_hash: str  # SHA256 of email (PII protection)
    email_type: EmailType
    status: str  # sent | failed | bounced
    error_reason: str | None = None
    resend_message_id: str | None = None
