"""Tests for MCP subprocess lifecycle manager."""

from unittest.mock import AsyncMock, patch

import pytest

from backend.mcp_server.lifecycle import MAX_RESTARTS, MCPSubprocessManager


def _make_mock_client(*, connect_ok: bool = True) -> AsyncMock:
    """Create a properly configured AsyncMock for MCPToolClient."""
    client = AsyncMock()
    client.is_connected = True
    client.list_tools.return_value = ["t1", "t2", "t3"]
    if not connect_ok:
        client.connect.side_effect = OSError("spawn failed")
        client.is_connected = False
    return client


class TestMCPSubprocessManagerStart:
    """Tests for start()."""

    @pytest.mark.asyncio
    async def test_start_connects_and_sets_mode(self) -> None:
        """Start spawns subprocess and sets mode to stdio."""
        mgr = MCPSubprocessManager()
        mgr._client = _make_mock_client()
        await mgr.start()

        assert mgr.mode == "stdio"
        assert mgr.healthy is True
        assert mgr.restart_count == 0

    @pytest.mark.asyncio
    async def test_start_failure_raises(self) -> None:
        """Start raises RuntimeError if subprocess fails."""
        mgr = MCPSubprocessManager()
        mgr._client = _make_mock_client(connect_ok=False)

        with pytest.raises(RuntimeError, match="failed to start"):
            await mgr.start()
        assert mgr.last_error is not None


class TestMCPSubprocessManagerRestart:
    """Tests for restart()."""

    @pytest.mark.asyncio
    @patch("backend.mcp_server.lifecycle.MCPToolClient")
    async def test_restart_succeeds(self, mock_cls: AsyncMock) -> None:
        """Successful restart resets mode to stdio."""
        mock_cls.return_value = _make_mock_client()

        mgr = MCPSubprocessManager()
        mgr._client = _make_mock_client()
        await mgr.start()
        result = await mgr.restart()

        assert result is True
        assert mgr.mode == "stdio"

    @pytest.mark.asyncio
    @patch("backend.mcp_server.lifecycle.MCPToolClient")
    async def test_max_restarts_triggers_fallback(self, mock_cls: AsyncMock) -> None:
        """After MAX_RESTARTS failed attempts, mode becomes fallback_direct."""
        mock_cls.return_value = _make_mock_client(connect_ok=False)

        mgr = MCPSubprocessManager()
        mgr._mode = "stdio"

        result = await mgr.restart()

        assert result is False
        assert mgr.mode == "fallback_direct"
        assert mgr.fallback_since is not None
        assert mgr.restart_count > MAX_RESTARTS


class TestMCPSubprocessManagerEnsureHealthy:
    """Tests for ensure_healthy()."""

    @pytest.mark.asyncio
    async def test_healthy_subprocess_returns_true(self) -> None:
        """Healthy subprocess returns True without restart."""
        mgr = MCPSubprocessManager()
        mgr._client = _make_mock_client()
        await mgr.start()
        assert await mgr.ensure_healthy() is True

    @pytest.mark.asyncio
    async def test_fallback_mode_returns_false(self) -> None:
        """In fallback mode, ensure_healthy returns False."""
        mgr = MCPSubprocessManager()
        mgr._mode = "fallback_direct"
        assert await mgr.ensure_healthy() is False


class TestMCPSubprocessManagerCallTool:
    """Tests for call_tool()."""

    @pytest.mark.asyncio
    async def test_call_tool_in_fallback_raises(self) -> None:
        """Call tool in fallback mode raises ConnectionError."""
        mgr = MCPSubprocessManager()
        mgr._mode = "fallback_direct"
        with pytest.raises(ConnectionError, match="fallback"):
            await mgr.call_tool("analyze_stock", {"ticker": "AAPL"})


class TestMCPSubprocessManagerStop:
    """Tests for stop()."""

    @pytest.mark.asyncio
    async def test_stop_sets_disabled(self) -> None:
        """Stop sets mode to disabled."""
        mgr = MCPSubprocessManager()
        mgr._client = _make_mock_client()
        await mgr.start()
        await mgr.stop()

        assert mgr.mode == "disabled"


class TestMCPSubprocessManagerProperties:
    """Tests for properties."""

    def test_initial_state(self) -> None:
        """Fresh manager starts in disabled mode."""
        mgr = MCPSubprocessManager()
        assert mgr.mode == "disabled"
        assert mgr.healthy is False
        assert mgr.restart_count == 0
        assert mgr.uptime_seconds is None
        assert mgr.last_error is None
        assert mgr.fallback_since is None
