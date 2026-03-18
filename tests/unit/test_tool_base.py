"""Tests for tool base classes."""

from datetime import timedelta

from backend.tools.base import (
    BaseTool,
    CachePolicy,
    ToolFilter,
    ToolInfo,
    ToolResult,
)


def test_cache_policy_fields():
    """CachePolicy stores TTL and key fields."""
    policy = CachePolicy(ttl=timedelta(hours=24), key_fields=["ticker"])
    assert policy.ttl == timedelta(hours=24)
    assert policy.key_fields == ["ticker"]


def test_tool_result_ok():
    """ToolResult with ok status stores data."""
    result = ToolResult(status="ok", data={"price": 150.0})
    assert result.status == "ok"
    assert result.data["price"] == 150.0


def test_tool_result_error():
    """ToolResult with error status stores error message."""
    result = ToolResult(status="error", error="Tool failed")
    assert result.status == "error"
    assert result.data is None


def test_tool_filter_matches():
    """ToolFilter matches tools in allowed categories."""
    f = ToolFilter(categories=["analysis", "data"])
    info = ToolInfo(name="t", description="d", category="analysis", parameters={})
    assert f.matches(info)


def test_tool_filter_no_match():
    """ToolFilter rejects tools not in allowed categories."""
    f = ToolFilter(categories=["portfolio"])
    info = ToolInfo(name="t", description="d", category="analysis", parameters={})
    assert not f.matches(info)


def test_tool_info_to_llm_schema():
    """ToolInfo.to_llm_schema() returns OpenAI-compatible function schema."""
    info = ToolInfo(
        name="compute_signals",
        description="Compute signals for a ticker",
        category="data",
        parameters={
            "type": "object",
            "properties": {"ticker": {"type": "string"}},
            "required": ["ticker"],
        },
    )
    schema = info.to_llm_schema()
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "compute_signals"
    assert "properties" in schema["function"]["parameters"]
