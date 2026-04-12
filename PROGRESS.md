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

### Sessions 79-98 (archived → `docs/superpowers/archive/progress-full-log.md`)
**S79:** Command Center MVP (PRs #154-155, +122 tests). **S81:** Portfolio Analytics — QuantStats, PyPortfolioOpt (PR #158). **S82:** Auth Overhaul — Google OAuth, email verification (30 tickets, PRs #159-161). **S84-86:** Test Infrastructure Overhaul — tiered T0-T5, CI overhaul, 13 Semgrep rules, Playwright E2E, Hypothesis (PRs #162-174, +552 tests). **S87-90:** Forecast Intelligence — Backtesting, News Sentiment, Convergence UX (PRs #177-185, +~500 tests). **S91:** SESSION_INDEX + CLAUDE.md update (PR #186). **S92:** Workflow Optimization system (PR #188). **S93:** LLM benchmark research (qwen2.5-coder fails tool use). **S94:** Bug Sweep + Tech Debt — KAN-314/315/316/317/320/321/322/393/394/399, 10 tickets resolved (PR #189). **S95:** Full DB reseed 580 stocks, 1.24M price rows; 4 pipeline bugs found (KAN-401-404). **S96:** KAN-403/404 resolved — Prophet price floor, pipeline integrity (PR #192). **S97:** KAN-408 Backend Code Health spec + 14-task plan (KAN-412/413/417). **S98:** Pipeline Architecture Overhaul — 8 specs + 8 plans + 3 reviews, ~80 findings, 8 JIRA tickets (KAN-419 Epic + KAN-420 through KAN-427). Tests at session 96: 1906 unit.

---

## Session 99 — KAN-421 Spec A Ingestion Foundation (2026-04-07)

**Branch:** `feat/KAN-421-ingestion-foundation` → develop | **PR #206 merged**

- Migration 025 — `ticker_ingestion_state` table (10 stages, FK CASCADE, 3 indexes, idempotent backfill)
- `backend/services/ticker_state.py` — `mark_stage_updated`, `get_ticker_readiness`, `get_universe_health`
- `StalenessSLAs` constants in `backend/config.py`
- `@tracked_task` decorator in `backend/tasks/pipeline.py` — Hard Rule #10 compliant
- `backend/services/observability/task_tracer.py` + module-level singletons + main.py lifespan wiring
- 4-persona Opus review (Staff Eng + Test Eng + Security + DB/Migration), 2 rounds — 1 CRITICAL + 14 HIGH fixed
- Tests: 1907 → 1932 unit (+25), 383 → 397 API (+14)
- Filed: KAN-428 (pyright), KAN-429 (JIRA automation bug), KAN-430 (worktree-from-main)

---

## Session 100 — KAN-433 Spec B3 Prophet Sentiment Fix (2026-04-07)

**Branch:** `feat/KAN-422-b3-prophet-sentiment-fix` → develop | **PR #207 merged**

- Fixed CRITICAL forecast bug: `predict_forecast` hard-coded all sentiment regressors to 0.0 in future DataFrame
- Hybrid source architecture: historical rows from `model.history`, post-training from DB query, forecast from 7-day trailing mean
- 4-persona review (Backend Architect, Test Engineer, Silent Failure Hunter, Domain Expert) caught 3 CRITICALs
- Tests: 6 new real-DB tests in `tests/api/` (testcontainers)
- 4th KAN-429 incident: PR body `## JIRA` section triggered mass-close of 5 unrelated tickets

---

## Session 101 — KAN-422 Spec B B1+B2+B4+B5 (2026-04-07)

**Branch:** `feat/KAN-422-spec-b-completeness` → develop | **PR #208 merged**

- B1 (KAN-431): Real `compute_convergence_snapshot_task` replaces stub. `pg_insert.on_conflict_do_update` upsert, `_backfill_actual_returns` for 90d/180d. Nightly chain Phase 3 (shifted drift→4, alerts→5).
- B2 (KAN-432): `BacktestEngine.run_walk_forward` wraps sync Prophet via `asyncio.to_thread`. Weekly Saturday 03:30 ET beat.
- B4 (KAN-434): `SentimentScorer.score_batch` rewritten to `asyncio.gather` + `Semaphore(5)` for concurrent news scoring.
- B5 (KAN-435): `ingest_ticker` Steps 6b/8/9/10 fire-and-forget dispatch for new tickers; `news_ingest_task` accepts `tickers` param.
- 3 feature flags: `CONVERGENCE_SNAPSHOT_ENABLED`, `BACKTEST_ENABLED`, `PROPHET_REAL_SENTIMENT_ENABLED`
- 5-persona pre-push review: 1 BLOCKING + 5 HIGH fixed (pyright wrap, beat schedule, stage marking, partial-failure isolation)
- Tests: 1932 → 1945 unit (+13), 397 → 441 API (+44)

---

## Session 103 — KAN-420 Spec D PR1 (2026-04-08 to 2026-04-11)

**Branch:** `feat/KAN-420-spec-d-pr1` → develop | **PR #210 merged**

- `LANGFUSE_TRACK_TASKS: bool` + `LANGFUSE_SENTIMENT_IO_SAMPLING_RATE: float` config flags
- 4 async consumer tests for Spec A's `trace_task` contract (no-op, create-trace, error-swallow, record-llm)
- Subagent incident: Sonnet placed `@tracked_task` in wrong position (above `@celery_app.task`). Hard-reset. 4 process memories saved.
- Wrote 2400-line monolithic plan for PR1.5 — 5-persona review × 2 rounds found critical issues (bypass_tracked logic inverted, alerts.py consumer breakage, watermark inversion). Decision: split into 4 PRs (PR1.5a/b/c/d).
- 5th KAN-429 incident: `Refs KAN-xxx` commit trailers auto-closed tickets on merge. Both manually reverted.
- Filed: KAN-445 (StalenessSLAs → Pydantic BaseSettings)

---

## Session 104 — KAN-420 @tracked_task Adoption Complete + KAN-445 (2026-04-11)

**PRs merged:** #211, #212, #213, #214, #215 (pending)

### KAN-420 Spec D — @tracked_task adoption (PRs #211-214)
- **PR1.5a (#211):** `no_op` status classification in `complete_run()` + `celery_task_id` column on `pipeline_runs` (migration 026)
- **PR1.5b (#212):** `bypass_tracked` test shim + migration of 53 test call sites across 11 files
- **PR1.5c (#213):** Category A — `@tracked_task` on `_model_retrain_all_async`, `_forecast_refresh_async`, split `_nightly_price_refresh_async` into outer/inner
- **PR1.5d (#214):** Category B — `@tracked_task` on 21 remaining helpers, hoisted nested closures in forecasting.py and warm_data.py, removed dead `_runner` from evaluation.py and recommendations.py

**Result:** Every Celery task in the codebase now has PipelineRunner lifecycle tracking via `@tracked_task`. Pipeline runs are automatically created, tracked, and finalized.

### KAN-445 — StalenessSLAs env-tunable (PR #215)
- Converted `StalenessSLAs` from plain class to Pydantic `BaseSettings` with `env_prefix="STALENESS_SLA_"`
- Override any SLA via ISO 8601 duration (e.g. `STALENESS_SLA_PRICES=PT2H`)
- Cached on Settings to avoid repeated parsing

### Process improvements
- Updated `.claude/rules/review-scaling.md` with authorship trust adjustment (subagent code always needs review regardless of diff size)
- 6th KAN-429 false closure incident documented

### Session 104 Totals
- 5 PRs merged (#211-215), ~900 lines of production code
- Tests: 1962 unit + 441 API
- 2 JIRA tickets completed (KAN-420, KAN-445)
- Resume: KAN-412 (split oversized routers — spec+plan ready from Session 97)

---

## Session 106 — KAN-408 Close + KAN-427 Quick Wins + KAN-425 Rate Limiters (2026-04-12)

### KAN-408 — Epic closed (all subtasks shipped in S105)

### KAN-427 — Quick Wins Z1/Z2/Z4/Z5/Z6 (PR #219 merged)
- **Z1:** Registry typo fix `sentiment_scoring_task` → `news_sentiment_scoring_task` + enforcement test
- **Z2:** Deleted `calibrate_seasonality_task` stub + `/calibrate` endpoint + orphaned schemas
- **Z4:** Renamed `refresh_all_watchlist_tickers_task` → `intraday_refresh_all_task` with deprecation alias
- **Z5:** `useIngestTicker` cache invalidation expanded to 12 query keys (was 2)
- **Z6:** `WelcomeBanner` mounted on cold-start dashboard (loading-state gated)
- **Z3 deferred:** gated on Spec F2/F3 rate limiters
- 2-persona review found 3 CRITICALs (query key mismatches, orphaned schemas, stacklevel) — all fixed
- Tests: 1980 unit + 448 API

### KAN-425 — Spec F Rate Limiters F2/F3/F4 (PR #220 merged)
- `TokenBucketLimiter` class with atomic Lua script + NOSCRIPT recovery
- Integrated into 4 news providers (replacing crude sleep patterns)
- Integrated into `stock_data.py` (3 yfinance call sites)
- `@limiter.limit("20/hour")` on ingest endpoint + frontend 429 handling
- Autouse conftest fixture for rate limiter no-op in all unit tests
- 2-persona review found 2 CRITICALs (dead None check, stale SHA) — fixed

### KAN-427 Z3 — News LIMIT 50→200 (PR #221 merged)
- Replaced `select(Stock.ticker).limit(50)` with `get_all_referenced_tickers()[:200]`
- Now safe with rate limiters in place

### KAN-446 — DQ Scanner (PR #222 merged)
- 10 nightly data quality checks in `backend/tasks/dq_scan.py`
- `DqCheckHistory` model + migration 027
- PipelineRegistry "data_quality" group (8th group)
- Critical findings generate in-app alerts
- Beat schedule at 04:00 ET daily

### KAN-447 — Retention Tasks (PR #223 merged)
- `purge_old_forecasts_task` — 30d window on ForecastResult
- `purge_old_news_articles_task` — 90d window on NewsArticle
- Beat schedule at 03:30/03:45 ET daily
- **Bonus:** Fixed flaky `test_refresh_issues_new_csrf_token` — Redis pool not reset between API tests caused event loop teardown crash

### Session 106 Totals
- 5 PRs merged (#219-223)
- Tests: 2023 unit + 448 API
- 5 JIRA tickets completed (KAN-408, KAN-425, KAN-427, KAN-446, KAN-447)
- 3 JIRA tickets filed (KAN-446/447/448) — 446+447 now Done, 448 remains
- Flaky CI test fixed (Redis pool teardown)
- Resume: KAN-448 (compression, Low), KAN-423 (entry points), KAN-424 (forecast quality)
