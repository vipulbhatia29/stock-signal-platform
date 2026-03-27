"""RecommendationsTool — wraps existing generate_recommendation function as BaseTool."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from backend.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class RecommendationsInput(BaseModel):
    """Input schema for get_recommendations tool."""

    ticker: str = Field(description="Stock ticker symbol")


class RecommendationsTool(BaseTool):
    """Get investment recommendation for a stock ticker."""

    name = "get_recommendations"
    description = (
        "Generate an investment recommendation (BUY/WATCH/AVOID/HOLD/SELL) "
        "for a ticker. Computes signals first, then applies decision rules."
    )
    category = "portfolio"
    parameters = {
        "type": "object",
        "properties": {
            "ticker": {"type": "string", "description": "Stock ticker symbol"},
        },
        "required": ["ticker"],
    }
    args_schema = RecommendationsInput
    timeout_seconds = 15.0

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        """Compute signals then generate recommendation."""
        ticker = params.get("ticker", "").upper()
        if not ticker:
            return ToolResult(status="error", error="Missing required param: ticker")
        try:
            from backend.database import async_session_factory
            from backend.tools.market_data import get_latest_price, load_prices_df
            from backend.tools.recommendations import generate_recommendation
            from backend.tools.signals import compute_signals

            async with async_session_factory() as session:
                df = await load_prices_df(ticker, session)
                if df.empty:
                    return ToolResult(
                        status="error",
                        error=f"No price data for {ticker}. Ingest it first.",
                    )
                signals = compute_signals(ticker, df)
                current_price = await get_latest_price(ticker, session) or 0.0
                rec = generate_recommendation(
                    signal=signals,
                    current_price=current_price,
                )
                return ToolResult(
                    status="ok",
                    data={
                        "ticker": ticker,
                        "action": rec.action.value,
                        "confidence": rec.confidence.value,
                        "composite_score": rec.composite_score,
                        "reasoning": rec.reasoning,
                    },
                )
        except Exception as e:
            logger.error("recommendations_failed", extra={"ticker": ticker, "error": str(e)})
            return ToolResult(
                status="error",
                error="Recommendation generation failed. Please try again.",
            )
