"""Tool hardening tests — ToolResult format, args_schema, error handling."""

import asyncio

import pytest

from backend.tools.base import BaseTool, ToolFilter, ToolInfo, ToolResult
from backend.tools.registry import ToolRegistry

# ---------------------------------------------------------------------------
# Fake tools for testing
# ---------------------------------------------------------------------------


class SuccessTool(BaseTool):
    """Tool that always succeeds."""

    name = "success_tool"
    description = "Always succeeds"
    category = "test"
    parameters = {"type": "object", "properties": {"ticker": {"type": "string"}}}
    timeout_seconds = 5.0

    async def _run(self, params):
        """Return a successful ToolResult."""
        return ToolResult(status="ok", data={"ticker": params.get("ticker", "TST")})


class ErrorTool(BaseTool):
    """Tool that always returns an error ToolResult."""

    name = "error_tool"
    description = "Always errors"
    category = "test"
    parameters = {"type": "object", "properties": {}}
    timeout_seconds = 5.0

    async def _run(self, params):
        """Return an error ToolResult without raising."""
        return ToolResult(status="error", error="Something went wrong")


class SlowTool(BaseTool):
    """Tool that takes too long."""

    name = "slow_tool"
    description = "Very slow"
    category = "test"
    parameters = {"type": "object", "properties": {}}
    timeout_seconds = 0.1  # Very short timeout

    async def _run(self, params):
        """Sleep longer than timeout."""
        await asyncio.sleep(5)
        return ToolResult(status="ok", data={})


class ExceptionTool(BaseTool):
    """Tool that raises an exception, caught by BaseTool.execute()."""

    name = "exception_tool"
    description = "Raises exception"
    category = "test"
    parameters = {"type": "object", "properties": {}}
    timeout_seconds = 5.0

    async def _run(self, params):
        """Raise an unexpected exception."""
        raise RuntimeError("Unexpected crash")


# ===========================================================================
# ToolResult format tests
# ===========================================================================


class TestToolResultFormat:
    """ToolResult dataclass correctness."""

    def test_ok_result_has_data(self):
        """OK ToolResult stores data and has no error."""
        result = ToolResult(status="ok", data={"price": 150.0})
        assert result.status == "ok"
        assert result.data["price"] == 150.0
        assert result.error is None

    def test_error_result_has_message(self):
        """Error ToolResult has error message and no data."""
        result = ToolResult(status="error", error="Not found")
        assert result.status == "error"
        assert result.error == "Not found"
        assert result.data is None

    def test_degraded_result(self):
        """Degraded ToolResult can have partial data."""
        result = ToolResult(status="degraded", data={"partial": True}, error="Stale data")
        assert result.status == "degraded"
        assert result.data is not None
        assert result.error is not None

    def test_timeout_result(self):
        """Timeout ToolResult status."""
        result = ToolResult(status="timeout", error="Tool timed out after 10s")
        assert result.status == "timeout"


# ===========================================================================
# Tool execution via registry
# ===========================================================================


class TestToolExecution:
    """Registry-based tool execution."""

    @pytest.mark.asyncio
    async def test_successful_tool_execution(self):
        """Registry executes a tool and returns its result."""
        registry = ToolRegistry()
        registry.register(SuccessTool())
        result = await registry.execute("success_tool", {"ticker": "AAPL"})
        assert result.status == "ok"
        assert result.data["ticker"] == "AAPL"

    @pytest.mark.asyncio
    async def test_error_tool_returns_result_not_raises(self):
        """Tools that error should return ToolResult, not raise exceptions."""
        registry = ToolRegistry()
        registry.register(ErrorTool())
        result = await registry.execute("error_tool", {})
        assert result.status == "error"
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_timeout_enforced(self):
        """Registry enforces tool timeout."""
        registry = ToolRegistry()
        registry.register(SlowTool())
        with pytest.raises(asyncio.TimeoutError):
            await registry.execute("slow_tool", {})

    @pytest.mark.asyncio
    async def test_unknown_tool_raises_key_error(self):
        """Requesting unknown tool raises KeyError."""
        registry = ToolRegistry()
        with pytest.raises(KeyError):
            await registry.execute("nonexistent_tool", {})


# ===========================================================================
# Tool metadata
# ===========================================================================


class TestToolMetadata:
    """Tool info and schema generation."""

    def test_tool_info_fields(self):
        """ToolInfo has name, description, category, parameters."""
        tool = SuccessTool()
        info = tool.info()
        assert isinstance(info, ToolInfo)
        assert info.name == "success_tool"
        assert info.category == "test"

    def test_tool_filter_matches(self):
        """ToolFilter correctly matches categories."""
        f = ToolFilter(categories=["analysis", "test"])
        info = SuccessTool().info()
        assert f.matches(info) is True

    def test_tool_filter_excludes(self):
        """ToolFilter excludes non-matching categories."""
        f = ToolFilter(categories=["portfolio"])
        info = SuccessTool().info()
        assert f.matches(info) is False

    def test_discover_returns_all_tools(self):
        """discover() returns metadata for all registered tools."""
        registry = ToolRegistry()
        registry.register(SuccessTool())
        registry.register(ErrorTool())
        infos = registry.discover()
        assert len(infos) == 2
        names = {i.name for i in infos}
        assert names == {"success_tool", "error_tool"}

    def test_by_category_filters(self):
        """by_category() returns only tools in specified categories."""
        registry = ToolRegistry()
        registry.register(SuccessTool())  # category="test"
        tools = registry.by_category("test")
        assert len(tools) == 1
        assert tools[0].name == "success_tool"

    def test_health_returns_all_true(self):
        """health() returns True for all registered tools."""
        registry = ToolRegistry()
        registry.register(SuccessTool())
        registry.register(ErrorTool())
        health = registry.health()
        assert all(v is True for v in health.values())
        assert len(health) == 2


# ===========================================================================
# Internal tool metadata checks
# ===========================================================================


class TestInternalToolMetadata:
    """Verify real internal tools have correct metadata."""

    def test_analyze_stock_tool_metadata(self):
        """AnalyzeStockTool has correct name and category."""
        from backend.tools.analyze_stock import AnalyzeStockTool

        tool = AnalyzeStockTool()
        assert tool.name == "analyze_stock"
        assert tool.category == "analysis"
        assert "ticker" in str(tool.parameters)

    def test_search_stocks_tool_metadata(self):
        """SearchStocksTool has correct name and category."""
        from backend.tools.search_stocks_tool import SearchStocksTool

        tool = SearchStocksTool()
        assert tool.name == "search_stocks"
        assert tool.category == "data"

    def test_all_tools_have_description(self):
        """Every internal tool has a non-empty description."""
        from backend.tools.analyze_stock import AnalyzeStockTool
        from backend.tools.search_stocks_tool import SearchStocksTool

        for ToolClass in [AnalyzeStockTool, SearchStocksTool]:
            tool = ToolClass()
            assert len(tool.description) > 10, f"{tool.name} has empty description"
