"""FinnhubAdapter — market intelligence via Finnhub REST API."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from backend.tools.adapters.base import MCPAdapter
from backend.tools.base import ProxiedTool, ToolResult

logger = logging.getLogger(__name__)

_BASE_URL = "https://finnhub.io/api/v1"


class FinnhubAdapter(MCPAdapter):
    """Adapter for the Finnhub market intelligence API."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    @property
    def name(self) -> str:
        """Adapter identifier."""
        return "finnhub_tools"

    def get_tools(self) -> list[ProxiedTool]:
        """Return ProxiedTool instances for Finnhub tools."""
        return [
            ProxiedTool(
                name="get_analyst_ratings",
                description="Get consensus analyst recommendation trends for a stock.",
                category="market_intelligence",
                parameters={
                    "type": "object",
                    "properties": {
                        "ticker": {"type": "string", "description": "Stock ticker symbol"},
                    },
                    "required": ["ticker"],
                },
                adapter=self,
            ),
            ProxiedTool(
                name="get_social_sentiment",
                description="Get social media sentiment from Reddit and Twitter.",
                category="market_intelligence",
                parameters={
                    "type": "object",
                    "properties": {
                        "ticker": {"type": "string", "description": "Stock ticker symbol"},
                    },
                    "required": ["ticker"],
                },
                adapter=self,
            ),
            ProxiedTool(
                name="get_etf_holdings",
                description="Get the holdings of an ETF.",
                category="market_intelligence",
                parameters={
                    "type": "object",
                    "properties": {
                        "ticker": {"type": "string", "description": "ETF ticker symbol"},
                    },
                    "required": ["ticker"],
                },
                adapter=self,
            ),
            ProxiedTool(
                name="get_esg_scores",
                description="Get ESG (Environmental, Social, Governance) scores for a company.",
                category="market_intelligence",
                parameters={
                    "type": "object",
                    "properties": {
                        "ticker": {"type": "string", "description": "Stock ticker symbol"},
                    },
                    "required": ["ticker"],
                },
                adapter=self,
            ),
            ProxiedTool(
                name="get_supply_chain",
                description="Get supply chain relationships (customers/suppliers).",
                category="market_intelligence",
                parameters={
                    "type": "object",
                    "properties": {
                        "ticker": {"type": "string", "description": "Stock ticker symbol"},
                    },
                    "required": ["ticker"],
                },
                adapter=self,
            ),
        ]

    async def execute(self, tool_name: str, params: dict) -> ToolResult:
        """Execute a Finnhub API call."""
        try:
            dispatch = {
                "get_analyst_ratings": self._fetch_analyst_ratings,
                "get_social_sentiment": self._fetch_social_sentiment,
                "get_etf_holdings": self._fetch_etf_holdings,
                "get_esg_scores": self._fetch_esg_scores,
                "get_supply_chain": self._fetch_supply_chain,
            }
            handler = dispatch.get(tool_name)
            if handler is None:
                return ToolResult(status="error", error=f"Unknown tool: {tool_name}")
            data = await handler(params)
            return ToolResult(status="ok", data=data)
        except Exception:
            logger.error("Finnhub API call failed", exc_info=True)
            return ToolResult(
                status="error",
                error="External data source unavailable. Please try again later.",
            )

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict:
        """Make an authenticated GET request to Finnhub."""
        query = {"token": self._api_key}
        if params:
            query.update(params)
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"{_BASE_URL}{path}", params=query)
            resp.raise_for_status()
            return resp.json()

    async def _fetch_analyst_ratings(self, params: dict[str, Any]) -> dict:
        """Fetch analyst recommendation trends."""
        ticker = params["ticker"]
        data = await self._get("/stock/recommendation", {"symbol": ticker})
        # data is a list of monthly recommendation objects
        recent = data[:6] if isinstance(data, list) else []
        return {
            "ticker": ticker,
            "recommendations": [
                {
                    "period": r.get("period", ""),
                    "buy": r.get("buy", 0),
                    "hold": r.get("hold", 0),
                    "sell": r.get("sell", 0),
                    "strong_buy": r.get("strongBuy", 0),
                    "strong_sell": r.get("strongSell", 0),
                }
                for r in recent
            ],
        }

    async def _fetch_social_sentiment(self, params: dict[str, Any]) -> dict:
        """Fetch social media sentiment."""
        ticker = params["ticker"]
        data = await self._get("/stock/social-sentiment", {"symbol": ticker})
        return {
            "ticker": ticker,
            "reddit": data.get("reddit", [])[:5],
            "twitter": data.get("twitter", [])[:5],
        }

    async def _fetch_etf_holdings(self, params: dict[str, Any]) -> dict:
        """Fetch ETF holdings."""
        ticker = params["ticker"]
        data = await self._get("/etf/holdings", {"symbol": ticker})
        holdings = data.get("holdings", [])[:20]
        return {
            "ticker": ticker,
            "holdings": [
                {
                    "symbol": h.get("symbol", ""),
                    "name": h.get("name", ""),
                    "percent": h.get("percent", 0),
                    "value": h.get("value", 0),
                }
                for h in holdings
            ],
        }

    async def _fetch_esg_scores(self, params: dict[str, Any]) -> dict:
        """Fetch ESG scores."""
        ticker = params["ticker"]
        data = await self._get("/stock/esg", {"symbol": ticker})
        return {
            "ticker": ticker,
            "total_score": data.get("totalESGScore", None),
            "environment": data.get("environmentScore", None),
            "social": data.get("socialScore", None),
            "governance": data.get("governanceScore", None),
        }

    async def _fetch_supply_chain(self, params: dict[str, Any]) -> dict:
        """Fetch supply chain relationships."""
        ticker = params["ticker"]
        data = await self._get("/stock/supply-chain", {"symbol": ticker})
        relationships = data.get("data", [])[:15]
        return {
            "ticker": ticker,
            "relationships": [
                {
                    "symbol": r.get("symbol", ""),
                    "name": r.get("name", ""),
                    "relationship": r.get("relatedType", ""),
                }
                for r in relationships
            ],
        }

    async def health_check(self) -> bool:
        """Verify Finnhub API is reachable."""
        try:
            await self._get("/stock/recommendation", {"symbol": "AAPL"})
            return True
        except (httpx.HTTPError, Exception):
            return False
