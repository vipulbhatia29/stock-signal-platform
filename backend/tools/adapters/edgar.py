"""EdgarAdapter — SEC filings via edgartools library."""

from __future__ import annotations

import asyncio
import logging
from functools import partial
from typing import Any

from backend.tools.adapters.base import MCPAdapter
from backend.tools.base import ProxiedTool, ToolResult

logger = logging.getLogger(__name__)


class EdgarAdapter(MCPAdapter):
    """Adapter for SEC EDGAR filings using the edgartools Python library."""

    @property
    def name(self) -> str:
        """Adapter identifier."""
        return "edgar_tools"

    def get_tools(self) -> list[ProxiedTool]:
        """Return ProxiedTool instances for EDGAR filing tools."""
        tools = [
            ProxiedTool(
                name="get_10k_section",
                description="Retrieve a specific section from a company's latest 10-K filing.",
                category="sec_filings",
                parameters={
                    "type": "object",
                    "properties": {
                        "ticker": {"type": "string", "description": "Stock ticker symbol"},
                        "section": {
                            "type": "string",
                            "description": "10-K section (e.g. '1A' for Risk Factors)",
                        },
                    },
                    "required": ["ticker", "section"],
                },
                adapter=self,
            ),
            ProxiedTool(
                name="get_13f_holdings",
                description="Retrieve 13-F institutional holdings for a company.",
                category="sec_filings",
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
                name="get_insider_trades",
                description="Retrieve recent insider trading activity (Form 4 filings).",
                category="sec_filings",
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
                name="get_8k_events",
                description="Retrieve recent 8-K event filings for a company.",
                category="sec_filings",
                parameters={
                    "type": "object",
                    "properties": {
                        "ticker": {"type": "string", "description": "Stock ticker symbol"},
                        "limit": {
                            "type": "integer",
                            "description": "Max filings to return",
                            "default": 5,
                        },
                    },
                    "required": ["ticker"],
                },
                adapter=self,
            ),
        ]
        return tools

    async def execute(self, tool_name: str, params: dict) -> ToolResult:
        """Execute an EDGAR tool by delegating to edgartools in a thread."""
        try:
            data = await self._call_edgar(tool_name, params)
            return ToolResult(status="ok", data=data)
        except Exception:
            logger.error("SEC EDGAR API call failed", exc_info=True)
            return ToolResult(
                status="error",
                error="External data source unavailable. Please try again later.",
            )

    async def _call_edgar(self, tool_name: str, params: dict[str, Any]) -> Any:
        """Call edgartools in a thread executor (it's synchronous)."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, partial(self._sync_call_edgar, tool_name, params))

    @staticmethod
    def _sync_call_edgar(tool_name: str, params: dict[str, Any]) -> Any:
        """Synchronous edgartools calls."""
        from edgar import Company  # type: ignore[import-untyped]

        ticker = params["ticker"]
        company = Company(ticker)

        if tool_name == "get_10k_section":
            filings = company.get_filings(form="10-K")
            latest = filings.latest(1)
            if not latest:
                return {"error": f"No 10-K filings found for {ticker}"}
            filing = latest[0] if hasattr(latest, "__getitem__") else latest
            doc = filing.obj()
            section = params.get("section", "1A")
            text = str(getattr(doc, f"item{section}", "Section not found"))
            return {"ticker": ticker, "section": section, "text": text[:5000]}

        if tool_name == "get_13f_holdings":
            filings = company.get_filings(form="13-F")
            latest = filings.latest(1)
            if not latest:
                return {"ticker": ticker, "holdings": []}
            filing = latest[0] if hasattr(latest, "__getitem__") else latest
            obj = filing.obj()
            holdings = []
            for h in getattr(obj, "holdings", [])[:20]:
                holdings.append(
                    {
                        "name": str(getattr(h, "nameOfIssuer", "")),
                        "value": str(getattr(h, "value", "")),
                        "shares": str(getattr(h, "shrsOrPrnAmt", "")),
                    }
                )
            return {"ticker": ticker, "holdings": holdings}

        if tool_name == "get_insider_trades":
            filings = company.get_filings(form="4")
            recent = filings.latest(10)
            trades = []
            items = recent if hasattr(recent, "__iter__") else [recent] if recent else []
            for f in items:
                trades.append(
                    {
                        "date": str(getattr(f, "filing_date", "")),
                        "description": str(f)[:200],
                    }
                )
            return {"ticker": ticker, "trades": trades}

        if tool_name == "get_8k_events":
            limit = params.get("limit", 5)
            filings = company.get_filings(form="8-K")
            recent = filings.latest(limit)
            events = []
            items = recent if hasattr(recent, "__iter__") else [recent] if recent else []
            for f in items:
                events.append(
                    {
                        "date": str(getattr(f, "filing_date", "")),
                        "description": str(f)[:200],
                    }
                )
            return {"ticker": ticker, "events": events}

        return {"error": f"Unknown tool: {tool_name}"}
