"""Tests for agent tool result session caching in executor."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from backend.services.cache import CacheService
from backend.tools.base import ToolResult


class TestToolResultCache:
    """Tests for tool result session caching."""

    @pytest.mark.asyncio
    async def test_cache_hit_skips_execution(self) -> None:
        """A cached tool result should skip tool execution."""
        from backend.agents.executor import execute_plan

        mock_redis = AsyncMock()
        cached_result = json.dumps(
            {"status": "ok", "data": {"ticker": "AAPL"}, "tool": "analyze_stock"}
        )
        mock_redis.get = AsyncMock(return_value=cached_result)
        mock_redis.set = AsyncMock()
        cache = CacheService(mock_redis)

        tool_executor = AsyncMock()
        steps = [{"tool": "analyze_stock", "params": {"ticker": "AAPL"}}]
        result = await execute_plan(steps, tool_executor, cache=cache, session_id="sess-123")

        tool_executor.assert_not_called()
        assert len(result["results"]) == 1

    @pytest.mark.asyncio
    async def test_cache_miss_executes_and_stores(self) -> None:
        """A cache miss should execute the tool and store the result."""
        from backend.agents.executor import execute_plan

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock()
        cache = CacheService(mock_redis)

        tool_executor = AsyncMock(
            return_value=ToolResult(status="ok", data={"ticker": "AAPL", "score": 8.5})
        )
        steps = [{"tool": "analyze_stock", "params": {"ticker": "AAPL"}}]
        await execute_plan(steps, tool_executor, cache=cache, session_id="sess-123")

        tool_executor.assert_called_once()
        mock_redis.set.assert_awaited()

    @pytest.mark.asyncio
    async def test_uncacheable_tool_always_executes(self) -> None:
        """Tools not in CACHEABLE_TOOLS should always execute and never cache."""
        from backend.agents.executor import execute_plan

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock()
        cache = CacheService(mock_redis)

        tool_executor = AsyncMock(return_value=ToolResult(status="ok", data={"results": []}))
        steps = [{"tool": "search_stocks", "params": {"query": "tech"}}]
        await execute_plan(steps, tool_executor, cache=cache, session_id="sess-123")

        tool_executor.assert_called_once()
        # search_stocks is NOT cacheable — should not call redis.get
        mock_redis.get.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_cache_still_works(self) -> None:
        """Executor without cache should work as before."""
        from backend.agents.executor import execute_plan

        tool_executor = AsyncMock(return_value=ToolResult(status="ok", data={"ticker": "AAPL"}))
        steps = [{"tool": "analyze_stock", "params": {"ticker": "AAPL"}}]
        await execute_plan(steps, tool_executor)
        tool_executor.assert_called_once()
