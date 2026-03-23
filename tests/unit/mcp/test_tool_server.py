"""Tests for MCP tool server — build_registry and ToolResult serialization."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from backend.tools.base import ToolResult
from backend.tools.build_registry import INTERNAL_TOOL_CLASSES, build_registry

# ---------------------------------------------------------------------------
# T1.1 — build_registry tests
# ---------------------------------------------------------------------------


class TestBuildRegistry:
    """Tests for the build_registry() function."""

    def test_build_registry_returns_all_tools(self) -> None:
        """Verify build_registry() returns 20 internal + 12 adapter = 32 tools."""
        registry = build_registry()
        tools = registry.discover()
        assert len(tools) == 32, f"Expected 32 tools, got {len(tools)}"

    def test_build_registry_has_expected_tool_names(self) -> None:
        """Check that specific well-known tool names are present."""
        registry = build_registry()
        tool_names = {t.name for t in registry.discover()}

        expected_names = {
            "analyze_stock",
            "screen_stocks",
            "compute_signals",
            "get_recommendations",
            "web_search",
            "search_stocks",
            "ingest_stock",
            "get_fundamentals",
            "get_forecast",
            "get_portfolio_forecast",
            "compare_stocks",
            "get_recommendation_scorecard",
            "dividend_sustainability",
            "risk_narrative",
            # Adapter tools
            "get_10k_section",
            "get_news_sentiment",
            "get_economic_series",
            "get_analyst_ratings",
        }
        missing = expected_names - tool_names
        assert not missing, f"Missing tools: {missing}"

    def test_build_registry_internal_tool_count(self) -> None:
        """Verify the INTERNAL_TOOL_CLASSES list has 20 entries."""
        assert len(INTERNAL_TOOL_CLASSES) == 20


# ---------------------------------------------------------------------------
# T1.2 — ToolResult JSON serialization tests
# ---------------------------------------------------------------------------


class TestToolResultSerialization:
    """Tests for ToolResult.to_json() and ToolResult.from_json()."""

    def test_tool_result_to_json_ok(self) -> None:
        """ToolResult with data serializes to valid JSON."""
        result = ToolResult(
            status="ok",
            data={"ticker": "AAPL", "price": 150.25, "signals": [1, 2, 3]},
        )
        json_str = result.to_json()
        assert '"status": "ok"' in json_str
        assert '"ticker": "AAPL"' in json_str
        assert '"price": 150.25' in json_str

    def test_tool_result_to_json_error(self) -> None:
        """ToolResult with error serializes correctly."""
        result = ToolResult(status="error", error="Tool timed out")
        json_str = result.to_json()
        assert '"status": "error"' in json_str
        assert '"error": "Tool timed out"' in json_str
        assert '"data": null' in json_str

    def test_tool_result_from_json_round_trip(self) -> None:
        """to_json -> from_json preserves all fields."""
        original = ToolResult(
            status="ok",
            data={"scores": [0.8, 0.9], "name": "test"},
            error=None,
        )
        restored = ToolResult.from_json(original.to_json())
        assert restored.status == original.status
        assert restored.data == original.data
        assert restored.error == original.error

    def test_tool_result_from_json_with_datetime(self) -> None:
        """Datetime objects are serialized to ISO strings and survive round-trip."""
        dt = datetime(2026, 3, 23, 14, 30, 0, tzinfo=timezone.utc)
        original = ToolResult(
            status="ok",
            data={"timestamp": dt, "date": date(2026, 3, 23)},
        )
        json_str = original.to_json()
        assert "2026-03-23T14:30:00+00:00" in json_str
        assert "2026-03-23" in json_str

        restored = ToolResult.from_json(json_str)
        assert restored.status == "ok"
        # Datetimes become strings after round-trip (expected behavior)
        assert restored.data["timestamp"] == "2026-03-23T14:30:00+00:00"
        assert restored.data["date"] == "2026-03-23"

    def test_tool_result_to_json_with_decimal(self) -> None:
        """Decimal values are serialized as floats."""
        result = ToolResult(
            status="ok",
            data={"price": Decimal("150.75"), "ratio": Decimal("0.123")},
        )
        json_str = result.to_json()
        assert "150.75" in json_str
        assert "0.123" in json_str

    def test_tool_result_from_json_error_round_trip(self) -> None:
        """Error ToolResult survives round-trip."""
        original = ToolResult(status="error", data=None, error="Not found")
        restored = ToolResult.from_json(original.to_json())
        assert restored.status == "error"
        assert restored.data is None
        assert restored.error == "Not found"

    def test_tool_result_to_json_degraded_status(self) -> None:
        """Degraded status with partial data serializes correctly."""
        result = ToolResult(
            status="degraded",
            data={"partial": True},
            error="Some sources unavailable",
        )
        json_str = result.to_json()
        restored = ToolResult.from_json(json_str)
        assert restored.status == "degraded"
        assert restored.data == {"partial": True}
        assert restored.error == "Some sources unavailable"
