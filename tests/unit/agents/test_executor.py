"""Tests for mechanical executor."""

from unittest.mock import patch

import pytest

from backend.agents.executor import (
    CIRCUIT_BREAKER_THRESHOLD,
    MAX_TOOL_CALLS,
    _resolve_prev_result,
    execute_plan,
)
from backend.tools.base import ToolResult


class TestResolvePrevResult:
    """Tests for $PREV_RESULT resolution."""

    def test_no_reference_passthrough(self) -> None:
        """Values without $PREV_RESULT pass through unchanged."""
        assert _resolve_prev_result("AAPL", []) == "AAPL"

    def test_resolves_ticker_from_prev(self) -> None:
        """$PREV_RESULT.ticker resolves from last result's data."""
        prev = [{"status": "ok", "data": {"ticker": "PLTR", "name": "Palantir"}}]
        assert _resolve_prev_result("$PREV_RESULT.ticker", prev) == "PLTR"

    def test_skips_failed_results(self) -> None:
        """Should skip unavailable results and use last successful one."""
        prev = [
            {"status": "ok", "data": {"ticker": "AAPL"}},
            {"status": "unavailable", "data": None},
        ]
        assert _resolve_prev_result("$PREV_RESULT.ticker", prev) == "AAPL"

    def test_no_results_returns_raw(self) -> None:
        """With no prior results, return the raw string."""
        assert _resolve_prev_result("$PREV_RESULT.ticker", []) == "$PREV_RESULT.ticker"


class TestExecutePlan:
    """Tests for execute_plan."""

    @pytest.mark.asyncio
    async def test_runs_plan_in_order(self) -> None:
        """Executor calls tools in plan order."""
        call_order = []

        async def mock_executor(tool_name: str, params: dict) -> ToolResult:
            call_order.append(tool_name)
            return ToolResult(status="ok", data={"ticker": "PLTR"})

        steps = [
            {"tool": "search_stocks", "params": {"query": "Palantir"}},
            {"tool": "analyze_stock", "params": {"ticker": "$PREV_RESULT.ticker"}},
        ]
        result = await execute_plan(steps, mock_executor)

        assert call_order == ["search_stocks", "analyze_stock"]
        assert len(result["results"]) == 2
        assert result["tool_calls"] == 2

    @pytest.mark.asyncio
    async def test_resolves_prev_result(self) -> None:
        """$PREV_RESULT.ticker resolves from previous tool output."""
        captured_params = []

        async def mock_executor(tool_name: str, params: dict) -> ToolResult:
            captured_params.append(params)
            if tool_name == "search_stocks":
                return ToolResult(status="ok", data=[{"ticker": "PLTR", "name": "Palantir"}])
            return ToolResult(status="ok", data={"ticker": params.get("ticker")})

        steps = [
            {"tool": "search_stocks", "params": {"query": "Palantir"}},
            {"tool": "analyze_stock", "params": {"ticker": "$PREV_RESULT.ticker"}},
        ]
        await execute_plan(steps, mock_executor)

        # Second call should have resolved ticker
        assert captured_params[1]["ticker"] == "PLTR"

    @pytest.mark.asyncio
    async def test_retries_on_failure(self) -> None:
        """Failed tool is retried once before marking unavailable."""
        call_count = 0

        async def flaky_executor(tool_name: str, params: dict) -> ToolResult:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("Transient error")
            return ToolResult(status="ok", data={"ticker": "AAPL"})

        steps = [{"tool": "analyze_stock", "params": {"ticker": "AAPL"}}]
        result = await execute_plan(steps, flaky_executor)

        assert call_count == 2  # original + 1 retry
        assert result["results"][0]["status"] == "ok"

    @pytest.mark.asyncio
    async def test_circuit_breaker(self) -> None:
        """N consecutive failures triggers circuit breaker."""

        async def failing_executor(tool_name: str, params: dict) -> ToolResult:
            return ToolResult(status="error", error="always fails")

        steps = [{"tool": f"tool_{i}", "params": {}} for i in range(5)]
        result = await execute_plan(steps, failing_executor)

        assert result["circuit_broken"] is True
        assert result["tool_calls"] == CIRCUIT_BREAKER_THRESHOLD

    @pytest.mark.asyncio
    async def test_respects_tool_limit(self) -> None:
        """Executor stops after MAX_TOOL_CALLS."""

        async def mock_executor(tool_name: str, params: dict) -> ToolResult:
            return ToolResult(status="ok", data={})

        steps = [{"tool": f"tool_{i}", "params": {}} for i in range(15)]
        result = await execute_plan(steps, mock_executor)

        assert result["tool_calls"] == MAX_TOOL_CALLS

    @pytest.mark.asyncio
    async def test_flags_replan_on_empty_search(self) -> None:
        """Empty search_stocks result flags for re-plan."""

        async def mock_executor(tool_name: str, params: dict) -> ToolResult:
            return ToolResult(status="ok", data=[])

        steps = [
            {"tool": "search_stocks", "params": {"query": "ZZZZZZ"}},
            {"tool": "analyze_stock", "params": {"ticker": "ZZZZZZ"}},
        ]
        result = await execute_plan(steps, mock_executor)

        assert result["needs_replan"] is True
        assert result["tool_calls"] == 1  # stopped after search

    @pytest.mark.asyncio
    @pytest.mark.regression
    async def test_tool_exception_logging_does_not_expose_str_e(self) -> None:
        """Regression: executor warning log must use error_type, not str(e).

        Verifies that when a tool raises an exception, the structured logging
        extra dict contains 'error_type' (the exception class name) and NOT
        'error' (the raw str(e) message), preventing internal detail leakage.
        """
        error_message = "internal db connection string: user=admin pass=secret"

        async def raising_executor(tool_name: str, params: dict) -> ToolResult:
            raise ValueError(error_message)

        steps = [{"tool": "analyze_stock", "params": {"ticker": "AAPL"}}]

        with patch("backend.agents.executor.logger") as mock_logger:
            await execute_plan(steps, raising_executor)

        # Collect all warning calls' extra dicts
        warning_extras = [
            call.kwargs.get("extra", {})
            for call in mock_logger.warning.call_args_list
            if call.args and call.args[0] == "executor_tool_error"
        ]

        assert warning_extras, "Expected at least one executor_tool_error warning"
        for extra in warning_extras:
            assert "error_type" in extra, "extra dict must have 'error_type' key"
            assert "error" not in extra, "extra dict must NOT have raw 'error' key"
            assert extra["error_type"] == "ValueError"
            # Confirm raw error message is not present anywhere in the extra dict
            assert error_message not in str(extra)

    @pytest.mark.asyncio
    async def test_calls_on_step_callback(self) -> None:
        """on_step callback fires for each completed step."""
        events = []

        async def mock_executor(tool_name: str, params: dict) -> ToolResult:
            return ToolResult(status="ok", data={"ticker": "AAPL"})

        async def on_step(idx: int, tool: str, status: str) -> None:
            events.append((idx, tool, status))

        steps = [
            {"tool": "analyze_stock", "params": {"ticker": "AAPL"}},
            {"tool": "get_fundamentals", "params": {"ticker": "AAPL"}},
        ]
        await execute_plan(steps, mock_executor, on_step=on_step)

        assert len(events) == 2
        assert events[0] == (0, "analyze_stock", "ok")
        assert events[1] == (1, "get_fundamentals", "ok")
