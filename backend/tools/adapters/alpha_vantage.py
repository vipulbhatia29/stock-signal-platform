"""AlphaVantageAdapter — market data via Alpha Vantage REST API."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from backend.services.http_client import get_http_client
from backend.tools.adapters.base import MCPAdapter
from backend.tools.base import ProxiedTool, ToolResult

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.alphavantage.co/query"


class AlphaVantageAdapter(MCPAdapter):
    """Adapter for Alpha Vantage market data API."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    @property
    def name(self) -> str:
        """Adapter identifier."""
        return "alpha_vantage_tools"

    def get_tools(self) -> list[ProxiedTool]:
        """Return ProxiedTool instances for Alpha Vantage tools."""
        return [
            ProxiedTool(
                name="get_news_sentiment",
                description="Get news sentiment analysis for a stock ticker from Alpha Vantage.",
                category="market_data",
                parameters={
                    "type": "object",
                    "properties": {
                        "ticker": {"type": "string", "description": "Stock ticker symbol"},
                        "limit": {
                            "type": "integer",
                            "description": "Max articles to return",
                            "default": 10,
                        },
                    },
                    "required": ["ticker"],
                },
                adapter=self,
            ),
            ProxiedTool(
                name="get_quotes",
                description="Get real-time stock quote from Alpha Vantage.",
                category="market_data",
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
        """Execute an Alpha Vantage API call."""
        try:
            if tool_name == "get_news_sentiment":
                data = await self._fetch_news_sentiment(params)
            elif tool_name == "get_quotes":
                data = await self._fetch_quote(params)
            else:
                return ToolResult(status="error", error=f"Unknown tool: {tool_name}")
            return ToolResult(status="ok", data=data)
        except Exception:
            logger.error("Alpha Vantage API call failed", exc_info=True)
            return ToolResult(
                status="error",
                error="External data source unavailable. Please try again later.",
            )

    async def _fetch_news_sentiment(self, params: dict[str, Any]) -> dict:
        """Fetch news sentiment from Alpha Vantage."""
        ticker = params["ticker"]
        limit = params.get("limit", 10)
        client = get_http_client()
        resp = await client.get(
            _BASE_URL,
            params={
                "function": "NEWS_SENTIMENT",
                "tickers": ticker,
                "limit": limit,
                "apikey": self._api_key,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        feed = data.get("feed", [])[:limit]
        return {
            "ticker": ticker,
            "articles": [
                {
                    "title": a.get("title", ""),
                    "source": a.get("source", ""),
                    "sentiment_score": a.get("overall_sentiment_score", 0),
                    "sentiment_label": a.get("overall_sentiment_label", ""),
                    "published": a.get("time_published", ""),
                }
                for a in feed
            ],
        }

    async def _fetch_quote(self, params: dict[str, Any]) -> dict:
        """Fetch real-time quote from Alpha Vantage."""
        ticker = params["ticker"]
        client = get_http_client()
        resp = await client.get(
            _BASE_URL,
            params={
                "function": "GLOBAL_QUOTE",
                "symbol": ticker,
                "apikey": self._api_key,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        quote = data.get("Global Quote", {})
        return {
            "ticker": ticker,
            "price": quote.get("05. price", ""),
            "change": quote.get("09. change", ""),
            "change_percent": quote.get("10. change percent", ""),
            "volume": quote.get("06. volume", ""),
        }

    async def health_check(self) -> bool:
        """Verify Alpha Vantage API is reachable."""
        try:
            client = get_http_client()
            resp = await client.get(
                _BASE_URL,
                params={"function": "TIME_SERIES_INTRADAY", "apikey": self._api_key},
                timeout=10,
            )
            return resp.status_code < 500
        except httpx.HTTPError:
            return False
