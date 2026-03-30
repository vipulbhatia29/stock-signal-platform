"""Pydantic v2 schemas for the alerts API."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class AlertResponse(BaseModel):
    """Single alert response."""

    id: uuid.UUID
    alert_type: str
    severity: Literal["critical", "warning", "info"]
    title: str
    ticker: str | None
    message: str
    metadata: dict | None = None
    is_read: bool
    created_at: datetime


class AlertListResponse(BaseModel):
    """Paginated list of alerts."""

    alerts: list[AlertResponse]
    total: int
    unread_count: int


class BatchReadRequest(BaseModel):
    """Request to mark alerts as read."""

    alert_ids: list[uuid.UUID]


class BatchReadResponse(BaseModel):
    """Response after marking alerts as read."""

    updated: int


class UnreadCountResponse(BaseModel):
    """Unread alert count for badge display."""

    unread_count: int
