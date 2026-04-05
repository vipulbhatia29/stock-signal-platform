"""AnalyzeStockTool — complete stock analysis combining technicals + fundamentals."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from backend.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class AnalyzeStockInput(BaseModel):
    """Input schema for analyze_stock tool."""

    ticker: str = Field(description="Stock ticker symbol (e.g., AAPL)")


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
    args_schema = AnalyzeStockInput
    timeout_seconds = 15.0

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        """Run full stock analysis pipeline, auto-ingesting if needed."""
        import re

        ticker = str(params.get("ticker", "")).upper()
        if not ticker:
            return ToolResult(status="error", error="Missing required param: ticker")

        # Validate ticker format (1-5 uppercase letters)
        if not re.match(r"^[A-Z]{1,5}$", ticker):
            return ToolResult(
                status="error",
                error="Invalid ticker format. Use 1-5 letters (e.g., AAPL).",
            )

        try:
            from backend.database import async_session_factory
            from backend.tools.market_data import load_prices_df
            from backend.tools.signals import compute_signals

            async with async_session_factory() as session:
                df = await load_prices_df(ticker, session)

                if df.empty:
                    # Auto-ingest: lightweight path (stock record + prices only)
                    from backend.services.stock_data import ensure_stock_exists, fetch_prices_delta

                    try:
                        await ensure_stock_exists(ticker, session)
                        await fetch_prices_delta(ticker, session)
                        await session.commit()
                    except Exception:
                        logger.warning("Auto-ingest failed for %s", ticker, exc_info=True)
                        return ToolResult(
                            status="error",
                            error=f"No data available for {ticker}. Verify the ticker is correct.",
                        )

                    df = await load_prices_df(ticker, session)
                    if df.empty:
                        return ToolResult(
                            status="error",
                            error=f"No price data available for {ticker} after ingestion.",
                        )

                signals = compute_signals(ticker, df)
                return ToolResult(
                    status="ok",
                    data={
                        "ticker": ticker,
                        "composite_score": signals.composite_score,
                        "rsi_value": signals.rsi_value,
                        "rsi_signal": signals.rsi_signal,
                        "macd_value": signals.macd_value,
                        "macd_signal": signals.macd_signal_label,
                        "sma_signal": signals.sma_signal,
                        "bb_position": signals.bb_position,
                        "annual_return": signals.annual_return,
                        "volatility": signals.volatility,
                        "sharpe_ratio": signals.sharpe_ratio,
                    },
                )
        except Exception as e:
            logger.error("analyze_stock_failed", extra={"ticker": ticker, "error": str(e)})
            return ToolResult(status="error", error="Stock analysis failed. Please try again.")
