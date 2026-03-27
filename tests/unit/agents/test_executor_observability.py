"""Tests for tool execution observability in executor."""

from unittest.mock import AsyncMock

import pytest

from backend.agents.observability import ObservabilityCollector
from backend.tools.base import ToolResult


class TestExecutorObservability:
    """Tests for executor recording tool execution events."""

    @pytest.mark.asyncio
    async def test_successful_tool_records_event(self) -> None:
        """A successful tool execution should record to collector."""
        from backend.agents.executor import execute_plan

        collector = ObservabilityCollector()
        collector.record_tool_execution = AsyncMock()

        tool_executor = AsyncMock(
            return_value=ToolResult(status="ok", data={"ticker": "AAPL", "price": 150.0})
        )

        steps = [{"tool": "analyze_stock", "params": {"ticker": "AAPL"}}]
        await execute_plan(steps, tool_executor, collector=collector)

        collector.record_tool_execution.assert_called_once()
        call_kwargs = collector.record_tool_execution.call_args[1]
        assert call_kwargs["tool_name"] == "analyze_stock"
        assert call_kwargs["status"] == "ok"
        assert call_kwargs["latency_ms"] >= 0

    @pytest.mark.asyncio
    async def test_failed_tool_records_error(self) -> None:
        """A failed tool execution should record error to collector."""
        from backend.agents.executor import execute_plan

        collector = ObservabilityCollector()
        collector.record_tool_execution = AsyncMock()

        tool_executor = AsyncMock(side_effect=Exception("tool crashed"))

        steps = [{"tool": "analyze_stock", "params": {"ticker": "AAPL"}}]
        await execute_plan(steps, tool_executor, collector=collector)

        collector.record_tool_execution.assert_called_once()
        call_kwargs = collector.record_tool_execution.call_args[1]
        assert call_kwargs["tool_name"] == "analyze_stock"
        assert call_kwargs["status"] == "error"
        assert "tool crashed" in call_kwargs["error"]

    @pytest.mark.asyncio
    async def test_no_collector_still_works(self) -> None:
        """Executor without collector should work as before."""
        from backend.agents.executor import execute_plan

        tool_executor = AsyncMock(return_value=ToolResult(status="ok", data={"ticker": "AAPL"}))

        steps = [{"tool": "analyze_stock", "params": {"ticker": "AAPL"}}]
        result = await execute_plan(steps, tool_executor)
        assert result["tool_calls"] == 1
        assert len(result["results"]) == 1

    @pytest.mark.asyncio
    async def test_cache_hit_records_with_cache_hit_true(self) -> None:
        """A cache hit should record tool execution with cache_hit=True and latency_ms=0."""

        from backend.agents.executor import execute_plan

        collector = ObservabilityCollector()
        collector.record_tool_execution = AsyncMock()

        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock(return_value='{"status": "ok", "ticker": "AAPL"}')

        tool_executor = AsyncMock(return_value=ToolResult(status="ok", data={}))

        steps = [{"tool": "analyze_stock", "params": {"ticker": "AAPL"}}]
        await execute_plan(
            steps,
            tool_executor,
            collector=collector,
            cache=mock_cache,
            session_id="test-session",
        )

        collector.record_tool_execution.assert_called_once()
        call_kwargs = collector.record_tool_execution.call_args[1]
        assert call_kwargs["cache_hit"] is True
        assert call_kwargs["latency_ms"] == 0
        assert call_kwargs["tool_name"] == "analyze_stock"
        # Tool executor should NOT have been called (cache hit)
        tool_executor.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_records_with_cache_hit_false(self) -> None:
        """A normal (non-cached) tool execution should record cache_hit=False."""
        from backend.agents.executor import execute_plan

        collector = ObservabilityCollector()
        collector.record_tool_execution = AsyncMock()

        tool_executor = AsyncMock(
            return_value=ToolResult(status="ok", data={"ticker": "AAPL", "price": 150.0})
        )

        steps = [{"tool": "analyze_stock", "params": {"ticker": "AAPL"}}]
        await execute_plan(steps, tool_executor, collector=collector)

        collector.record_tool_execution.assert_called_once()
        call_kwargs = collector.record_tool_execution.call_args[1]
        assert call_kwargs["cache_hit"] is False
