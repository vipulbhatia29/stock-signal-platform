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

### Sessions 79-104 (archived → `docs/superpowers/archive/progress-full-log.md`)
**S79:** Command Center MVP (PRs #154-155). **S81:** Portfolio Analytics (PR #158). **S82:** Auth Overhaul — Google OAuth, email verification (PRs #159-161). **S84-86:** Test Infrastructure Overhaul — T0-T5, CI, Semgrep, Playwright, Hypothesis (PRs #162-174). **S87-90:** Forecast Intelligence — Backtesting, News Sentiment, Convergence UX (PRs #177-185). **S91-92:** Workflow Optimization (PR #188). **S93-96:** LLM benchmark + Bug Sweep + DB reseed + pipeline bugs (PRs #189-192). **S97-98:** Pipeline Overhaul specs+plans (Epic KAN-419). **S99:** Spec A — `ticker_ingestion_state`, `@tracked_task`, `PipelineRunner` (PR #206). **S100:** Spec B3 — Prophet sentiment fix (PR #207). **S101:** Spec B — convergence, backtest, concurrent scoring, ingest extension (PR #208). **S103:** Spec D PR1 — Langfuse config, `trace_task` tests (PR #210). **S104:** Spec D complete — `@tracked_task` on all 24 tasks, `bypass_tracked` shim, KAN-445 StalenessSLAs (PRs #211-215). Tests at S104: 1962 unit + 441 API.

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

---

## Session 107 — KAN-424 Spec E Forecast Quality & Scale (2026-04-12)

**Branch:** `feat/KAN-424-forecast-quality-scale` → develop | **PR #225**

### KAN-424 — Spec E: Forecast Quality & Scale
- **E1:** `MAX_NEW_MODELS_PER_NIGHT` 20→100 + `priority=True` bypass on `retrain_single_ticker_task` for user-initiated adds via `ingest_ticker`
- **E2:** Beat entry renamed `model-retrain-biweekly` → `model-retrain-weekly`, removed misleading comment (no biweekly filter existed)
- **E3:** Split `_refresh_ticker_async` → `_refresh_ticker_fast` (prices + signals + QuantStats) + `_refresh_ticker_slow` (yfinance info + dividends). Parallelized nightly fast path via `asyncio.gather + Semaphore(5)`. Added `_refresh_all_slow_async` + Phase 1.5 in nightly chain.
- `INTRADAY_REFRESH_CONCURRENCY: int = 5` added to config (env-tunable)
- `mark_stage_updated` wired into both fast ("signals") and slow ("fundamentals") paths (Spec A integration)
- Code review caught 2 IMPORTANT: missing stage updates + dead param — both fixed
- Tests: 2023 → 2037 unit (+14)

### KAN-423 — Spec C: Entry Point Unification (prep)
- Split monolithic plan (~800 lines) into 4 PRs per Hard Rule #12
- Created `docs/superpowers/plans/2026-04-06-pipeline-overhaul-plan-C-entry-points-v2.md`
- Created 4 JIRA subtasks: KAN-449 (C1+C6), KAN-450 (C2+C3), KAN-451 (C4), KAN-452 (C5)
- Added blocking links: KAN-449 blocks KAN-450/451/452
- Gap analysis: 7 issues identified (missing exceptions, wrong test framework, line drift)

### Session 107 Totals
- 1 PR (#225)
- Tests: 2037 unit + 448 API
- 1 JIRA ticket shipped (KAN-424), 4 filed (KAN-449–452)
- Resume: KAN-449 (watchlist auto-ingest, PR1 of Spec C)

---

## Session 108 — KAN-449 Spec C PR1: Watchlist Auto-Ingest (2026-04-12)

**Branch:** `feat/KAN-449-watchlist-auto-ingest` → develop

### KAN-449 — C1+C6: Watchlist Auto-Ingest + Redis Dedup Infra
- **`ingest_lock.py`** (new): Redis SETNX dedup lock using shared `get_redis()` pool, fail-open, 60s TTL
- **`IngestInProgressError`** (new): 409 exception with safe_message
- **`WATCHLIST_AUTO_INGEST`** feature flag in config.py
- **`add_to_watchlist`** rewritten: dup→size→lock→ingest→insert ordering. Auto-ingests unknown tickers via canonical `ingest_ticker`. `IngestFailedError` → `StockNotFoundError` with `from exc` chain.
- **Watchlist router**: 409 handler for `IngestInProgressError`
- **Frontend layout.tsx**: Removed two-phase `useIngestTicker` hack — single `addToWatchlist.mutateAsync()` call
- **`useAddToWatchlist`**: Broader query invalidation (`watchlist`, `stocks`, `signals`), toasts only in caller
- 3-persona Opus review (Backend Architect + Test Engineer + Reliability) caught 2 CRITICALs:
  - Missing `from exc` on exception chain
  - Double toast (hook + caller both firing)
- Both fixed + 1 MEDIUM (missing edge-case test) added

### KAN-450 — C2+C3: Portfolio Sync-Ingest + Chat Canonical Ingest
- **`portfolio.py`**: `create_transaction` now checks `stock.last_fetched_at is None` → calls `ingest_ticker` with dedup lock (non-fatal on failure)
- **`analyze_stock.py`**: Rewrote `_run` to use canonical `ingest_ticker` + reload signals via `get_latest_signals`. Timeout 15→45s. Chat and stock page now agree.
- **`portfolio-client.tsx`**: `useLogTransaction.onSuccess` invalidates `stocks`, `signals`, `watchlist` caches
- **`use-stream-chat.ts`**: `tool_result` case invalidates `stocks`/`signals` when `analyze_stock` completes
- 2-persona Opus review (BA + TE): no CRITICALs, removed 3 duplicate ingest_lock tests

### KAN-451 — C4: Stale Auto-Refresh + Redis Debounce
- **`data.py`**: `_try_dispatch_refresh` helper — Redis SETNX 5-min debounce, dispatches `refresh_ticker_task.delay`
- **`get_signals`**: wired stale detection → auto-dispatch, `is_refreshing=True` optimistic, skip cache on stale
- **`SignalResponse`**: added `is_refreshing: bool`
- **Frontend**: `useSignals` polls every 5s when refreshing, `StockHeader` shows blue "Refreshing" / amber "Outdated" badges
- 1-persona Opus review (BA): no issues

### KAN-452 — C5: Bulk CSV Upload
- **`bulk_import.py`** (new): `parse_csv` + `ingest_new_tickers` (Semaphore(5), dedup lock)
- **`portfolio.py`**: `POST /portfolio/transactions/bulk` — multipart, rate limited 3/hr, 256KB, validate_only
- **Schemas**: `BulkTransactionRow/Error/Response`
- **Frontend**: `postMultipart`, `useBulkUploadTransactions`, `BulkTransactionUpload` component, template CSV
- 2-persona Opus review: no CRITICALs

### Session 108 Totals
- Tests: 2037 → 2080 unit (+43 new across KAN-449/450/451/452)
- 4 JIRA tickets shipped (KAN-449, KAN-450, KAN-451, KAN-452) — **Spec C complete**
- 4 PRs merged (#229, #230, #231, #232)
- Resume: KAN-426 (Spec G frontend polish) or KAN-429 (JIRA automation bug)

---

## Session 109 — KAN-448 TimescaleDB Compression + Spec B Follow-ups (2026-04-13)

**Branch:** `feat/KAN-448-timescaledb-compression` → develop | **PR #233**

### KAN-448 — TimescaleDB Compression Policies
- Migration 028: compression on stock_prices (180d), signal_snapshots (180d), news_articles (60d, segmentby=ticker)
- Refactored news retention from row-level DELETE to `drop_chunks()` (compression-compatible)
- Pre-implementation audit caught 4 blocking conflicts (upserts, UPDATEs, DELETEs on compressed chunks) — thresholds adjusted
- 3-persona review (Backend Architect + Test Engineer + DB/SQL Expert) caught 7 issues — all fixed

### Spec B Follow-ups (KAN-439/440/441/443/444)
- **KAN-439:** Backtest returns `status="degraded"` when `failed > 0`, includes `failed_tickers` list
- **KAN-440:** BacktestRun UniqueConstraint + `pg_insert` upsert (migration 029 with dedup guard)
- **KAN-441:** Celery `time_limit=3600` / `soft_time_limit=3300` on `run_backtest_task`
- **KAN-443:** Already fixed in Spec B refactor (`sentiment_regressors.py:67`) — closed with audit
- **KAN-444:** Forecast test TZ flake fixed with `freezegun` pin

### JIRA Cleanup
- KAN-212, KAN-214: → Done (work confirmed in codebase, folded into prior PRs)
- KAN-419: → In Progress (6/8 specs shipped)
- KAN-406: NOT fixed despite project-plan claim — comment added, kept open

### Session 109 Totals
- Tests: 2080 → 2096 unit (+16 new), 0 failures (KAN-444 flake resolved)
- 6 JIRA tickets resolved (KAN-448, KAN-439, KAN-440, KAN-441, KAN-443, KAN-444)
- 2 stale tickets closed (KAN-212, KAN-214)
- 1 PR (#233)
- Resume: Spec G frontend polish, JIRA automation bug

---

## Session 110 — Epic Gap Fixes + Spec G Frontend Polish (2026-04-13)

**Branches:** `feat/gap-fixes` → develop (PR #234), `feat/frontend-polish` → develop (PR #235)

### Gap Analysis of Epic Pipeline Architecture Overhaul
- 2-phase review (audit + fact-gathering subagents) found 7 specs partial-shipped
- Corrected 4 false positives (convergence seed, Prophet flag, tracked_task coverage, cache invalidation — all already shipped)
- Real gaps: 5 missing `mark_stage_updated` stages, yfinance limiter bypass in slow path, 3 missing admin endpoints
- Deferred task_tracer wiring (observability-only, no user impact)

### PR #234 — Pipeline Overhaul Gap Fixes
- **Spec A:** `mark_stage_updated` for `forecast`, `news`, `sentiment` stages (convergence + backtest were already shipped)
- **Spec D:** 3 new admin endpoints — per-task trigger, universe health, audit log listing
- **Spec F:** `yfinance_limiter.acquire()` before both `yf.Ticker()` calls in `_refresh_ticker_slow`
- **Cosmetic:** `"biweekly"` → `"weekly"` in pipeline_registry_config
- 15 new tests + 3 test hygiene fixes (existing tests silently attempted real DB/Redis connections after new `mark_stages_updated` calls)
- Upstream/downstream review found no runtime regressions — `mark_stages_updated` is fire-and-forget, `yfinance_limiter` is fail-open

### PR #235 — Spec G Frontend Polish
- **G1 Backend:** `GET /stocks/{ticker}/ingest-state` endpoint — reads `ticker_ingestion_state`, returns 7-stage freshness with SLA-based classification (fresh/stale/pending/missing)
- **G1 Frontend:** `useIngestProgress` hook (polls 2s, stops on ready) + `IngestProgressToast` component with per-stage status icons
- **G1 Wire:** `IngestProgressToast` replaces plain toasts in layout (watchlist add) and stock-detail (Run Analysis)
- **G3:** `TickerSearch` replaces free-text `Input` in `LogTransactionDialog` — typo prevention
- **G4:** `StalenessBadge` component integrated into `signal-cards` (sla=4h), `stock-header` (replaces manual stale/refresh spans), `news-card` (sla=6h)
- **Skipped with reasoning:** `score-bar.tsx` (no timestamp data), `forecast-card.tsx` (no `created_at` on response), `usePositions` polling (requires backend join)
- Review fixes: added `id` to `toast.custom` (duplicate prevention), removed dead `isStale` prop, removed phantom wrapper div

### Verified Already Shipped (no work)
- `useSignals` polling on `is_refreshing` (lines 211-222 of `use-stocks.ts`)
- 11 cache invalidation keys in `useIngestTicker.onSuccess`
- `WelcomeBanner` mounted on dashboard

### Session 110 Totals
- Tests: 2096 → 2115 unit (+19 new), 448 frontend (+5 new), 0 failures
- 4 JIRA tickets resolved (KAN-453, 454, 455, 426)
- Epic status: **All 8 specs shipped** — pending develop → main promotion for final Epic Done transition
- Deferred ticket created: KAN-456 (Langfuse task_tracer wiring, low priority)
- 2 PRs (#234, #235)
- Resume: JIRA automation bug fix, or Phase E UI Overhaul refinement
