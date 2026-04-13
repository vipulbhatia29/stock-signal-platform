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

## ADR-009: Prophet Train-Once-Predict-Many Architecture

**Date:** 2026-04-02 | **Status:** Implemented (Session 88, PR #177) | **Context:** Phase 8.6+ Forecast Intelligence (KAN-370)

### Decision
Prophet models are trained on a weekly schedule (or on-demand via drift detection). Forecasts are generated for all future dates at training time and stored in `forecast_results`. Daily changes in news and signals are reflected through the convergence layer, not through Prophet retraining.

### Problem
Stock prices change daily and news changes every few hours. Naively, this suggests retraining Prophet daily. But Prophet fitting is expensive (~5s/ticker × 500 tickers = ~42 min), and daily retraining provides marginal accuracy improvement for a curve-fitting model.

### Options Considered

| Option | Pros | Cons |
|--------|------|------|
| **A) Retrain daily** | Freshest possible forecast | ~42 min compute nightly, marginal accuracy gain for a trend+seasonality model |
| **B) Train weekly + convergence layer** | 6x less compute, daily freshness via convergence, drift detection handles exceptions | Stored forecast is stale between retrains |
| **C) Train monthly** | Minimal compute | Too stale for volatile tickers, drift detection would trigger constant retrains |

### Rationale (Option B chosen)
- **Prophet is a curve-fitting model**, not a neural network. It decomposes time series into trend + seasonality + regressors. The trend doesn't change meaningfully day-to-day.
- **The convergence layer provides daily freshness** without retraining: it combines the stored forecast direction with fresh RSI, MACD, SMA, Piotroski, and news sentiment signals. This is what users actually see (traffic lights + divergence alerts).
- **Drift detection auto-triggers retrains** when a model's rolling MAPE exceeds its per-ticker calibrated threshold (backtest MAPE × 1.5). No manual intervention needed.
- **News sentiment impacts two layers**: (1) convergence view updates within hours (no retrain), (2) Prophet regressors update at next weekly retrain via `add_regressor()`.
- **Admin can force retrain** for specific tickers via `POST /backtests/run` when market events warrant it.

### How the Layers Work

```
WEEKLY (Prophet retrain):
  Historical prices + sentiment → fit model → store forecast_results
  ↳ Static until next retrain

NIGHTLY (convergence snapshot, <1 min):
  Stored forecast direction + fresh RSI + fresh MACD + fresh SMA
  + fresh Piotroski + fresh news sentiment → convergence label
  ↳ Updates every night, reflects daily changes

EVERY 4 HOURS (news pipeline):
  Ingest articles → LLM scoring → news_sentiment_daily
  ↳ Feeds into next convergence snapshot

ON DRIFT (automatic):
  Rolling MAPE > calibrated threshold → queue retrain → validate → promote
  ↳ Self-healing: experimental models auto-recover when passing
```

### Consequences
- Users see daily-fresh convergence signals even though Prophet trains weekly.
- Divergence alerts ("forecast says bullish but 3 signals say bearish") are the primary user-facing value — they don't require retraining.
- The admin pipeline dashboard must clearly communicate this architecture — "Why weekly?" explanation on the Prophet retrain task card.
- Pipeline scheduling is editable by admins (stored in Redis, validated with min-interval guards).

---

## ADR-010: Per-Ticker Calibrated Drift Detection

**Date:** 2026-04-02 | **Status:** Implemented (Session 88, PR #177) | **Context:** Phase 8.6+ (KAN-376)

### Decision
Replace the flat 20% MAPE drift threshold with per-ticker calibrated baselines: `backtest_mape × 1.5`. Models that fail 3 consecutive drift checks are demoted to "experimental" status. Models self-heal when they pass again.

### Options Considered

| Option | Pros | Cons |
|--------|------|------|
| **A) Flat 20% threshold** | Simple | TSLA at 15% might be great; JNJ at 15% might be terrible |
| **B) Per-ticker calibrated** | Tight thresholds for stable stocks, permissive for volatile ones | Requires backtest data; falls back to 20% if none |
| **C) Percentile-based** | Statistical rigor | Requires many backtest runs to establish percentiles |

### Rationale (Option B chosen)
- Calibrated thresholds reflect each ticker's inherent predictability. A utility stock with 5% MAPE should alert at 7.5%, not 20%.
- Falls back gracefully to 20% when no backtest data exists (new tickers, pre-backtest state).
- The 1.5× multiplier provides a buffer — normal variance doesn't trigger false alarms.
- Experimental demotion (3 consecutive failures) prevents unreliable models from being used in convergence alignment counts.
- Self-healing means temporary market shocks don't permanently sideline a model.

### Consequences
- `BacktestRun` table must exist and be populated before calibrated thresholds kick in.
- `ModelVersion.metrics` stores `consecutive_drift_failures` and `drift_threshold_used` for observability.
- Admin dashboard shows the calibrated threshold alongside the actual MAPE for transparency.

---

## ADR-011: Event-Driven Cache Invalidation (Not TTL-Only)

**Date:** 2026-04-02 | **Status:** Implemented (Session 88, PR #177) | **Context:** Phase 8.6+ (KAN-376)

### Decision
Use a single `CacheInvalidator` service with event-driven methods (`on_prices_updated`, `on_forecast_updated`, etc.) rather than relying solely on TTL expiry.

### Options Considered

| Option | Pros | Cons |
|--------|------|------|
| **A) TTL-only** | Zero coordination code | Stale data served until TTL expires (up to 1hr for some caches) |
| **B) Event-driven invalidation** | Immediate freshness after data changes | Requires wiring into all data-write sites |
| **C) Hybrid** | Immediate for critical paths, TTL for expensive recomputation | Two mechanisms to reason about |

### Rationale (Option C — hybrid chosen)
- **Per-ticker caches** (convergence, forecast, signals) use event-driven invalidation — stale convergence data after a signal update is confusing for users.
- **User-scoped caches** (BL forecast, Monte Carlo, CVaR) use 1hr TTL — these are expensive to compute and don't change frequently. Portfolio changes trigger explicit invalidation.
- **Sector caches** use pattern-based SCAN clearing when forecasts update (can't efficiently map ticker→sector in the invalidator).
- All methods are fire-and-forget with try/except — Redis failures log warnings but never crash the caller.
- Batched `delete(*keys)` instead of per-key calls for performance at scale.

### Consequences
- Every data-write site (Celery tasks, API endpoints) must call the appropriate `CacheInvalidator` method.
- Cache keys follow a namespaced convention: `app:{domain}:{identifier}` (e.g., `app:convergence:AAPL`).
- Admin can clear caches manually via the pipeline dashboard, with audit logging.

---

## ADR-012: DB-Driven LLM Model Cascade (Not Hardcoded)

**Date:** 2026-04-03 | **Status:** Implemented | **Context:** Phase 6 (Epic KAN-139), llm-factory-cascade spec

### Decision
LLM provider cascade is configured via `llm_model_config` database table, not hardcoded in `config.py`. Admin can rebalance models and costs at runtime without code deploy.

### Options Considered

| Option | Pros | Cons |
|--------|------|------|
| **A) DB-driven config** | Runtime rebalancing without deploy, per-tier model configs (cheap/quality/reason), cost tracking per model, easy A/B testing | Additional DB lookup on every model call (cached) |
| **B) Hardcoded cascade** | No DB dependency, simple | Code deploy required for any model change, no per-tier tuning |

### Rationale
- Admin observes cost or latency spikes and rebalances models in minutes, not hours (code deploy).
- Per-tier pricing: `tier="cheap"` might use Groq ($/1M lower), `tier="quality"` uses Anthropic, `tier="reason"` uses o1-preview. Database enables this flexibility.
- Cost tracking per model tier enables accurate per-feature cost attribution to users.
- Cached reads prevent N+1 lookups — `llm_model_config` is hydrated once per request and stored in request-scoped cache.

### Consequences
- `llm_model_config` table is a critical dependency. Migration must create default rows at init time.
- Hot-reload endpoint exists for admins (requires `role="admin"`). No app restart needed.
- All LLM factory calls pass through `get_model_config(tier)`, which reads from cache.

---

## ADR-013: Three-Tier Redis Cache Namespace with SCAN

**Date:** 2026-04-03 | **Status:** Implemented | **Context:** Phase 7 (KAN-170), redis-cache spec

### Decision
Cache keys use `app:`, `user:`, `session:` prefixes for namespacing. Pattern clearing uses Redis `SCAN` (never `KEYS *`).

### Options Considered

| Option | Pros | Cons |
|--------|------|------|
| **A) Flat keys + KEYS *** | Simple namespace detection | KEYS blocks Redis in production (~500ms on 1M keys), prevents cache operations during clearing |
| **B) Namespaced prefixes + SCAN** | Non-blocking pattern iteration, prevents cross-user cache leaks, clear by prefix | Requires consistent prefix discipline across all code |

### Rationale
- `KEYS` is a synchronous blocking operation — using it in production violates observability SLAs.
- SCAN is O(N) but non-blocking: it iterates in batches and yields control to other clients.
- Namespace tiers prevent accidents: `user:alice:*` never leaks into `user:bob:*` if patterns are enforced.
- `app:` tier for global caches (schema, config), `user:` for user-scoped (portfolio, forecast), `session:` for request-scoped.
- TTL jitter (±10%) on all tiers prevents thundering herd after mass expiry.

### Consequences
- All new cache code must follow the naming convention. Code review enforces this.
- `CacheInvalidator.clear_user_caches(user_id)` uses `SCAN app:*`, `SCAN user:{user_id}:*` patterns.
- Monitoring alerts if SCAN takes >100ms (indicates Redis memory pressure).

---

## ADR-014: httpOnly Cookies + Dual-Mode Auth

**Date:** 2026-04-03 | **Status:** Implemented | **Context:** Phase 2 (Sessions 4-7), auth-overhaul spec

### Decision
JWT tokens are stored in httpOnly Secure SameSite=Lax cookies. Server reads tokens from cookies OR Authorization header (dual-mode) for compatibility.

### Options Considered

| Option | Pros | Cons |
|--------|------|------|
| **A) localStorage** | Client can read token in JS | Vulnerable to XSS attacks (attacker JS exfiltrates token) |
| **B) Cookie-only** | XSS-safe | Breaks API clients, browser doesn't send cookies for cross-origin requests without credentials |
| **C) Dual-mode (cookie + header)** | XSS-safe + API clients work, CORS-friendly | Requires CORS allow_credentials=True |

### Rationale
- httpOnly cookies prevent XSS attacks from accessing tokens via `document.cookie`.
- Dual-mode supports both browser clients (cookie auto-sent) and programmatic clients (pass header manually).
- SameSite=Lax blocks accidental CSRF while allowing cross-site top-level navigations.
- Secure flag ensures cookies only sent over HTTPS (enforced in production, skipped in local dev with `os.getenv`).

### Consequences
- CORS configuration must allow credentials: `allow_credentials=True` with explicit origin list (no wildcard).
- Frontend never accesses the token — no `localStorage.getItem('token')` pattern.
- API clients must be documented: "Pass `Authorization: Bearer <token>` header OR set the cookie via `credentials: 'include'` in fetch."

---

## ADR-015: User-Level Token Revocation (Not Per-Token JTI)

**Date:** 2026-04-03 | **Status:** Implemented | **Context:** Phase C Auth Overhaul (KAN-325), Session 82

### Decision
On sensitive actions (password change, account delete), set Redis key `auth:revoke:{user_id}` to current Unix timestamp. Any JWT with `iat < revoke_timestamp` is rejected on every request.

### Options Considered

| Option | Pros | Cons |
|--------|------|------|
| **A) Per-token JTI blocklist** | Revokes exactly one token | Scales O(N) — one Redis entry per revoked token, huge for active users |
| **B) User-level revocation** | Revokes ALL sessions in O(1) lookup | Logs out all devices simultaneously |

### Rationale
- Password change or account deletion requires revocation of all sessions for security. Per-token revocation defeats this purpose.
- Redis `GET auth:revoke:{user_id}` is O(1) — scales to millions of users.
- Every JWT must include `iat` claim (standard RFC 7519). Verification compares `token.iat < redis_revoke_timestamp`.
- On first login after revocation, new JWT has fresh `iat > revoke_timestamp`, so it passes.
- Fire-and-forget: if Redis is down, we skip the revocation check but log a warning (don't fail the request).

### Consequences
- All user-modifying endpoints (change password, delete account) must call `set_user_revocation(user_id)`.
- `get_current_user` adds one Redis lookup per request (cached via middleware).
- Admins cannot revoke individual sessions — by design.

---

## ADR-016: Soft-Delete with 30-Day Grace Period

**Date:** 2026-04-03 | **Status:** Implemented | **Context:** Phase C Auth Overhaul (KAN-343), Session 82

### Decision
Account deletion sets `deleted_at` timestamp. Celery Beat task purges accounts where `deleted_at + 30d < now` with hard delete + cascading FK deletes.

### Options Considered

| Option | Pros | Cons |
|--------|------|------|
| **A) Immediate hard delete** | Clean, no soft-deleted rows | Irreversible if accidental, blocks GDPR requests |
| **B) Soft-delete with grace period** | Recovery window, GDPR-compliant, audit trail | Requires cleanup task, deleted accounts still in DB temporarily |

### Rationale
- 30-day grace period allows accidental recovery and gives GDPR requests time to verify user identity.
- Admin recovery endpoint exists: `POST /admin/restore/{user_id}` (requires 2FA + audit log).
- Hard delete after 30d is automatic and non-reversible — users accept this in confirmation dialog.
- Soft deletion is transparent to queries: `WHERE deleted_at IS NULL` filters automatically in `get_user(user_id)`.

### Consequences
- `User` model has `deleted_at` nullable timestamp column.
- All user queries add implicit `deleted_at IS NULL` filter (enforced via SQLAlchemy hybrid property or query base class).
- Celery Beat task `purge_deleted_accounts` runs daily at 03:00 UTC. ON DELETE CASCADE must exist on all FK relationships.

---

## ADR-017: Tiered Test Pyramid — xdist Only for Unit Tests

**Date:** 2026-04-03 | **Status:** Implemented | **Context:** Phase D Test Overhaul (Epic KAN-356), test-suite-overhaul spec

### Decision
pytest-xdist parallel execution (`-n auto`) is enabled ONLY for `tests/unit/`. API and integration tests run sequentially on a single worker.

### Options Considered

| Option | Pros | Cons |
|--------|------|------|
| **A) xdist everywhere** | Faster overall CI time | Race conditions on shared test database, timing-dependent failures, hard to debug |
| **B) Sequential all** | Deterministic, reproducible | Slow CI — API tests alone take 6 min single-threaded |
| **C) Tiered parallelism** | Unit tests parallelized (pure functions), API/integration sequential (shared DB) | Two job types to maintain |

### Rationale
- Unit tests are pure functions with no I/O — parallelizing them is safe and fast.
- API and integration tests share a single test database. Parallel writes cause race conditions (`IntegrityError` on duplicate key inserts, `RowNotFound` on concurrent deletes).
- `tests/unit/` runs with `-n auto` (~8s), `tests/api/` and `tests/integration/` run sequentially (~6m).
- Total CI time with filtering: ~4 min (backend only) or ~8 min (both backend + frontend).

### Consequences
- CI splits into two jobs: `test-unit-parallel` and `test-api-sequential`.
- New tests are marked `@pytest.mark.unit`, `@pytest.mark.api`, or `@pytest.mark.integration` via conftest.
- Developers run locally: `uv run pytest tests/unit/ -n auto` for speed, `uv run pytest tests/api/` sequentially before push.

---

## ADR-018: Path-Based CI Routing (dorny/paths-filter)

**Date:** 2026-04-03 | **Status:** Implemented | **Context:** Phase D Sprint 2 (KAN-358), Session 84

### Decision
GitHub Actions jobs only run when relevant files change. Backend jobs skip on frontend-only PRs. Frontend jobs skip on backend-only PRs. Uses `dorny/paths-filter` action.

### Options Considered

| Option | Pros | Cons |
|--------|------|------|
| **A) Run all checks on every PR** | Simple, no conditional logic | ~8 min per PR, 14 checks × 2 languages = wasteful |
| **B) Path-based filtering** | Backend PR takes ~3 min (backend tests + lint), frontend PR takes ~2 min (frontend tests + lint) | Requires filter config, aggregator job needed |

### Rationale
- Full CI suite (all 14 checks) takes ~8 minutes. Path filtering reduces median PR time to ~3 min.
- Developers expect instant feedback — 8 min is too slow.
- `ci-gate` aggregator job ensures "all relevant checks pass" before merge is allowed.
- Filter config is declarative YAML — easy to update when directories change.

### Consequences
- `.github/workflows/ci-gate.yml` includes path-filter step + conditional job runs via `needs: test-backend` syntax.
- New directories require updating the paths-filter config (e.g., new backend service directory).
- Developers running locally: `uv run pytest tests/ -q && uv run ruff check && uv run pyright`.

---

## ADR-019: Three-Level Forecast Hierarchy (Stock → Sector → Portfolio)

**Date:** 2026-04-03 | **Status:** Implemented | **Context:** Phase 8.6+ (Epic KAN-369), forecast-intelligence spec

### Decision
Stock-level Prophet forecasts aggregate upward via equal-weighting. Sector forecasts equal-weight their stock constituents (not independent models). Portfolio forecasts use Black-Litterman optimization with Prophet views + Monte Carlo + CVaR.

### Options Considered

| Option | Pros | Cons |
|--------|------|------|
| **A) Independent models per level** | Precise sector/portfolio models | High compute cost, hard to explain why sector model disagrees with stocks |
| **B) Sector = equal-weight, Portfolio = BL** | Transparent aggregation, BL handles correlations, lower compute | Sector accuracy depends entirely on stock accuracy |
| **C) Portfolio-only (skip sector)** | Simpler | Users lose sector-level insights |

### Rationale
- Equal-weight sector aggregation is transparent: "Sector forecast = average of its stocks' forecasts." Users understand this.
- Black-Litterman is the industry standard for combining market priors with views. Prophet views (expected returns) feed naturally into BL.
- Stock-level accuracy >> sector/portfolio accuracy in forecasting. Aggregating up preserves this advantage.
- Portfolio forecast requires ≥2 positions with 1yr price history — it's not computed for new users until history exists.

### Consequences
- `forecast_sector` view reads `forecast_stock` and aggregates via SQL `GROUP BY sector, date`. No separate Prophet model for sectors.
- `get_portfolio_forecast` runs Black-Litterman on holdings. Requires covariance matrix (computed from historical prices) and expected returns (from Prophet).
- Sector forecast is deterministic and cacheable (`user:*:sector_forecast:SPX` cached for 1d).

---

## ADR-020: Template-Based Rationale (LLM Only for Complex Divergences)

**Date:** 2026-04-03 | **Status:** Implemented | **Context:** Phase 8.6+ Spec C (KAN-384), Session 90

### Decision
~90% of convergence rationales are generated via Python string templates. LLM-generated rationale is reserved for complex divergence cases (e.g., BUY signal but 3+ indicators bearish, contradictory news sentiment).

### Options Considered

| Option | Pros | Cons |
|--------|------|------|
| **A) LLM for all rationales** | Flexible, always novel | $0.001–0.01 per rationale, 500ms latency, ~500 tickers × 2 nightly runs = $5/day + 4 min compute |
| **B) Templates only** | Zero cost, instant, deterministic | Limited flexibility, static text feels canned |
| **C) Templates + LLM fallback** | 90% instant + cheap, 10% flexible for edge cases | Template library must be comprehensive |

### Rationale
- At 500 tickers × 2 daily convergence snapshots = 1,000 rationales/day. LLM cost adds up fast ($5/day = $150/month).
- Template generation is O(1) per rationale — instant response.
- Complex divergences are rare (~5–10% of tickers) and genuinely benefit from LLM reasoning.
- Template library covers all common patterns: price near MA, RSI overbought, strong divergence alignment, weak signals, etc.
- LLM fallback prevents users seeing "rationale not available" for edge cases.

### Consequences
- Create comprehensive template library in `backend/convergers/rationale_templates.py`. Add templates as new divergence patterns emerge.
- LLM calls to `anthropic.beta.messages.create()` only for divergences matching 3+ specific conditions (tagged `needs_llm_reasoning=True`).
- Monitor template coverage: if >20% of rationales fall back to LLM, add new templates.

---

## ADR-021: Observability as Bounded Package (backend/observability/)

**Date:** 2026-04-03 | **Status:** Implemented | **Context:** Phase B.5 BU-7 Command Center (KAN-233), command-center spec

### Decision
Extract all observability code into `backend/observability/` package with a single public API. Re-export shims at old import paths for backward compatibility during migration.

### Options Considered

| Option | Pros | Cons |
|--------|------|------|
| **A) Observability scattered** | No extra indirection | Hard to maintain, unclear ownership, difficult to extract as service later |
| **B) Bounded observability package** | Clear ownership, enables future extraction as microservice, centralized config, single entry point | Requires minor refactoring, backward-compat shims needed |

### Rationale
- Current observability code spans `agents/`, `routers/`, `services/` — ownership is diffuse.
- Bounded package enables future microservice extraction (Phase 9B) without major refactoring.
- Single entry point for metrics, tracing, health checks, and admin routers makes onboarding easier.
- Clean dependency graph: routers call `backend.observability.collector`, not `backend.agents.observer`.

### Consequences
- Create `backend/observability/` with 8 modules: `collector.py`, `writer.py`, `langfuse.py`, `context.py`, `token_budget.py`, `queries.py`, `models.py`, and `metrics/` subpackage.
- Old imports like `from backend.agents import observer` still work via shims in `backend/agents/__init__.py`.
- Gradual migration: new code imports from `backend.observability`, old code imports from shims.

---

## ADR-022: Redis-Backed HTTP Metrics (Not In-Memory Counters)

**Date:** 2026-04-03 | **Status:** Implemented | **Context:** Phase B.5 BU-7 (KAN-290), command-center spec

### Decision
HttpMetricsMiddleware stores request metrics in Redis sorted sets with 5-minute sliding windows. Path normalization prevents high cardinality.

### Options Considered

| Option | Pros | Cons |
|--------|------|------|
| **A) In-memory counters** | Simple, no external dependency | Uvicorn spawns N workers — counters are 1/N of actual traffic per worker. Totals are wrong. |
| **B) Redis-backed metrics** | Accurate aggregate across all workers, queryable per-path, sliding-window TTL | Redis latency (~1ms per request) |
| **C) Prometheus client library** | Standard observability format | Still has the N-worker problem without a shared backend |

### Rationale
- Uvicorn with `--workers 4` spawns 4 processes. In-memory counters in each worker show 25% of actual traffic — dashboards are wrong.
- Redis sorted sets with timestamp scores enable sliding-window queries: `ZCOUNT path:method:path_name now-5min now` = requests in last 5 min.
- Path normalization (`/users/{user_id}` → `/users/{id}`) prevents cardinality explosion (no per-user metrics).
- Excluded paths (`/health`, `/admin/command-center`) prevent self-monitoring loops.

### Consequences
- Add `HttpMetricsMiddleware` to FastAPI app startup. Increments Redis counters on every request (fire-and-forget via background task).
- Admin endpoint `GET /admin/metrics/http` queries Redis and returns per-path stats (top 10 slow endpoints, error rates by path, etc.).
- Metric retention: 24hr TTL on sorted sets (no manual cleanup needed, TTL expires old entries).

---

## ADR-023: Intraday Refresh Fast/Slow Path Split

**Date:** 2026-04-12 | **Status:** Implemented (Session 107, PR #225, KAN-424)

### Decision
Split `_refresh_ticker_async` into `_refresh_ticker_fast` (parallelized) and `_refresh_ticker_slow` (sequential nightly only). Fast path uses `asyncio.gather + Semaphore(5)`. Slow path runs as Phase 1.5 in the nightly chain before Phase 2.

### Options Considered

| Option | Pros | Cons |
|--------|------|------|
| **A) Unified async with higher concurrency** | Simpler single function | yfinance blocks signals unnecessarily |
| **B) Fast/slow split** | Fast path parallelized (~0.1s/ticker), slow path isolated (~3s/ticker) | Two code paths to maintain |
| **C) Thread pool for slow path** | True parallelism for blocking calls | Adds complexity, asyncio.gather is simpler |

### Rationale
- The single `_refresh_ticker_async` function combined fast operations (prices + signals + QuantStats, ~0.1s/ticker) with slow operations (yfinance info + dividends, ~3s/ticker). With 600 tickers, the combined sequential loop took ~50 minutes — exceeding the 30-minute beat schedule interval.
- Splitting allows the fast path to run 600 tickers in ~2 min (was ~50 min) via `asyncio.gather + Semaphore(5)`.
- Phase 1.5 adds ~20 min for slow path but doesn't block signal computation.
- `_refresh_ticker_async` preserved as backward-compatible wrapper for on-demand refresh.

### Consequences
- Nightly fast path: 600 tickers in ~2 min (was ~50 min).
- Phase 1.5 adds ~20 min for slow path but doesn't block signal computation.
- `_refresh_ticker_async` preserved as backward-compatible wrapper for on-demand refresh.

---

## ADR-024: Semaphore Bound = DB Pool Size

**Date:** 2026-04-12 | **Status:** Implemented (Session 107, PR #225, KAN-424)

### Decision
Set `INTRADAY_REFRESH_CONCURRENCY=5` (= `pool_size`). This ensures concurrent refreshes never exhaust the base pool, leaving all 10 overflow connections for API traffic and other tasks.

### Options Considered

| Option | Pros | Cons |
|--------|------|------|
| **A) Semaphore=10 (use overflow)** | Higher throughput | API traffic would compete for connections during nightly refresh |
| **B) Semaphore=pool_size (5)** | Leaves overflow for API traffic, predictable resource usage | Slightly lower throughput |
| **C) Semaphore=pool_size/2** | Very conservative, large headroom | Over-conservative; nightly runs off-peak when API traffic is minimal |

### Rationale
- The fast path parallelizes ticker refreshes via `asyncio.gather`. Each refresh needs one DB connection from `async_session_factory()`. Postgres pool is configured as `pool_size=5, max_overflow=10` (effective peak 15).
- Setting concurrency to `pool_size` ensures base pool is used, overflow is reserved for API traffic and other tasks.
- Nightly refresh runs off-peak, so `pool_size/2` is unnecessarily conservative.

### Consequences
- Config is env-tunable via `INTRADAY_REFRESH_CONCURRENCY` in backend/.env.
- If `DB_POOL_SIZE` changes, `INTRADAY_REFRESH_CONCURRENCY` should be updated in tandem.

---

## ADR-025: @tracked_task Decorator for Pipeline Observability

**Date:** 2026-04-07 | **Status:** Implemented (Sessions 99-104, KAN-420, PRs #210-214)

### Decision
Wrap all Celery async helpers in `@tracked_task(pipeline_name, trigger)` which:
1. Creates a `PipelineRun` row before execution (status: running)
2. Injects `run_id: uuid.UUID` as a keyword argument
3. On success: marks run as completed with timing
4. On exception: marks run as failed with generic error summary (Hard Rule #10), re-raises

### Pattern
```python
@tracked_task("model_retrain", trigger="scheduled")
async def _retrain_all_async(*, run_id: uuid.UUID) -> dict:
    ...  # run_id auto-injected by decorator
```

### Options Considered

| Option | Pros | Cons |
|--------|------|------|
| **A) Manual tracking in each task** | No decorator magic | Boilerplate in 24 tasks, inconsistent lifecycle handling |
| **B) @tracked_task decorator** | Unified lifecycle, consistent error handling, auto-injected run_id | Decorator indirection |
| **C) Celery signals (task_prerun/postrun)** | No code changes per task | No per-ticker granularity, can't inject run_id |

### Rationale
- Celery tasks had no unified lifecycle tracking. Failures were logged but not persisted. Admin dashboard couldn't show per-task execution history, per-ticker outcomes, or pipeline health.
- The decorator pattern provides consistent lifecycle tracking across all 24 Celery task helpers.
- `bypass_tracked` test shim (PR #212) allows unit tests without DB setup.
- `celery_task_id` column links PipelineRun to Celery retry chain.

### Consequences
- All 24 Celery task helpers now have PipelineRun lifecycle tracking.
- Admin dashboard shows per-run: start/end time, duration, ticker success/failure counts.
- `bypass_tracked` test shim (PR #212) allows unit tests without DB setup.
- `celery_task_id` column links PipelineRun to Celery retry chain.

---

## ADR-026: PipelineRunner State Machine

**Date:** 2026-04-07 | **Status:** Implemented (Sessions 99-104, KAN-420/421)

### Decision
`PipelineRunner` class provides:
- `start_run(pipeline_name, trigger, tickers_total)` — creates PipelineRun row
- `record_ticker_success(run_id, ticker)` / `record_ticker_failure(run_id, ticker, reason)` — per-ticker tracking
- `complete_run(run_id)` — finalizes with end time and status
- `update_watermark(pipeline_name, date)` — advances high-water mark for gap detection
- `detect_stale_runs()` — cleans up runs stuck in "running" state (crash recovery)

### Models

| Model | Key Fields |
|-------|------------|
| `PipelineRun` | id, pipeline_name, trigger, status (running/completed/failed), tickers_total, succeeded_count, failed_count, started_at, completed_at, error_summary, celery_task_id |
| `PipelineWatermark` | pipeline_name (unique), last_completed_date, last_completed_at, status |

### Options Considered

| Option | Pros | Cons |
|--------|------|------|
| **A) Flat log table** | Simple append-only | No state transitions, no watermarks, no crash recovery |
| **B) State machine with watermarks** | Resumable runs, gap detection, stale run cleanup | More complex model layer |
| **C) External orchestrator (Airflow/Prefect)** | Battle-tested state machines | Heavy dependency for ~24 tasks, operational overhead |

### Rationale
- The `@tracked_task` decorator needs a backing state machine to manage run lifecycle, per-ticker outcomes, and watermarks for gap detection.
- Pipeline execution is resumable — failed tickers can be reprocessed without re-running successes.
- Watermark prevents gap-filling from reprocessing already-completed dates.
- An external orchestrator is overkill for 24 tasks — the state machine is ~200 lines of Python.

### Consequences
- Pipeline execution is resumable — failed tickers can be reprocessed without re-running successes.
- Watermark prevents gap-filling from reprocessing already-completed dates.
- PipelineRun table grows ~50 rows/night — retention policy recommended (90 day archive).

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
| 009 | Prophet train-once-predict-many + convergence layer | 8.6+ | 2026-04-02 |
| 010 | Per-ticker calibrated drift detection (MAPE × 1.5) | 8.6+ | 2026-04-02 |
| 011 | Event-driven cache invalidation (hybrid TTL) | 8.6+ | 2026-04-02 |
| 012 | DB-driven LLM model cascade (not hardcoded) | 6 | 2026-04-03 |
| 013 | Three-tier Redis cache namespace with SCAN | 7 | 2026-04-03 |
| 014 | httpOnly cookies + dual-mode auth | 2 | 2026-04-03 |
| 015 | User-level token revocation (not per-token JTI) | C | 2026-04-03 |
| 016 | Soft-delete with 30-day grace period | C | 2026-04-03 |
| 017 | Tiered test pyramid — xdist only for unit tests | D | 2026-04-03 |
| 018 | Path-based CI routing (dorny/paths-filter) | D | 2026-04-03 |
| 019 | Three-level forecast hierarchy (stock → sector → portfolio) | 8.6+ | 2026-04-03 |
| 020 | Template-based rationale (LLM only for complex divergences) | 8.6+ | 2026-04-03 |
| 021 | Observability as bounded package (backend/observability/) | B.5 | 2026-04-03 |
| 022 | Redis-backed HTTP metrics (not in-memory counters) | B.5 | 2026-04-03 |
| 023 | Intraday refresh fast/slow path split | F | 2026-04-12 |
| 024 | Semaphore bound = DB pool size | F | 2026-04-12 |
| 025 | @tracked_task decorator for pipeline observability | E | 2026-04-07 |
| 026 | PipelineRunner state machine | E | 2026-04-07 |
