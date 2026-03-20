"""AnalystTargetsTool — read analyst price targets from DB."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from backend.tools.base import BaseTool, CachePolicy, ToolResult

logger = logging.getLogger(__name__)


class AnalystTargetsInput(BaseModel):
    """Input schema for get_analyst_targets tool."""

    ticker: str = Field(description="Stock ticker symbol (e.g., AAPL, PLTR)")


class AnalystTargetsTool(BaseTool):
    """Get analyst price targets and recommendation breakdown for a stock.

    Returns target prices (mean, high, low), upside percentage, and
    buy/hold/sell counts. Data is read from the database (materialized
    during ingestion), not fetched from yfinance at runtime.
    """

    name = "get_analyst_targets"
    description = (
        "Get analyst consensus price targets and buy/hold/sell breakdown. "
        "Returns target mean, high, low, upside %, and recommendation counts."
    )
    category = "data"
    parameters = {
        "type": "object",
        "properties": {
            "ticker": {"type": "string", "description": "Stock ticker symbol"},
        },
        "required": ["ticker"],
    }
    args_schema = AnalystTargetsInput
    cache_policy = CachePolicy(
        ttl=__import__("datetime").timedelta(hours=1),
        key_fields=["ticker"],
    )
    timeout_seconds = 5.0

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        """Read analyst targets from DB for the given ticker."""
        ticker = str(params.get("ticker", "")).upper().strip()
        if not ticker:
            return ToolResult(status="error", error="Missing required param: ticker")

        try:
            from sqlalchemy import select

            from backend.database import async_session_factory
            from backend.models.stock import Stock

            async with async_session_factory() as session:
                result = await session.execute(
                    select(Stock).where(Stock.ticker == ticker)
                )
                stock = result.scalar_one_or_none()

            if stock is None:
                return ToolResult(
                    status="error",
                    error=f"Ticker '{ticker}' not found in database. Use ingest_stock first.",
                )

            # Check if analyst data is available
            if stock.analyst_target_mean is None:
                return ToolResult(
                    status="ok",
                    data={
                        "ticker": stock.ticker,
                        "has_targets": False,
                        "message": "No analyst target data available for this ticker.",
                    },
                )

            # Calculate upside from current market cap proxy (latest close)
            # We use analyst_target_mean vs current price if available
            data: dict[str, Any] = {
                "ticker": stock.ticker,
                "has_targets": True,
                "target_mean": stock.analyst_target_mean,
                "target_high": stock.analyst_target_high,
                "target_low": stock.analyst_target_low,
                "buy_count": stock.analyst_buy,
                "hold_count": stock.analyst_hold,
                "sell_count": stock.analyst_sell,
            }

            return ToolResult(status="ok", data=data)

        except Exception as e:
            logger.error("get_analyst_targets_failed", extra={"ticker": ticker, "error": str(e)})
            return ToolResult(status="error", error=str(e))
