# Pipeline Overhaul — Review Resolutions (CRITICAL only)

**Date:** 2026-04-06
**Scope:** Applied CRITICAL findings from the three review files
(`review-staff-engineer.md`, `review-test-engineer.md`, `review-efgz.md`)
as inline, surgical edits to the Spec + Plan documents. HIGH/MEDIUM/LOW
findings are deferred to JIRA for implementation-time fixing.

## Resolution table

| # | Finding | Files touched | Status |
|---|---|---|---|
| 1 | `task_tracer` import path locked to `backend/services/observability/task_tracer.py` | Spec B, Plan B (×3), Plan D | RESOLVED |
| 2 | `mark_stage_updated` signature locked to 2-arg form (opens its own session) | Spec B, Plan B | RESOLVED |
| 3 | `"recommendation"` added to Spec A `Stage` Literal + `_STAGE_COLUMNS` + SQL + model | Spec A, Plan B | RESOLVED |
| 4 | `tracked_task` decorator signature locked to `(pipeline_name, *, trigger=...)` (no `scope=`, no `tracer=`) | Spec D, Plan D | RESOLVED |
| 5 | `task_tracer` / `trace_task` locked to **async** context manager; Spec D annotated to translate `with` sketches to `async with trace_task(...)` | Spec D, Plan D (Task 1 + nightly chain rewrite) | RESOLVED |
| 6 | Plan D's references to nonexistent `start_span` / `start_generation` / `record_generation` removed; consumer test rewritten to use real `create_trace` / `handle.record_llm` / `handle.add_metadata` API | Plan D (Task 1) | RESOLVED |
| 7 | `last_error JSONB NULL` column + `recommendation_updated_at` column added to Spec A migration DDL and SQLAlchemy model | Spec A §A1 | RESOLVED |
| 8 | `langfuse_service` + `observability_collector` module-level singletons and setters added to Spec A `task_tracer.py`; Plan D Task 1 now publishes them from `main.py` lifespan | Spec A, Plan D (Task 1) | RESOLVED |
| 9 | Plan A `error_summary` leak test rewritten to assert no `"hunter2"` / `"secret db password"` / `"RuntimeError"` in the persisted redacted `error_summary`; companion real-DB integration test `tests/api/test_tracked_task_error_redaction.py` added (new Task 7) | Plan A | RESOLVED |
| 10 | (a) Plan A Task 7 extends `tests/unit/conftest.py` with a `db_session` guardrail. (b) Plan B test file list rewritten: all `db_session`-using tests moved from `tests/unit/tasks/` / `tests/unit/services/` to `tests/api/`. (c) Plan C adds a note that `tests/unit/services/test_watchlist_ingest.py` + `test_bulk_import.py` MUST use `MagicMock` sessions only. Plan D is already clean (AST + pure mocks). | Plan A, Plan B, Plan C | RESOLVED |
| 11 | Plan B Task B3.1 Prophet sentiment regression test replaced with a deterministic synthetic-correlation test (200 days, known beta) that asserts the zeroed-regressor path produces materially different yhat values | Plan B | RESOLVED |
| 12 | Plan C `tests/unit/tools/test_analyze_stock.py` retargeted to `tests/api/test_analyze_stock_tool.py`; legacy `tests/unit/test_analyze_stock_autoingest.py` scheduled for deletion | Plan C (Task 4) | RESOLVED |
| 13 | Plan C undefined `seed_stock_with_last_fetched` fixture replaced with inline `db_session.add(Stock(...))` factory usage | Plan C | RESOLVED |
| 14 | Plan C Task 1 Step 0 added: `ingest_ticker` import lands in `backend/services/watchlist.py` BEFORE the failing tests are written (so `patch.object(wl_mod, "ingest_ticker", ...)` resolves) | Plan C | RESOLVED |
| 15 | Plan B Task B5.4 patch path corrected: `backend.services.pipelines.news_ingest_task.delay` (lookup site), NOT `backend.tasks.news_sentiment.news_ingest_task.delay`; same correction for convergence + retrain + error-path test | Plan B | RESOLVED |
| 16 | Spec D cache-invalidator coverage test heuristic replaced with a strict AST walk (`ast.Call` with `.func.attr == "add"` + guarded model class) scanning siblings in the same `FunctionDef` for a matching `await cache_invalidator.on_*` call; false-positive "add(" substring match removed | Spec D | RESOLVED |
| 17 | Spec D + Plan D `PipelineTaskTriggerRequest` — `extra_kwargs: dict[str, Any]` removed; `model_config = {"extra": "forbid"}` added; only `ticker` flows into the Celery kwargs dict. Frontend TS interface also cleaned up. | Spec D, Plan D | RESOLVED |
| 18 | Spec C Redis SETNX dedup added (`ingest:in_flight:{ticker}` TTL 60s). Plan C Watchlist Step 3 now acquires/releases an `ingest_lock`; contention raises `IngestInProgressError` which the router maps to a 409 with a generic message | Spec C §C1, Plan C | RESOLVED |
| 19 | Spec C error messages already generic (`"not recognized"`, `"Could not load market data"`); added explicit Hard Rule #10 reminder; `exc.step` only logged internally, never surfaced. No user-visible message includes the failing step. | Spec C | RESOLVED (already compliant; note added) |
| 20 | Spec E + Plan E: `Semaphore(10)` → `Semaphore(5)` to match Postgres `pool_size=5, max_overflow=10` effective pool of 15, not the phantom "max 20". Per-cycle estimate updated from 60s → 120s; default setting updated. | Spec E §E3, Plan E | RESOLVED |
| 21 | Spec F + Plan F migration 027 `downgrade()` now walks every compressed chunk via `decompress_chunk` in a `DO $$ ... $$` loop BEFORE clearing `timescaledb.compress = false`. Explicit note added that the old flag-only downgrade was query-broken against pre-compressed chunks. | Spec F §F6, Plan F Task 8 | RESOLVED |
| 22 | Plan G Vitest → Jest: `import from "vitest"` blocks removed; `vi.fn()` / `vi.useFakeTimers()` / `vi.useRealTimers()` / `vi.advanceTimersByTimeAsync` / `vi.setSystemTime` replaced with `jest.*`. Header comments added explaining `describe`/`it`/`expect` are Jest globals. | Plan G | RESOLVED |
| 23 | Spec Z + Plan Z explicit sequencing gate: Z3 news-ingest cap 50→200 MUST merge AFTER Spec F2 + F3 rate limiters. Fallback rule: set cap to 50 until F2/F3 deploy. | Spec Z §Z3, Plan Z Task 3 | RESOLVED |
| 24 | Migration revision-ID convention: Plan A already uses hash IDs. Plan F (Tasks 7 + 8) + Spec F §F6 now explicitly reference `<hash-A>`, `<hash-F26>`, `<hash-F27>` placeholders and document the chain; numeric slugs are labelled as filename prefixes only. | Plan F, Spec F | RESOLVED |
| 25 | Spec D `latency-trends` query — verified that `backend/models/pipeline.py` defines `total_duration_seconds: Mapped[float \| None]` at line 42. The column exists. No spec/plan change required. | — | NO-OP (verified) |

## Deferred (not CRITICAL)

HIGH / MEDIUM / LOW findings from all three reviews are not applied here —
they will be filed as JIRA subtasks under the pipeline overhaul epic and
resolved at implementation time alongside the code changes.

## Verification notes

- `backend/models/pipeline.py` — confirmed `total_duration_seconds` column
  exists (line 42), so Spec D's `latency-trends` SQL is valid as-written.
- `backend/observability/langfuse.py` — Spec A's `task_tracer` uses
  `create_trace` (the real method); Plan D's nonexistent `start_span` /
  `start_generation` references have been removed.
- `tests/unit/conftest.py` — already guards `client` / `authenticated_client`;
  Plan A Task 7 extends the same pattern to `db_session`.
- `tests/unit/test_analyze_stock_autoingest.py` exists — Plan C now explicitly
  deletes it before creating the new `tests/api/test_analyze_stock_tool.py`.
