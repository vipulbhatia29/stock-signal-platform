"""Tests for observability MCP tool registration."""

from __future__ import annotations

import asyncio

from backend.mcp_server.observability_tools import create_obs_mcp_app


class TestObsMcpRegistry:
    def test_creates_mcp_app(self) -> None:
        """Test that create_obs_mcp_app returns a FastMCP instance."""
        app = create_obs_mcp_app()
        assert app is not None

    def test_registers_13_tools(self) -> None:
        """Test that exactly 13 observability tools are registered."""
        app = create_obs_mcp_app()
        tools = asyncio.run(app.list_tools())
        assert len(tools) == 13

    def test_tool_names(self) -> None:
        """Test that all expected tool names are registered."""
        app = create_obs_mcp_app()
        tools = asyncio.run(app.list_tools())
        expected_names = {
            "describe_observability_schema",
            "get_platform_health",
            "get_trace",
            "get_recent_errors",
            "get_anomalies",
            "get_external_api_stats",
            "get_dq_findings",
            "diagnose_pipeline",
            "get_slow_queries",
            "get_cost_breakdown",
            "search_errors",
            "get_deploys",
            "get_observability_health",
        }
        tool_names = {t.name for t in tools}
        assert tool_names == expected_names
