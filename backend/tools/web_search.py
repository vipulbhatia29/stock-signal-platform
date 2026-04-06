"""WebSearchTool — general web search via SerpAPI."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from backend.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class WebSearchInput(BaseModel):
    """Input schema for web_search tool."""

    query: str = Field(description="Search query")
    num_results: int = Field(default=5, description="Number of results (default 5)")


class WebSearchTool(BaseTool):
    """Search the web for current information using SerpAPI."""

    name = "web_search"
    description = "Search the web for current news, articles, and information on any topic."
    category = "data"
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "num_results": {
                "type": "integer",
                "description": "Number of results (default 5)",
                "default": 5,
            },
        },
        "required": ["query"],
    }
    args_schema = WebSearchInput
    timeout_seconds = 10.0

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        """Execute web search via SerpAPI."""
        try:
            from backend.config import settings
            from backend.services.http_client import get_http_client

            if not settings.SERPAPI_API_KEY:
                return ToolResult(status="error", error="SERPAPI_API_KEY not configured")

            num_results = params.get("num_results", 5)
            client = get_http_client()
            resp = await client.get(
                "https://serpapi.com/search",
                params={
                    "q": params["query"],
                    "api_key": settings.SERPAPI_API_KEY,
                    "engine": "google",
                    "num": num_results,
                },
                timeout=8.0,
            )
            resp.raise_for_status()
            data = resp.json()

            results = [
                {
                    "title": r.get("title", ""),
                    "link": r.get("link", ""),
                    "snippet": r.get("snippet", ""),
                }
                for r in data.get("organic_results", [])[:num_results]
            ]
            return ToolResult(status="ok", data=results)
        except Exception:
            logger.exception("Web search failed for query %s", params.get("query"))
            return ToolResult(status="error", error="Web search failed. Please try again.")
