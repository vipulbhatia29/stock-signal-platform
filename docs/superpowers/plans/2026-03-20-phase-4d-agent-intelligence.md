# Phase 4D — Agent Intelligence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current single ReAct agent loop with a three-phase Plan→Execute→Synthesize architecture that produces factual, data-grounded financial analysis with full evidence lineage.

**Architecture:** Sonnet plans + mechanical executor (no LLM) calls tools + Sonnet synthesizes. Feature-flagged behind `AGENT_V2=true`. New yfinance tools enrich the data layer. Cross-session memory injects portfolio context. All outputs grounded in tool results.

**Tech Stack:** LangGraph StateGraph, Claude Sonnet (planner/synthesizer), ToolRegistry (mechanical executor), yfinance, Pydantic v2, pytest, Alembic

**Spec:** `docs/superpowers/specs/2026-03-20-phase-4d-agent-intelligence-design.md`

---

## File Structure

### New Files
| File | Responsibility |
|---|---|
| `backend/tools/fundamentals_tool.py` | Registered tool wrapping extended `fetch_fundamentals()` — financials, growth, margins |
| `backend/tools/analyst_targets_tool.py` | Registered tool: yfinance analyst price targets (current, high, low, mean, median) |
| `backend/tools/earnings_history_tool.py` | Registered tool: yfinance earnings history + surprise % |
| `backend/tools/company_profile_tool.py` | Registered tool: yfinance company profile (summary, sector, employees, market cap) |
| `backend/agents/planner.py` | Plan node: classifies intent, checks scope, generates tool plan |
| `backend/agents/executor.py` | Mechanical executor: runs tool plan, validates results, handles $PREV_RESULT |
| `backend/agents/synthesizer.py` | Synthesis node: builds confidence, scenarios, evidence tree |
| `backend/agents/graph_v2.py` | New 3-phase LangGraph StateGraph (coexists with graph.py behind feature flag) |
| `backend/agents/user_context.py` | `build_user_context()` utility — DB query for portfolio + preferences |
| `backend/agents/result_validator.py` | Tool result validation layer (null check, staleness, schema) |
| `backend/agents/simple_formatter.py` | Template-based formatter for simple queries (no LLM) |
| `backend/agents/prompts/planner.md` | Planner few-shot prompt with scope enforcement |
| `backend/agents/prompts/synthesizer.md` | Synthesizer few-shot prompt with evidence rules |
| `backend/migrations/versions/XXX_009_agent_v2.py` | Migration: feedback on ChatMessage, tier+query_id on LLMCallLog, query_id on ToolExecutionLog |
| `tests/unit/test_planner.py` | Planner unit tests (scope, intent, plan generation) |
| `tests/unit/test_executor.py` | Executor unit tests (tool calling, $PREV_RESULT, retries, circuit breaker) |
| `tests/unit/test_synthesizer.py` | Synthesizer unit tests (confidence, scenarios, evidence) |
| `tests/unit/test_result_validator.py` | Validation layer tests |
| `tests/unit/test_user_context.py` | User context builder tests |
| `tests/unit/test_fundamentals_tool.py` | Fundamentals tool tests |
| `tests/unit/test_analyst_targets.py` | Analyst targets tool tests |
| `tests/unit/test_earnings_history.py` | Earnings history tool tests |
| `tests/unit/test_company_profile.py` | Company profile tool tests |
| `tests/unit/test_simple_formatter.py` | Simple query formatter tests |
| `tests/integration/test_agent_v2_flow.py` | Full 3-phase integration test (mocked tools) |
| `frontend/src/components/chat/plan-display.tsx` | Plan event component (shows "Here's what I'm researching...") |
| `frontend/src/components/chat/evidence-section.tsx` | Collapsible evidence tree component |
| `frontend/src/components/chat/feedback-buttons.tsx` | Thumbs up/down component |
| `frontend/src/components/chat/decline-message.tsx` | Scope decline message component |

### Modified Files
| File | Change |
|---|---|
| `backend/agents/llm_client.py` | Add `tier_config` dict constructor, `tier` param on `chat()` |
| `backend/agents/stream.py` | Add `plan`, `tool_error`, `evidence`, `decline` event types |
| `backend/agents/base.py` | Keep for backward compat (feature flag off), no changes |
| `backend/routers/chat.py` | Inject user context, add query_id, feature flag graph selection, concurrent query guard |
| `backend/main.py` | Build graph_v2 at startup when `AGENT_V2=true`, register new tools |
| `backend/config.py` | Add `AGENT_V2: bool = False` setting |
| `backend/models/chat.py` | Add `feedback` column |
| `backend/models/logs.py` | Add `tier`, `query_id` to LLMCallLog; `query_id` to ToolExecutionLog |
| `backend/tools/fundamentals.py` | Extend `fetch_fundamentals()` to return financials, growth, margins |
| `frontend/src/types/api.ts` | Add new StreamEvent types, FeedbackRequest |
| `frontend/src/components/chat/message-bubble.tsx` | Add feedback buttons, evidence section |
| `frontend/src/components/chat/chat-panel.tsx` | Handle new event types (plan, evidence, decline) |
| `frontend/src/hooks/use-stream-chat.ts` | Handle new NDJSON event types |

---

## Chunk 1: New yfinance Tools (Tasks 1-4)

Independent of agent rewrite. Enriches data layer. Ship first.

### Task 1: Extend fetch_fundamentals with full financial data

**Files:**
- Modify: `backend/tools/fundamentals.py`
- Test: `tests/unit/test_fundamentals_tool.py`

- [ ] **Step 1: Write failing test for extended fundamentals**

```python
# tests/unit/test_fundamentals_tool.py
"""Tests for extended fundamentals data from yfinance."""
import pytest
from unittest.mock import patch, MagicMock

@pytest.mark.asyncio
async def test_fetch_fundamentals_includes_financials():
    """Extended fundamentals should include revenue, net income, margins."""
    with patch("backend.tools.fundamentals.yf.Ticker") as mock_ticker:
        mock_info = {
            "trailingPE": 28.5,
            "pegRatio": 1.2,
            "debtToEquity": 45.0,
            "revenueGrowth": 0.21,
            "grossMargins": 0.82,
            "operatingMargins": 0.41,
            "profitMargins": 0.36,
            "returnOnEquity": 0.26,
            "marketCap": 362000000000,
            "enterpriseValue": 365000000000,
        }
        mock_ticker.return_value.info = mock_info
        mock_ticker.return_value.quarterly_income_stmt = MagicMock(empty=True)
        mock_ticker.return_value.quarterly_balance_sheet = MagicMock(empty=True)
        mock_ticker.return_value.quarterly_cashflow = MagicMock(empty=True)

        from backend.tools.fundamentals import fetch_fundamentals
        result = fetch_fundamentals("PLTR")

        assert result.revenue_growth == 0.21
        assert result.gross_margins == 0.82
        assert result.operating_margins == 0.41
        assert result.profit_margins == 0.36
        assert result.return_on_equity == 0.26
        assert result.market_cap == 362000000000
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_fundamentals_tool.py::test_fetch_fundamentals_includes_financials -v`
Expected: FAIL — `FundamentalResult` has no attribute `revenue_growth`

- [ ] **Step 3: Extend FundamentalResult and fetch_fundamentals**

Add new fields to `FundamentalResult` dataclass and pull from `yf.Ticker.info`:
- `revenue_growth`, `gross_margins`, `operating_margins`, `profit_margins`, `return_on_equity`
- `market_cap`, `enterprise_value`

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_fundamentals_tool.py -v`

- [ ] **Step 5: Create registered FundamentalsTool**

Create `backend/tools/fundamentals_tool.py` — a `BaseTool` subclass with `args_schema` that wraps `fetch_fundamentals()` and returns the extended data as a tool result.

- [ ] **Step 6: Write test for FundamentalsTool.execute()**

- [ ] **Step 7: Register in main.py**

- [ ] **Step 8: Commit**

```bash
git add backend/tools/fundamentals.py backend/tools/fundamentals_tool.py tests/unit/test_fundamentals_tool.py backend/main.py
git commit -m "feat(KAN-4D): extend fundamentals with financials + register as tool"
```

### Task 2: Analyst Price Targets Tool

**Files:**
- Create: `backend/tools/analyst_targets_tool.py`
- Test: `tests/unit/test_analyst_targets.py`

- [ ] **Step 1: Write failing test**

```python
"""Tests for analyst price targets tool."""
import pytest
from unittest.mock import patch, MagicMock

@pytest.mark.asyncio
async def test_analyst_targets_returns_data():
    """Should return current, high, low, mean, median targets."""
    with patch("backend.tools.analyst_targets_tool.yf.Ticker") as mock:
        mock.return_value.analyst_price_targets = {
            "current": 151.66, "high": 260.0, "low": 70.0,
            "mean": 186.60, "median": 199.0,
        }
        from backend.tools.analyst_targets_tool import AnalystTargetsTool
        tool = AnalystTargetsTool()
        result = await tool.execute({"ticker": "PLTR"})
        assert result.status == "ok"
        assert result.data["current_price"] == 151.66
        assert result.data["target_high"] == 260.0
        assert result.data["target_mean"] == 186.60
```

- [ ] **Step 2: Run to verify fail**
- [ ] **Step 3: Implement AnalystTargetsTool**

`BaseTool` subclass with `AnalystTargetsInput(ticker: str)` schema. Calls `yf.Ticker(ticker).analyst_price_targets` in executor thread. Returns `{current_price, target_high, target_low, target_mean, target_median, upside_pct}`.

- [ ] **Step 4: Write edge case test (no targets available)**
- [ ] **Step 5: Register in main.py**
- [ ] **Step 6: Run all tests, commit**

### Task 3: Earnings History Tool

**Files:**
- Create: `backend/tools/earnings_history_tool.py`
- Test: `tests/unit/test_earnings_history.py`

- [ ] **Step 1: Write failing test**

Test that tool returns EPS estimate, actual, surprise %, and a `beat_count` summary (e.g., "Beat 3 of last 4 quarters").

- [ ] **Step 2: Implement EarningsHistoryTool**

`BaseTool` wrapping `yf.Ticker(ticker).earnings_history`. Returns list of `{quarter, eps_estimate, eps_actual, surprise_pct}` + `{beat_count, total_quarters}` summary.

- [ ] **Step 3: Edge case test (no earnings data)**
- [ ] **Step 4: Register in main.py, run all tests, commit**

### Task 4: Company Profile Tool

**Files:**
- Create: `backend/tools/company_profile_tool.py`
- Test: `tests/unit/test_company_profile.py`

- [ ] **Step 1: Write failing test**

Test that tool returns business summary, sector, industry, employees, website, market cap.

- [ ] **Step 2: Implement CompanyProfileTool**

`BaseTool` wrapping `yf.Ticker(ticker).info`. Returns `{ticker, name, summary (truncated to 500 chars), sector, industry, employees, website, market_cap}`.

- [ ] **Step 3: Edge case test (delisted/invalid ticker)**
- [ ] **Step 4: Register in main.py, run all tests, commit**

**Chunk 1 checkpoint:** Run full unit test suite. Baseline + 4 new tools with tests. All existing tests still green. Commit + push.

---

## Chunk 2: DB Migration + Model Changes (Task 5)

### Task 5: Alembic Migration 009 — Agent V2 Fields

**Files:**
- Create: `backend/migrations/versions/XXX_009_agent_v2.py`
- Modify: `backend/models/chat.py`
- Modify: `backend/models/logs.py`

- [ ] **Step 1: Add feedback column to ChatMessage model**

```python
# backend/models/chat.py — add to ChatMessage class
feedback: Mapped[str | None] = mapped_column(String(10), nullable=True)  # "up" | "down"
```

- [ ] **Step 2: Add tier + query_id to LLMCallLog model**

```python
# backend/models/logs.py — add to LLMCallLog class
tier: Mapped[str | None] = mapped_column(String(20), nullable=True)  # planner|synthesizer
query_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
```

- [ ] **Step 3: Add query_id to ToolExecutionLog model**

```python
# backend/models/logs.py — add to ToolExecutionLog class (cache_hit already exists)
query_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
```

- [ ] **Step 4: Generate Alembic migration**

Run: `uv run alembic revision --autogenerate -m "009 agent v2 fields"`
**Review the migration** — check for false TimescaleDB index drops.

- [ ] **Step 5: Apply migration**

Run: `uv run alembic upgrade head`

- [ ] **Step 6: Run existing tests to confirm no regressions, commit**

---

## Chunk 3: Agent V2 Core (Tasks 6-11)

The heart of the rewrite. All behind `AGENT_V2=true` feature flag.

### Task 6: Feature Flag + Config

**Files:**
- Modify: `backend/config.py`

- [ ] **Step 1: Add AGENT_V2 setting**

```python
# backend/config.py — add to Settings class
AGENT_V2: bool = False
```

- [ ] **Step 2: Commit**

### Task 7: User Context Builder

**Files:**
- Create: `backend/agents/user_context.py`
- Test: `tests/unit/test_user_context.py`

- [ ] **Step 1: Write failing test**

Test that `build_user_context()` returns portfolio positions, sector allocation, preferences, and watchlist for a given user ID.

- [ ] **Step 2: Implement build_user_context**

Async function that queries portfolio, positions, preferences, and watchlist. Returns a dict matching the schema in spec §6. Uses `get_or_create_portfolio`, `get_positions_with_pnl`, and watchlist query.

- [ ] **Step 3: Test edge case — new user with no portfolio**

Should return empty positions, default preferences, empty watchlist.

- [ ] **Step 4: Run tests, commit**

### Task 8: Tool Result Validator

**Files:**
- Create: `backend/agents/result_validator.py`
- Test: `tests/unit/test_result_validator.py`

- [ ] **Step 1: Write failing tests**

```python
def test_validates_null_result():
    """Null tool result should be marked unavailable."""

def test_flags_stale_price_data():
    """Price data >24h old during market hours flagged as stale."""

def test_passes_valid_result():
    """Valid tool result passes through with source annotation."""

def test_handles_tool_error():
    """Tool returning error status is marked unavailable."""
```

- [ ] **Step 2: Implement validate_tool_result()**

Function that takes a `ToolResult` + tool name + timestamp, returns an annotated dict:
```python
{
    "tool": "analyze_stock",
    "status": "ok" | "unavailable" | "stale",
    "data": {...},
    "timestamp": "2026-03-20T09:15:00Z",
    "source": "TimescaleDB (computed from yfinance prices)",
    "reason": None | "API timeout" | "Data is 3 days old"
}
```

- [ ] **Step 3: Run tests, commit**

### Task 9: Simple Query Formatter

**Files:**
- Create: `backend/agents/simple_formatter.py`
- Test: `tests/unit/test_simple_formatter.py`

- [ ] **Step 1: Write failing tests**

```python
def test_formats_price_result():
    """Price tool result formatted as human-readable string."""

def test_formats_unknown_tool():
    """Unknown tool result formatted as JSON summary."""
```

- [ ] **Step 2: Implement format_simple_result()**

Template-based formatter. Maps tool names to formatting templates:
- `analyze_stock` → "{ticker} has a composite score of {composite_score}/10. RSI: {rsi_signal}, MACD: {macd_signal}."
- `get_company_profile` → "{name} ({ticker}) — {sector}, {industry}. Market cap: ${market_cap}."
- Default → JSON summary of top-level keys.

- [ ] **Step 3: Run tests, commit**

### Task 10: Planner Node

**Files:**
- Create: `backend/agents/planner.py`
- Create: `backend/agents/prompts/planner.md`
- Test: `tests/unit/test_planner.py`

- [ ] **Step 1: Write planner prompt**

Write `backend/agents/prompts/planner.md` with:
- Scope enforcement (financial context only, data-grounded only)
- Available tools list (auto-populated at runtime)
- User context placeholder
- Planning rules (max 10 tools, check DB first, include portfolio for personalized queries)
- 13 few-shot examples from spec §7
- Output format specification (JSON plan schema)

- [ ] **Step 2: Write failing tests**

```python
@pytest.mark.asyncio
async def test_planner_generates_stock_analysis_plan():
    """'Analyze PLTR' should produce a multi-tool plan."""

@pytest.mark.asyncio
async def test_planner_declines_out_of_scope():
    """'What is the capital of Uganda?' should return out_of_scope."""

@pytest.mark.asyncio
async def test_planner_declines_speculative():
    """'Will AAPL hit $300?' should return out_of_scope."""

@pytest.mark.asyncio
async def test_planner_simple_query():
    """'What is AAPL price?' should produce single-tool plan with skip_synthesis."""

@pytest.mark.asyncio
async def test_planner_includes_portfolio_context():
    """When user has holdings, plan should include get_portfolio_exposure."""
```

- [ ] **Step 3: Implement plan_query() function**

Async function that:
1. Loads planner prompt template
2. Injects available tool descriptions from registry
3. Injects user context
4. Calls LLM (tier="planner")
5. Parses JSON plan from response
6. Returns structured plan dict

Mock the LLM call in tests — test prompt construction and output parsing, not the LLM itself.

- [ ] **Step 4: Run tests, commit**

### Task 11: Mechanical Executor

**Files:**
- Create: `backend/agents/executor.py`
- Test: `tests/unit/test_executor.py`

- [ ] **Step 1: Write failing tests**

```python
@pytest.mark.asyncio
async def test_executor_runs_plan_in_order():
    """Executor calls tools in plan order via registry."""

@pytest.mark.asyncio
async def test_executor_resolves_prev_result():
    """$PREV_RESULT.ticker resolves from previous tool output."""

@pytest.mark.asyncio
async def test_executor_retries_on_failure():
    """Failed tool is retried once before marking unavailable."""

@pytest.mark.asyncio
async def test_executor_circuit_breaker():
    """3 consecutive failures triggers circuit breaker."""

@pytest.mark.asyncio
async def test_executor_respects_tool_limit():
    """Executor stops after 10 tool calls."""

@pytest.mark.asyncio
async def test_executor_flags_replan():
    """Empty search_stocks result flags for re-plan."""
```

- [ ] **Step 2: Implement execute_plan() function**

Async function that:
1. Iterates plan steps
2. Resolves `$PREV_RESULT` references from accumulated results
3. Calls `registry.execute(tool_name, params)` for each step
4. Validates each result via `validate_tool_result()`
5. Tracks consecutive failures for circuit breaker
6. Returns list of validated, annotated tool results + replan flag

- [ ] **Step 3: Run tests, commit**

**Chunk 3 checkpoint:** Run full unit test suite. All new components tested independently. Commit + push.

---

## Chunk 4: Synthesizer + Graph V2 (Tasks 12-14)

### Task 12: Synthesizer Node

**Files:**
- Create: `backend/agents/synthesizer.py`
- Create: `backend/agents/prompts/synthesizer.md`
- Test: `tests/unit/test_synthesizer.py`

- [ ] **Step 1: Write synthesizer prompt**

Write `backend/agents/prompts/synthesizer.md` with:
- Role: factual financial analyst
- Output format (confidence + scenarios + evidence)
- Rules: no claims without citations, acknowledge gaps, personalize to portfolio
- Conflicting signal handling
- 4 few-shot examples from spec §7

- [ ] **Step 2: Write failing tests**

```python
@pytest.mark.asyncio
async def test_synthesizer_produces_confidence_and_scenarios():
    """Given tool results, synthesizer returns confidence + bull/base/bear."""

@pytest.mark.asyncio
async def test_synthesizer_handles_partial_data():
    """When some tools are unavailable, synthesizer acknowledges gaps."""

@pytest.mark.asyncio
async def test_synthesizer_builds_evidence_tree():
    """Every claim links to a tool result with timestamp."""
```

- [ ] **Step 3: Implement synthesize_results() function**

Async function that:
1. Loads synthesizer prompt
2. Injects validated tool results with source annotations
3. Injects user context
4. Calls LLM (tier="synthesizer")
5. Parses response into structured sections (confidence, scenarios, evidence)
6. Returns synthesis dict

- [ ] **Step 4: Run tests, commit**

### Task 13: LLMClient Tier Support

**Files:**
- Modify: `backend/agents/llm_client.py`
- Test: existing `tests/unit/test_llm_client.py` (add new tests)

- [ ] **Step 1: Write failing test for tier_config**

```python
def test_llm_client_tier_routing():
    """LLMClient with tier_config routes to correct provider per tier."""

def test_llm_client_tier_fallback():
    """If primary provider fails for a tier, falls to next in tier chain."""

def test_llm_client_backward_compat():
    """Old constructor style (providers list) still works as 'default' tier."""
```

- [ ] **Step 2: Implement tier_config constructor**

Add optional `tier_config: dict[str, list[LLMProvider]] | None` parameter. If provided, `chat(messages, tier="planner")` selects the provider chain for that tier. If not provided, falls back to existing `providers` list behavior.

- [ ] **Step 3: Run all LLM client tests, commit**

### Task 14: Graph V2 — Three-Phase StateGraph

**Files:**
- Create: `backend/agents/graph_v2.py`
- Test: `tests/integration/test_agent_v2_flow.py`

- [ ] **Step 1: Define AgentStateV2**

```python
class AgentStateV2(TypedDict):
    messages: list
    phase: Literal["plan", "execute", "synthesize", "done"]
    plan: list[dict]
    tool_results: list[dict]
    iteration: int
    tool_calls_count: int
    failed_tools: list[str]
    replan_count: int
    start_time: float
    user_context: dict
    query_id: str
    skip_synthesis: bool
```

- [ ] **Step 2: Implement build_agent_graph_v2()**

LangGraph StateGraph with nodes:
- `plan` → calls `plan_query()`
- `execute` → calls `execute_plan()`
- `synthesize` → calls `synthesize_results()`
- `format_simple` → calls `format_simple_result()` (for skip_synthesis plans)

Conditional edges:
- `plan` → `execute` (normal) | `done` (out_of_scope/decline)
- `execute` → `synthesize` (normal) | `plan` (replan) | `format_simple` (skip_synthesis)
- `synthesize` → `done`
- `format_simple` → `done`

- [ ] **Step 3: Write integration test with mocked LLM + tools**

```python
@pytest.mark.asyncio
async def test_full_analysis_flow():
    """Full plan→execute→synthesize flow with mocked components."""

@pytest.mark.asyncio
async def test_out_of_scope_exits_at_plan():
    """Out-of-scope query exits after plan phase, no tools called."""

@pytest.mark.asyncio
async def test_simple_query_skips_synthesis():
    """Simple query goes plan→execute→format_simple, no synthesizer."""

@pytest.mark.asyncio
async def test_replan_on_empty_search():
    """Empty search result triggers replan, max once."""

@pytest.mark.asyncio
async def test_circuit_breaker_exits_to_synthesis():
    """3 consecutive tool failures → partial synthesis."""
```

- [ ] **Step 4: Run integration tests, commit**

**Chunk 4 checkpoint:** Run full test suite (unit + integration). The agent V2 graph works end-to-end with mocks. Commit + push.

---

## Chunk 5: Stream Events + Router Wiring (Tasks 15-17)

### Task 15: Extended Stream Events

**Files:**
- Modify: `backend/agents/stream.py`
- Test: add tests in existing `tests/unit/test_stream.py` or new file

- [ ] **Step 1: Add new StreamEvent types**

Add `plan`, `tool_error`, `evidence`, `decline` to the event type literal. Update `to_ndjson()` for new fields.

- [ ] **Step 2: Implement stream_graph_v2_events()**

New streaming function for graph_v2 that yields:
- `plan` event when planner returns
- `tool_start` / `tool_result` / `tool_error` during execution
- `evidence` event with the structured evidence tree
- `decline` event for out-of-scope
- `token` events during synthesis streaming
- `done` event

- [ ] **Step 3: Write tests for new event types, commit**

### Task 16: Chat Router — Feature Flag + Context Injection

**Files:**
- Modify: `backend/routers/chat.py`

- [ ] **Step 1: Add concurrent query guard**

Check if session already has an active stream. If so, return 429.

- [ ] **Step 2: Add user context injection**

Before building input state, call `build_user_context(user.id, db)` and include in state.

- [ ] **Step 3: Add feature flag graph selection**

```python
if settings.AGENT_V2:
    graph = request.app.state.agent_v2_graph
else:
    graph = request.app.state.stock_graph if agent_type == "stock" else request.app.state.general_graph
```

- [ ] **Step 4: Add query_id generation and tracking**

Generate `query_id = uuid4()` per request. Pass to graph state. Log in LLMCallLog and ToolExecutionLog.

- [ ] **Step 5: Add feedback endpoint**

```python
@router.patch("/sessions/{session_id}/messages/{message_id}/feedback")
async def set_feedback(session_id, message_id, feedback: Literal["up", "down"], ...):
```

- [ ] **Step 6: Write API tests for new behavior, commit**

### Task 17: Main.py — Graph V2 Startup

**Files:**
- Modify: `backend/main.py`

- [ ] **Step 1: Register new tools (4 yfinance tools)**

Add `FundamentalsTool`, `AnalystTargetsTool`, `EarningsHistoryTool`, `CompanyProfileTool` to the registry (unconditional — useful for both V1 and V2).

- [ ] **Step 2: Build graph_v2 when AGENT_V2=true**

In lifespan startup:
```python
if settings.AGENT_V2:
    from backend.agents.graph_v2 import build_agent_graph_v2
    app.state.agent_v2_graph = build_agent_graph_v2(registry, llm_client)
```

- [ ] **Step 3: Run full backend test suite, commit**

**Chunk 5 checkpoint:** Backend is complete. Agent V2 works end-to-end behind feature flag. All unit + integration + API tests green. Commit + push.

---

## Chunk 6: Frontend (Tasks 18-21)

### Task 18: New Stream Event Types

**Files:**
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/hooks/use-stream-chat.ts`

- [ ] **Step 1: Add new event types to TypeScript interfaces**

```typescript
// Add to StreamEvent type
type: "plan" | "thinking" | "tool_start" | "tool_result" | "tool_error" | "token" | "evidence" | "decline" | "error" | "done"

// New interfaces
interface PlanEvent { type: "plan"; plan: PlanStep[]; estimated_confidence: string; }
interface EvidenceEvent { type: "evidence"; tree: EvidenceNode[]; }
interface DeclineEvent { type: "decline"; reason: string; }
```

- [ ] **Step 2: Update useStreamChat to handle new events**

Add cases in the stream parser for `plan`, `evidence`, `decline`, `tool_error`.

- [ ] **Step 3: Commit**

### Task 19: Plan Display Component

**Files:**
- Create: `frontend/src/components/chat/plan-display.tsx`
- Test: `frontend/src/__tests__/components/plan-display.test.tsx`

- [ ] **Step 1: Implement PlanDisplay**

Shows "Here's what I'm researching..." with a list of planned tool calls and their reasons. Checkmarks appear as tools complete.

- [ ] **Step 2: Write test, commit**

### Task 20: Evidence Section Component

**Files:**
- Create: `frontend/src/components/chat/evidence-section.tsx`
- Test: `frontend/src/__tests__/components/evidence-section.test.tsx`

- [ ] **Step 1: Implement EvidenceSection**

Collapsible "Show Evidence" section. Renders the evidence tree: each claim → tool name + timestamp + data source. Uses indentation for hierarchy.

- [ ] **Step 2: Write test, commit**

### Task 21: Feedback Buttons + Decline Message

**Files:**
- Create: `frontend/src/components/chat/feedback-buttons.tsx`
- Create: `frontend/src/components/chat/decline-message.tsx`
- Modify: `frontend/src/components/chat/message-bubble.tsx`
- Test: `frontend/src/__tests__/components/feedback-buttons.test.tsx`

- [ ] **Step 1: Implement FeedbackButtons (thumbs up/down)**

API call to `PATCH /chat/sessions/{id}/messages/{id}/feedback`. Visual state: neutral → selected (filled icon).

- [ ] **Step 2: Implement DeclineMessage**

Styled message for out-of-scope/ungroundable queries. Friendly tone, suggests financial topics.

- [ ] **Step 3: Wire into MessageBubble**

Add `FeedbackButtons` to every assistant message. Render `DeclineMessage` for decline events. Render `EvidenceSection` when evidence data is present.

- [ ] **Step 4: Write tests, commit**

**Chunk 6 checkpoint:** Run frontend tests (`npx jest --watchAll=false`). All components render correctly. Commit + push.

---

## Chunk 7: Full Regression + Polish (Tasks 22-24)

### Task 22: Full Regression Test Suite

- [ ] **Step 1: Run unit tests**

```bash
uv run pytest tests/unit/ -v --tb=short
```
Expected: All existing 255 + new tests passing.

- [ ] **Step 2: Run API tests with testcontainers**

```bash
uv run pytest tests/api/ -v --tb=short
```
Expected: All 132 existing + new feedback endpoint tests passing.

- [ ] **Step 3: Run integration tests**

```bash
uv run pytest tests/integration/test_agent_v2_flow.py -v --tb=short
```
Expected: All 5+ integration tests passing.

- [ ] **Step 4: Run frontend tests**

```bash
cd frontend && npx jest --watchAll=false
```
Expected: All 57 existing + new component tests passing.

- [ ] **Step 5: Lint everything**

```bash
uv run ruff check backend/ tests/ --fix && uv run ruff format backend/ tests/
cd frontend && npm run lint
```

- [ ] **Step 6: TypeScript build check**

```bash
cd frontend && npx tsc --noEmit
```

### Task 23: Manual E2E Verification

- [ ] **Step 1: Set AGENT_V2=true in .env, restart backend**
- [ ] **Step 2: Test "Analyze Palantir" end-to-end**

Verify: plan streams → tools execute → synthesis with confidence + scenarios + evidence

- [ ] **Step 3: Test "What is the capital of Uganda?"**

Verify: polite decline, no tools fired

- [ ] **Step 4: Test "Will AAPL hit $300?"**

Verify: polite decline (speculative, not groundable)

- [ ] **Step 5: Test "Should I rebalance?" (with portfolio)**

Verify: portfolio context injected, personalized analysis

- [ ] **Step 6: Test tool failure (disable an API key temporarily)**

Verify: graceful degradation, partial analysis with gap acknowledgment

- [ ] **Step 7: Test thumbs up/down**

Verify: feedback saved to DB, icon state updates

### Task 24: Final Commit + PR

- [ ] **Step 1: Update project-plan.md — mark Phase 4D deliverables**
- [ ] **Step 2: Update PROGRESS.md — session entry**
- [ ] **Step 3: Update Serena project/state memory**
- [ ] **Step 4: Commit all docs**
- [ ] **Step 5: Push branch, open PR to develop**

---

## Estimated Effort

| Chunk | Tasks | Est. Time | Sessions |
|---|---|---|---|
| 1: yfinance tools | 1-4 | ~2 hours | 1 |
| 2: DB migration | 5 | ~20 min | same |
| 3: Agent V2 core | 6-11 | ~4 hours | 1-2 |
| 4: Synthesizer + graph | 12-14 | ~3 hours | 1 |
| 5: Stream + router | 15-17 | ~2 hours | 1 |
| 6: Frontend | 18-21 | ~2 hours | 1 |
| 7: Regression + polish | 22-24 | ~1 hour | same |
| **Total** | **24 tasks** | **~14 hours** | **~4-5 sessions** |
