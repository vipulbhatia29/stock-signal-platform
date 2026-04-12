"""Admin auth endpoints: email verification override, account recovery."""

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_async_session
from backend.dependencies import get_current_user, require_admin
from backend.models.user import User
from backend.schemas.auth import AdminRecoverAccountRequest, MessageResponse

logger = logging.getLogger(__name__)

router = APIRouter()


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
