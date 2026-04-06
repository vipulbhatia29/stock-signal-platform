"""FundamentalsTool — read enriched fundamentals from DB (not yfinance at runtime)."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError

from backend.tools.base import BaseTool, CachePolicy, ToolResult

logger = logging.getLogger(__name__)


class FundamentalsInput(BaseModel):
    """Input schema for get_fundamentals tool."""

    ticker: str = Field(description="Stock ticker symbol (e.g., AAPL, PLTR)")


class FundamentalsTool(BaseTool):
    """Get fundamental financial data for a stock.

    Returns valuation ratios, growth rates, margins, and Piotroski F-Score.
    Data is read from the database (materialized during ingestion), not
    fetched from yfinance at runtime.
    """

    name = "get_fundamentals"
    description = (
        "Get fundamental financial data for a stock: P/E, PEG, FCF yield, "
        "debt-to-equity, revenue growth, margins, ROE, market cap, and "
        "Piotroski F-Score. Data comes from the database (refreshed on ingest)."
    )
    category = "data"
    parameters = {
        "type": "object",
        "properties": {
            "ticker": {"type": "string", "description": "Stock ticker symbol"},
        },
        "required": ["ticker"],
    }
    args_schema = FundamentalsInput
    cache_policy = CachePolicy(
        ttl=__import__("datetime").timedelta(hours=1),
        key_fields=["ticker"],
    )
    timeout_seconds = 5.0

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        """Read fundamentals from DB for the given ticker."""
        ticker = str(params.get("ticker", "")).upper().strip()
        if not ticker:
            return ToolResult(status="error", error="Missing required param: ticker")

        try:
            from sqlalchemy import select

            from backend.database import async_session_factory
            from backend.models.stock import Stock

            async with async_session_factory() as session:
                result = await session.execute(select(Stock).where(Stock.ticker == ticker))
                stock = result.scalar_one_or_none()

            if stock is None:
                return ToolResult(
                    status="error",
                    error=f"Ticker '{ticker}' not found in database. Use ingest_stock first.",
                )

            return ToolResult(
                status="ok",
                data={
                    "ticker": stock.ticker,
                    "name": stock.name,
                    "sector": stock.sector,
                    "industry": stock.industry,
                    "market_cap": stock.market_cap,
                    "revenue_growth": stock.revenue_growth,
                    "gross_margins": stock.gross_margins,
                    "operating_margins": stock.operating_margins,
                    "profit_margins": stock.profit_margins,
                    "return_on_equity": stock.return_on_equity,
                },
            )

        except SQLAlchemyError:
            logger.exception("Failed to get fundamentals for %s", ticker)
            return ToolResult(status="error", error="Failed to get fundamentals. Please try again.")
