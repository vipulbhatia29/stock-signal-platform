"""Template-based formatter for simple queries (no LLM needed).

Used by the planner when a query maps to a single tool call with
skip_synthesis=True (e.g., "What is AAPL's price?").
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def format_simple_result(tool_name: str, data: dict[str, Any] | Any) -> str:
    """Format a single tool result into a human-readable string.

    Args:
        tool_name: Name of the tool that produced this result.
        data: The tool's result data (usually a dict).

    Returns:
        Formatted string suitable for direct display to the user.
    """
    if not isinstance(data, dict):
        return str(data)

    formatter = _FORMATTERS.get(tool_name, _format_default)
    try:
        return formatter(data)
    except (KeyError, TypeError, ValueError):
        logger.warning("simple_format_fallback", extra={"tool": tool_name})
        return _format_default(data)


def _format_analyze_stock(data: dict[str, Any]) -> str:
    """Format analyze_stock result."""
    ticker = data.get("ticker", "?")
    score = data.get("composite_score")
    rsi = data.get("rsi_signal", "n/a")
    macd = data.get("macd_signal_label", "n/a")
    sma = data.get("sma_signal", "n/a")
    score_str = f"{score:.1f}/10" if score is not None else "n/a"
    return (
        f"**{ticker}** has a composite score of {score_str}. "
        f"RSI: {rsi}, MACD: {macd}, SMA trend: {sma}."
    )


def _format_company_profile(data: dict[str, Any]) -> str:
    """Format get_company_profile result."""
    name = data.get("name", "Unknown")
    ticker = data.get("ticker", "?")
    sector = data.get("sector", "n/a")
    industry = data.get("industry", "n/a")
    mcap = data.get("market_cap")
    mcap_str = _format_market_cap(mcap) if mcap else "n/a"
    summary = data.get("summary", "")
    parts = [f"**{name}** ({ticker}) — {sector}, {industry}. Market cap: {mcap_str}."]
    if summary:
        parts.append(summary)
    return " ".join(parts)


def _format_fundamentals(data: dict[str, Any]) -> str:
    """Format get_fundamentals result."""
    ticker = data.get("ticker", "?")
    parts = [f"**{ticker} Fundamentals:**"]
    for label, key, fmt in [
        ("P/E", "pe_ratio", ".1f"),
        ("Revenue Growth", "revenue_growth", ".1%"),
        ("Gross Margins", "gross_margins", ".1%"),
        ("ROE", "return_on_equity", ".1%"),
    ]:
        val = data.get(key)
        if val is not None:
            parts.append(f"{label}: {val:{fmt}}")
    mcap = data.get("market_cap")
    if mcap:
        parts.append(f"Market Cap: {_format_market_cap(mcap)}")
    return " | ".join(parts)


def _format_analyst_targets(data: dict[str, Any]) -> str:
    """Format get_analyst_targets result."""
    if not data.get("has_targets"):
        return f"No analyst target data available for {data.get('ticker', 'this ticker')}."
    ticker = data.get("ticker", "?")
    mean = data.get("target_mean")
    high = data.get("target_high")
    low = data.get("target_low")
    buy = data.get("buy_count", 0)
    hold = data.get("hold_count", 0)
    sell = data.get("sell_count", 0)
    return (
        f"**{ticker} Analyst Targets:** Mean ${mean:.2f} "
        f"(Low ${low:.2f} — High ${high:.2f}). "
        f"Consensus: {buy} Buy, {hold} Hold, {sell} Sell."
    )


def _format_earnings(data: dict[str, Any]) -> str:
    """Format get_earnings_history result."""
    if not data.get("has_earnings"):
        return f"No earnings data available for {data.get('ticker', 'this ticker')}."
    ticker = data.get("ticker", "?")
    summary = data.get("summary", "")
    return f"**{ticker} Earnings:** {summary}."


def _format_search(data: list | dict) -> str:
    """Format search_stocks result."""
    if isinstance(data, list):
        if not data:
            return "No matching stocks found."
        lines = [f"- **{s.get('ticker')}** — {s.get('name', '?')}" for s in data[:5]]
        return "Found:\n" + "\n".join(lines)
    return _format_default(data)


def _format_default(data: dict[str, Any] | Any) -> str:
    """Fallback: JSON summary of top-level keys."""
    if isinstance(data, dict):
        # Summarize top-level keys with truncated values
        parts = []
        for k, v in list(data.items())[:8]:
            if isinstance(v, str) and len(v) > 80:
                v = v[:77] + "..."
            parts.append(f"**{k}:** {v}")
        return " | ".join(parts)
    return str(data)


def _format_market_cap(mcap: float) -> str:
    """Format market cap as human-readable string."""
    if mcap >= 1e12:
        return f"${mcap / 1e12:.2f}T"
    if mcap >= 1e9:
        return f"${mcap / 1e9:.1f}B"
    if mcap >= 1e6:
        return f"${mcap / 1e6:.0f}M"
    return f"${mcap:,.0f}"


_FORMATTERS: dict[str, Any] = {
    "analyze_stock": _format_analyze_stock,
    "get_company_profile": _format_company_profile,
    "get_fundamentals": _format_fundamentals,
    "get_analyst_targets": _format_analyst_targets,
    "get_earnings_history": _format_earnings,
    "search_stocks": _format_search,
}
