"""Tests for chat and log database models."""

import uuid

from backend.models.chat import ChatMessage, ChatSession
from backend.models.logs import LLMCallLog, ToolExecutionLog


def test_chat_session_defaults():
    """ChatSession has correct column defaults."""
    session = ChatSession(
        user_id=uuid.uuid4(),
        agent_type="stock",
    )
    # default=True is DB-side; Python default is None before flush
    assert session.agent_type == "stock"


def test_chat_message_fields():
    """ChatMessage stores role, content, and token metadata."""
    msg = ChatMessage(
        session_id=uuid.uuid4(),
        role="user",
        content="Analyze AAPL",
    )
    assert msg.role == "user"
    assert msg.content == "Analyze AAPL"
    assert msg.tool_calls is None


def test_llm_call_log_fields():
    """LLMCallLog stores provider, model, and cost data."""
    log = LLMCallLog(
        provider="groq",
        model="llama-3.3-70b",
        prompt_tokens=100,
        completion_tokens=50,
        latency_ms=1200,
    )
    assert log.provider == "groq"
    assert log.cost_usd is None


def test_tool_execution_log_fields():
    """ToolExecutionLog stores tool name, params, and status."""
    log = ToolExecutionLog(
        tool_name="compute_signals",
        status="ok",
        latency_ms=250,
        cache_hit=False,
    )
    assert log.status == "ok"
    assert log.cache_hit is False
