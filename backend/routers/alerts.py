"""Alerts API — paginated alerts, batch mark-read, unread count."""

import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_async_session
from backend.dependencies import get_current_user
from backend.models.alert import InAppAlert
from backend.models.user import User
from backend.schemas.alerts import (
    AlertListResponse,
    AlertResponse,
    BatchReadRequest,
    BatchReadResponse,
    UnreadCountResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get(
    "",
    response_model=AlertListResponse,
    summary="Get user alerts (paginated, unread first)",
)
async def get_alerts(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> AlertListResponse:
    """Get paginated alerts for the current user, unread first.

    Args:
        limit: Max alerts per page (1-100).
        offset: Pagination offset.
        db: Async database session.
        current_user: Authenticated user.

    Returns:
        AlertListResponse with alerts, total count, and unread count.
    """
    # Total count
    total_result = await db.execute(
        select(func.count()).where(InAppAlert.user_id == current_user.id)
    )
    total = total_result.scalar_one()

    # Unread count
    unread_result = await db.execute(
        select(func.count()).where(
            InAppAlert.user_id == current_user.id,
            InAppAlert.is_read.is_(False),
        )
    )
    unread_count = unread_result.scalar_one()

    # Alerts: unread first, then by created_at desc
    result = await db.execute(
        select(InAppAlert)
        .where(InAppAlert.user_id == current_user.id)
        .order_by(InAppAlert.is_read.asc(), InAppAlert.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    alerts = result.scalars().all()

    return AlertListResponse(
        alerts=[
            AlertResponse(
                id=a.id,
                alert_type=a.alert_type,
                severity=a.severity,
                title=a.title,
                ticker=a.ticker,
                message=a.message,
                metadata=a.metadata_,
                is_read=a.is_read,
                created_at=a.created_at,
            )
            for a in alerts
        ],
        total=total,
        unread_count=unread_count,
    )


@router.patch(
    "/read",
    response_model=BatchReadResponse,
    summary="Batch mark alerts as read",
)
async def mark_alerts_read(
    body: BatchReadRequest,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> BatchReadResponse:
    """Mark multiple alerts as read.

    Only updates alerts belonging to the current user (IDOR protection).

    Args:
        body: Request with list of alert IDs.
        db: Async database session.
        current_user: Authenticated user.

    Returns:
        BatchReadResponse with count of updated alerts.
    """
    if not body.alert_ids:
        return BatchReadResponse(updated=0)

    result = await db.execute(
        update(InAppAlert)
        .where(
            InAppAlert.id.in_(body.alert_ids),
            InAppAlert.user_id == current_user.id,
        )
        .values(is_read=True)
    )
    await db.commit()

    return BatchReadResponse(updated=result.rowcount)


@router.get(
    "/unread-count",
    response_model=UnreadCountResponse,
    summary="Get unread alert count for badge",
)
async def get_unread_count(
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> UnreadCountResponse:
    """Get the count of unread alerts (lightweight, for badge display).

    Args:
        db: Async database session.
        current_user: Authenticated user.

    Returns:
        UnreadCountResponse with count.
    """
    result = await db.execute(
        select(func.count()).where(
            InAppAlert.user_id == current_user.id,
            InAppAlert.is_read.is_(False),
        )
    )
    return UnreadCountResponse(unread_count=result.scalar_one())
