"""Tests for Anthropic multi-turn message normalization."""

from __future__ import annotations

import json

from backend.agents.providers.anthropic import _normalize_messages_for_anthropic


def test_normalize_assistant_with_tool_calls() -> None:
    """OpenAI-format assistant message with tool_calls converts to Anthropic content blocks."""
    messages = [
        {
            "role": "assistant",
            "content": "Let me look that up.",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "get_stock_price",
                        "arguments": json.dumps({"ticker": "AAPL"}),
                    },
                }
            ],
        }
    ]

    result = _normalize_messages_for_anthropic(messages)

    assert len(result) == 1
    msg = result[0]
    assert msg["role"] == "assistant"
    assert isinstance(msg["content"], list)

    # First block should be the text content
    text_block = msg["content"][0]
    assert text_block["type"] == "text"
    assert text_block["text"] == "Let me look that up."

    # Second block should be the tool_use block
    tool_block = msg["content"][1]
    assert tool_block["type"] == "tool_use"
    assert tool_block["id"] == "call_1"
    assert tool_block["name"] == "get_stock_price"
    assert tool_block["input"] == {"ticker": "AAPL"}


def test_normalize_assistant_with_tool_calls_no_text_content() -> None:
    """Assistant message with tool_calls and no text produces only tool_use blocks."""
    messages = [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_2",
                    "type": "function",
                    "function": {
                        "name": "search_stocks",
                        "arguments": {"query": "tech"},
                    },
                }
            ],
        }
    ]

    result = _normalize_messages_for_anthropic(messages)

    assert len(result) == 1
    msg = result[0]
    assert msg["role"] == "assistant"
    content = msg["content"]
    assert len(content) == 1
    assert content[0]["type"] == "tool_use"
    assert content[0]["input"] == {"query": "tech"}


def test_normalize_tool_result_message() -> None:
    """role:tool message converts to role:user with tool_result content block."""
    messages = [
        {
            "role": "tool",
            "tool_call_id": "call_1",
            "content": '{"price": 182.50}',
        }
    ]

    result = _normalize_messages_for_anthropic(messages)

    assert len(result) == 1
    msg = result[0]
    assert msg["role"] == "user"
    assert isinstance(msg["content"], list)
    assert len(msg["content"]) == 1

    block = msg["content"][0]
    assert block["type"] == "tool_result"
    assert block["tool_use_id"] == "call_1"
    assert block["content"] == '{"price": 182.50}'


def test_normalize_plain_messages_unchanged() -> None:
    """Regular user/assistant messages without tool_calls pass through untouched."""
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "What is the price of AAPL?"},
        {"role": "assistant", "content": "The price is $182.50."},
    ]

    result = _normalize_messages_for_anthropic(messages)

    assert result == messages


def test_normalize_mixed_message_sequence() -> None:
    """Full multi-turn sequence with tool use normalizes correctly end-to-end."""
    messages = [
        {"role": "system", "content": "You are a financial assistant."},
        {"role": "user", "content": "Analyze AAPL for me."},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_abc",
                    "type": "function",
                    "function": {
                        "name": "get_stock_data",
                        "arguments": json.dumps({"ticker": "AAPL"}),
                    },
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call_abc",
            "content": '{"ticker": "AAPL", "price": 182.50}',
        },
        {"role": "assistant", "content": "Based on the data, AAPL looks strong."},
    ]

    result = _normalize_messages_for_anthropic(messages)

    assert len(result) == 5

    # system passes through
    assert result[0] == {"role": "system", "content": "You are a financial assistant."}

    # user passes through
    assert result[1] == {"role": "user", "content": "Analyze AAPL for me."}

    # assistant tool_calls → content blocks
    assert result[2]["role"] == "assistant"
    assert isinstance(result[2]["content"], list)
    tool_block = result[2]["content"][0]
    assert tool_block["type"] == "tool_use"
    assert tool_block["id"] == "call_abc"
    assert tool_block["name"] == "get_stock_data"
    assert tool_block["input"] == {"ticker": "AAPL"}

    # tool → user with tool_result
    assert result[3]["role"] == "user"
    assert result[3]["content"][0]["type"] == "tool_result"
    assert result[3]["content"][0]["tool_use_id"] == "call_abc"

    # final assistant text passes through
    assert result[4] == {"role": "assistant", "content": "Based on the data, AAPL looks strong."}
