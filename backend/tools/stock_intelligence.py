"""Stock intelligence agent tool — wraps intelligence.py functions for agent use."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from pydantic import BaseModel, Field

from backend.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class StockIntelligenceInput(BaseModel):
    """Input schema for stock intelligence tool."""

    ticker: str = Field(..., description="Stock ticker symbol")


class StockIntelligenceTool(BaseTool):
    """Get analyst upgrades, insider, earnings, EPS revisions, short interest.

    Wraps the intelligence.py fetch functions into a single agent-callable tool.
    """

    name = "get_stock_intelligence"
    description = (
        "Get recent analyst upgrades/downgrades, insider transactions, "
        "upcoming earnings date, EPS revisions, and short interest for a stock. "
        "Use when the user asks about analyst sentiment, insider activity, "
        "short selling pressure, or upcoming catalysts."
    )
    category = "data"
    parameters = {
        "type": "object",
        "properties": {
            "ticker": {"type": "string", "description": "Stock ticker symbol"},
        },
        "required": ["ticker"],
    }
    args_schema = StockIntelligenceInput
    timeout_seconds = 15.0

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        """Execute intelligence data fetch for a ticker."""
        ticker = str(params.get("ticker", "")).upper().strip()
        if not ticker:
            return ToolResult(status="error", error="Ticker is required")

        try:
            from backend.tools.intelligence import (
                fetch_eps_revisions,
                fetch_insider_transactions,
                fetch_next_earnings_date,
                fetch_short_interest,
                fetch_upgrades_downgrades,
            )

            upgrades, insider, earnings, eps, short = await asyncio.gather(
                asyncio.to_thread(fetch_upgrades_downgrades, ticker),
                asyncio.to_thread(fetch_insider_transactions, ticker),
                asyncio.to_thread(fetch_next_earnings_date, ticker),
                asyncio.to_thread(fetch_eps_revisions, ticker),
                asyncio.to_thread(fetch_short_interest, ticker),
            )

            return ToolResult(
                status="ok",
                data={
                    "ticker": ticker,
                    "upgrades_downgrades": upgrades,
                    "insider_transactions": insider,
                    "next_earnings_date": earnings,
                    "eps_revisions": eps,
                    "short_interest": short,
                },
            )
        except Exception as e:
            logger.error(
                "stock_intelligence_failed",
                extra={"ticker": ticker, "error": str(e)},
            )
            return ToolResult(
                status="error",
                error=f"Failed to fetch intelligence for {ticker}",
            )
