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

### Sessions 79-113 (archived → `docs/superpowers/archive/progress-full-log.md`)
**S79:** Command Center MVP (PRs #154-155). **S81:** Portfolio Analytics (PR #158). **S82:** Auth Overhaul (PRs #159-161). **S84-86:** Test Infra (PRs #162-174). **S87-90:** Forecast Intelligence (PRs #177-185). **S91-92:** Workflow (PR #188). **S93-96:** Benchmark + Bug Sweep (PRs #189-192). **S97-104:** Pipeline Overhaul specs A-D (PRs #206-215). Tests at S104: 1962 unit + 441 API. **S106:** Quick Wins + Rate Limiters + DQ + Retention (PRs #219-223, 2023 unit). **S107:** Spec E Forecast Quality (PR #225). **S108:** Spec C Entry Points — 4 PRs (#229-232). **S109:** TimescaleDB Compression (PR #233). **S110:** Gap Fixes + Spec G Frontend (PRs #234-235), KAN-419 all 8 specs shipped. **S111:** Worktree Rule + SPY Seed (PRs #237-238), KAN-419 Done. **S113:** Obs Epic JIRA scaffolding (KAN-457/458/459/460) + 6 plans.

---

## Sessions 106-113 (compact — see archive for detail)
**S106:** Quick Wins + Rate Limiters + DQ + Retention (PRs #219-223, tests 2023). **S107:** Spec E Forecast Quality (PR #225). **S108:** Spec C Entry Points complete — 4 PRs (#229-232, tests 2080). **S109:** TimescaleDB Compression + Spec B follow-ups (PR #233). **S110:** Gap Fixes + Spec G Frontend (PRs #234-235, KAN-419 all 8 specs shipped). **S111:** Worktree Rule + SPY Seed (PRs #237-238, KAN-419 Done). **S113:** Obs Epic JIRA scaffolding (KAN-457/458/459/460) + 6 PR-scoped plans for 1a.

ORPHAN_DELETE_START### KAN-425 — Spec F Rate Limiters F2/F3/F4 (PR #220 merged)
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

---

## Session 111 — Quick Wins Batch: Epic Closeout + Worktree Rule + SPY Seed (2026-04-16)

**Branches:** `chore/KAN-430-worktree-rule` → develop (PR #237), `chore/KAN-406-spy-10y-seed` → develop (PR #238)

### JIRA Hygiene
- **KAN-398** closed as superseded by KAN-400 (Phase E UI Overhaul Epic explicitly absorbs it)
- **KAN-419** Epic promoted to Done — all 8 specs (A–G, Z) shipped across PRs #206–#235. Post-transition audit clean (no KAN-429 cascade from manual Epic transition — verified 22s gap between KAN-398 and KAN-419 resolutions)

### PR #237 — KAN-430 Worktree Reset-to-Develop Rule
- New `.claude/rules/worktree-create.md` documenting the post-`EnterWorktree` discipline (`git fetch origin develop && git reset --hard origin/develop`)
- Explicit hotfix exception to prevent over-application; rationale for rejecting PostToolUse hook (destructive `git reset --hard` risk)
- One-line CLAUDE.md reference under `## Git Branching`
- 50 lines, docs-only — CI correctly skipped test/lint jobs via change filter

### PR #238 — KAN-406 SPY ETF 10y Seed
- `scripts/seed_etfs.py`: `period="2y"` → `"10y"` to match `scripts/seed_prices.py` default (lines 125, 222)
- Unblocks full 10y QuantStats benchmarking (alpha, beta, Sharpe vs SPY) — was capped at 2y despite the stock universe having 10y of data
- Verified no code hardcodes 2y window: `backend/services/signals.py:121` + `portfolio/analytics.py` query SPY by date range
- README Step 2 runbook comment updated for consistency
- 15 lines, all 13 CI checks green (backend-test 10m25s)

### Gap Analysis Before Coding (requested by PM)
- KAN-430: evaluated wrapper/hook/rule options, picked rule-only (Option 3) — zero-risk, consistent with existing `.claude/rules/*` pattern
- KAN-406: verified no consumer assumes 2y; confirmed `seed_etfs.py` is already in README Step 2 runbook
- KAN-419: flagged KAN-429 automation risk on manual Epic transition — audit showed it didn't fire (manual transitions bypass the PR-merge automation)

### Session 111 Totals
- Tests: 2115 unit + 448 API (no new tests — pure config/docs)
- 4 JIRA tickets resolved (KAN-398, KAN-419, KAN-430, KAN-406)
- 2 PRs (#237, #238)
- Post-merge audit: KAN-406 + KAN-430 closed exactly as expected, 57s apart, no KAN-429 cascade misfire
- Resume: KAN-429 (JIRA automation bug, remaining sole HIGH), KAN-400 Epic refinement, or test hardening (KAN-213/215/216/217)

---

## Session 113 — Observability Epic JIRA scaffolding + 1a plans (2026-04-16)

**Branch:** `docs/obs-1a-plans` → develop | PR TBD

No code changes this session — pure planning + JIRA hygiene + memory fixes.

### JIRA scaffolding (Epic KAN-457 "Platform Observability Infrastructure")
- Filed parent Epic (KAN-457, High)
- 3 child Stories: KAN-458 (1a Foundations, High), KAN-459 (1b Coverage, Med), KAN-460 (1c Agent Consumption + UI, Med)
- "Blocks" links: KAN-458 → KAN-459 → KAN-460 (strict sequence)
- 5 refinement subtasks under KAN-458 per `conventions/jira-sdlc-workflow`:
  - KAN-461 Brainstorm 1a ✅ Done (shipped in prior sessions)
  - KAN-462 Write spec 1a ✅ Done (shipped in PR #240)
  - KAN-463 Review spec 1a ✅ Done (PM-approved via PR #240 merge)
  - KAN-464 Write plan 1a 🟡 In Progress → Ready for Verification after this PR merges
  - KAN-465 Review plan 1a ⬜ PM gate (next)

### 1a plans (split per Hard Rule #12)
6 PR-scoped plans written at `docs/superpowers/plans/2026-04-16-obs-1a-pr{1,2a,2b,3,4,5}-*.md`:
- **PR1** — migration 030 + `ObsEventBase` + `EventType` enum + `describe_observability_schema()` skeleton (440 lines plan)
- **PR2a** — SDK core: `ObservabilityClient` + `DirectTarget` + `MemoryTarget` + spool + buffer + FastAPI+Celery lifespan (1018 lines — exceeds 500-line cap; documented exception)
- **PR2b** — `InternalHTTPTarget` + `POST /obs/v1/events` ingest endpoint + CSRF-exempt path fix (459 lines)
- **PR3** — trace_id middleware + Celery propagation + structured JSON logging (628 lines — slightly over cap)
- **PR4** — `ObservedHttpClient` + 10 providers + `rate_limiter_event` + retention (612 lines)
- **PR5** — strangler-fig refactor with `OBS_LEGACY_DIRECT_WRITES` + `wrote_via_legacy` snapshot dedup (522 lines)

**Spec's PR2 split into PR2a+PR2b** to keep each plan reviewable. Total: 6 PRs for 1a, not 5.

### Adversarial 2-persona plan review (Backend Architect + Reliability Engineer)
- **4 CRITICAL + 9 HIGH** findings identified on round 1
- **CRITICALs fixed inline:**
  1. `emit_sync` missing but required by PR4+PR5 → added to PR2a with loop-agnostic `queue.SimpleQueue` buffer
  2. Celery event-loop mismatch (`@tracked_task` via `asyncio.run()` vs buffer's startup loop) → persistent background-thread loop pattern in PR2a
  3. `/obs/v1/events` would 403 from CSRF middleware → added to `csrf_exempt_paths` in PR2b
  4. Strangler-fig spool-replay-after-flag-flip = duplicate rows → `wrote_via_legacy: bool` snapshot field captured at emit time, not read at write time
- **HIGHs fixed inline:** `_flush_loop` poison-event safety, `_maybe_get_obs_client()` via ContextVar, `stop()` race fix, Celery signal ContextVar leak via token-reset, `build_observed_http_client()` factory defined
- **Round 2 delta review dispatched** for verification of the fixes; results informed final approval

### Stale-memory audit (check-stale-memories run)
- 6 memories fixed: `serena/tool-usage` (MCP prefix), `architecture/system-overview` (obs pkg 8→18 files, Alembic head 029, routers count), `architecture/auth-jwt-flow` (bcrypt pin framing), `serena/memory-map` (dead reference removed), `project/jira-integration-brainstorm` (Session-67 Epic list replaced with pointer)
- 1 memory trimmed: `future_work/AgentArchitectureBrainstorming` (180 lines → 10-line pointer; 7/8 items resolved)
- 3 session memories deleted: `session/kan-449-gap-analysis`, `session/kan-450-gap-analysis`, `session/kan-451-gap-analysis` (all shipped via PRs #229-231)

### Session 113 Totals
- Tests: 2115 unit + 448 API (no new tests — docs + JIRA only)
- 4 JIRA items filed (KAN-457/458/459/460) + 5 subtasks (KAN-461–465); 3 refinement subtasks transitioned to Done (brainstorm + spec + spec-review for 1a)
- 1 PR (docs-only, TBD number)
- 10 memory fixes applied (6 stale + 3 deleted + 1 trimmed)
- Resume (next session): KAN-465 PM plan-review gate → if approved, start 1a PR1 implementation on a fresh session

---

## Session 114 — Obs 1a PR1: Schema Foundation (2026-04-16)

**Branch:** `feat/KAN-458-obs-1a-pr1-schema` → develop | **PR #242 merged**

### KAN-465 — PM plan-review gate → Done
- All 6 PR-scoped plans approved without changes

### KAN-466 — Obs 1a PR1: Schema Foundation (PR #242)
- **Migration 030:** `observability` Postgres schema + `schema_versions` registry table (seeded `v1`)
- **Schema v1:** `ObsEventBase` envelope + `EventType` (7 types), `AttributionLayer` (10 layers), `Severity` (4 levels) enums
- **SchemaVersion model:** SQLAlchemy mapped to `observability.schema_versions`
- **describe_observability_schema():** skeleton async function (1c extends to MCP tool)
- **uuid-utils>=0.12.0** added for UUIDv7 (used starting PR3)
- **models.py → models/ package:** orphaned re-export file converted to package (zero-consumer, PM-approved)

### Verify-before-plan gate: 2 drifts caught
1. `backend/observability/models.py` file-vs-package conflict (plan missed existing file)
2. `tests/unit/conftest.py:67` db_session guardrail → DB tests moved to `tests/integration/observability/`

### Reviews
- **Spec compliance:** ✅ passed (1 minor: missing test docstrings — fixed)
- **Code quality:** 3 IMPORTANT fixed (dep ordering, describe_schema docstring, redundant frozen=False), 1 IMPORTANT reverted (SchemaVersion in models/__init__.py broke test metadata.create_all — observability schema only exists via raw DDL)

### KAN-429 misfire (incident #8+)
- Branch name `feat/KAN-458-obs-1a-pr1-schema` matched KAN-458 → closed parent Story
- Manually reopened KAN-458 → In Progress
- **Action item:** future PR branches should omit Story number (e.g., `feat/obs-1a-pr2a-sdk-core`)

### Session 114 Totals
- Tests: 2121 unit (+6) + 2 integration (+2) + 448 API = 0 failures
- Alembic: 029 → 030 (`c4d5e6f7a8b9`)
- 3 JIRA tickets resolved (KAN-465, KAN-466 + KAN-458 reopened after misfire)
- 1 PR (#242)
- Resume: File KAN-467 (PR2a subtask), create worktree `feat/obs-1a-pr2a-sdk-core` (no KAN-458 in name)

---

## Session 115 — Obs 1a PR2a: SDK Core + Default Targets + Lifespan Wiring (2026-04-17)

**Branch:** `feat/obs-1a-pr2a-sdk-core` → develop | **PR #243 merged**

### KAN-467 — Obs 1a PR2a: SDK Core (PR #243)
- **ObservabilityClient** — async `emit()` + sync `emit_sync()`, buffered flush loop, spool integration
- **EventBuffer** — loop-agnostic `queue.Queue(maxsize=N)` with thread-safe `_drops` counter (`threading.Lock`)
- **ObservabilityTarget Protocol** + `MemoryTarget` (tests) + `DirectTarget` (monolith default, delegates to event_writer stub)
- **JSONL disk spool** — `SpoolWriter`/`SpoolReader`, per-worker PID file, size-capped, reclaim loop
- **bootstrap.py** — `build_client_from_settings()`, `obs_client_var` ContextVar, `_maybe_get_obs_client()` helper
- **FastAPI lifespan** — init before yield, stop after
- **Celery signals** — `worker_process_init` + `worker_ready` (dual-signal for prefork + solo pool), persistent daemon-thread event loop
- **7 `OBS_*` config settings** with kill switches (`OBS_ENABLED=false` → all paths no-op)
- **`aiofiles>=24.1.0`** added for spool I/O

### Reviews (3 rounds)
1. **Round 1 (2-persona):** H1 (non-atomic `_drops` counter) + M2 (temp dir leak) — both fixed
2. **CI fixes:** `Field(default=...)` for pyright, `conf.update()` for pre-existing pyright error, format fix for `test_client.py`
3. **Round 2 (3-persona — BA + TE + Reliability):** M1 (missing concurrent producer test) + M3 (ContextVar + prefork propagation) + L4 (globals not reset on shutdown) — all fixed. M2 (at-least-once delivery semantic) documented, deferred to PR4/PR5.

### CI lessons
- `ruff check` was scoped to changed files locally but CI runs on full codebase — always run `ruff check backend/ tests/ scripts/`
- `ruff format` auto-fixes were applied locally but not committed — always verify `git diff` after format
- `Field(True, ...)` positional not recognized by pyright — use `default=True` keyword
- Pre-existing pyright errors surface when touching a file — fix properly, don't suppress

### Post-merge audit
- KAN-467 → Done (correct, via `Refs KAN-467` in commit trailer)
- KAN-458 → In Progress (correct, no misfire)
- Branch name omitted KAN-458 — KAN-429 avoidance strategy confirmed working

### Session 115 Totals
- Tests: 2121 → 2134 unit (+13), 0 failures
- 1 JIRA ticket filed + resolved (KAN-467)
- 1 PR (#243), 12 commits squash-merged
- Resume: File KAN-468 (PR2b subtask — InternalHTTPTarget + `/obs/v1/events` ingest endpoint)

---

## Session 118 — Obs 1a PR4: ObservedHttpClient + External API Logging (2026-04-17)

**Branch:** `feat/obs-1a-pr4-external-api-logging` → develop | **PR #246**

### KAN-469 — Obs 1a PR4: ObservedHttpClient + external API logging + rate limiter events
- **Migration 031:** `external_api_call_log` + `rate_limiter_event` hypertables with compression (7d, segmentby provider) + retention (30d)
- **SQLAlchemy models:** `ExternalApiCallLog` + `RateLimiterEvent` in `observability.` schema
- **ExternalProvider enum** (10 providers) + **ErrorReason enum** (8 classifications)
- **ObservedHttpClient:** `httpx.AsyncClient` subclass overriding `send()` — emits `EXTERNAL_API_CALL` event with status classification, latency, rate-limit header parsing. Emission never masks HTTP errors.
- **10 provider integrations:** OpenAI/Anthropic/Groq (via `http_client=`), 4 news providers + Google OAuth (via `get_observed_http_client()`), Resend (manual emission), yfinance (`YfinanceObservedSession` requests.Session subclass)
- **Rate-limiter emission:** `rate_limiter_event` at 5 fallback branches (redis_down, script_load_failed, redis_error ×2, timeout)
- **4 retention tasks:** `llm_call_log` (30d, drop_chunks), `tool_execution_log` (30d, drop_chunks), `pipeline_runs` (90d, DELETE), `dq_check_history` (90d, DELETE) — staggered 4:15-5:00 AM ET
- **Event writer:** Routes `EXTERNAL_API_CALL` + `RATE_LIMITER_EVENT` to real DB persistence (was stub in PR2a)

### Fact-sheet divergences caught pre-implementation
- Groq uses `AsyncGroq` SDK (not LangChain ChatGroq) — simpler http_client= integration
- `purge-login-attempts-daily` already exists at 3:00 AM — skipped duplicate
- `llm_call_log` + `tool_execution_log` are hypertables → use `drop_chunks` not DELETE
- 5 rate-limiter fallback branches (not 6 as plan stated)

### Code review (1 Opus reviewer)
- **0 CRITICAL, 3 IMPORTANT** — all addressed:
  - I-1: Retention docstrings referenced migration 031 instead of 008 — fixed
  - I-2: Silent `pass` in rate_limiter emission error handler — replaced with `logger.warning`
  - I-3: Connection pool per SDK call — noted as follow-up (move to `__init__`)

### Session 118 Totals
- Tests: 2133 → 2233 unit (+100 new), 0 failures
- Alembic: 030 → 031 (`d5e6f7a8b9c0`)
- 1 JIRA ticket filed (KAN-469) → In Progress
- 1 PR (#246), 9 commits
- 34 files changed, 3632 insertions
- Resume: Merge PR #246, transition KAN-469 → Done, file PR5 subtask (strangler-fig refactor)

---

## Session 119 — Obs 1a PR5: Strangler-Fig Refactor (2026-04-18)

**Branch:** `feat/obs-1a-pr5-emitter-refactor` → develop | **PR #247 merged**

### KAN-470 — Obs 1a PR5: Strangler-fig refactor — SDK migration of existing emitters
- **`OBS_LEGACY_DIRECT_WRITES` config flag** (default `true`) gates legacy direct-DB writes
- **5 Pydantic event subclasses** (`LLMCallEvent`, `ToolExecutionEvent`, `LoginAttemptEvent`, `DqFindingEvent`, `PipelineLifecycleEvent`) with `_LegacyStranglerFigMixin` carrying `wrote_via_legacy: bool` snapshot
- **4 emitter routes through SDK:** `record_request` + `record_cascade` (collector.py), `record_tool_execution` (collector.py), `_write_login_attempt` (_helpers.py), DQ persist (dq_scan.py)
- **`@tracked_task` PIPELINE_LIFECYCLE events** via `_emit_lifecycle` helper using `emit_sync` (safe from Celery asyncio.run context). Emits started + terminal (success/failed/no_op/partial). Existing UPDATE semantics unchanged.
- **`legacy_emitters_writer.py`** routes 5 event types back to original tables when flag is flipped off. `persist_pipeline_lifecycle` is DEBUG-log stub (1b adds the real table).
- **Dedup invariant:** `wrote_via_legacy` captured at emit time into event envelope; writer skips when `true`, inserts when `false`. Spool-replay safe.
- **`event_writer.py`** extended with 5 new routing branches (lazy imports, per-event-type grouping)

### Plan deviations (all beneficial)
- Skipped `get_status` prerequisite — `complete_run` already returns classified status
- `record_cascade` also routed (plan missed this 5th emitter)
- `PipelineLifecycleEvent.transition` uses "success" not plan's "succeeded"
- `DqFindingEvent.severity` expanded: added "high"/"medium" (real DQ check values)
- `LLMCallEvent.latency_ms/prompt_tokens/completion_tokens` made Optional (cascade events pass None)

### Code review (3-persona: Backend Architect + Test Engineer + Reliability)
- **0 CRITICAL, 3 IMPORTANT** — all fixed:
  - I-1: `event_writer.py` list annotations cleaned up
  - I-2: `test_event_writer` unhandled-event test fixed (MagicMock → _FakeEventType)
  - I-3: `_write_login_attempt` data loss edge case documented (not a regression)

### CI fix
- Pre-existing pyright error on `dq_scan_task` sync/async mismatch (since KAN-446) — added `type: ignore[arg-type]`

### KAN-458 → Done (6/6 PRs shipped for sub-epic 1a)

### Session 119 Totals
- Tests: 2233 → 2312 unit (+79 new), 0 failures
- 1 JIRA ticket filed (KAN-470) → Done
- KAN-458 (1a Foundations Story) → Done (all 6 PRs merged: #242, #243, #244, #245, #246, #247)
- 1 PR (#247), 10 commits squash-merged
- 13 files changed, 2569 insertions, 33 deletions
- Resume: Start sub-epic 1b (KAN-459 Coverage), or pick from backlog (KAN-429, KAN-400)

---

## Session 120 — Obs 1b Refinement (2026-04-18)
Planning session — 7 PR-scoped plans written + reviewed. See archive for details.

---

## Session 121 — Obs 1b PR1+PR2 Implementation (2026-04-18)

### JIRA Phase C — Implementation subtasks filed
- KAN-474 (Write plan) + KAN-475 (Review plan) → Done
- KAN-476–482: 7 implementation subtasks filed

### KAN-476 — PR1: HTTP layer (PR #250 merged)
- Migration 032, RequestLog + ApiErrorLog hypertables, PII redaction utility, ObsHttpMiddleware, batch writers, retention tasks
- CI fixes: revision ID collision, composite PK for TimescaleDB, pyright suppressions
- 29 new tests, 20 files, 1357 lines

### KAN-477 — PR2: Auth layer (PR #251 open)
- Migration 033, auth_event_log + oauth_event_log + email_send_log + login_attempts trace_id
- Auth/OAuth/email emissions wired into all auth endpoints, JWT recursion guard
- Fixed SQLAlchemy reserved `metadata` → `extra_data`
- 22 new tests

### Session 121 Totals
- Tests: 2312 → 2361 unit (+49), 0 regressions
- Alembic: 031 → 032 (merged) → 033 (PR2 branch)
- 2 PRs: #250 merged, #251 open

---

## Session 122 — Obs 1b PR3+PR4+PR5 Implementation (2026-04-18/19)

### KAN-478 — PR3: DB+Cache layer (PR #253 merged)
- Migration 034: slow_query_log + cache_operation_log (hypertables), db_pool_event + schema_migration_log (regular tables)
- SQLAlchemy before/after_execute hooks for slow query detection (>500ms) with `_in_obs_write` ContextVar feedback loop guard
- Cache instrumentation: 1% sampled, 100% on error, key redaction
- Query normalization (literals → $N/$S/$U placeholders)
- Alembic env.py migration event emission
- 4 retention tasks + beat schedule
- Review fix: C1 — `_in_obs_write` guard set in all writers before commit
- 45 new tests, 20 files, 1949 lines

### KAN-479 — PR4: Celery layer (PR #254 merged)
- Migration 035: celery_worker_heartbeat + celery_queue_depth (hypertables), beat_schedule_run (regular), pipeline_runs.trace_id
- Heartbeat daemon thread (30s), queue depth polling (60s via Redis LLEN)
- @tracked_task wired: retry_count from request.retries, trace_id from ContextVar
- Beat drift schema ready, emission deferred to 1c
- Review fixes: deferral docs, Redis try/finally, Mapped[dict]→Mapped[list]
- 12 new tests, 15 files, 1101 lines

### KAN-480 — PR5: Agent layer (PR #255 merged)
- Migration 036: agent_intent_log + agent_reasoning_log (regular), provider_health_snapshot (hypertable)
- Intent emission at chat.py call site (privacy-safe SHA256 hash)
- ReAct loop: per-iteration plan events + 4 termination paths (zero_tool_calls, wall_clock_timeout, exception, max_iterations)
- Provider health snapshot: schema + table ready, task is no-op stub (LLMClient request-scoped)
- Review fixes: 4 missing ProviderHealth fields + 2 missing indexes + 5 pre-existing pyright suppressions
- 14 new tests, 15 files, 1174 lines

### Session 122 Totals
- Tests: 2362 → 2433 unit (+71), 0 regressions
- Alembic: 033 → 034 → 035 → 036
- 3 PRs merged: #253, #254, #255
- Obs 1b: 5/7 PRs shipped (PR1-PR5). Remaining: PR6 (Frontend/Deploy), PR7 (Semgrep)
- TDD + FSD updated with 1b coverage
- Resume: PR6 (Frontend beacon, KAN-481) + PR7 (Semgrep rules, KAN-482)
