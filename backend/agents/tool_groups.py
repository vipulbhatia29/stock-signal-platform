"""Tool Groups — intent-based tool filtering for the ReAct agent.

Maps each intent category to a curated list of tool names. The agent uses
this to restrict the tool set available per query, reducing token usage and
improving focus.
"""

from __future__ import annotations

import logging

from backend.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

# Maps intent → list of tool name strings (None means "all tools").
TOOL_GROUPS: dict[str, list[str] | None] = {
    "stock": [
        "analyze_stock",
        "get_fundamentals",
        "get_forecast",
        "get_stock_intelligence",
        "get_earnings_history",
        "get_company_profile",
        "get_analyst_targets",
        "risk_narrative",
        "dividend_sustainability",
        "get_recommendation_scorecard",
    ],  # 10 tools
    "portfolio": [
        "get_portfolio_exposure",
        "portfolio_health",
        "get_portfolio_forecast",
        "recommend_stocks",
        "dividend_sustainability",
        "risk_narrative",
        "analyze_stock",  # for drill-down into holdings
        "get_fundamentals",
        "market_briefing",
        "get_forecast",
        "get_recommendation_scorecard",
    ],  # 11 tools
    "market": [
        "market_briefing",
        "get_sector_forecast",
        "screen_stocks",
        "get_forecast",
        "recommend_stocks",
    ],  # 5 tools
    "comparison": [
        "analyze_stock",
        "get_fundamentals",
        "get_forecast",
        "compare_stocks",
        "get_stock_intelligence",
    ],  # 5 tools
    "simple_lookup": [
        "analyze_stock",
    ],  # 1 tool (fast path only uses this)
    "general": None,  # all tools (fallback)
}


def get_tool_schemas_for_group(
    tool_group: str | None,
    registry: ToolRegistry,
) -> list[dict]:
    """Return OpenAI function-calling schemas for the tools in a group.

    Looks up the tool names for the given intent group and resolves each to a
    schema via the registry. Unknown groups and ``None`` both fall back to
    returning schemas for every registered tool.

    Args:
        tool_group: Intent group key (e.g. ``"stock"``, ``"portfolio"``), or
            ``None`` to return all tools.
        registry: The populated :class:`~backend.tools.registry.ToolRegistry`
            to resolve tool names from.

    Returns:
        A list of OpenAI-compatible function-calling schema dicts, each with
        ``{"type": "function", "function": {...}}``.
    """
    tool_names = TOOL_GROUPS.get(tool_group) if tool_group is not None else None  # type: ignore[arg-type]

    # None value (from "general" key) or unknown group key → all tools
    if tool_names is None:
        return [info.to_llm_schema() for info in registry.discover()]

    schemas: list[dict] = []
    for name in tool_names:
        try:
            tool = registry.get(name)
        except KeyError:
            logger.warning(
                "tool_group_missing_tool",
                extra={"group": tool_group, "tool": name},
            )
            continue
        schemas.append(tool.info().to_llm_schema())

    return schemas
