"""Email service using Resend API.

Dev mode (ENVIRONMENT=development): logs email content to console instead of sending.
"""

from __future__ import annotations

import logging
import secrets
import time

from backend.config import settings
from backend.observability.instrumentation.auth import emit_email_send
from backend.observability.schema.auth_events import EmailType

logger = logging.getLogger(__name__)

_RESEND_ENDPOINT = "/emails"
_RESEND_METHOD = "POST"


def _emit_resend_event(
    latency_ms: int,
    error_reason: str | None,
) -> None:
    """Emit an EXTERNAL_API_CALL event for a Resend API call.

    Emission failures are silently swallowed — they must NEVER prevent emails from
    being sent or surfacing the real error to the caller.

    Args:
        latency_ms: Call duration in milliseconds.
        error_reason: ErrorReason.value string on failure, or None on success.
    """
    try:
        from datetime import datetime, timezone
        from uuid import UUID

        from uuid_utils import uuid7

        from backend.observability.bootstrap import _maybe_get_obs_client
        from backend.observability.context import current_span_id, current_trace_id
        from backend.observability.instrumentation.providers import ExternalProvider
        from backend.observability.schema.external_api_events import ExternalApiCallEvent
        from backend.observability.schema.v1 import EventType

        obs_client = _maybe_get_obs_client()
        if obs_client is None:
            return

        ambient_trace = current_trace_id()
        trace_id: UUID = ambient_trace if ambient_trace is not None else UUID(bytes=uuid7().bytes)
        span_id: UUID = UUID(bytes=uuid7().bytes)
        parent_span_id: UUID | None = current_span_id()

        env_mapping = {
            "development": "dev",
            "dev": "dev",
            "staging": "staging",
            "production": "prod",
            "prod": "prod",
        }
        env_str = env_mapping.get(settings.ENVIRONMENT.lower(), "dev")
        git_sha: str | None = getattr(settings, "GIT_SHA", None)

        event = ExternalApiCallEvent(
            event_type=EventType.EXTERNAL_API_CALL,
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            ts=datetime.now(timezone.utc),
            env=env_str,  # type: ignore[arg-type]
            git_sha=git_sha,
            user_id=None,
            session_id=None,
            query_id=None,
            provider=ExternalProvider.RESEND.value,
            endpoint=_RESEND_ENDPOINT,
            method=_RESEND_METHOD,
            status_code=None,
            error_reason=error_reason,
            latency_ms=latency_ms,
        )
        obs_client.emit_sync(event)
    except Exception:  # noqa: BLE001 — emission MUST NOT mask email errors
        logger.warning("obs.resend.emit_failed", exc_info=True)


def generate_token() -> str:
    """Generate a URL-safe token for email verification or password reset.

    Returns:
        A cryptographically secure 32-byte URL-safe token string.
    """
    return secrets.token_urlsafe(32)


async def send_verification_email(to: str, token: str) -> None:
    """Send email verification link.

    Args:
        to: Recipient email address.
        token: URL-safe verification token.
    """
    verify_url = f"{settings.FRONTEND_BASE_URL}/auth/verify-email?token={token}"
    subject = "Verify your email — Stock Signal Platform"
    html = f"""
    <h2>Verify your email address</h2>
    <p>Click the link below to verify your email:</p>
    <p><a href="{verify_url}"
       style="background:#1e3a5f;color:white;padding:12px 24px;
       text-decoration:none;border-radius:6px;display:inline-block;"
       >Verify Email</a></p>
    <p>Or copy this link: {verify_url}</p>
    <p>This link expires in 24 hours.</p>
    <p>— Stock Signal Platform</p>
    """
    await _send(to, subject, html, email_type=EmailType.VERIFICATION)


async def send_password_reset_email(to: str, token: str) -> None:
    """Send password reset link.

    Args:
        to: Recipient email address.
        token: URL-safe password reset token.
    """
    reset_url = f"{settings.FRONTEND_BASE_URL}/auth/reset-password?token={token}"
    subject = "Reset your password — Stock Signal Platform"
    html = f"""
    <h2>Reset your password</h2>
    <p>Click the link below to reset your password:</p>
    <p><a href="{reset_url}"
       style="background:#1e3a5f;color:white;padding:12px 24px;
       text-decoration:none;border-radius:6px;display:inline-block;"
       >Reset Password</a></p>
    <p>Or copy this link: {reset_url}</p>
    <p>This link expires in 1 hour. If you didn't request this, ignore this email.</p>
    <p>— Stock Signal Platform</p>
    """
    await _send(to, subject, html, email_type=EmailType.PASSWORD_RESET)


async def send_password_reset_google_only(to: str) -> None:
    """Send 'you use Google' message for forgot-password on Google-only accounts.

    Args:
        to: Recipient email address.
    """
    subject = "Password reset request — Stock Signal Platform"
    html = """
    <h2>You sign in with Google</h2>
    <p>Your account uses Google Sign-In and doesn't have a password set.</p>
    <p>To sign in, use the "Sign in with Google" button on the login page.</p>
    <p>If you'd like to set a password, sign in with Google first, then go to Account Settings.</p>
    <p>— Stock Signal Platform</p>
    """
    await _send(to, subject, html, email_type=EmailType.PASSWORD_RESET)


async def send_deletion_confirmation(to: str) -> None:
    """Send account deletion confirmation email.

    Args:
        to: Recipient email address.
    """
    subject = "Account deletion confirmed — Stock Signal Platform"
    html = """
    <h2>Your account has been scheduled for deletion</h2>
    <p>Your account has been deactivated and will be permanently deleted in 30 days.</p>
    <p>If you change your mind, contact support within 30 days to recover your account.</p>
    <p>— Stock Signal Platform</p>
    """
    await _send(to, subject, html, email_type=EmailType.DELETION_CONFIRMATION)


async def _send(to: str, subject: str, html: str, email_type: EmailType | None = None) -> None:
    """Send email via Resend API. In dev mode, log to console instead.

    Args:
        to: Recipient email address.
        subject: Email subject line.
        html: HTML body content.
    """
    if settings.ENVIRONMENT == "development" or not settings.RESEND_API_KEY:
        logger.info(
            "Email (dev mode — not sent):\n  To: %s\n  Subject: %s\n  Body: %s",
            to,
            subject,
            html[:200],
        )
        return

    import resend  # noqa: PLC0415 — lazy import to avoid errors if package missing

    resend.api_key = settings.RESEND_API_KEY
    _start = time.monotonic()
    _error_reason: str | None = None
    _resend_msg_id: str | None = None
    try:
        result = resend.Emails.send(
            {
                "from": settings.EMAIL_FROM_ADDRESS,
                "to": [to],
                "subject": subject,
                "html": html,
            }
        )
        _resend_msg_id = getattr(result, "id", None)
        logger.info("Email sent to %s: %s", to, subject)
    except Exception:
        from backend.observability.instrumentation.providers import ErrorReason

        _error_reason = ErrorReason.SERVER_ERROR_5XX.value
        logger.exception("Failed to send email to %s", to)
    finally:
        _latency_ms = int((time.monotonic() - _start) * 1000)
        _emit_resend_event(latency_ms=_latency_ms, error_reason=_error_reason)
        if email_type is not None:
            emit_email_send(
                email=to,
                email_type=email_type,
                status="failed" if _error_reason else "sent",
                error_reason=_error_reason,
                resend_message_id=_resend_msg_id,
            )
