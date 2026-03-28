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


class FeedbackRequest(BaseModel):
    """Request body for PATCH /chat/sessions/{id}/messages/{id}/feedback."""

    feedback: Literal["up", "down"] = Field(..., description="Thumbs up or down")


class ChatMessageResponse(BaseModel):
    """Response schema for chat message history."""

    id: uuid.UUID
    role: str
    content: str | None
    tool_calls: list[dict] | None
    model_used: str | None
    tokens_used: int | None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    latency_ms: int | None = None
    feedback: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Admin chat schemas ──────────────────────────────────────────────────────


class AdminChatSessionSummary(BaseModel):
    """Admin view of a chat session with user email and message count."""

    id: uuid.UUID
    agent_type: str
    title: str | None
    is_active: bool
    decline_count: int
    user_email: str
    message_count: int
    created_at: datetime
    last_active_at: datetime

    model_config = {"from_attributes": True}


class AdminChatSessionListResponse(BaseModel):
    """Paginated list of chat sessions for admin."""

    total: int
    sessions: list[AdminChatSessionSummary]


class AdminChatTranscriptResponse(BaseModel):
    """Full transcript of a single chat session."""

    session: AdminChatSessionSummary
    messages: list[ChatMessageResponse]


class AdminChatStatsResponse(BaseModel):
    """Aggregate chat statistics."""

    total_sessions: int
    total_messages: int
    active_sessions: int
    feedback_up: int
    feedback_down: int
