"""Auth observability emission helpers.

All functions are fire-and-forget — they catch and log exceptions internally,
never blocking the auth flow. Each helper is guarded by `settings.OBS_ENABLED`.

The JWT verification helper uses a ContextVar guard (`_emitting_auth_event`) to
prevent infinite recursion when obs endpoints themselves fail auth verification.
"""

from __future__ import annotations

import contextvars
import hashlib
import logging
import uuid
from datetime import datetime, timezone

from backend.config import settings
from backend.observability.context import span_id_var, trace_id_var
from backend.observability.schema.auth_events import (
    AuthEventLogEvent,
    AuthEventType,
    AuthOutcome,
    EmailSendEvent,
    EmailType,
    OAuthAction,
    OAuthEventLogEvent,
)

logger = logging.getLogger(__name__)

# Guard against recursion: set True before emitting, prevents re-entry if
# obs endpoints themselves fail JWT verification.
_emitting_auth_event: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "_emitting_auth_event", default=False
)


def _get_obs_client():
    """Get observability client without creating import cycles.

    Returns:
        The ObservabilityClient instance from app.state, or None if unavailable.
    """
    try:
        from backend.observability.bootstrap import _maybe_get_obs_client

        return _maybe_get_obs_client()
    except Exception:
        return None


def emit_auth_event(
    *,
    auth_event_type: AuthEventType,
    outcome: AuthOutcome,
    user_id: uuid.UUID | None = None,
    failure_reason: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    method: str | None = None,
    path: str | None = None,
    metadata: dict | None = None,
) -> None:
    """Emit an auth lifecycle event. Fire-and-forget. Guarded against recursion.

    Uses a ContextVar guard to prevent infinite loops when the observability
    endpoints themselves fail JWT verification.

    Args:
        auth_event_type: Specific auth event subtype (e.g. JWT_VERIFY_FAILURE).
        outcome: SUCCESS or FAILURE.
        user_id: Authenticated user who triggered the event, if known.
        failure_reason: Structured failure reason string on failure.
        ip_address: Client IP address.
        user_agent: User-Agent header.
        method: HTTP method of the triggering request.
        path: Normalized request path.
        metadata: Additional structured context.
    """
    if not settings.OBS_ENABLED or _emitting_auth_event.get():
        return
    token = _emitting_auth_event.set(True)
    try:
        client = _get_obs_client()
        if not client:
            return
        event = AuthEventLogEvent(
            trace_id=trace_id_var.get(None) or uuid.uuid4(),
            span_id=span_id_var.get(None) or uuid.uuid4(),
            parent_span_id=None,
            ts=datetime.now(timezone.utc),
            env=getattr(settings, "APP_ENV", "dev"),
            git_sha=getattr(settings, "GIT_SHA", None),
            user_id=user_id,
            session_id=None,
            query_id=None,
            auth_event_type=auth_event_type,
            outcome=outcome,
            failure_reason=failure_reason,
            ip_address=ip_address,
            user_agent=user_agent,
            method=method,
            path=path,
            metadata=metadata,
        )
        client.emit_sync(event)
    except Exception:
        logger.warning("obs.auth.emit_auth_event.failed", exc_info=True)
    finally:
        _emitting_auth_event.reset(token)


def emit_oauth_event(
    *,
    provider: str,
    action: OAuthAction,
    status: str,
    user_id: uuid.UUID | None = None,
    error_reason: str | None = None,
    metadata: dict | None = None,
) -> None:
    """Emit an OAuth provider flow event. Fire-and-forget.

    Args:
        provider: OAuth provider name (e.g. "google").
        action: OAuth flow step (e.g. CODE_EXCHANGE).
        status: "success" or "failure".
        user_id: User who triggered the event, if known.
        error_reason: Structured error description on failure.
        metadata: Additional structured context.
    """
    if not settings.OBS_ENABLED:
        return
    try:
        client = _get_obs_client()
        if not client:
            return
        event = OAuthEventLogEvent(
            trace_id=trace_id_var.get(None) or uuid.uuid4(),
            span_id=span_id_var.get(None) or uuid.uuid4(),
            parent_span_id=None,
            ts=datetime.now(timezone.utc),
            env=getattr(settings, "APP_ENV", "dev"),
            git_sha=getattr(settings, "GIT_SHA", None),
            user_id=user_id,
            session_id=None,
            query_id=None,
            provider=provider,
            action=action,
            status=status,
            error_reason=error_reason,
            metadata=metadata,
        )
        client.emit_sync(event)
    except Exception:
        logger.warning("obs.auth.emit_oauth_event.failed", exc_info=True)


def emit_email_send(
    *,
    email: str,
    email_type: EmailType,
    status: str,
    user_id: uuid.UUID | None = None,
    error_reason: str | None = None,
    resend_message_id: str | None = None,
) -> None:
    """Emit an email send event. Fire-and-forget. Hashes email for PII protection.

    The email address is SHA256-hashed before construction of the event so that
    no PII is ever passed to the observability SDK or stored in the DB.

    Args:
        email: Recipient email address (will be SHA256-hashed, never stored raw).
        email_type: Category of email sent.
        status: "sent", "failed", or "bounced".
        user_id: User who triggered the send, if known.
        error_reason: Provider error description on failure.
        resend_message_id: Resend API message ID for tracking.
    """
    if not settings.OBS_ENABLED:
        return
    try:
        client = _get_obs_client()
        if not client:
            return
        recipient_hash = hashlib.sha256(email.lower().encode()).hexdigest()
        event = EmailSendEvent(
            trace_id=trace_id_var.get(None) or uuid.uuid4(),
            span_id=span_id_var.get(None) or uuid.uuid4(),
            parent_span_id=None,
            ts=datetime.now(timezone.utc),
            env=getattr(settings, "APP_ENV", "dev"),
            git_sha=getattr(settings, "GIT_SHA", None),
            user_id=user_id,
            session_id=None,
            query_id=None,
            recipient_hash=recipient_hash,
            email_type=email_type,
            status=status,
            error_reason=error_reason,
            resend_message_id=resend_message_id,
        )
        client.emit_sync(event)
    except Exception:
        logger.warning("obs.auth.emit_email_send.failed", exc_info=True)
