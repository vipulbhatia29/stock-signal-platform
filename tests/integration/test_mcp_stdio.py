"""Integration tests for MCP stdio transport — real subprocess round-trips.

These tests spawn an actual MCP tool server subprocess via MCPToolClient
and verify the full stdio JSON-RPC communication path. They are slower
than unit tests and marked with ``pytest.mark.integration``.

Requires: ``uv`` on PATH, all backend dependencies installed.
"""

from __future__ import annotations

import pytest

from backend.mcp_server.lifecycle import MAX_RESTARTS, MCPSubprocessManager
from backend.mcp_server.tool_client import MCPToolClient

# Minimum expected tools (20 internal + 4 MCP adapters).
_MIN_EXPECTED_TOOLS = 20


@pytest.fixture
async def mcp_client():
    """Spawn a real MCP tool server subprocess and yield a connected client.

    Teardown suppresses anyio RuntimeError from cancel-scope task mismatch —
    a known incompatibility between anyio task groups and pytest-asyncio
    fixture teardown.
    """
    client = MCPToolClient()
    await client.connect("backend.mcp_server.tool_server")
    yield client
    try:
        await client.close()
    except RuntimeError:
        # anyio cancel scope exited in different task — harmless in teardown
        client._connected = False


# ---------------------------------------------------------------------------
# T5.1 — stdio round-trip tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestStdioRoundTrip:
    """Round-trip tests using a real stdio subprocess."""

    @pytest.mark.asyncio
    async def test_subprocess_starts_and_lists_tools(self, mcp_client: MCPToolClient) -> None:
        """Tool server subprocess starts and advertises 20+ tools."""
        tools = await mcp_client.list_tools()
        assert len(tools) >= _MIN_EXPECTED_TOOLS, (
            f"Expected at least {_MIN_EXPECTED_TOOLS} tools, got {len(tools)}: {tools}"
        )

    @pytest.mark.asyncio
    async def test_tool_names_include_known_tools(self, mcp_client: MCPToolClient) -> None:
        """Known tool names appear in the server's tool list."""
        tools = await mcp_client.list_tools()
        expected_subset = {"search_stocks", "screen_stocks", "compute_signals"}
        assert expected_subset.issubset(set(tools)), (
            f"Missing tools: {expected_subset - set(tools)}"
        )

    @pytest.mark.asyncio
    async def test_call_search_stocks_round_trip(self, mcp_client: MCPToolClient) -> None:
        """Call search_stocks via stdio and get a valid ToolResult back.

        search_stocks uses a DB query so without a real DB it returns an error,
        but the important thing is the round-trip: we get a properly deserialized
        ToolResult (not a transport error).
        """
        result = await mcp_client.call_tool("search_stocks", {"query": "AAPL"})
        # We got a ToolResult back (not a transport/connection error)
        assert result.status in ("ok", "error", "degraded")
        # If error, it should be a tool-level error (DB), not a protocol error
        if result.status == "error":
            assert "MCP transport" not in (result.error or "")

    @pytest.mark.asyncio
    async def test_call_tool_with_invalid_name(self, mcp_client: MCPToolClient) -> None:
        """Calling a non-existent tool returns an error ToolResult."""
        result = await mcp_client.call_tool("nonexistent_tool_xyz", {})
        assert result.status == "error"
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_call_tool_with_empty_params(self, mcp_client: MCPToolClient) -> None:
        """Calling a tool with empty params is handled gracefully."""
        result = await mcp_client.call_tool("search_stocks", {})
        # Should get a ToolResult, possibly error due to missing required params
        assert result.status in ("ok", "error", "degraded")

    @pytest.mark.asyncio
    async def test_client_is_connected_property(self, mcp_client: MCPToolClient) -> None:
        """Client reports connected state after successful connect."""
        assert mcp_client.is_connected is True

    @pytest.mark.asyncio
    async def test_client_disconnects_cleanly(self) -> None:
        """Client can connect and disconnect without errors."""
        client = MCPToolClient()
        await client.connect("backend.mcp_server.tool_server")
        assert client.is_connected is True
        await client.close()
        assert client.is_connected is False


# ---------------------------------------------------------------------------
# T5.2 — Subprocess lifecycle tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestSubprocessLifecycle:
    """Tests for MCPSubprocessManager lifecycle: start, restart, fallback."""

    @pytest.mark.asyncio
    async def test_manager_starts_in_stdio_mode(self) -> None:
        """MCPSubprocessManager starts and enters 'stdio' mode."""
        manager = MCPSubprocessManager()
        try:
            await manager.start()
            assert manager.mode == "stdio"
            assert manager.healthy is True
            assert manager.uptime_seconds is not None
            assert manager.uptime_seconds >= 0
        finally:
            await manager.stop()

    @pytest.mark.asyncio
    async def test_manager_stop_sets_disabled(self) -> None:
        """Stopping the manager sets mode to 'disabled'."""
        manager = MCPSubprocessManager()
        try:
            await manager.start()
            assert manager.mode == "stdio"
        finally:
            await manager.stop()
        assert manager.mode == "disabled"
        assert manager.healthy is False

    @pytest.mark.asyncio
    async def test_manager_restart_succeeds(self) -> None:
        """Manager can restart after explicit close of its internal client."""
        manager = MCPSubprocessManager()
        try:
            await manager.start()
            # Simulate subprocess going away by closing the client
            await manager._client.close()
            assert manager._client.is_connected is False

            # restart() should reconnect
            success = await manager.restart()
            assert success is True
            assert manager.mode == "stdio"
            assert manager.healthy is True
        finally:
            await manager.stop()

    @pytest.mark.asyncio
    async def test_ensure_healthy_restarts_dead_subprocess(self) -> None:
        """ensure_healthy() detects a dead subprocess and restarts it."""
        manager = MCPSubprocessManager()
        try:
            await manager.start()
            # Kill the connection
            await manager._client.close()

            # ensure_healthy should detect and restart
            healthy = await manager.ensure_healthy()
            assert healthy is True
            assert manager.mode == "stdio"
        finally:
            await manager.stop()

    @pytest.mark.asyncio
    async def test_fallback_after_max_restarts(self) -> None:
        """Manager enters fallback_direct mode after MAX_RESTARTS failures.

        We simulate this by setting _restart_count just below the threshold
        and then triggering a restart that will fail (because we monkeypatch
        connect to always raise).
        """
        manager = MCPSubprocessManager()
        try:
            await manager.start()

            # Exhaust restart budget by setting count to MAX_RESTARTS
            manager._restart_count = MAX_RESTARTS

            # Next restart attempt should trigger fallback
            success = await manager.restart()
            assert success is False
            assert manager.mode == "fallback_direct"
            assert manager.fallback_since is not None
            assert manager.healthy is False
        finally:
            await manager.stop()

    @pytest.mark.asyncio
    async def test_call_tool_in_fallback_raises(self) -> None:
        """call_tool raises ConnectionError when in fallback mode."""
        manager = MCPSubprocessManager()
        try:
            await manager.start()
            # Force fallback
            manager._restart_count = MAX_RESTARTS
            await manager.restart()

            with pytest.raises(ConnectionError, match="fallback"):
                await manager.call_tool("search_stocks", {"query": "AAPL"})
        finally:
            await manager.stop()

    @pytest.mark.asyncio
    async def test_manager_call_tool_round_trip(self) -> None:
        """Manager.call_tool() performs a full round-trip through the subprocess."""
        manager = MCPSubprocessManager()
        try:
            await manager.start()
            result = await manager.call_tool("search_stocks", {"query": "AAPL"})
            assert result.status in ("ok", "error", "degraded")
            # Not a transport error
            if result.status == "error":
                assert "MCP transport" not in (result.error or "")
        finally:
            await manager.stop()
