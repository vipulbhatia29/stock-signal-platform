# Project State — Stock Signal Platform

**Last updated:** Session 101 (2026-04-07) — KAN-422 Spec B B1+B2+B4+B5 ready to push (PR pending)

## Current phase
Pipeline Architecture Overhaul (Epic KAN-419) — **Spec A done (PR #206), Spec B B3 done (PR #207), Spec B B1+B2+B4+B5 ready to push** (this session). After PR merge: 5 children remaining (Spec C/D/E/F/G/Z = KAN-420, 423-427).

## Branch / repo state
- Active branch: `feat/KAN-422-spec-b-completeness` (29 commits ahead of develop)
- Latest commit on branch: `b8d5e68` — `style: fix E501 line-too-long in beat schedule and concurrent batch test (Spec B)`
- Latest develop tip: `12fcbe4` — `[KAN-422 / B3] Prophet sentiment predict-time fix (#207)`
- Alembic head: `e1f2a3b4c5d6` (migration 025 — `ticker_ingestion_state` table) — no migration in this PR

## Test counts (post Session 101 fixes)
- Backend unit: **1945** (+13 net from Session 99 baseline 1932)
- API: **428+** (+31+ from baseline 397; convergence/backtest/drift/ingest extension)
- Frontend: 439
- E2E: 48
- Nightly perf: 27
- **Total: ~2887+**

## What shipped this session (still on branch — pending push + PR merge)
- **B1 (KAN-431)** — Real `compute_convergence_snapshot_task` (universe + single mode), backfill 90d/180d, mark_stage for ALL requested tickers, partial-failure isolation. Wired into nightly chain Phase 3.
- **B2 (KAN-432)** — `BacktestEngine.run_walk_forward` (asyncio.to_thread Prophet), real `_run_backtest_async` with per-ticker isolation + ModelVersion lookup, weekly Saturday 03:30 ET beat schedule, drift consumer regression test.
- **B4 (KAN-434)** — Concurrent `score_batch` with `asyncio.gather` + `Semaphore(NEWS_SCORING_MAX_CONCURRENCY=5)`.
- **B5 (KAN-435)** — `news_ingest_task` tickers param + `ingest_ticker` Steps 6b/8/9/10 (mark_stage + new-ticker dispatch fanout).
- **Final.1** — 3 feature flags with rollback semantics + `.env.example` doc.

## Open follow-up tickets to file (post-merge)
- **KAN-perf-mark-stages-bulk** — bulk `mark_stages_updated(tickers, stage)` helper (500 → 1 query)
- **KAN-perf-walk-forward-sentiment** — pre-load sentiment per ticker not per window (~55k → ~500 queries on weekly run)
- **KAN-perf-backtest-session-per-ticker** — open fresh DB session per ticker iteration in `_run_backtest_async`
- **KAN-backtest-degraded-status** — return `status="degraded"` when `failed > 0`
- **KAN-backtest-unique-constraint** — add `(ticker, model_version_id, test_end, horizon_days)` UniqueConstraint + upsert (drift uses MIN so correctness preserved, but disk grows)
- **KAN-backtest-time-limit** — Celery `time_limit` on `run_backtest_task`
- **KAN-backtest-sentiment-helper-dedup** — consolidate `_fetch_sentiment_for_window` into `_fetch_sentiment_regressors` (DRY)
- **KAN-pyright-tools-forecasting** — same `pd.Index(...)` wrap needed at `backend/tools/forecasting.py:508` (KAN-428 sub-item)
- **KAN-test-forecast-tz-flake** — pre-existing `test_forecast_has_correct_fields` fails on develop too (ET production code vs UTC `date.today()` test assertion)

## Carry-over from Session 99
- **KAN-428** (Medium, ~2-3h) — pyright cleanup, 6 errors tagged TODO + the new follow-up above
- **KAN-429 (HIGH)** — JIRA automation mass-close bug; **every PR merge requires post-merge JQL audit** until fixed
- **KAN-430** (Low, ~1h) — Worktree tooling defaults to main instead of develop

## Resume options after this PR merges
1. **KAN-427 (Spec Z Quick Wins)** — independent, low risk
2. **KAN-420 (Spec D Admin + Observability)** — depends on Spec A; adopts `@tracked_task` (the deferral noted in this PR — apply to async helpers, NOT sync Celery wrappers) and `task_tracer` across tasks
3. Spec C/E/F/G of the Pipeline Overhaul

## Hard rule reminders
- Branch from `develop`, never `main`
- All PRs target `develop`
- `uv run` for all Python commands
- No `str(e)` in user-facing strings
- Mock at lookup site, not definition site
- DB-hitting tests in `tests/api/`, mock-only in `tests/unit/`
- **PR body NEVER includes sibling KAN-xxx links** (KAN-429 mass-close bug)

## Spec A primitives still in use
- `mark_stage_updated(ticker, stage)` from `backend.services.ticker_state` — fire-and-forget with own session
- `get_all_referenced_tickers(db)` from `backend.services.ticker_universe`
- `@tracked_task` from `backend.tasks.pipeline` — **only wraps async callables**; do NOT apply to sync Celery wrappers (Spec D will wire onto `_compute_convergence_snapshot_async` / `_run_backtest_async` directly)
- `StalenessSLAs` from `backend.config.settings.staleness_slas`
- `langfuse_service` + `observability_collector` module-level singletons

## Lessons / pitfalls captured this session
- **`mark_stage_updated` opens its own session** — do NOT add a `db.commit()` after it expecting the writes to land via the caller's session; they're already committed.
- **`_fetch_sentiment_for_window` was duplicated** instead of reusing `_fetch_sentiment_regressors` — caught in persona review, deferred to follow-up. Lesson: when the spec says "follow the same pattern as B3," explicitly check the existing function and prefer extension over duplication.
- **`@tracked_task` decorator types**: only `Callable[..., Awaitable[R]]`. Wrapping a sync Celery entrypoint is architecturally incorrect — defer to Spec D and wire onto the async helpers.
- **Beat schedule collisions** are easy to introduce. Run a full audit of `crontab(...)` entries after adding any new one.
- **5-persona pre-push review** caught 1 BLOCKING + 5 HIGH that would have shipped. The same code with all per-task spec reviews + lint + tests still let those bugs through. The persona review is load-bearing.
