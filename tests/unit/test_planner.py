"""Tests for the planner node."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.agents.planner import (
    build_planner_prompt,
    parse_plan_response,
    plan_query,
)


class TestBuildPlannerPrompt:
    """Tests for prompt construction."""

    def test_injects_query(self) -> None:
        """Query should appear in the prompt."""
        prompt = build_planner_prompt("Analyze PLTR", "tool list", {})
        assert "Analyze PLTR" in prompt

    def test_injects_tools_description(self) -> None:
        """Tools description should be injected."""
        prompt = build_planner_prompt("test", "get_fundamentals: Get data", {})
        assert "get_fundamentals: Get data" in prompt

    def test_injects_user_context_with_holdings(self) -> None:
        """User holdings should appear in context."""
        ctx = {"held_tickers": ["AAPL", "PLTR"], "watchlist": [], "preferences": {}}
        prompt = build_planner_prompt("test", "tools", ctx)
        assert "AAPL" in prompt
        assert "PLTR" in prompt

    def test_empty_context_shows_no_data(self) -> None:
        """Empty context should show 'No portfolio data'."""
        prompt = build_planner_prompt("test", "tools", {})
        assert "No portfolio data" in prompt


class TestParsePlanResponse:
    """Tests for plan response parsing."""

    def test_parses_valid_json(self) -> None:
        """Valid JSON plan should parse correctly."""
        response = json.dumps(
            {
                "intent": "stock_analysis",
                "reasoning": "Analyze the stock",
                "skip_synthesis": False,
                "steps": [
                    {"tool": "analyze_stock", "params": {"ticker": "PLTR"}},
                ],
            }
        )
        plan = parse_plan_response(response)
        assert plan["intent"] == "stock_analysis"
        assert len(plan["steps"]) == 1
        assert plan["steps"][0]["tool"] == "analyze_stock"

    def test_strips_markdown_fences(self) -> None:
        """Should handle ```json ... ``` wrapping."""
        inner = json.dumps(
            {"intent": "simple_lookup", "steps": [{"tool": "search_stocks", "params": {}}]}
        )
        response = f"```json\n{inner}\n```"
        plan = parse_plan_response(response)
        assert plan["intent"] == "simple_lookup"

    def test_rejects_invalid_intent(self) -> None:
        """Invalid intent should raise ValueError."""
        response = json.dumps({"intent": "invalid_type", "steps": []})
        with pytest.raises(ValueError, match="Invalid intent"):
            parse_plan_response(response)

    def test_rejects_invalid_json(self) -> None:
        """Non-JSON response should raise ValueError."""
        with pytest.raises(ValueError, match="Failed to parse"):
            parse_plan_response("not json at all")

    def test_rejects_step_without_tool(self) -> None:
        """Step missing 'tool' key should raise ValueError."""
        response = json.dumps(
            {"intent": "stock_analysis", "steps": [{"params": {"ticker": "X"}}]}
        )
        with pytest.raises(ValueError, match="missing 'tool'"):
            parse_plan_response(response)

    def test_truncates_excessive_steps(self) -> None:
        """Plans with >10 steps should be truncated."""
        steps = [{"tool": f"tool_{i}", "params": {}} for i in range(15)]
        response = json.dumps({"intent": "stock_analysis", "steps": steps})
        plan = parse_plan_response(response)
        assert len(plan["steps"]) == 10

    def test_out_of_scope_plan(self) -> None:
        """Out-of-scope plan should have empty steps."""
        response = json.dumps(
            {
                "intent": "out_of_scope",
                "reasoning": "Not financial",
                "decline_message": "I focus on financial analysis.",
                "skip_synthesis": True,
                "steps": [],
            }
        )
        plan = parse_plan_response(response)
        assert plan["intent"] == "out_of_scope"
        assert plan["steps"] == []
        assert plan["skip_synthesis"] is True


class TestPlanQuery:
    """Tests for the full plan_query function."""

    @pytest.mark.asyncio
    async def test_calls_llm_and_parses_response(self) -> None:
        """Should call LLM with prompt and parse JSON response."""
        mock_response = MagicMock()
        mock_response.content = json.dumps(
            {
                "intent": "stock_analysis",
                "reasoning": "Analyze PLTR",
                "skip_synthesis": False,
                "steps": [{"tool": "analyze_stock", "params": {"ticker": "PLTR"}}],
            }
        )
        mock_llm = AsyncMock(return_value=mock_response)

        plan = await plan_query(
            query="Analyze PLTR",
            tools_description="analyze_stock: Analyze a stock",
            user_context={},
            llm_chat=mock_llm,
        )

        assert plan["intent"] == "stock_analysis"
        assert len(plan["steps"]) == 1
        mock_llm.assert_called_once()

    @pytest.mark.asyncio
    async def test_includes_portfolio_context(self) -> None:
        """User context with holdings should be in the prompt."""
        mock_response = MagicMock()
        mock_response.content = json.dumps(
            {
                "intent": "portfolio",
                "steps": [{"tool": "get_portfolio_exposure", "params": {}}],
            }
        )
        mock_llm = AsyncMock(return_value=mock_response)

        await plan_query(
            query="Should I rebalance?",
            tools_description="tools",
            user_context={"held_tickers": ["AAPL"], "watchlist": [], "preferences": {}},
            llm_chat=mock_llm,
        )

        # Check that AAPL appears in the prompt sent to LLM
        call_args = mock_llm.call_args
        messages = call_args.kwargs.get("messages") or call_args[1].get("messages", [])
        prompt_text = messages[0]["content"]
        assert "AAPL" in prompt_text
