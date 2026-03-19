"""RecommendationsTool — wraps existing generate_recommendation function as BaseTool."""

from __future__ import annotations

import logging
from typing import Any

from backend.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


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
    timeout_seconds = 15.0

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        """Compute signals then generate recommendation."""
        ticker = params["ticker"].upper()
        try:
            from backend.database import async_session_factory
            from backend.tools.recommendations import generate_recommendation
            from backend.tools.signals import compute_signals

            async with async_session_factory() as session:
                signals = await compute_signals(session, ticker)
                rec = generate_recommendation(
                    signal=signals,
                    current_price=0.0,  # Price context not available here
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
            return ToolResult(status="error", error=str(e))
