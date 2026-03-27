"""Tests for the ReAct loop core async generator."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from backend.agents.guards import DISCLAIMER
from backend.agents.llm_client import LLMResponse
from backend.agents.react_loop import (
    CIRCUIT_BREAKER,
    MAX_ITERATIONS,
    MAX_PARALLEL_TOOLS,
    MAX_TOOL_CALLS,
    react_loop,
)
from backend.agents.stream import StreamEvent
from backend.tools.base import ToolResult


def _make_response(
    content: str = "",
    tool_calls: list | None = None,
    model: str = "test-model",
    prompt_tokens: int = 100,
    completion_tokens: int = 50,
) -> LLMResponse:
    """Helper to build an LLMResponse."""
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
    """Helper to build a tool call dict."""
    return {
        "id": call_id,
        "name": name,
        "arguments": arguments or {"ticker": "AAPL"},
    }


async def _collect_events(gen) -> list[StreamEvent]:
    """Collect all events from an async generator."""
    events = []
    async for event in gen:
        events.append(event)
    return events


@pytest.mark.asyncio
async def test_single_tool_then_finish():
    """LLM calls 1 tool, then finishes with content."""
    tool_call = _make_tool_call()
    llm_chat = AsyncMock(
        side_effect=[
            _make_response(content="Let me look up AAPL.", tool_calls=[tool_call]),
            _make_response(content="AAPL looks great."),
        ]
    )
    tool_executor = AsyncMock(return_value=ToolResult(status="ok", data={"price": 150}))

    events = await _collect_events(
        react_loop(
            query="How is AAPL?",
            session_messages=[],
            tools=[{"type": "function", "function": {"name": "analyze_stock"}}],
            tool_executor=tool_executor,
            llm_chat=llm_chat,
            user_context={},
        )
    )

    types = [e.type for e in events]
    assert "thinking" in types
    assert "tool_start" in types
    assert "tool_result" in types
    assert "token" in types
    assert types[-1] == "done"
    tool_executor.assert_called_once_with("analyze_stock", {"ticker": "AAPL"})


@pytest.mark.asyncio
async def test_multi_iteration():
    """LLM calls tool, reasons, calls another, then finishes."""
    tc1 = _make_tool_call(name="analyze_stock", call_id="c1")
    tc2 = _make_tool_call(name="compute_signals", call_id="c2", arguments={"ticker": "AAPL"})
    llm_chat = AsyncMock(
        side_effect=[
            _make_response(content="Checking stock data.", tool_calls=[tc1]),
            _make_response(content="Now checking signals.", tool_calls=[tc2]),
            _make_response(content="Based on the data, AAPL is strong."),
        ]
    )
    tool_executor = AsyncMock(return_value=ToolResult(status="ok", data={"result": "ok"}))

    events = await _collect_events(
        react_loop(
            query="Analyze AAPL",
            session_messages=[],
            tools=[{"type": "function"}],
            tool_executor=tool_executor,
            llm_chat=llm_chat,
            user_context={},
        )
    )

    tool_start_events = [e for e in events if e.type == "tool_start"]
    assert len(tool_start_events) == 2
    assert tool_start_events[0].tool == "analyze_stock"
    assert tool_start_events[1].tool == "compute_signals"
    assert tool_executor.call_count == 2


@pytest.mark.asyncio
async def test_parallel_tool_calls():
    """LLM returns 2 tool_calls, both should be executed."""
    tc1 = _make_tool_call(name="tool_a", call_id="c1")
    tc2 = _make_tool_call(name="tool_b", call_id="c2")
    llm_chat = AsyncMock(
        side_effect=[
            _make_response(content="Running both.", tool_calls=[tc1, tc2]),
            _make_response(content="Done."),
        ]
    )
    tool_executor = AsyncMock(return_value=ToolResult(status="ok", data={"x": 1}))

    events = await _collect_events(
        react_loop(
            query="Test",
            session_messages=[],
            tools=[],
            tool_executor=tool_executor,
            llm_chat=llm_chat,
            user_context={},
        )
    )

    tool_starts = [e for e in events if e.type == "tool_start"]
    assert len(tool_starts) == 2
    assert tool_executor.call_count == 2


@pytest.mark.asyncio
async def test_max_parallel_capped():
    """LLM returns 5 tool_calls but only MAX_PARALLEL_TOOLS (4) are executed."""
    tool_calls = [_make_tool_call(name=f"tool_{i}", call_id=f"c{i}") for i in range(5)]
    llm_chat = AsyncMock(
        side_effect=[
            _make_response(content="Running all.", tool_calls=tool_calls),
            _make_response(content="Done."),
        ]
    )
    tool_executor = AsyncMock(return_value=ToolResult(status="ok", data={}))

    events = await _collect_events(
        react_loop(
            query="Test",
            session_messages=[],
            tools=[],
            tool_executor=tool_executor,
            llm_chat=llm_chat,
            user_context={},
        )
    )

    tool_starts = [e for e in events if e.type == "tool_start"]
    assert len(tool_starts) == MAX_PARALLEL_TOOLS
    assert tool_executor.call_count == MAX_PARALLEL_TOOLS


@pytest.mark.asyncio
async def test_finish_no_tool_calls():
    """LLM returns content only with no tool calls — immediate finish."""
    llm_chat = AsyncMock(return_value=_make_response(content="The answer is 42."))
    tool_executor = AsyncMock()

    events = await _collect_events(
        react_loop(
            query="Simple question",
            session_messages=[],
            tools=[],
            tool_executor=tool_executor,
            llm_chat=llm_chat,
            user_context={},
        )
    )

    types = [e.type for e in events]
    # thinking from content, then token with disclaimer, then done
    assert "token" in types
    assert types[-1] == "done"
    tool_executor.assert_not_called()


@pytest.mark.asyncio
async def test_max_iterations_forces_summary():
    """After MAX_ITERATIONS, loop forces a summary without tools."""
    # Always return a tool call so loop never naturally finishes
    tc = _make_tool_call()
    responses = [
        _make_response(content=f"Step {i}", tool_calls=[tc]) for i in range(MAX_ITERATIONS)
    ]
    # Final forced summary (no tools)
    responses.append(_make_response(content="Here is my summary."))

    llm_chat = AsyncMock(side_effect=responses)
    tool_executor = AsyncMock(return_value=ToolResult(status="ok", data={"x": 1}))

    events = await _collect_events(
        react_loop(
            query="Complex analysis",
            session_messages=[],
            tools=[{"type": "function"}],
            tool_executor=tool_executor,
            llm_chat=llm_chat,
            user_context={},
        )
    )

    # Should have MAX_ITERATIONS + 1 LLM calls (loop + forced summary)
    assert llm_chat.call_count == MAX_ITERATIONS + 1
    # Last call should have empty tools list (forced finish)
    last_call_tools = llm_chat.call_args_list[-1][0][1]
    assert last_call_tools == []
    # Final events should be token + done
    assert events[-1].type == "done"
    assert events[-2].type == "token"


@pytest.mark.asyncio
async def test_circuit_breaker():
    """3 consecutive tool failures triggers circuit breaker and forced finish."""
    tc = _make_tool_call()
    # Each iteration: LLM returns tool call, tool fails
    tool_responses = [
        _make_response(content=f"Try {i}", tool_calls=[tc]) for i in range(CIRCUIT_BREAKER)
    ]
    # After circuit breaker: forced summary
    tool_responses.append(_make_response(content="Sorry, tools failed."))

    llm_chat = AsyncMock(side_effect=tool_responses)
    tool_executor = AsyncMock(return_value=ToolResult(status="error", error="Connection failed"))

    events = await _collect_events(
        react_loop(
            query="Analyze AAPL",
            session_messages=[],
            tools=[{"type": "function"}],
            tool_executor=tool_executor,
            llm_chat=llm_chat,
            user_context={},
        )
    )

    # Should have CIRCUIT_BREAKER iterations + 1 forced summary
    assert llm_chat.call_count == CIRCUIT_BREAKER + 1
    # All tool results should be errors
    tool_errors = [e for e in events if e.type == "tool_error"]
    assert len(tool_errors) == CIRCUIT_BREAKER
    assert events[-1].type == "done"


@pytest.mark.asyncio
async def test_wall_clock_timeout(monkeypatch):
    """Simulate wall clock timeout by patching time.monotonic."""
    call_count = 0
    base_time = 1000.0

    def fake_monotonic():
        nonlocal call_count
        call_count += 1
        # First call is wall_start, second is in the loop iteration check
        if call_count <= 1:
            return base_time
        # Return time beyond timeout on second call
        return base_time + 50.0

    monkeypatch.setattr("backend.agents.react_loop.time.monotonic", fake_monotonic)

    llm_chat = AsyncMock(
        return_value=_make_response(content="Never reached.", tool_calls=[_make_tool_call()])
    )
    tool_executor = AsyncMock()

    events = await _collect_events(
        react_loop(
            query="Slow query",
            session_messages=[],
            tools=[],
            tool_executor=tool_executor,
            llm_chat=llm_chat,
            user_context={},
        )
    )

    types = [e.type for e in events]
    assert "token" in types
    assert types[-1] == "done"
    # LLM should never have been called (timeout on first iteration)
    llm_chat.assert_not_called()


@pytest.mark.asyncio
async def test_max_tool_calls_budget():
    """After MAX_TOOL_CALLS, tools are stripped from LLM call."""
    # Use max_iterations high enough, but exhaust tool budget
    # Each iteration uses 1 tool, need MAX_TOOL_CALLS iterations to exhaust
    tc = _make_tool_call()
    responses = []
    for i in range(MAX_TOOL_CALLS):
        responses.append(_make_response(content=f"Step {i}", tool_calls=[tc]))
    # After budget exhausted, LLM gets no tools and must finish
    responses.append(_make_response(content="Summary with budget exhausted."))

    llm_chat = AsyncMock(side_effect=responses)
    tool_executor = AsyncMock(return_value=ToolResult(status="ok", data={"x": 1}))

    events = await _collect_events(
        react_loop(
            query="Big analysis",
            session_messages=[],
            tools=[{"type": "function"}],
            tool_executor=tool_executor,
            llm_chat=llm_chat,
            user_context={},
            max_iterations=MAX_TOOL_CALLS + 2,  # enough iterations to hit budget
        )
    )

    # Verify the final LLM call had empty tools (budget exhausted)
    # The call after budget is exhausted should have tools=[]
    budget_call = llm_chat.call_args_list[MAX_TOOL_CALLS]
    assert budget_call[0][1] == []  # tools parameter is empty
    assert events[-1].type == "done"


@pytest.mark.asyncio
async def test_observability_loop_step():
    """Collector.record_request is called with correct loop_step per iteration."""
    tc = _make_tool_call()
    llm_chat = AsyncMock(
        side_effect=[
            _make_response(content="Step 0", tool_calls=[tc]),
            _make_response(content="Final answer."),
        ]
    )
    tool_executor = AsyncMock(return_value=ToolResult(status="ok", data={"x": 1}))
    collector = AsyncMock()

    await _collect_events(
        react_loop(
            query="Test",
            session_messages=[],
            tools=[],
            tool_executor=tool_executor,
            llm_chat=llm_chat,
            user_context={},
            collector=collector,
        )
    )

    # record_request should be called for each LLM call
    assert collector.record_request.call_count == 2
    # First call: loop_step=0
    first_call_kwargs = collector.record_request.call_args_list[0].kwargs
    assert first_call_kwargs["loop_step"] == 0
    # Second call: loop_step=1
    second_call_kwargs = collector.record_request.call_args_list[1].kwargs
    assert second_call_kwargs["loop_step"] == 1


@pytest.mark.asyncio
async def test_disclaimer_appended():
    """Finish content includes the financial disclaimer."""
    llm_chat = AsyncMock(return_value=_make_response(content="AAPL is a good stock."))
    tool_executor = AsyncMock()

    events = await _collect_events(
        react_loop(
            query="Is AAPL good?",
            session_messages=[],
            tools=[],
            tool_executor=tool_executor,
            llm_chat=llm_chat,
            user_context={},
        )
    )

    token_events = [e for e in events if e.type == "token"]
    assert len(token_events) == 1
    assert DISCLAIMER in token_events[0].content


@pytest.mark.asyncio
async def test_empty_tool_calls_list():
    """LLM returns empty tool_calls list — treated as finish."""
    llm_chat = AsyncMock(return_value=_make_response(content="Here is the answer.", tool_calls=[]))
    tool_executor = AsyncMock()

    events = await _collect_events(
        react_loop(
            query="Quick question",
            session_messages=[],
            tools=[],
            tool_executor=tool_executor,
            llm_chat=llm_chat,
            user_context={},
        )
    )

    types = [e.type for e in events]
    assert "token" in types
    assert types[-1] == "done"
    tool_executor.assert_not_called()
