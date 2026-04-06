"""CompanyProfileTool — read company profile from DB."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from backend.tools.base import BaseTool, CachePolicy, ToolResult

logger = logging.getLogger(__name__)


class CompanyProfileInput(BaseModel):
    """Input schema for get_company_profile tool."""

    ticker: str = Field(description="Stock ticker symbol (e.g., AAPL, PLTR)")


class CompanyProfileTool(BaseTool):
    """Get company profile information for a stock.

    Returns business summary, sector, industry, employee count, website,
    and market cap. Data is read from the database (materialized during
    ingestion), not fetched from yfinance at runtime.
    """

    name = "get_company_profile"
    description = (
        "Get company profile: business summary, sector, industry, employees, "
        "website, and market cap. Use this to understand what a company does."
    )
    category = "data"
    parameters = {
        "type": "object",
        "properties": {
            "ticker": {"type": "string", "description": "Stock ticker symbol"},
        },
        "required": ["ticker"],
    }
    args_schema = CompanyProfileInput
    cache_policy = CachePolicy(
        ttl=__import__("datetime").timedelta(hours=1),
        key_fields=["ticker"],
    )
    timeout_seconds = 5.0

    async def _run(self, params: dict[str, Any]) -> ToolResult:
        """Read company profile from DB for the given ticker."""
        ticker = str(params.get("ticker", "")).upper().strip()
        if not ticker:
            return ToolResult(status="error", error="Missing required param: ticker")

        from sqlalchemy import select

        from backend.database import async_session_factory
        from backend.models.stock import Stock

        async with async_session_factory() as session:
            result = await session.execute(select(Stock).where(Stock.ticker == ticker))
            stock = result.scalar_one_or_none()

        if stock is None:
            return ToolResult(
                status="error",
                error=f"Ticker '{ticker}' not found in database. Use ingest_stock first.",
            )

        # Truncate business summary to 500 chars for concise agent context
        summary = stock.business_summary
        if summary and len(summary) > 500:
            summary = summary[:497] + "..."

        return ToolResult(
            status="ok",
            data={
                "ticker": stock.ticker,
                "name": stock.name,
                "summary": summary,
                "sector": stock.sector,
                "industry": stock.industry,
                "employees": stock.employees,
                "website": stock.website,
                "market_cap": stock.market_cap,
            },
        )
