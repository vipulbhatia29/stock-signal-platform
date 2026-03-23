"""GetRecommendationScorecard agent tool — wraps compute_scorecard()."""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from pydantic import BaseModel, Field

from backend.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class ScorecardInput(BaseModel):
    """Input schema for get_recommendation_scorecard tool."""

    user_id: str = Field(description="User UUID (auto-injected by executor)")


class GetRecommendationScorecardTool(BaseTool):
    """Get the user's recommendation scorecard.

    Shows hit rate, alpha, buy/sell breakdown, worst miss, and
    per-horizon performance based on evaluated recommendation outcomes.
    """

    name = "get_recommendation_scorecard"
    description = (
        "Get recommendation scorecard: overall hit rate, average alpha, "
        "buy/sell breakdown, worst miss, and per-horizon performance. "
        "Shows how accurate past BUY/SELL recommendations have been."
    )
    category = "portfolio"
    parameters = {
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "User UUID (auto-injected)",
            },
        },
        "required": ["user_id"],
    }
    args_schema: ClassVar[type[BaseModel] | None] = ScorecardInput
    timeout_seconds = 10.0

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        """Compute and return the recommendation scorecard."""
        import uuid as uuid_mod

        user_id_str = str(params.get("user_id", "")).strip()
        if not user_id_str:
            return ToolResult(status="error", error="Missing required param: user_id")

        try:
            user_id = uuid_mod.UUID(user_id_str)
        except ValueError:
            return ToolResult(status="error", error="Invalid user_id format")

        try:
            from backend.database import async_session_factory
            from backend.tools.scorecard import compute_scorecard

            async with async_session_factory() as session:
                scorecard = await compute_scorecard(user_id, session)

            if scorecard.total_outcomes == 0:
                return ToolResult(
                    status="ok",
                    data={
                        "message": "No evaluated recommendations yet.",
                        "total_outcomes": 0,
                    },
                )

            horizons = []
            for h in scorecard.horizons:
                horizons.append(
                    {
                        "horizon_days": h.horizon_days,
                        "total": h.total,
                        "correct": h.correct,
                        "hit_rate": round(h.hit_rate * 100, 1),
                        "avg_alpha": round(h.avg_alpha * 100, 2),
                    }
                )

            return ToolResult(
                status="ok",
                data={
                    "total_outcomes": scorecard.total_outcomes,
                    "overall_hit_rate_pct": round(scorecard.overall_hit_rate * 100, 1),
                    "avg_alpha_pct": round(scorecard.avg_alpha * 100, 2),
                    "buy_hit_rate_pct": round(scorecard.buy_hit_rate * 100, 1),
                    "sell_hit_rate_pct": round(scorecard.sell_hit_rate * 100, 1),
                    "worst_miss": {
                        "ticker": scorecard.worst_miss_ticker,
                        "return_pct": round(scorecard.worst_miss_pct * 100, 2),
                    },
                    "horizons": horizons,
                },
            )

        except Exception as e:
            logger.error(
                "get_recommendation_scorecard_failed",
                extra={"error": str(e)},
            )
            return ToolResult(
                status="error",
                error="Failed to compute recommendation scorecard",
            )
