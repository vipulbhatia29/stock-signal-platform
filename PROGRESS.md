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

### Sessions 79-87 (archived → `docs/superpowers/archive/progress-full-log.md`)
**S79:** Command Center MVP (PRs #154-155, +122 tests). **S80:** Live testing, 5 bugs found, Phase 8.5 brainstorm. **S81:** Portfolio Analytics — pandas-ta-openbb, QuantStats, PyPortfolioOpt (PR #158, +38 tests). **S82:** Auth Overhaul — Google OAuth, email verification, account management (30 tickets, 13 endpoints, migration 023). **S83:** Test overhaul spec + JIRA Epic KAN-356. **S84:** Test Sprints 1-2, CI overhaul, 13 Semgrep rules, bug fixes (PRs #162-167). **S85:** Phase D Sprints 3-4 — Hypothesis property tests, golden datasets, auth+security tests, 185 new tests (PRs #169-170). **S86:** Playwright E2E (35 specs) + MSW integration (29 tests), PRs #172-173. **S87:** Phase 8.6+ Forecast Intelligence brainstorm + spec (21 sections, 3 review rounds) + plan (13 sprints) + 19 JIRA tickets + doc overhaul.

---

## Session 88 — Phase 8.6+ Spec A: Backtesting Engine (Sprints 1-4) (2026-04-02)

**Branch:** `feat/KAN-370-backtesting` → develop | **PR #177 merged (squash)**

### Sprint 1 (KAN-374): Foundation
- Migration 024: 5 tables (backtest_runs, signal_convergence_daily, news_articles, news_sentiment_daily, admin_audit_log), 3 TimescaleDB hypertables, custom indexes
- 11 config settings (backtesting, BL, Monte Carlo, pipeline, sentiment)
- 5 factory-boy factories, 4 router stubs, 10 TypeScript interfaces
- Fixed: NewsArticle dedupe_hash unique constraint needs partitioning column for TimescaleDB

### Sprint 2 (KAN-375): BacktestEngine
- 7 Pydantic schemas, BacktestEngine with expanding window generation
- 5 metric functions: MAPE, MAE, RMSE, direction accuracy, CI containment + bias
- WindowSpec dataclass, `_safe_float` NaN/Inf guard, `strict=True` on all zips
- Opus fix: all-zero MAPE returns NaN, boundary condition documented

### Sprint 3 (KAN-376): CacheInvalidator + Convergence + Drift
- CacheInvalidator: 8 event methods, batched Redis deletes, fire-and-forget error handling, SCAN-based pattern clearing
- 5 convergence classifiers (RSI, MACD, SMA, Piotroski, forecast) + label computation
- Per-ticker calibrated drift: backtest_mape × 1.5 threshold, consecutive failure tracking, experimental demotion after 3 failures, self-healing
- Opus fixes: BL cache clear on forecast update, sector cache clear on price update, typed Redis param, boundary tests

### Sprint 4 (KAN-377): Backtest API
- 5 endpoints: GET /summary/all, POST /run (admin), POST /calibrate (admin), GET /{ticker}, GET /{ticker}/history
- Celery task stubs: run_backtest_task, calibrate_seasonality_task
- Opus fixes: route ordering (literal before path-param), summary count mismatch, None→404

### CI Fixes
- Line length in migration (ruff format)
- Pyright: `from __future__ import annotations` for date column self-reference in convergence + news_sentiment models

### Composite Review (Opus, cross-sprint)
- 0 critical, 3 warnings fixed: batched Redis deletes, model_version_id in schema, TS type sync
- All 4 pre-existing pyright errors unchanged (advisory check)

### ADR Updates
- ADR-009: Prophet train-once-predict-many architecture
- ADR-010: Per-ticker calibrated drift detection
- ADR-011: Event-driven cache invalidation (hybrid TTL)

### Session 88 Totals
- 1 PR merged (#177), 33 files changed, +2643 lines
- Tests: 1494 backend unit (was 1380, +114 new)
- Alembic head: `b2351fa2d293` (migration 024)
- 4 Opus expert reviews + 1 composite cross-sprint review
- 3 new ADRs documenting key architecture decisions
- Resume: Phase 8.6+ Sprint 5 (KAN-378) — PipelineRegistry + seed tasks

---

## Session 89 — Phase 8.6+ Specs D + B + C Start (2026-04-03)

**Branch:** multiple PRs | **PRs #179-180 merged**

### Spec D (KAN-371): Admin Pipeline Orchestrator — PR #179
- PipelineRegistry with TaskDefinition, dependency resolution, 7 task groups
- GroupRunManager: Redis lifecycle with atomic SET NX + Lua script for concurrent safety
- 10 Celery seed task wrappers (asyncio.run bridge, progress reporting)
- 8 admin pipeline API endpoints (groups, trigger, runs, history, cache clear)
- Pipeline Control frontend page (/admin/pipelines) with accordion groups, live polling
- 133 new tests, 3 Opus reviews (7 CRITICALs fixed)

### Spec B (KAN-372): News Sentiment Pipeline — PR #180
- 4 news providers: Finnhub, EDGAR 8-K, Fed RSS/FRED, Google News (defusedxml for XXE safety)
- SentimentScorer: GPT-4o-mini batch scoring, event_type allowlist, exponential decay aggregation
- NewsIngestionService: parallel fetching via asyncio.gather, batch dedup (no N+1)
- Prophet regressor integration (3 sentiment regressors, feature-flagged)
- Celery tasks: ingest 4x/day + score, CacheInvalidator wired, single-transaction
- 4 sentiment API endpoints with bulk (DISTINCT ON, capped 100), paginated articles
- 111 new tests, 2 Opus reviews (4 CRITICALs fixed)

### Session 89 Totals
- 2 PRs merged (#179-180), 41 files changed in Spec D, 22 in Spec B
- Tests: 1768 backend unit (was 1494, +274 new)
- 6 Opus expert reviews, 13 CRITICALs found and fixed
- Orchestration: Sonnet implements, Opus reviews, Haiku documents

---

## Session 90 — Phase 8.6+ Spec C: Convergence UX (Sprints 10-13) (2026-04-03)

**Branch:** `feat/KAN-373-convergence-ux` → develop | **PR merged (squash)**

### Sprint 10 (KAN-383): Portfolio Forecast
- PortfolioForecastService: Black-Litterman (Idzorek view confidences), vectorized Monte Carlo (Cholesky), CVaR (95%+99%)
- 8 Pydantic schemas, 2 portfolio forecast endpoints
- 30 new tests, 1 Opus review (2 CRITICALs fixed: double-vol MC, missing BL confidences)

### Sprint 11 (KAN-384): Convergence Service + Rationale + API
- SignalConvergenceService: 5 classifiers + news sentiment, divergence detection, portfolio/sector aggregation
- RationaleGenerator: natural-language explanations for convergence state
- 4 convergence API endpoints (ticker, history, portfolio, sector)
- Convergence history snapshots with actual return tracking

### Sprint 12a (KAN-385): Frontend Convergence Components
- TrafficLightRow: signal-by-signal bullish/bearish/neutral indicators
- DivergenceAlert: warning banner for forecast/technical divergence
- AccuracyBadge: MAPE-based model accuracy tier display
- RationaleSection: collapsible explanation panel

### Sprint 12b (KAN-386): Frontend Portfolio Components + Page Integration
- BLForecastCard: Black-Litterman expected returns display
- MonteCarloChart: fan chart visualization (Recharts)
- CVaRCard: 95th/99th percentile risk metrics
- ConvergenceSummary: portfolio-level convergence overview
- Integrated into stock detail + portfolio pages

### Sprint 13 (KAN-387): E2E Tests + Command Center Integration
- Convergence E2E tests (signal rendering, divergence alerts, history)
- Portfolio forecast E2E tests (BL card, MC chart, CVaR card)
- Command center convergence data integration

### 5-Persona Extreme Review
- PM, Full-Stack, Backend, Tester, JIRA Gap Verifier
- 7 CRITICALs found, all fixed
- 7 JIRA bugs created (KAN-388–394), 4 resolved same session
- 5 follow-up tasks created (KAN-395–399)

### Session 90 Totals
- 1 PR merged, 44 files changed
- Tests: 1848 backend + 423 frontend + 48 E2E = ~2319 total
- Coverage: 68.95% (floor 60%)
- Phase 8.6+ Epic KAN-369: ALL 4 SPECS COMPLETE (A+D+B+C)
- Resume: Tech debt (KAN-395-399) or Phase F (Subscriptions)
