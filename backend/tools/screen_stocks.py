"""ScreenStocksTool — stock screener with signal and sector filters."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from backend.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class ScreenStocksInput(BaseModel):
    """Input schema for screen_stocks tool."""

    min_score: float | None = Field(default=None, description="Minimum composite score (0-10)")
    sector: str | None = Field(default=None, description="Filter by sector (e.g., Technology)")
    rsi_state: str | None = Field(
        default=None, description="RSI state: oversold, neutral, overbought"
    )
    limit: int = Field(default=20, description="Max results (default 20)")


class ScreenStocksTool(BaseTool):
    """Screen stocks by score, sector, and signal filters."""

    name = "screen_stocks"
    description = (
        "Screen stocks using filters: minimum composite score, sector, "
        "RSI state (oversold/neutral/overbought), and MACD state (bullish/bearish). "
        "Returns top matches sorted by composite score."
    )
    category = "analysis"
    parameters = {
        "type": "object",
        "properties": {
            "min_score": {"type": "number", "description": "Minimum composite score (0-10)"},
            "sector": {"type": "string", "description": "Filter by sector (e.g., Technology)"},
            "rsi_state": {
                "type": "string",
                "description": "RSI state: oversold, neutral, overbought",
            },
            "limit": {"type": "integer", "description": "Max results (default 20)", "default": 20},
        },
    }
    args_schema = ScreenStocksInput
    timeout_seconds = 10.0

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        """Run stock screener query."""
        try:
            from sqlalchemy import desc, select

            from backend.database import async_session_factory
            from backend.models.signal import SignalSnapshot

            limit = params.get("limit", 20)
            async with async_session_factory() as session:
                query = (
                    select(SignalSnapshot)
                    .order_by(desc(SignalSnapshot.composite_score))
                    .limit(limit)
                )
                if params.get("min_score"):
                    query = query.where(SignalSnapshot.composite_score >= params["min_score"])
                if params.get("rsi_state"):
                    query = query.where(SignalSnapshot.rsi_signal == params["rsi_state"])

                result = await session.execute(query)
                rows = result.scalars().all()
                return ToolResult(
                    status="ok",
                    data=[
                        {
                            "ticker": r.ticker,
                            "composite_score": r.composite_score,
                            "rsi_signal": r.rsi_signal,
                            "macd_signal": r.macd_signal_label,
                        }
                        for r in rows
                    ],
                )
        except Exception:
            logger.exception("Failed to screen stocks")
            return ToolResult(status="error", error="Stock screening failed. Please try again.")
