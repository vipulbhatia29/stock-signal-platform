"""Registry builder — creates a fully populated ToolRegistry.

Extracted from main.py lifespan so both the FastAPI app and the MCP stdio
tool server can share the same registration logic.
"""

from __future__ import annotations

import logging

from backend.config import settings
from backend.tools.adapters.alpha_vantage import AlphaVantageAdapter
from backend.tools.adapters.edgar import EdgarAdapter
from backend.tools.adapters.finnhub import FinnhubAdapter
from backend.tools.adapters.fred import FredAdapter
from backend.tools.analyst_targets_tool import AnalystTargetsTool
from backend.tools.analyze_stock import AnalyzeStockTool
from backend.tools.company_profile_tool import CompanyProfileTool
from backend.tools.compute_signals_tool import ComputeSignalsTool
from backend.tools.dividend_sustainability import DividendSustainabilityTool
from backend.tools.earnings_history_tool import EarningsHistoryTool
from backend.tools.forecast_tools import (
    CompareStocksTool,
    GetForecastTool,
    GetPortfolioForecastTool,
    GetSectorForecastTool,
)
from backend.tools.fundamentals_tool import FundamentalsTool
from backend.tools.geopolitical import GeopoliticalEventsTool
from backend.tools.ingest_stock_tool import IngestStockTool
from backend.tools.portfolio_exposure import PortfolioExposureTool
from backend.tools.recommendations_tool import RecommendationsTool
from backend.tools.registry import ToolRegistry
from backend.tools.risk_narrative import RiskNarrativeTool
from backend.tools.scorecard_tool import GetRecommendationScorecardTool
from backend.tools.screen_stocks import ScreenStocksTool
from backend.tools.search_stocks_tool import SearchStocksTool
from backend.tools.web_search import WebSearchTool

logger = logging.getLogger(__name__)

# All internal tool classes, in registration order.
INTERNAL_TOOL_CLASSES: list[type] = [
    AnalyzeStockTool,
    PortfolioExposureTool,
    ScreenStocksTool,
    ComputeSignalsTool,
    RecommendationsTool,
    WebSearchTool,
    GeopoliticalEventsTool,
    SearchStocksTool,
    IngestStockTool,
    FundamentalsTool,
    AnalystTargetsTool,
    EarningsHistoryTool,
    CompanyProfileTool,
    GetForecastTool,
    GetSectorForecastTool,
    GetPortfolioForecastTool,
    CompareStocksTool,
    GetRecommendationScorecardTool,
    DividendSustainabilityTool,
    RiskNarrativeTool,
]


def build_registry() -> ToolRegistry:
    """Build a ToolRegistry with all internal tools and MCP adapters.

    Creates and returns a fully populated registry containing:
    - 20 internal tools (analysis, screening, forecasting, etc.)
    - 4 MCP adapter tools (Edgar, Alpha Vantage, FRED, Finnhub)

    Returns:
        A ToolRegistry instance with all tools registered.
    """
    registry = ToolRegistry()

    # 1. Internal tools
    for tool_cls in INTERNAL_TOOL_CLASSES:
        registry.register(tool_cls())

    # 2. MCP adapter tools — 4 external data sources
    for adapter in [
        EdgarAdapter(),
        AlphaVantageAdapter(api_key=settings.ALPHA_VANTAGE_API_KEY or ""),
        FredAdapter(api_key=settings.FRED_API_KEY or ""),
        FinnhubAdapter(api_key=settings.FINNHUB_API_KEY or ""),
    ]:
        registry.register_mcp(adapter)

    logger.info("ToolRegistry built: %d tools registered", len(registry.discover()))
    return registry
