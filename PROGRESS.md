# Progress Log

Track what was built in each Claude Code session.
Full verbose history: `docs/superpowers/archive/progress-full-log.md`

---

## Project Timeline (compact)

### Phase 1 — Signal Engine + Database + API (Sessions 1-3)
**Tests:** 0 → 114 | FastAPI + SQLAlchemy async + Alembic + TimescaleDB + JWT auth. Signal engine (RSI, MACD, SMA, Bollinger, composite 0-10). Recommendation engine. 7 stock endpoints. Seed scripts.

### Phase 2 — Dashboard + Screener UI (Sessions 4-7)
**Tests:** 114 → 147 | httpOnly cookie auth, StockIndex model, on-demand ingest, bulk signals, signal history. Full Next.js frontend (login, dashboard, screener, stock detail).

### Phase 2.5 — Design System + UI Polish (Sessions 8-13)
**Tests:** 147 → 148 | **PR #1 merged.** Financial CSS vars, `useChartColors()`, Sparkline, SignalMeter, MetricCard, entry animations, Bloomberg dark mode.

### Phase 3 — Security + Portfolio (Sessions 14-22)
**Tests:** 148 → 218 | **PRs #2-4 merged.** JWT validation, rate limiting, CORS, Sharpe filter, Celery Beat refresh, portfolio FIFO engine, P&L, sector allocation, fundamentals (Piotroski F-Score), snapshots, dividends.

### Phase 3.5 — Advanced Portfolio (Sessions 23-25)
Divestment rules engine (4 rules), portfolio-aware recommendations, rebalancing suggestions (equal-weight).

### Phase 4 — AI Agent + UI Redesign (Sessions 26-44)
**PRs #5-50 merged.** Phase 4A: Navy command-center UI (25 tasks). Phase 4B: LangGraph agent + Plan→Execute→Synthesize. Phase 4C: NDJSON streaming chat UI (23 files). Phase 4D: ReAct loop + enriched data layer + 15 Stock columns. Phase 4E: Security (11 findings). Phase 4F: Full UI migration (9 stories). Phase 4G: Backend hardening (154 tests).

### Phase 5 — Forecasting + Alerts (Sessions 45-51)
**Tests → ~1258.** Prophet forecasting, nightly pipeline (9-step chain), recommendation evaluation, drift detection, in-app alerts, 6 new agent tools, MCP stdio tool server, Redis refresh token blocklist, 20 MCP integration tests.

### Phase 6 — LLM Factory + Observability (Sessions 53-55)
**PRs #95-99.** V1 deprecation, TokenBudget, llm_model_config, GroqProvider cascade, admin API, ObservabilityCollector DB writer, Playwright E2E specs. Phase 6C: test cleanup.

### Phase 7 — Backend Hardening + Tech Debt (Sessions 56-60)
**PRs #102-121.** Guardrails, data enrichment (beta/yield/PE), 4 new agent tools, pagination, cache, bcrypt migration, N+1 fixes, safe errors, ESLint cleanup. SaaS readiness audit (6.5/10 → 8/10). Service layer extraction.

### Phase 8 — Observability + ReAct Agent (Sessions 61-64)
**PRs #123-131.** Provider observability, cost_usd wiring, cache_hit logging, ReAct loop (3-phase StateGraph), intent classifier (8 intents), tool filtering, input validation.

### SaaS Launch Roadmap Phase A-B.5 (Sessions 67-79)
**PRs #138-157.** Phase A: TokenBudget → Redis. Phase B: Langfuse + eval framework + OIDC SSO + golden dataset. Phase B.5: 7 BUs — schema sync, alerts redesign, stock detail enrichment, dashboard 5-zone redesign, observability backend+frontend, Command Center (package extraction + instrumentation + 4 zone panels).

---

### Sessions 79-91 (archived → `docs/superpowers/archive/progress-full-log.md`)
**S79:** Command Center MVP (PRs #154-155, +122 tests). **S80:** Live testing, 5 bugs found, Phase 8.5 brainstorm. **S81:** Portfolio Analytics — pandas-ta-openbb, QuantStats, PyPortfolioOpt (PR #158, +38 tests). **S82:** Auth Overhaul — Google OAuth, email verification, account management (30 tickets, 13 endpoints, migration 023). **S83:** Test overhaul spec + JIRA Epic KAN-356. **S84:** Test Sprints 1-2, CI overhaul, 13 Semgrep rules, bug fixes (PRs #162-167). **S85:** Phase D Sprints 3-4 — Hypothesis property tests, golden datasets, auth+security tests, 185 new tests (PRs #169-170). **S86:** Playwright E2E (35 specs) + MSW integration (29 tests), PRs #172-173. **S87:** Phase 8.6+ Forecast Intelligence brainstorm + spec + plan + 19 JIRA tickets. **S88:** Spec A Backtesting Engine — 4 sprints, migration 024, BacktestEngine, CacheInvalidator, convergence classifiers, 3 ADRs (PR #177, +114 tests). **S89:** Specs D+B — Admin Pipeline Orchestrator + News Sentiment Pipeline (PRs #179-180, +274 tests, 13 CRITICALs fixed). **S90:** Spec C Convergence UX — BL, Monte Carlo, CVaR, 12 frontend components, 5-persona review (PR merged, +80 tests). **S91:** SESSION_INDEX regenerated, CLAUDE.md updated (PR #186).

---

## Session 92 — Workflow Optimization System (2026-04-04)

**Branch:** `feat/workflow-optimization` → develop | **PR #188 merged**

- 5 rules: 1-round review (R1), brainstorm routing by design complexity (R2), domain persona auto-select (R3), doc-delta tracking (R4), phase-end review dimensions (R5)
- 2 hooks: stale-state-check (H1), doc-delta-reminder (H2)
- 3 skills: `/sprint-closeout` (S1), `/phase-closeout` (S2), `/spec-plan` (S3)
- Updated `/ship` with ## Ships section + JIRA transition prompt

---

## Session 93 — LLM Benchmark Research (2026-04-04)

- Built tooling for local LLM evaluation (qwen2.5-coder:14b)
- Findings: model fails tool use — cannot call MCP tools reliably
- Documented in `docs/superpowers/specs/2026-04-04-llm-benchmark-session-93-findings.md`
- Resume: try larger models or different tool-use approach

---

## Session 94 — Bug Sweep + Tech Debt Clearout (2026-04-04)

**Branch:** `fix/security-bugs-314-316-317` → develop | **PR #189 merged**

### Security Bugs (KAN-314, KAN-316, KAN-317)
- KAN-314: Split `/health` into public (status+version) + `/health/detail` (auth required)
- KAN-316: Removed intent_category exception — analytics now user-scoped for all dimensions
- KAN-317: Replaced `str(e)` with `type(e).__name__` in executor logging

### Tech Debt (KAN-393, KAN-394, KAN-399)
- KAN-399 + KAN-394-M1: Replaced all 22 `date.today()` with `datetime.now(timezone.utc).date()` across 13 files
- KAN-394-M2: Ticker validation after BL price pivot
- KAN-394-M3: 5 `type:ignore[arg-type]` → explicit enum casts in convergence router
- KAN-394-M5/M6/M7: Error-state tests, LLM prompt inspection tests, convergence edge case
- KAN-393: AccuracyBadge + DrillDownSheet in ForecastCard, Prophet breakdown in rationale, axe-core a11y checks

### Remaining Bugs (KAN-320, KAN-321, KAN-322, KAN-315)
- KAN-320: Intelligence endpoint 500 on cold start — `asyncio.gather(return_exceptions=True)` + per-tool fault isolation
- KAN-321: Chat tool args char-by-char display — parse JSON string before `Object.entries()`
- KAN-322: 63 stocks missing sector — `seed_portfolio.py` now fetches sector from yfinance + `--backfill-sectors`
- KAN-315: `duration_ms` now includes LLM + tool latency (was tool-only)

### Process Improvement
- Rewrote `.claude/rules/review-config.md` with scoring-based review routing (skip ≤6 / quick 7-10 / full 11+)
- Change-type → persona mapping (11 categories, prioritized reviewers)

### Session 94 Totals
- 1 PR merged (#189), 41 files changed, +1361 lines
- Tests: 1860 backend + 439 frontend + 38 API = ~2337 total
- 10 JIRA tickets resolved — **zero open bugs/tech debt remaining**
- All 11 Sonnet agents ran in parallel (3 batches), Opus orchestrated + reviewed
- Resume: Phase E (UI Overhaul, KAN-400) or Phase F (Subscriptions + Monetization)

---

## Session 95 — Full Data Reseed + DQ Analysis (2026-04-04)

**Branch:** `fix/news-pipeline-hotfixes-kan-401-402` → develop

### Reseed Execution
Full database reseed (preserving portfolio/user/watchlist) to validate backend with real data:
- Stock universe: 580 stocks (S&P 500 + NASDAQ-100 + Dow 30 + 12 ETFs)
- Stock prices: 1,241,547 rows (10y history for 505 tickers + 2y ETFs)
- Signals: 505 snapshots computed inline during price seed
- Forecasts: 1,548 results (516 tickers × 3 horizons), 516 Prophet models trained
- Dividends: 52,137 rows (472 tickers)
- Earnings: 2,225 snapshots (558 tickers)
- News: 1,985 articles (4 providers: Finnhub, Google News, EDGAR, Fed RSS)
- Sentiment: 394 articles scored via GPT-4o-mini, 4 daily sentiment rows

### Bugs Found (3 pipeline bugs + 1 DQ critical)
- **KAN-401** (High): NewsArticle tz mismatch — tz-aware datetimes vs naive columns. Hotfix applied.
- **KAN-402** (Medium): Google News RSS source_url > VARCHAR(500). Hotfix applied.
- **KAN-403** (High): Prophet predicts negative stock prices for 6 tickers (FISV, HUM, ELV, SMCI, IT, CSGP)
- **KAN-404** (High): seed_prices --universe misses 61 portfolio/watchlist tickers not in indexes

### DQ Analysis
- Stock prices: 0 nulls, 0 non-positive, 0 negative volume — clean
- Signals: RSI [0,100], composite [0,10], 0 Bollinger violations — clean
- Forecasts: 10 negative predicted prices — **KAN-403**
- 61 positions without price/signal/forecast data — **KAN-404**
- Score distribution: 405 AVOID, 100 WATCH, 0 BUY — market conditions
- No orphan records, no duplicate signals, no duplicate news

### Enhancements Filed
- **KAN-405** (Medium): Sentiment scoring concurrent batching (9 min → 30 sec)
- **KAN-406** (Low): SPY ETF 2y history misaligned with 10y universe

### Session 95 Totals
- 6 JIRA tickets created (KAN-401–406): 4 bugs, 2 enhancements
- 2 hotfixes applied (ingestion.py, news_sentiment.py)
- No new tests (DQ suite recommended as future work)
- Resume: Fix KAN-401–404 properly, then Phase E or Phase F

---

## Session 96 — Pipeline Integrity + Skills Audit (2026-04-05)

**Branch:** `fix/KAN-403-404-pipeline-integrity` → develop | **PR #192**

### KAN-403: Prophet Negative Price Floor
- Scale-appropriate floor: `max(0.01, last_price * 0.01)` in `predict_forecast()`
- `Field(ge=0.01)` validation on `ForecastHorizon` schema
- Warning logged with ticker, horizon, raw values when flooring applied

### KAN-404: Pipeline Integrity — 6 Fixes for Non-Universe Tickers
- **Canonical ticker universe** (`backend/services/ticker_universe.py`): single UNION query (index + watchlist + portfolio)
- **Nightly forecast trains new tickers**: dispatch `retrain_single_ticker_task` for up to 20/night with ≥200 data points
- **Chat auto-ingest**: `analyze_stock` tool does lightweight ingest (ensure_stock + price fetch) instead of erroring
- **Portfolio auto-ingest**: `ensure_stock_exists` before transaction, ticker format validation
- **No silent skip**: `missing_tickers` field in `PortfolioForecastResponse`, weight denominator fix
- **On-ingest forecast dispatch**: fire-and-forget `retrain_single_ticker_task.delay()` for new tickers only

### 5-Persona Review Findings Fixed
- Ticker case mismatch (`body.ticker` → `ticker_upper`)
- `Field(gt=0)` → `Field(ge=0.01)` (prevents 500s on stale data)
- N+1 `_get_price_data_count` → batch GROUP BY query
- Cap logic: count dispatched, not considered
- Weak tests rewritten (portfolio autoingest, forecast missing)
- Fire-and-forget exception tests added

### Skills/Rules Audit & Refactoring
- Converted `review-config.md` rule → `reviewing-code` skill (~900 tokens saved per interaction)
- Deleted `phase-end-review.md` + `workflow-optimization.md` rules (~600 tokens saved)
- Renamed `implement-ollama` → `implement-local`, `lmstudio-triage` → `local-llm-triage`
- Fixed CLAUDE.md ↔ doc-delta.md contradiction (batch-at-phase-end is canonical)
- Brainstorm routing cut from ~300 → ~120 tokens
- Added mandatory fix-verification step + Test Engineer persona to review workflow

### Session 96 Totals
- 1 PR (#192), 14 commits, 20+ files changed
- Tests: 1906 unit (46 new), 0 failures
- 2 JIRA tickets resolved (KAN-403, KAN-404)
- Skills/rules: ~1,500 tokens/interaction saved, 3 rules deleted/converted, 2 renamed
- Resume: Phase E (UI Overhaul, KAN-400) or Phase F (Subscriptions + Monetization)
