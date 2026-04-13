"""AnalyzeStockTool — canonical ingest-based stock analysis (Spec C PR2)."""

from __future__ import annotations

import logging
import re
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
    timeout_seconds = 45.0

    async def _run(self, params: dict[str, Any]) -> ToolResult:
        """Run full stock analysis pipeline, auto-ingesting if needed.

        Uses canonical ingest_ticker (idempotent — skips if data is fresh),
        then reloads signals from DB via get_latest_signals. This ensures chat
        and the stock page always agree on signal values.

        Args:
            params: Dict with required key ``ticker`` (stock symbol, 1-5 letters).

        Returns:
            ToolResult with status='ok' and signal data, or status='error'
            with a safe user-facing message.
        """
        ticker = str(params.get("ticker", "")).upper()
        if not ticker:
            return ToolResult(status="error", error="Missing required param: ticker")

        if not re.match(r"^[A-Z]{1,5}$", ticker):
            return ToolResult(
                status="error",
                error="Invalid ticker format. Use 1-5 letters (e.g., AAPL).",
            )

        from backend.database import async_session_factory
        from backend.services.ingest_lock import acquire_ingest_lock, release_ingest_lock
        from backend.services.pipelines import ingest_ticker
        from backend.services.signals import get_latest_signals

        async with async_session_factory() as session:
            # Run canonical ingest (idempotent — skips if data is fresh)
            if await acquire_ingest_lock(ticker):
                try:
                    await ingest_ticker(ticker, session)
                except Exception:
                    logger.warning("Ingest failed for %s in analyze_stock", ticker, exc_info=True)
                finally:
                    await release_ingest_lock(ticker)

            # Reload persisted signals from DB
            snapshot = await get_latest_signals(ticker, session)
            if snapshot is None:
                return ToolResult(
                    status="error",
                    error=f"No analysis data available for {ticker}.",
                )

            return ToolResult(
                status="ok",
                data={
                    "ticker": ticker,
                    "composite_score": snapshot.composite_score,
                    "rsi_value": snapshot.rsi_value,
                    "rsi_signal": snapshot.rsi_signal,
                    "macd_signal": snapshot.macd_signal_label,
                    "sma_signal": snapshot.sma_signal,
                    "bb_position": snapshot.bb_position,
                    "annual_return": snapshot.annual_return,
                    "volatility": snapshot.volatility,
                    "sharpe_ratio": snapshot.sharpe_ratio,
                    "computed_at": (
                        snapshot.computed_at.isoformat() if snapshot.computed_at else None
                    ),
                },
            )
