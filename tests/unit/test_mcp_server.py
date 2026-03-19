"""Tests for MCP server setup."""

import pytest

from backend.mcp_server.server import create_mcp_app
from backend.tools.base import BaseTool, ToolResult
from backend.tools.registry import ToolRegistry


class _DummyTool(BaseTool):
    """A minimal tool for testing MCP server registration."""

    name = "dummy_tool"
    description = "A dummy tool for testing."
    category = "testing"
    parameters: dict = {"type": "object", "properties": {}}

    async def execute(self, params: dict) -> ToolResult:
        """Return a dummy result."""
        return ToolResult(status="ok", data={"message": "hello"})


def test_mcp_app_creates():
    """MCP app can be created with a registry."""
    registry = ToolRegistry()
    mcp = create_mcp_app(registry)
    assert mcp is not None


@pytest.mark.asyncio
async def test_mcp_app_registers_tools():
    """MCP app registers all tools from the registry."""
    registry = ToolRegistry()
    tool = _DummyTool()
    registry.register(tool)

    mcp = create_mcp_app(registry)
    assert mcp is not None
    # Verify the tool was registered with FastMCP
    registered_tool = await mcp.get_tool("dummy_tool")
    assert registered_tool is not None


def test_mcp_app_empty_registry():
    """MCP app works with an empty registry."""
    registry = ToolRegistry()
    mcp = create_mcp_app(registry)
    assert mcp is not None


def test_mcp_http_app_creates():
    """FastMCP.http_app() returns a Starlette ASGI application."""
    registry = ToolRegistry()
    mcp = create_mcp_app(registry)
    http_app = mcp.http_app()
    assert http_app is not None
    # Should be a Starlette-compatible ASGI app
    assert callable(http_app)
