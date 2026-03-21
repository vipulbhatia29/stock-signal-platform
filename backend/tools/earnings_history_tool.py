"""EarningsHistoryTool — read quarterly earnings data from DB."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from backend.tools.base import BaseTool, CachePolicy, ToolResult

logger = logging.getLogger(__name__)


class EarningsHistoryInput(BaseModel):
    """Input schema for get_earnings_history tool."""

    ticker: str = Field(description="Stock ticker symbol (e.g., AAPL, PLTR)")
    quarters: int = Field(default=8, description="Number of quarters to return (default 8)")


class EarningsHistoryTool(BaseTool):
    """Get quarterly earnings history for a stock.

    Returns EPS estimates, actuals, surprise percentages, and a beat/miss
    summary. Data is read from the database (materialized during ingestion).
    """

    name = "get_earnings_history"
    description = (
        "Get quarterly earnings history: EPS estimates, actuals, surprise %, "
        "and beat/miss summary. Returns the last N quarters (default 8)."
    )
    category = "data"
    parameters = {
        "type": "object",
        "properties": {
            "ticker": {"type": "string", "description": "Stock ticker symbol"},
            "quarters": {
                "type": "integer",
                "description": "Number of quarters (default 8)",
                "default": 8,
            },
        },
        "required": ["ticker"],
    }
    args_schema = EarningsHistoryInput
    cache_policy = CachePolicy(
        ttl=__import__("datetime").timedelta(hours=1),
        key_fields=["ticker"],
    )
    timeout_seconds = 5.0

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        """Read earnings history from DB for the given ticker."""
        ticker = str(params.get("ticker", "")).upper().strip()
        if not ticker:
            return ToolResult(status="error", error="Missing required param: ticker")

        quarters = int(params.get("quarters", 8))

        try:
            from sqlalchemy import select

            from backend.database import async_session_factory
            from backend.models.earnings import EarningsSnapshot

            async with async_session_factory() as session:
                result = await session.execute(
                    select(EarningsSnapshot)
                    .where(EarningsSnapshot.ticker == ticker)
                    .order_by(EarningsSnapshot.quarter.desc())
                    .limit(quarters)
                )
                snapshots = list(result.scalars().all())

            if not snapshots:
                return ToolResult(
                    status="ok",
                    data={
                        "ticker": ticker,
                        "has_earnings": False,
                        "message": "No earnings data available. Use ingest_stock to fetch it.",
                    },
                )

            # Build quarterly data and beat/miss summary
            earnings_list = []
            beat_count = 0
            total_with_both = 0

            for snap in snapshots:
                entry: dict[str, Any] = {
                    "quarter": snap.quarter,
                    "eps_estimate": snap.eps_estimate,
                    "eps_actual": snap.eps_actual,
                    "surprise_pct": snap.surprise_pct,
                }
                if snap.eps_estimate is not None and snap.eps_actual is not None:
                    total_with_both += 1
                    if snap.eps_actual > snap.eps_estimate:
                        beat_count += 1
                earnings_list.append(entry)

            return ToolResult(
                status="ok",
                data={
                    "ticker": ticker,
                    "has_earnings": True,
                    "quarters": earnings_list,
                    "beat_count": beat_count,
                    "total_quarters": total_with_both,
                    "summary": f"Beat {beat_count} of last {total_with_both} quarters"
                    if total_with_both > 0
                    else "No comparable quarters",
                },
            )

        except Exception as e:
            logger.error("get_earnings_history_failed", extra={"ticker": ticker, "error": str(e)})
            return ToolResult(status="error", error=f"Failed to get earnings for {ticker}")
