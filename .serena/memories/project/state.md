# Project State (updated Session 148, 2026-05-02)

## Current Phase
Sprint 1 of execution order — fix broken data (KAN-568, KAN-558).

## Last Session (Session 148)
- **KAN-557 shipped** (PR #299 merged) — historical features ADX/OBV/MFI + daily task wired
- **KAN-554 Epic COMPLETE** — all 3 PRs shipped (#297, #298, #299)
- **Gap analysis:** forecast pipeline (6 gaps → Epic KAN-562), chart UX (KAN-559), portfolio data ($44K vs $85K → KAN-568)
- **Decisions:** FinBERT replaces GPT-4o-mini, ETFs must be imported, data-first execution order
- **JIRA:** 10 created (KAN-559-568), 5 closed (429, 529, 550, 551, 553), KAN-546 scoped to chat

## Epic Status
- **KAN-554** (Signal Scoring) — ✅ COMPLETE
- **KAN-562** (Forecast Pipeline v2) — To Do, 6 stories (KAN-563-568)
- **KAN-548** (Forecast Redesign) — In Progress (PR3 frontend pending)
- **KAN-400** (UI Overhaul) — To Do, KAN-559 (chart) + 15 open tasks
- **KAN-211** (Test Hardening) — Deferred to Sprint 7

## Test Counts
- Unit: 2742 (0 failures)
- Integration: 78, API: 454, Frontend: 551

## Alembic Head
Migration 045 (rev `0ff65ce55dc5`)

## Execution Order (PM-approved)
Sprint 1: KAN-568 + KAN-558 (fix data)
Sprint 2: KAN-564 (FinBERT + sentiment)
Sprint 3: KAN-563, 565, 566 (forecast features + validation)
Sprint 4: KAN-559, 532, 540 (stock detail + chart)
Sprint 5: KAN-535-537, 533, 534, 541 (portfolio + screener + nav)
Sprint 6: KAN-538, 545, 544, 539, 543, 542 (sectors + admin)
Sprint 7: KAN-567, 211, 217, 363 (tuning + test infra)

## Resume Point
Sprint 1: KAN-568 (fix portfolio data — ETF parser, auto-backfill, reconciliation)