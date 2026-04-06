"""MCP client wrapper for calling tools via stdio transport.

Connects to a FastMCP tool server subprocess and provides a simple
interface for calling tools and getting ToolResults back.
"""

import asyncio
import logging
import os
from contextlib import AsyncExitStack

from backend.tools.base import ToolResult

logger = logging.getLogger(__name__)

# Tools that require user context (user_id) injected into params.
_USER_CONTEXT_TOOLS = frozenset(
    {
        "portfolio_exposure",
        "get_portfolio_forecast",
        "recommendations",
    }
)

# Timeout for individual tool calls via MCP.
_TOOL_CALL_TIMEOUT = 30.0


class MCPToolClient:
    """Client that calls tools via MCP stdio transport.

    Connects to a FastMCP tool server subprocess and provides
    a simple interface for calling tools and getting ToolResults.
    """

    def __init__(self) -> None:
        """Initialize the MCP tool client (not yet connected)."""
        self._session = None
        self._exit_stack = AsyncExitStack()
        self._connected = False

    async def connect(self, server_script: str) -> None:
        """Spawn the MCP tool server subprocess and establish stdio connection.

        Args:
            server_script: Python module path for the tool server
                          (e.g., "backend.mcp_server.tool_server").
        """
        from mcp import ClientSession
        from mcp.client.stdio import StdioServerParameters, stdio_client

        server_params = StdioServerParameters(
            command="uv",
            args=["run", "python", "-m", server_script],
            env=dict(os.environ),
        )
        stdio_transport = await self._exit_stack.enter_async_context(stdio_client(server_params))
        read, write = stdio_transport
        self._session = await self._exit_stack.enter_async_context(ClientSession(read, write))
        await self._session.initialize()
        self._connected = True
        logger.info("MCP tool client connected to %s", server_script)

    async def call_tool(self, name: str, params: dict) -> ToolResult:
        """Call a tool via MCP and return a ToolResult.

        Args:
            name: Tool name (e.g., "analyze_stock").
            params: Tool parameters dict.

        Returns:
            ToolResult deserialized from the MCP response.

        Raises:
            ConnectionError: If not connected to tool server.
        """
        if not self._connected or self._session is None:
            raise ConnectionError("MCP tool client is not connected")

        try:
            # Wrap params inside {"params": ...} so FastMCP maps them to the
            # server handler's `params: dict` argument rather than attempting
            # to unpack each key as a separate keyword argument.
            wrapped = {"params": params} if params else {}
            result = await asyncio.wait_for(
                self._session.call_tool(name, wrapped),
                timeout=_TOOL_CALL_TIMEOUT,
            )
            # MCP response content is a list of content blocks.
            # Our tool server returns a single text block with JSON.
            if result.content and len(result.content) > 0:
                text = result.content[0].text
                return ToolResult.from_json(text)
            return ToolResult(status="error", data=None, error="Empty MCP response")
        except asyncio.TimeoutError:
            logger.warning("MCP tool call timed out: %s", name)
            return ToolResult(status="timeout", data=None, error=f"Tool {name} timed out")
        except ConnectionError:
            raise
        except Exception:
            logger.error("MCP tool '%s' execution failed", name, exc_info=True)
            return ToolResult(
                status="error",
                data=None,
                error="Tool execution failed. Please try again.",
            )

    async def list_tools(self) -> list[str]:
        """List available tools from the MCP server.

        Returns:
            List of tool name strings.

        Raises:
            ConnectionError: If not connected to tool server.
        """
        if not self._connected or self._session is None:
            raise ConnectionError("MCP tool client is not connected")

        result = await self._session.list_tools()
        return [tool.name for tool in result.tools]

    async def close(self) -> None:
        """Terminate the subprocess gracefully."""
        await self._exit_stack.aclose()
        self._session = None
        self._connected = False
        logger.info("MCP tool client disconnected")

    @property
    def is_connected(self) -> bool:
        """Check if the client is connected to the tool server."""
        return self._connected


def inject_user_context(tool_name: str, params: dict, user_id: str | None) -> dict:
    """Inject user_id into params for portfolio tools if not already present.

    Args:
        tool_name: Name of the tool being called.
        params: Original tool parameters.
        user_id: Current user's ID string, or None if unavailable.

    Returns:
        Updated params dict (new dict if injection needed, same otherwise).
    """
    if tool_name in _USER_CONTEXT_TOOLS and user_id and "user_id" not in params:
        return {**params, "user_id": user_id}
    return params
