# Architecture Decision Records (ADR)

Captures significant architecture decisions with context, options considered, and rationale.
These decisions are load-bearing — changing them requires a new ADR, not a silent edit.

---

## ADR-001: Pure Async Generator for ReAct Loop (not LangGraph)

**Date:** 2026-03-27 | **Status:** Implemented (Session 63, PR #128) | **Context:** Phase 8B (KAN-189)

### Decision
Use a pure async generator function for the single-agent ReAct loop. Reserve LangGraph for the multi-agent orchestrator (Phase 9A).

### Options Considered

| Option | Pros | Cons |
|--------|------|------|
| **A) LangGraph StateGraph** | Auto-tracing with LangSmith, graph visualization | `ainvoke` blocks (no mid-loop streaming), state must serialize through TypedDict between every node, error handling requires state-based routing, imperative loop forced into declarative edges |
| **B) Pure async generator** | Full streaming control via `yield`, state is local variables (no serialization), normal try/except, top-to-bottom readability, standard unit testing | No auto-tracing (need ~15 lines of `@observe` decorators), no graph visualization |

### Rationale
- A ReAct loop is fundamentally imperative: reason → check → act → append → repeat. Encoding this as graph edges adds complexity without benefit.
- LangGraph's auto-tracing saves ~15 lines but constrains streaming and state management.
- The generator becomes a **building block** for Phase 9A — it's called from inside a LangGraph orchestrator node. Zero rewrite.
- LangGraph excels at multi-agent orchestration (routing, fan-out, state merging, parallel branches) — that's Phase 9A's problem, not 8B's.

### Consequences
- We keep LangGraph as a dependency for Phase 9A but don't use it for the single-agent loop.
- LangFuse/LangSmith integration requires manual `@observe` decorators (~15 lines) instead of automatic callback handlers.
- Testing is simpler: mock `llm_chat` + `tool_executor`, iterate the generator, assert on results.

---

## ADR-002: Native Tool Use API (not JSON-in-Content)

**Date:** 2026-03-27 | **Status:** Implemented (Session 63) | **Context:** Phase 8B (KAN-189)

### Decision
Use provider-native function calling (tool_use API) for the ReAct loop, not JSON-in-content parsing.

### Options Considered

| Option | Pros | Cons |
|--------|------|------|
| **A) JSON-in-content** | Provider-agnostic, works with any LLM, we have parsing code already | Fragile parsing, no schema enforcement, thought + action bundled in one JSON blob |
| **B) Native tool_use API** | Schema enforcement by provider, natural interleave of reasoning (content) + actions (tool_calls), "finish" = no tool calls (no special action needed) | Requires provider support (all three of ours support it) |

### Rationale
- Our `LLMResponse.tool_calls` already normalizes across Groq/Anthropic/OpenAI — the abstraction layer exists.
- Schema enforcement catches malformed params before they hit our tool executor.
- The scratchpad follows the standard `role: "assistant"` + `role: "tool"` protocol that all providers expect for multi-turn tool use.
- Portability: if we ever need a text-only provider, a thin `TextOnlyProvider` adapter (~15 lines) wraps JSON-in-content as fake `tool_calls` on `LLMResponse`.

### Consequences
- Providers that don't support tool_use need an adapter class.
- The planner prompt changes: instead of "respond with JSON," we provide tool schemas and let the provider handle structured output.
- `planner.md` few-shot examples need rewriting (from JSON output to natural language + tool calls).

---

## ADR-003: Parallel Tool Calls (LLM-Decided, Capped)

**Date:** 2026-03-27 | **Status:** Implemented (Session 63) | **Context:** Phase 8B (KAN-189)

### Decision
Allow the LLM to return multiple tool calls per iteration. Execute them concurrently via `asyncio.gather`. Cap at MAX_PARALLEL_TOOLS = 4.

### Options Considered

| Option | Pros | Cons |
|--------|------|------|
| **A) Strict 1 tool per iteration** | Maximum adaptivity — every tool call informed by previous result | Slow for comparison queries (3 serial analyze_stock calls) |
| **B) Parallel, LLM-decided** | Faster for independent calls (comparison, multi-ticker), fewer LLM iterations | Parallel calls decided before seeing results |

### Rationale
- The tool_use API natively supports 1 or N tool calls per response — no artificial limit needed at the protocol level.
- The LLM naturally calls 1 tool when reasoning step-by-step and multiple when they're independent.
- Prompt guidance instructs: "call tools in parallel ONLY when independent."
- MAX_PARALLEL_TOOLS = 4 prevents a hallucinating model from calling 15 tools at once.
- Comparison queries ("Compare AAPL and MSFT") go from 4 iterations to 2.

### Guards Against Excessive Calls
1. **Tool filtering (8C):** LLM sees 8 tools, not 28 — fewer options to abuse.
2. **Prompt instruction:** "Compare at most 3 stocks. If the user provides more, pick the 3 most relevant by market cap or portfolio holdings, explain why, and offer to cover the rest in follow-up messages."
3. **MAX_PARALLEL_TOOLS = 4:** Code cap per iteration.
4. **MAX_ITERATIONS = 8:** Total loop iterations.
5. **WALL_CLOCK_TIMEOUT = 45s:** Hard time limit.
6. **TokenBudget:** Per-model TPM/RPM sliding windows.

### Consequences
- Implementation uses `asyncio.gather` for tool execution within an iteration.
- Multiple `role: "tool"` messages appended to scratchpad per iteration (standard tool_use protocol).
- The 3-stock comparison limit is enforced by prompt, not code — LLM explains its selection to the user.

---

## ADR-004: Pre-Router Fast Path for Simple Lookups

**Date:** 2026-03-27 | **Status:** Implemented (Session 63) | **Context:** Phase 8B + 8C (KAN-189)

### Decision
Keep a fast path that bypasses the ReAct loop for simple lookups. The 8C intent classifier routes `simple_lookup` queries directly to tool + template formatting — zero LLM calls.

### Options Considered

| Option | Pros | Cons |
|--------|------|------|
| **A) Everything through ReAct** | One code path, simplest | 2 LLM calls for "What's AAPL's price?" (~$0.001, ~600ms) |
| **B) Pre-router fast path** | Zero LLM calls for simple lookups (~$0, ~300ms) | Two code paths, need intent classifier |

### Rationale
- ~40% of queries in a stock app are simple lookups ("price?", "RSI?", "signals?").
- 2 LLM calls per simple lookup is wasteful when a regex + tool + template achieves the same result.
- The 8C intent classifier is already planned — it powers both tool filtering AND fast-path routing.
- The existing `format_simple` templates are reused.

### Build Order Consequence
This makes 8C (tool filtering + intent classifier) a **prerequisite** for 8B (ReAct loop), not a parallel track:
```
8C (intent classifier + tool filtering, ~4h) → 8B (ReAct loop, ~16h)
```

### Consequences
- Two code paths: fast path (classifier → tool → template) and full path (classifier → ReAct loop with filtered tools).
- The classifier must be high-precision for `simple_lookup` — a false positive skips ReAct and gives a shallow answer.
- Testing requires coverage of both paths.

---

## ADR-005: 8C Before 8B (Tool Filtering is a Prerequisite)

**Date:** 2026-03-27 | **Status:** Implemented (Session 63) | **Context:** Phase 8B + 8C (KAN-189)

### Decision
Build the intent classifier and tool filtering (8C) before the ReAct loop (8B).

### Rationale
The ReAct loop depends on 8C in two ways:
1. **Fast path routing** (ADR-004): simple lookups bypass ReAct entirely.
2. **Tool filtering:** ReAct with 28 tools produces worse quality than with 8-10 filtered tools. The LLM makes better parallel-call decisions with fewer options.

### Build Sequence
```
Phase 8C (~4h):
  - Rule-based intent classifier (keyword match, zero LLM cost)
  - Intent → tool group mapping (stock: 8, portfolio: 6, market: 5, comparison: stock+compare, general: all)
  - Fast path: simple_lookup → extract ticker → tool → template → done

Phase 8B (~16h):
  - Pure async generator ReAct loop
  - Uses 8C classifier for tool set selection
  - System prompt + tool_use API
  - Scratchpad management with old-result truncation
  - Observability wiring (loop_step, tier="reason")
  - Streaming events from inside the loop
```

---

## ADR-006: Scratchpad Optimization Strategy

**Date:** 2026-03-27 | **Status:** Implemented (Session 63) | **Context:** Phase 8B (KAN-189)

### Decision
Truncate older tool results in the scratchpad to manage token cost growth. Keep latest results full, compress older ones.

### Problem
Scratchpad grows every iteration. Sending the entire history re-sends all previous tool results. Token cost is O(n^2) across iterations.

### Strategy (phased)
1. **Phase 8B (implement now):** Truncate tool results older than the latest 2 to MAX_TOOL_RESULT_CHARS (setting already exists). Append `"... [truncated, already analyzed]"` suffix.
2. **If needed later:** Per-tool result formatters that extract only decision-relevant fields.
3. **If needed later:** Sliding window on scratchpad messages (keep first 2 + last N).

### Rationale
Option 1 is low-effort and sufficient. At MAX_ITERATIONS=8 with truncation, worst-case scratchpad is ~4K tokens (vs ~8K+ without). The existing `MAX_TOOL_RESULT_CHARS` setting provides a tuning knob without code changes.

---

## ADR-007: Observability Wiring for ReAct

**Date:** 2026-03-27 | **Status:** Implemented (Session 63) | **Context:** Phase 8B (KAN-189), builds on KAN-190

### Decision
Wire `loop_step` into the observability writer. Use `tier="reason"` for all ReAct LLM calls.

### Context
KAN-190 (Session 62) pre-added `loop_step` (Integer, nullable) and `agent_instance_id` (UUID, nullable) columns to both log tables. The writer has comments: "deferred to Phase 8B."

### Wiring
- Each ReAct iteration passes `loop_step=i` in the data dict to `collector.record_request()`.
- The observability writer reads it and writes to the DB column.
- `tier="reason"` replaces `tier="planner"` / `tier="synthesizer"` — single LLM role in ReAct.
- `agent_type` ContextVar (set in chat.py) continues to work unchanged.

### Consequences
- Per-query cost endpoint now shows per-iteration cost (N rows per query instead of 2).
- `tier="planner"` / `tier="synthesizer"` rows stop appearing for new queries. Old rows in DB keep their tier values.
- `llm_model_config` tier column: existing "planner" and "synthesizer" tiers either map to "reason" or we keep both pointed at the same models. Simplest: add `tier="reason"` rows, keep old rows for backward compatibility.

---

## ADR-008: Portfolio Query Handling in ReAct

**Date:** 2026-03-27 | **Status:** Implemented (Session 63) | **Context:** Phase 8B (KAN-189)

### Decision
Portfolio queries use the same ReAct loop with portfolio-filtered tool set. The LLM adaptively drills into problem areas.

### Current Portfolio Tools
| Tool | Purpose | Needs user_id? |
|------|---------|----------------|
| `get_portfolio_exposure` | Sector allocation, total value, P&L, concentration | Yes (ContextVar) |
| `portfolio_health` | 0-10 health score (diversification, signals, risk, income, sector) | Yes (ContextVar) |
| `get_portfolio_forecast` | Aggregate forecast from individual stock forecasts | Yes (ContextVar) |
| `recommend_stocks` | Multi-signal ranking with portfolio fit weighting | Yes (ContextVar) |
| `dividend_sustainability` | Payout ratio, FCF coverage for specific ticker | No (ticker param) |
| `risk_narrative` | Ranked risk factors for specific ticker | No (ticker param) |

### How It Works
1. User: "Analyze my portfolio"
2. 8C classifier → intent: `portfolio` → filtered tool set (6 portfolio tools + a few stock tools for drill-down)
3. `user_context` (pre-loaded before loop) gives LLM the list of held tickers
4. ReAct loop:
   - Iteration 1: LLM calls `get_portfolio_exposure` + `portfolio_health` (parallel)
   - Iteration 2: LLM sees health=4.2, concentrated → calls `analyze_stock` for top holdings
   - Iteration 3: LLM sees weak signals on AAPL → calls `recommend_stocks` for rebalancing
   - Iteration 4: finish with actionable answer

### Key Design Points
- Portfolio tools use `current_user_id` ContextVar — no explicit user_id param needed. The LLM just calls the tool.
- The LLM knows held tickers from `user_context` — can decide which to drill into.
- Healthy portfolios get quick 2-iteration answers. Sick portfolios get deeper investigation automatically. This is the core value of ReAct over the batch pipeline.
- `agent_type` for portfolio queries: currently "general" — consider adding "portfolio" type for cost attribution.

### Consequences
- Portfolio queries tend to use more iterations (3-5) than simple stock queries (2-3) because the LLM drills into problems.
- KAN-149 (portfolio aggregation for large portfolios) is a tool optimization, not a ReAct design concern — the loop calls whatever tools exist.

---

## ADR Index

| # | Decision | Phase | Date |
|---|----------|-------|------|
| 001 | Pure async generator for ReAct (LangGraph for 9A orchestrator) | 8B | 2026-03-27 |
| 002 | Native tool_use API (not JSON-in-content) | 8B | 2026-03-27 |
| 003 | Parallel tool calls, LLM-decided, capped at 4 | 8B | 2026-03-27 |
| 004 | Pre-router fast path for simple lookups | 8B+8C | 2026-03-27 |
| 005 | 8C before 8B (tool filtering is prerequisite) | 8B+8C | 2026-03-27 |
| 006 | Scratchpad truncation for token cost management | 8B | 2026-03-27 |
| 007 | Observability wiring — loop_step + tier="reason" | 8B | 2026-03-27 |
| 008 | Portfolio queries use ReAct with adaptive drill-down | 8B | 2026-03-27 |
