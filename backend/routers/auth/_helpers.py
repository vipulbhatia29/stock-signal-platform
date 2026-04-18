"""Shared auth helpers — cookie management, token TTL, background tasks."""

import asyncio
import logging
import re
import secrets
import uuid
from datetime import datetime, timezone
from uuid import UUID

import jwt
from fastapi import Response
from uuid_utils import uuid7

from backend.config import settings
from backend.dependencies import (
    COOKIE_ACCESS_TOKEN,
    COOKIE_CSRF_TOKEN,
    COOKIE_PATH,
    COOKIE_REFRESH_TOKEN,
    COOKIE_SAMESITE,
)
from backend.observability.bootstrap import _maybe_get_obs_client
from backend.observability.context import current_span_id, current_trace_id
from backend.observability.schema.legacy_events import LoginAttemptEvent
from backend.services.email import (
    send_deletion_confirmation,
    send_password_reset_email,
    send_password_reset_google_only,
    send_verification_email,
)

logger = logging.getLogger(__name__)

PASSWORD_PATTERN = re.compile(r"^(?=.*[A-Z])(?=.*\d).{8,}$")

# Shared error messages (avoid line-length issues in endpoints)
_PW_STRENGTH_MSG = "Password must contain at least 1 uppercase letter and 1 digit"
_NO_PW_MSG = "No password set. Use set-password instead."
_PW_ALREADY_SET_MSG = "Password already set. Use change-password instead."
_RESET_SENT_MSG = "If an account with that email exists, a reset link has been sent"


def _get_token_remaining_ttl(token: str) -> int:
    """Get remaining TTL in seconds for a JWT token.

    Decodes without verification (already validated by decode_token).
    Returns 0 if the token is already expired.
    """
    import time

    payload = jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
        options={"verify_exp": False},
    )
    exp = payload.get("exp", 0)
    remaining = int(exp - time.time())
    return max(remaining, 0)


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    """Set httpOnly auth cookies + non-httpOnly CSRF cookie on the response.

    Args:
        response: FastAPI Response object.
        access_token: JWT access token.
        refresh_token: JWT refresh token.
    """
    response.set_cookie(
        key=COOKIE_ACCESS_TOKEN,
        value=access_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        path=COOKIE_PATH,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    response.set_cookie(
        key=COOKIE_REFRESH_TOKEN,
        value=refresh_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        path=COOKIE_PATH,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
    )
    response.set_cookie(
        key=COOKIE_CSRF_TOKEN,
        value=secrets.token_urlsafe(32),
        httponly=False,  # Frontend must read this via document.cookie
        secure=settings.COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        path=COOKIE_PATH,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


def _clear_auth_cookies(response: Response) -> None:
    """Clear auth cookies + CSRF cookie from the response."""
    response.delete_cookie(key=COOKIE_ACCESS_TOKEN, path=COOKIE_PATH)
    response.delete_cookie(key=COOKIE_REFRESH_TOKEN, path=COOKIE_PATH)
    response.delete_cookie(key=COOKIE_CSRF_TOKEN, path=COOKIE_PATH)


def _record_login_attempt_bg(
    email: str,
    success: bool,
    user_id: uuid.UUID | None,
    ip_address: str,
    user_agent: str,
    failure_reason: str | None = None,
    method: str = "password",
) -> None:
    """Schedule fire-and-forget login attempt recording.

    Uses its own DB session to avoid blocking the auth flow
    or double-committing on the caller's session.
    """
    asyncio.create_task(
        _write_login_attempt(
            email=email,
            success=success,
            user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            failure_reason=failure_reason,
            method=method,
        )
    )


async def _write_login_attempt(
    email: str,
    success: bool,
    user_id: uuid.UUID | None,
    ip_address: str,
    user_agent: str,
    failure_reason: str | None = None,
    method: str = "password",
) -> None:
    """Write login attempt to DB with its own session, and emit via SDK."""
    wrote_via_legacy = settings.OBS_LEGACY_DIRECT_WRITES  # snapshot NOW

    if wrote_via_legacy:
        try:
            from backend.database import async_session_factory
            from backend.models.login_attempt import LoginAttempt

            async with async_session_factory() as db:
                attempt = LoginAttempt(
                    timestamp=datetime.now(timezone.utc),
                    user_id=user_id,
                    email=email,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    success=success,
                    failure_reason=failure_reason,
                    method=method,
                )
                db.add(attempt)
                await db.commit()
        except Exception:
            logger.debug("Failed to record login attempt", exc_info=True)

    # SDK emission — always (no-op when OBS_ENABLED=false)
    obs_client = _maybe_get_obs_client()
    if obs_client is not None:
        try:
            event = LoginAttemptEvent(
                trace_id=current_trace_id() or UUID(bytes=uuid7().bytes),
                span_id=UUID(bytes=uuid7().bytes),
                parent_span_id=current_span_id(),
                ts=datetime.now(timezone.utc),
                env=getattr(settings, "APP_ENV", "dev"),
                git_sha=None,
                user_id=user_id,
                session_id=None,
                query_id=None,
                wrote_via_legacy=wrote_via_legacy,
                email=email,
                success=success,
                ip_address=ip_address,
                user_agent=user_agent,
                failure_reason=failure_reason,
                method=method,
            )
            await obs_client.emit(event)
        except Exception:
            logger.debug("Failed to emit login attempt via SDK", exc_info=True)


async def _send_verification_bg(email: str, token: str) -> None:
    """Fire-and-forget verification email."""
    try:
        await send_verification_email(email, token)
    except Exception:
        logger.exception("Failed to send verification email to %s", email)


async def _send_reset_email_bg(email: str, token: str, google_only: bool = False) -> None:
    """Fire-and-forget password reset email."""
    try:
        if google_only:
            await send_password_reset_google_only(email)
        else:
            await send_password_reset_email(email, token)
    except Exception:
        logger.exception("Failed to send reset notification email to %s", email)


async def _send_deletion_email_bg(email: str) -> None:
    """Fire-and-forget deletion confirmation email."""
    try:
        await send_deletion_confirmation(email)
    except Exception:
        logger.exception("Failed to send deletion email to %s", email)
