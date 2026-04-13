# Project State (updated Session 108, 2026-04-12)

## Current Phase
Pipeline Architecture Overhaul — Epic KAN-419, Spec C (Entry Points)

## Active Branch
`feat/KAN-449-watchlist-auto-ingest` (ready for commit+PR)

## Last Shipped
- KAN-449 (C1+C6: Watchlist auto-ingest + Redis dedup) — Session 108
- KAN-424 (Spec E: Forecast quality & scale) — Session 107

## Test Counts
- Unit: 2052 passed, 1 pre-existing failure (`test_forecast_has_correct_fields`)
- API: 448

## Resume Point
KAN-450 (C2+C3: Portfolio sync-ingest + Chat canonical ingest, PR2 of Spec C)
Blocked by: KAN-449 merge

## Alembic Head
Migration 027 (dq_check_history) — no new migrations in S108

## Open Work
- KAN-450 (C2+C3) — blocked by KAN-449
- KAN-451 (C4: stale auto-refresh) — blocked by KAN-449
- KAN-452 (C5: bulk CSV) — blocked by KAN-449
- KAN-429 (JIRA automation bug) — High, unblocked
- KAN-426 (frontend polish, Spec G) — blocked by Spec C
- KAN-448 (TimescaleDB compression) — Low
