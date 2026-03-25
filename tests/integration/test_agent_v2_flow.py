"""Integration tests for Agent V2 three-phase flow.

Tests the full plan→execute→synthesize pipeline with mocked LLM and tools.
No real API calls or DB connections — validates graph routing and data flow.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from backend.agents.graph import AgentStateV2, build_agent_graph
from backend.tools.base import ToolResult


def _make_plan_fn(plan_response: dict) -> Any:
    """Create a mock plan function that returns a fixed plan."""

    async def plan_fn(
        query: str,
        tools_description: str,
        user_context: dict,
    ) -> dict:
        return plan_response

    return plan_fn


def _make_synthesize_fn(synthesis: dict) -> Any:
    """Create a mock synthesize function returning a fixed synthesis."""

    async def synthesize_fn(
        tool_results: list[dict],
        user_context: dict,
    ) -> dict:
        return synthesis

    return synthesize_fn


def _make_tool_executor(responses: dict[str, ToolResult]) -> Any:
    """Create a mock tool executor returning fixed results per tool name."""

    async def tool_executor(tool_name: str, params: dict) -> ToolResult:
        return responses.get(tool_name, ToolResult(status="ok", data={}))

    return tool_executor


def _initial_state(query: str = "Analyze PLTR") -> AgentStateV2:
    """Create a minimal initial state for the graph."""
    return AgentStateV2(
        messages=[{"role": "user", "content": query}],
        phase="plan",
        plan={},
        tool_results=[],
        synthesis={},
        iteration=0,
        replan_count=0,
        start_time=0.0,
        user_context={},
        query_id="test-query-id",
        skip_synthesis=False,
        response_text="",
        decline_message="",
    )


class TestFullAnalysisFlow:
    """Test the happy path: plan → execute → synthesize."""

    @pytest.mark.asyncio
    async def test_full_flow_produces_synthesis(self) -> None:
        """Full analysis flow should produce a synthesis with confidence."""
        plan = {
            "intent": "stock_analysis",
            "reasoning": "Analyze PLTR",
            "skip_synthesis": False,
            "steps": [
                {"tool": "get_fundamentals", "params": {"ticker": "PLTR"}},
                {"tool": "get_analyst_targets", "params": {"ticker": "PLTR"}},
            ],
        }
        synthesis = {
            "confidence": 0.75,
            "confidence_label": "high",
            "summary": "PLTR looks strong.",
            "scenarios": {},
            "evidence": [],
            "gaps": [],
        }
        tool_responses = {
            "get_fundamentals": ToolResult(
                status="ok", data={"ticker": "PLTR", "revenue_growth": 0.21}
            ),
            "get_analyst_targets": ToolResult(
                status="ok", data={"ticker": "PLTR", "has_targets": True, "target_mean": 186.6}
            ),
        }

        graph = build_agent_graph(
            plan_fn=_make_plan_fn(plan),
            execute_fn=AsyncMock(
                return_value={
                    "results": [
                        {"tool": "get_fundamentals", "status": "ok", "data": {"ticker": "PLTR"}},
                        {
                            "tool": "get_analyst_targets",
                            "status": "ok",
                            "data": {"target_mean": 186.6},
                        },
                    ],
                    "needs_replan": False,
                    "timed_out": False,
                    "circuit_broken": False,
                    "tool_calls": 2,
                }
            ),
            synthesize_fn=_make_synthesize_fn(synthesis),
            format_simple_fn=lambda t, d: str(d),
            tool_executor=_make_tool_executor(tool_responses),
            tools_description="test tools",
        )

        result = await graph.ainvoke(_initial_state("Analyze PLTR"))

        assert result["synthesis"]["confidence"] == 0.75
        assert result["response_text"] == "PLTR looks strong."


class TestOutOfScopeFlow:
    """Test out-of-scope queries exit at plan phase."""

    @pytest.mark.asyncio
    async def test_out_of_scope_exits_without_execution(self) -> None:
        """Out-of-scope query should exit after plan, no tools called."""
        plan = {
            "intent": "out_of_scope",
            "reasoning": "Not financial",
            "decline_message": "I focus on financial analysis.",
            "skip_synthesis": True,
            "steps": [],
        }

        execute_fn = AsyncMock()  # Should never be called

        graph = build_agent_graph(
            plan_fn=_make_plan_fn(plan),
            execute_fn=execute_fn,
            synthesize_fn=_make_synthesize_fn({}),
            format_simple_fn=lambda t, d: str(d),
            tool_executor=_make_tool_executor({}),
            tools_description="test tools",
        )

        result = await graph.ainvoke(_initial_state("What is the capital of Uganda?"))

        assert result["plan"]["intent"] == "out_of_scope"
        assert result["decline_message"] == "I focus on financial analysis."
        execute_fn.assert_not_called()


class TestSimpleQueryFlow:
    """Test simple queries skip synthesis."""

    @pytest.mark.asyncio
    async def test_simple_query_uses_formatter(self) -> None:
        """Simple lookup should go plan → execute → format_simple, no synthesizer."""
        plan = {
            "intent": "simple_lookup",
            "reasoning": "Single tool lookup",
            "skip_synthesis": True,
            "steps": [{"tool": "analyze_stock", "params": {"ticker": "AAPL"}}],
        }

        synthesize_fn = AsyncMock()  # Should never be called

        graph = build_agent_graph(
            plan_fn=_make_plan_fn(plan),
            execute_fn=AsyncMock(
                return_value={
                    "results": [
                        {
                            "tool": "analyze_stock",
                            "status": "ok",
                            "data": {"ticker": "AAPL", "composite_score": 7.5},
                        }
                    ],
                    "needs_replan": False,
                    "timed_out": False,
                    "circuit_broken": False,
                    "tool_calls": 1,
                }
            ),
            synthesize_fn=synthesize_fn,
            format_simple_fn=lambda t, d: f"{d.get('ticker')} score: {d.get('composite_score')}",
            tool_executor=_make_tool_executor({}),
            tools_description="test tools",
        )

        result = await graph.ainvoke(_initial_state("What's AAPL price?"))

        assert "AAPL" in result["response_text"]
        assert "7.5" in result["response_text"]
        synthesize_fn.assert_not_called()


class TestCircuitBreakerFlow:
    """Test circuit breaker exits to partial synthesis."""

    @pytest.mark.asyncio
    async def test_circuit_breaker_still_synthesizes(self) -> None:
        """When circuit breaks, partial results go to synthesis."""
        plan = {
            "intent": "stock_analysis",
            "skip_synthesis": False,
            "steps": [
                {"tool": "tool_1", "params": {}},
                {"tool": "tool_2", "params": {}},
            ],
        }
        synthesis = {
            "confidence": 0.35,
            "confidence_label": "low",
            "summary": "Limited data available.",
            "gaps": ["Multiple tools failed"],
        }

        graph = build_agent_graph(
            plan_fn=_make_plan_fn(plan),
            execute_fn=AsyncMock(
                return_value={
                    "results": [
                        {"tool": "tool_1", "status": "unavailable", "data": None},
                    ],
                    "needs_replan": False,
                    "timed_out": False,
                    "circuit_broken": True,
                    "tool_calls": 3,
                }
            ),
            synthesize_fn=_make_synthesize_fn(synthesis),
            format_simple_fn=lambda t, d: str(d),
            tool_executor=_make_tool_executor({}),
            tools_description="test tools",
        )

        result = await graph.ainvoke(_initial_state("Analyze PLTR"))

        assert result["synthesis"]["confidence"] == 0.35
        assert "Limited data" in result["response_text"]
