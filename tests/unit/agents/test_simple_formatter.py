"""Tests for simple query formatter."""

from backend.agents.simple_formatter import format_simple_result


class TestFormatSimpleResult:
    """Tests for format_simple_result."""

    def test_formats_analyze_stock(self) -> None:
        """Analyze stock result formatted as readable string."""
        data = {
            "ticker": "PLTR",
            "composite_score": 7.5,
            "rsi_signal": "neutral",
            "macd_signal_label": "bullish",
            "sma_signal": "bullish",
        }
        result = format_simple_result("analyze_stock", data)
        assert "PLTR" in result
        assert "7.5/10" in result
        assert "bullish" in result

    def test_formats_company_profile(self) -> None:
        """Company profile formatted with sector and market cap."""
        data = {
            "ticker": "AAPL",
            "name": "Apple Inc",
            "sector": "Technology",
            "industry": "Consumer Electronics",
            "market_cap": 3_000_000_000_000,
            "summary": "Apple designs consumer electronics.",
        }
        result = format_simple_result("get_company_profile", data)
        assert "Apple Inc" in result
        assert "$3.00T" in result
        assert "Technology" in result

    def test_formats_fundamentals(self) -> None:
        """Fundamentals formatted with P/E, growth, margins."""
        data = {
            "ticker": "PLTR",
            "pe_ratio": 120.5,
            "revenue_growth": 0.21,
            "gross_margins": 0.82,
            "return_on_equity": 0.26,
            "market_cap": 362_000_000_000,
        }
        result = format_simple_result("get_fundamentals", data)
        assert "120.5" in result
        assert "21.0%" in result
        assert "$362.0B" in result

    def test_formats_analyst_targets(self) -> None:
        """Analyst targets formatted with mean, range, consensus."""
        data = {
            "ticker": "PLTR",
            "has_targets": True,
            "target_mean": 186.60,
            "target_high": 260.0,
            "target_low": 70.0,
            "buy_count": 12,
            "hold_count": 5,
            "sell_count": 2,
        }
        result = format_simple_result("get_analyst_targets", data)
        assert "$186.60" in result
        assert "12 Buy" in result

    def test_formats_no_targets(self) -> None:
        """No targets returns informative message."""
        data = {"ticker": "TINY", "has_targets": False}
        result = format_simple_result("get_analyst_targets", data)
        assert "No analyst target" in result

    def test_formats_unknown_tool(self) -> None:
        """Unknown tool result formatted as key-value summary."""
        data = {"foo": "bar", "count": 42}
        result = format_simple_result("custom_tool", data)
        assert "foo" in result
        assert "bar" in result

    def test_handles_non_dict_data(self) -> None:
        """Non-dict data returns str representation."""
        result = format_simple_result("some_tool", "plain string")
        assert result == "plain string"

    def test_formats_search_results(self) -> None:
        """Search results formatted as bullet list."""
        data = [
            {"ticker": "AAPL", "name": "Apple Inc"},
            {"ticker": "AMZN", "name": "Amazon.com Inc"},
        ]
        result = format_simple_result("search_stocks", data)
        assert "AAPL" in result
        assert "AMZN" in result
