"""ReAct loop core — async generator that yields StreamEvent objects.

Replaces the Plan-Execute-Synthesize pipeline with a Reason+Act loop.
Pure async generator with all dependencies injected (no DB access, no request objects).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any, AsyncGenerator, Callable

from backend.agents.guards import DISCLAIMER
from backend.agents.llm_client import LLMResponse
from backend.agents.result_validator import validate_tool_result
from backend.agents.stream import StreamEvent
from backend.tools.base import ToolResult

logger = logging.getLogger(__name__)

_PROMPT_DIR = Path(__file__).parent / "prompts"

# --- Constants ---
MAX_ITERATIONS = 8
MAX_PARALLEL_TOOLS = 4
MAX_TOOL_CALLS = 12
WALL_CLOCK_TIMEOUT = 45
CIRCUIT_BREAKER = 3
_EXTERNAL_TOOLS = {"web_search", "get_geopolitical_events"}


# --- System prompt ---


def _render_system_prompt(
    user_context: dict[str, Any],
    entity_registry: Any | None,
) -> str:
    """Render the ReAct system prompt with user and entity context.

    Loads the template from prompts/react_system.md and fills
    {{user_context}} and {{entity_context}} placeholders.

    Args:
        user_context: Portfolio, prefs, watchlist info.
        entity_registry: EntityRegistry for recently discussed tickers.

    Returns:
        Rendered system prompt string.
    """
    template_path = _PROMPT_DIR / "react_system.md"
    template = template_path.read_text(encoding="utf-8")

    # Format user context summary
    ctx_parts: list[str] = []
    if user_context.get("positions"):
        tickers = [p.get("ticker", "?") for p in user_context["positions"][:10]]
        ctx_parts.append(f"Holdings: {', '.join(tickers)}")
    if user_context.get("watchlist"):
        ctx_parts.append(f"Watchlist: {', '.join(user_context['watchlist'][:10])}")
    if user_context.get("preferences"):
        ctx_parts.append(f"Preferences: {json.dumps(user_context['preferences'])}")
    user_ctx_str = "\n".join(ctx_parts) if ctx_parts else "No portfolio data available."

    # Format entity context
    entity_ctx_str = ""
    if entity_registry is not None:
        try:
            entity_ctx_str = entity_registry.format_for_prompt()
        except Exception:
            logger.debug("entity_registry.format_for_prompt() failed")
    if not entity_ctx_str:
        entity_ctx_str = "No prior context."

    return template.replace("{{user_context}}", user_ctx_str).replace(
        "{{entity_context}}", entity_ctx_str
    )


# --- Scratchpad helpers ---


def _build_initial_messages(
    query: str,
    session_messages: list[dict[str, Any]],
    user_context: dict[str, Any],
    entity_registry: Any | None,
) -> list[dict[str, Any]]:
    """Build the initial scratchpad with system prompt, prior turns, and current query.

    Args:
        query: The user's current question.
        session_messages: Prior conversation turns for multi-turn context.
        user_context: Portfolio, prefs, watchlist info.
        entity_registry: EntityRegistry for pronoun resolution context.

    Returns:
        List of message dicts forming the initial scratchpad.
    """
    system = _render_system_prompt(user_context, entity_registry)
    messages: list[dict[str, Any]] = [{"role": "system", "content": system}]

    # Prior conversation turns (for multi-turn), capped at 10
    for msg in session_messages[-10:]:
        messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})

    messages.append({"role": "user", "content": query})
    return messages


def _append_assistant_message(scratchpad: list[dict[str, Any]], response: LLMResponse) -> None:
    """Append LLM response (with tool_calls) to scratchpad in OpenAI format.

    Args:
        scratchpad: The current message list.
        response: The LLM response to append.
    """
    msg: dict[str, Any] = {"role": "assistant", "content": response.content or ""}
    if response.tool_calls:
        msg["tool_calls"] = [
            {
                "id": tc["id"],
                "type": "function",
                "function": {
                    "name": tc["name"],
                    "arguments": (
                        json.dumps(tc["arguments"])
                        if isinstance(tc["arguments"], dict)
                        else tc["arguments"]
                    ),
                },
            }
            for tc in response.tool_calls
        ]
    scratchpad.append(msg)


def _append_tool_messages(
    scratchpad: list[dict[str, Any]],
    tool_calls: list[dict[str, Any]],
    results: list[ToolResult],
) -> None:
    """Append tool result messages to scratchpad.

    Args:
        scratchpad: The current message list.
        tool_calls: The tool calls that were executed.
        results: The corresponding tool results.
    """
    for tc, result in zip(tool_calls, results):
        scratchpad.append(
            {
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": (
                    json.dumps(result.data, default=str)
                    if result.data
                    else result.error or "No data"
                ),
            }
        )


def _truncate_old_results(scratchpad: list[dict[str, Any]], keep_latest: int = 2) -> None:
    """Truncate tool result content older than the latest N tool messages.

    Keeps the latest ``keep_latest`` tool messages at full length.
    Older tool messages are truncated to 200 chars with a suffix.

    Args:
        scratchpad: The current message list (modified in place).
        keep_latest: Number of recent tool messages to keep untruncated.
    """
    tool_indices = [i for i, m in enumerate(scratchpad) if m.get("role") == "tool"]
    if len(tool_indices) <= keep_latest:
        return
    for idx in tool_indices[:-keep_latest]:
        content = scratchpad[idx]["content"]
        if len(content) > 200:
            scratchpad[idx]["content"] = content[:200] + "... [truncated, already analyzed]"


# --- Tool execution ---


async def _execute_single_tool(
    tool_call: dict[str, Any],
    tool_executor: Callable[..., Any],
    collector: Any | None,
    cache: Any | None,
    session_id: str | None,
    loop_step: int = 0,
) -> ToolResult:
    """Execute a single tool call with cache check and observability.

    Args:
        tool_call: Dict with id, name, arguments keys.
        tool_executor: Async callable (name, params) -> ToolResult.
        collector: ObservabilityCollector or None.
        cache: CacheService or None.
        session_id: Session ID for cache key scoping.
        loop_step: Current loop iteration for observability.

    Returns:
        The ToolResult from execution or cache.
    """
    name = tool_call["name"]
    params = tool_call.get("arguments", {})
    if isinstance(params, str):
        try:
            params = json.loads(params)
        except (json.JSONDecodeError, TypeError):
            params = {}

    # Cache check
    cache_hit = False
    if cache and session_id:
        cache_key = f"tool:{session_id}:{name}:{json.dumps(params, sort_keys=True, default=str)}"
        try:
            cached = await cache.get(cache_key)
            if cached is not None:
                cache_hit = True
                result = ToolResult(status="ok", data=cached)
                if collector:
                    await collector.record_tool_execution(
                        tool_name=name,
                        latency_ms=0,
                        status="ok",
                        cache_hit=True,
                        loop_step=loop_step,
                    )
                return result
        except Exception:
            logger.debug("cache_check_failed", extra={"tool": name})

    # Execute
    start = time.monotonic()
    try:
        result = await tool_executor(name, params)
    except Exception:
        logger.exception("tool_execution_error", extra={"tool": name})
        result = ToolResult(status="error", error="Tool execution failed")

    latency_ms = int((time.monotonic() - start) * 1000)

    # Validate output
    validate_tool_result(result, name)

    # Record observability
    if collector:
        result_size = len(json.dumps(result.data, default=str)) if result.data else 0
        await collector.record_tool_execution(
            tool_name=name,
            latency_ms=latency_ms,
            status=result.status,
            result_size_bytes=result_size,
            params=params,
            error=result.error,
            cache_hit=cache_hit,
            loop_step=loop_step,
            result=result.data,
        )

    # Cache write for successful results
    if cache and session_id and result.status == "ok" and result.data is not None:
        cache_key = f"tool:{session_id}:{name}:{json.dumps(params, sort_keys=True, default=str)}"
        try:
            await cache.set(cache_key, result.data, ttl=300)
        except Exception:
            logger.debug("cache_write_failed", extra={"tool": name})

    return result


async def _execute_tools(
    tool_calls: list[dict[str, Any]],
    tool_executor: Callable[..., Any],
    collector: Any | None,
    cache: Any | None,
    session_id: str | None,
    loop_step: int = 0,
) -> list[ToolResult]:
    """Execute multiple tool calls in parallel.

    Args:
        tool_calls: List of tool call dicts.
        tool_executor: Async callable (name, params) -> ToolResult.
        collector: ObservabilityCollector or None.
        cache: CacheService or None.
        session_id: Session ID for cache scoping.
        loop_step: Current iteration for observability.

    Returns:
        List of ToolResult in same order as tool_calls.
    """
    tasks = [
        _execute_single_tool(tc, tool_executor, collector, cache, session_id, loop_step)
        for tc in tool_calls
    ]
    return list(await asyncio.gather(*tasks))


# --- Core ReAct loop ---


async def react_loop(
    query: str,
    session_messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    tool_executor: Callable[..., Any],
    llm_chat: Callable[..., Any],
    user_context: dict[str, Any],
    entity_registry: Any | None = None,
    collector: Any | None = None,
    cache: Any | None = None,
    session_id: str | None = None,
    max_iterations: int = MAX_ITERATIONS,
    langfuse_trace: Any | None = None,
) -> AsyncGenerator[StreamEvent, None]:
    """Core ReAct loop — reason and act in alternating steps.

    Yields StreamEvent objects as the agent reasons, calls tools, and
    produces a final answer. All dependencies are injected; the loop
    has no DB access or request-object coupling.

    Args:
        query: The user's current question.
        session_messages: Prior conversation turns for multi-turn context.
        tools: Tool schemas (from tool_groups) for LLM function calling.
        tool_executor: Async callable (name, params) -> ToolResult.
        llm_chat: Async callable (messages, tools) -> LLMResponse.
        user_context: Portfolio, prefs, watchlist context.
        entity_registry: EntityRegistry for pronoun resolution.
        collector: ObservabilityCollector for metrics.
        cache: CacheService for tool result caching.
        session_id: Session identifier for cache scoping.
        max_iterations: Maximum LLM calls in the loop.

    Yields:
        StreamEvent objects: thinking, tool_start, tool_result, tool_error,
        token, done, error.
    """
    scratchpad = _build_initial_messages(query, session_messages, user_context, entity_registry)
    total_tool_calls = 0
    consecutive_failures = 0
    wall_start = time.monotonic()

    for i in range(max_iterations):
        # 1. Wall clock check
        elapsed = time.monotonic() - wall_start
        if elapsed > WALL_CLOCK_TIMEOUT:
            logger.warning("react_loop_timeout", extra={"elapsed": elapsed, "iteration": i})
            try:
                from backend.observability.instrumentation.agent import emit_reasoning_log

                emit_reasoning_log(
                    loop_step=i,
                    reasoning_type="synthesize",
                    content_summary="wall clock timeout",
                    termination_reason="wall_clock_timeout",
                )
            except Exception:  # noqa: BLE001
                pass
            timeout_msg = (
                "I ran out of time to complete the analysis. "
                "Here is what I found so far." + DISCLAIMER
            )
            yield StreamEvent(type="token", content=timeout_msg)
            yield StreamEvent(type="done", usage={})
            return

        # Langfuse: start iteration span
        iter_span = None
        if langfuse_trace:
            try:
                iter_span = langfuse_trace.span(
                    name=f"react.iteration.{i + 1}",
                    metadata={"iteration": i + 1},
                )
            except Exception:
                logger.debug("langfuse_iteration_span_failed", extra={"iteration": i})

        # 2. Tool budget check — if exhausted, force summarization
        tools_for_call = tools
        if total_tool_calls >= MAX_TOOL_CALLS:
            scratchpad.append(
                {
                    "role": "user",
                    "content": (
                        "You have used all available tool calls. Summarize your findings now."
                    ),
                }
            )
            tools_for_call = []

        # 3. Reason: call LLM
        try:
            response: LLMResponse = await llm_chat(scratchpad, tools_for_call)
        except Exception:
            logger.exception("react_loop_llm_error", extra={"iteration": i})
            yield StreamEvent(type="error", error="An internal error occurred. Please try again.")
            yield StreamEvent(type="done", usage={})
            return

        # 4. Record observability
        from backend.request_context import current_query_id

        qid = current_query_id.get(None)

        if collector:
            await collector.record_request(
                model=response.model,
                provider="",
                tier="react",
                latency_ms=0,
                prompt_tokens=response.prompt_tokens,
                completion_tokens=response.completion_tokens,
                loop_step=i,
                langfuse_trace_id=qid,
            )

        # 5. Yield thinking event if content present
        if response.content:
            yield StreamEvent(type="thinking", content=response.content)

        # 5b. Emit reasoning event (obs 1b PR5)
        try:
            from backend.observability.instrumentation.agent import emit_reasoning_log

            emit_reasoning_log(
                loop_step=i,
                reasoning_type="plan",
                content_summary=(response.content or "")[:500],
                tool_calls_proposed=(
                    {"tools": [tc["name"] for tc in response.tool_calls]}
                    if response.has_tool_calls
                    else None
                ),
            )
        except Exception:  # noqa: BLE001
            pass

        # 6. If no tool calls → finish
        if not response.has_tool_calls:
            # Langfuse: rename iteration span to "synthesis" — this is the final answer
            if iter_span:
                try:
                    iter_span.update(name="synthesis")
                    iter_span.end()
                except Exception:
                    logger.debug("langfuse_synthesis_span_failed")
            final_content = response.content or ""
            try:
                from backend.observability.instrumentation.agent import emit_reasoning_log

                emit_reasoning_log(
                    loop_step=i,
                    reasoning_type="synthesize",
                    content_summary=final_content[:500],
                    termination_reason="zero_tool_calls",
                )
            except Exception:  # noqa: BLE001
                pass
            yield StreamEvent(type="token", content=final_content + DISCLAIMER)
            yield StreamEvent(type="done", usage=response.usage_dict())
            return

        # 7. Cap parallel tools
        tool_calls = response.tool_calls[:MAX_PARALLEL_TOOLS]

        # 8. Yield tool_start events
        for tc in tool_calls:
            yield StreamEvent(type="tool_start", tool=tc["name"], params=tc.get("arguments"))

        # 9. Execute tools in parallel
        results = await _execute_tools(
            tool_calls, tool_executor, collector, cache, session_id, loop_step=i
        )

        # Langfuse: record tool execution spans
        if iter_span:
            for tc_span, result_span in zip(tool_calls, results):
                try:
                    tool_type = "external" if tc_span["name"] in _EXTERNAL_TOOLS else "db"
                    tool_span = iter_span.span(
                        name=f"tool.{tc_span['name']}",
                        metadata={
                            "type": tool_type,
                            "source": tc_span["name"],
                            "cache_hit": getattr(result_span, "cache_hit", False),
                            "status": result_span.status,
                        },
                    )
                    tool_span.end()
                except Exception:
                    logger.debug("langfuse_tool_span_failed", extra={"tool": tc_span["name"]})

        # 10. Update total
        total_tool_calls += len(tool_calls)

        # 11. Yield tool_result / tool_error events
        all_failed = True
        for tc, result in zip(tool_calls, results):
            if result.status in ("error", "timeout"):
                yield StreamEvent(
                    type="tool_error",
                    tool=tc["name"],
                    error=result.error or "Tool failed",
                )
            else:
                all_failed = False
                yield StreamEvent(
                    type="tool_result",
                    tool=tc["name"],
                    status=result.status,
                    data=result.data,
                )

        # 12. Update entity registry
        if entity_registry:
            for tc, result in zip(tool_calls, results):
                if result.status == "ok" and result.data:
                    try:
                        entity_registry.extract_from_tool_result(tc["name"], {"data": result.data})
                    except Exception:
                        logger.debug("entity_registry_update_failed", extra={"tool": tc["name"]})

        # 13. Append assistant + tool messages to scratchpad
        _append_assistant_message(scratchpad, response)
        _append_tool_messages(scratchpad, tool_calls, results)

        # 14. Truncate old tool results
        _truncate_old_results(scratchpad)

        # Langfuse: end iteration span
        if iter_span:
            try:
                iter_span.end()
            except Exception:
                logger.debug("langfuse_iter_end_failed", extra={"iteration": i})

        # 15. Circuit breaker
        if all_failed:
            consecutive_failures += 1
        else:
            consecutive_failures = 0

        if consecutive_failures >= CIRCUIT_BREAKER:
            logger.warning("react_loop_circuit_breaker", extra={"failures": consecutive_failures})
            try:
                from backend.observability.instrumentation.agent import emit_reasoning_log

                emit_reasoning_log(
                    loop_step=i,
                    reasoning_type="synthesize",
                    content_summary="circuit breaker triggered",
                    termination_reason="exception",
                )
            except Exception:  # noqa: BLE001
                pass
            scratchpad.append(
                {
                    "role": "user",
                    "content": "Multiple tool calls have failed. Summarize what you have.",
                }
            )
            try:
                final_response = await llm_chat(scratchpad, [])
                content = final_response.content or "I was unable to gather sufficient data."
                yield StreamEvent(type="token", content=content + DISCLAIMER)
                yield StreamEvent(type="done", usage=final_response.usage_dict())
            except Exception:
                logger.exception("react_loop_circuit_breaker_llm_error")
                yield StreamEvent(
                    type="error",
                    error="An internal error occurred. Please try again.",
                )
                yield StreamEvent(type="done", usage={})
            return

    # Exhausted MAX_ITERATIONS — force summary
    try:
        from backend.observability.instrumentation.agent import emit_reasoning_log

        emit_reasoning_log(
            loop_step=max_iterations,
            reasoning_type="synthesize",
            content_summary="max iterations exhausted",
            termination_reason="max_iterations",
        )
    except Exception:  # noqa: BLE001
        pass
    scratchpad.append(
        {
            "role": "user",
            "content": "Summarize what you have so far and provide your analysis.",
        }
    )
    try:
        final_response = await llm_chat(scratchpad, [])
        content = final_response.content or "Analysis complete."
        yield StreamEvent(type="token", content=content + DISCLAIMER)
        yield StreamEvent(type="done", usage=final_response.usage_dict())
    except Exception:
        logger.exception("react_loop_final_summary_error")
        yield StreamEvent(type="error", error="An internal error occurred. Please try again.")
        yield StreamEvent(type="done", usage={})
