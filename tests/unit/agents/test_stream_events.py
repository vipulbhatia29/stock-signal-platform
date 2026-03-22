"""Tests for stream event serialization."""

import json

from backend.agents.stream import StreamEvent


def test_thinking_event():
    """Thinking event serializes correctly."""
    e = StreamEvent(type="thinking", content="Analyzing AAPL...")
    line = e.to_ndjson()
    parsed = json.loads(line)
    assert parsed["type"] == "thinking"
    assert parsed["content"] == "Analyzing AAPL..."


def test_tool_start_event():
    """Tool start event includes tool name and params."""
    e = StreamEvent(type="tool_start", tool="compute_signals", params={"ticker": "AAPL"})
    parsed = json.loads(e.to_ndjson())
    assert parsed["tool"] == "compute_signals"
    assert parsed["params"]["ticker"] == "AAPL"


def test_tool_result_event():
    """Tool result event includes status and data."""
    e = StreamEvent(type="tool_result", tool="compute_signals", status="ok", data={"score": 8.5})
    parsed = json.loads(e.to_ndjson())
    assert parsed["status"] == "ok"
    assert parsed["data"]["score"] == 8.5


def test_token_event():
    """Token event includes content."""
    e = StreamEvent(type="token", content="Based on")
    parsed = json.loads(e.to_ndjson())
    assert parsed["content"] == "Based on"


def test_done_event():
    """Done event includes usage info."""
    e = StreamEvent(type="done", usage={"tokens": 4521, "model": "llama-3.3-70b"})
    parsed = json.loads(e.to_ndjson())
    assert parsed["usage"]["tokens"] == 4521


def test_provider_fallback_event():
    """Provider fallback event includes from/to data."""
    e = StreamEvent(type="provider_fallback", data={"from": "groq", "to": "anthropic"})
    parsed = json.loads(e.to_ndjson())
    assert parsed["data"]["from"] == "groq"


def test_null_fields_excluded():
    """Null fields are excluded from NDJSON output."""
    e = StreamEvent(type="token", content="hi")
    parsed = json.loads(e.to_ndjson())
    assert "tool" not in parsed
    assert "params" not in parsed
    assert "error" not in parsed


def test_error_event():
    """Error event includes error message."""
    event = StreamEvent(type="error", error="All providers failed")
    data = json.loads(event.to_ndjson())
    assert data["type"] == "error"
    assert data["error"] == "All providers failed"
    assert "content" not in data
