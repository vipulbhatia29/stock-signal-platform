"""Tool result validation layer for Agent V2.

Sits between executor and synthesizer. Annotates each tool result with
status (ok/unavailable/stale), source, timestamp, and reason.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.tools.base import ToolResult

logger = logging.getLogger(__name__)

# Tools whose data has a freshness window
_PRICE_TOOLS = {"analyze_stock", "compute_signals", "get_recommendations"}
_STALE_THRESHOLD = timedelta(hours=24)


def validate_tool_result(
    result: ToolResult,
    tool_name: str,
    timestamp: datetime | None = None,
) -> dict[str, Any]:
    """Validate and annotate a tool result for the synthesizer.

    Args:
        result: The raw ToolResult from tool execution.
        tool_name: Name of the tool that produced this result.
        timestamp: When the tool was called. Defaults to now.

    Returns:
        Annotated dict with status, data, source, timestamp, reason.
    """
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)

    ts_str = timestamp.isoformat()

    # Error status → unavailable
    if result.status == "error":
        return {
            "tool": tool_name,
            "status": "unavailable",
            "data": None,
            "timestamp": ts_str,
            "source": None,
            "reason": result.error or "Tool returned error",
        }

    # Timeout status → unavailable
    if result.status == "timeout":
        return {
            "tool": tool_name,
            "status": "unavailable",
            "data": None,
            "timestamp": ts_str,
            "source": None,
            "reason": "Tool execution timed out",
        }

    # Null/empty data → unavailable
    if result.data is None:
        return {
            "tool": tool_name,
            "status": "unavailable",
            "data": None,
            "timestamp": ts_str,
            "source": None,
            "reason": "No data returned",
        }

    # Check staleness for price-related tools
    status = "ok"
    reason = None

    if tool_name in _PRICE_TOOLS and isinstance(result.data, dict):
        last_updated = result.data.get("last_fetched_at") or result.data.get("computed_at")
        if last_updated:
            try:
                if isinstance(last_updated, str):
                    dt = datetime.fromisoformat(last_updated)
                else:
                    dt = last_updated
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                age = timestamp - dt
                if age > _STALE_THRESHOLD:
                    status = "stale"
                    reason = f"Data is {age.days}d {age.seconds // 3600}h old"
            except (ValueError, TypeError):
                pass

    return {
        "tool": tool_name,
        "status": status,
        "data": result.data,
        "timestamp": ts_str,
        "source": _get_source(tool_name),
        "reason": reason,
    }


def _get_source(tool_name: str) -> str:
    """Return a human-readable data source for a tool."""
    sources = {
        "analyze_stock": "TimescaleDB (computed from yfinance prices)",
        "compute_signals": "TimescaleDB (technical indicators)",
        "get_recommendations": "Recommendation engine (composite score)",
        "get_fundamentals": "Stock model (materialized from yfinance)",
        "get_analyst_targets": "Stock model (materialized from yfinance)",
        "get_earnings_history": "EarningsSnapshot table (materialized from yfinance)",
        "get_company_profile": "Stock model (materialized from yfinance)",
        "get_portfolio_exposure": "Portfolio model (user transactions)",
        "screen_stocks": "Signal snapshots (latest computed)",
        "search_stocks": "Stock table + Yahoo Finance API",
        "ingest_stock": "yfinance (live fetch → DB materialization)",
        "web_search": "SerpAPI (live web search)",
        "get_geopolitical_events": "FRED + news APIs",
    }
    return sources.get(tool_name, f"Tool: {tool_name}")
