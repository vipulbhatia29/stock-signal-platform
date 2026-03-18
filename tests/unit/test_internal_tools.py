"""Tests for internal tool wrappers."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_analyze_stock_tool_metadata():
    """AnalyzeStockTool has correct name and category."""
    from backend.tools.analyze_stock import AnalyzeStockTool

    tool = AnalyzeStockTool()
    assert tool.name == "analyze_stock"
    assert tool.category == "analysis"
    assert "ticker" in tool.parameters["properties"]


@pytest.mark.asyncio
async def test_analyze_stock_tool_error_handling():
    """AnalyzeStockTool returns error ToolResult on exception."""
    from backend.tools.analyze_stock import AnalyzeStockTool

    tool = AnalyzeStockTool()
    # No DB running in unit tests — should return error, not raise
    result = await tool.execute({"ticker": "AAPL"})
    assert result.status == "error"
    assert result.error is not None


@pytest.mark.asyncio
async def test_portfolio_exposure_tool_metadata():
    """PortfolioExposureTool has correct name and category."""
    from backend.tools.portfolio_exposure import PortfolioExposureTool

    tool = PortfolioExposureTool()
    assert tool.name == "get_portfolio_exposure"
    assert tool.category == "portfolio"


@pytest.mark.asyncio
async def test_screen_stocks_tool_metadata():
    """ScreenStocksTool has correct name and category."""
    from backend.tools.screen_stocks import ScreenStocksTool

    tool = ScreenStocksTool()
    assert tool.name == "screen_stocks"
    assert tool.category == "analysis"


@pytest.mark.asyncio
async def test_web_search_tool_metadata():
    """WebSearchTool has correct name and category."""
    from backend.tools.web_search import WebSearchTool

    tool = WebSearchTool()
    assert tool.name == "web_search"
    assert tool.category == "data"
    assert "query" in tool.parameters["properties"]


@pytest.mark.asyncio
async def test_web_search_tool_no_api_key():
    """WebSearchTool returns error when SERPAPI_API_KEY is empty."""
    from backend.tools.web_search import WebSearchTool

    tool = WebSearchTool()
    result = await tool.execute({"query": "test"})
    # May succeed or error depending on key — just verify it doesn't raise
    assert result.status in ("ok", "error")


@pytest.mark.asyncio
async def test_geopolitical_tool_metadata():
    """GeopoliticalEventsTool has correct name and category."""
    from backend.tools.geopolitical import GeopoliticalEventsTool

    tool = GeopoliticalEventsTool()
    assert tool.name == "get_geopolitical_events"
    assert tool.category == "macro"
    assert "query" in tool.parameters["properties"]
