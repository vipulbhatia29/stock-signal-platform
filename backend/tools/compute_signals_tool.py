"""ComputeSignalsTool — wraps existing compute_signals function as BaseTool."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from backend.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class ComputeSignalsInput(BaseModel):
    """Input schema for compute_signals tool."""

    ticker: str = Field(description="Stock ticker symbol (e.g., AAPL)")


class ComputeSignalsTool(BaseTool):
    """Compute technical signals for a stock ticker."""

    name = "compute_signals"
    description = (
        "Compute technical signals for a ticker: RSI, MACD, SMA crossover, "
        "Bollinger Bands, annualized return, volatility, Sharpe ratio, and composite score."
    )
    category = "data"
    parameters = {
        "type": "object",
        "properties": {
            "ticker": {"type": "string", "description": "Stock ticker symbol (e.g., AAPL)"},
        },
        "required": ["ticker"],
    }
    args_schema = ComputeSignalsInput
    timeout_seconds = 10.0

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        """Compute signals for the given ticker."""
        ticker = str(params.get("ticker", "")).upper()
        if not ticker:
            return ToolResult(status="error", error="Missing required param: ticker")
        try:
            from backend.database import async_session_factory
            from backend.tools.market_data import load_prices_df
            from backend.tools.signals import compute_signals

            async with async_session_factory() as session:
                df = await load_prices_df(ticker, session)
                if df.empty:
                    return ToolResult(
                        status="error",
                        error=f"No price data for {ticker}. Ingest it first.",
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
            logger.error("compute_signals_failed", extra={"ticker": ticker, "error": str(e)})
            return ToolResult(status="error", error=str(e))
