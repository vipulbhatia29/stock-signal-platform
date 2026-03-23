"""Session entity registry for pronoun resolution in agent conversations.

Tracks which tickers have been discussed during an agent session so that
queries like "compare them" or "what about it?" can be resolved.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Patterns that indicate pronoun references to previously discussed tickers
_PRONOUN_PATTERNS: dict[str, str] = {
    "singular": r"\b(it|this stock|this one|that stock|that one|the stock)\b",
    "dual": r"\b(both|these two|those two|the two|the pair)\b",
    "plural": r"\b(them|these stocks|those stocks|all of them|these|those)\b",
}


@dataclass
class EntityInfo:
    """Metadata about a discussed ticker."""

    ticker: str
    name: str | None = None
    source_tool: str | None = None
    mention_count: int = 1


@dataclass
class EntityRegistry:
    """Tracks tickers discussed during an agent session.

    Maintains an ordered dict of tickers with metadata. New mentions
    move the ticker to the end (most recent). Pronoun resolution uses
    recency ordering.
    """

    discussed_tickers: dict[str, EntityInfo] = field(default_factory=dict)

    def add(
        self,
        ticker: str,
        name: str | None = None,
        source_tool: str | None = None,
    ) -> None:
        """Add or update a ticker in the registry."""
        ticker = ticker.upper().strip()
        if not ticker:
            return

        if ticker in self.discussed_tickers:
            entity = self.discussed_tickers.pop(ticker)
            entity.mention_count += 1
            if name:
                entity.name = name
            if source_tool:
                entity.source_tool = source_tool
            self.discussed_tickers[ticker] = entity
        else:
            self.discussed_tickers[ticker] = EntityInfo(
                ticker=ticker,
                name=name,
                source_tool=source_tool,
            )

    def extract_from_tool_result(
        self,
        tool_name: str,
        result: dict[str, Any],
    ) -> None:
        """Auto-populate registry from a tool result.

        Looks for common patterns in tool output: 'ticker' field,
        'comparisons' list, 'contributions' list, etc.
        """
        if not isinstance(result, dict):
            return

        data = result.get("data", result)
        if not isinstance(data, dict):
            return

        # Single ticker field
        if "ticker" in data:
            self.add(
                ticker=str(data["ticker"]),
                name=data.get("name"),
                source_tool=tool_name,
            )

        # Comparison results (CompareStocksTool)
        for item in data.get("comparisons", []):
            if isinstance(item, dict) and "ticker" in item:
                self.add(
                    ticker=str(item["ticker"]),
                    name=item.get("name"),
                    source_tool=tool_name,
                )

        # Portfolio contributions (GetPortfolioForecastTool)
        for item in data.get("contributions", []):
            if isinstance(item, dict) and "ticker" in item:
                self.add(
                    ticker=str(item["ticker"]),
                    source_tool=tool_name,
                )

    def resolve_pronouns(self, query: str) -> list[str]:
        """Resolve pronoun references in a query to ticker symbols.

        Args:
            query: User's natural language query.

        Returns:
            List of resolved tickers (empty if no pronouns detected
            or registry is empty).
        """
        if not self.discussed_tickers:
            return []

        query_lower = query.lower()
        ordered = list(self.discussed_tickers.keys())

        # Check singular pronouns → last 1 ticker
        if re.search(_PRONOUN_PATTERNS["singular"], query_lower):
            return ordered[-1:]

        # Check dual pronouns → last 2 tickers
        if re.search(_PRONOUN_PATTERNS["dual"], query_lower):
            return ordered[-2:] if len(ordered) >= 2 else ordered

        # Check plural pronouns → last 2+ tickers (up to 5)
        if re.search(_PRONOUN_PATTERNS["plural"], query_lower):
            return ordered[-5:] if len(ordered) >= 2 else ordered

        return []

    def recent_tickers(self, limit: int = 5) -> list[str]:
        """Return the most recently discussed tickers."""
        return list(self.discussed_tickers.keys())[-limit:]

    def format_for_prompt(self) -> str:
        """Format registry contents for injection into planner prompt."""
        if not self.discussed_tickers:
            return ""

        lines = ["Recently discussed tickers:"]
        for ticker, info in self.discussed_tickers.items():
            name_part = f" ({info.name})" if info.name else ""
            lines.append(f"  - {ticker}{name_part}")
        return "\n".join(lines)
