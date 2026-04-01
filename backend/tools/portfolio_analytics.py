"""PortfolioAnalyticsTool — reads materialized QuantStats metrics from DB."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel

from backend.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class PortfolioAnalyticsInput(BaseModel):
    """Input schema — no parameters, user_id injected via ContextVar."""


class PortfolioAnalyticsTool(BaseTool):
    """Get portfolio-level QuantStats analytics (Sharpe, Sortino, drawdown, alpha, beta, etc.)."""

    name = "get_portfolio_analytics"
    description = (
        "Get the user's portfolio risk analytics: Sharpe, Sortino, max drawdown, "
        "Calmar, alpha, beta (vs SPY), VaR 95%, and CAGR. "
        "These are computed nightly from portfolio snapshot history."
    )
    category = "portfolio"
    parameters = {
        "type": "object",
        "properties": {},
    }
    args_schema = PortfolioAnalyticsInput
    timeout_seconds = 10.0

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        """Fetch materialized QuantStats metrics from latest portfolio snapshot."""
        try:
            from sqlalchemy import select

            from backend.database import async_session_factory
            from backend.models.portfolio import PortfolioSnapshot
            from backend.request_context import current_user_id
            from backend.tools.portfolio import get_or_create_portfolio

            user_id = current_user_id.get()
            if user_id is None:
                return ToolResult(status="error", error="No user context available")

            async with async_session_factory() as session:
                portfolio = await get_or_create_portfolio(user_id, session)

                result = await session.execute(
                    select(PortfolioSnapshot)
                    .where(PortfolioSnapshot.portfolio_id == portfolio.id)
                    .order_by(PortfolioSnapshot.snapshot_date.desc())
                    .limit(1)
                )
                snapshot = result.scalar_one_or_none()

                if snapshot is None:
                    return ToolResult(
                        status="ok",
                        data={
                            "message": (
                                "No portfolio snapshots yet. "
                                "Analytics available after the nightly pipeline runs."
                            ),
                        },
                    )

                # Extract values within session scope
                data = {
                    "sharpe": snapshot.sharpe,
                    "sortino": snapshot.sortino,
                    "max_drawdown": snapshot.max_drawdown,
                    "max_drawdown_duration_days": snapshot.max_drawdown_duration,
                    "calmar": snapshot.calmar,
                    "alpha": snapshot.alpha,
                    "beta": snapshot.beta,
                    "var_95": snapshot.var_95,
                    "cagr": snapshot.cagr,
                    "data_days": snapshot.data_days,
                }

            # Filter out None values for cleaner LLM output
            data = {k: v for k, v in data.items() if v is not None}

            if not data:
                return ToolResult(
                    status="ok",
                    data={
                        "message": (
                            "Portfolio analytics not yet computed. "
                            "Need at least 30 days of snapshots."
                        ),
                    },
                )

            return ToolResult(status="ok", data=data)

        except Exception:
            logger.exception("PortfolioAnalyticsTool failed")
            return ToolResult(status="error", error="Failed to retrieve portfolio analytics")
