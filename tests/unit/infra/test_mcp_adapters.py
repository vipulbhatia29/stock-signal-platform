"""Tests for MCP adapter base and implementations."""

from unittest.mock import AsyncMock, patch

import pytest

from backend.tools.adapters.base import MCPAdapter
from backend.tools.base import ProxiedTool, ToolResult


def test_mcp_adapter_is_abstract():
    """MCPAdapter cannot be instantiated directly."""
    with pytest.raises(TypeError):
        MCPAdapter()


def test_edgar_adapter_discover():
    """EdgarAdapter discovers expected tools."""
    from backend.tools.adapters.edgar import EdgarAdapter

    adapter = EdgarAdapter()
    tools = adapter.get_tools()
    names = [t.name for t in tools]
    assert "get_10k_section" in names
    assert "get_13f_holdings" in names
    assert "get_insider_trades" in names
    assert "get_8k_events" in names
    assert all(isinstance(t, ProxiedTool) for t in tools)


def test_alpha_vantage_adapter_discover():
    """AlphaVantageAdapter discovers expected tools."""
    from backend.tools.adapters.alpha_vantage import AlphaVantageAdapter

    adapter = AlphaVantageAdapter(api_key="test")
    tools = adapter.get_tools()
    names = [t.name for t in tools]
    assert "get_news_sentiment" in names
    assert "get_quotes" in names
    assert all(isinstance(t, ProxiedTool) for t in tools)


def test_fred_adapter_discover():
    """FredAdapter discovers expected tools."""
    from backend.tools.adapters.fred import FredAdapter

    adapter = FredAdapter(api_key="test")
    tools = adapter.get_tools()
    names = [t.name for t in tools]
    assert "get_economic_series" in names
    assert all(isinstance(t, ProxiedTool) for t in tools)


def test_finnhub_adapter_discover():
    """FinnhubAdapter discovers expected tools."""
    from backend.tools.adapters.finnhub import FinnhubAdapter

    adapter = FinnhubAdapter(api_key="test")
    tools = adapter.get_tools()
    names = [t.name for t in tools]
    assert "get_analyst_ratings" in names
    assert "get_social_sentiment" in names
    assert "get_etf_holdings" in names
    assert "get_esg_scores" in names
    assert "get_supply_chain" in names
    assert all(isinstance(t, ProxiedTool) for t in tools)


def test_adapter_tools_have_correct_categories():
    """All adapter tools have the correct category set."""
    from backend.tools.adapters.alpha_vantage import AlphaVantageAdapter
    from backend.tools.adapters.edgar import EdgarAdapter
    from backend.tools.adapters.finnhub import FinnhubAdapter
    from backend.tools.adapters.fred import FredAdapter

    adapters = [
        (EdgarAdapter(), "sec_filings"),
        (AlphaVantageAdapter(api_key="test"), "market_data"),
        (FredAdapter(api_key="test"), "economic_data"),
        (FinnhubAdapter(api_key="test"), "market_intelligence"),
    ]
    for adapter, expected_category in adapters:
        for tool in adapter.get_tools():
            assert tool.category == expected_category, (
                f"{tool.name} has category {tool.category!r}, expected {expected_category!r}"
            )


@pytest.mark.asyncio
async def test_edgar_adapter_execute_success():
    """EdgarAdapter.execute returns ToolResult on success."""
    from backend.tools.adapters.edgar import EdgarAdapter

    adapter = EdgarAdapter()
    with patch(
        "backend.tools.adapters.edgar.EdgarAdapter._call_edgar",
        new_callable=AsyncMock,
        return_value={"section": "Risk Factors", "text": "Sample risk text..."},
    ):
        result = await adapter.execute("get_10k_section", {"ticker": "AAPL", "section": "1A"})
    assert isinstance(result, ToolResult)
    assert result.status == "ok"


@pytest.mark.asyncio
async def test_adapter_execute_error_handling():
    """Adapters return ToolResult(status='error') on failure, not raise."""
    from backend.tools.adapters.fred import FredAdapter

    adapter = FredAdapter(api_key="test")
    with patch(
        "backend.tools.adapters.fred.FredAdapter._fetch_series",
        new_callable=AsyncMock,
        side_effect=Exception("API down"),
    ):
        result = await adapter.execute("get_economic_series", {"series_ids": ["DFF"]})
    assert isinstance(result, ToolResult)
    assert result.status == "error"
    assert result.error == "External data source unavailable. Please try again later."
