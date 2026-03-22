"""Tests for chat Pydantic schemas."""

import uuid

import pytest
from pydantic import ValidationError

from backend.schemas.chat import ChatMessageResponse, ChatRequest, ChatSessionResponse


def test_chat_request_new_session():
    """New session requires agent_type."""
    req = ChatRequest(message="Analyze AAPL", agent_type="stock")
    assert req.session_id is None
    assert req.agent_type == "stock"


def test_chat_request_resume_session():
    """Resume session ignores agent_type."""
    sid = uuid.uuid4()
    req = ChatRequest(message="Follow up", session_id=sid)
    assert req.session_id == sid


def test_chat_request_invalid_agent_type():
    """Invalid agent_type rejected."""
    with pytest.raises(ValidationError):
        ChatRequest(message="Hello", agent_type="invalid")


def test_chat_request_empty_message():
    """Empty message rejected."""
    with pytest.raises(ValidationError):
        ChatRequest(message="", agent_type="stock")


def test_chat_session_response_fields():
    """ChatSessionResponse serializes correctly."""
    resp = ChatSessionResponse(
        id=uuid.uuid4(),
        agent_type="stock",
        title="Analyze AAPL",
        is_active=True,
        created_at="2026-03-17T00:00:00Z",
        last_active_at="2026-03-17T00:00:00Z",
    )
    assert resp.agent_type == "stock"


def test_chat_message_response_fields():
    """ChatMessageResponse serializes correctly."""
    resp = ChatMessageResponse(
        id=uuid.uuid4(),
        role="assistant",
        content="AAPL looks strong...",
        tool_calls=None,
        model_used="llama-3.3-70b",
        tokens_used=150,
        created_at="2026-03-17T00:00:00Z",
    )
    assert resp.role == "assistant"
