## Project State (Session 97)

**Current phase:** Completing Epic KAN-408 (Backend Code Health & Security Hardening)
**Resume point:** Execute `docs/superpowers/plans/2026-04-06-backend-code-health-final.md` (14 tasks) for KAN-412, KAN-413, KAN-417. Then Phase E (UI Overhaul KAN-400) → Phase F (Subscriptions).
**Branch:** `develop` — Session 97 was spec/plan work only, no code changes yet
**Latest merged:** PRs #198-200 (KAN-407, 409, 410, 411, 414, 415, 416, 418 — backend code health batches 1-3)

### Session 97 Summary — KAN-408 Spec + Plan
- Brainstormed KAN-412 (auth router split), KAN-413 (portfolio service split), KAN-417 (CSRF protection)
- Design decisions: 7 auth sub-modules (core, email_verification, password, oauth, oidc, admin, _helpers), 3 portfolio sub-modules (core, fifo, analytics), double-submit cookie CSRF
- Spec written: `docs/superpowers/specs/2026-04-06-backend-code-health-final.md`
- Plan written: `docs/superpowers/plans/2026-04-06-backend-code-health-final.md` (14 tasks)
- 2 rounds of staff + test engineer reviews — 3 CRITICALs fixed (middleware ordering, _helpers re-export pattern, dead /health path), plus 9 HIGHs + 12 MEDIUMs
- Upstream/downstream dependency audit found 3 gaps (backend/tools/portfolio.py re-exports _group_sectors and _get_transactions_for_ticker — both added to __init__.py re-exports)
- **Security hardening:** CSRF middleware now checks BOTH access_token AND refresh_token cookies (attacker with only refresh cookie must not bypass CSRF)
- JIRA comments added to KAN-412, 413, 417 with spec/plan links

### Key Facts
- Alembic head: `b2351fa2d293` (migration 024)
- Tests: 1906 backend unit + 439 frontend + 38 API + 48 E2E + 27 nightly = ~2458 total
- Coverage: ~69% (floor 60%)
- Internal tools: 25 + 4 MCP adapters
- Docker: Postgres 5433, Redis 6380, Langfuse 3001+5434
- Skills/rules audit Session 96: ~1,500 tokens/interaction saved
- ADRs: 11 total

### Open JIRA (Epic KAN-408 remaining)
- **KAN-412 (HIGH):** Split oversized routers (auth.py 1263L, portfolio.py 776L) — Refinement complete, Ready for implementation (tasks 1-5)
- **KAN-413 (HIGH):** Split portfolio service into focused modules — Refinement complete, Ready for implementation (tasks 6-8)
- **KAN-417 (MEDIUM):** Add CSRF protection for cookie-based auth — Refinement complete, Ready for implementation (tasks 9-13)

### Other Open JIRA
- KAN-400: Phase E UI Overhaul (Epic) — To Do
- KAN-398: Wire AccuracyBadge into forecast-card.tsx — To Do
- KAN-405: Sentiment scoring concurrent batch dispatch — To Do
- KAN-406: SPY ETF 2y history misalignment — Low priority
- KAN-211: Test Suite Hardening Epic (5 stories KAN-212-216)
- KAN-217: Playwright E2E Refresh (blocked on KAN-400)
- KAN-363: Visual Regression (blocked on KAN-400)
- KAN-157: Live LLM eval tests in CI
- KAN-162: Langfuse self-hosted integration

### Recently Completed (Sessions 92-97)
- Session 92: Workflow optimization system (PR #188)
- Session 93: LLM benchmark research
- Session 94: Bug sweep + tech debt clearout (PR #189)
- Session 95: Full data reseed + DQ analysis (KAN-401-406 filed)
- Session 96: Pipeline integrity + skills audit (PR #192, KAN-403/404)
- Session 97 (in progress): KAN-408 spec + plan (this session)
- KAN-407, 409, 410, 411, 414, 415, 416, 418 already merged (PRs #198-200, backend code health batches)

### Next Steps
1. **Execute KAN-408 plan** — 14 tasks, ship via subagent-driven-development or inline execution
2. **Phase E (UI Overhaul KAN-400)** — after KAN-408 ships
3. **Phase F (Subscriptions + Monetization)** — post Phase E
4. **Phase G (Cloud Deployment)** — final phase
