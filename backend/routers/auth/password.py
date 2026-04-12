"""Password management and account settings endpoints."""

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_async_session
from backend.dependencies import (
    CachedUser,
    get_current_user,
    hash_password,
    verify_password,
)
from backend.models.oauth_account import OAuthAccount
from backend.models.user import User
from backend.rate_limit import limiter
from backend.routers.auth._helpers import (
    _NO_PW_MSG,
    _PW_ALREADY_SET_MSG,
    _PW_STRENGTH_MSG,
    _RESET_SENT_MSG,
    PASSWORD_PATTERN,
    _send_deletion_email_bg,
    _send_reset_email_bg,
)
from backend.schemas.auth import (
    AccountInfoResponse,
    ChangePasswordRequest,
    DeleteAccountRequest,
    ForgotPasswordRequest,
    MessageResponse,
    ResetPasswordRequest,
    SetPasswordRequest,
)
from backend.services.email import generate_token
from backend.services.redis_pool import get_redis
from backend.services.token_blocklist import set_user_revocation

logger = logging.getLogger(__name__)

router = APIRouter()


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
                await redis.set(  # nosemgrep: no-unbounded-redis-key
                    f"password_reset:{token}",
                    str(user.id),
                    ex=3600,
                )
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
