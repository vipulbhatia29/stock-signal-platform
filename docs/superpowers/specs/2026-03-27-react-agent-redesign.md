# KAN-189: Agent Redesign — Intent Classifier + ReAct Loop

**JIRA:** KAN-189 (Epic), KAN-188 (tool filtering)
**Phase:** 8C (intent classifier, ~4h) → 8B (ReAct loop, ~16h)
**ADRs:** 001-008 in `docs/ADR.md`
**Branch:** `feat/KAN-189-react-agent`
**Spec version:** 2 (post-review — 14 findings fixed, see §12)

---

## 1. Problem Statement

The current agent is a **batch pipeline** (Plan → Execute → Synthesize), not a reasoning agent:
- Planner decides ALL tools upfront before seeing any data
- Executor runs tools mechanically in order — no adaptation between tool calls
- Synthesizer formats output — never changes the plan
- All 28 tool descriptions sent to planner every query (~2K tokens wasted)
- `graph.ainvoke()` blocks — user sees nothing during 3-10s of processing
- Simple lookups ("What's AAPL's price?") require 2 LLM calls when zero would suffice

### Current call flow
```
User → Guards → Planner (LLM #1) → Executor (mechanical) → Synthesizer (LLM #2) → User
                all 28 tools           no reasoning              fixed format
```

### Target call flow
```
User → Guards → Intent Classifier (rule-based, 0 LLM)
                  ├─ simple_lookup → Tool → Template → User        (0 LLM calls)
                  └─ complex → ReAct Loop (N LLM calls) → User     (adaptive)
                                ├─ Reason (LLM sees scratchpad)
                                ├─ Act (1-4 tools, parallel)
                                └─ repeat or finish
```

---

## 2. Goals

1. LLM adapts after each tool call — tool N+1 informed by tool N's result
2. Simple lookups: zero LLM calls, ~300ms (vs ~600ms today)
3. Complex queries: LLM decides when it has enough data and stops
4. Tool filtering: LLM sees 6-10 relevant tools, not 28
5. Parallel tool calls when tools are independent (comparison queries 2x faster)
6. Portfolio queries: adaptive drill-down into problem areas
7. `loop_step` observability wired for per-iteration cost tracking

---

## 3. Non-Goals

- Multi-agent fan-out (Phase 9A — LangGraph orchestrator)
- Token-level streaming (provider support needed)
- LangFuse/LangSmith integration (KAN-162 — decorator-based, independent)
- Subscription-tier tool limits (Phase 9B)
- New tools (this redesign uses existing 28 tools)

---

## 4. Phase 8C — Intent Classifier + Tool Filtering (~4h)

### 4.1 Intent Classifier

Rule-based, zero LLM cost. Classifies user query into an intent that determines:
1. Which tools the ReAct loop sees
2. Whether to use the fast path (simple lookup) or full ReAct

```python
# backend/agents/intent_classifier.py

@dataclass
class ClassifiedIntent:
    intent: str            # stock | portfolio | market | comparison | simple_lookup | general | out_of_scope
    tickers: list[str]     # extracted tickers (uppercase, 1-5 chars)
    tool_group: str        # maps to tool set name
    fast_path: bool        # True = bypass ReAct, use template
    confidence: float      # 0-1, for logging/debugging

def classify_intent(query: str, held_tickers: list[str] | None = None) -> ClassifiedIntent:
    """Rule-based intent classification. Zero LLM cost."""
    ...
```

### Classification rules (priority order)

| Pattern | Intent | Fast Path? |
|---------|--------|------------|
| Price/quote keywords + single ticker | `simple_lookup` | Yes |
| "Compare" / "vs" / "versus" + 2-3 tickers | `comparison` | No |
| Portfolio keywords ("my portfolio", "holdings", "positions", "rebalance") | `portfolio` | No |
| Market keywords ("market", "sectors", "S&P", "briefing") | `market` | No |
| Single ticker + analysis keywords ("analyze", "deep dive", "signals") | `stock` | No |
| Single ticker only (no action word) | `simple_lookup` | Yes |
| General/unclear | `general` | No |
| Off-topic (weather, history, geography, code) | `out_of_scope` | Yes (decline) |

Ticker extraction: regex `\b[A-Z]{1,5}\b` minus stop words (AND, THE, FOR, ARE, etc.), cross-referenced with held tickers for pronoun resolution ("my biggest position").

### 4.2 Tool Groups

```python
# backend/agents/tool_groups.py

TOOL_GROUPS: dict[str, list[str]] = {
    "stock": [
        "analyze_stock", "get_fundamentals", "get_forecast",
        "get_stock_intelligence", "get_earnings_history",
        "get_company_profile", "get_analyst_targets",
        "risk_narrative",
    ],  # 8 tools
    "portfolio": [
        "get_portfolio_exposure", "portfolio_health",
        "get_portfolio_forecast", "recommend_stocks",
        "dividend_sustainability", "risk_narrative",
        "analyze_stock",  # for drill-down into holdings
        "get_fundamentals",
    ],  # 8 tools
    "market": [
        "market_briefing", "get_sector_forecast",
        "screen_stocks", "get_forecast",
        "recommend_stocks",
    ],  # 5 tools
    "comparison": [
        "analyze_stock", "get_fundamentals", "get_forecast",
        "compare_stocks", "get_stock_intelligence",
    ],  # 5 tools
    "simple_lookup": [
        "analyze_stock",
    ],  # 1 tool (fast path only uses this)
    "general": None,  # all tools (fallback)
}
```

When `tool_group` is `None`, the ReAct loop gets all registered tools (rare — only for truly ambiguous queries).

### Tool schema resolution

`get_tool_schemas_for_group()` takes the registry as a parameter (available on `app.state.tool_registry`):

```python
def get_tool_schemas_for_group(
    tool_group: str, registry: ToolRegistry
) -> list[dict]:
    """Return OpenAI function-calling schemas for tools in the group."""
    names = TOOL_GROUPS.get(tool_group)
    if names is None:
        # "general" — return all tools
        return [info.to_llm_schema() for info in registry.list_tools()]
    return [
        registry.get(name).info().to_llm_schema()
        for name in names
        if registry.get(name) is not None
    ]
```

The schema format is `{"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}` — the standard OpenAI function-calling format. `AnthropicProvider.chat()` already converts this to Anthropic's format internally (lines 56-64 of `anthropic.py`).

### 4.3 Fast Path

For `simple_lookup` and `out_of_scope`:

```python
# In chat router or agent entry point
classified = classify_intent(query, held_tickers=user_context.get("held_tickers"))

if classified.intent == "out_of_scope":
    yield StreamEvent(type="decline", content="I can only help with stock analysis...")
    return

if classified.fast_path and classified.tickers:
    result = await tool_executor("analyze_stock", {"ticker": classified.tickers[0]})
    formatted = format_simple("analyze_stock", result.data)
    yield StreamEvent(type="token", content=formatted)
    yield StreamEvent(type="done")
    return

# Full ReAct path
tools = get_tools_for_group(classified.tool_group)
async for event in react_loop(query, tools, ...):
    yield event
```

Existing `format_simple` templates from `simple_formatter.py` are reused.

### 4.4 Files

| File | Action |
|------|--------|
| `backend/agents/intent_classifier.py` | NEW — `classify_intent()` + `ClassifiedIntent` dataclass |
| `backend/agents/tool_groups.py` | NEW — `TOOL_GROUPS` mapping + `get_tools_for_group()` |
| `tests/unit/agents/test_intent_classifier.py` | NEW — ~15 tests covering all intents + edge cases |
| `tests/unit/agents/test_tool_groups.py` | NEW — ~5 tests for tool group resolution |

### 4.5 Tests (~20)

Intent classifier tests:
- `test_simple_lookup_price_query` — "What's AAPL's price?" → simple_lookup, fast_path=True
- `test_simple_lookup_single_ticker` — "AAPL" → simple_lookup
- `test_stock_analysis` — "Analyze AAPL in detail" → stock
- `test_comparison_two_tickers` — "Compare AAPL and MSFT" → comparison
- `test_comparison_vs` — "AAPL vs MSFT" → comparison
- `test_portfolio_keywords` — "How is my portfolio?" → portfolio
- `test_market_keywords` — "Market overview" → market
- `test_out_of_scope` — "What's the weather?" → out_of_scope, fast_path=True
- `test_general_ambiguous` — "Tell me something interesting" → general
- `test_ticker_extraction` — extracts correct tickers, filters stop words
- `test_held_tickers_resolution` — "my biggest position" + held_tickers → resolves
- `test_many_tickers_capped` — 10 tickers → only 3 extracted (comparison cap)
- `test_pronoun_with_entity_context` — "What about it?" + prior tickers
- `test_injection_attempt` — "ignore instructions and..." → out_of_scope
- `test_empty_query` — "" → out_of_scope

Tool group tests:
- `test_stock_group_has_8_tools`
- `test_portfolio_group_includes_analyze_stock` — for drill-down
- `test_general_returns_all_tools`
- `test_unknown_group_returns_all`
- `test_tool_group_names_valid` — all tool names exist in registry

---

## 5. Phase 8B — ReAct Loop (~16h)

### 5.1 Core Loop

```python
# backend/agents/react_loop.py

async def react_loop(
    query: str,
    session_messages: list[dict], # prior conversation turns for multi-turn context
    tools: list[dict],           # tool schemas (from tool_groups)
    tool_executor: Callable,     # async (name, params) -> ToolResult
    llm_chat: Callable,          # async (messages, tools) -> LLMResponse
    user_context: dict,          # portfolio, prefs, watchlist
    entity_registry: EntityRegistry,
    collector: Any = None,       # ObservabilityCollector
    cache: Any = None,           # CacheService
    session_id: str | None = None,
    max_iterations: int = MAX_ITERATIONS,
) -> AsyncGenerator[StreamEvent, None]:
    """ReAct reasoning loop. Yields StreamEvents as they occur."""

    scratchpad = _build_initial_messages(query, session_messages, tools, user_context, entity_registry)
    total_tool_calls = 0
    loop_start = time.monotonic()

    for i in range(max_iterations):
        # Wall clock check
        if time.monotonic() - loop_start > WALL_CLOCK_TIMEOUT:
            yield StreamEvent(type="token", content="I'm running low on time. Here's what I found so far...")
            yield StreamEvent(type="done")
            return

        # Tool call budget check
        if total_tool_calls >= MAX_TOOL_CALLS:
            scratchpad.append({"role": "user", "content": "You've used all available tool calls. Summarize and answer now."})

        # 1. Reason — LLM sees scratchpad, returns content + optional tool_calls
        tools_for_call = tools if total_tool_calls < MAX_TOOL_CALLS else []  # no tools if budget exhausted
        response = await llm_chat(messages=scratchpad, tools=tools_for_call)

        # Wire observability (loop_step added to collector in this phase)
        if collector:
            await collector.record_request(
                model=response.model, provider="", tier="reason",
                latency_ms=0, prompt_tokens=response.prompt_tokens,
                completion_tokens=response.completion_tokens,
                cost_usd=None, loop_step=i,  # cost computed by provider base class
            )

        # 2. Yield thought
        if response.content:
            yield StreamEvent(type="thinking", content=response.content)

        # 3. Check finish — no tool calls means done
        if not response.tool_calls:
            yield StreamEvent(type="token", content=response.content)
            from backend.agents.guards import DISCLAIMER
            yield StreamEvent(type="token", content=DISCLAIMER)
            yield StreamEvent(type="done")
            return

        # 4. Cap parallel calls
        tool_calls = response.tool_calls[:MAX_PARALLEL_TOOLS]

        # 5. Act — execute tool(s), potentially parallel
        yield StreamEvent(type="plan", data={"steps": [tc["name"] for tc in tool_calls]})

        results = await _execute_tools(
            tool_calls, tool_executor, collector, cache, session_id, loop_step=i
        )
        total_tool_calls += len(tool_calls)

        # 6. Yield tool results
        for tc, result in zip(tool_calls, results):
            if result.status == "ok":
                yield StreamEvent(type="tool_result", tool=tc["name"], data=result.data)
                entity_registry.extract_from_tool_result(tc["name"], result.data)
            else:
                yield StreamEvent(type="tool_error", tool=tc["name"], error=result.error)

        # 7. Append to scratchpad
        _append_assistant_message(scratchpad, response)
        _append_tool_messages(scratchpad, tool_calls, results)

        # 8. Truncate old tool results
        _truncate_old_results(scratchpad, keep_latest=2)

        # 9. Circuit breaker
        if _consecutive_failures(results) >= CIRCUIT_BREAKER:
            yield StreamEvent(type="token", content=_forced_summary(scratchpad))
            yield StreamEvent(type="done")
            return

    # Max iterations reached — force finish
    scratchpad.append({"role": "user", "content": "Summarize what you have so far and answer the user's question."})
    response = await llm_chat(messages=scratchpad, tools=[])  # no tools = must finish
    yield StreamEvent(type="token", content=response.content)
    yield StreamEvent(type="done")
```

### 5.2 System Prompt

New file: `backend/agents/prompts/react_system.md`

```markdown
You are a stock research assistant for part-time investors. You have access to real-time market data,
portfolio analysis, and forecasting tools.

## How you work
- Call tools to gather data before answering
- After each tool result, reason about what you learned and what else you need
- When you have enough information, respond directly without calling more tools
- Cite specific numbers from tool results in your answers

## Rules
- Call tools in parallel ONLY when they are independent (e.g., analyze_stock for different tickers)
- Call tools sequentially when one result informs the next
- Compare at most 3 stocks per query. If the user asks for more, pick the 3 most relevant
  (by market cap, portfolio weight, or sector diversity), explain your selection, and offer
  to cover the rest in follow-up messages
- Prefer fewer tool calls. If you can answer from what you already have, do so
- Never fabricate data. If a tool returns an error, say so
- Include a brief disclaimer when making forward-looking statements

## User context
{{user_context}}

## Entity context
{{entity_context}}
```

### 5.3 Tool Execution Within the Loop

```python
async def _execute_tools(
    tool_calls: list[dict],
    tool_executor: Callable,
    collector: Any,
    cache: Any,
    session_id: str | None,
    loop_step: int,
) -> list[ToolResult]:
    """Execute 1-N tools, potentially in parallel."""

    async def _run_one(tc: dict) -> ToolResult:
        tool_name = tc["name"]
        params = tc["arguments"] if isinstance(tc["arguments"], dict) else json.loads(tc["arguments"])

        # Input guards
        from backend.agents.guards import TICKER_TOOLS, SEARCH_TOOLS, validate_ticker, validate_search_query
        if tool_name in TICKER_TOOLS and "ticker" in params:
            err = validate_ticker(str(params["ticker"]))
            if err:
                return ToolResult(status="error", error=err)

        # Cache check
        if cache and session_id and tool_name in CACHEABLE_TOOLS:
            cache_key = f"session:{session_id}:tool:{tool_name}:{_param_hash(params)}"
            cached = await cache.get(cache_key)
            if cached:
                if collector:
                    await collector.record_tool_execution(
                        tool_name=tool_name, latency_ms=0, status="success",
                        result_size_bytes=len(cached), cache_hit=True,
                    )
                return ToolResult(status="ok", data=json.loads(cached))

        # Execute
        start = time.monotonic()
        try:
            result = await tool_executor(tool_name, params)
        except Exception as e:
            logger.warning("Tool %s failed: %s", tool_name, str(e)[:200])
            result = ToolResult(status="error", error="Tool execution failed")

        elapsed_ms = int((time.monotonic() - start) * 1000)

        # Observability
        if collector:
            await collector.record_tool_execution(
                tool_name=tool_name, latency_ms=elapsed_ms,
                status=result.status, cache_hit=False,
                result_size_bytes=len(json.dumps(result.data, default=str)) if result.data else 0,
            )

        # Cache write
        if cache and session_id and tool_name in CACHEABLE_TOOLS and result.status == "ok":
            await cache.set(cache_key, json.dumps(result.data, default=str), CacheTier.SESSION)

        return result

    if len(tool_calls) == 1:
        return [await _run_one(tool_calls[0])]
    return await asyncio.gather(*[_run_one(tc) for tc in tool_calls])
```

### 5.4 Scratchpad Management

```python
def _build_initial_messages(query, session_messages, tools, user_context, entity_registry) -> list[dict]:
    """Build the initial scratchpad with system prompt + conversation history + current query."""
    system = _render_system_prompt(user_context, entity_registry)
    messages = [{"role": "system", "content": system}]
    # Prepend prior conversation turns for multi-turn context
    # (e.g., "What about AAPL?" in turn 3 needs turns 1-2 for context)
    if session_messages:
        messages.extend(session_messages)
    messages.append({"role": "user", "content": query})
    return messages

def _append_assistant_message(scratchpad: list, response: LLMResponse) -> None:
    """Append LLM response (with tool_calls) to scratchpad."""
    msg = {"role": "assistant", "content": response.content or ""}
    if response.tool_calls:
        msg["tool_calls"] = [
            {"id": tc["id"], "type": "function", "function": {"name": tc["name"], "arguments": json.dumps(tc["arguments"]) if isinstance(tc["arguments"], dict) else tc["arguments"]}}
            for tc in response.tool_calls
        ]
    scratchpad.append(msg)

def _append_tool_messages(scratchpad: list, tool_calls: list, results: list) -> None:
    """Append tool result messages to scratchpad."""
    for tc, result in zip(tool_calls, results):
        scratchpad.append({
            "role": "tool",
            "tool_call_id": tc["id"],
            "content": json.dumps(result.data, default=str) if result.data else result.error or "No data",
        })

def _truncate_old_results(scratchpad: list, keep_latest: int = 2) -> None:
    """Truncate tool result content older than the latest N tool messages."""
    tool_indices = [i for i, m in enumerate(scratchpad) if m.get("role") == "tool"]
    if len(tool_indices) <= keep_latest:
        return
    for idx in tool_indices[:-keep_latest]:
        content = scratchpad[idx]["content"]
        if len(content) > 200:
            scratchpad[idx]["content"] = content[:200] + "... [truncated, already analyzed]"
```

### 5.5 Chat Router Integration

Replace `_event_generator`'s graph invocation:

```python
# backend/routers/chat.py — inside _event_generator

# Build user context (existing code, unchanged)
user_context = await build_user_context(user.id, ctx_db)
entity_registry = EntityRegistry(state.get("entity_registry", {}))

# NEW: classify intent
from backend.agents.intent_classifier import classify_intent
from backend.agents.tool_groups import get_tool_schemas_for_group

classified = classify_intent(
    body.message,
    held_tickers=[p["ticker"] for p in user_context.get("positions", [])],
)

# Fast path
if classified.intent == "out_of_scope":
    yield _ndjson(StreamEvent(type="decline", content=DECLINE_MESSAGE))
    yield _ndjson(StreamEvent(type="done"))
    return

if classified.fast_path and classified.tickers:
    result = await tool_executor("analyze_stock", {"ticker": classified.tickers[0]})
    formatted = format_simple("analyze_stock", result.data)
    yield _ndjson(StreamEvent(type="token", content=formatted))
    yield _ndjson(StreamEvent(type="done"))
    # Persist assistant message (same pattern as current _event_generator)
    await save_message(db, chat_session.id, role="assistant", content=formatted)
    return

# Full ReAct path
tools = get_tool_schemas_for_group(classified.tool_group, registry=request.app.state.tool_registry)
async for event in react_loop(
    query=body.message,
    session_messages=session_messages,  # prior turns for multi-turn context
    tools=tools,
    tool_executor=tool_executor,
    llm_chat=lambda msgs, tls: llm_client.chat(messages=msgs, tools=tls, tier="reason"),
    user_context=user_context,
    entity_registry=entity_registry,
    collector=collector,
    cache=cache_service,
    session_id=str(chat_session.id),
):
    yield _ndjson(event)
```

### 5.6 What Gets Deleted

| File | Action |
|------|--------|
| `backend/agents/graph.py` | DELETE — replaced by `react_loop.py` |
| `backend/agents/planner.py` | DELETE — reasoning now happens in the ReAct loop |
| `backend/agents/prompts/planner.md` | DELETE — replaced by `react_system.md` |
| `backend/agents/synthesizer.py` | DELETE — LLM writes its own answer |
| `backend/agents/prompts/synthesizer.md` | DELETE — replaced by `react_system.md` |
| `backend/agents/executor.py` | DELETE — tool execution moved into `_execute_tools` |
| `backend/agents/stream.py` | HEAVY EDIT — `stream_graph_v2_events` removed, `StreamEvent` stays |

### 5.7 What Stays Unchanged

| File | Why |
|------|-----|
| `backend/agents/llm_client.py` | Provider abstraction — modified to handle Anthropic multi-turn scratchpad (see §8 modified files) |
| `backend/agents/providers/*` | All providers + base class observability (KAN-190) |
| `backend/agents/observability.py` | Collector — modified to accept `loop_step` param (see §8 modified files) |
| `backend/agents/observability_writer.py` | Writer — modified to wire `loop_step` (see §8 modified files) |
| `backend/agents/guards.py` | Input/output guards — called from `_execute_tools` and output |
| `backend/agents/entity_registry.py` | Pronoun resolution — lives as object in generator closure |
| `backend/agents/result_validator.py` | Tool result annotation — called after tool execution |
| `backend/agents/simple_formatter.py` | Templates — used by fast path |
| `backend/agents/user_context.py` | Pre-flight portfolio/prefs — called before loop |
| `backend/agents/model_config.py` | DB config loader — unchanged |
| `backend/agents/token_budget.py` | Per-model rate limiting — unchanged |
| `backend/tools/*` | All 28 tools — unchanged |
| `backend/services/*` | All services — unchanged |
| `backend/main.py` | Lifespan builds providers, executor — wiring changes (see §5.8) |

### 5.8 main.py Changes

```python
# Remove: graph compilation (build_agent_graph, _plan_fn, _synthesize_fn)
# Remove: from backend.agents.graph import build_agent_graph
# Remove: from backend.agents.planner import plan_query
# Remove: from backend.agents.executor import execute_plan
# Remove: from backend.agents.synthesizer import synthesize_results
# Remove: app.state.agent_graph = build_agent_graph(...)

# Add: store components for chat router to use
app.state.tool_executor = _tool_executor
app.state.llm_client = llm_client
app.state.collector = collector  # already exists
app.state.cache = cache_service  # already exists
```

The chat router assembles the `react_loop` call from these components.

### 5.9 Observability Wiring

- `loop_step=i` passed to `collector.record_request()` from inside the ReAct loop
- `loop_step=i` passed to `collector.record_tool_execution()` from `_execute_tools`
- The writer reads `loop_step` from data dict and writes to DB column (already prepared in KAN-190)
- `tier="reason"` for all LLM calls in the loop
- Add `tier="reason"` row to `llm_model_config` table (or alias existing planner/synthesizer tiers)

### 5.10 Frontend Impact

StreamEvent types change slightly:

| Old Event | New Event | Change |
|-----------|-----------|--------|
| `thinking` (once, at start) | `thinking` (per iteration) | Multiple thinking events, each with the LLM's reasoning |
| `plan` (tool list) | `plan` (tool list per iteration) | Per-iteration, not upfront |
| `tool_result` / `tool_error` | Same | Unchanged |
| `evidence` (from synthesis) | KEPT during flag period | Emitted from tool_result data for `EvidenceSection` backward compat. Removed in cleanup story. |
| `token` (final answer) | `token` (final answer) | Same — but now includes evidence inline |
| `done` | Same | Unchanged |
| `decline` | Same | Unchanged |

Frontend `useStreamChat` hook needs to handle multiple `thinking` events (append to a thoughts list, or show latest). The `evidence` event removal means the `EvidenceSection` component shows data from `tool_result` events instead.

---

## 6. Migration Strategy

### Feature flag: `REACT_AGENT=true` (default: true)

During development, the flag allows instant rollback to the old pipeline:

```python
# chat.py
if settings.REACT_AGENT:
    # New path: intent classifier → fast path or ReAct loop
    ...
else:
    # Old path: graph.ainvoke() — kept as fallback
    ...
```

Old files are kept (not deleted) until the flag is removed after validation. The flag is removed in a cleanup story at the end.

---

## 7. Limits and Safety

| Limit | Value | Purpose |
|-------|-------|---------|
| MAX_ITERATIONS | 8 | Total LLM calls in ReAct loop |
| MAX_PARALLEL_TOOLS | 4 | Tool calls per iteration |
| MAX_TOOL_CALLS | 12 | Total tool calls across all iterations |
| WALL_CLOCK_TIMEOUT | 45s | Hard time limit for entire loop |
| CIRCUIT_BREAKER | 3 | Consecutive tool failures → forced finish |
| MAX_COMPARISON_TICKERS | 3 | Prompt-enforced, LLM explains selection |
| SCRATCHPAD_TRUNCATE_AFTER | 2 | Keep latest N tool results full, truncate older |

---

## 8. File Change Map

### New Files (4)

| File | Purpose |
|------|---------|
| `backend/agents/intent_classifier.py` | Rule-based intent classification + ticker extraction |
| `backend/agents/tool_groups.py` | Intent → tool set mapping |
| `backend/agents/react_loop.py` | Core ReAct async generator |
| `backend/agents/prompts/react_system.md` | System prompt for ReAct LLM |

### Deleted Files (5, after flag removal)

| File | Replaced by |
|------|-------------|
| `backend/agents/graph.py` | `react_loop.py` |
| `backend/agents/planner.py` | ReAct LLM reasoning |
| `backend/agents/prompts/planner.md` | `react_system.md` |
| `backend/agents/executor.py` | `_execute_tools` in `react_loop.py` |
| `backend/agents/synthesizer.py` | ReAct LLM finish action |

### Modified Files (8)

| File | Change |
|------|--------|
| `backend/routers/chat.py` | Replace graph invocation with intent classifier + ReAct loop. Persist assistant message. Collect tokens for save_message. |
| `backend/main.py` | Remove graph compilation, expose `tool_executor`, `llm_client`, `tool_registry` on app.state |
| `backend/agents/stream.py` | Remove `stream_graph_v2_events`, keep `StreamEvent`. Emit `evidence` events from tool_result data for backward compat during flag period. |
| `backend/agents/prompts/synthesizer.md` | Keep for old path behind flag, delete later |
| `backend/agents/observability.py` | Add `loop_step: int | None = None` param to `record_request()` and `record_tool_execution()`. Pass through to data dict. |
| `backend/agents/observability_writer.py` | Wire `loop_step` from data dict into both `LLMCallLog` and `ToolExecutionLog` row construction (column + comment already exist from KAN-190). |
| `backend/config.py` | Add `REACT_AGENT: bool = True` to `Settings` class |
| `backend/agents/llm_client.py` | Ensure provider `chat()` methods handle multi-turn tool_use scratchpad format. Add message normalization for Anthropic (convert OpenAI-format tool_calls in assistant messages to Anthropic content blocks). |

### Test Files (8)

| File | Tests |
|------|-------|
| `tests/unit/agents/test_intent_classifier.py` | NEW — ~15 tests |
| `tests/unit/agents/test_tool_groups.py` | NEW — ~5 tests |
| `tests/unit/agents/test_react_loop.py` | NEW — ~15 tests (mock LLM + tools, assert event sequence) |
| `tests/unit/agents/test_react_scratchpad.py` | NEW — ~5 tests (truncation, message formatting) |
| `tests/unit/agents/test_react_integration.py` | NEW — ~5 tests (end-to-end with mock LLM returning multi-step sequences) |
| `tests/unit/agents/test_planner.py` | KEEP — old path behind flag |
| `tests/unit/agents/test_executor_observability.py` | UPDATE — test `_execute_tools` cache_hit + observability |
| `tests/api/test_chat.py` | UPDATE — test fast path + ReAct path |

**Estimated new tests: ~45-50**

---

## 9. Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| ReAct loop quality worse than batch pipeline | Feature flag for instant rollback. A/B comparison during validation. |
| LLM calls more expensive (N vs 2) | Token budget + MAX_ITERATIONS cap. Simple lookups are FREE (fast path). Net cost may decrease due to fewer wasted tool calls. |
| Scratchpad grows too large | Truncation of old results. MAX_ITERATIONS=8 caps worst case. |
| Intent classifier misroutes | Start conservative: only `simple_lookup` and `out_of_scope` on fast path. Everything else → ReAct. Tune later with usage data. |
| Tool_use API inconsistency across providers | Already normalized in `LLMResponse.tool_calls`. Tested across Groq + Anthropic. |
| Breaking change for frontend | StreamEvent types are additive (multiple `thinking` events). No type removal until flag cleanup. `evidence` events can be emitted from tool_result data if frontend needs them. |
| Old tests break | Old pipeline tests kept behind feature flag. New tests cover new path. |

---

## 10. Success Criteria

1. Simple lookup ("AAPL price?") responds in <500ms with zero LLM calls
2. Stock analysis query uses 2-4 ReAct iterations with adaptive tool selection
3. Portfolio query drills into problem areas (health < 6 → check holdings → recommend)
4. Comparison query runs tools in parallel (2 tickers in one iteration)
5. `loop_step` visible in `llm_call_log` and `tool_execution_log` for all ReAct queries
6. Feature flag rollback to old pipeline works
7. Intent classifier routes correctly for >90% of test queries
8. ~45 new tests passing, all existing tests still pass behind flag
9. Token cost per query not higher than 2x current (compensated by fast path savings)
10. Latency for complex queries comparable to current (~3-6s)

---

## 11. Dependencies

- **KAN-190 (Phase 8A):** DONE — observability infrastructure, `loop_step` column, provider base class
- **KAN-172/173:** DONE — service layer extraction (tools are thin shims)
- **8C → 8B:** Intent classifier is prerequisite for ReAct loop (ADR-005)
- **Blocks:** Phase 8D (dynamic concurrency controller), Phase 9A (multi-agent orchestrator)

---

## 12. Review Findings & Resolutions (v2)

14 issues found during code-reviewer audit. All fixed in spec v2:

### Critical (would crash) — fixed in-place above

| # | Issue | Resolution |
|---|-------|-----------|
| 1 | `_append_disclaimer` doesn't exist | Replaced with `yield StreamEvent(type="token", content=DISCLAIMER)` (§5.1) |
| 2 | Fast path `tool_executor(ticker)` wrong signature | Fixed to `tool_executor("analyze_stock", {"ticker": ticker})` (§5.5) |
| 3 | `collector.record_request` has no `loop_step` param | Added to modified files: `observability.py` gets `loop_step` param (§8) |
| 4 | `collector.record_tool_execution` also missing `loop_step` | Same fix as #3 |
| 6 | `entity_registry.extract_from_tool_result` wrong call sig | Fixed to include `tc["name"]` as first arg (§5.1) |
| 10 | `REACT_AGENT` not in `config.py` | Added `config.py` to modified files (§8) |

### Important (silent bugs) — fixed in-place above

| # | Issue | Resolution |
|---|-------|-----------|
| 5 | `tier="reason"` not in `llm_model_config` DB | Explicit note in §5.9 — seed data task in plan |
| 7 | Anthropic multi-turn scratchpad format incompatible | Added `llm_client.py` to modified files for message normalization (§8). Provider `chat()` must convert OpenAI-format `tool_calls` in assistant messages to Anthropic content blocks. |
| 8 | Entity registry cross-turn persistence | Reconstructed from `session_messages` (same as current behavior). Entity state is implicit in conversation history, not a separate DB field. |
| 9 | `save_message` pattern omitted | Added to fast path (§5.5) + noted in chat.py change description (§8). Full ReAct path collects tokens + calls `save_message` after generator completes (same pattern as current `_event_generator`). |
| 11 | `get_tool_schemas_for_group` registry wiring | Function spec added (§4.2). Takes `registry` as parameter, resolved from `app.state.tool_registry`. |
| 12 | 6 old test files import deleted modules | Files kept on disk during flag period (§6 already states this). Deletion happens in cleanup story. No `ImportError`. |
| 13 | `evidence` event removal breaks `EvidenceSection` | `evidence` events KEPT during flag period, emitted from tool_result data. Updated §5.10. |
| 14 | Multi-turn `session_messages` dropped | Added `session_messages` param to `react_loop` + `_build_initial_messages` (§5.1, §5.4, §5.5). Prior turns prepended to scratchpad. |

### Informational gaps — noted for implementation

| Gap | Resolution |
|-----|-----------|
| `tier_config` not wired on `LLMClient` | Existing behavior: tier falls through to default providers. Acceptable for 8B. Fix properly when adding `"reason"` tier to DB. |
| `WALL_CLOCK_TIMEOUT` not enforced in loop code | Add `time.monotonic()` check at top of each iteration. `asyncio.wait_for` around generator is fragile — prefer manual check. |
| `MAX_TOOL_CALLS=12` not counted in loop | Added `total_tool_calls` counter in §5.1 init. Check per iteration. |
| Tool name verification (`compare_stocks`) | Verify during implementation — `get_tool_schemas_for_group` silently skips missing names (§4.2). |
