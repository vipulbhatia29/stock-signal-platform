"""SearchStocksTool — resolve company name or ticker via DB + Yahoo Finance."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from backend.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class SearchStocksInput(BaseModel):
    """Input schema for search_stocks tool."""

    query: str = Field(
        description="Search query — company name or ticker symbol (e.g., 'Palantir' or 'PLTR')"
    )
    limit: int = Field(default=5, description="Max results to return (default 5)")


class SearchStocksTool(BaseTool):
    """Search for stocks by company name or ticker symbol.

    Searches the local database first, then supplements with Yahoo Finance
    results for stocks not yet in the platform. Use this to resolve a
    company name to its ticker before calling analyze_stock or ingest_stock.
    """

    name = "search_stocks"
    description = (
        "Search for a stock by company name or ticker symbol. "
        "Returns matching stocks from the database and Yahoo Finance. "
        "Results include an 'in_db' flag — if False, use ingest_stock to add it first."
    )
    category = "data"
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Company name or ticker symbol"},
            "limit": {"type": "integer", "description": "Max results (default 5)", "default": 5},
        },
        "required": ["query"],
    }
    args_schema = SearchStocksInput
    timeout_seconds = 10.0

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        """Search DB + Yahoo Finance for matching stocks."""
        query = params.get("query", "").strip()
        if not query:
            return ToolResult(status="error", error="Missing required param: query")

        limit = params.get("limit", 5)

        try:
            import httpx
            from sqlalchemy import select

            from backend.database import async_session_factory
            from backend.models.stock import Stock

            # 1. Local DB search
            async with async_session_factory() as session:
                db_query = (
                    select(Stock)
                    .where((Stock.ticker.ilike(f"{query}%")) | (Stock.name.ilike(f"%{query}%")))
                    .where(Stock.is_active.is_(True))
                    .order_by(Stock.ticker)
                    .limit(limit)
                )
                result = await session.execute(db_query)
                db_stocks = list(result.scalars().all())

            db_results = [
                {
                    "ticker": s.ticker,
                    "name": s.name,
                    "exchange": s.exchange,
                    "sector": s.sector,
                    "in_db": True,
                }
                for s in db_stocks
            ]

            # 2. If DB has enough, return early
            if len(db_results) >= limit:
                return ToolResult(status="ok", data=db_results)

            # 3. Supplement with Yahoo Finance
            _YF_ALLOWED_TYPES = {"EQUITY", "ETF"}
            _YF_US_EXCHANGES = {
                "NASDAQ",
                "NYSE",
                "NYSEArca",
                "NasdaqGS",
                "NasdaqGM",
                "NasdaqCM",
            }

            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.get(
                        "https://query2.finance.yahoo.com/v1/finance/search",
                        params={
                            "q": query,
                            "quotesCount": limit,
                            "newsCount": 0,
                            "listsCount": 0,
                        },
                        headers={
                            "User-Agent": "Mozilla/5.0 (compatible; StockSignalPlatform/1.0)",
                        },
                    )
                    resp.raise_for_status()
                    quotes = resp.json().get("quotes", [])
            except Exception:
                logger.warning("yahoo_search_in_tool_failed", extra={"query": query})
                return ToolResult(status="ok", data=db_results)

            db_tickers = {r["ticker"] for r in db_results}
            for q_item in quotes:
                if len(db_results) >= limit:
                    break
                if q_item.get("quoteType") not in _YF_ALLOWED_TYPES:
                    continue
                ticker = q_item.get("symbol", "").replace(".", "-")
                exchange = q_item.get("exchDisp", "")
                if exchange not in _YF_US_EXCHANGES:
                    continue
                if ticker in db_tickers:
                    continue
                db_results.append(
                    {
                        "ticker": ticker,
                        "name": q_item.get("longname") or q_item.get("shortname", ""),
                        "exchange": exchange,
                        "sector": q_item.get("sectorDisp"),
                        "in_db": False,
                    }
                )
                db_tickers.add(ticker)

            return ToolResult(status="ok", data=db_results)

        except Exception:
            logger.exception("Failed to search stocks for query %s", query)
            return ToolResult(status="error", error="Search failed. Please try again.")
