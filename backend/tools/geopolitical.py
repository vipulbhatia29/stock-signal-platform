"""GeopoliticalEventsTool — GDELT API wrapper for geopolitical events."""

from __future__ import annotations

import logging
from typing import Any

from backend.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class GeopoliticalEventsTool(BaseTool):
    """Search geopolitical events via GDELT for sector impact analysis."""

    name = "get_geopolitical_events"
    description = (
        "Search recent geopolitical events and news using GDELT. "
        "Returns articles with titles, URLs, and tone scores. "
        "Useful for assessing geopolitical risk impact on sectors."
    )
    category = "macro"
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query (e.g., 'Iran oil sanctions')"},
            "days": {"type": "integer", "description": "Look back N days (default 7)", "default": 7},
            "max_results": {"type": "integer", "description": "Max articles (default 10)", "default": 10},
        },
        "required": ["query"],
    }
    timeout_seconds = 15.0

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        """Search GDELT for geopolitical events."""
        try:
            from datetime import datetime, timedelta

            from gdeltdoc import GdeltDoc, Filters

            days = params.get("days", 7)
            max_results = params.get("max_results", 10)
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)

            gd = GdeltDoc()
            filters = Filters(
                keyword=params["query"],
                start_date=start_date.strftime("%Y-%m-%d"),
                end_date=end_date.strftime("%Y-%m-%d"),
            )
            articles = gd.article_search(filters)

            if articles is None or articles.empty:
                return ToolResult(status="ok", data=[])

            results = []
            for _, row in articles.head(max_results).iterrows():
                results.append({
                    "title": row.get("title", ""),
                    "url": row.get("url", ""),
                    "domain": row.get("domain", ""),
                    "language": row.get("language", ""),
                    "seendate": str(row.get("seendate", "")),
                })
            return ToolResult(status="ok", data=results)
        except Exception as e:
            logger.error("geopolitical_failed", extra={"query": params.get("query"), "error": str(e)})
            return ToolResult(status="error", error=str(e))
