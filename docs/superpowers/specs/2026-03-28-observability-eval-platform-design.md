# LLM Observability + Eval Platform — Design Spec

**JIRA:** KAN-162 (merged with KAN-157)
**Phase:** SaaS Launch Roadmap Phase B (revised)
**Status:** Draft
**Created:** 2026-03-28 (Session 68 brainstorm)

---

## 1. Vision

**Transparency as a feature.** Users see both the stock intelligence AND how the AI behind it is performing. The observability page is a first-class product surface — not an internal debugging tool.

Two audiences, two surfaces:
- **Users:** In-app Observability Page (`/observability`) — structured table with KPI ticker, navy theme, expandable drill-down
- **Developers:** Langfuse (port 3001) — full trace waterfall, prompt versioning, deep debugging. Linked from in-app via SSO.

## 2. Product Requirements

### 2.1 In-App Observability Page

#### KPI Ticker (top of page)
Five stat cards displayed horizontally above the table:

| Card | Source | Update Frequency |
|------|--------|-----------------|
| Queries Today | `llm_call_log` count (grouped by date) | On page load |
| Avg Latency | `tool_execution_log` avg duration per query | On page load |
| Avg Cost / Query | `llm_call_log` avg `cost_usd` per `query_id` | On page load |
| Eval Score | Latest eval run aggregate pass rate | After eval completes |
| Fallback Rate | `ObservabilityCollector.fallback_rate_last_60s()` | On page load |

#### Structured Table — Three Expansion Levels

**L1 — Row (aggregate per query):**

| Column | Source |
|--------|--------|
| Timestamp | `llm_call_log.created_at` |
| Query Text | `chat_messages` table (role=user) |
| Agent Type | `llm_call_log.agent_type` (future-proof for multi-agent) |
| Tools Used | `tool_execution_log` names joined, e.g. "analyze_stock → get_fundamentals → compute_signals" |
| LLM Calls | Count + model name(s), e.g. "2× llama-3.3-70b" |
| DB Calls | Count + function/table, e.g. "3× (signals, fundamentals, stocks)" |
| External Calls | Count + source, e.g. "1× yfinance, 1× Google News" |
| Total Cost | Sum of `cost_usd` for this `query_id` |
| Duration | Wall-clock from first to last log entry for this `query_id` |
| Eval Score | Backfilled from periodic eval (null if not evaluated) |
| Status | OK / Error / Declined |

**L2 — Expanded (per ReAct step):**
Click a row to expand. Shows each step of the ReAct loop:

| Field | Content |
|-------|---------|
| Step # | Loop iteration (1, 2, 3...) |
| Action | Tool name or "LLM reasoning" |
| Type Tag | `LLM` (with model name) / `DB` (with function) / `External` (with source) |
| Input | Tool params (truncated, expandable) |
| Output Summary | First 200 chars of tool result |
| Latency | Per-step duration |
| Cost | Per-step LLM cost (zero for DB/external calls) |
| Cache Hit | Yes/No (from `tool_execution_log.cache_hit`) |

**L3 — Deep Link to Langfuse:**
Button at bottom of L2 expansion: "View Full Trace in Langfuse →"
- Links to `{LANGFUSE_BASEURL}/trace/{query_id}`
- `query_id` is used as Langfuse `trace_id` (UUID, already unique)
- SSO pass-through: user is already authenticated (see §4)

#### Table Features
- **Filterable:** Date range, agent_type, status, cost threshold
- **Sortable:** Any column
- **Groupable by:** Agent type (future multi-agent), session, date
- **Pagination:** Server-side, 25 rows default

### 2.2 Langfuse (Developer Surface)

Self-hosted Langfuse instance for deep debugging. NOT embedded in the app — separate UI on port 3001, linked from the observability page.

**Used for:**
- Full trace waterfall (nested spans with timing)
- Prompt versioning and A/B testing
- Eval dataset management
- Session replay (full conversation thread)
- Cost breakdown visualizations

**NOT used for:** User-facing observability (that's the in-app table).

## 3. Langfuse Integration Architecture

### 3.1 Infrastructure

```
docker-compose.yml additions:
├── langfuse-db      (Postgres 16, separate instance, port 5434)
└── langfuse-server   (Langfuse v3, port 3001)
    ├── LANGFUSE_SECRET_KEY, LANGFUSE_PUBLIC_KEY (in .env)
    ├── DATABASE_URL → langfuse-db:5432
    └── NEXTAUTH_URL=http://localhost:3001
```

- **Separate Postgres:** Langfuse gets its own DB instance. No migration coupling with our app DB. ~50MB overhead.
- **Feature flag:** All Langfuse SDK calls gated on `settings.LANGFUSE_SECRET_KEY` being set. App works identically without it.

### 3.2 SDK Integration Points

```
backend/main.py (lifespan):
  └── Initialize Langfuse client (alongside Redis, TokenBudget, CacheService)
  └── Flush on shutdown

backend/routers/chat.py (chat_stream):
  └── Create Langfuse trace(id=query_id, session_id=chat_session_id, user_id=user.id)

backend/agents/react_loop.py (react_loop):
  └── Per-iteration: Langfuse span(name="react.iteration.{n}")
  └── LLM call: Langfuse generation(name="llm.{provider}.{model}", model=..., usage=..., cost=...)
  └── Tool call: Langfuse span(name="tool.{tool_name}", metadata={type: "db"|"llm"|"external", ...})

backend/agents/llm_client.py (LLMClient.chat):
  └── Langfuse generation with model, tokens, cost from _compute_cost()
  └── Cascade events: span per provider attempt

backend/agents/observability.py (ObservabilityCollector):
  └── NOT changed — continues writing to DB independently
  └── Langfuse is a parallel trace, not a replacement
```

### 3.3 Span Naming Convention

```
trace: query_id (UUID)
  ├── span: "react.iteration.1"
  │   ├── generation: "llm.groq.llama-3.3-70b"      [type: llm]
  │   └── span: "tool.analyze_stock"                  [type: db]
  ├── span: "react.iteration.2"
  │   ├── generation: "llm.groq.llama-3.3-70b"      [type: llm]
  │   └── span: "tool.get_fundamentals"              [type: db]
  ├── span: "react.iteration.3"
  │   ├── generation: "llm.groq.llama-3.3-70b"      [type: llm]
  │   └── span: "tool.web_search"                    [type: external, source: serp]
  └── span: "synthesis"
      └── generation: "llm.groq.llama-3.3-70b"      [type: llm]
```

**Metadata on every span:**
- `type`: `"llm"` | `"db"` | `"external"`
- `model`: Model name (for LLM spans)
- `source`: Function/table (for DB) or API name (for external)
- `cache_hit`: boolean
- `agent_type`: From ContextVar (future multi-agent grouping)
- `agent_instance_id`: From ContextVar

### 3.4 Correlation Strategy

| Our System | Langfuse | Relationship |
|-----------|----------|-------------|
| `query_id` (ContextVar) | `trace.id` | 1:1 — same UUID |
| Chat session ID | `trace.session_id` | Groups traces by conversation |
| `user.id` | `trace.user_id` | Per-user filtering |
| `agent_type` | `trace.metadata.agent_type` | Multi-agent grouping |
| ReAct iteration | `span.name` | Nested under trace |
| LLM call | `generation` | Model, tokens, cost |
| Tool call | `span` | Tagged db/llm/external |

## 4. SSO — Langfuse Authentication

Users authenticated to the stock signal app get seamless access to Langfuse without a separate login.

**Approach:** Configure Langfuse's custom OAuth provider to point to our backend as the OIDC issuer.

```
Langfuse env vars:
  AUTH_CUSTOM_CLIENT_ID=stock-signal-langfuse
  AUTH_CUSTOM_CLIENT_SECRET=<generated>
  AUTH_CUSTOM_ISSUER=http://localhost:8181/api/v1/auth
  AUTH_CUSTOM_NAME="Stock Signal Platform"
```

**Backend addition:** Minimal OIDC-compatible endpoints on our auth router:
- `GET /api/v1/auth/.well-known/openid-configuration` — discovery document
- `GET /api/v1/auth/authorize` — authorization endpoint (validates existing JWT session)
- `POST /api/v1/auth/token` — token exchange
- `GET /api/v1/auth/userinfo` — returns user profile

**User flow:**
1. User clicks "View in Langfuse" on observability page
2. Redirect to Langfuse with auth params
3. Langfuse calls our `/authorize` → we validate the user's existing JWT cookie
4. User lands on the correct trace page — no login prompt

**Google OAuth compatibility (Phase C / KAN-152):**
Both auth flows (email/password and Google OAuth) terminate in our JWT. Langfuse's OIDC config trusts our JWT issuer — it doesn't know or care how the JWT was originally issued. No changes needed to Langfuse SSO when Google OAuth lands.

The `/userinfo` endpoint returns consistent fields regardless of auth origin:
```json
{
  "sub": "user-uuid",
  "email": "user@example.com",
  "name": "Display Name",
  "auth_provider": "local | google"
}
```

**Fallback:** If OIDC setup proves complex, simpler alternative is a shared session token passed as URL parameter. Evaluate during implementation.

## 5. Eval Framework

### 5.1 Architecture

```
Eval Runner (Python script / CI job)
  ├── Load golden dataset (14 queries + failure variants)
  ├── For each query:
  │   ├── Call ReAct loop with real LLM (Groq)
  │   ├── Capture: tools called, tool outputs, final response, iteration count
  │   ├── Score: 5 dimensions (4 deterministic + 1 LLM-judge)
  │   └── Push scores to Langfuse (dataset run + scores)
  ├── Compute aggregate pass rate
  └── Output: JSON report + Langfuse dashboard update
```

### 5.2 Golden Query Dataset — 14 Queries

#### Intent Coverage (10 queries)

| # | Category | Query | Expected Tools | Route | Grounding Check |
|---|----------|-------|---------------|-------|-----------------|
| 1 | Single stock analysis | "Analyze AAPL for me" | analyze_stock, get_fundamentals | stock | References actual RSI, MACD, P/E values (analyze_stock returns signals internally) |
| 2 | Multi-stock comparison | "Compare AAPL and MSFT" | analyze_stock ×2, compare_stocks | comparison | Both tickers' data present, comparison table |
| 3 | Portfolio health | "How's my portfolio doing?" | portfolio_health, get_portfolio_exposure | portfolio | References user's actual positions |
| 4 | Market briefing | "What's happening in the market today?" | market_briefing | market | References real index values, sector data |
| 5 | Stock intelligence | "Any insider trading activity on TSLA?" | get_stock_intelligence | stock | References actual insider transaction data |
| 6 | Forecast query | "Where will AAPL be in 6 months?" | get_forecast, get_fundamentals | stock | References Prophet model output, confidence interval |
| 7 | Recommendation | "What should I buy for my portfolio?" | recommend_stocks, portfolio_health | portfolio | Portfolio-aware, not generic advice |
| 8 | Out-of-scope decline | "Write me a poem about stocks" | *none* | out_of_scope | Polite decline, zero tool calls |
| 9 | Ambiguous follow-up | "What about its dividends?" (after AAPL context) | dividend_sustainability | stock | Resolves pronoun to AAPL via EntityRegistry |
| 10 | Edge case — no data | "Analyze XYZFAKE123" | analyze_stock (fails gracefully) | stock | No hallucination, reports data unavailable |

#### Multi-Step Reasoning (4 queries)

| # | Category | Query | Expected Tools | Route | Reasoning Check |
|---|----------|-------|---------------|-------|-----------------|
| 11 | Cross-domain synthesis | "Is AAPL overvalued given its fundamentals and forecast?" | analyze_stock, get_fundamentals, get_forecast | stock | Must reason ACROSS all three — not just list them. Connects P/E to forecast to signals. |
| 12 | Conditional logic | "Should I sell TSLA if it drops below its SMA 200?" | analyze_stock, get_fundamentals | stock | Handles hypothetical vs current data. analyze_stock returns SMA data. |
| 13 | Portfolio + market synthesis | "How exposed am I to a tech sector downturn?" | portfolio_health, get_portfolio_exposure, market_briefing | portfolio | Synthesizes sector overlap between portfolio and market sectors. |
| 14 | Contradictory signals | "NVDA has great fundamentals but bearish technicals — what should I do?" | analyze_stock, get_fundamentals | stock | Acknowledges tension, weighs both sides. analyze_stock returns signal data. |

#### Tool Group Fixes Required (implementation prerequisite)

The following tool group gaps must be fixed in `backend/agents/tool_groups.py` before the assessment framework can run correctly:

1. **Add `dividend_sustainability` to `stock` group** — query 9 needs it for dividend follow-up on a specific ticker
2. **Add `market_briefing` to `portfolio` group** — query 13 needs cross-domain portfolio+market synthesis
3. **Add `compute_signals` to `stock` group** — not strictly needed (analyze_stock calls it internally) but useful if the agent wants signals without full analysis

#### Failure Variants (external API resilience)

For queries 1, 4, 5 — run once normally, once with external APIs mocked to fail:
- `news.py` → 503 (Google News RSS down)
- `yfinance` → timeout (market data unavailable)
- `web_search` → empty results (SERP API returns nothing)

**Check:** Agent produces grounded response (minus the unavailable data) rather than hallucinating or crashing. Graceful degradation, not silent failure.

### 5.3 Scoring Rubric — 5 Dimensions

| Dimension | Check Type | Method | Threshold |
|-----------|-----------|--------|-----------|
| **Tool Selection** | Deterministic | Set comparison: expected tools ⊆ actual tools called (order-insensitive) | 100% match required |
| **Grounding** | Deterministic | Substring check: response contains key values from tool output (ticker, scores, dates) | ≥80% of expected substrings present |
| **Termination** | Deterministic | Iteration count ≤ expected + 1. No duplicate tool calls. | Within bounds |
| **External Resilience** | Deterministic | On failure variants: no hallucinated data, graceful error message, partial results OK | No hallucination |
| **Reasoning Coherence** | LLM-as-judge | Sonnet scores 1-5: "Does the synthesis connect insights across tool outputs, or just list them?" | ≥3/5 average |

**Reasoning coherence** only evaluated on queries 11-14 (the multi-step reasoning set). Cost: 4 Sonnet calls per eval run ≈ $0.02.

### 5.4 CI Integration

```yaml
# .github/workflows/eval.yml
name: Agent Eval
on:
  schedule:
    - cron: '0 6 * * 1'  # Weekly Monday 6am UTC
  workflow_dispatch:       # Manual trigger
env:
  CI_GROQ_API_KEY: ${{ secrets.CI_GROQ_API_KEY }}
  LANGFUSE_SECRET_KEY: ${{ secrets.LANGFUSE_SECRET_KEY }}
  LANGFUSE_PUBLIC_KEY: ${{ secrets.LANGFUSE_PUBLIC_KEY }}
  LANGFUSE_BASEURL: ${{ secrets.LANGFUSE_BASEURL }}
```

**Pass/fail:**
- Hard fail if ANY deterministic score is below threshold (tool selection, grounding, termination, resilience)
- Soft warn if reasoning coherence < 3/5 average (doesn't block CI, but logged)
- Aggregate pass rate = (passed queries / total queries) × 100

**Scores backfilled:** After each eval run, scores are written to `eval_results` table (new) and to Langfuse dataset runs. The observability page reads from `eval_results` for the KPI ticker and per-query score column.

### 5.5 Multi-Agent Future-Proofing

The eval framework is designed to support multi-agent when the data justifies it:

- Golden queries are tagged by `intent_category` (stock, portfolio, market, comparison, etc.)
- Scores are recorded per `agent_type` — currently all "react_v2", but the schema supports N agents
- If eval data shows the single agent consistently scores low on portfolio queries (e.g., reasoning coherence < 3), that's the signal to specialize a Portfolio Agent
- `agent_type` column already exists on `llm_call_log` and `tool_execution_log` (migration 016)
- Observability table is filterable/groupable by agent_type

**Decision gate (project-plan):** After 4 weeks of eval data, review per-category scores. If any category consistently scores <80% on deterministic checks or <3/5 on reasoning, that category is a candidate for a specialized agent. This is NOT deprecated — it's a data-driven activation threshold.

## 6. Data Model

### 6.1 New Table: `eval_results`

```sql
CREATE TABLE eval_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    eval_run_id UUID NOT NULL,          -- groups all queries in one eval run
    query_index INTEGER NOT NULL,        -- 1-14
    query_text TEXT NOT NULL,
    intent_category VARCHAR(50) NOT NULL,
    agent_type VARCHAR(50) NOT NULL DEFAULT 'react_v2',
    -- scores
    tool_selection_pass BOOLEAN NOT NULL,
    grounding_score FLOAT NOT NULL,      -- 0.0-1.0
    termination_pass BOOLEAN NOT NULL,
    external_resilience_pass BOOLEAN,    -- NULL for non-failure-variant runs
    reasoning_coherence_score FLOAT,     -- 1.0-5.0, NULL for non-reasoning queries
    -- metadata
    tools_called JSONB NOT NULL,         -- ["analyze_stock", "get_fundamentals"]
    iteration_count INTEGER NOT NULL,
    total_cost_usd FLOAT NOT NULL,
    total_duration_ms INTEGER NOT NULL,
    langfuse_trace_id UUID,             -- link to Langfuse trace
    -- timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_eval_results_run ON eval_results(eval_run_id);
CREATE INDEX idx_eval_results_category ON eval_results(intent_category);
```

### 6.2 New Table: `eval_runs`

```sql
CREATE TABLE eval_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trigger VARCHAR(20) NOT NULL,        -- 'ci_scheduled' | 'ci_manual' | 'local'
    total_queries INTEGER NOT NULL,
    passed_queries INTEGER NOT NULL,
    pass_rate FLOAT NOT NULL,            -- 0.0-1.0
    total_cost_usd FLOAT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ NOT NULL
);
```

### 6.3 Existing Tables — No Changes

- `llm_call_log` — already has `query_id`, `agent_type`, `agent_instance_id`, `loop_step`, `cost_usd`
- `tool_execution_log` — already has `query_id`, `agent_type`, `cache_hit`
- `chat_messages` — already has query text
- No new columns needed on existing tables.

## 7. API Endpoints

### 7.1 Observability API (new router: `backend/routers/observability.py`)

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/api/v1/observability/kpis` | KPI ticker data (5 cards) | User (own data) or Admin (all) |
| GET | `/api/v1/observability/queries` | Paginated query list (L1 data) | User (own) or Admin (all) |
| GET | `/api/v1/observability/queries/{query_id}` | Single query detail (L2 data) | User (own) or Admin |
| GET | `/api/v1/observability/queries/{query_id}/langfuse-url` | Langfuse deep link URL | User (own) or Admin |
| GET | `/api/v1/observability/eval/latest` | Latest eval run summary | Any authenticated |
| GET | `/api/v1/observability/eval/history` | Eval run history | Admin |

### 7.2 OIDC Endpoints (additions to auth router)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/auth/.well-known/openid-configuration` | OIDC discovery |
| GET | `/api/v1/auth/authorize` | Authorization (validates JWT session) |
| POST | `/api/v1/auth/token` | Token exchange |
| GET | `/api/v1/auth/userinfo` | User profile |

## 8. Frontend

### 8.1 New Page: `/observability`

- Route: `src/app/(authenticated)/observability/page.tsx`
- Protected by auth guard (same as other authenticated pages)
- Navy theme, consistent with existing design system

### 8.2 Components

| Component | Description |
|-----------|-------------|
| `ObservabilityKPIs` | 5 stat cards (queries, latency, cost, eval score, fallback rate) |
| `QueryTable` | Paginated, sortable, filterable table (L1) |
| `QueryDetailPanel` | Expandable panel showing ReAct steps (L2) |
| `StepRow` | Single ReAct step with type tag (LLM/DB/External) |
| `LangfuseLink` | "View in Langfuse" button with trace_id |
| `EvalBadge` | Score badge (green/yellow/red) |

### 8.3 Hooks

| Hook | Purpose |
|------|---------|
| `useObservabilityKPIs()` | Fetch KPI data |
| `useQueryList(filters)` | Paginated query list with filters |
| `useQueryDetail(queryId)` | Fetch L2 detail for expanded row |

## 9. Non-Goals (This Phase)

- Real-time per-query scoring (no latency impact on chat)
- Building multi-agent architecture (observe first, decide with data)
- Replacing ObservabilityCollector or DB log tables (Langfuse is parallel)
- Embedding Langfuse UI in iframe (custom table is better UX)
- Prompt versioning workflows (Langfuse supports it, but not in scope)

## 10. Open Questions

1. **Langfuse v3 custom auth:** Need to verify exact env vars and OIDC flow compatibility during implementation. Fallback: shared token URL parameter.
2. **Eval test user:** The eval runner needs a seeded test user with portfolio data. Create during eval setup or use existing seed data?
3. **Eval query 9 (follow-up):** Requires session context from query 1. Run them sequentially in same session, or mock EntityRegistry state?

## 11. Acceptance Criteria

- [ ] Langfuse self-hosted running via `docker compose up` (port 3001)
- [ ] All ReAct loop steps visible as Langfuse traces with correct span hierarchy
- [ ] SSO: user clicks "View in Langfuse" and lands on trace without separate login
- [ ] `/observability` page renders KPI ticker + structured table (L1 + L2)
- [ ] Deep link from L2 to Langfuse trace works with correct `trace_id`
- [ ] 14 golden queries defined with expected tools and grounding checks
- [ ] Eval runner scores all 5 dimensions, outputs JSON + Langfuse dataset run
- [ ] CI eval job runs weekly (or on-demand), fails on deterministic score violations
- [ ] Scores visible on observability page (KPI ticker + per-query column)
- [ ] `agent_type` filterable in observability table (multi-agent future-proof)
- [ ] Failure variants test external API resilience (no hallucination on API failure)
- [ ] All existing tests pass (zero regression)

## 12. Review: Code Impact & Tech Debt

### 12.1 Files to Create (~18 new files)

**Backend (11):**
- `backend/routers/observability.py` — 6 endpoints (KPIs, query list, detail, Langfuse URL, eval)
- `backend/schemas/observability.py` — Pydantic request/response models
- `backend/models/eval.py` — `EvalRun`, `EvalResult` SQLAlchemy models
- `backend/services/langfuse_client.py` — Langfuse SDK wrapper, gated on feature flag
- `backend/services/oidc_provider.py` — OIDC endpoints for Langfuse SSO (or URL param fallback)
- `backend/tasks/eval_runner.py` — Eval orchestration: golden dataset, scoring, Langfuse push
- `backend/tasks/eval_dataset.py` — Golden queries as frozen dataclass (immutable, versioned)
- `backend/migrations/versions/017_add_eval_tables_and_indexes.py` — eval tables + missing log indexes
- `tests/api/test_observability.py` — API endpoint tests
- `tests/integration/test_eval_runner.py` — Eval runner integration tests
- `.github/workflows/eval.yml` — Weekly + on-demand CI job

**Frontend (7):**
- `src/app/(authenticated)/observability/page.tsx`
- `src/components/ObservabilityKPIs.tsx`
- `src/components/QueryTable.tsx`
- `src/components/QueryDetailPanel.tsx`
- `src/components/StepRow.tsx`
- `src/hooks/useObservabilityKPIs.ts`
- `src/hooks/useQueryList.ts`

### 12.2 Files to Modify (~9 files)

| File | Changes |
|------|---------|
| `backend/config.py` | Add `LANGFUSE_SECRET_KEY`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_BASEURL` to Settings |
| `backend/main.py` | Initialize Langfuse client in lifespan (after Redis/TokenBudget), flush on shutdown, mount observability router |
| `backend/agents/react_loop.py` | Add Langfuse span recording per iteration/tool/LLM call (gated). Extract `_record_iteration_span()`, `_record_tool_span()` helpers. |
| `backend/agents/llm_client.py` | Add Langfuse generation recording in `LLMClient.chat()`. Inject client via `__init__`. |
| `backend/routers/chat.py` | Create Langfuse trace after `query_id` is set (~line 163) |
| `backend/routers/auth.py` | Add 4 OIDC endpoints (or import from `oidc_provider.py`) |
| `docker-compose.yml` | Add `langfuse-db` (Postgres 16, port 5434) + `langfuse-server` (v3, port 3001) |
| `pyproject.toml` | Add `langfuse` SDK dependency |
| `backend/.env.example` | Add Langfuse env var template |

### 12.3 Tech Debt Found (address during implementation)

**CRITICAL — Missing indexes on log tables:**
```sql
CREATE INDEX idx_llm_call_log_created_at ON llm_call_log(created_at DESC);
CREATE INDEX idx_tool_execution_log_created_at ON tool_execution_log(created_at DESC);
CREATE INDEX idx_llm_call_log_query_cost ON llm_call_log(query_id, cost_usd);
CREATE INDEX idx_llm_call_log_created_agent ON llm_call_log(created_at DESC, agent_type);
```
Without these, KPI and query list endpoints will full-table scan. Include in migration 017.

**HIGH — Duplicate observability query logic:**
`backend/routers/admin.py` has `/admin/observability/query/{query_id}/cost` that queries the same tables as the new `/observability/queries/{query_id}`. Extract shared logic into `backend/services/observability_queries.py` to avoid divergence.

**HIGH — Langfuse must be fire-and-forget:**
Every Langfuse SDK call must be wrapped in try-except with logging. Chat loop must NEVER wait for or fail on Langfuse. Follow the same pattern as `ObservabilityCollector._safe_db_write()`.

**MEDIUM — Eval runner design gaps:**
- Golden dataset stored as frozen Python dataclass (not DB, not YAML) — immutable, versioned
- Entry point: `uv run python -m backend.tasks.eval_runner` (CLI) + Celery task
- Test user: seeded during eval setup (insert user + portfolio + positions)
- Query 9 (follow-up): run sequentially after query 1 in same session

**MEDIUM — KPI endpoint caching:**
Heavy aggregate queries on page load. Use CacheService with `volatile` TTL (60s) for KPI results.

**LOW — Frontend sidebar nav:**
Add "Observability" link to sidebar navigation component.

### 12.4 Architecture Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Langfuse container failure breaks chat | HIGH | Feature-gated, fire-and-forget, try-except all SDK calls |
| OIDC SSO complexity with Langfuse v3 | HIGH | Verify during dev; URL param fallback ready |
| React loop instrumentation adds 100+ lines | MEDIUM | Extract span recording into helper functions |
| Eval dataset becomes stale as tools change | MEDIUM | Frozen versioned dataclass, bump schema_version on changes |
| KPI queries slow on large tables | MEDIUM | Indexes (§12.3) + CacheService volatile TTL |
