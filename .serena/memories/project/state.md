# Project State (updated Session 108, 2026-04-12)

## Current Phase
Pipeline Architecture Overhaul — Epic KAN-419, Spec C (Entry Points)

## Active Branch
`feat/KAN-450-portfolio-chat-ingest` (ready for commit+PR)

## Last Shipped
- KAN-450 (C2+C3: Portfolio sync-ingest + Chat canonical ingest) — Session 108
- KAN-449 (C1+C6: Watchlist auto-ingest + Redis dedup) — Session 108, PR #229

## Test Counts
- Unit: 2060 passed, 1 pre-existing failure (`test_forecast_has_correct_fields`)
- API: 448

## Resume Point
KAN-451 (C4: Stale auto-refresh + Redis debounce, PR3 of Spec C)
KAN-452 (C5: Bulk CSV upload, PR4 of Spec C)
Both are now unblocked.

## Alembic Head
Migration 027 (dq_check_history) — no new migrations in S108

## Open Work
- KAN-451 (C4: stale auto-refresh) — unblocked
- KAN-452 (C5: bulk CSV) — unblocked
- KAN-429 (JIRA automation bug) — High, unblocked
- KAN-426 (frontend polish, Spec G) — blocked by Spec C
- KAN-448 (TimescaleDB compression) — Low
