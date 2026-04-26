# Stock Signal Platform — Project Plan

> **Guideline:** When completing any sprint or phase, update this file with the relevant JIRA ticket references (Epic, Story, Subtask keys). When closing JIRA tickets, verify they are reflected here. Run a JIRA↔project-plan reconciliation at each session closeout.

## Completed Phases (Sessions 1-81)

### Phase 1: Signal Engine + Database + API ✅ (Sessions 1-3)
FastAPI + SQLAlchemy async + Alembic + TimescaleDB + JWT auth. Signal engine (RSI, MACD, SMA, Bollinger, composite 0-10). Recommendation engine (BUY/WATCH/AVOID). 7 endpoints. Seed scripts.
*(Pre-JIRA — no tickets)*

### Phase 2: Dashboard + Screener UI ✅ (Sessions 4-7)
httpOnly cookie auth, StockIndex model, on-demand ingest, bulk signals, signal history. Next.js frontend (login, dashboard, screener, stock detail).
*(Pre-JIRA — no tickets)*

### Phase 2.5: Design System + UI Polish ✅ (Sessions 8-13, PR #1)
Financial CSS vars, `useChartColors()`, 10 new components, entry animations, Bloomberg dark mode.
*(Pre-JIRA — no tickets)*

### Phase 3: Security + Portfolio + Fundamentals ✅ (Sessions 14-25, PRs #2-5)
JWT validation, rate limiting, CORS. Portfolio FIFO engine, P&L, sector allocation. Piotroski F-Score (50/50 blending). Snapshots, dividends, divestment rules, portfolio-aware recs, rebalancing.
*(Pre-JIRA — no tickets)*

### Phase 4: AI Agent + UI Redesign ✅ (Sessions 26-44, PRs #5-50)
- **4A:** Navy command-center UI (25 tasks, KAN-87–98)
- **4B:** LangGraph Plan→Execute→Synthesize (Epic KAN-1, KAN-12/13/15)
- **4C:** NDJSON streaming chat UI (23 files, Epic KAN-30)
- **4D:** ReAct loop + enriched data layer (Epic KAN-61, KAN-62–68)
- **4E:** Security hardening (11 findings, Epic KAN-69, KAN-70–72)
- **4F:** Full UI migration (Epic KAN-88, 9 stories KAN-89–96, KAN-97 animations)
- **4G:** Backend hardening (154 tests, Epic KAN-73, KAN-74–84)

### Phase 5: Forecasting + Alerts ✅ (Sessions 45-52, PRs #54-93, Epic KAN-106)
Prophet forecasting, 9-step nightly pipeline, recommendation evaluation, drift detection, in-app alerts, 6 agent tools (KAN-107–117). MCP stdio tool server (Epic KAN-119, KAN-132–136). Redis refresh token blocklist (Epic KAN-118). Dashboard bug sprints. CI/CD pipeline (Epic KAN-22).

### Phase 6: LLM Factory + Observability ✅ (Sessions 53-55, PRs #95-101, Epic KAN-139)
V1 deprecation (KAN-140), TokenBudget (KAN-141), llm_model_config (KAN-142), GroqProvider cascade (KAN-143), admin API (KAN-144), truncation (KAN-145), ObservabilityCollector DB writer, Playwright E2E. Redis cache (KAN-148). OHLC (KAN-150).

### Phase 7: Backend Hardening + Tech Debt ✅ (Sessions 56-60, PRs #102-121, Epic KAN-147)
Guardrails (KAN-158), data enrichment (KAN-159), agent intelligence (KAN-160), pagination (KAN-168), cache (KAN-170), passlib→bcrypt (KAN-174). SaaS readiness audit (Epic KAN-176, KAN-176–186). Service layer extraction (KAN-172/173). Code analysis tech debt (Epic KAN-163).

### Phase 8: Observability + ReAct Agent ✅ (Sessions 61-64, PRs #123-131, Epic KAN-189)
- **8A:** Provider observability, cost_usd, cache_hit, agent_id (KAN-190–198)
- **8B:** ReAct loop (KAN-189, KAN-203–210)
- **8C:** Intent classifier + tool filtering (KAN-199–202)
- Input validation (KAN-154), OHLC (KAN-150)

### SaaS Launch Roadmap Phase A ✅ (Session 67, PR #138, KAN-186)
TokenBudget → Redis sorted sets. ObservabilityCollector reads → DB.

### SaaS Launch Roadmap Phase B ✅ (Sessions 68-70, PRs #140-143, Epic KAN-218)
Langfuse infra (KAN-220), trace instrumentation (KAN-221), assessment data layer (KAN-222), OIDC SSO + eval framework (KAN-223). Observability frontend (KAN-224). Tests + docs (KAN-225).

### SaaS Launch Roadmap Phase B.5 ✅ (Sessions 72-79, PRs #144-157, Epic KAN-226)
- **BU-1:** Schema sync + alerts redesign (KAN-227, subtasks KAN-265–266)
- **BU-2:** Stock detail enrichment (KAN-228)
- **BU-3/4:** Dashboard 5-zone redesign + chat (KAN-229/230, subtasks KAN-267–274)
- **BU-5:** Observability backend gaps (KAN-231, subtasks KAN-275–279)
- **BU-6:** Observability frontend (KAN-232)
- **BU-7:** Command Center (KAN-233, subtasks KAN-288–299, KAN-311, KAN-313)

### Phase 8.5: Portfolio Analytics ✅ (Session 81, PR #158, Epic KAN-246)
pandas-ta-openbb (KAN-249), QuantStats (KAN-247), PyPortfolioOpt (KAN-248). Migration 022. 4-expert review (21 findings fixed). Bug fixes: KAN-318, KAN-319. 25 internal tools. Alembic head: `c870473fe107`.

---

## Active / Future Phases

### Phase C: Auth Overhaul ✅ (Session 82, Epic KAN-325)

> Google OAuth, email verification, password reset, account settings, account deletion, admin tools.
> Brainstormed + spec-reviewed + design-reviewed. 30 JIRA tickets (KAN-326 to KAN-355).

**Sprint 1-6 (Implementation) ✅:**
- **Sprint 1:** Foundation — models, migration 023, config, CachedUser, token revocation, schemas (KAN-326–334)
- **Sprint 2:** EmailService (Resend) + email verification endpoints (KAN-335–336)
- **Sprint 3:** GoogleOAuthService + OAuth authorize/callback + login guards (KAN-337–339)
- **Sprint 4:** Password reset + change/set password + Google unlink + account info (KAN-340–342)
- **Sprint 5:** Account deletion + admin endpoints + Celery purge + write guards on 11 endpoints (KAN-343–346)
- **Sprint 6:** Frontend — API functions, Google buttons, 3 auth pages, account settings, verification banner (KAN-347–352)

**Expert review:** 4-persona review (PM, Staff FS, Security, QA) found 22 issues — all critical/major fixed.
**Files:** 10 new + 25 modified = 35 total. Migration 023 applied (`5c9a05c38ee1`).
**Tests:** 1296 backend passing (no regressions). TypeScript 0 errors.

**Sprint 7 (Testing) — absorbed into Phase D Test Overhaul (KAN-354/355 → KAN-360):**
- KAN-353: Unit tests (~33 tests) ✅ (Session 82)
- KAN-354: API integration tests → absorbed into KAN-360 (Sprint 4)
- KAN-355: Frontend Jest tests → absorbed into KAN-360 (Sprint 4)

### Phase D: Test Infrastructure Overhaul ✅ (Sessions 84-86, Epic KAN-356)

> Complete test suite redesign: tiered architecture (T0-T5), path-based CI routing, quality gates, security test matrix, Hypothesis domain tests, Playwright E2E expansion, Lighthouse performance, custom Semgrep rules. 4-expert reviewed spec.
> **Spec:** `docs/superpowers/specs/2026-04-01-test-suite-overhaul.md`

| Sprint | Ticket | Summary | Status |
|--------|--------|---------|--------|
| 1 | KAN-357 | Foundation + Cleanup — delete dead tests, add packages, configure markers | ✅ Session 84, PR #162 |
| 2 | KAN-358 | CI Overhaul — path-filter, ci-gate, quality gates, 13 Semgrep rules | ✅ Session 84, PRs #163-167 |
| 3 | KAN-359 | Domain + Cache + Regression — Hypothesis (50+), golden datasets, Celery | ✅ Session 85, PR #169 |
| 4 | KAN-360 | Auth + Security — IDOR matrix, token security, OAuth, rate limiting (absorbs KAN-354/355) | ✅ Session 85, PR #170 |
| 5 | KAN-361 | Playwright E2E Expansion (35 specs) + msw component integration (29 tests) | ✅ Session 86, PRs #172-173 |
| 6 | KAN-362 | Performance + Memory — Lighthouse, chart sizing, CDP heap, nightly CI | ✅ Session 86, PR #174 |
| 7 | KAN-363 | Visual Regression — baseline capture (after UI stable) | ⏸ Blocked on KAN-400 (UI Overhaul) |

**Bug fixes during Sprint 2:** KAN-364 (6x str(e) leak, PR #167), KAN-365 (Semgrep false positives, PR #167).
**Tech debt fixes:** TimescaleDB teardown (PR #164), Next.js Suspense (PR #165), pyright config (PR #166).
**Sprint 5 infra:** MSW v2 setup (server + handlers + custom jest-env-with-fetch), @axe-core/playwright for WCAG 2.0 AA.
**Sprint 6 infra:** playwright-lighthouse, @lhci/cli, ci-nightly.yml (weekdays 04:00 UTC), "nightly" Playwright project.
**Final count:** 1380 backend + 378 frontend + 42 E2E + 27 nightly perf = ~1827 tests. 14 CI checks (13 + ci-gate).

### Phase 8.6+: Forecast Intelligence System ✅ (Sessions 87-90, Epic KAN-369)

> Three-level forecast system (stock → sector → portfolio) with backtesting, news sentiment, signal convergence UX, and admin pipeline orchestrator. Supersedes old KAN-323/KAN-324 (closed).
> **Spec:** `docs/superpowers/specs/2026-04-02-forecast-intelligence-design.md`
> **Plan:** `docs/superpowers/plans/2026-04-02-forecast-intelligence-plan.md`

| Sprint | Ticket | Summary | Status |
|--------|--------|---------|--------|
| **Spec A: Backtesting Engine (KAN-370)** | | Branch: `feat/KAN-370-backtesting` | **✅ Session 88, PR #177** |
| 1 | KAN-374 | Migration 024 + config + shared models + factories + router stubs | ✅ Session 88 |
| 2 | KAN-375 | BacktestEngine + walk-forward + metrics + DB integration | ✅ Session 88 |
| 3 | KAN-376 | CacheInvalidator + drift upgrade + convergence snapshot | ✅ Session 88 |
| 4 | KAN-377 | Backtest API + tests + frontend accuracy badge | ✅ Session 88 |
| **Spec D: Admin Pipeline Orchestrator (KAN-371)** | | Branch: `feat/KAN-371-admin-pipelines` | **✅ Session 89, PR #179** |
| 5 | KAN-378 | PipelineRegistry + seed tasks + admin user | ✅ Session 89 |
| 6 | KAN-379 | Pipeline API + admin frontend page | ✅ Session 89 |
| **Spec B: News Sentiment Pipeline (KAN-372)** | | Branch: `feat/KAN-372-news-sentiment` | **✅ Session 89, PR #180** |
| 7 | KAN-380 | NewsProvider interface + Finnhub + EDGAR + Fed + Google | ✅ Session 89 |
| 8 | KAN-381 | Sentiment scorer + Prophet integration + Celery tasks | ✅ Session 89 |
| 9 | KAN-382 | Sentiment API + tests | ✅ Session 89 |
| **Spec C: Convergence UX (KAN-373)** | | Branch: `feat/KAN-373-convergence-ux` | **✅ Session 90** |
| 10 | KAN-383 | Portfolio forecast (BL + Monte Carlo + CVaR) | ✅ Session 89-90 |
| 11 | KAN-384 | Convergence service + rationale + API | ✅ Session 90 |
| 12a | KAN-385 | Frontend convergence components | ✅ Session 90 |
| 12b | KAN-386 | Frontend portfolio components + page integration | ✅ Session 90 |
| 13 | KAN-387 | E2E tests + command center integration + final regression | ✅ Session 90 |

**Session 90 — 5-persona extreme review:** PM, Full-Stack, Backend, Tester, JIRA Gap Verifier. 7 CRITICALs found, all fixed. 7 JIRA bugs created (KAN-388–394), 4 resolved same session. 5 follow-up tasks created (KAN-395–399). KAN-395/396/397 resolved. KAN-388–392 resolved.

**Tests:** 1848 backend + 423 frontend + 48 E2E = ~2319 total. Coverage: 68.95% (floor 60%).

### Workflow Optimization ✅ (Session 92, PR #188)

> 5 rules (R1-R5), 2 hooks (H1-H2), 3 skills (S1-S3). Brainstorm routing, review scoring, doc-delta tracking, phase-end dimensions.

### Bug Sweep + Tech Debt Clearout ✅ (Session 94, PR #189)

> Resolved all 10 open bugs and tech debt: KAN-314, 315, 316, 317, 320, 321, 322, 393, 394, 399.
> Zero open bugs remaining. Intelligent review-config scoring system implemented.
> **Tests:** 1860 backend + 439 frontend + 38 API = ~2337 total.

### Full Data Reseed + Pipeline Integrity ✅ (Sessions 95-96, PR #192)

> Session 95: Full DB reseed with 580 stocks, 1.24M price rows, 1548 forecasts. 4 pipeline bugs found (KAN-401-404) + 2 enhancements filed (KAN-405-406).
> Session 96: KAN-403 (Prophet negative price floor) + KAN-404 (pipeline integrity: 6 fixes for non-universe tickers) resolved. Skills/rules audit: ~1,500 tokens/interaction saved.
> **Tests:** 1906 backend unit (+46 new) after Session 96.

### Phase Benchmark + Backend Code Health Batches ✅ (Sessions 93, 97, PRs #195-200)

> Session 93: LLM benchmark research — built local LLM harness, qwen2.5-coder:14b fails tool use.
> Session 97 (prior): Model benchmark framework built, Groq/LiteLLM smoke test (not Claude Code compatible).
> **Backend code health batches:** KAN-407, 409, 410, 411, 414, 415, 416, 418 resolved across PRs #198, #199, #200.

---

### Epic KAN-419: Pipeline Architecture Overhaul (REFINED — Session 98)

> Comprehensive refactor of ingestion + observability + UX after a full audit found stub tasks closed without code, broken Prophet sentiment integration, missed entry points, and observability gaps.
> **8 specs + 8 plans + 3 expert reviews. ~80 review findings (28 CRITICAL applied inline). 7 superseded JIRA tickets.**
>
> **Specs:** `docs/superpowers/specs/2026-04-06-pipeline-overhaul-spec-{A..G,Z}-*.md` (~5,576 lines)
> **Plans:** `docs/superpowers/plans/2026-04-06-pipeline-overhaul-plan-{A..G,Z}-*.md` (~9,853 lines)
> **Reviews:** `docs/superpowers/plans/2026-04-06-pipeline-overhaul-review-{staff-engineer,test-engineer,efgz,resolutions}.md`

| Ticket | Spec | Priority | Summary | Status |
|--------|------|----------|---------|--------|
| KAN-419 | Epic | High | Pipeline Architecture Overhaul | **✅ Done (Session 111)** — Epic closed after all 8 specs shipped |
| KAN-421 | A | High | Ingestion Foundation — state table, SLAs, PipelineRunner contract, observability helpers | ✅ Done (PR #206, Session 99) |
| KAN-422 | B | High | Pipeline Completeness — convergence, backtest, Prophet sentiment fix, news concurrency | **✅ Done (PRs #207 + #208, Sessions 100-101)** |
| &nbsp;&nbsp;↳ KAN-431 | B1 | High | Convergence task real implementation + backfill + nightly chain wiring | **✅ Done (PR #208, Session 101)** |
| &nbsp;&nbsp;↳ KAN-432 | B2 | High | Backtest task real impl + BacktestEngine.run_walk_forward + weekly beat | **✅ Done (PR #208, Session 101)** |
| &nbsp;&nbsp;↳ KAN-433 | B3 | Highest | **Prophet sentiment predict-time fix** (async + `model.history` source + post-training DB fetch + 7d projection) | **✅ Done (PR #207, Session 100)** |
| &nbsp;&nbsp;↳ KAN-434 | B4 | Medium | News scoring concurrent batch dispatch (`asyncio.gather` + `Semaphore(5)`) | **✅ Done (PR #208, Session 101)** |
| &nbsp;&nbsp;↳ KAN-435 | B5 | High | `ingest_ticker` extension — Steps 8/9/10 wiring news + convergence + `mark_stage_updated` (depends on B1) | **✅ Done (PR #208, Session 101)** |
| KAN-423 | C | High | Entry Point Unification — watchlist, portfolio, chat, stale auto-refresh, bulk CSV | Split into 4 PRs ✅ |
| &nbsp;&nbsp;↳ KAN-449 | C1+C6 | High | Watchlist auto-ingest + Redis dedup infra | **✅ Done (Session 108)** |
| &nbsp;&nbsp;↳ KAN-450 | C2+C3 | High | Portfolio sync-ingest + Chat canonical ingest | **✅ Done (Session 108)** |
| &nbsp;&nbsp;↳ KAN-451 | C4 | Medium | Stale auto-refresh + Redis debounce | **✅ Done (Session 108)** |
| &nbsp;&nbsp;↳ KAN-452 | C5 | Medium | Bulk CSV upload (endpoint + component) | **✅ Done (Session 108)** |
| KAN-420 | D | High | Admin + Observability — universal PipelineRunner, per-task trigger, ingestion health, Langfuse spans | **✅ Done (PRs #210-214, Sessions 103-104)** |
| &nbsp;&nbsp;↳ KAN-445 | D (follow-up) | Medium | Convert StalenessSLAs to env-tunable Pydantic settings (supersedes A-LOW-2) | **✅ Done (PR #215, Session 104)** |
| KAN-424 | E | Medium | Forecast Quality & Scale — cap raise, weekly retrain, intraday fast/slow split | **✅ Done (PR #225, Session 107)** |
| KAN-425 | F2/F3/F4 | Medium | Rate Limiters — Redis token bucket for yfinance + news providers + ingest endpoint | **✅ Done (PR #220, Session 106)** |
| &nbsp;&nbsp;↳ KAN-446 | F1 | Medium | DQ Scanner — nightly 10-check scan + alert generation + migration 027 | **✅ Done (PR #222, Session 106)** |
| &nbsp;&nbsp;↳ KAN-447 | F5 | Medium | Retention Tasks — purge forecasts (30d) + news (90d) | **✅ Done (PR #223, Session 106)** |
| &nbsp;&nbsp;↳ KAN-448 | F6 | Low | TimescaleDB Compression — compression policies on 3 hypertables | **✅ Done (PR #233, Session 109)** |
| KAN-426 | G | Medium | Frontend Polish — ingest progress, polling, stale badges, ticker search | **✅ Done (PR #235, Session 110)** |
| KAN-427 | Z | Medium | Quick Wins — Z1/Z2/Z4/Z5/Z6 (Z3 deferred to after F2/F3) | **✅ Done (PR #219, Session 106)** |

**Superseded tickets** (commented in JIRA, will close when corresponding KAN- ticket lands):
- KAN-405 (sentiment concurrent) → folded into KAN-422
- KAN-395 (convergence stub — was wrongly closed) → folded into KAN-422
- KAN-398 (AccuracyBadge wiring) → closed as superseded by KAN-400 (Phase E UI Overhaul Epic, Session 111)
- KAN-406 (SPY 2y history) → ✅ Done as standalone fix (PR #238, Session 111) — was NOT actually absorbed into KAN-424 despite earlier assumption
- KAN-212 (tool orchestration tests) → folded into KAN-423
- KAN-213 (testcontainers refactor) → overhaul test strategy
- KAN-214 (error path tests) → folded across KAN-422/423/420
- KAN-162 (Langfuse self-hosted) → partially folded into KAN-420

**Execution order (isolation batches):**

```
Batch Z (KAN-427) ─────────┐ Independent — anytime
Batch A (KAN-421) ─────────┤ Foundation — anytime
                            │
Batch A → Batch B (KAN-422) ┤ B uses A's primitives
Batch A → Batch D (KAN-420) ┤ D uses A's primitives
Batch B → Batch C (KAN-423) ┤ C uses B's extended ingest_ticker
Batch A + F → Batch E ──────┤ E uses F3 yfinance rate limiter
Batch C → Batch G (KAN-426) ┘ G uses C's API contract
```

**Migration sequence:** Current head `e1f2a3b4c5d6` (migration 025 — Spec A ticker_ingestion_state, shipped Session 99) → 026 `8c13a01dd3fa` (KAN-420 PR1.5a: `celery_task_id` on `pipeline_runs`, coded on branch not yet merged) → 027 (Spec F) → 028 (Spec F).

**KAN-420 Spec D PR breakdown (Session 103 decision — monolithic plan split into 4 PRs):**

| PR | Scope | Status | Branch |
|---|---|---|---|
| PR1 (PR #210) | Config flags + trace_task consumer tests | ✅ Merged Session 103 | deleted |
| PR1.5a | pipeline.py core: `no_op` status + `celery_task_id` column + docstring fix | Coded, needs review + push | `feat/KAN-420-pr1.5a-pipeline-core` |
| PR1.5b | Test infrastructure: `bypass_tracked` shim + migrate ~56 test call sites to `.__wrapped__` | Planned, not started | — |
| PR1.5c | Category A refactor: 3 helpers (`model_retrain`, `forecast_refresh`, `nightly_price_refresh` outer/inner split) | Planned, not started | — |
| PR1.5d | Category B + B-hoist + B-wrap + B-fanout: ~28 helpers + AST enforcement test (3-layer) | Planned, not started | — |

Category audit table + full plan reference: `feat/KAN-420-spec-d-pr1.5-tracked-task-adoption` branch (local, not merged — 2400-line planning artifact with 35-task audit table).

**Critical fixes already applied to specs/plans** (review pre-merge, see resolutions doc): 25 cross-cutting fixes including `task_tracer` import path consolidation, `mark_stage_updated` signature lock, `Stage` Literal extension, Prophet sentiment async refactor, Postgres pool math correction, TimescaleDB compression downgrade fix, frontend Jest (not Vitest), Redis SETNX dedup, etc.

**B3 review findings deferred as follow-ups** (not blocking PR 2): H-Callers (differentiate DB vs solver errors in `backend/tasks/forecasting.py` exception handlers), Domain H2 (evaluate training-window mean / AR(1) / exp-decay vs current 7d projection for 270d horizons), Domain M2 (evaluate multiplicative vs additive regressor mode), pre-existing bug (`make_future_dataframe` extends from `training_end` not `today` → stale-model target_date falls off the end).

**Spec B persona pre-push review follow-ups** (Session 101 — filed as KAN-436..KAN-444, labels `spec-b-followup` + `kan-422`):

| Key | Priority | Summary |
|---|---|---|
| KAN-436 | High | Bulk `mark_stages_updated` helper — 500 sequential round-trips → 1 query |
| KAN-437 | High | Walk-forward sentiment N+1 — pre-load once per ticker (~55k → ~500 queries on weekly run) |
| KAN-438 | High | Per-ticker DB session in `_run_backtest_async` (currently one session wraps full loop) |
| KAN-439 | Medium | Backtest task returns `status="degraded"` when `failed > 0` | **✅ Done (PR #233, S109)** |
| KAN-440 | Medium | `BacktestRun` UniqueConstraint + upsert | **✅ Done (PR #233, S109)** |
| KAN-441 | Medium | Celery `time_limit` / `soft_time_limit` on `run_backtest_task` | **✅ Done (PR #233, S109)** |
| KAN-442 | Low | Consolidate `_fetch_sentiment_for_window` into `_fetch_sentiment_regressors` (DRY cleanup) |
| KAN-443 | Low | Pyright `pd.Index(...)` wrap — already fixed in Spec B refactor | **✅ Done (S109 audit)** |
| KAN-444 | Low (Bug) | Forecast test TZ mismatch — freezegun fix | **✅ Done (PR #233, S109)** |

**Spec B deferrals to Spec D** (wiring dependencies, not defects):
- `@tracked_task` decoration on convergence / backtest tasks — decorator only wraps `Callable[..., Awaitable[R]]`; must be applied to the async helpers (`_compute_convergence_snapshot_async`, `_run_backtest_async`) rather than the sync Celery wrappers.
- `task_tracer` spans inside `SentimentScorer.score_batch` — observability integration tracked under Spec D.

---

### Epic KAN-408: Backend Code Health & Security Hardening ✅ (Sessions 97-105)

> Refined this session. Spec + plan written, 2 rounds of staff + test engineer reviews complete.
> **Spec:** `docs/superpowers/specs/2026-04-06-backend-code-health-final.md`
> **Plan:** `docs/superpowers/plans/2026-04-06-backend-code-health-final.md`

| Ticket | Priority | Summary | Status |
|--------|----------|---------|--------|
| KAN-407 | High | Backend code health batch 1 | ✅ Done (PR #198) |
| KAN-409 | High | Backend code health batch 2 | ✅ Done (PR #199) |
| KAN-410 | High | Backend code health batch 2 | ✅ Done (PR #199) |
| KAN-411 | High | Backend code health batch 2 | ✅ Done (PR #199) |
| KAN-414 | High | Backend code health batch 3 | ✅ Done (PR #200) |
| KAN-415 | High | Backend code health batch 3 | ✅ Done (PR #200) |
| KAN-416 | High | Backend code health batch 1 | ✅ Done (PR #198) |
| KAN-418 | High | Backend code health batch 2 | ✅ Done (PR #199) |
| KAN-412 | High | Split oversized routers (auth.py 1263L, portfolio.py 776L) | ✅ Done (S105) |
| KAN-413 | High | Split portfolio service into focused modules | ✅ Done (S105) |
| KAN-417 | Medium | Add CSRF protection for cookie-based auth | ✅ Done (S105) |

**Plan highlights:**
- 14 tasks total, TDD-style (failing tests before implementation)
- Double-submit cookie CSRF enforced only on cookie-authenticated mutating requests
- Security hardening: CSRF checks both access_token AND refresh_token cookies
- Staff engineer + Test engineer review findings: 3 CRITICALs + 9 HIGHs + 12 MEDIUMs all addressed

---

### Epic KAN-457: Platform Observability Infrastructure — ✅ COMPLETE (Sessions 113-129)

> Build the observability substrate every layer (HTTP/auth/DB/cache/external APIs/LLM/agent/Celery/frontend) emits through a single `ObservabilityClient` SDK. Isolated `observability.*` Postgres schema + `obs:*` Redis namespace make the module extractable to a standalone microservice with a single config change. Consumed by both human operators (admin dashboard) and LLM agents (MCP tools) from day one.

**Sub-epics (sequenced):**
- **1a Foundations (KAN-458)** — SDK + DirectTarget + ingest endpoint + trace_id middleware + structured JSON logging + `ObservedHttpClient` wrapping 10 external providers + `external_api_call_log` + `rate_limiter_event` + retention + strangler-fig refactor of existing emitters. **~9-10 days, 6 PRs.**
- **1b Coverage Completion (KAN-459)** — HTTP `request_log` + auth/OAuth/email + DB slow-query/pool/migration + cache + Celery heartbeat + agent intent/reasoning + frontend beacon + deploy_events + PII redaction + Semgrep coverage rules. **~8-10 days, 7 PRs. Blocked by 1a.**
- **1c Agent Consumption + Admin UI (KAN-460)** — 13 MCP tools + CLI `health_report` + anomaly engine + admin REST query endpoints + 8-zone admin dashboard + JIRA draft integration. **~6-8 days, 7 PRs. Blocked by 1b.**

**Why this sequence:** Observability must exist before seed runs (Epic 2 below) so anomalies surface cleanly, and before UI polish (Phase E) so dashboard data is real. User decision captured in Session 112 — "observability on every aspect is the core-objective".

**Session 129 status:**
- **1a COMPLETE** — 6/6 PRs merged (#242-#247, Sessions 114-119)
- **1b COMPLETE** — 7/7 PRs merged (#250-#257, Sessions 120-123) + audit fixes (PR #259, Session 124)
- **1c COMPLETE** — 9/9 items shipped (Sessions 124-129)

**1c PR breakdown (COMPLETE):**
| PR | Scope | Status |
|---|---|---|
| PR1 | Anomaly engine + finding_log + rules 1-6 | ✅ PR #260 (S124) |
| PR2 | Rules 7-12 + auto-close (3 negative checks → resolved) | ✅ #261 (S125) |
| PR3 | MCP tools (13 agent consumption tools) | ✅ #262 (S126) |
| PR4 | CLI health_report script | ✅ #263 (S127) |
| PR5 | Admin REST query endpoints | ✅ #264 (S127) |
| PR6-T1 | Page shell + Zone 1 health strip | ✅ #265 (S127) |
| PR6-T2 | Zones 2-8: error stream, anomaly findings, external API, cost, pipeline, DQ | ✅ #267 (S128) |
| PR6-T5+T6 | Zone 3 enhancements (PATCH ack/suppress, kind filter) + Zone 4 trace explorer (waterfall) | ✅ #268 (S129, KAN-491+KAN-492) |
| PR7 | JIRA draft integration (POST /jira-draft, observed HTTP client, ExternalProvider.JIRA) | ✅ #269 (S129) |

### Epic KAN-493: Observability Suite Validation — ✅ COMPLETE (Sessions 130-133)

> Validates that the 22 PRs of Epic KAN-457 integrate correctly as a system. 48 integration tests across 7 files + production bug fix (asyncpg INTERVAL parameterization) + 4 pre-existing test fixes.
> **Spec:** `docs/superpowers/specs/2026-04-25-observability-integration-test-suite.md`
> **Plan:** `docs/superpowers/plans/2026-04-25-observability-integration-test-suite.md` (v2)

| Ticket | Summary | Status |
|--------|---------|--------|
| KAN-493 | Epic: Observability Suite Validation | ✅ Done |
| KAN-494 | Refinement: Obs Integration Test Suite | ✅ Done |
| KAN-495 | Brainstorm obs integration test architecture | ✅ Done (S130) |
| KAN-496 | Write spec: Obs integration test suite | ✅ Done (S130) |
| KAN-497 | Review spec: Obs integration test suite | ✅ Done (S130) |
| KAN-498 | Write plan: Obs integration test suite | ✅ Done (S130) |
| KAN-499 | Review plan: Obs integration test suite | ✅ Done (S131) |
| KAN-500 | PR1: Fixtures + SDK pipeline + trace propagation | ✅ Done (PR #272, S131) |
| KAN-501 | PR2+PR3: Anomaly lifecycle + admin + MCP + retention | ✅ Done (PRs #273+#274, S132-133) |
| KAN-503 | Bug: schema_versions seed data not visible in tests | To Do (Low) |

**Test files (shipped):**
| File | Tests | What it proves |
|---|---|---|
| `conftest.py` | — | 6 factories, session factory patch, obs table cleanup, admin fixtures |
| `test_sdk_pipeline.py` | 6 | emit → DirectTarget → DB for 5 event types + disabled no-op |
| `test_trace_propagation.py` | 5 | trace ID generation/adoption, `_in_obs_write` guard, auth recursion guard |
| `test_anomaly_lifecycle.py` | 5 | rule→finding→dedup→auto-close→JIRA draft |
| `test_admin_endpoints.py` | 7 | auth enforcement, KPIs, error filtering, finding ack/suppress |
| `test_mcp_tools.py` | 5 | MCP envelope structure for health, trace, anomalies, search, obs-health |
| `test_retention.py` | 21 | regular table purge, allowlist rejection, 18 task existence checks |

**Production bug found:** `INTERVAL :interval` in retention SQL — asyncpg can't parameterize it. Fixed to `make_interval(days => :days)`.

---

### Epic 2: Seed Universe (planned — blocked by Epic 1)

> Rebuild + validate the 10y ticker universe with observability coverage in place. Design work still pending; start after 1a merges so seed runs emit structured events.

### Phase E: UI Overhaul (Epic KAN-400) — IN PROGRESS (Session 135 refinement complete)

> Surface all backend data that has no frontend representation. Session 134 UI walkthrough confirmed all existing pages render correctly with graceful empty states. Session 135 brainstorming refined scope into 3 specs.

**Session 135 corrections:** E-1 (Stock Intelligence) and candlestick toggle already shipped. `usePortfolioAnalytics`, `usePortfolioForecastFull`, `usePortfolioConvergence` already wired on dashboard. Backtesting → admin only (not user-facing). 3-spec split approved.

**JIRA:** KAN-400 (Epic), KAN-505 (Refinement, Done), KAN-511 (Spec A), KAN-512 (Spec B), KAN-513 (Spec C), KAN-504 (test follow-up)

**Spec A — Stock Detail Enrichment** ✅ (KAN-511, PRs #279+#280, Session 136):
- ConvergenceCard + history chart, Forecast Track Record (new `GET /forecasts/{ticker}/track-record` endpoint), SentimentCard + articles, CollapsibleSection extraction, section reorder (13 sections)
- Spec: `docs/superpowers/specs/2026-04-25-ui-overhaul-spec-a-stock-detail-enrichment.md`
- Plan: `docs/superpowers/plans/2026-04-25-ui-overhaul-spec-a-stock-detail-enrichment.md`

**Spec B — Dashboard, Screener & Sectors Enrichment** (KAN-512, ~1.5 days, 1 PR) — **NEXT**:
- ✅ Spec: `docs/superpowers/specs/2026-04-26-ui-overhaul-spec-b-dashboard-portfolio.md`
- ✅ Plan: `docs/superpowers/plans/2026-04-26-ui-overhaul-spec-b-dashboard-portfolio.md`
- 5 changes: portfolio health sparkline, macro sentiment badge, bulk sentiment screener column, sector convergence badges, delete dead `usePortfolioForecast`
- 3 type bugs discovered and planned: `usePortfolioHealthHistory` wrong type, `useBulkSentiment` broken (type + missing param), `NewsSentiment` missing 2 fields
- 6 subtasks: KAN-515 (type fixes), KAN-516 (sparkline), KAN-517 (macro badge), KAN-518 (screener column), KAN-519 (sector badges), KAN-520 (dead code cleanup)

**KAN-514 — Forecast Components Endpoint** (deferred):
- `GET /portfolio/{id}/forecast/components` is a placeholder (returns `components: []`). Needs Prophet per-ticker data populated before frontend can consume it. Tracked separately.

**Spec C — Admin Enhancements** (KAN-513, ~2 days, 1 PR):
- Backtest summary table (admin), command center drill-down fix, audit log viewer

**KAN-504 — E2E/Integration/Playwright tests** (after A+B+C ship, ~2 days)

**Session 134 UI Assessment:** 15 pages walked through with Playwright. 13/15 render correctly. 3 bugs fixed (pipeline_runs columns, nested button, breadcrumb). 6 new E2E test files added (~50 tests). Lighthouse expanded to 12 pages.

**Priority 1 — Backend features with NO frontend UI:**

| # | Feature | Backend Endpoints | Effort Est. |
|---|---------|-------------------|-------------|
| E-1 | **Stock Intelligence Display** | `/stocks/{ticker}/intelligence` (hook exists, no component) | ~1 day |
| E-2 | **Backtesting Dashboard** | `/backtests/run`, `/{ticker}`, `/{ticker}/history`, `/summary/all` | ~2-3 days |
| E-3 | **LLM Admin Console** | 11 endpoints under `/observability/llm/*` (models, tiers, usage, chat sessions, costs) | ~2-3 days |

**Priority 2 — Partial implementations:**

| # | Feature | Gap | Effort Est. |
|---|---------|-----|-------------|
| E-4 | Audit Log Viewer | `/admin/pipelines/audit-log` — no admin UI | ~0.5 day |
| E-5 | Task Status Monitor | `/tasks/{task_id}/status` — no progress UI | ~0.5 day |
| E-6 | Forecast Component Breakdown | `/portfolio/{id}/forecast/components` — no drill-down | ~1 day |
| E-7 | Sentiment Article Browser | `/sentiment/articles` — no listing page | ~1 day |
| E-8 | Command Center Forecast Health | `/admin/command-center/forecast-health` — no panel/hook | ~0.5 day |
| E-9 | System Health Drill-down | Command Center panel has no "View Details" | ~0.5 day |

**Priority 2b — Command Center missing panels (from `command-center-prototype.html`):**

The HTML prototype defined 8 panels but only 4 shipped + 1 partial. Each panel also needs a drill-down sheet (slide-over detail view) like the shipped panels have.

| # | Panel | Backend Schema | Backend Collector | Backend Drill-down | Frontend Component | Frontend Types | Status |
|---|-------|---------------|-------------------|-------------------|-------------------|---------------|--------|
| E-10 | **Cache Performance** | **Missing** | **Missing** | **Missing** | **Missing** | **Missing** | Zero impl |
| E-11 | **Chat & Agent** | **Missing** | **Missing** | **Missing** | **Missing** | **Missing** | Zero impl |
| E-12 | **Auth & Security** | **Missing** | **Missing** | **Missing** | **Missing** | **Missing** | Zero impl |
| E-13 | **Alerts & Forecasting** | `ForecastHealthZone` exists (partial) | `_get_forecast_health_safe()` exists (partial) | **Missing** | **Missing** | **Missing** | Backend partial |

**Per-panel implementation requirements:**

**E-10 Cache Performance** (~1 day):
- Backend: `CachePerformanceZone` schema + `_get_cache_performance()` collector (Redis INFO, DBSIZE, namespace SCAN) + drill-down endpoint
- Data source: Redis `INFO` command (memory, keyspace), `cache_operation_log` obs table (hit/miss rates)
- Frontend: `cache-performance-panel.tsx` + `cache-detail.tsx` + types + hit rate donut chart (Recharts PieChart)
- Prototype: donut (78% hit), namespace list (7 entries), memory bar (45/256 MB)

**E-11 Chat & Agent** (~1.5 days):
- Backend: `ChatAgentZone` schema + `_get_chat_agent()` collector + drill-down endpoint
- Data source: `agent_intent_log`, `agent_reasoning_log`, `tool_execution_log`, `chat_message` tables
- Frontend: `chat-agent-panel.tsx` + `chat-agent-detail.tsx` + types + top tools bar chart (Recharts BarChart)
- Prototype: messages/hr (34, peak annotation), avg response (3.2s P95), tool calls (1247, 78% cached), feedback (89% positive), top 5 tools

**E-12 Auth & Security** (~1 day):
- Backend: `AuthSecurityZone` schema + `_get_auth_security()` collector + drill-down endpoint
- Data source: `auth_event_log`, `login_attempts`, `rate_limiter_event` obs tables, `users` table (active count)
- Frontend: `auth-security-panel.tsx` + `auth-security-detail.tsx` + types
- Prototype: active users (12), login success% (98.5%), failed logins (7), token refresh (45/hr), rate limits (3 today)

**E-13 Alerts & Forecasting** (~1.5 days):
- Backend: Extend `ForecastHealthZone` (add stale/drifting counts, accuracy, VIX) + `AlertsZone` schema + collector + drill-down
- Data source: `finding_log` (anomaly alerts), `in_app_alerts`, `forecast_results`, `backtest_runs`, `model_versions`
- Frontend: `alerts-forecasting-panel.tsx` + detail + types + severity bar chart (Recharts)
- Prototype: severity chart (critical/warning/info), dedup suppressed (23), unread (9), fresh/stale/drifting models, MAPE accuracy, VIX regime

**Also needed for shipped panels — minor enhancements:**
- API Traffic: sparkline area chart (Recharts), P50/P99 in main view
- LLM Operations: provider tab selector (Groq/Anthropic/OpenAI)
- Pipeline: step-by-step execution timeline with per-step timings

**Priority 3 — Original scope (from Frontend Backlog):**
- Stock detail: revenue/margins/growth card, analyst price targets viz, earnings history chart, company profile section, analyst consensus chart, candlestick toggle (KAN-150), benchmark chart (KAN-151)
- Portfolio: strategy picker UI for 3 rebalancing strategies
- Chat: artifact bar enhancements (tool buttons, scroll pill, agent badge, auto-retry)
- Final design polish + accessibility audit

**Blocks:** KAN-363 (Visual Regression), KAN-217 (Playwright E2E Refresh), KAN-216 (Frontend component tests)
**Note:** AccuracyBadge + ForecastCard MAPE badge already wired in Session 94 (KAN-393/398). Security bugs + tech debt cleared.

### Phase F: Subscriptions + Monetization (~5 days) — No JIRA tickets yet

> Stripe integration, tier enforcement, pricing. **Depends on Phase C ✅ + Phase D ✅.**

| # | Task | Brainstorm? | Effort |
|---|------|-------------|--------|
| F1 | Tier definitions (Free/Pro/Premium), quotas, pricing | **Business** | ~0.5 day |
| F2 | Stripe integration, webhooks, lifecycle | **Technical** | ~0.5 day |
| F3 | User model: subscription_tier, stripe_customer_id, migration | No | ~0.5 day |
| F4 | Stripe checkout + webhook endpoints | No | ~1.5 days |
| F5 | SubscriptionGuard middleware: tier + quota enforcement | No | ~1 day |
| F6 | LLM tier routing: free users → cheap models | No | ~0.5 day |
| F7 | Frontend: pricing cards, usage meter, billing page | No | ~1 day |

### Phase G: Cloud Deployment (~4 days) — No JIRA tickets yet

| # | Task | Brainstorm? | Effort |
|---|------|-------------|--------|
| G1 | Cloud provider selection (Azure/AWS/GCP), managed services | **Technical** | ~0.5 day |
| G2 | Docker Compose: all services containerized (inc. MCP Tool Server) | No | ~1 day |
| G3 | MCP transport swap: stdio → Streamable HTTP (config change only) | No | ~0.5 day |
| G4 | Terraform / IaC for cloud infra | No | ~1.5 days |
| G5 | deploy.yml: wire actual CI/CD deployment | No | ~0.5 day |

### Phase H: Comparison Fan-Out (optional, ~2 days) — No JIRA tickets yet

Parallel multi-ticker analysis with concurrency control. Data-driven activation — only if eval scores warrant it per multi-agent decision gate.

---

## Open Bugs (Session 95 — Data Reseed DQ Findings)

| Ticket | Priority | Summary | Status |
|--------|----------|---------|--------|
| KAN-401 | High | News pipeline: tz mismatch on NewsArticle timestamps (published_at + scored_at) | Hotfix applied, proper migration needed |
| KAN-402 | Medium | Google News RSS source_url exceeds VARCHAR(500) | Hotfix applied, column migration needed |
| KAN-403 | High | Prophet forecast produces negative stock prices for 6 tickers | ✅ Done — PR #192 (Session 96) |
| KAN-404 | High | Pipeline integrity: non-universe tickers missing data (7 gaps) | ✅ Done — PR #192 (Session 96) |

## Enhancements (Session 95)

| Ticket | Priority | Summary | Status |
|--------|----------|---------|--------|
| KAN-405 | Medium | Sentiment scoring: concurrent batch dispatch + larger batch size | Superseded by KAN-434 (Spec B4) |
| KAN-406 | Low | SPY ETF 2y history misaligned with 10y universe for QuantStats | ✅ Done — PR #238 (Session 111) |

## Tech Debt

All prior tech debt resolved in Session 94 (PR #189). KAN-398 absorbed into KAN-393.

## Backlog (JIRA tickets, not yet scheduled)

| Ticket | Summary | Notes |
|--------|---------|-------|
| KAN-157 | Live LLM eval tests in CI | Needs CI_GROQ_API_KEY + CI_ANTHROPIC_API_KEY secrets |
| KAN-162 | Langfuse Self-Hosted Integration | Visual trace debugging UX — partially done |
| KAN-211 | Test Suite Hardening Epic (KAN-212–216) | 5 stories: tool orchestration, pipeline mocks, error paths, ReAct integration, frontend components |
| KAN-217 | Playwright E2E Refresh | Blocked on KAN-400 (UI Overhaul) — POM selectors will change |

## Parking Lot

- Schwab CSV import — parse "Positions" export, create BUY transactions
- ForecastCard currentPrice display — signal schema doesn't expose it
- Forecasts blended into composite score — deferred pending accuracy validation
- Telegram alerts — deferred, in-app only for now
