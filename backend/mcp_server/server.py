"""FastMCP server — exposes Tool Registry as MCP Streamable HTTP at /mcp."""

from __future__ import annotations

import logging
from typing import Any

from fastmcp import FastMCP

from backend.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


def create_mcp_app(registry: ToolRegistry) -> FastMCP:
    """Create a FastMCP server that mirrors the Tool Registry.

    Each tool in the registry is registered with FastMCP so that external
    MCP clients can discover and invoke them over Streamable HTTP.

    Args:
        registry: The ToolRegistry containing all registered tools.

    Returns:
        A configured FastMCP instance ready to be mounted on FastAPI.
    """
    mcp = FastMCP("StockSignal Intelligence Platform")

    for tool_info in registry.discover():
        tool = registry.get(tool_info.name)
        if tool is None:
            continue

        # Capture tool in closure via default argument
        _register_tool(mcp, tool_info.name, tool_info.description, tool)

    logger.info("MCP server created with %d tools", len(registry.discover()))
    return mcp


def _register_tool(mcp: FastMCP, name: str, description: str, tool: Any) -> None:
    """Register a single tool with FastMCP using closure capture."""

    @mcp.tool(name=name, description=description)
    async def _handler(params: dict = {}, _tool: Any = tool) -> Any:  # noqa: B006
        """MCP tool handler — delegates to the internal tool."""
        result = await _tool.execute(params)
        if result.status == "ok":
            return result.data
        return {"error": result.error, "status": result.status}
