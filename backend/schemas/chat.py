"""Chat request and response schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Request body for POST /api/v1/chat/stream."""

    message: str = Field(..., min_length=1, max_length=4000)
    session_id: uuid.UUID | None = None
    agent_type: Literal["stock", "general"] | None = Field(
        default=None,
        description="Required for new sessions. Ignored when resuming.",
    )


class ChatSessionResponse(BaseModel):
    """Response schema for chat session listing."""

    id: uuid.UUID
    agent_type: str
    title: str | None
    is_active: bool
    created_at: datetime
    last_active_at: datetime

    model_config = {"from_attributes": True}


class ChatMessageResponse(BaseModel):
    """Response schema for chat message history."""

    id: uuid.UUID
    role: str
    content: str | None
    tool_calls: dict | None
    model_used: str | None
    tokens_used: int | None
    created_at: datetime

    model_config = {"from_attributes": True}
