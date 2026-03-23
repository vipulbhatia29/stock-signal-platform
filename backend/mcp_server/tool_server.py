"""MCP Tool Server — stdio transport.

Standalone process that exposes all 20+ tools via MCP protocol.
Spawned by FastAPI lifespan, communicates via stdin/stdout.

Usage::

    uv run python -m backend.mcp_server.tool_server
"""

from __future__ import annotations

import logging
from typing import Any

from fastmcp import FastMCP

from backend.tools.base import ToolResult
from backend.tools.build_registry import build_registry
from backend.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


def create_stdio_server() -> FastMCP:
    """Build a FastMCP server with all tools from the registry.

    Creates its own ToolRegistry via ``build_registry()`` and registers
    every tool as a FastMCP tool handler. Each handler delegates to the
    internal tool's ``execute()`` method and returns a JSON-serialized
    ``ToolResult``.

    Returns:
        A configured FastMCP instance ready for stdio transport.
    """
    registry = build_registry()
    mcp = FastMCP("StockSignal Tool Server (stdio)")

    for tool_info in registry.discover():
        tool = registry.get(tool_info.name)
        _register_tool(mcp, tool_info.name, tool_info.description, tool, registry)

    logger.info(
        "MCP stdio server created with %d tools",
        len(registry.discover()),
    )
    return mcp


def _register_tool(
    mcp: FastMCP,
    name: str,
    description: str,
    tool: Any,
    registry: ToolRegistry,
) -> None:
    """Register a single tool with FastMCP using closure capture.

    Args:
        mcp: The FastMCP server instance.
        name: Tool name for MCP registration.
        description: Tool description for MCP registration.
        tool: The BaseTool instance to delegate execution to.
        registry: The ToolRegistry (unused but kept for future middleware).
    """

    @mcp.tool(name=name, description=description)
    async def _handler(params: dict = {}, _tool: Any = tool) -> str:  # noqa: B006
        """MCP tool handler — delegates to internal tool, returns JSON."""
        result: ToolResult = await _tool.execute(params)
        return result.to_json()


if __name__ == "__main__":
    server = create_stdio_server()
    server.run(transport="stdio")
