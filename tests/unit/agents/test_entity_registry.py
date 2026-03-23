"""Tests for the session entity registry."""

from __future__ import annotations

from backend.agents.entity_registry import EntityRegistry


class TestEntityRegistryAdd:
    """Tests for adding tickers to the registry."""

    def test_add_new_ticker(self) -> None:
        """Should add a new ticker to the registry."""
        registry = EntityRegistry()
        registry.add("AAPL", name="Apple Inc", source_tool="get_fundamentals")

        assert "AAPL" in registry.discussed_tickers
        assert registry.discussed_tickers["AAPL"].name == "Apple Inc"
        assert registry.discussed_tickers["AAPL"].mention_count == 1

    def test_add_updates_mention_count(self) -> None:
        """Should increment mention count for existing ticker."""
        registry = EntityRegistry()
        registry.add("AAPL")
        registry.add("AAPL")

        assert registry.discussed_tickers["AAPL"].mention_count == 2

    def test_add_moves_to_end(self) -> None:
        """Re-adding a ticker should move it to the end (most recent)."""
        registry = EntityRegistry()
        registry.add("AAPL")
        registry.add("MSFT")
        registry.add("AAPL")

        keys = list(registry.discussed_tickers.keys())
        assert keys == ["MSFT", "AAPL"]

    def test_add_normalizes_ticker(self) -> None:
        """Should uppercase and strip whitespace."""
        registry = EntityRegistry()
        registry.add("  aapl  ")

        assert "AAPL" in registry.discussed_tickers

    def test_add_empty_ticker_ignored(self) -> None:
        """Should ignore empty string tickers."""
        registry = EntityRegistry()
        registry.add("")

        assert len(registry.discussed_tickers) == 0


class TestEntityRegistryExtract:
    """Tests for extract_from_tool_result."""

    def test_extract_single_ticker(self) -> None:
        """Should extract ticker from a tool result with 'ticker' field."""
        registry = EntityRegistry()
        registry.extract_from_tool_result(
            "get_fundamentals",
            {"data": {"ticker": "NVDA", "name": "NVIDIA Corp"}},
        )

        assert "NVDA" in registry.discussed_tickers
        assert registry.discussed_tickers["NVDA"].name == "NVIDIA Corp"

    def test_extract_from_comparisons(self) -> None:
        """Should extract all tickers from comparison results."""
        registry = EntityRegistry()
        registry.extract_from_tool_result(
            "compare_stocks",
            {
                "data": {
                    "comparisons": [
                        {"ticker": "AAPL", "name": "Apple"},
                        {"ticker": "MSFT", "name": "Microsoft"},
                    ]
                }
            },
        )

        assert "AAPL" in registry.discussed_tickers
        assert "MSFT" in registry.discussed_tickers

    def test_extract_from_contributions(self) -> None:
        """Should extract tickers from portfolio contributions."""
        registry = EntityRegistry()
        registry.extract_from_tool_result(
            "get_portfolio_forecast",
            {
                "data": {
                    "contributions": [
                        {"ticker": "AAPL", "weight_pct": 30.0},
                        {"ticker": "TSLA", "weight_pct": 20.0},
                    ]
                }
            },
        )

        assert "AAPL" in registry.discussed_tickers
        assert "TSLA" in registry.discussed_tickers

    def test_extract_non_dict_is_noop(self) -> None:
        """Should safely handle non-dict results."""
        registry = EntityRegistry()
        registry.extract_from_tool_result("tool", "not a dict")

        assert len(registry.discussed_tickers) == 0


class TestEntityRegistryResolvePronouns:
    """Tests for pronoun resolution."""

    def test_resolve_it_returns_last_ticker(self) -> None:
        """'it' should resolve to the most recently discussed ticker."""
        registry = EntityRegistry()
        registry.add("AAPL")
        registry.add("NVDA")

        result = registry.resolve_pronouns("What about it?")
        assert result == ["NVDA"]

    def test_resolve_both_returns_last_two(self) -> None:
        """'both' should resolve to the two most recently discussed tickers."""
        registry = EntityRegistry()
        registry.add("AAPL")
        registry.add("MSFT")
        registry.add("NVDA")

        result = registry.resolve_pronouns("Compare both")
        assert result == ["MSFT", "NVDA"]

    def test_resolve_them_returns_last_multiple(self) -> None:
        """'them' should resolve to the 2+ most recently discussed tickers."""
        registry = EntityRegistry()
        registry.add("AAPL")
        registry.add("MSFT")
        registry.add("NVDA")

        result = registry.resolve_pronouns("Compare them")
        assert result == ["AAPL", "MSFT", "NVDA"]

    def test_resolve_empty_registry_returns_empty(self) -> None:
        """Empty registry should return empty list for any pronoun."""
        registry = EntityRegistry()

        result = registry.resolve_pronouns("Compare them")
        assert result == []

    def test_resolve_no_pronoun_returns_empty(self) -> None:
        """Non-pronoun query should return empty list."""
        registry = EntityRegistry()
        registry.add("AAPL")

        result = registry.resolve_pronouns("Analyze MSFT")
        assert result == []

    def test_resolve_this_stock_singular(self) -> None:
        """'this stock' should resolve to last ticker like 'it'."""
        registry = EntityRegistry()
        registry.add("TSLA")

        result = registry.resolve_pronouns("What about this stock?")
        assert result == ["TSLA"]


class TestEntityRegistryFormatting:
    """Tests for prompt formatting."""

    def test_format_for_prompt_empty(self) -> None:
        """Empty registry should return empty string."""
        registry = EntityRegistry()
        assert registry.format_for_prompt() == ""

    def test_format_for_prompt_with_tickers(self) -> None:
        """Should format tickers with names for prompt injection."""
        registry = EntityRegistry()
        registry.add("AAPL", name="Apple Inc")
        registry.add("MSFT")

        formatted = registry.format_for_prompt()
        assert "AAPL (Apple Inc)" in formatted
        assert "MSFT" in formatted

    def test_recent_tickers_limit(self) -> None:
        """Should respect the limit parameter."""
        registry = EntityRegistry()
        for t in ["A", "B", "C", "D", "E", "F"]:
            registry.add(t)

        assert len(registry.recent_tickers(limit=3)) == 3
        assert registry.recent_tickers(limit=3) == ["D", "E", "F"]
