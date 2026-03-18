"""Tests for the LangGraph agent graph."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.agents.graph import AgentState, build_agent_graph, execute_tool_safely
from backend.tools.base import BaseTool, ToolResult
from backend.tools.registry import ToolRegistry


@pytest.fixture
def mock_registry():
    """Fresh ToolRegistry for each test."""
    return ToolRegistry()


def test_agent_state_has_required_fields():
    """AgentState TypedDict has all required fields."""
    state: AgentState = {
        "messages": [],
        "agent_type": "stock",
        "iteration": 0,
        "tool_results": [],
        "usage": {},
    }
    assert state["agent_type"] == "stock"
    assert state["iteration"] == 0


def test_build_agent_graph_compiles():
    """build_agent_graph returns a compiled runnable."""
    from backend.agents.stock_agent import StockAgent

    registry = ToolRegistry()
    mock_llm = MagicMock()
    mock_llm.bind_tools = MagicMock(return_value=mock_llm)

    graph = build_agent_graph(
        agent=StockAgent(),
        registry=registry,
        llm=mock_llm,
    )
    assert graph is not None


@pytest.mark.asyncio
async def test_execute_tool_safely_success(mock_registry):
    """execute_tool_safely returns ToolResult on success."""

    class FakeTool(BaseTool):
        name = "fake_tool"
        description = "Fake"
        category = "test"
        parameters = {}
        timeout_seconds = 5.0

        async def execute(self, params):
            """Return success."""
            return ToolResult(status="ok", data={"result": "success"})

    mock_registry.register(FakeTool())
    result = await execute_tool_safely(mock_registry, "fake_tool", {})
    assert result.status == "ok"


@pytest.mark.asyncio
async def test_execute_tool_safely_timeout(mock_registry):
    """execute_tool_safely returns timeout on slow tool."""

    class SlowTool(BaseTool):
        name = "slow_tool"
        description = "Slow"
        category = "test"
        parameters = {}
        timeout_seconds = 0.01

        async def execute(self, params):
            """Simulate slow execution."""
            await asyncio.sleep(10)
            return ToolResult(status="ok")

    mock_registry.register(SlowTool())
    result = await execute_tool_safely(mock_registry, "slow_tool", {})
    assert result.status == "timeout"


@pytest.mark.asyncio
async def test_execute_tool_safely_not_found(mock_registry):
    """execute_tool_safely returns error for unknown tool."""
    result = await execute_tool_safely(mock_registry, "nonexistent", {})
    assert result.status == "error"
    assert "not found" in result.error
