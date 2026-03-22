"""Tests for tool result validator."""

from datetime import datetime, timedelta, timezone

from backend.agents.result_validator import validate_tool_result
from backend.tools.base import ToolResult


class TestValidateToolResult:
    """Tests for validate_tool_result."""

    def test_validates_null_result(self) -> None:
        """Null tool result should be marked unavailable."""
        result = ToolResult(status="ok", data=None)
        validated = validate_tool_result(result, "analyze_stock")
        assert validated["status"] == "unavailable"
        assert validated["reason"] == "No data returned"

    def test_handles_tool_error(self) -> None:
        """Tool returning error status is marked unavailable."""
        result = ToolResult(status="error", error="API timeout")
        validated = validate_tool_result(result, "web_search")
        assert validated["status"] == "unavailable"
        assert "API timeout" in validated["reason"]

    def test_handles_tool_timeout(self) -> None:
        """Tool timeout is marked unavailable."""
        result = ToolResult(status="timeout")
        validated = validate_tool_result(result, "analyze_stock")
        assert validated["status"] == "unavailable"
        assert "timed out" in validated["reason"]

    def test_passes_valid_result(self) -> None:
        """Valid tool result passes through with source annotation."""
        result = ToolResult(status="ok", data={"ticker": "AAPL", "composite_score": 7.5})
        now = datetime.now(timezone.utc)
        validated = validate_tool_result(result, "analyze_stock", timestamp=now)
        assert validated["status"] == "ok"
        assert validated["data"]["ticker"] == "AAPL"
        assert validated["source"] == "TimescaleDB (computed from yfinance prices)"
        assert validated["reason"] is None

    def test_flags_stale_price_data(self) -> None:
        """Price data >24h old during market hours flagged as stale."""
        now = datetime.now(timezone.utc)
        old_time = (now - timedelta(days=3)).isoformat()
        result = ToolResult(
            status="ok",
            data={"ticker": "AAPL", "last_fetched_at": old_time},
        )
        validated = validate_tool_result(result, "analyze_stock", timestamp=now)
        assert validated["status"] == "stale"
        assert "3d" in validated["reason"]

    def test_non_price_tool_not_checked_for_staleness(self) -> None:
        """Non-price tools should not be flagged stale."""
        now = datetime.now(timezone.utc)
        old_time = (now - timedelta(days=30)).isoformat()
        result = ToolResult(
            status="ok",
            data={"ticker": "AAPL", "last_fetched_at": old_time},
        )
        validated = validate_tool_result(result, "get_company_profile", timestamp=now)
        assert validated["status"] == "ok"

    def test_unknown_tool_gets_default_source(self) -> None:
        """Unknown tool name gets a generic source string."""
        result = ToolResult(status="ok", data={"foo": "bar"})
        validated = validate_tool_result(result, "custom_tool")
        assert validated["source"] == "Tool: custom_tool"
