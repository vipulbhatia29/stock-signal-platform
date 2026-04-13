# Project State — Stock Signal Platform

**Last updated:** Session 107 (2026-04-12) — KAN-424 Spec E shipped (PR #225 merged)

## Current phase
Pipeline Architecture Overhaul (Epic KAN-419) — **Specs A/B/D/E/F all Done.** Spec C (Entry Points) split into 4 subtasks (KAN-449 through KAN-452), ready to start.

## Branch / repo state
- Active branch: `develop` (clean after PR #225 merge)
- Latest develop tip: `665b6d4` — `[KAN-424] feat: forecast quality & scale (#225)`
- Alembic head: migration 027 (`dq_check_history`)
- PRs merged: #1-225

## Test counts (Session 107)
- Backend unit: **2037** (+14 from Session 106 baseline 2023)
- API: **448**
- Frontend: 439
- E2E: 48
- Nightly perf: 27

## What shipped recently (Sessions 105-107)
- **KAN-412/413/417** — Split oversized modules + CSRF (PR #217)
- **KAN-428** — Pyright fixes (PR #218)
- **KAN-427 Z1-Z6** — Quick wins: registry typo, dead stub, task rename, cache invalidation, WelcomeBanner (PRs #219, #221)
- **KAN-425** — Redis TokenBucketLimiter for yfinance + news + ingest (PR #220)
- **KAN-446** — DQ Scanner: 10 nightly checks + DqCheckHistory model (PR #222)
- **KAN-447** — Retention: purge forecasts 30d + news 90d (PR #223)
- **KAN-424** — Forecast Quality: cap 100, weekly retrain, fast/slow split, Phase 1.5 (PR #225)

## KAN-423 Spec C split (next up)
| Subtask | Scope | Status |
|---------|-------|--------|
| KAN-449 | C1+C6: Watchlist auto-ingest + Redis dedup | To Do |
| KAN-450 | C2+C3: Portfolio sync-ingest + Chat canonical ingest | To Do (blocked by 449) |
| KAN-451 | C4: Stale auto-refresh + Redis debounce | To Do (blocked by 449) |
| KAN-452 | C5: Bulk CSV upload | To Do (blocked by 449) |

Plan: `docs/superpowers/plans/2026-04-06-pipeline-overhaul-plan-C-entry-points-v2.md`

## Open backlog
- **KAN-429 (HIGH)** — JIRA automation mass-close bug (8 incidents). Post-merge JQL audit mandatory.
- **KAN-426 (Medium)** — Frontend polish
- **KAN-448 (Low)** — TimescaleDB compression

## Hard rule reminders
- Branch from `develop`, never `main`
- All PRs target `develop`
- No `str(e)` in user-facing strings
- Mock at lookup site, not definition site
- PR body NEVER includes sibling KAN-xxx links (KAN-429 mass-close bug)
- Sonnet for implementation, Opus for reviews
