"""End-to-end integration tests for the ReAct loop simulating real conversations.

Uses mocked LLM and tool executor to validate full conversation flows
without hitting external services or the database.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from backend.agents.guards import DISCLAIMER
from backend.agents.intent_classifier import classify_intent
from backend.agents.llm_client import LLMResponse
from backend.agents.react_loop import react_loop
from backend.agents.stream import StreamEvent
from backend.tools.base import ToolResult

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_response(
    content: str = "",
    tool_calls: list | None = None,
    model: str = "test-model",
    prompt_tokens: int = 100,
    completion_tokens: int = 50,
) -> LLMResponse:
    """Build an LLMResponse for use in mocked side_effect sequences.

    Args:
        content: Assistant reasoning / final answer text.
        tool_calls: Optional list of tool call dicts.
        model: Model identifier string.
        prompt_tokens: Simulated prompt token count.
        completion_tokens: Simulated completion token count.

    Returns:
        Fully constructed LLMResponse instance.
    """
    return LLMResponse(
        content=content,
        tool_calls=tool_calls or [],
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )


def _make_tool_call(
    name: str = "analyze_stock",
    call_id: str = "call_1",
    arguments: dict | None = None,
) -> dict:
    """Build a tool call dict in OpenAI function-calling format.

    Args:
        name: Tool name to invoke.
        call_id: Unique call identifier.
        arguments: Keyword arguments for the tool.

    Returns:
        Tool call dict with id, name, and arguments keys.
    """
    return {
        "id": call_id,
        "name": name,
        "arguments": arguments or {"ticker": "AAPL"},
    }


async def _collect_events(gen) -> list[StreamEvent]:
    """Drain an async generator and return all emitted StreamEvents.

    Args:
        gen: Async generator yielding StreamEvent objects.

    Returns:
        Ordered list of all collected StreamEvent instances.
    """
    events: list[StreamEvent] = []
    async for event in gen:
        events.append(event)
    return events


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stock_analysis_full_flow() -> None:
    """Full stock analysis flow: analyze_stock → reasoning → get_fundamentals → answer.

    Simulates a two-tool sequence where the agent first fetches stock data,
    reasons about it, then retrieves fundamentals before producing a final
    answer. Validates that thinking events, tool results, final token, done
    event, and DISCLAIMER are all present.
    """
    tc1 = _make_tool_call(name="analyze_stock", call_id="c1", arguments={"ticker": "TSLA"})
    tc2 = _make_tool_call(name="get_fundamentals", call_id="c2", arguments={"ticker": "TSLA"})

    llm_chat = AsyncMock(
        side_effect=[
            _make_response(
                content="Let me first analyze TSLA's current signal.",
                tool_calls=[tc1],
            ),
            _make_response(
                content="Good signal. Now let me check the fundamentals.",
                tool_calls=[tc2],
            ),
            _make_response(
                content="TSLA has a BUY signal with strong fundamentals. PE ratio looks reasonable."
            ),
        ]
    )
    tool_executor = AsyncMock(
        side_effect=[
            ToolResult(status="ok", data={"ticker": "TSLA", "composite_score": 8.5}),
            ToolResult(
                status="ok",
                data={"ticker": "TSLA", "pe_ratio": 65.2, "debt_to_equity": 0.4},
            ),
        ]
    )

    events = await _collect_events(
        react_loop(
            query="Give me a full analysis of TSLA",
            session_messages=[],
            tools=[
                {"type": "function", "function": {"name": "analyze_stock"}},
                {"type": "function", "function": {"name": "get_fundamentals"}},
            ],
            tool_executor=tool_executor,
            llm_chat=llm_chat,
            user_context={},
        )
    )

    types = [e.type for e in events]

    # Thinking events emitted from LLM reasoning content
    thinking_events = [e for e in events if e.type == "thinking"]
    assert len(thinking_events) >= 2, "Expected at least 2 thinking events (one per tool call step)"

    # Both tool results present
    tool_result_events = [e for e in events if e.type == "tool_result"]
    assert len(tool_result_events) == 2, "Expected exactly 2 tool_result events"
    tool_names_called = {e.tool for e in tool_result_events}
    assert "analyze_stock" in tool_names_called
    assert "get_fundamentals" in tool_names_called

    # Exactly one final token event
    token_events = [e for e in events if e.type == "token"]
    assert len(token_events) == 1, "Expected exactly 1 final token event"

    # DISCLAIMER appended to final answer
    assert DISCLAIMER in token_events[0].content, (
        "Financial disclaimer must be present in final token"
    )

    # Loop terminates with done
    assert types[-1] == "done", "Last event must be done"


@pytest.mark.asyncio
async def test_portfolio_adaptive_drilldown() -> None:
    """Portfolio health check triggers adaptive drilldown on top holding.

    Simulates the agent detecting a low portfolio score and adapting its
    reasoning to drill into the weakest holding. Validates that two distinct
    tools are called, demonstrating adaptive multi-step reasoning.
    """
    tc1 = _make_tool_call(
        name="portfolio_health",
        call_id="c1",
        arguments={"user_id": "user-123"},
    )
    tc2 = _make_tool_call(
        name="analyze_stock",
        call_id="c2",
        arguments={"ticker": "GME"},
    )

    llm_chat = AsyncMock(
        side_effect=[
            _make_response(
                content="Checking overall portfolio health first.",
                tool_calls=[tc1],
            ),
            _make_response(
                content=(
                    "Portfolio score is low (4.2/10). GME is dragging it down. Let me drill in."
                ),
                tool_calls=[tc2],
            ),
            _make_response(
                content=(
                    "GME has weak fundamentals and poor momentum. "
                    "Consider reducing your position to improve portfolio health."
                )
            ),
        ]
    )
    tool_executor = AsyncMock(
        side_effect=[
            ToolResult(
                status="ok",
                data={
                    "portfolio_score": 4.2,
                    "weakest_holding": "GME",
                    "holdings": ["GME", "AAPL"],
                },
            ),
            ToolResult(
                status="ok",
                data={"ticker": "GME", "composite_score": 2.1, "signal": "AVOID"},
            ),
        ]
    )

    events = await _collect_events(
        react_loop(
            query="How is my portfolio doing?",
            session_messages=[],
            tools=[
                {"type": "function", "function": {"name": "portfolio_health"}},
                {"type": "function", "function": {"name": "analyze_stock"}},
            ],
            tool_executor=tool_executor,
            llm_chat=llm_chat,
            user_context={"positions": [{"ticker": "GME"}, {"ticker": "AAPL"}]},
        )
    )

    # Verify both distinct tools were called (adaptation visible)
    tool_start_events = [e for e in events if e.type == "tool_start"]
    called_tool_names = [e.tool for e in tool_start_events]
    assert len(called_tool_names) == 2, "Expected 2 tool_start events"
    assert called_tool_names[0] == "portfolio_health", "First tool must be portfolio_health"
    assert called_tool_names[1] == "analyze_stock", (
        "Second tool must be analyze_stock (adaptive drilldown)"
    )

    # Both results surfaced in events
    tool_result_events = [e for e in events if e.type == "tool_result"]
    assert len(tool_result_events) == 2

    # Final answer present with disclaimer
    token_events = [e for e in events if e.type == "token"]
    assert len(token_events) == 1
    assert DISCLAIMER in token_events[0].content

    assert [e for e in events if e.type == "done"], "Loop must emit done event"


@pytest.mark.asyncio
async def test_comparison_parallel() -> None:
    """LLM returns 2 parallel tool calls for AAPL and MSFT comparison.

    Validates that both tool_calls in a single LLM response are executed
    concurrently and both tool_result events appear before the final answer.
    """
    tc_aapl = _make_tool_call(name="analyze_stock", call_id="c1", arguments={"ticker": "AAPL"})
    tc_msft = _make_tool_call(name="analyze_stock", call_id="c2", arguments={"ticker": "MSFT"})

    llm_chat = AsyncMock(
        side_effect=[
            _make_response(
                content="I'll analyze both stocks simultaneously.",
                tool_calls=[tc_aapl, tc_msft],
            ),
            _make_response(
                content=(
                    "AAPL scores 8.5/10 (BUY) while MSFT scores 7.8/10 (WATCH). "
                    "AAPL has stronger momentum at this time."
                )
            ),
        ]
    )
    tool_executor = AsyncMock(
        side_effect=[
            ToolResult(
                status="ok",
                data={"ticker": "AAPL", "composite_score": 8.5, "signal": "BUY"},
            ),
            ToolResult(
                status="ok",
                data={"ticker": "MSFT", "composite_score": 7.8, "signal": "WATCH"},
            ),
        ]
    )

    events = await _collect_events(
        react_loop(
            query="Compare AAPL vs MSFT",
            session_messages=[],
            tools=[{"type": "function", "function": {"name": "analyze_stock"}}],
            tool_executor=tool_executor,
            llm_chat=llm_chat,
            user_context={},
        )
    )

    # Both tools executed
    tool_start_events = [e for e in events if e.type == "tool_start"]
    assert len(tool_start_events) == 2, "Expected 2 tool_start events for parallel calls"
    assert tool_executor.call_count == 2, "tool_executor must be called twice"

    # Both tool results present
    tool_result_events = [e for e in events if e.type == "tool_result"]
    assert len(tool_result_events) == 2, "Expected 2 tool_result events"
    result_tickers = {e.data["ticker"] for e in tool_result_events if e.data}
    assert "AAPL" in result_tickers
    assert "MSFT" in result_tickers

    # Final answer with disclaimer
    token_events = [e for e in events if e.type == "token"]
    assert len(token_events) == 1
    assert DISCLAIMER in token_events[0].content

    types = [e.type for e in events]
    assert types[-1] == "done"


@pytest.mark.asyncio
async def test_simple_lookup_bypasses_react() -> None:
    """Bare ticker input is classified as simple_lookup with fast_path=True.

    Validates that the intent classifier short-circuits the ReAct loop for
    trivial single-ticker lookups. Checks intent, fast_path flag, and
    that the extracted ticker is correct.
    """
    result = classify_intent("AAPL")

    assert result.intent == "simple_lookup", (
        f"Bare ticker 'AAPL' must classify as simple_lookup, got {result.intent!r}"
    )
    assert result.fast_path is True, "simple_lookup must set fast_path=True to bypass ReAct loop"
    assert "AAPL" in result.tickers, "AAPL must be extracted as the ticker"
    assert result.decline_message is None, "simple_lookup must not produce a decline message"


@pytest.mark.asyncio
async def test_out_of_scope_decline() -> None:
    """Out-of-scope query (weather) is declined without calling the ReAct loop.

    Validates that the intent classifier immediately rejects non-finance
    queries and provides an appropriate decline_message, fast_path=True,
    with no tickers extracted.
    """
    result = classify_intent("What's the weather like in New York today?")

    assert result.intent == "out_of_scope", (
        f"Weather query must classify as out_of_scope, got {result.intent!r}"
    )
    assert result.fast_path is True, "out_of_scope must set fast_path=True to skip ReAct loop"
    assert result.decline_message is not None, "out_of_scope must include a decline_message"
    assert len(result.decline_message) > 0, "decline_message must not be empty"
    # Decline message guides user back to finance domain
    decline_lower = result.decline_message.lower()
    assert any(
        kw in decline_lower for kw in ("stock", "portfolio", "market", "financial", "investment")
    ), f"decline_message should mention finance domain, got: {result.decline_message!r}"
