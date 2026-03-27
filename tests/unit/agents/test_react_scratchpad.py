"""Tests for ReAct loop scratchpad helper functions."""

from __future__ import annotations

import json

from backend.agents.llm_client import LLMResponse
from backend.agents.react_loop import (
    _append_assistant_message,
    _append_tool_messages,
    _build_initial_messages,
    _truncate_old_results,
)
from backend.tools.base import ToolResult


def test_build_initial_with_session_messages():
    """Prior conversation turns are prepended between system and current query."""
    session_messages = [
        {"role": "user", "content": "What is AAPL?"},
        {"role": "assistant", "content": "AAPL is Apple Inc."},
    ]

    messages = _build_initial_messages(
        query="Tell me more about it.",
        session_messages=session_messages,
        user_context={},
        entity_registry=None,
    )

    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == "What is AAPL?"
    assert messages[2]["role"] == "assistant"
    assert messages[2]["content"] == "AAPL is Apple Inc."
    assert messages[3]["role"] == "user"
    assert messages[3]["content"] == "Tell me more about it."
    assert len(messages) == 4


def test_build_initial_caps_at_10_turns():
    """Session messages are capped at the last 10 turns."""
    session_messages = [{"role": "user", "content": f"Message {i}"} for i in range(15)]

    messages = _build_initial_messages(
        query="Current query",
        session_messages=session_messages,
        user_context={},
        entity_registry=None,
    )

    # system + 10 turns + current query = 12
    assert len(messages) == 12
    # First session message should be #5 (index 5 of original 15)
    assert messages[1]["content"] == "Message 5"


def test_truncate_old_results():
    """Older tool results are compressed to 200 chars."""
    scratchpad = [
        {"role": "system", "content": "System prompt"},
        {"role": "tool", "tool_call_id": "c1", "content": "A" * 500},
        {"role": "tool", "tool_call_id": "c2", "content": "B" * 500},
        {"role": "tool", "tool_call_id": "c3", "content": "C" * 500},
        {"role": "tool", "tool_call_id": "c4", "content": "D" * 500},
    ]

    _truncate_old_results(scratchpad, keep_latest=2)

    # First two tool messages should be truncated
    assert len(scratchpad[1]["content"]) == 200 + len("... [truncated, already analyzed]")
    assert scratchpad[1]["content"].endswith("... [truncated, already analyzed]")
    assert len(scratchpad[2]["content"]) == 200 + len("... [truncated, already analyzed]")
    # Last two should be untouched
    assert scratchpad[3]["content"] == "C" * 500
    assert scratchpad[4]["content"] == "D" * 500


def test_truncate_keeps_latest_2():
    """When there are only 2 tool messages, nothing is truncated."""
    scratchpad = [
        {"role": "system", "content": "System prompt"},
        {"role": "tool", "tool_call_id": "c1", "content": "X" * 500},
        {"role": "tool", "tool_call_id": "c2", "content": "Y" * 500},
    ]

    _truncate_old_results(scratchpad, keep_latest=2)

    assert scratchpad[1]["content"] == "X" * 500
    assert scratchpad[2]["content"] == "Y" * 500


def test_append_assistant_with_tool_calls():
    """Assistant message has correct OpenAI format with function wrapper."""
    scratchpad: list[dict] = []
    response = LLMResponse(
        content="Let me check.",
        tool_calls=[
            {"id": "call_1", "name": "analyze_stock", "arguments": {"ticker": "AAPL"}},
            {"id": "call_2", "name": "compute_signals", "arguments": '{"ticker": "MSFT"}'},
        ],
        model="test",
        prompt_tokens=100,
        completion_tokens=50,
    )

    _append_assistant_message(scratchpad, response)

    assert len(scratchpad) == 1
    msg = scratchpad[0]
    assert msg["role"] == "assistant"
    assert msg["content"] == "Let me check."
    assert len(msg["tool_calls"]) == 2

    # First tool call: dict arguments → serialized to JSON string
    tc1 = msg["tool_calls"][0]
    assert tc1["id"] == "call_1"
    assert tc1["type"] == "function"
    assert tc1["function"]["name"] == "analyze_stock"
    assert json.loads(tc1["function"]["arguments"]) == {"ticker": "AAPL"}

    # Second tool call: string arguments → kept as-is
    tc2 = msg["tool_calls"][1]
    assert tc2["function"]["arguments"] == '{"ticker": "MSFT"}'


def test_append_tool_messages():
    """Tool messages have correct tool_call_id linking."""
    scratchpad: list[dict] = []
    tool_calls = [
        {"id": "call_1", "name": "analyze_stock", "arguments": {"ticker": "AAPL"}},
        {"id": "call_2", "name": "compute_signals", "arguments": {"ticker": "MSFT"}},
    ]
    results = [
        ToolResult(status="ok", data={"price": 150.0}),
        ToolResult(status="error", error="Not found"),
    ]

    _append_tool_messages(scratchpad, tool_calls, results)

    assert len(scratchpad) == 2

    # First: ok result with data
    assert scratchpad[0]["role"] == "tool"
    assert scratchpad[0]["tool_call_id"] == "call_1"
    assert json.loads(scratchpad[0]["content"]) == {"price": 150.0}

    # Second: error result
    assert scratchpad[1]["role"] == "tool"
    assert scratchpad[1]["tool_call_id"] == "call_2"
    assert scratchpad[1]["content"] == "Not found"
