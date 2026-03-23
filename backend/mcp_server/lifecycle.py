"""MCP subprocess lifecycle manager.

Manages the stdio tool server subprocess: start, health check,
restart on failure, and fallback to direct calls after max retries.
"""

import logging
import time

from backend.mcp_server.tool_client import MCPToolClient
from backend.tools.base import ToolResult

logger = logging.getLogger(__name__)

MAX_RESTARTS = 3
_SERVER_MODULE = "backend.mcp_server.tool_server"


class MCPSubprocessManager:
    """Manages the MCP tool server subprocess lifecycle.

    Provides start/stop, health checking, auto-restart with max retries,
    and fallback to direct registry calls when the subprocess is unavailable.
    """

    def __init__(self) -> None:
        """Initialize the subprocess manager."""
        self._client = MCPToolClient()
        self._restart_count = 0
        self._mode = "disabled"
        self._started_at: float | None = None
        self._last_error: str | None = None
        self._fallback_since: str | None = None

    async def start(self) -> None:
        """Start the MCP tool server subprocess.

        Raises:
            RuntimeError: If the subprocess fails to start or health check fails.
        """
        try:
            await self._client.connect(_SERVER_MODULE)
            tools = await self._client.list_tools()
            self._mode = "stdio"
            self._started_at = time.time()
            self._restart_count = 0
            logger.info("MCP Tool Server started: %d tools available", len(tools))
        except Exception as exc:
            self._last_error = str(exc)
            logger.exception("Failed to start MCP Tool Server")
            raise RuntimeError(f"MCP Tool Server failed to start: {exc}") from exc

    async def restart(self) -> bool:
        """Attempt to restart the subprocess.

        Returns:
            True if restart succeeded, False if max retries exceeded.
        """
        self._restart_count += 1
        if self._restart_count > MAX_RESTARTS:
            self._mode = "fallback_direct"
            self._fallback_since = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            logger.error(
                "MCP Tool Server: %d restart attempts exhausted — falling back to direct calls",
                MAX_RESTARTS,
            )
            return False

        logger.warning(
            "MCP Tool Server restart attempt %d/%d",
            self._restart_count,
            MAX_RESTARTS,
        )
        try:
            await self._client.close()
        except Exception:
            pass  # Best-effort cleanup

        try:
            self._client = MCPToolClient()
            await self._client.connect(_SERVER_MODULE)
            tools = await self._client.list_tools()
            self._mode = "stdio"
            self._started_at = time.time()
            self._last_error = None
            logger.info("MCP Tool Server restarted successfully: %d tools", len(tools))
            return True
        except Exception as exc:
            self._last_error = str(exc)
            logger.exception("MCP Tool Server restart failed")
            return await self.restart()

    async def ensure_healthy(self) -> bool:
        """Check if subprocess is alive; restart if dead.

        Returns:
            True if healthy (or restarted successfully), False if in fallback.
        """
        if self._mode == "fallback_direct":
            return False

        if not self._client.is_connected:
            return await self.restart()

        try:
            await self._client.list_tools()
            return True
        except Exception:
            return await self.restart()

    async def call_tool(self, name: str, params: dict) -> ToolResult:
        """Call a tool via MCP, with auto-restart on failure.

        If the subprocess is unhealthy and restarts are exhausted,
        raises ConnectionError so the caller can fall back to direct calls.

        Args:
            name: Tool name.
            params: Tool parameters.

        Returns:
            ToolResult from the tool server.

        Raises:
            ConnectionError: If in fallback mode (subprocess unavailable).
        """
        if self._mode == "fallback_direct":
            raise ConnectionError("MCP subprocess unavailable — in fallback mode")

        result = await self._client.call_tool(name, params)
        # If the call returned a transport-level error, try restart
        if result.status == "error" and "MCP transport" in (result.error or ""):
            healthy = await self.ensure_healthy()
            if healthy:
                return await self._client.call_tool(name, params)
            raise ConnectionError("MCP subprocess unavailable after restart attempts")
        return result

    async def stop(self) -> None:
        """Stop the subprocess gracefully."""
        try:
            await self._client.close()
        except Exception:
            pass
        self._mode = "disabled"
        logger.info("MCP Tool Server stopped")

    @property
    def healthy(self) -> bool:
        """Whether the subprocess is running and responsive."""
        return self._mode == "stdio" and self._client.is_connected

    @property
    def restart_count(self) -> int:
        """Number of restart attempts since last successful start."""
        return self._restart_count

    @property
    def mode(self) -> str:
        """Current mode: 'stdio', 'fallback_direct', or 'disabled'."""
        return self._mode

    @property
    def uptime_seconds(self) -> float | None:
        """Seconds since subprocess started, or None if not running."""
        if self._started_at is None:
            return None
        return time.time() - self._started_at

    @property
    def last_error(self) -> str | None:
        """Last error message from subprocess failure."""
        return self._last_error

    @property
    def fallback_since(self) -> str | None:
        """ISO timestamp when fallback mode was entered, or None."""
        return self._fallback_since
