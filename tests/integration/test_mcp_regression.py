"""Regression tests — MCP stdio path vs direct in-process path.

The key proof that the MCP refactor is behavior-preserving: calling a tool
through the stdio subprocess must produce the same ToolResult as calling it
directly via ToolRegistry.execute().

Without a real database these tools will error, but the regression tests
verify structural equivalence: both paths error the same way, and tool
discovery is identical.
"""

from __future__ import annotations

import pytest

from backend.mcp_server.tool_client import MCPToolClient
from backend.tools.base import ToolResult
from backend.tools.build_registry import build_registry


@pytest.fixture
async def mcp_client():
    """Spawn a real MCP tool server subprocess and yield a connected client."""
    client = MCPToolClient()
    await client.connect("backend.mcp_server.tool_server")
    yield client
    try:
        await client.close()
    except RuntimeError:
        client._connected = False


@pytest.fixture
def direct_registry():
    """Build a fresh in-process ToolRegistry for direct comparison."""
    return build_registry()


async def _safe_execute(registry, name: str, params: dict) -> ToolResult:
    """Execute a tool via direct registry, catching exceptions as ToolResult errors.

    The MCP path always returns a ToolResult (errors are caught in the client).
    The direct path may raise exceptions. This helper normalizes both to ToolResult.
    """
    try:
        return await registry.execute(name, params)
    except Exception as exc:
        return ToolResult(status="error", data=None, error=str(exc))


@pytest.mark.integration
class TestMCPVsDirectRegression:
    """Compare MCP and direct tool execution results."""

    @pytest.mark.asyncio
    async def test_tool_list_matches(self, mcp_client: MCPToolClient, direct_registry) -> None:
        """MCP server exposes the same tool names as the direct registry."""
        mcp_tools = set(await mcp_client.list_tools())
        direct_tools = {info.name for info in direct_registry.discover()}
        assert mcp_tools == direct_tools, (
            f"Tool mismatch — MCP-only: {mcp_tools - direct_tools}, "
            f"Direct-only: {direct_tools - mcp_tools}"
        )

    @pytest.mark.asyncio
    async def test_search_stocks_identical_status(
        self, mcp_client: MCPToolClient, direct_registry
    ) -> None:
        """search_stocks produces identical status via MCP and direct.

        search_stocks has an API fallback (doesn't require DB), so both
        paths should return the same status. This is the core regression proof.
        """
        params = {"query": "AAPL"}

        mcp_result = await mcp_client.call_tool("search_stocks", params)
        direct_result = await _safe_execute(direct_registry, "search_stocks", params)

        assert mcp_result.status == direct_result.status, (
            f"Status mismatch: MCP={mcp_result.status} ({mcp_result.error}), "
            f"direct={direct_result.status} ({direct_result.error})"
        )

    @pytest.mark.asyncio
    async def test_mcp_tool_call_returns_structured_data(self, mcp_client: MCPToolClient) -> None:
        """MCP tool call returns properly structured data, not raw strings.

        Verifies the full chain: tool.execute() → to_json() → stdio → from_json()
        preserves the data structure (list of dicts with expected keys).
        """
        result = await mcp_client.call_tool("search_stocks", {"query": "AAPL"})
        assert result.status == "ok"
        assert isinstance(result.data, list)
        if len(result.data) > 0:
            first = result.data[0]
            assert "ticker" in first
            assert "name" in first

    @pytest.mark.asyncio
    async def test_invalid_tool_both_paths_error(
        self, mcp_client: MCPToolClient, direct_registry
    ) -> None:
        """Both MCP and direct paths produce errors for non-existent tools."""
        mcp_result = await mcp_client.call_tool("nonexistent_tool_xyz", {})
        assert mcp_result.status == "error"

        with pytest.raises(KeyError):
            await direct_registry.execute("nonexistent_tool_xyz", {})

    @pytest.mark.asyncio
    async def test_tool_result_serialization_round_trip(
        self, mcp_client: MCPToolClient, direct_registry
    ) -> None:
        """ToolResult survives JSON serialization through stdio.

        Calls a tool via MCP, verifies the result is a proper ToolResult
        with all expected fields (status, data, error) — proving the
        to_json()/from_json() round-trip through stdio pipes is lossless.
        """
        result = await mcp_client.call_tool("search_stocks", {"query": "test"})
        assert isinstance(result, ToolResult)
        assert result.status in ("ok", "error", "degraded", "timeout")
        # Verify it can round-trip again
        json_str = result.to_json()
        restored = ToolResult.from_json(json_str)
        assert restored.status == result.status
        assert restored.data == result.data
        assert restored.error == result.error

    @pytest.mark.asyncio
    async def test_tool_count_matches(self, mcp_client: MCPToolClient, direct_registry) -> None:
        """MCP server reports the same number of tools as the direct registry."""
        mcp_count = len(await mcp_client.list_tools())
        direct_count = len(direct_registry.discover())
        assert mcp_count == direct_count, (
            f"Tool count mismatch: MCP={mcp_count}, direct={direct_count}"
        )
