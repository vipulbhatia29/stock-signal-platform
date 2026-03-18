"""AnalyzeStockTool — complete stock analysis combining technicals + fundamentals."""

from __future__ import annotations

import logging
from typing import Any

from backend.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class AnalyzeStockTool(BaseTool):
    """Analyze a stock: technicals, fundamentals, and recommendation."""

    name = "analyze_stock"
    description = (
        "Analyze a stock ticker: compute technical signals (RSI, MACD, SMA, Bollinger), "
        "fundamental metrics (P/E, Piotroski), and generate a composite score with recommendation."
    )
    category = "analysis"
    parameters = {
        "type": "object",
        "properties": {
            "ticker": {"type": "string", "description": "Stock ticker symbol (e.g., AAPL)"},
        },
        "required": ["ticker"],
    }
    timeout_seconds = 15.0

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        """Run full stock analysis pipeline."""
        ticker = params["ticker"].upper()
        try:
            from backend.database import async_session_factory
            from backend.tools.signals import compute_signals

            async with async_session_factory() as session:
                signals = await compute_signals(session, ticker)
                return ToolResult(
                    status="ok",
                    data={
                        "ticker": ticker,
                        "composite_score": signals.composite_score,
                        "rsi": {"value": signals.rsi.value, "signal": signals.rsi.signal},
                        "macd": {"value": signals.macd.value, "signal": signals.macd.signal},
                        "sma": {"signal": signals.sma.signal},
                        "bollinger": {"position": signals.bb.position},
                        "annual_return": signals.annual_return,
                        "volatility": signals.volatility,
                        "sharpe_ratio": signals.sharpe_ratio,
                    },
                )
        except Exception as e:
            logger.error("analyze_stock_failed", extra={"ticker": ticker, "error": str(e)})
            return ToolResult(status="error", error=str(e))
