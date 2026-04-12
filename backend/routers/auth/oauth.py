"""Google OAuth endpoints."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.database import get_async_session
from backend.dependencies import (
    CachedUser,
    create_access_token,
    create_refresh_token,
    get_current_user,
)
from backend.models.oauth_account import OAuthAccount
from backend.models.user import User, UserPreference
from backend.rate_limit import limiter
from backend.routers.auth._helpers import (
    _record_login_attempt_bg,
    _set_auth_cookies,
)
from backend.schemas.auth import MessageResponse
from backend.services.google_oauth import build_auth_url, exchange_code

logger = logging.getLogger(__name__)

router = APIRouter()


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
