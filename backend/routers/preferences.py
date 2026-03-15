"""User preferences API: get and update investment thresholds."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_async_session
from backend.dependencies import get_current_user
from backend.models.user import User, UserPreference
from backend.schemas.portfolio import UserPreferenceResponse, UserPreferenceUpdate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/preferences", tags=["preferences"])


async def _get_or_create_preference(
    user_id,
    db: AsyncSession,
) -> UserPreference:
    """Fetch the user's preferences, creating defaults if missing.

    Args:
        user_id: The authenticated user's UUID.
        db: Async SQLAlchemy session.

    Returns:
        The user's UserPreference row.
    """
    result = await db.execute(select(UserPreference).where(UserPreference.user_id == user_id))
    pref = result.scalar_one_or_none()
    if pref is None:
        pref = UserPreference(user_id=user_id)
        db.add(pref)
        await db.flush()
        logger.info("Created default preferences for user %s", user_id)
    return pref


@router.get(
    "",
    response_model=UserPreferenceResponse,
    summary="Get user investment preferences",
)
async def get_preferences(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> UserPreferenceResponse:
    """Return the user's investment threshold preferences.

    Creates a row with defaults on first access.
    """
    pref = await _get_or_create_preference(current_user.id, db)
    await db.commit()
    return UserPreferenceResponse.model_validate(pref)


@router.patch(
    "",
    response_model=UserPreferenceResponse,
    summary="Update user investment preferences",
)
async def update_preferences(
    body: UserPreferenceUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> UserPreferenceResponse:
    """Partially update investment threshold preferences.

    Only supplied fields are changed; omitted fields keep their current values.
    """
    pref = await _get_or_create_preference(current_user.id, db)

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(pref, field, value)

    await db.commit()
    await db.refresh(pref)
    logger.info("Updated preferences for user %s: %s", current_user.id, update_data)
    return UserPreferenceResponse.model_validate(pref)
