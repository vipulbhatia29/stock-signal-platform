"""Tests for ToolRegistry."""

import pytest

from backend.tools.base import BaseTool, ToolFilter, ToolResult
from backend.tools.registry import ToolRegistry


class FakeTool(BaseTool):
    """A fake tool for testing."""

    def __init__(self, name: str = "fake_tool", category: str = "test"):
        self.name = name
        self.description = f"Fake tool: {name}"
        self.category = category
        self.parameters = {"type": "object", "properties": {}}
        self.cache_policy = None
        self.timeout_seconds = 5.0

    async def execute(self, params):
        """Return a successful result."""
        return ToolResult(status="ok", data={"result": "success"})


@pytest.fixture
def registry():
    """Fresh ToolRegistry for each test."""
    return ToolRegistry()


def test_register_and_get(registry):
    """Register a tool and retrieve it by name."""
    tool = FakeTool()
    registry.register(tool)
    assert registry.get("fake_tool") is tool


def test_register_duplicate_raises(registry):
    """Registering a tool with the same name raises ValueError."""
    tool = FakeTool()
    registry.register(tool)
    with pytest.raises(ValueError, match="already registered"):
        registry.register(tool)


def test_get_unknown_raises(registry):
    """Getting an unknown tool raises KeyError."""
    with pytest.raises(KeyError):
        registry.get("nonexistent")


def test_discover_returns_all(registry):
    """discover() returns metadata for all registered tools."""
    registry.register(FakeTool("tool_a", "analysis"))
    registry.register(FakeTool("tool_b", "data"))
    infos = registry.discover()
    assert len(infos) == 2
    assert {i.name for i in infos} == {"tool_a", "tool_b"}


def test_by_category(registry):
    """by_category() filters tools by category."""
    registry.register(FakeTool("tool_a", "analysis"))
    registry.register(FakeTool("tool_b", "data"))
    registry.register(FakeTool("tool_c", "analysis"))
    result = registry.by_category("analysis")
    assert len(result) == 2


def test_schemas_with_filter(registry):
    """schemas() returns LLM-compatible schemas for filtered tools."""
    registry.register(FakeTool("tool_a", "analysis"))
    registry.register(FakeTool("tool_b", "data"))
    f = ToolFilter(categories=["analysis"])
    schemas = registry.schemas(f)
    assert len(schemas) == 1
    assert schemas[0]["function"]["name"] == "tool_a"


@pytest.mark.asyncio
async def test_execute(registry):
    """execute() runs a tool and returns its result."""
    tool = FakeTool()
    registry.register(tool)
    result = await registry.execute("fake_tool", {})
    assert result.status == "ok"


def test_health_all_ok(registry):
    """health() returns True for all registered tools."""
    registry.register(FakeTool("t1"))
    health = registry.health()
    assert health["t1"] is True


def test_register_mcp(registry):
    """register_mcp() registers all tools from an adapter."""
    from unittest.mock import MagicMock

    adapter = MagicMock()
    tool_a = FakeTool("mcp_tool_a", "sec")
    tool_b = FakeTool("mcp_tool_b", "sec")
    adapter.get_tools.return_value = [tool_a, tool_b]

    registry.register_mcp(adapter)
    assert registry.get("mcp_tool_a") is tool_a
    assert registry.get("mcp_tool_b") is tool_b
    assert len(registry.discover()) == 2
