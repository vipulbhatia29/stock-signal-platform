"""PortfolioExposureTool — sector/geographic exposure and risk analysis."""

from __future__ import annotations

import logging
from typing import Any

from backend.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


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
        "properties": {
            "user_id": {"type": "string", "description": "User UUID (injected by agent)"},
        },
        "required": ["user_id"],
    }
    timeout_seconds = 10.0

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        """Fetch portfolio summary with sector breakdown."""
        try:
            from backend.database import async_session_factory
            from backend.tools.portfolio import get_portfolio_summary

            user_id = params["user_id"]
            async with async_session_factory() as session:
                summary = await get_portfolio_summary(session, user_id)
                return ToolResult(status="ok", data=summary)
        except Exception as e:
            logger.error("portfolio_exposure_failed", extra={"error": str(e)})
            return ToolResult(status="error", error=str(e))
