"""FredAdapter — economic data via FRED REST API."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from backend.services.http_client import get_http_client
from backend.tools.adapters.base import MCPAdapter
from backend.tools.base import ProxiedTool, ToolResult

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"


class FredAdapter(MCPAdapter):
    """Adapter for the Federal Reserve Economic Data (FRED) API."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    @property
    def name(self) -> str:
        """Adapter identifier."""
        return "fred_tools"

    def get_tools(self) -> list[ProxiedTool]:
        """Return ProxiedTool instances for FRED tools."""
        return [
            ProxiedTool(
                name="get_economic_series",
                description=(
                    "Fetch one or more FRED economic data series "
                    "(e.g. DFF, CPIAUCSL, DGS10, UNRATE, DCOILWTICO)."
                ),
                category="economic_data",
                parameters={
                    "type": "object",
                    "properties": {
                        "series_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of FRED series IDs",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Max observations per series",
                            "default": 10,
                        },
                    },
                    "required": ["series_ids"],
                },
                adapter=self,
            ),
        ]

    async def execute(self, tool_name: str, params: dict) -> ToolResult:
        """Execute a FRED API call."""
        try:
            if tool_name != "get_economic_series":
                return ToolResult(status="error", error=f"Unknown tool: {tool_name}")
            data = await self._fetch_series(params)
            return ToolResult(status="ok", data=data)
        except Exception:
            logger.error("FRED API call failed", exc_info=True)
            return ToolResult(
                status="error",
                error="External data source unavailable. Please try again later.",
            )

    async def _fetch_series(self, params: dict[str, Any]) -> dict:
        """Fetch observations for one or more FRED series."""
        series_ids = params["series_ids"]
        limit = params.get("limit", 10)
        results: dict[str, list[dict]] = {}

        client = get_http_client()
        for sid in series_ids:
            resp = await client.get(
                _BASE_URL,
                params={
                    "series_id": sid,
                    "api_key": self._api_key,
                    "file_type": "json",
                    "sort_order": "desc",
                    "limit": limit,
                },
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            observations = data.get("observations", [])
            results[sid] = [
                {"date": o.get("date", ""), "value": o.get("value", "")} for o in observations
            ]

        return {"series": results}

    async def health_check(self) -> bool:
        """Verify FRED API is reachable."""
        try:
            client = get_http_client()
            resp = await client.get(
                "https://api.stlouisfed.org/fred/series",
                params={
                    "series_id": "DFF",
                    "api_key": self._api_key,
                    "file_type": "json",
                },
                timeout=10,
            )
            return resp.status_code < 500
        except httpx.HTTPError:
            return False
