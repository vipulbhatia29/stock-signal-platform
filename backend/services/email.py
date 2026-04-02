"""Email service using Resend API.

Dev mode (ENVIRONMENT=development): logs email content to console instead of sending.
"""

from __future__ import annotations

import logging
import secrets

from backend.config import settings

logger = logging.getLogger(__name__)


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
    await _send(to, subject, html)


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
    await _send(to, subject, html)


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
    await _send(to, subject, html)


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
    await _send(to, subject, html)


async def _send(to: str, subject: str, html: str) -> None:
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
    try:
        resend.Emails.send(
            {
                "from": settings.EMAIL_FROM_ADDRESS,
                "to": [to],
                "subject": subject,
                "html": html,
            }
        )
        logger.info("Email sent to %s: %s", to, subject)
    except Exception:
        logger.exception("Failed to send email to %s", to)
