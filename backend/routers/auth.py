"""Authentication endpoints: register, login, refresh, logout, OIDC SSO."""

import asyncio
import logging
import re
import uuid
from datetime import datetime, timezone
from urllib.parse import urlencode

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.database import get_async_session
from backend.dependencies import (
    COOKIE_ACCESS_TOKEN,
    COOKIE_PATH,
    COOKIE_REFRESH_TOKEN,
    COOKIE_SAMESITE,
    CachedUser,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    hash_password,
    require_admin,
    verify_password,
)
from backend.models.oauth_account import OAuthAccount
from backend.models.user import User, UserPreference
from backend.rate_limit import limiter
from backend.schemas.auth import (
    AccountInfoResponse,
    AdminRecoverAccountRequest,
    ChangePasswordRequest,
    DeleteAccountRequest,
    ForgotPasswordRequest,
    MessageResponse,
    ResetPasswordRequest,
    SetPasswordRequest,
    TokenRefreshRequest,
    TokenResponse,
    UserLoginRequest,
    UserProfileResponse,
    UserRegisterRequest,
    UserRegisterResponse,
    VerifyEmailRequest,
)
from backend.services.email import (
    generate_token,
    send_deletion_confirmation,
    send_password_reset_email,
    send_password_reset_google_only,
    send_verification_email,
)
from backend.services.google_oauth import build_auth_url, exchange_code
from backend.services.oidc_provider import (
    build_discovery_document,
    exchange_auth_code,
    store_auth_code,
)
from backend.services.redis_pool import get_redis
from backend.services.token_blocklist import add_to_blocklist, is_blocklisted, set_user_revocation

logger = logging.getLogger(__name__)

router = APIRouter()

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
    """Set httpOnly auth cookies on the response.

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


def _clear_auth_cookies(response: Response) -> None:
    """Clear httpOnly auth cookies from the response."""
    response.delete_cookie(key=COOKIE_ACCESS_TOKEN, path=COOKIE_PATH)
    response.delete_cookie(key=COOKIE_REFRESH_TOKEN, path=COOKIE_PATH)


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
    """Write login attempt to DB with its own session."""
    try:
        from datetime import datetime, timezone

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


@router.post(
    "/register",
    response_model=UserRegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("3/minute")
async def register(
    request: Request,
    body: UserRegisterRequest,
    db: AsyncSession = Depends(get_async_session),
) -> User:
    """Register a new user.

    Creates the user and their default preferences.
    """
    # Validate password strength
    if not PASSWORD_PATTERN.match(body.password):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password must be at least 8 characters with 1 uppercase and 1 digit",
        )

    # Check for duplicate email
    result = await db.execute(select(User).where(User.email == body.email))
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    # Create user
    user = User(
        email=body.email,
        hashed_password=hash_password(body.password),
    )
    db.add(user)
    await db.flush()

    # Create default preferences
    preference = UserPreference(user_id=user.id)
    db.add(preference)

    await db.commit()
    await db.refresh(user)

    # Send verification email (or auto-verify in dev mode)
    if settings.ENVIRONMENT == "development":
        user.email_verified = True
        user.email_verified_at = datetime.now(timezone.utc)
        await db.commit()
    else:
        token = generate_token()
        redis = await get_redis()
        if redis:
            await redis.set(f"email_verify:{token}", str(user.id), ex=86400)  # 24h TTL
            await redis.set(f"email_verify_current:{user.id}", token, ex=86400)
        asyncio.create_task(_send_verification_bg(user.email, token))

    return user


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
async def login(
    request: Request,
    body: UserLoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_async_session),
) -> TokenResponse:
    """Authenticate user and return JWT token pair.

    Sets httpOnly cookies with the tokens for browser-based auth,
    and also returns them in the JSON body for non-browser clients.
    """
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if user is None:
        _record_login_attempt_bg(
            email=body.email,
            success=False,
            user_id=None,
            ip_address=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("user-agent", "")[:500],
            failure_reason="invalid_credentials",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # Check for deleted account (before is_active check)
    if user.deleted_at is not None:
        _record_login_attempt_bg(
            email=body.email,
            success=False,
            user_id=user.id,
            ip_address=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("user-agent", "")[:500],
            failure_reason="account_deleted",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This account has been deleted. Contact support within 30 days to recover.",
        )

    if not user.is_active:
        _record_login_attempt_bg(
            email=body.email,
            success=False,
            user_id=user.id,
            ip_address=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("user-agent", "")[:500],
            failure_reason="account_disabled",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is disabled",
        )

    # Google-only user has no password
    if user.hashed_password is None:
        _record_login_attempt_bg(
            email=body.email,
            success=False,
            user_id=user.id,
            ip_address=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("user-agent", "")[:500],
            failure_reason="no_password_set",
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No password set. Use Google Sign-In or set a password in Account Settings.",
        )

    if not verify_password(body.password, user.hashed_password):
        _record_login_attempt_bg(
            email=body.email,
            success=False,
            user_id=user.id,
            ip_address=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("user-agent", "")[:500],
            failure_reason="invalid_credentials",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)

    _set_auth_cookies(response, access_token, refresh_token)

    _record_login_attempt_bg(
        email=body.email,
        success=True,
        user_id=user.id,
        ip_address=request.client.host if request.client else "unknown",
        user_agent=request.headers.get("user-agent", "")[:500],
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("5/minute")
async def refresh_token(
    request: Request,
    body: TokenRefreshRequest,
    response: Response,
    db: AsyncSession = Depends(get_async_session),
) -> TokenResponse:
    """Exchange a refresh token for a new token pair.

    Validates the old token, checks the blocklist, issues new tokens,
    and blocklists the old refresh token to prevent replay attacks.
    """
    token_payload = decode_token(body.refresh_token, expected_type="refresh")

    # Check if the refresh token has been revoked
    if token_payload.jti and await is_blocklisted(token_payload.jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
        )

    # Verify user still exists and is active
    result = await db.execute(select(User).where(User.id == token_payload.user_id))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    access_token = create_access_token(user.id)
    new_refresh_token = create_refresh_token(user.id)

    # Blocklist the old refresh token to prevent reuse
    if token_payload.jti:
        remaining_ttl = _get_token_remaining_ttl(body.refresh_token)
        await add_to_blocklist(token_payload.jti, expires_in_seconds=remaining_ttl)

    _set_auth_cookies(response, access_token, new_refresh_token)

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response) -> None:
    """Log out by clearing auth cookies and revoking the refresh token.

    This endpoint does not require authentication — clearing cookies
    is safe even if the user is already logged out.
    """
    # Try to blocklist the refresh token if present
    refresh_token_value = request.cookies.get(COOKIE_REFRESH_TOKEN)
    if refresh_token_value:
        try:
            token_payload = decode_token(refresh_token_value, expected_type="refresh")
            if token_payload.jti:
                remaining_ttl = _get_token_remaining_ttl(refresh_token_value)
                await add_to_blocklist(token_payload.jti, expires_in_seconds=remaining_ttl)
        except HTTPException:
            # Token already expired or invalid — nothing to blocklist
            pass

    _clear_auth_cookies(response)


@router.get("/me", response_model=UserProfileResponse)
async def get_me(
    user: User | CachedUser = Depends(get_current_user),
) -> UserProfileResponse:
    """Return the current authenticated user's profile.

    Returns:
        The user's id, email, role, and active status.
    """
    return UserProfileResponse(
        id=user.id,
        email=user.email,
        role=user.role.value,
        is_active=user.is_active,
    )


# ---------------------------------------------------------------------------
# Email verification endpoints
# ---------------------------------------------------------------------------


@router.get("/verify-email", response_class=HTMLResponse)
async def verify_email_page(token: str = "") -> HTMLResponse:
    """Render HTML page that auto-POSTs the verification token (bot protection)."""
    # Sanitize token — only allow URL-safe base64 chars (defense-in-depth)
    safe_token = re.sub(r"[^A-Za-z0-9_\-]", "", token)
    html = f"""<!DOCTYPE html>
<html><head><title>Verifying email...</title></head>
<body>
<p id="msg">Verifying your email...</p>
<script>
function setMessage(text) {{
    var el = document.getElementById('msg');
    if (el) el.textContent = text;
}}
fetch('/api/v1/auth/verify-email', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{token: '{safe_token}'}}),
    credentials: 'include'
}}).then(r => {{
    if (r.ok) window.location.href = '/login?verified=true';
    else setMessage('Invalid or expired link. Please request a new one.');
}}).catch(() => {{
    setMessage('Something went wrong. Please try again.');
}});
</script>
</body></html>"""
    return HTMLResponse(content=html)


@router.post("/verify-email", response_model=MessageResponse)
async def verify_email(
    body: VerifyEmailRequest,
    db: AsyncSession = Depends(get_async_session),
) -> MessageResponse:
    """Verify email address with token."""
    redis = await get_redis()
    if not redis:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    key = f"email_verify:{body.token}"
    user_id_str = await redis.get(key)
    if not user_id_str:
        raise HTTPException(status_code=400, detail="Invalid or expired verification token")

    # Decode user_id (might be bytes from Redis)
    if isinstance(user_id_str, bytes):
        user_id_str = user_id_str.decode()

    user_id = uuid.UUID(user_id_str)
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid verification token")

    # Delete token first (single-use, prevents race condition)
    await redis.delete(key)

    user.email_verified = True
    user.email_verified_at = datetime.now(timezone.utc)
    await db.commit()

    return MessageResponse(message="Email verified")


@router.post("/resend-verification", response_model=MessageResponse)
@limiter.limit("3/hour")
async def resend_verification(
    request: Request,
    user: User = Depends(get_current_user),
) -> MessageResponse:
    """Resend verification email. Rate limited to 3/hour."""
    if user.email_verified:
        return MessageResponse(message="Email already verified")

    token = generate_token()
    redis = await get_redis()
    if redis:
        # Invalidate previous token if tracked
        old_token = await redis.get(f"email_verify_current:{user.id}")
        if old_token:
            if isinstance(old_token, bytes):
                old_token = old_token.decode()
            await redis.delete(f"email_verify:{old_token}")

        # Store new token + track it per user
        await redis.set(f"email_verify:{token}", str(user.id), ex=86400)
        await redis.set(f"email_verify_current:{user.id}", token, ex=86400)

    asyncio.create_task(_send_verification_bg(user.email, token))
    return MessageResponse(message="Verification email sent")


# --- Password reset & account settings ---


@router.post("/forgot-password", response_model=MessageResponse)
@limiter.limit("3/hour")
async def forgot_password(
    request: Request,
    body: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_async_session),
) -> MessageResponse:
    """Request password reset. Always returns 200 (no email enumeration)."""
    # Per-email rate limit (3/hour) via Redis — supplements IP-based limiter
    redis = await get_redis()
    if redis:
        rate_key = f"forgot_pw_rate:{body.email}"
        count = await redis.incr(rate_key)
        if count == 1:
            await redis.expire(rate_key, 3600)
        if count > 3:
            return MessageResponse(message=_RESET_SENT_MSG)

    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if user:
        if user.hashed_password is None:
            # Google-only user
            asyncio.create_task(_send_reset_email_bg(user.email, "", google_only=True))
        else:
            token = generate_token()
            redis = await get_redis()
            if redis:
                await redis.set(f"password_reset:{token}", str(user.id), ex=3600)  # 1h TTL
            asyncio.create_task(_send_reset_email_bg(user.email, token))

    # Always return same response (no email enumeration)
    return MessageResponse(message=_RESET_SENT_MSG)


@router.post("/reset-password", response_model=MessageResponse)
@limiter.limit("5/hour")
async def reset_password(
    request: Request,
    body: ResetPasswordRequest,
    db: AsyncSession = Depends(get_async_session),
) -> MessageResponse:
    """Reset password with token. Revokes all sessions."""
    if not PASSWORD_PATTERN.match(body.new_password):
        raise HTTPException(status_code=422, detail=_PW_STRENGTH_MSG)

    redis = await get_redis()
    if not redis:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    key = f"password_reset:{body.token}"
    user_id_str = await redis.get(key)
    if not user_id_str:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    if isinstance(user_id_str, bytes):
        user_id_str = user_id_str.decode()

    user_id = uuid.UUID(user_id_str)
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid reset token")

    user.hashed_password = hash_password(body.new_password)
    await db.commit()

    # Delete token (single-use) and revoke all sessions
    await redis.delete(key)
    await set_user_revocation(user.id)

    return MessageResponse(message="Password reset. Please log in.")


@router.post("/change-password", response_model=MessageResponse)
@limiter.limit("5/hour")
async def change_password(
    request: Request,
    body: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> MessageResponse:
    """Change password (requires current password). Revokes other sessions."""
    if not PASSWORD_PATTERN.match(body.new_password):
        raise HTTPException(status_code=422, detail=_PW_STRENGTH_MSG)

    # Must have a password to change it
    if isinstance(user, CachedUser):
        if not user.has_password:
            raise HTTPException(status_code=400, detail=_NO_PW_MSG)
        result = await db.execute(select(User).where(User.id == user.id))
        db_user = result.scalar_one_or_none()
        if not db_user:
            raise HTTPException(status_code=401, detail="User not found")
    else:
        if user.hashed_password is None:
            raise HTTPException(status_code=400, detail=_NO_PW_MSG)
        db_user = user

    if not verify_password(body.current_password, db_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    db_user.hashed_password = hash_password(body.new_password)
    await db.commit()

    # Revoke all other sessions
    await set_user_revocation(user.id)

    return MessageResponse(message="Password changed")


@router.post("/set-password", response_model=MessageResponse)
@limiter.limit("5/hour")
async def set_password(
    request: Request,
    body: SetPasswordRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> MessageResponse:
    """Set password for Google-only users (no current password needed)."""
    if not PASSWORD_PATTERN.match(body.new_password):
        raise HTTPException(status_code=422, detail=_PW_STRENGTH_MSG)

    # Only allowed when no password is set
    if isinstance(user, CachedUser):
        if user.has_password:
            raise HTTPException(status_code=400, detail=_PW_ALREADY_SET_MSG)
        result = await db.execute(select(User).where(User.id == user.id))
        db_user = result.scalar_one_or_none()
        if not db_user:
            raise HTTPException(status_code=401, detail="User not found")
    else:
        if user.hashed_password is not None:
            raise HTTPException(status_code=400, detail=_PW_ALREADY_SET_MSG)
        db_user = user

    db_user.hashed_password = hash_password(body.new_password)
    await db.commit()

    return MessageResponse(message="Password set")


@router.get("/account", response_model=AccountInfoResponse)
async def get_account_info(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> AccountInfoResponse:
    """Return account info for settings page."""
    result = await db.execute(
        select(OAuthAccount).where(
            OAuthAccount.user_id == user.id,
            OAuthAccount.provider == "google",
        )
    )
    google_oauth = result.scalar_one_or_none()

    has_pw = user.has_password if isinstance(user, CachedUser) else user.hashed_password is not None

    return AccountInfoResponse(
        id=user.id,
        email=user.email,
        email_verified=user.email_verified,
        has_password=has_pw,
        google_linked=google_oauth is not None,
        google_email=google_oauth.provider_email if google_oauth else None,
        created_at=user.created_at,
    )


@router.post("/delete-account", response_model=MessageResponse)
@limiter.limit("3/hour")
async def delete_account(
    request: Request,
    body: DeleteAccountRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> MessageResponse:
    """Soft-delete account. Anonymize, deactivate, revoke tokens."""
    if body.confirmation != "DELETE":
        raise HTTPException(status_code=400, detail='Type "DELETE" to confirm')

    # Re-auth: password users must provide password
    if isinstance(user, CachedUser):
        result = await db.execute(select(User).where(User.id == user.id))
        db_user = result.scalar_one_or_none()
        if not db_user:
            raise HTTPException(status_code=401, detail="User not found")
        has_pw = user.has_password
    else:
        db_user = user
        has_pw = user.hashed_password is not None

    if has_pw:
        if not body.password:
            raise HTTPException(status_code=400, detail="Password required")
        if not verify_password(body.password, db_user.hashed_password):
            raise HTTPException(status_code=401, detail="Incorrect password")

    # Send deletion email BEFORE anonymizing
    original_email = db_user.email
    asyncio.create_task(_send_deletion_email_bg(original_email))

    # Anonymize and deactivate
    db_user.email = f"deleted_{uuid.uuid4()}@removed.local"
    db_user.hashed_password = None
    db_user.is_active = False
    db_user.deleted_at = datetime.now(timezone.utc)

    # Remove OAuth links
    result = await db.execute(select(OAuthAccount).where(OAuthAccount.user_id == db_user.id))
    for oauth in result.scalars().all():
        await db.delete(oauth)

    await db.commit()

    # Revoke all tokens
    await set_user_revocation(db_user.id)

    return MessageResponse(message="Account scheduled for deletion")


# ---------------------------------------------------------------------------
# Google OAuth endpoints
# ---------------------------------------------------------------------------


@router.get("/google/authorize")
@limiter.limit("10/minute")
async def google_authorize(
    request: Request,
    next: str = "/dashboard",
) -> RedirectResponse:
    """Redirect to Google OAuth consent screen.

    Args:
        request: The incoming request (required by rate limiter).
        next: URL to redirect to after successful authentication.

    Returns:
        A redirect to Google's OAuth consent screen.
    """
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=503, detail="Google OAuth not configured")

    # Validate redirect target (prevent open redirect)
    safe_next = next if next.startswith("/") and not next.startswith("//") else "/dashboard"
    auth_url, _ = await build_auth_url(next_url=safe_next)
    return RedirectResponse(url=auth_url, status_code=302)  # nosemgrep: no-open-redirect


@router.get("/google/callback")
@limiter.limit("10/minute")
async def google_callback(
    request: Request,
    code: str = "",
    state: str = "",
    db: AsyncSession = Depends(get_async_session),
) -> RedirectResponse:
    """Handle Google OAuth callback.

    Exchanges code for user info, creates/links account, sets cookies.

    Handles three flows:
    1. Returning user (sub already linked) — log in.
    2. Existing user by email (auto-link) — link + log in.
    3. New user — create account + log in.

    Args:
        request: The incoming request (required by rate limiter).
        code: Authorization code from Google.
        state: State token for CSRF protection.
        db: Async database session.

    Returns:
        A redirect to the post-login destination with auth cookies set.
    """
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state parameter")

    # Exchange code for user info
    try:
        google_user, next_url = await exchange_code(code, state)
    except ValueError:
        logger.exception("Google OAuth exchange failed")
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired session. Please try again.",
        )
    except Exception:
        logger.exception("Google OAuth API error")
        raise HTTPException(
            status_code=502,
            detail="Google Sign-In temporarily unavailable. Use email/password.",
        )

    if not google_user.email_verified:
        raise HTTPException(status_code=400, detail="Google account email not verified")

    # --- Flow 1: Check if Google sub already linked ---
    result = await db.execute(
        select(OAuthAccount).where(
            OAuthAccount.provider == "google",
            OAuthAccount.provider_sub == google_user.sub,
        )
    )
    existing_oauth = result.scalar_one_or_none()

    if existing_oauth:
        # Returning Google user — look up their account
        result = await db.execute(select(User).where(User.id == existing_oauth.user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=401, detail="Account not found")
        if user.deleted_at:
            raise HTTPException(
                status_code=401,
                detail="This account has been deleted. Contact support within 30 days to recover.",
            )
        if not user.is_active:
            raise HTTPException(status_code=401, detail="Account is disabled")
    else:
        # --- Flow 2: Check if email matches an existing user ---
        result = await db.execute(select(User).where(User.email == google_user.email))
        user = result.scalar_one_or_none()

        if user:
            # Auto-link Google to existing account
            if not user.is_active:
                raise HTTPException(status_code=401, detail="Account is disabled")
            if user.deleted_at:
                raise HTTPException(
                    status_code=401,
                    detail=(
                        "This account has been deleted. Contact support within 30 days to recover."
                    ),
                )

            # Check if user already has a different Google account linked
            result = await db.execute(
                select(OAuthAccount).where(
                    OAuthAccount.user_id == user.id,
                    OAuthAccount.provider == "google",
                )
            )
            if result.scalar_one_or_none():
                raise HTTPException(
                    status_code=409,
                    detail="A different Google account is already linked to this user.",
                )

            oauth_account = OAuthAccount(
                user_id=user.id,
                provider="google",
                provider_sub=google_user.sub,
                provider_email=google_user.email,
            )
            db.add(oauth_account)

            # Auto-verify email if not already verified
            if not user.email_verified:
                user.email_verified = True
                user.email_verified_at = datetime.now(timezone.utc)

            await db.commit()
        else:
            # --- Flow 3: New user — create account ---
            user = User(
                email=google_user.email,
                hashed_password=None,
                email_verified=True,
                email_verified_at=datetime.now(timezone.utc),
            )
            db.add(user)
            await db.flush()

            # Create default preferences
            preference = UserPreference(user_id=user.id)
            db.add(preference)

            oauth_account = OAuthAccount(
                user_id=user.id,
                provider="google",
                provider_sub=google_user.sub,
                provider_email=google_user.email,
            )
            db.add(oauth_account)
            await db.commit()
            await db.refresh(user)

    # Issue JWT tokens and set cookies
    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)

    redirect = RedirectResponse(url=next_url, status_code=302)  # nosemgrep: no-open-redirect
    _set_auth_cookies(redirect, access_token, refresh_token)

    # Record login attempt
    _record_login_attempt_bg(
        email=user.email,
        success=True,
        user_id=user.id,
        ip_address=request.client.host if request.client else "unknown",
        user_agent=request.headers.get("user-agent", "")[:500],
        method="google_oauth",
    )

    return redirect


@router.post("/google/unlink", response_model=MessageResponse)
async def google_unlink(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> MessageResponse:
    """Unlink Google account. Blocked if no password set (lockout prevention)."""
    result = await db.execute(
        select(OAuthAccount).where(
            OAuthAccount.user_id == user.id,
            OAuthAccount.provider == "google",
        )
    )
    oauth = result.scalar_one_or_none()
    if not oauth:
        raise HTTPException(status_code=400, detail="No Google account linked")

    # Check if user has a password (lockout prevention)
    has_pw = user.has_password if isinstance(user, CachedUser) else user.hashed_password is not None
    if not has_pw:
        raise HTTPException(status_code=400, detail="Set a password before unlinking Google")

    await db.delete(oauth)
    await db.commit()

    return MessageResponse(message="Google account unlinked")


# ---------------------------------------------------------------------------
# OIDC endpoints (Langfuse SSO integration)
# ---------------------------------------------------------------------------


@router.get("/.well-known/openid-configuration")
async def oidc_discovery(request: Request) -> JSONResponse:
    """Return the OpenID Connect discovery document.

    Langfuse uses this to discover authorization, token, and
    userinfo endpoint URLs.
    """
    base_url = str(request.base_url).rstrip("/")
    return JSONResponse(content=build_discovery_document(base_url))


def _oidc_enabled() -> bool:
    """Check if OIDC is configured (client secret is set)."""
    return bool(settings.OIDC_CLIENT_SECRET)


def _allowed_redirect_uris() -> set[str]:
    """Parse the comma-separated redirect URI whitelist from settings."""
    return {u.strip() for u in settings.OIDC_REDIRECT_URIS.split(",") if u.strip()}


@router.get("/authorize")
async def oidc_authorize(
    request: Request,
    response_type: str = "code",
    client_id: str = "",
    redirect_uri: str = "",
    state: str = "",
    user: User = Depends(get_current_user),
) -> RedirectResponse:
    """OIDC authorization endpoint.

    Validates the user's existing JWT (from cookie or header),
    generates a short-lived auth code stored in Redis, and
    redirects back to Langfuse with the code.

    Args:
        request: The incoming request.
        response_type: Must be "code".
        client_id: OIDC client ID (must match settings).
        redirect_uri: Where to redirect after authorization (must be whitelisted).
        state: Opaque state parameter passed through to the redirect.
        user: The authenticated user (injected by dependency).

    Returns:
        A redirect to the callback URI with the auth code.
    """
    if not _oidc_enabled():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OIDC is not configured",
        )

    if response_type != "code":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported response_type",
        )

    if client_id != settings.OIDC_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid client_id",
        )

    if not redirect_uri:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="redirect_uri is required",
        )

    if redirect_uri not in _allowed_redirect_uris():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="redirect_uri is not registered",
        )

    code = await store_auth_code(user.id)

    params = {"code": code}
    if state:
        params["state"] = state
    redirect_url = f"{redirect_uri}?{urlencode(params)}"

    # nosemgrep: no-open-redirect — redirect_url built from trusted FRONTEND_BASE_URL + params
    return RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)


@router.post("/token")
async def oidc_token(
    request: Request,
    db: AsyncSession = Depends(get_async_session),
) -> JSONResponse:
    """OIDC token exchange endpoint.

    Exchanges an authorization code for an access token (our existing JWT).
    Validates client credentials and the auth code from Redis.

    Returns:
        JSON with access_token, token_type, and expires_in.
    """
    if not _oidc_enabled():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OIDC is not configured",
        )

    form = await request.form()
    grant_type = form.get("grant_type", "")
    code = form.get("code", "")
    client_id = form.get("client_id", "")
    client_secret = form.get("client_secret", "")

    if grant_type != "authorization_code":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported grant_type",
        )

    if client_id != settings.OIDC_CLIENT_ID or client_secret != settings.OIDC_CLIENT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid client credentials",
        )

    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Authorization code is required",
        )

    user_id = await exchange_auth_code(str(code))
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired authorization code",
        )

    # Verify user still exists and is active
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    access_token = create_access_token(user.id)

    return JSONResponse(
        content={
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        }
    )


@router.get("/userinfo")
async def oidc_userinfo(
    user: User = Depends(get_current_user),
) -> JSONResponse:
    """OIDC userinfo endpoint.

    Returns user profile information. Protected by Bearer token
    (the JWT issued at the token endpoint).

    Args:
        user: The authenticated user (injected by dependency).

    Returns:
        JSON with sub, email, name, and auth_provider fields.
    """
    return JSONResponse(
        content={
            "sub": str(user.id),
            "email": user.email,
            "name": user.email.split("@")[0],
            "auth_provider": "local",
        }
    )


# --- Admin endpoints ---


@router.post("/admin/users/{user_id}/verify-email", response_model=MessageResponse)
async def admin_verify_email(
    user_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> MessageResponse:
    """Admin: manually verify a user's email."""
    require_admin(user)

    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    target.email_verified = True
    target.email_verified_at = datetime.now(timezone.utc)
    await db.commit()

    return MessageResponse(message="Email verified")


@router.post("/admin/users/{user_id}/recover", response_model=MessageResponse)
async def admin_recover_account(
    user_id: uuid.UUID,
    body: AdminRecoverAccountRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> MessageResponse:
    """Admin: recover a soft-deleted account within 30-day window."""
    require_admin(user)

    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    if not target.deleted_at:
        raise HTTPException(status_code=400, detail="Account is not deleted")

    # Check 30-day window
    days_since = (datetime.now(timezone.utc) - target.deleted_at).days
    if days_since > 30:
        raise HTTPException(status_code=400, detail="Recovery window expired (30 days)")

    # Check new email not taken
    existing = await db.execute(select(User).where(User.email == body.new_email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already in use")

    target.email = body.new_email
    target.is_active = True
    target.deleted_at = None
    target.email_verified = False
    target.email_verified_at = None
    await db.commit()

    return MessageResponse(message="Account recovered. User must verify new email.")
