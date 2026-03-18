"""ComputeSignalsTool — wraps existing compute_signals function as BaseTool."""

from __future__ import annotations

import logging
from typing import Any

from backend.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


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
    timeout_seconds = 10.0

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        """Compute signals for the given ticker."""
        ticker = params["ticker"].upper()
        try:
            from backend.database import async_session_factory
            from backend.tools.signals import compute_signals

            async with async_session_factory() as session:
                signals = compute_signals(session, ticker)
                return ToolResult(
                    status="ok",
                    data={
                        "ticker": ticker,
                        "composite_score": signals.composite_score,
                        "rsi_value": signals.rsi.value,
                        "rsi_signal": signals.rsi.signal,
                        "macd_value": signals.macd.value,
                        "macd_signal": signals.macd.signal,
                        "sma_signal": signals.sma.signal,
                        "bb_position": signals.bb.position,
                        "annual_return": signals.annual_return,
                        "volatility": signals.volatility,
                        "sharpe_ratio": signals.sharpe_ratio,
                    },
                )
        except Exception as e:
            logger.error("compute_signals_failed", extra={"ticker": ticker, "error": str(e)})
            return ToolResult(status="error", error=str(e))
