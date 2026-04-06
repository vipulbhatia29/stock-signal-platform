"""IngestStockTool — fetch prices, signals, and fundamentals for any ticker."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from pydantic import BaseModel, Field

from backend.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

_TICKER_RE = re.compile(r"^[A-Za-z0-9.\-]{1,10}$")


class IngestStockInput(BaseModel):
    """Input schema for ingest_stock tool."""

    ticker: str = Field(description="Stock ticker symbol to ingest (e.g., PLTR, AAPL)")


class IngestStockTool(BaseTool):
    """Ingest a stock into the platform — fetch prices, compute signals, get fundamentals.

    Works for both new stocks (full 10Y history) and existing stocks (delta update).
    After ingestion, the stock is available for analysis, recommendations, and screening.
    """

    name = "ingest_stock"
    description = (
        "Fetch price history, compute technical signals, and get fundamentals for a ticker. "
        "Use this when a stock isn't in the database yet, or to refresh stale data. "
        "After ingestion, analyze_stock and get_recommendations will work for this ticker."
    )
    category = "data"
    parameters = {
        "type": "object",
        "properties": {
            "ticker": {"type": "string", "description": "Stock ticker symbol (e.g., PLTR)"},
        },
        "required": ["ticker"],
    }
    args_schema = IngestStockInput
    timeout_seconds = 30.0

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        """Ingest a ticker: ensure stock exists, fetch prices, compute signals."""
        ticker = str(params.get("ticker", "")).upper().strip()
        if not ticker or not _TICKER_RE.match(ticker):
            return ToolResult(status="error", error="Invalid ticker format")

        try:
            from backend.database import async_session_factory
            from backend.tools.fundamentals import (
                fetch_analyst_data,
                fetch_earnings_history,
                fetch_fundamentals,
                persist_earnings_snapshots,
                persist_enriched_fundamentals,
            )
            from backend.tools.market_data import (
                ensure_stock_exists,
                fetch_prices_delta,
                load_prices_df,
                update_last_fetched_at,
            )
            from backend.tools.signals import compute_signals, store_signal_snapshot

            async with async_session_factory() as session:
                # 1. Ensure stock record exists (creates from yfinance if needed)
                try:
                    stock = await ensure_stock_exists(ticker, session)
                except ValueError:
                    return ToolResult(
                        status="error",
                        error=f"Ticker '{ticker}' not found. Check the symbol and try again.",
                    )

                is_new = stock.last_fetched_at is None

                # 2. Fetch price data (full 10Y for new, delta for existing)
                try:
                    delta_df = await fetch_prices_delta(ticker, session)
                except ValueError:
                    logger.exception("Failed to fetch price delta for %s", ticker)
                    return ToolResult(
                        status="error",
                        error=f"Failed to fetch price data for {ticker}. Please try again.",
                    )

                rows_fetched = len(delta_df) if not delta_df.empty else 0

                # 3. Load full history for signal computation
                full_df = await load_prices_df(ticker, session)

                # 4. Fetch fundamentals (synchronous — run in executor)
                loop = asyncio.get_event_loop()
                fundamentals = await loop.run_in_executor(None, fetch_fundamentals, ticker)
                piotroski = fundamentals.piotroski_score

                # 4b. Persist enriched fundamentals + analyst data
                analyst_data = await loop.run_in_executor(None, fetch_analyst_data, ticker)
                await persist_enriched_fundamentals(stock, fundamentals, analyst_data, session)

                # 4c. Persist earnings history
                earnings = await loop.run_in_executor(None, fetch_earnings_history, ticker)
                await persist_earnings_snapshots(ticker, earnings, session)

                # 4d. Sync dividend history
                try:
                    from backend.tools.dividends import fetch_dividends, store_dividends

                    dividends = await loop.run_in_executor(None, fetch_dividends, ticker)
                    if dividends:
                        await store_dividends(ticker, dividends, session)
                except Exception:
                    logger.warning("Failed to sync dividends for %s", ticker)

                # 5. Compute and store signals
                composite_score = None
                if not full_df.empty:
                    signal_result = compute_signals(ticker, full_df, piotroski_score=piotroski)
                    if signal_result.composite_score is not None:
                        await store_signal_snapshot(signal_result, session)
                        composite_score = signal_result.composite_score

                await update_last_fetched_at(ticker, session)
                await session.commit()

                return ToolResult(
                    status="ok",
                    data={
                        "ticker": ticker,
                        "name": stock.name,
                        "rows_fetched": rows_fetched,
                        "composite_score": composite_score,
                        "status": "created" if is_new else "updated",
                        "piotroski_score": piotroski,
                    },
                )

        except Exception:
            logger.exception("Failed to ingest stock %s", ticker)
            return ToolResult(status="error", error=f"Failed to ingest {ticker}")
