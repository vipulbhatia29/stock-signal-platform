---
scope: project
category: future_work
created_by: session-60
updated_by: session-60 (final — 3-pronged analysis + observability audit)
---

# Agent Architecture Redesign — Full Analysis (Session 60)

JIRA: KAN-189 (Epic), KAN-188 (tool filtering)

## PRONG 1: WHERE WE ARE (current codebase)

### Agent Pipeline (NOT a real agent)
- `graph.py`: Linear StateGraph — `START → plan → execute → synthesize → END`
- `planner.py`: Single LLM call picks ALL tools upfront, before seeing any data
- `executor.py`: Mechanical — runs tool list in order, $PREV_RESULT substitution, circuit breaker, no reasoning
- `synthesizer.py`: Formats output, never changes the plan
- Only adaptation: `MAX_REPLAN=1` if search returns empty (not true reasoning)
- All 24 tool descriptions sent to planner every query (~2K tokens wasted)

### LLM Infrastructure (solid foundation)
- `LLMClient` with tier-based provider routing + fallback chain
- `GroqProvider` with internal multi-model cascade + error classification
- `TokenBudget` — async sliding-window tracker (TPM/RPM/TPD/RPD per model, 80% threshold)
- `ModelConfigLoader` — reads `llm_model_config` DB table, groups by tier, caches
- `llm_model_config` table has: provider, model_name, tier, priority, is_enabled, rate limits, **cost_per_1k_input/output**
- Admin API: CRUD on model configs, enable/disable tiers, reload config

### Observability (5 layers, partially wired)
1. **In-memory collector** (`observability.py`): requests/model, cascade count, RPM, tier health (healthy/degraded/down), latency avg+p95
2. **DB persistence** (`observability_writer.py`): LLMCallLog + ToolExecutionLog tables (TimescaleDB hypertables), session_id + query_id from ContextVars
3. **Token budget** (`token_budget.py`): per-model TPM/RPM/TPD/RPD sliding windows
4. **LLM cascade** (`providers/groq.py`): cascade events recorded to collector
5. **Admin API**: GET stats, GET health, PATCH enable/disable tiers

### DB Schema (designed for more than what's wired)
- `LLMCallLog`: has `cost_usd` column — **exists but never populated**
- `LLMCallLog`: has `tool_calls_requested` JSONB — captures what planner asked for
- `ToolExecutionLog`: has `cache_hit` boolean — **exists but never populated**
- `llm_model_config`: has `cost_per_1k_input/output` — pricing exists in DB, not used for cost calc
- Both log tables have `query_id` index — per-query aggregation is SQL-ready

## PRONG 2: WHERE THE GAPS ARE

### Agent Architecture Gaps
1. **No reasoning after tool calls** — planner decides everything upfront
2. **No adaptive tool selection** — tool N+1 is always the same regardless of tool N's result
3. **No self-determined stopping** — always runs all planned tools
4. **No tool filtering** — all 24 descriptions on every query
5. **No clarifying questions** — agent guesses and proceeds

### Observability Gaps
1. **cost_usd never calculated** — `llm_model_config` has pricing, `LLMCallLog` has column, no code connects them
2. **cache_hit never set** — executor knows (`CACHEABLE_TOOLS`), writer doesn't receive it
3. **No agent_id** — can't attribute costs/latency to specific agents (needed for multi-agent)
4. **No fallback_rate_last_60s()** — need windowed ratio, not just cumulative count
5. **No loop_step tracking** — needed after ReAct loop exists
6. **No per-query cost aggregation endpoint** — query_id exists, SQL is trivial
7. **No dynamic concurrency controller** — semaphore limit is hardcoded
8. **TokenBudget in-process only** — KAN-186 to move to Redis for multi-worker

### aset-platform Comparison
- They solved: specialized sub-agents with ReAct loops, two-tier routing, per-agent LLM instances, cost estimation
- They didn't solve: cross-domain queries (single dispatch only), fan-out parallel, dynamic concurrency, synthesis as separate node
- Our advantages: async-safe collector, tool execution tracking, DB persistence with query_id, tiered model config table

## Tiered LLM Setup — Already Built, Needs Wiring

### What exists (6 layers, solid)
1. **DB config** (`llm_model_config`): provider, model_name, tier, priority, is_enabled, TPM/RPM/TPD/RPD limits, cost_per_1k_input/output
2. **ModelConfigLoader**: reads DB at startup, groups by tier, caches, admin can reload
3. **TokenBudget**: per-model sliding windows TPM/RPM/TPD/RPD, 80% threshold pre-check
4. **GroqProvider**: internal multi-model cascade, budget-aware, error classification (rate_limit/context_length/auth/transient/permanent)
5. **LLMClient**: tier-based routing (`chat(tier="planner")` vs `chat(tier="synthesizer")`), provider-level fallback
6. **Three providers implemented**: `GroqProvider` (wired), `AnthropicProvider` (wired as fallback), `OpenAIProvider` (implemented but NOT wired in main.py)

### What needs wiring
- `cost_per_1k_input/output` all 0.000000 — never populated with real prices
- Anthropic + OpenAI rows missing from `llm_model_config` — should be in DB alongside Groq
- `OpenAIProvider` not in `main.py` cascade — one `providers.append()` line needed
- `cost_usd` on LLMCallLog never calculated — pricing in config table, formula trivial

### ReAct impact on tiers
- `tier="planner"` + `tier="synthesizer"` → `tier="reason"` (single LLM role, DB rows need updating)
- Multi-agent future: `tier="stock_reason"`, `tier="portfolio_reason"` (per-agent tiers)
- N calls per query instead of 2 → TokenBudget pressure increases, RPM limits hit faster
- Dynamic concurrency controller (KAN-189 Step 4) depends on fallback_rate from observability

## PRONG 3: WHERE WE'RE HEADING

### Build Order (from PM's 10-part spec)

**Step 1 — ReAct Loop (replaces pipeline)**
Replace graph.py/planner.py/executor.py/synthesizer.py with reason⇄act loop.
- `reason` node: LLM observes scratchpad → outputs thought + next_action OR finish
- `act` node: runs ONE tool, appends to scratchpad
- No separate planner. No separate synthesizer. One LLM does all three adaptively.
- Validation: tool N+1 must change based on tool N result.

**Step 2 — Tool Filtering (alongside Step 1)**
Rule-based intent classifier → inject relevant tool subset. Zero LLM cost.
Stock→8 tools, portfolio→6, market→5, comparison→stock+compare, general→all.

**Step 3 — Observability Audit (items 1-5 from gaps, doable NOW)**
Wire cost_usd calculation, populate cache_hit, add agent_id param, add fallback_rate method, per-query cost endpoint.

**Step 4 — Dynamic Concurrency Controller (after Step 3)**
ConcurrencyController reads fallback_rate → adjusts semaphore dynamically.

**Step 5 — Multi-Agent Fan-Out (after Step 1 stable)**
Stock Research Agent (structured StockFinding output), Portfolio Agent (holistic), Orchestrator Agent.
Fan-out for comparison queries. Holistic for portfolio. Never fan-out for rebalancing.

**Step 6 — Fallback Stagger + Cascade Protection (after Step 5)**
Jitter on fan-out starts. Fallback rate → semaphore throttling.

### What Does NOT Change
- `backend/services/` — service layer is correct, agents call atomic services
- `backend/tools/` — thin wrappers remain, tools become ReAct actions
- `llm_client.py` — fallback chain stays, called per-loop-iteration
- `token_budget.py` — stays, KAN-186 moves to Redis
- `llm_model_config` table — already has everything needed
- Frontend streaming — NDJSON events change names but same transport

### Pricing Data Already Available
`llm_model_config.cost_per_1k_input/output` → can calculate cost_usd per LLM call NOW.
Formula: `cost_usd = (prompt_tokens * cost_per_1k_input + completion_tokens * cost_per_1k_output) / 1000`
No new table needed — just wire ModelConfigLoader cache into observability_writer.
