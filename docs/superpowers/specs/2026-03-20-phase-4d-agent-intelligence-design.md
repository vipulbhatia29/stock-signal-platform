# Phase 4D — Agent Intelligence Architecture

## Overview

Redesign the chat agent from a reactive tool-caller to a **factual-first financial analyst** that plans its research, executes with cost-efficient model tiering, and synthesizes personalized analysis with full data lineage.

**Target user:** Passive investors who want "tell me what to do and show me why" — not quant traders or API consumers.

**Intelligence level:** Context-Aware Advisor (Level 2) — remembers portfolio and preferences across sessions. No proactive push notifications (that's the dashboard's job).

---

## §1 Three-Phase Agent Loop

Every chat query flows through three phases. This replaces the current single ReAct loop.

### Phase 1: Plan (Sonnet)

The planner receives the user's query plus their portfolio context (injected at session start) and generates a structured plan before any tools fire.

**Responsibilities:**
- Classify query intent (stock analysis, portfolio review, market overview, general Q&A)
- Check if query requires high-token operations (multi-year historical comparisons) → **graceful decline** before any tools fire: "This feature is coming soon — we've noted your interest"
- Generate an ordered list of tool calls with rationale for each
- Estimate confidence range based on which data sources are available
- Stream a `plan` event to the frontend so the user sees "Here's what I'm researching..."

**Planner output schema:**
```python
{
    "intent": "stock_analysis",
    "ticker": "PLTR",
    "plan": [
        {"tool": "search_stocks", "reason": "Resolve company name to ticker"},
        {"tool": "ingest_stock", "reason": "Not in DB — fetch prices + signals"},
        {"tool": "analyze_stock", "reason": "Technical signals + composite score"},
        {"tool": "get_fundamentals_extended", "reason": "Financials, growth, margins"},
        {"tool": "get_portfolio_exposure", "reason": "Check user's tech concentration"},
        {"tool": "get_analyst_targets", "reason": "Consensus price target"},
        {"tool": "get_earnings_history", "reason": "Earnings surprise track record"},
        {"tool": "get_news_sentiment", "reason": "Recent news sentiment"}
    ],
    "estimated_confidence": "65-80%",
    "decline_reason": null
}
```

**Simple query optimization:** If the query is trivial ("What's AAPL's price?"), the planner generates a single-tool plan and marks `skip_synthesis: true`. The executor calls the tool, and a lightweight Python formatter (not an LLM) converts the result into a human-readable string: e.g., `{"adj_close": 152.30}` → "AAPL is currently trading at $152.30." This is a template-based formatter, not an LLM call. Total LLM calls for simple queries: 1 (planner only).

### Phase 2: Execute (Mechanical — No LLM)

The executor is **not an LLM call**. It mechanically follows the plan, calling each tool in order via the ToolRegistry. No Groq/LLM is used here — this saves 6-10 LLM calls per query.

**How it works:**
1. Planner generates tool calls with **explicit parameters** (not just tool names):
   ```python
   {"tool": "search_stocks", "params": {"query": "Palantir"}}
   {"tool": "ingest_stock", "params": {"ticker": "$PREV_RESULT.ticker"}}
   ```
2. The executor resolves `$PREV_RESULT` references by substituting values from previous tool outputs. This handles dynamic parameter passing (e.g., search returns "PLTR", ingest uses that ticker).
3. Each tool is called via `registry.execute(name, params)` — the same function that already exists.
4. Results are validated, annotated with source metadata, and accumulated.

**No LLM reasoning per step.** The planner's job is to generate complete, executable tool calls. If the plan is wrong (tool returns unexpected data), the executor flags it for re-plan (back to Phase 1, max once). The planner is the only component that "thinks."

**Responsibilities:**
- Call each tool in plan order, resolving `$PREV_RESULT` references
- Validate every tool result before passing downstream (not null, not stale, schema correct)
- Stream `tool_start` and `tool_result` events for each step
- If a tool fails → retry once, then annotate as `{status: "unavailable", reason: "..."}` and continue
- If a critical tool fails → flag for re-plan (max 1 re-plan)
- Track tool call count against budget limit (max 10)

**Re-plan trigger rules (hard-coded, not LLM-decided):**
- `search_stocks` returns empty → re-plan with "ticker not found, suggest alternatives"
- `ingest_stock` fails with "ticker not found" → re-plan without ingest step
- Tool returns data for a different ticker than expected → re-plan
- All other failures → mark unavailable, continue (don't re-plan)

**Re-plan context:** The planner receives the original query + the executor's partial results + the failure reason. Token budget carries over (does not reset). This means a re-planned query has less budget for the second attempt, naturally limiting complexity.

**Concurrent query protection:** The chat router rejects a second query on the same session while one is streaming. Return HTTP 429 with "Analysis in progress — please wait for the current response to complete." Scoped by `session_id`, not `user_id` — the user can have multiple sessions open.

**Tool result validation rules:**
- Null/empty response → mark unavailable, don't pass to synthesizer
- Price data older than 24 hours during market hours → flag as stale with timestamp
- Financial statements older than 1 quarter → flag as stale
- Any tool returning an error string → log, mark unavailable, continue

### Phase 3: Synthesize (Sonnet)

The synthesizer receives all validated tool results with their source annotations and produces the final analysis.

**Responsibilities:**
- Compute confidence score from signal consensus (number of bullish vs bearish signals / total signals)
- Generate bull/base/bear scenarios with probability allocations
- Personalize to user's portfolio (concentration risk, existing exposure, position sizing)
- Time horizon recommendations (3-month, 6-month, long-term)
- Build evidence tree (every quantitative claim → tool name + timestamp + data source)
- **Hard rule:** No quantitative claims without tool backing. If a tool was unavailable, acknowledge the gap explicitly: "I couldn't access analyst price targets, so this analysis is based on technical and fundamental data only."
- Detect conflicting signals and frame them as insight (see §4)
- Gracefully decline any part of the query that would require data we don't have

**Synthesizer MUST NOT:**
- Generate price predictions from parametric memory
- Cite sources not in the tool results
- Present opinion as data
- Claim certainty when data is incomplete

---

## §2 Model Tiering

| Role | Model | When | Cost Impact |
|---|---|---|---|
| **Planner** | Claude Sonnet | Query classification + plan generation | ~$0.01/query |
| **Executor** | No LLM — mechanical | Tool calling via ToolRegistry | $0 (pure function calls) |
| **Synthesizer** | Claude Sonnet | Final analysis generation | ~$0.02-0.04/query |
| **Fallback planner/synthesizer** | OpenAI GPT-4o-mini | If Anthropic is down | ~$0.005/query |

**Implementation:** Extend existing `LLMClient` constructor to accept a tier-based config:

```python
# Current: LLMClient(providers=[groq, anthropic, openai])  # ordered fallback
# New: LLMClient(tier_config={...})

tier_config = {
    "planner": [anthropic_sonnet, openai_gpt4o_mini],      # Sonnet preferred, GPT-4o-mini fallback
    "synthesizer": [anthropic_sonnet, openai_gpt4o_mini],   # Same as planner
}

llm_client = LLMClient(tier_config=tier_config)
llm_client.invoke(messages, tier="planner")     # → tries Sonnet, falls back to GPT-4o-mini
llm_client.invoke(messages, tier="synthesizer")  # → same chain
# Executor does NOT use an LLM — it calls tools directly via registry.execute()
```

The `tier` key selects the provider fallback chain. Each tier has its own ordered list — if the first provider fails or is rate-limited, it falls to the next. The existing `ProviderHealth` tracking applies per-provider across all tiers (if Anthropic is down for the planner, it's also skipped for the synthesizer).

**Backward compatibility:** The old `LLMClient(providers=[...])` constructor can remain as a shortcut that creates a single "default" tier. This avoids breaking existing tests.

**Sonnet is called exactly twice per query** (plan + synthesize). The executor is mechanical — no LLM needed. This means ~80% cost reduction vs the current approach of sending everything through Sonnet.

**Prompt caching:** System prompt + tool schemas are identical across all queries. Enable Anthropic's prompt caching to reduce input token costs by ~90% for the cached portion. This requires the `anthropic-beta: prompt-caching-2024-07-31` header. LangChain's `ChatAnthropic` supports this via `cache_control` in message metadata — validate during implementation. If LangChain doesn't support it natively, use the Anthropic SDK directly for planner/synthesizer calls.

**Note on Groq:** Originally considered for executor tier, but since the executor is mechanical (no LLM), Groq is not needed in Phase 4D. Groq remains available in the LLMClient fallback chain for future use (e.g., if we add an LLM-powered executor for complex parameter resolution in Phase 5).

---

## §3 Loop Exit Strategy

Every loop has explicit exit conditions. No infinite loops possible.

### Hard Limits (non-negotiable)

| Limit | Value | Action on breach |
|---|---|---|
| Max tool calls per query | 10 | Stop execution, move to Phase 3 |
| Max re-plans | 1 | Second failure → partial synthesis |
| Max LLM calls total | 3 | Plan (1) + synthesize (1) + re-plan if needed (1). Executor uses no LLM. |
| Wall clock timeout | 45 seconds | Force exit to synthesis with available data |
| Max input tokens per phase | 16K planner, 4K executor, 32K synthesizer | Truncate/summarize if exceeded |
| Consecutive tool failures | 3 | Circuit breaker → partial synthesis |

### Exit conditions per phase

**Phase 1 (Plan):**
- Happy exit → plan generated, move to Phase 2
- Decline exit → query out of scope, respond with graceful decline, no tools fired
- Simple exit → trivial query, single tool call, skip Phase 3

**Phase 2 (Execute):**
- Happy exit → all plan steps completed, move to Phase 3
- Partial exit → some tools failed after retry, move to Phase 3 with annotations
- Abort exit → 3+ consecutive failures, circuit breaker, synthesize with what we have
- Re-plan exit → tool result changes picture, back to Phase 1 (max once)
- Budget exit → token/tool count limit hit, stop and synthesize

**Phase 3 (Synthesize):**
- Happy exit → full analysis with evidence
- Insufficient data exit → honest response: "Not enough data for full analysis. Here's what I found."
- Timeout exit → 45-second wall clock, synthesize whatever is available

### LangGraph State

```python
class AgentState(TypedDict):
    messages: list
    phase: Literal["plan", "execute", "synthesize", "done"]
    plan: list[dict]          # Generated tool plan
    tool_results: list[dict]  # Validated results with source tags
    iteration: int
    tool_calls_count: int
    failed_tools: list[str]
    replan_count: int
    start_time: float
    token_budget_remaining: int
    user_context: dict        # Portfolio + preferences (injected at start)
```

---

## §4 Output Format

### Confidence + Scenarios + Evidence

Every substantive analysis follows this structure:

```
Confidence: 72% Bullish
⚠️ Risk Flag: Bear case severity is HIGH despite bullish consensus

Bull Case (40% probability): [scenario with conditions]
Base Case (40% probability): [scenario with conditions]
Bear Case (20% probability): [scenario with conditions]

Recommendation: BUY — but limit position to 3% (not 5%) due to tail risk
Time Horizon: Strong for 6-month+, cautious short-term (RSI overbought)

▶ Show Evidence  [collapsible]
  → Composite Score: 7.2/10 (from analyze_stock, 2026-03-20 09:15 UTC)
    → RSI: 58.3 — Neutral
    → MACD: Bullish crossover on Mar 18
    → SMA: Price above 200-day ($72.40 vs $65.10)
    → Piotroski: 7/9 — Strong fundamentals
  → Revenue Growth: 21% YoY (from get_fundamentals_extended, yfinance)
  → Analyst Consensus: Buy, target $95 (from get_analyst_targets, yfinance)
  → Portfolio: 0 shares held, Tech at 28% (from get_portfolio_exposure)
  → News Sentiment: 0.72 positive, 7 articles (from get_news_sentiment, Alpha Vantage)
```

### Confidence scoring rules

- Confidence = (bullish signals / total signals) × 100, adjusted for signal quality
- Below 50% → "Insufficient conviction — WATCH"
- 50-65% → "Mixed signals — position conservatively if at all"
- 65-80% → actionable, show full analysis
- 80%+ → high conviction, still show risks

### Conflicting signals

When confidence and scenario severity diverge (high confidence but severe bear case), display both and frame the conflict as insight:
- "72% bullish, BUT bear case is a 40% drawdown"
- Adjust position sizing recommendation accordingly

### Graceful declines

For queries requiring unsupported operations:
- "Comparing Apple's risk factors across 5 years of 10-K filings isn't available yet. I can analyze the latest 10-K risk factors and current signals — would that help?"
- "I can't predict exact prices, but I can show you analyst consensus targets and the technical trend."

---

## §5 Enriched Data Layer (yfinance Extension)

Extend existing `fetch_fundamentals()` and add new tool functions to pull richer data from yfinance. **No paid APIs. No new dependencies.**

### New data to pull (all from yfinance, free)

| Data | yfinance source | New tool or extend existing? |
|---|---|---|
| Full income statement (revenue, net income, EBITDA, margins) | `Ticker.quarterly_income_stmt` | Extend `fetch_fundamentals()` |
| Balance sheet (debt, equity, cash, assets) | `Ticker.quarterly_balance_sheet` | Extend `fetch_fundamentals()` |
| Cash flow (FCF, capex, operating cash flow) | `Ticker.quarterly_cashflow` | Extend `fetch_fundamentals()` |
| Revenue/earnings growth rates, margins | `Ticker.info` (revenueGrowth, grossMargins, etc.) | Extend `fetch_fundamentals()` |
| Analyst price targets (current, high, low, mean, median) | `Ticker.analyst_price_targets` | New: `get_analyst_targets` tool |
| Earnings history + surprise % | `Ticker.earnings_history` | New: `get_earnings_history` tool |
| Company profile (summary, employees, market cap) | `Ticker.info` | New: `get_company_profile` tool |
| Analyst recommendations (buy/hold/sell counts) | `Ticker.recommendations` | Extend Finnhub adapter or replace |

### Tool name mapping (spec → implementation)

| Name in spec examples | Status | Implementation |
|---|---|---|
| `search_stocks` | Exists | `backend/tools/search_stocks_tool.py` |
| `ingest_stock` | Exists | `backend/tools/ingest_stock_tool.py` |
| `analyze_stock` | Exists | `backend/tools/analyze_stock.py` |
| `get_fundamentals_extended` | **New** | Extend `backend/tools/fundamentals.py` → register as tool with `args_schema` |
| `get_analyst_targets` | **New** | `backend/tools/analyst_targets.py` — wraps `yf.Ticker.analyst_price_targets` |
| `get_earnings_history` | **New** | `backend/tools/earnings_history.py` — wraps `yf.Ticker.earnings_history` |
| `get_company_profile` | **New** | `backend/tools/company_profile.py` — wraps `yf.Ticker.info` |
| `get_portfolio_exposure` | Exists | `backend/tools/portfolio_exposure.py` |
| `get_news_sentiment` | Exists | `backend/tools/adapters/alpha_vantage.py` (MCP adapter) |
| `get_10k_section` | Exists | `backend/tools/adapters/edgar.py` (MCP adapter) |
| `get_analyst_ratings` | Exists | `backend/tools/adapters/finnhub.py` (MCP adapter) |
| `get_economic_series` | Exists | `backend/tools/adapters/fred.py` (MCP adapter) |
| `screen_stocks` | Exists | `backend/tools/screen_stocks.py` |
| `get_recommendations` | Exists | `backend/tools/recommendations_tool.py` |
| `web_search` | Exists | `backend/tools/web_search.py` |
| `get_geopolitical_events` | Exists | `backend/tools/geopolitical.py` |

### What we keep as-is

- `compute_signals()` — our composite scoring is a differentiator
- `generate_recommendation()` — portfolio-aware logic is unique
- `get_portfolio_exposure()` — no API provides this
- Portfolio tools (positions, P&L, FIFO, rebalancing, dividends, divestment rules)
- Edgar adapter (10-K sections, 13-F, insider trades, 8-K)
- FRED adapter (macro data)
- GDELT geopolitical events
- SerpAPI web search

### DCF valuation

Deferred. yfinance provides free cash flow data, so we could compute a simple DCF, but it's a Phase 5 enhancement. The agent should acknowledge "DCF valuation is not available yet" if asked.

### Peers / competitors

Not directly available from yfinance. For now, the agent can use `screen_stocks` with the same sector + industry to find comparable companies. A dedicated peers tool is a Phase 5 enhancement.

---

## §6 Cross-Session Memory (Level 1)

At the start of every chat session, inject the user's portfolio context into the system prompt:

```python
# Injected into system prompt at session start
user_context = {
    "positions": [
        {"ticker": "AAPL", "shares": 100, "avg_cost": 145.0, "sector": "Technology"},
        {"ticker": "PLTR", "shares": 50, "avg_cost": 85.0, "sector": "Technology"},
    ],
    "total_value": 52300.0,
    "sector_allocation": {"Technology": 42%, "Healthcare": 18%, ...},
    "preferences": {
        "max_position_pct": 5.0,
        "max_sector_pct": 30.0,
        "stop_loss_pct": 20.0,
    },
    "watchlist": ["AAPL", "PLTR", "MSFT", "GOOGL"],
}
```

**Implementation:** In `backend/routers/chat.py`, before building the input state, query the DB for the user's context:

```python
# New utility function in backend/tools/portfolio.py (or a new user_context.py)
async def build_user_context(user_id: UUID, db: AsyncSession) -> dict:
    """Build the user context dict for agent session start."""
    portfolio = await get_or_create_portfolio(user_id, db)
    positions = await get_positions_with_pnl(portfolio.id, db)
    # ... build the dict shown above
    return user_context
```

The context is injected as a **system message** prepended to the planner's input messages:
```python
system_msg = f"USER PORTFOLIO CONTEXT:\n{json.dumps(user_context, indent=2)}"
```

This way the planner sees the portfolio before generating its plan, and the synthesizer sees it when personalizing the output. The executor doesn't need it (it just calls tools).

**No Level 2+ memory:** We don't store past analysis summaries or user facts across sessions. If the user asks "What did you say about PLTR last time?" the agent responds honestly: "I don't have access to our previous conversations. Would you like me to run a fresh analysis?"

---

## §7 Few-Shot Prompt Design

Three separate prompts: planner, executor, synthesizer. Each loaded from markdown files in `backend/agents/prompts/`.

### Planner prompt (`planner.md`)

Key sections:
- Role: "You are a research planner for a financial analysis platform"
- Available tools list (auto-populated from registry)
- User context (auto-populated from DB)
- Planning rules:
  - Always check if stock is in DB before calling analyze_stock
  - Always include portfolio context tools for personalized queries
  - Cap plan at 10 tool calls
  - If query requires multi-year historical comparisons or price predictions, decline gracefully
  - Estimate confidence range based on data availability
- Few-shot examples:
  1. "Analyze Palantir" → search → ingest → signals → fundamentals → portfolio → news → earnings
  2. "Should I rebalance?" → portfolio exposure → for top 3 holdings: signals + recommendations
  3. "What's AAPL's price?" → single tool call (get_latest_price), no synthesis needed
  4. "Compare Apple's 10-K risk factors across 2020-2025" → graceful decline
  5. "How's the market looking?" → FRED macro data → sector performance → geopolitical events

### Executor prompt (`executor.md`)

Minimal — the executor just needs to call tools correctly:
- "Call the specified tool with the given parameters"
- "Validate the result is not null or error"
- "Return the raw result with source annotation"

### Synthesizer prompt (`synthesizer.md`)

The most critical prompt. Key sections:
- Role: "You are a financial analyst synthesizing research into actionable advice"
- Output format specification (confidence + scenarios + evidence tree)
- Rules:
  - Every quantitative claim MUST cite a tool result with timestamp
  - If data is missing, acknowledge the gap explicitly
  - Confidence = bullish signals / total signals, adjusted for quality
  - When signals conflict, present both sides and adjust position sizing
  - Personalize to user's portfolio (reference their holdings by name)
  - Time horizons: always address 3-month, 6-month, and long-term
  - Never predict specific prices
  - Never present opinion as fact
  - Acknowledge "investment is subject to market risk" naturally (not as a disclaimer banner)
- Few-shot examples:
  1. Full analysis with high confidence (all data available)
  2. Partial analysis (some tools failed — honest about gaps)
  3. Conflicting signals (high confidence but severe bear case)
  4. Portfolio-personalized (user already holds the stock)

---

## §8 Hallucination Guardrails

### Prevention (built into architecture)

1. **Tool-grounded responses:** The synthesizer's few-shot prompt enforces "no claim without citation." The evidence tree is a structural requirement, not optional.
2. **Tool result validation layer:** Between executor and synthesizer, validate every result:
   - Null → marked unavailable
   - Stale (>24h prices, >1Q financials) → flagged with timestamp
   - Error → logged, marked unavailable
   - The synthesizer receives a clean manifest: `{tool: "analyze_stock", status: "ok", data: {...}, timestamp: "..."}` or `{tool: "get_analyst_targets", status: "unavailable", reason: "API timeout"}`
3. **No parametric financial data:** The planner prompt explicitly forbids the LLM from using its training data for any financial numbers. "If you don't have a tool result for a claim, you don't make the claim."

### Detection (safety net)

4. **Post-synthesis validation (Phase 4D stretch goal):** A lightweight check that scans the synthesizer's output for quantitative claims and verifies each one appears in the tool results. If a claim can't be traced → strip it and add "[data not verified]". This can be a simple regex + JSON match, not a separate LLM call.

### Data lineage

Every tool result includes:
```python
{
    "tool": "analyze_stock",
    "source": "TimescaleDB (computed from yfinance prices)",
    "timestamp": "2026-03-20T09:15:00Z",
    "freshness": "current",  # or "stale (24h old)"
    "data": { ... }
}
```

The frontend renders this in the collapsible evidence section.

---

## §9 Cost Tracking

### Schema (extend existing LLMCallLog)

The `LLMCallLog` hypertable already exists (migration 008). Add fields:

```python
# New fields on LLMCallLog
tier: str          # "planner" | "synthesizer" (executor has no LLM calls)
query_id: UUID     # Groups all calls for a single user query (B-tree index)

# New fields on ToolExecutionLog
query_id: UUID     # Same grouping (B-tree index)
# NOTE: cache_hit already exists on ToolExecutionLog — no change needed
```

**Migration:** Alembic migration 009 (current head: `664e54e974c5`). Add B-tree indexes on `query_id` for both tables — this is the primary correlation key for debugging.

### Per-query cost estimation

After each query completes, compute and log:
- Total input tokens (across all phases)
- Total output tokens
- Estimated cost in USD (based on model pricing)
- Tool calls count
- Wall clock time

### Token budget enforcement

Before each LLM call, check remaining budget:
```python
if token_budget_remaining < estimated_tokens:
    # Truncate context or skip to synthesis
```

The planner's system prompt + tool schemas are cached (Anthropic prompt caching). This portion doesn't count against the per-query budget.

### Subscription preparation (future)

Log everything now. When monetization comes, the data is there to set tier limits:
- Free: 20 queries/day, executor model only (no deep analysis)
- Pro: 100 queries/day, full three-phase analysis
- Premium: unlimited, priority models

---

## §10 Response Strategy (B+C Hybrid)

**For watchlist/portfolio stocks (strategy C — pre-computed):**
- Celery Beat nightly task pre-computes signals, fundamentals, and a cached analysis summary for every stock in the user's watchlist
- Stored in `SignalSnapshot` + `RecommendationSnapshot` (already exist)
- When the user asks about a watchlist stock, the planner checks DB freshness first. If data is <24h old, skip the fetch tools and go straight to synthesis using cached data
- Response time: ~3-5 seconds (1 planner LLM call + synthesis from cached data)
- Displayed with "Last updated: 6 hours ago" timestamp

**For unknown stocks (strategy B — quick then deep):**
- Planner generates the full tool plan (search → ingest → signals → fundamentals → etc.)
- Executor runs all steps, streaming progress to the user
- Response time: ~15-30 seconds for a comprehensive analysis
- User sees tool cards appearing as each step completes

**Freshness rules:**
- Prices: current if from last market close (accounts for weekends — Friday close is "current" until Monday open)
- Signals: current if computed today
- Fundamentals: current if from the latest quarterly filing
- News: always fetched live (not cached)

## §10 Error UX

### NDJSON Stream Events (extending existing)

```python
class StreamEvent:
    type: Literal[
        "plan",          # NEW: agent's research plan
        "thinking",      # Existing: processing indicator
        "tool_start",    # Existing: tool execution started
        "tool_result",   # Existing: tool returned data
        "tool_error",    # NEW: tool failed (with fallback info)
        "token",         # Existing: streaming text
        "evidence",      # NEW: structured evidence tree
        "error",         # Existing: fatal error
        "decline",       # NEW: query gracefully declined
        "done",          # Existing: stream complete
    ]
```

### What the user sees for each failure mode

| Failure | User sees | Behind the scenes |
|---|---|---|
| Single tool fails | "I couldn't access [tool]. Analysis based on remaining data." | Retry once, mark unavailable, continue |
| 3+ tools fail | "I'm having trouble accessing several data sources. Here's a partial analysis with what I could gather." | Circuit breaker, partial synthesis |
| LLM provider down | Brief delay, then response from fallback model | Provider failover (existing) |
| Query too expensive | "Analyzing 5 years of 10-K filings isn't available yet. I can analyze the latest filing — would that help?" | Planner declines at Phase 1 |
| Timeout (45s) | "This is taking longer than expected. Here's what I've gathered so far:" + partial results | Force synthesis |
| Stock doesn't exist | "I couldn't find [ticker] on any US exchange. Did you mean [suggestions]?" | search_stocks returns empty |

### Developer debugging

All errors logged to `ToolExecutionLog` and `LLMCallLog` with:
- Full exception traceback (server-side only, never to client)
- Query ID for correlation across phases
- Model used, tokens consumed, latency
- Tool params that caused the failure

Frontend never sees stack traces, file paths, or internal hostnames. Error messages are human-readable and actionable.

---

## §11 Feedback Loop

### Phase 4D (implement now)

**Thumbs up/down:**
- Add `feedback: Literal["up", "down"] | None` column to `ChatMessage` model
- Frontend: thumbs up/down buttons on every assistant message
- Logged with full trace context (query_id links to LLMCallLog + ToolExecutionLog)

**Trace logging:**
- Every query gets a `query_id` (UUID)
- All LLM calls, tool executions, and the final response are tagged with this ID
- This is the debugging trail: "user rated thumbs-down → look up query_id → see every LLM call, every tool result, every decision"

### Phase 5+ (implement later)

**LLM-as-judge:** A cheap model evaluates a sample of responses against tool results. "Did the analysis accurately reflect the data?" Flags mismatches.

**Eval dataset:** Collect 50-100 representative queries from production. Run before deploying prompt changes.

**Weekly review:** You look at thumbs-down responses, identify patterns, we update prompts.

---

## §12 Migration Plan

### What changes (existing code)

| File | Change | Risk |
|---|---|---|
| `backend/agents/graph.py` | Replace single ReAct loop with 3-phase graph (plan → execute → synthesize) | **HIGH** — core agent logic |
| `backend/agents/base.py` | Remove StockAgent/GeneralAgent distinction. Single agent with planner-driven tool selection | **MEDIUM** — simplification |
| `backend/agents/stream.py` | Add `plan`, `tool_error`, `evidence`, `decline` event types | **LOW** — additive |
| `backend/agents/llm_client.py` | Add `tier` parameter to `invoke()`, configure Groq for executor tier | **MEDIUM** — extends existing |
| `backend/agents/prompts/` | Replace 2 prompts with 3 (planner, executor, synthesizer) | **LOW** — file replacement |
| `backend/routers/chat.py` | Inject user context at session start, add query_id tracking | **LOW** — additive |
| `backend/tools/fundamentals.py` | Extend to return full financials, growth rates, margins | **LOW** — additive |
| `backend/models/chat.py` | Add `feedback` column to ChatMessage | **LOW** — migration |
| `backend/models/logs.py` | Add `tier`, `query_id` to LLMCallLog; `query_id`, `cache_hit` to ToolExecutionLog | **LOW** — migration |
| `frontend/src/components/chat/` | Add plan display, evidence section, feedback buttons, decline messages | **MEDIUM** — new UI components |

### New code

| File | Purpose |
|---|---|
| `backend/tools/analyst_targets.py` | New tool: yfinance analyst price targets |
| `backend/tools/earnings_history.py` | New tool: yfinance earnings history + surprises |
| `backend/tools/company_profile.py` | New tool: yfinance company profile |
| `backend/agents/prompts/planner.md` | Planner few-shot prompt |
| `backend/agents/prompts/executor.md` | Executor prompt |
| `backend/agents/prompts/synthesizer.md` | Synthesizer few-shot prompt |

### Regression testing strategy

1. **Before starting:** Baseline all existing tests (255 unit + 132 API + 57 frontend = 444)
2. **Unit tests for each new component:**
   - Planner: given query + context → produces valid plan
   - Executor: given plan → calls tools in order, handles failures
   - Synthesizer: given tool results → produces formatted analysis with evidence
   - Each new tool: standard happy + error path
   - Exit conditions: test every limit (max tools, timeout, consecutive failures)
3. **Integration tests:**
   - Full three-phase flow with mocked tools
   - Partial failure scenarios (tool unavailable, stale data)
   - Circuit breaker activation
   - Model fallback chain
4. **API tests:**
   - Chat stream endpoint returns new event types (plan, evidence, decline)
   - Feedback endpoint works
   - User context injection works
5. **Frontend tests:**
   - Plan display component
   - Evidence collapsible section
   - Feedback buttons
   - Decline message rendering
6. **Manual E2E:**
   - "Analyze Palantir" end-to-end (search → ingest → analyze → synthesize)
   - "Should I rebalance?" with portfolio context
   - Tool failure scenario (disable an API key)
   - Graceful decline ("Compare 5 years of 10-Ks")

### Rollback plan

The existing agent code stays in git history. If the new three-phase approach has critical issues:

**Option A — Feature flag (preferred):** Implement behind `AGENT_V2=true` env var. Old and new graphs coexist. The chat router checks the flag and selects the graph. This allows A/B testing and instant rollback without git reverts.

**Option B — Git revert (if feature flag isn't feasible):** Revert ALL of these files together (not just `graph.py`):
1. `backend/agents/graph.py`
2. `backend/agents/base.py`
3. `backend/agents/stream.py`
4. `backend/routers/chat.py`
5. `backend/agents/prompts/*.md`
6. `backend/main.py` (lifespan wiring)

The new tools (analyst_targets, earnings_history, company_profile) and the feedback column are backward-compatible and don't need rollback.

---

## §13 Decisions Log

| Decision | Choice | Rationale |
|---|---|---|
| Agent pattern | Plan-then-Execute (GPA + ReAct) | Explicit planning enables evidence trail, model tiering, and user visibility into agent reasoning |
| Model tiering | Sonnet (plan+synthesize), Groq Llama (execute), GPT-4o-mini (fallback) | Sonnet called 2x, not 10x. ~60% cost reduction |
| Data sources | yfinance only, no paid APIs | Free, covers 90% of gaps. Our value is the intelligence layer, not data fetching |
| RAG | No. Deferred to Phase 5+ | Our data is structured (DB queries) or small unstructured (5K char 10-K sections). RAG is for large corpora we don't have yet |
| Memory | Level 1: portfolio + preferences injected at session start | Simple DB query, no new infrastructure. Level 2 (analysis summaries) deferred |
| Confidence display | Show ≥65% with scenarios + evidence | Below 65% is "WATCH". Confidence = signal consensus ratio. Conflicts between confidence and bear case severity shown explicitly |
| Output format | Confidence + bull/base/bear scenarios + collapsible evidence | Clean analysis on top, "Show Evidence" expands full lineage tree |
| Response strategy | B+C hybrid: cached for watchlist (Celery nightly), quick+deep for unknown | Instant for common queries, streaming for deep analysis |
| Feedback loop | Thumbs up/down + full trace logging now. LLM-as-judge later | Start simple, iterate based on real data |
| Agent routing | Planner-driven (no manual agent selection) | The planner determines which tools to use, not the user |
| High-token queries | Graceful decline at Phase 1 | "This feature is coming soon" — prevents runaway costs |
| Hallucination | No claim without tool citation + tool result validation layer | Structural prevention > post-hoc detection |
| Error UX | Honest, actionable, never shows internals | "I couldn't access X, here's what I could gather" |
