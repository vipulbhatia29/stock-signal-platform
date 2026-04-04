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

---

### Phase E: UI Overhaul (Epic KAN-400) — To Do

> Surface all backend data that has no frontend representation. Prerequisite for visual regression baseline (KAN-363) and Playwright E2E refresh (KAN-217).

**Scope (from Frontend Backlog):**
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

## Open Bugs

All bugs resolved in Session 94 (PR #189).

## Tech Debt

All tech debt resolved in Session 94 (PR #189). KAN-398 absorbed into KAN-393.

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
