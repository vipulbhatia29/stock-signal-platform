"""PortfolioExposureTool — sector/geographic exposure and risk analysis."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel

from backend.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class PortfolioExposureInput(BaseModel):
    """Input schema for get_portfolio_exposure tool.

    No LLM-facing parameters — user_id is injected via ContextVar.
    """


class PortfolioExposureTool(BaseTool):
    """Get portfolio sector allocation and exposure analysis."""

    name = "get_portfolio_exposure"
    description = (
        "Get the user's portfolio sector allocation, total value, "
        "unrealized P&L, and concentration risk analysis."
    )
    category = "portfolio"
    parameters = {
        "type": "object",
        "properties": {},
    }
    args_schema = PortfolioExposureInput
    timeout_seconds = 10.0

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        """Fetch portfolio summary with sector breakdown."""
        try:
            from backend.database import async_session_factory
            from backend.request_context import current_user_id
            from backend.tools.portfolio import get_or_create_portfolio, get_portfolio_summary

            user_id = current_user_id.get()
            if user_id is None:
                return ToolResult(status="error", error="No user context available")

            async with async_session_factory() as session:
                portfolio = await get_or_create_portfolio(user_id, session)
                summary = await get_portfolio_summary(portfolio.id, session)
                return ToolResult(status="ok", data=summary.model_dump())
        except Exception:
            logger.exception("Failed to retrieve portfolio exposure")
            return ToolResult(
                status="error",
                error="Failed to retrieve portfolio exposure. Please try again.",
            )
