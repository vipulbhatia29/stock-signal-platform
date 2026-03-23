"""Tests for MCP tool client and user context injection."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.mcp_server.tool_client import MCPToolClient, inject_user_context


class TestMCPToolClientCallTool:
    """Tests for MCPToolClient.call_tool()."""

    @pytest.mark.asyncio
    async def test_call_tool_deserializes_ok_result(self) -> None:
        """Successful tool call returns deserialized ToolResult."""
        client = MCPToolClient()
        client._connected = True
        client._session = AsyncMock()
        ok_json = '{"status": "ok", "data": {"price": 150.0}, "error": null}'
        client._session.call_tool.return_value = SimpleNamespace(
            content=[SimpleNamespace(text=ok_json)]
        )
        result = await client.call_tool("analyze_stock", {"ticker": "AAPL"})
        assert result.status == "ok"
        assert result.data == {"price": 150.0}
        assert result.error is None

    @pytest.mark.asyncio
    async def test_call_tool_deserializes_error_result(self) -> None:
        """Error tool call returns ToolResult with status 'error'."""
        client = MCPToolClient()
        client._connected = True
        client._session = AsyncMock()
        err_json = '{"status": "error", "data": null, "error": "Not found"}'
        client._session.call_tool.return_value = SimpleNamespace(
            content=[SimpleNamespace(text=err_json)]
        )
        result = await client.call_tool("get_forecast", {"ticker": "ZZZZZ"})
        assert result.status == "error"
        assert result.error == "Not found"

    @pytest.mark.asyncio
    async def test_call_tool_when_not_connected_raises(self) -> None:
        """Calling a tool when not connected raises ConnectionError."""
        client = MCPToolClient()
        with pytest.raises(ConnectionError):
            await client.call_tool("analyze_stock", {"ticker": "AAPL"})

    @pytest.mark.asyncio
    async def test_call_tool_wraps_mcp_exception(self) -> None:
        """MCP exceptions are wrapped into error ToolResult."""
        client = MCPToolClient()
        client._connected = True
        client._session = AsyncMock()
        client._session.call_tool.side_effect = RuntimeError("MCP transport error")
        result = await client.call_tool("analyze_stock", {"ticker": "AAPL"})
        assert result.status == "error"
        assert "MCP transport error" in result.error

    @pytest.mark.asyncio
    async def test_call_tool_handles_empty_response(self) -> None:
        """Empty MCP response returns error ToolResult."""
        client = MCPToolClient()
        client._connected = True
        client._session = AsyncMock()
        client._session.call_tool.return_value = SimpleNamespace(content=[])
        result = await client.call_tool("analyze_stock", {"ticker": "AAPL"})
        assert result.status == "error"
        assert "Empty" in result.error


class TestMCPToolClientListTools:
    """Tests for MCPToolClient.list_tools()."""

    @pytest.mark.asyncio
    async def test_list_tools_returns_names(self) -> None:
        """list_tools returns a list of tool name strings."""
        client = MCPToolClient()
        client._connected = True
        client._session = AsyncMock()
        client._session.list_tools.return_value = SimpleNamespace(
            tools=[
                SimpleNamespace(name="analyze_stock"),
                SimpleNamespace(name="get_forecast"),
                SimpleNamespace(name="search_stocks"),
            ]
        )
        names = await client.list_tools()
        assert names == ["analyze_stock", "get_forecast", "search_stocks"]

    @pytest.mark.asyncio
    async def test_list_tools_when_not_connected_raises(self) -> None:
        """Listing tools when not connected raises ConnectionError."""
        client = MCPToolClient()
        with pytest.raises(ConnectionError):
            await client.list_tools()


class TestMCPToolClientLifecycle:
    """Tests for MCPToolClient connection lifecycle."""

    @pytest.mark.asyncio
    async def test_close_sets_disconnected(self) -> None:
        """After close, is_connected is False."""
        client = MCPToolClient()
        client._connected = True
        client._session = AsyncMock()
        await client.close()
        assert client.is_connected is False
        assert client._session is None

    def test_is_connected_default_false(self) -> None:
        """New client is not connected by default."""
        client = MCPToolClient()
        assert client.is_connected is False


class TestInjectUserContext:
    """Tests for the inject_user_context helper."""

    def test_adds_user_id_for_portfolio_tool(self) -> None:
        """Portfolio tool gets user_id injected."""
        result = inject_user_context("portfolio_exposure", {"other": "val"}, "user-123")
        assert result["user_id"] == "user-123"
        assert result["other"] == "val"

    def test_skips_non_portfolio_tools(self) -> None:
        """Non-portfolio tools are returned unchanged."""
        params = {"ticker": "AAPL"}
        result = inject_user_context("analyze_stock", params, "user-123")
        assert "user_id" not in result
        assert result is params

    def test_does_not_overwrite_existing_user_id(self) -> None:
        """If user_id already in params, don't overwrite."""
        params = {"user_id": "existing-id"}
        result = inject_user_context("portfolio_exposure", params, "new-id")
        assert result["user_id"] == "existing-id"
        assert result is params

    def test_skips_when_no_user_id(self) -> None:
        """If user_id is None, don't inject."""
        params = {"other": "val"}
        result = inject_user_context("portfolio_exposure", params, None)
        assert "user_id" not in result

    def test_all_portfolio_tools_covered(self) -> None:
        """All three portfolio tools get user_id injected."""
        for tool_name in (
            "portfolio_exposure",
            "get_portfolio_forecast",
            "recommendations",
        ):
            result = inject_user_context(tool_name, {}, "user-123")
            assert result["user_id"] == "user-123", f"Failed for {tool_name}"
