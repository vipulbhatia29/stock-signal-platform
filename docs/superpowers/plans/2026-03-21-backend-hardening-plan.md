# Phase 4G: Backend Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add ~211 hardening tests, restructure test directories, build an LLM-as-Judge eval pyramid, and install pre-commit hooks with agent-aware gating.

**Architecture:** TDD approach — write failing tests, implement minimal fixes where needed, commit per story. Stories are independent after S0 (directory restructure), so S1-S9 can be parallelized. S10 (pre-commit hooks) depends on all test stories.

**Tech Stack:** pytest, pytest-asyncio, factory-boy, freezegun, httpx, AsyncMock, tiktoken, pre-commit, ruff

**Spec:** `docs/superpowers/specs/2026-03-21-backend-hardening-design.md`
**Branch:** `feat/backend-hardening-spec` (continue on this branch)
**JIRA Epic:** KAN-73

---

## Chunk 1: Directory Restructure (S0 — KAN-74)

### Task 1: Create subdirectory structure

**Files:**
- Create: `tests/unit/signals/__init__.py`
- Create: `tests/unit/recommendations/__init__.py`
- Create: `tests/unit/tools/__init__.py`
- Create: `tests/unit/agents/__init__.py`
- Create: `tests/unit/auth/__init__.py`
- Create: `tests/unit/chat/__init__.py`
- Create: `tests/unit/portfolio/__init__.py`
- Create: `tests/unit/pipeline/__init__.py`
- Create: `tests/unit/infra/__init__.py`
- Create: `tests/unit/adversarial/__init__.py`
- Create: `tests/e2e/__init__.py`
- Create: `tests/e2e/conftest.py`
- Create: `tests/e2e/eval/__init__.py`
- Create: `tests/e2e/eval/results/.gitkeep`
- Create: `tests/markers.py`

- [ ] **Step 1: Create all subdirectories with `__init__.py` files**

```bash
mkdir -p tests/unit/{signals,recommendations,tools,agents,auth,chat,portfolio,pipeline,infra,adversarial}
mkdir -p tests/e2e/eval/results
for dir in tests/unit/{signals,recommendations,tools,agents,auth,chat,portfolio,pipeline,infra,adversarial} tests/e2e tests/e2e/eval; do
  touch "$dir/__init__.py"
done
touch tests/e2e/eval/results/.gitkeep
```

- [ ] **Step 2: Create pytest markers file**

Create `tests/markers.py`:
```python
"""Custom pytest markers for test gating."""
import pytest

pre_commit = pytest.mark.pre_commit
ci_only = pytest.mark.ci_only
agent_gated = pytest.mark.agent_gated
```

- [ ] **Step 3: Register markers in `pyproject.toml`**

Add to `[tool.pytest.ini_options]`:
```toml
markers = [
    "pre_commit: fast tests for pre-commit hook",
    "ci_only: tests that only run in CI pipeline",
    "agent_gated: tests gated by agent/tool code changes",
]
```

- [ ] **Step 4: Add eval results to `.gitignore`**

Append to root `.gitignore`:
```
tests/e2e/eval/results/*.json
```

- [ ] **Step 5: Create `tests/e2e/conftest.py`**

```python
"""E2E test fixtures — real user, portfolio, LLM key gating."""
import os
import pytest

def pytest_collection_modifyitems(config, items):
    """Skip e2e tests if no LLM API key is available."""
    if not os.environ.get("GROQ_API_KEY") and not os.environ.get("ANTHROPIC_API_KEY"):
        skip_marker = pytest.mark.skip(reason="No LLM API key — skipping e2e tests")
        for item in items:
            item.add_marker(skip_marker)
```

---

### Task 2: Move existing test files into subdirectories

**Files:**
- Move: 36 files from `tests/unit/` → domain subdirectories

- [ ] **Step 1: Move signal tests**

```bash
mv tests/unit/test_signals.py tests/unit/signals/
```

- [ ] **Step 2: Move recommendation tests**

```bash
mv tests/unit/test_recommendations.py tests/unit/recommendations/
```

- [ ] **Step 3: Move tool tests**

```bash
mv tests/unit/test_tool_base.py tests/unit/tools/
mv tests/unit/test_tool_registry.py tests/unit/tools/
mv tests/unit/test_internal_tools.py tests/unit/tools/
mv tests/unit/test_fundamentals.py tests/unit/tools/
mv tests/unit/test_fundamentals_tool.py tests/unit/tools/
mv tests/unit/test_analyst_targets.py tests/unit/tools/
mv tests/unit/test_earnings_history.py tests/unit/tools/
mv tests/unit/test_company_profile.py tests/unit/tools/
mv tests/unit/test_dividends.py tests/unit/tools/
mv tests/unit/test_yahoo_search.py tests/unit/tools/
```

- [ ] **Step 4: Move agent tests**

```bash
mv tests/unit/test_agents.py tests/unit/agents/
mv tests/unit/test_agent_graph.py tests/unit/agents/
mv tests/unit/test_planner.py tests/unit/agents/
mv tests/unit/test_executor.py tests/unit/agents/
mv tests/unit/test_synthesizer.py tests/unit/agents/
mv tests/unit/test_llm_client.py tests/unit/agents/
mv tests/unit/test_simple_formatter.py tests/unit/agents/
mv tests/unit/test_result_validator.py tests/unit/agents/
mv tests/unit/test_stream_events.py tests/unit/agents/
mv tests/unit/test_stream_v2.py tests/unit/agents/
```

- [ ] **Step 5: Move auth tests**

```bash
mv tests/unit/test_dependencies.py tests/unit/auth/
```

- [ ] **Step 6: Move chat tests**

```bash
mv tests/unit/test_chat_schemas.py tests/unit/chat/
mv tests/unit/test_chat_models.py tests/unit/chat/
mv tests/unit/test_session_management.py tests/unit/chat/
```

- [ ] **Step 7: Move portfolio tests**

```bash
mv tests/unit/test_portfolio.py tests/unit/portfolio/
mv tests/unit/test_divestment.py tests/unit/portfolio/
```

- [ ] **Step 8: Move pipeline tests**

```bash
mv tests/unit/test_seed_prices.py tests/unit/pipeline/
mv tests/unit/test_sync_sp500.py tests/unit/pipeline/
mv tests/unit/test_warm_data.py tests/unit/pipeline/
```

- [ ] **Step 9: Move infra tests**

```bash
mv tests/unit/test_health.py tests/unit/infra/
mv tests/unit/test_tasks.py tests/unit/infra/
mv tests/unit/test_mcp_server.py tests/unit/infra/
mv tests/unit/test_mcp_adapters.py tests/unit/infra/
mv tests/unit/test_user_context.py tests/unit/infra/
```

- [ ] **Step 10: Verify all existing tests still pass**

```bash
uv run pytest tests/unit/ -v --tb=short
uv run pytest tests/api/ -v --tb=short
```
Expected: All 340 unit + 132 API tests pass. If any fail due to import path changes, fix the imports.

- [ ] **Step 11: Commit**

```bash
git add tests/ pyproject.toml .gitignore
git commit -m "refactor(KAN-74): restructure test directories — flat to domain-organized

Move 36 unit test files into domain subdirectories: signals/, recommendations/,
tools/, agents/, auth/, chat/, portfolio/, pipeline/, infra/. Create tests/e2e/
with eval/ subfolder. Add pytest markers (pre_commit, ci_only, agent_gated).

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Chunk 2: Auth & Security (S1 — KAN-75)

### Task 3: Auth hardening tests

**Files:**
- Create: `tests/api/test_auth_hardening.py`
- Reference: `backend/dependencies.py` (JWT validation)
- Reference: `backend/routers/auth.py` (login/register)
- Reference: `backend/routers/portfolio.py` (IDOR target)
- Reference: `backend/routers/chat.py` (IDOR target)

- [ ] **Step 1: Write token expiry + malformed JWT tests (tests 1-4)**

Tests: Token rejected after 15min (freezegun), refresh rejected after 7 days, refresh reuse blocked, malformed JWT payloads (missing sub, missing type, wrong algorithm) → 401.

Use `freezegun` for time-based tests. Create tokens with `create_access_token()` from `backend/dependencies.py`.

- [ ] **Step 2: Write cross-user IDOR tests (tests 5-8)**

Create two users (UserFactory × 2) with separate authenticated clients. User A calls User B's portfolio, chat sessions, watchlist, preferences → assert 404 or 403 (not 200 with User B's data).

Key endpoints to test:
- `GET /api/v1/portfolio/positions` (user_a_client with user_b's portfolio)
- `GET /api/v1/chat/sessions/{user_b_session_id}/messages`
- `GET /api/v1/stocks/watchlist` (each user sees only their own)
- `GET /api/v1/preferences` (each user sees only their own)

- [ ] **Step 3: Write rate limiting + cookie + password + injection tests (tests 9-15)**

- Rate limit: 6 login attempts in loop → 429 on 6th
- Cookie flags: Login response has `Set-Cookie` with `HttpOnly`, `SameSite=Lax`
- Password: Register with "short", "nouppercase1", "NODIGIT" → all 422
- Inactive: Set `user.is_active = False` → 401 on `GET /stocks/watchlist`
- SQL injection: `GET /stocks/search?q='; DROP TABLE stocks;--` → safe (no 500)
- XSS: POST transaction with `notes="<script>alert(1)</script>"` → GET returns escaped

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/api/test_auth_hardening.py -v
```
Expected: All 15 tests pass. If any IDOR test fails → log as Bug (Critical).

- [ ] **Step 5: Commit**

```bash
git add tests/api/test_auth_hardening.py
git commit -m "test(KAN-75): auth & security hardening — 15 tests

IDOR regression (portfolio, chat, watchlist, preferences), token expiry,
malformed JWT, rate limiting, cookie flags, password strength, SQL injection,
XSS sanitization.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Chunk 3: Data Pipeline + Signals (S2 + S3 — KAN-76, KAN-77)

### Task 4: Ingest pipeline tests (S2)

**Files:**
- Create: `tests/api/test_ingest_pipeline.py`
- Create: `tests/unit/pipeline/test_seed_pipeline.py`
- Reference: `backend/routers/stocks.py` (ingest endpoint)
- Reference: `backend/tools/market_data.py` (price fetching)
- Reference: `backend/tools/signals.py` (signal computation)

- [ ] **Step 1: Write API-level ingest tests (tests 1-9, 12-14)**

Mock `yfinance` at the tool level. Test full pipeline: POST ingest → verify Stock, StockPrice, SignalSnapshot, EarningsSnapshot rows created. Test delta refresh (last_fetched_at check). Test invalid ticker → 422. Test empty yfinance response → graceful error.

- [ ] **Step 2: Write unit-level pipeline tests (tests 10-11, 15)**

Test `sync_sp500()` with mocked Wikipedia response. Test `warm_data()` with mocked Redis. Test partial failure: mock signals to raise, verify prices still persisted.

- [ ] **Step 3: Run and commit**

```bash
uv run pytest tests/api/test_ingest_pipeline.py tests/unit/pipeline/test_seed_pipeline.py -v
git add tests/api/test_ingest_pipeline.py tests/unit/pipeline/test_seed_pipeline.py
git commit -m "test(KAN-76): ingest & data pipeline hardening — 15 tests

Full ingest (new + delta), stale detection, idempotency, fundamentals
materialization, earnings persistence, S&P 500 seed, warm cache,
partial failure rollback.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

### Task 5: Signal & recommendation engine tests (S3)

**Files:**
- Create: `tests/unit/signals/test_signal_engine_hardening.py`
- Create: `tests/unit/recommendations/test_recommendation_hardening.py`
- Reference: `backend/tools/signals.py` (compute_signals)
- Reference: `backend/tools/recommendations.py` (generate_recommendation)

- [ ] **Step 1: Write signal edge case tests (tests 1-7, 13)**

Generate synthetic price data using `_make_price_series()` helper. Test: composite always [0,10], Piotroski blending (50/50), single data point → baseline 2.5, insufficient history → SMA200 None but composite works, all-bullish → near 10, all-bearish → near 0, staleness badge.

- [ ] **Step 2: Write recommendation hardening tests (tests 8-12, 14)**

Use factories to create portfolio state. Test: portfolio-aware BUY respects max_position_pct, concentration cap at 5% → HOLD, sector cap at 30% → WATCH, stop-loss >20% → SELL, empty portfolio → no crash, custom composite weights.

- [ ] **Step 3: Run and commit**

```bash
uv run pytest tests/unit/signals/test_signal_engine_hardening.py tests/unit/recommendations/test_recommendation_hardening.py -v
git add tests/unit/signals/ tests/unit/recommendations/
git commit -m "test(KAN-77): signal & recommendation engine hardening — 14 tests

Composite score range, Piotroski blending, edge cases (single data point,
insufficient history, all bullish/bearish), portfolio-aware recommendations
(concentration, sector cap, stop-loss, empty portfolio).

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Chunk 4: Agent V2 Regression + Adversarial (S4 — KAN-78)

### Task 6: Agent V2 mocked regression tests (S4a + S4b)

**Files:**
- Create: `tests/unit/agents/test_agent_v2_regression.py`
- Reference: `backend/agents/planner.py` (plan_query, parse_plan_response)
- Reference: `backend/agents/executor.py` (execute_plan)
- Reference: `backend/agents/synthesizer.py` (synthesize_results)
- Reference: `backend/tools/chat_session.py` (build_context_window)

- [ ] **Step 1: Write intent classification tests (S4a tests 1-15)**

Mock `llm_chat` to return canned JSON plan responses. For each prompt, verify the parsed plan has correct `intent` field. For tool planning tests (9-15), verify `steps` array contains expected tool names.

Key pattern:
```python
async def test_intent_stock_analysis():
    mock_llm = AsyncMock(return_value=LLMResponse(
        content='{"intent": "stock_analysis", "steps": [{"tool": "analyze_stock", "params": {"ticker": "AAPL"}}], "reasoning": "..."}'
    ))
    plan = await plan_query("Analyze AAPL", TOOLS_DESC, USER_CONTEXT, mock_llm)
    assert plan["intent"] == "stock_analysis"
```

- [ ] **Step 2: Write executor & synthesizer tests (S4b tests 1-15)**

Test `$PREV_RESULT` resolution, retry logic, circuit breaker (3 failures → stop), max 8 tool calls, confidence score range, scenarios present, evidence citations, decline message, event ordering.

Mock tool executor to return controlled results. For circuit breaker: make mock fail 3 times consecutively.

- [ ] **Step 3: Write context-aware tests (S4b tests 16-20)**

Test `build_context_window()`: 50-message history → output ≤ 16K tokens, recent messages preserved, oldest dropped. Test multi-turn comparison: history with AAPL + MSFT → "Compare them" → plan includes both tickers. Test ambiguous "compare" with no history → clarification or decline.

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/unit/agents/test_agent_v2_regression.py -v
```
Expected: All 35 tests pass.

### Task 7: Adversarial & guardrail tests (S4c)

**Files:**
- Create: `tests/unit/adversarial/test_agent_adversarial.py`
- Reference: `backend/agents/planner.py`
- Reference: `backend/agents/graph_v2.py`

- [ ] **Step 1: Write adversarial tests (10 tests)**

Mock LLM responses. Test: prompt injection → decline (no system prompt in response), goal hijacking → decline, specific financial advice → includes disclaimer, fake ticker → "not found", excessive scope → max 8 tools, SQL via agent → ORM safe, cross-user data → only authenticated user's data, multi-turn drift → T2 declined, numerical gaslighting → real DB data used, prompt leak via tool error → no fragments.

- [ ] **Step 2: Run and commit all S4**

```bash
uv run pytest tests/unit/agents/test_agent_v2_regression.py tests/unit/adversarial/test_agent_adversarial.py -v
git add tests/unit/agents/test_agent_v2_regression.py tests/unit/adversarial/
git commit -m "test(KAN-78): agent V2 mocked regression + adversarial — 45 tests

S4a: intent classification (15 prompts), tool plan validation.
S4b: executor ($PREV_RESULT, retry, circuit breaker), synthesizer
(confidence, scenarios, evidence), context window (size, recency,
multi-turn comparison, pronoun resolution).
S4c: adversarial guardrails (prompt injection, goal hijacking, SQL,
cross-user data, numerical gaslighting).

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Chunk 5: Search + Celery + Tools + API Contracts (S6, S7, S8, S9 — KAN-80, 81, 82, 83)

### Task 8: Stock search → ingest flow (S6)

**Files:**
- Create: `tests/api/test_search_flow.py`
- Reference: `backend/routers/stocks.py` (search endpoint, ingest endpoint)

- [ ] **Step 1: Write search flow tests (10 tests)**

Insert a Stock via factory (e.g., AAPL). Test: search q=AAPL → DB hit; search q=App → prefix match; mock Yahoo for miss→fallback; q=XYZNOTREAL → empty; q="" → 422; q=`<script>` → safe; search→ingest→re-search full flow (3 tests covering stock created, signals available, fundamentals materialized).

- [ ] **Step 2: Run and commit**

```bash
uv run pytest tests/api/test_search_flow.py -v
git add tests/api/test_search_flow.py
git commit -m "test(KAN-80): stock search → ingest flow — 10 tests

DB hit, partial match, Yahoo fallback, empty/XSS inputs, full
search→ingest→re-search cycle with signals and fundamentals.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

### Task 9: Celery & background jobs (S7)

**Files:**
- Create: `tests/unit/infra/test_celery_hardening.py`
- Create: `tests/api/test_celery_hardening.py`
- Reference: `backend/tasks/__init__.py` (beat schedule)
- Reference: `backend/tasks/market_data.py` (refresh tasks)
- Reference: `backend/tasks/portfolio.py` (snapshot tasks)

- [ ] **Step 1: Write unit-level Celery tests (tests 1-5, 12, 15)**

Mock yfinance + DB. Test refresh_ticker happy path, retry on failure (mock to fail then succeed), fan-out (mock delay and verify 3 tasks dispatched), empty watchlist, beat schedule verification (inspect `app.conf.beat_schedule`), asyncio.run() bridge.

- [ ] **Step 2: Write API-level Celery tests (tests 6-8, 13-14)**

Test snapshot creation, empty portfolio snapshot, task status endpoint lifecycle (mock Celery AsyncResult), task failure sanitized error.

- [ ] **Step 3: Run and commit**

```bash
uv run pytest tests/unit/infra/test_celery_hardening.py tests/api/test_celery_hardening.py -v
git add tests/unit/infra/test_celery_hardening.py tests/api/test_celery_hardening.py
git commit -m "test(KAN-81): Celery & background jobs hardening — 15 tests

refresh_ticker (happy, retry), fan-out, snapshots (happy, empty,
idempotency), beat schedule verification, task status endpoint,
asyncio.run() bridge.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

### Task 10: Tool & MCP coverage (S8)

**Files:**
- Create: `tests/unit/tools/test_tool_hardening.py`
- Create: `tests/unit/infra/test_mcp_hardening.py`
- Reference: `backend/tools/*.py` (all tool classes)
- Reference: `backend/mcp_server/server.py`
- Reference: `backend/mcp_server/auth.py`
- Reference: `backend/tools/adapters/*.py` (4 adapters)

- [ ] **Step 1: Write internal tool tests (19 tests)**

For each of the 8 untested tools: mock external dependencies (DB, APIs), test happy path, error handling, result format. Each tool must return `ToolResult(status, data, error)` — never raise exceptions.

- [ ] **Step 2: Write MCP adapter tests (12 tests)**

For each adapter (Edgar, AlphaVantage, Fred, Finnhub): mock HTTP responses, test happy path, error case (invalid input), error sanitization (no raw API error in response).

- [ ] **Step 3: Write MCP server + cross-cutting tests (8 tests)**

MCP auth: valid JWT → 200, no token → 401, expired → 401. Tool listing: all 13 tools in response. Cross-cutting: ToolResult format for every tool, error sanitization check, JSON Schema validation for every tool's `args_schema`.

- [ ] **Step 4: Run and commit**

```bash
uv run pytest tests/unit/tools/test_tool_hardening.py tests/unit/infra/test_mcp_hardening.py -v
git add tests/unit/tools/test_tool_hardening.py tests/unit/infra/test_mcp_hardening.py
git commit -m "test(KAN-82): tool & MCP coverage — 39 tests

Internal tools (8 tools × happy/error/schema), MCP adapters
(4 adapters × happy/error/sanitization), MCP server auth (3 tests),
cross-cutting (ToolResult format, error sanitization, schema validation).

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

### Task 11: API contract hardening (S9)

**Files:**
- Create: `tests/api/test_api_contracts.py`
- Reference: All routers in `backend/routers/`

- [ ] **Step 1: Write schema validation tests (7 tests)**

For each endpoint: call it with valid auth + data, assert every expected field is present in the response JSON. Use factories to seed required data.

- [ ] **Step 2: Write pagination + status code tests (14 tests)**

Pagination edge cases: page=0, -1, 99999, per_page=1000, no matches, ticker filter. HTTP status codes: 401 no token, 404 unknown ticker/transaction, 409 duplicate watchlist, 422 invalid/FIFO/full, 429 rate limit.

- [ ] **Step 3: Write header + resource cleanup tests (8 tests)**

Content-Type checks, CORS preflight, no server version leak. Resource cleanup: DB connection pool unchanged after 10 requests, ContextVar reset, stream buffer cleanup, Celery event loop cleanup.

- [ ] **Step 4: Run and commit**

```bash
uv run pytest tests/api/test_api_contracts.py -v
git add tests/api/test_api_contracts.py
git commit -m "test(KAN-83): API contract hardening — 29 tests

Response schemas (7 endpoints), pagination edge cases (6), HTTP
status codes (8), headers (4), resource cleanup (4).

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Chunk 6: Live LLM Eval Pyramid (S5 — KAN-79)

### Task 12: Build eval infrastructure

**Files:**
- Create: `tests/e2e/eval/rubric.py`
- Create: `tests/e2e/eval/judge.py`
- Create: `tests/e2e/eval/golden_set.yaml`

- [ ] **Step 1: Write eval rubric**

Define 8 dimensions with scoring criteria (1-5 scale), financial domain context, and fail thresholds. The rubric is a prompt template string that gets sent to the judge LLM.

- [ ] **Step 2: Write judge caller**

`judge.py`: async function that calls Haiku with `{prompt, agent_response, tool_results, rubric}`, parses structured JSON scores. Skips gracefully if no `ANTHROPIC_API_KEY`.

- [ ] **Step 3: Write golden set**

`golden_set.yaml`: 13 prompts with expected tool usage, per-dimension eval criteria, and structural assertions.

- [ ] **Step 4: Commit eval infrastructure**

```bash
git add tests/e2e/eval/
git commit -m "feat(KAN-79): eval infrastructure — rubric, judge, golden set

8 eval dimensions (7 scored 1-5 + 1 binary hallucination check):
factual grounding, hallucination, actionability, risk disclosure,
evidence quality, scope compliance, personalization, context relevance.
Haiku judge with graceful degradation. 13-prompt golden set.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

### Task 13: Write live LLM structural tests

**Files:**
- Create: `tests/e2e/test_agent_v2_live.py`
- Reference: `backend/agents/graph_v2.py`
- Reference: `backend/main.py` (app startup, graph building)

- [ ] **Step 1: Write 13 structural validation tests**

Each test sends a real prompt through the agent graph, validates response structure (not content). Uses real LLM (Groq primary). 60s timeout per test. Create test user + portfolio via factories.

Tests: analyze AAPL, unknown ticker→ingest, portfolio query, simple lookup (fast), out-of-scope decline, single-turn comparison, multi-turn comparison, dividend question, risk assessment, stale refresh, deep dive (≥3 tools), low confidence (recent IPO), prompt injection.

Each test also verifies observability assertions: `LLMCallLog` row exists with `token_count > 0` and `cost > 0`, `ToolExecutionLog` rows exist for each tool call, latency bounds (plan < 15s, execute < 30s, synthesize < 15s).

- [ ] **Step 2: Run structural tests**

```bash
uv run pytest tests/e2e/test_agent_v2_live.py -v --timeout=120
```
Expected: All 13 pass (requires `GROQ_API_KEY` in `.env`). If any fail → triage per spec.

### Task 14: Write LLM-as-Judge quality eval tests

**Files:**
- Create: `tests/e2e/test_agent_v2_eval.py`
- Create: `tests/e2e/eval/baseline.json` (auto-generated on first run)

- [ ] **Step 1: Write 13 quality eval tests**

Each test: run the agent prompt, capture response + tool results, call judge with rubric, assert all 8 dimensions above threshold. Save results to `tests/e2e/eval/results/`. On first run, save as baseline. On subsequent runs, detect drift > 0.5.

- [ ] **Step 2: Run eval tests and establish baseline**

```bash
uv run pytest tests/e2e/test_agent_v2_eval.py -v --timeout=180
```
Expected: All pass, baseline.json created. Review scores manually.

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/test_agent_v2_live.py tests/e2e/test_agent_v2_eval.py tests/e2e/eval/baseline.json
git commit -m "test(KAN-79): agent V2 live LLM + eval pyramid — 26 tests

13 structural tests (real LLM, response shape validation).
13 quality evals (LLM-as-Judge, 8 dimensions, drift detection).
Baseline established.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Chunk 7: Pre-commit Hooks + CI (S10 — KAN-84)

### Task 15: Create pre-commit config and agent gate

**Files:**
- Create: `.pre-commit-config.yaml`
- Create: `scripts/pre-commit-agent-gate.sh`
- Modify: `.github/workflows/` (add ci-eval.yml)

- [ ] **Step 1: Write agent gate script**

`scripts/pre-commit-agent-gate.sh`: Check `git diff --cached --name-only` for `backend/agents/` or `backend/tools/`. If no changes → skip. If no LLM key → warn and skip. If both → run `uv run pytest tests/e2e/ -v --timeout=120`.

```bash
chmod +x scripts/pre-commit-agent-gate.sh
```

- [ ] **Step 2: Write `.pre-commit-config.yaml`**

7-stage pipeline: ruff check, ruff format, frontend lint, unit tests (pre_commit marker), agent gate, eval gate, no-secrets check.

- [ ] **Step 3: Install pre-commit hooks**

```bash
uv add --dev pre-commit
uv run pre-commit install
```

- [ ] **Step 4: Write `ci-eval.yml` workflow**

Path-filtered on `backend/agents/**` and `backend/tools/**` + weekly cron + manual dispatch. Uses `CI_GROQ_API_KEY` and optionally `CI_ANTHROPIC_API_KEY` from GitHub Secrets.

- [ ] **Step 5: Test pre-commit locally**

```bash
uv run pre-commit run --all-files
```
Expected: All hooks pass (ruff, format, lint, unit tests).

- [ ] **Step 6: Commit**

```bash
git add .pre-commit-config.yaml scripts/pre-commit-agent-gate.sh .github/workflows/ci-eval.yml pyproject.toml uv.lock
git commit -m "feat(KAN-84): pre-commit hooks + ci-eval workflow

7-stage pre-commit: ruff check, ruff format, frontend lint, unit tests
(pre_commit marker), agent gate (conditional), eval gate (conditional),
no-secrets check. ci-eval.yml: path-filtered PRs + weekly cron.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Chunk 8: Finalize — Docs, Memories, Triage

### Task 16: Update documentation and memories

**Files:**
- Modify: `PROGRESS.md`
- Modify: `project-plan.md` (mark stories complete)
- Update: Serena memories (`project/state`, `project/testing`, `serena/memory-map`, `architecture/cicd-pipeline`)

- [ ] **Step 1: Update `PROGRESS.md` with session entry**

Log: all stories completed, test counts, bugs found, backlog items identified, JIRA tickets created.

- [ ] **Step 2: Mark stories complete in `project-plan.md`**

Change `- [ ]` to `- [x]` for each completed story (S0-S10).

- [ ] **Step 3: Update Serena memories**

- `project/state`: test count, Phase 4G status, pre-commit hooks active
- `project/testing`: new directory structure, markers, run commands, eval pyramid
- `serena/memory-map`: add tests/e2e/ and eval/
- `architecture/cicd-pipeline`: ci-eval.yml, pre-commit hooks

- [ ] **Step 4: Create JIRA tickets for known backlog items + test-discovered issues**

Pre-create 7 known backlog items from spec Section 8 as JIRA Stories under Phase 5 Epic:
1. Session entity registry (pronoun resolution, lazy re-fetch)
2. Stock comparison tool (structured side-by-side)
3. Context-aware planner prompt (recently_discussed_tickers)
4. Dividend sustainability tool
5. Risk narrative tool
6. Red flag scanner
7. Tax-loss harvesting (out of scope — create as Won't Do)

For each test failure discovered during implementation: classify as Bug or Backlog per spec Section 4 triage rules. Create JIRA tickets under appropriate Epic.

- [ ] **Step 5: Final commit and push**

```bash
git add PROGRESS.md project-plan.md
git commit -m "docs(KAN-73): Phase 4G complete — PROGRESS + project-plan updated

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
git push
```

---

## Execution Order & Dependencies

```
Chunk 1 (S0) ──────────────────────────── MUST BE FIRST
    │
    ├── Chunk 2 (S1) ─────────────┐
    ├── Chunk 3 (S2 + S3) ────────┤
    ├── Chunk 4 (S4) ─────────────┤── All independent, parallelizable
    ├── Chunk 5 (S6-S9) ──────────┤
    └── Chunk 6 (S5) ─────────────┘
                                   │
                              Chunk 7 (S10) ── Depends on all test stories
                                   │
                              Chunk 8 (Docs) ── Last
```

## Session Estimate

| Session | Chunks | Estimated Time |
|---------|--------|----------------|
| Session 40 | Chunk 1 (S0) + Chunk 2 (S1) + Chunk 3 (S2+S3) | ~3h |
| Session 41 | Chunk 4 (S4) + Chunk 5 (S6-S9) | ~4h |
| Session 42 | Chunk 6 (S5) + Chunk 7 (S10) + Chunk 8 (Docs) | ~3h |

## Verification Checklist

After all chunks are complete:

```bash
# All existing tests still pass
uv run pytest tests/unit/ tests/api/ tests/integration/ -v

# New hardening tests pass
uv run pytest tests/unit/ tests/api/ -v -k "hardening or adversarial or pipeline or search_flow or celery or contracts"

# E2E tests pass (requires LLM keys)
uv run pytest tests/e2e/ -v --timeout=180

# Pre-commit hooks work
uv run pre-commit run --all-files

# Total test count
uv run pytest tests/ --co -q | tail -1
# Expected: ~757 tests (546 existing + 211 new)
```
