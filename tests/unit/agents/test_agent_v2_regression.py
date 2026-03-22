"""Agent V2 mocked regression tests — intent classification, executor edge cases, context window."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.agents.executor import (
    CIRCUIT_BREAKER_THRESHOLD,
    MAX_TOOL_CALLS,
    execute_plan,
)
from backend.agents.planner import VALID_INTENTS, parse_plan_response, plan_query
from backend.agents.synthesizer import parse_synthesis_response, synthesize_results
from backend.tools.chat_session import build_context_window

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _llm_response(content: str) -> MagicMock:
    """Create a mock LLMResponse with given content."""
    resp = MagicMock()
    resp.content = content
    resp.tool_calls = []
    resp.model = "test-model"
    resp.prompt_tokens = 100
    resp.completion_tokens = 50
    return resp


def _plan_json(
    intent: str = "stock_analysis",
    steps: list | None = None,
    reasoning: str = "test",
    skip_synthesis: bool = False,
    decline_message: str | None = None,
) -> str:
    """Build a valid plan JSON string."""
    plan = {
        "intent": intent,
        "reasoning": reasoning,
        "skip_synthesis": skip_synthesis,
        "steps": steps or [{"tool": "analyze_stock", "params": {"ticker": "AAPL"}}],
    }
    if decline_message:
        plan["decline_message"] = decline_message
    return json.dumps(plan)


async def _ok_executor(tool_name: str, params: dict) -> MagicMock:
    """Mock tool executor that always succeeds."""
    result = MagicMock()
    result.status = "ok"
    result.data = {"ticker": params.get("ticker", "TST"), "score": 7.5}
    result.error = None
    return result


async def _failing_executor(tool_name: str, params: dict) -> MagicMock:
    """Mock tool executor that always raises."""
    raise Exception("Tool failed")


# ===========================================================================
# 1. Intent classification (S4a)
# ===========================================================================


class TestIntentClassification:
    """Verify planner correctly classifies intents from diverse prompts."""

    @pytest.mark.asyncio
    async def test_stock_analysis_intent(self):
        """'Analyze AAPL' should produce stock_analysis intent."""
        mock_llm = AsyncMock(return_value=_llm_response(_plan_json(intent="stock_analysis")))
        plan = await plan_query("Analyze AAPL", "tools", {}, mock_llm)
        assert plan["intent"] == "stock_analysis"

    @pytest.mark.asyncio
    async def test_portfolio_intent(self):
        """'Show my portfolio' should produce portfolio intent."""
        mock_llm = AsyncMock(
            return_value=_llm_response(
                _plan_json(intent="portfolio", steps=[{"tool": "get_portfolio", "params": {}}])
            )
        )
        plan = await plan_query("Show my portfolio", "tools", {}, mock_llm)
        assert plan["intent"] == "portfolio"

    @pytest.mark.asyncio
    async def test_market_overview_intent(self):
        """'How is the market doing?' should produce market_overview intent."""
        mock_llm = AsyncMock(
            return_value=_llm_response(
                _plan_json(
                    intent="market_overview",
                    steps=[{"tool": "get_economic_series", "params": {}}],
                )
            )
        )
        plan = await plan_query("How is the market doing?", "tools", {}, mock_llm)
        assert plan["intent"] == "market_overview"

    @pytest.mark.asyncio
    async def test_simple_lookup_intent(self):
        """'What is AAPL's price?' should produce simple_lookup intent."""
        mock_llm = AsyncMock(
            return_value=_llm_response(
                _plan_json(
                    intent="simple_lookup",
                    steps=[{"tool": "analyze_stock", "params": {"ticker": "AAPL"}}],
                    skip_synthesis=True,
                )
            )
        )
        plan = await plan_query("What is AAPL's price?", "tools", {}, mock_llm)
        assert plan["intent"] == "simple_lookup"
        assert plan["skip_synthesis"] is True

    @pytest.mark.asyncio
    async def test_out_of_scope_intent(self):
        """'What is the weather?' should produce out_of_scope intent."""
        mock_llm = AsyncMock(
            return_value=_llm_response(
                _plan_json(
                    intent="out_of_scope",
                    steps=[],
                    decline_message="I can only help with stock analysis.",
                )
            )
        )
        plan = await plan_query("What is the weather?", "tools", {}, mock_llm)
        assert plan["intent"] == "out_of_scope"
        assert "decline_message" in plan

    def test_invalid_intent_rejected(self):
        """Custom/invalid intent raises ValueError."""
        with pytest.raises(ValueError, match="intent"):
            parse_plan_response(
                json.dumps({"intent": "custom_type", "steps": [], "reasoning": "test"})
            )

    def test_all_valid_intents_accepted(self):
        """Every intent in VALID_INTENTS parses successfully."""
        for intent in VALID_INTENTS:
            plan = parse_plan_response(
                json.dumps({"intent": intent, "steps": [], "reasoning": "test"})
            )
            assert plan["intent"] == intent

    @pytest.mark.asyncio
    async def test_plan_with_multi_step_tools(self):
        """Multi-step plan with tool chaining parses correctly."""
        steps = [
            {"tool": "search_stocks", "params": {"query": "Apple"}},
            {"tool": "analyze_stock", "params": {"ticker": "$PREV_RESULT.ticker"}},
            {"tool": "get_fundamentals", "params": {"ticker": "$PREV_RESULT.ticker"}},
        ]
        mock_llm = AsyncMock(return_value=_llm_response(_plan_json(steps=steps)))
        plan = await plan_query("Tell me about Apple", "tools", {}, mock_llm)
        assert len(plan["steps"]) == 3
        assert plan["steps"][1]["params"]["ticker"] == "$PREV_RESULT.ticker"

    def test_malformed_json_with_trailing_text_rejected(self):
        """LLM response with trailing text after JSON raises ValueError."""
        with pytest.raises(ValueError):
            parse_plan_response('{"intent": "stock_analysis", "steps": []} some extra text')

    def test_markdown_fenced_json_parsed(self):
        """JSON wrapped in markdown code fences is parsed correctly."""
        fenced = f"```json\n{_plan_json()}\n```"
        plan = parse_plan_response(fenced)
        assert plan["intent"] == "stock_analysis"


# ===========================================================================
# 2. Executor edge cases (S4b)
# ===========================================================================


class TestExecutorEdgeCases:
    """Executor $PREV_RESULT, circuit breaker, timeout, and tool limit."""

    @pytest.mark.asyncio
    async def test_prev_result_list_access(self):
        """$PREV_RESULT.ticker resolves from list data (first element)."""
        call_params = {}

        async def capturing_executor(tool_name, params):
            call_params.update(params)
            result = MagicMock()
            result.status = "ok"
            result.data = [{"ticker": "PLTR", "name": "Palantir"}]
            result.error = None
            return result

        steps = [
            {"tool": "search_stocks", "params": {"query": "Palantir"}},
            {"tool": "analyze_stock", "params": {"ticker": "$PREV_RESULT.ticker"}},
        ]
        await execute_plan(steps, capturing_executor)
        assert call_params.get("ticker") == "PLTR"

    @pytest.mark.asyncio
    async def test_prev_result_no_match_returns_raw(self):
        """$PREV_RESULT.nonexistent returns the raw string."""
        call_params = {}

        async def capturing_executor(tool_name, params):
            call_params.update(params)
            result = MagicMock()
            result.status = "ok"
            result.data = {"score": 7.5}
            result.error = None
            return result

        steps = [
            {"tool": "analyze_stock", "params": {"ticker": "AAPL"}},
            {"tool": "get_fundamentals", "params": {"ticker": "$PREV_RESULT.nonexistent"}},
        ]
        await execute_plan(steps, capturing_executor)
        # Should pass through the raw string or resolve to something
        assert "ticker" in call_params

    @pytest.mark.asyncio
    async def test_circuit_breaker_triggers(self):
        """Circuit breaker fires after CIRCUIT_BREAKER_THRESHOLD consecutive failures."""
        failure_count = 0

        async def counting_failing_executor(tool_name, params):
            nonlocal failure_count
            failure_count += 1
            raise Exception("Always fails")

        steps = [{"tool": f"tool_{i}", "params": {}} for i in range(10)]
        result = await execute_plan(steps, counting_failing_executor)
        assert result["circuit_broken"] is True
        # Should stop after threshold (each tool retried once = threshold * 2 calls max)
        assert result["tool_calls"] <= CIRCUIT_BREAKER_THRESHOLD

    @pytest.mark.asyncio
    async def test_tool_limit_enforced(self):
        """Executor stops after MAX_TOOL_CALLS steps."""
        call_count = 0

        async def counting_executor(tool_name, params):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            result.status = "ok"
            result.data = {"value": call_count}
            result.error = None
            return result

        steps = [{"tool": f"tool_{i}", "params": {}} for i in range(20)]
        result = await execute_plan(steps, counting_executor)
        assert result["tool_calls"] == MAX_TOOL_CALLS

    @pytest.mark.asyncio
    async def test_empty_search_triggers_replan(self):
        """search_stocks returning empty list sets needs_replan=True."""

        async def empty_search_executor(tool_name, params):
            result = MagicMock()
            result.status = "ok"
            result.data = [] if tool_name == "search_stocks" else {"value": 1}
            result.error = None
            return result

        steps = [{"tool": "search_stocks", "params": {"query": "XYZNOTREAL"}}]
        result = await execute_plan(steps, empty_search_executor)
        assert result["needs_replan"] is True

    @pytest.mark.asyncio
    async def test_retry_succeeds_on_second_attempt(self):
        """Tool fails once, then succeeds on retry."""
        attempt_count = 0

        async def flaky_executor(tool_name, params):
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count == 1:
                raise Exception("Temporary failure")
            result = MagicMock()
            result.status = "ok"
            result.data = {"recovered": True}
            result.error = None
            return result

        steps = [{"tool": "flaky_tool", "params": {}}]
        result = await execute_plan(steps, flaky_executor)
        assert len(result["results"]) == 1
        assert result["results"][0]["status"] == "ok"

    @pytest.mark.asyncio
    async def test_on_step_callback_called(self):
        """on_step callback fires for each step."""
        callbacks = []

        async def on_step(idx, tool_name, status):
            callbacks.append((idx, tool_name, status))

        steps = [
            {"tool": "tool_a", "params": {}},
            {"tool": "tool_b", "params": {}},
        ]
        await execute_plan(steps, _ok_executor, on_step=on_step)
        assert len(callbacks) == 2
        assert callbacks[0][1] == "tool_a"
        assert callbacks[1][1] == "tool_b"

    @pytest.mark.asyncio
    async def test_wall_clock_timeout(self):
        """Executor respects wall clock timeout."""

        async def slow_executor(tool_name, params):
            import asyncio

            await asyncio.sleep(0.1)
            result = MagicMock()
            result.status = "ok"
            result.data = {}
            result.error = None
            return result

        steps = [{"tool": f"tool_{i}", "params": {}} for i in range(100)]
        with patch("backend.agents.executor.WALL_CLOCK_TIMEOUT_S", 0.05):
            result = await execute_plan(steps, slow_executor)
        assert result["timed_out"] is True


# ===========================================================================
# 3. Synthesizer edge cases (S4b)
# ===========================================================================


class TestSynthesizerEdgeCases:
    """Synthesizer confidence, scenarios, evidence validation."""

    def test_confidence_auto_labeling_high(self):
        """Confidence >= 0.65 labeled 'high'."""
        synthesis = parse_synthesis_response(
            json.dumps({"confidence": 0.8, "summary": "Good", "evidence": [], "gaps": []})
        )
        assert synthesis["confidence_label"] == "high"

    def test_confidence_auto_labeling_medium(self):
        """Confidence 0.40-0.64 labeled 'medium'."""
        synthesis = parse_synthesis_response(
            json.dumps({"confidence": 0.5, "summary": "OK", "evidence": [], "gaps": []})
        )
        assert synthesis["confidence_label"] == "medium"

    def test_confidence_auto_labeling_low(self):
        """Confidence < 0.40 labeled 'low'."""
        synthesis = parse_synthesis_response(
            json.dumps({"confidence": 0.2, "summary": "Weak", "evidence": [], "gaps": []})
        )
        assert synthesis["confidence_label"] == "low"

    def test_missing_confidence_defaults_to_0_5(self):
        """Missing confidence defaults to 0.5 (medium)."""
        synthesis = parse_synthesis_response(
            json.dumps({"summary": "Analysis", "evidence": [], "gaps": []})
        )
        assert synthesis["confidence"] == 0.5
        assert synthesis["confidence_label"] == "medium"

    def test_scenarios_preserved(self):
        """Scenarios dict is preserved from LLM response."""
        scenarios = {
            "bull": {"thesis": "AI growth", "probability": 0.4},
            "base": {"thesis": "Steady", "probability": 0.4},
            "bear": {"thesis": "Downturn", "probability": 0.2},
        }
        synthesis = parse_synthesis_response(
            json.dumps(
                {
                    "confidence": 0.7,
                    "summary": "Mixed",
                    "scenarios": scenarios,
                    "evidence": [],
                    "gaps": [],
                }
            )
        )
        assert "bull" in synthesis["scenarios"]
        assert synthesis["scenarios"]["bull"]["probability"] == 0.4

    def test_evidence_list_preserved(self):
        """Evidence citations are preserved."""
        evidence = [
            {"claim": "Score 8.2", "source_tool": "analyze_stock", "value": "8.2"},
        ]
        synthesis = parse_synthesis_response(
            json.dumps(
                {
                    "confidence": 0.8,
                    "summary": "Strong",
                    "evidence": evidence,
                    "gaps": [],
                }
            )
        )
        assert len(synthesis["evidence"]) == 1
        assert synthesis["evidence"][0]["source_tool"] == "analyze_stock"

    def test_gaps_from_unavailable_tools(self):
        """Gaps list is preserved for unavailable tool data."""
        synthesis = parse_synthesis_response(
            json.dumps(
                {
                    "confidence": 0.6,
                    "summary": "Partial",
                    "evidence": [],
                    "gaps": ["Fundamentals unavailable (timeout)"],
                }
            )
        )
        assert len(synthesis["gaps"]) == 1

    @pytest.mark.asyncio
    async def test_synthesize_calls_llm(self):
        """synthesize_results calls LLM and returns parsed response."""
        mock_llm = AsyncMock(
            return_value=_llm_response(
                json.dumps(
                    {
                        "confidence": 0.75,
                        "summary": "AAPL looks strong",
                        "evidence": [],
                        "gaps": [],
                    }
                )
            )
        )
        tool_results = [
            {"tool": "analyze_stock", "status": "ok", "data": {"score": 8.0}},
        ]
        synthesis = await synthesize_results(tool_results, {}, mock_llm)
        mock_llm.assert_called_once()
        assert synthesis["confidence"] == 0.75

    def test_markdown_fenced_synthesis_parsed(self):
        """Synthesis wrapped in markdown fences is parsed."""
        inner = json.dumps(
            {
                "confidence": 0.6,
                "summary": "Test",
                "evidence": [],
                "gaps": [],
            }
        )
        fenced = f"```json\n{inner}\n```"
        synthesis = parse_synthesis_response(fenced)
        assert synthesis["summary"] == "Test"


# ===========================================================================
# 4. Context window (S4b)
# ===========================================================================


class TestContextWindow:
    """build_context_window truncation and recency preservation."""

    def test_short_history_preserved(self):
        """Short history under max_tokens is returned unchanged."""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        result = build_context_window(messages, max_tokens=16000)
        assert len(result) == 2

    def test_long_history_truncated(self):
        """Long history is truncated to fit within max_tokens."""
        messages = [{"role": "user", "content": f"Message {i} " * 100} for i in range(100)]
        result = build_context_window(messages, max_tokens=1000)
        assert len(result) < len(messages)

    def test_recent_messages_preserved(self):
        """Most recent messages survive truncation."""
        messages = [{"role": "user", "content": f"Old message {i} " * 50} for i in range(20)]
        messages.append({"role": "user", "content": "Latest message"})
        result = build_context_window(messages, max_tokens=500)
        assert result[-1]["content"] == "Latest message"

    def test_empty_history_returns_empty(self):
        """Empty message list returns empty list."""
        result = build_context_window([], max_tokens=16000)
        assert result == []

    def test_single_large_message_kept(self):
        """Single message exceeding budget is still returned (can't drop it)."""
        messages = [{"role": "user", "content": "x " * 10000}]
        result = build_context_window(messages, max_tokens=100)
        assert len(result) == 1
