# Pipeline Overhaul — Test Engineer Review (Specs A–D)

**Reviewer:** Test Engineer (Opus)
**Date:** 2026-04-06
**Scope:** Specs A/B/C/D and matching plans for the pipeline overhaul epic.
**Method:** Audited mock paths, test placement vs the `tests/unit/` xdist guardrail (PR #204), coverage gaps, fixture impact, and timing-flake risk. Cross-checked existing tests under `tests/unit/`, `tests/api/`, and `tests/conftest.py`.

> Reference: `~/.serena/memories/global/debugging/mock-patching-gotchas` — patch at the **lookup site**, not the definition site. Reference: `tests/unit/conftest.py:46-63` — `client` and `authenticated_client` are banned in `tests/unit/`. The same race risk applies in spirit to `db_session` because the root conftest does not isolate sessions per worker (only the `client` fixture truncates after each test).

---

## Spec / Plan A — Ingestion Foundation

### CRITICAL

**A-TEST-CRIT-1 — `task_tracer` test mocks `LangfuseService.create_trace` but the service's real method may not exist with that signature.**
- Plan A test (`tests/unit/services/test_task_tracer.py`, plan lines 1400-1419) calls `langfuse.create_trace(trace_id=..., session_id=..., user_id=..., metadata=...)` and verifies via `_make_langfuse(trace_obj)` whose `create_trace` is a `MagicMock`. The plan never patches the **definition site** but constructs a `MagicMock()` and passes it as the `langfuse` argument — this is fine because the SUT consumes the dependency by parameter, not by import. **However**, the production code path for `langfuse_service` is a singleton imported elsewhere (Spec D Plan uses `patch("backend.tasks.tracing.langfuse_service")`). The two specs disagree on whether `langfuse_service` is a parameter or a module-level singleton. See A-TEST-CRIT-2.
- **Fix:** Spec A's tracer takes `langfuse` as a parameter — keep the parameterised mocks. Add a test that imports `backend.observability.langfuse` and confirms the **module exposes a singleton** (`langfuse_service = LangfuseService(...)`) so Spec D's `patch("backend.tasks.tracing.langfuse_service")` will work after import re-export.

**A-TEST-CRIT-2 — Spec A and Spec B/D disagree on the import paths of every Spec A primitive.**
- Spec A places:
  - `tracked_task` in `backend/tasks/pipeline.py`
  - `mark_stage_updated` in `backend/services/ticker_state.py`
  - `trace_task` in `backend/services/observability/task_tracer.py`
- Spec B (line 171-172, 257-258, 469-470, 1120) imports them from:
  - `backend.observability.task_tracer` (wrong)
  - `backend.services.ingestion_state` (wrong — the module is `ticker_state`)
- Spec D (Plan D Task 2, line 284-285) imports them from:
  - `backend.tasks.tracking` (wrong — should be `backend.tasks.pipeline`)
  - `backend.tasks.tracing` (a third, completely new module)
- Effect: every test that uses `patch("backend.observability.task_tracer.tracked_task")` or `patch("backend.tasks.tracking.tracked_task")` will fail with `ModuleNotFoundError` or `AttributeError`. This breaks the entire B/C/D test sequence.
- **Fix:** Pick canonical paths (Spec A's are correct) and search-and-replace across Spec B/C/D specs and plans before any implementation begins. Add a regression test in Plan A Task 7 that imports each primitive from its canonical path; this will fail loudly if a later spec re-locates them.

**A-TEST-CRIT-3 — `mark_stage_updated` signature mismatch.**
- Spec A defines `async def mark_stage_updated(ticker: str, stage: Stage)` (no DB session arg) — opens its own session via `async_session_factory()`.
- Spec B (line 260, 546, 549, 1130, 1132) calls `await mark_stage_updated(db, ticker, "convergence")` (3 args including session).
- Plan B Task B1.4 (line 269) follows Spec B's incorrect 3-arg shape.
- Effect: every Plan B test asserting `mark_stage_updated` was called with `(db, ticker, stage)` will pass against the wrong implementation, then fail when wired to Spec A's real function. Worse: the production call sites raise `TypeError` immediately at runtime.
- **Fix:** Decide one shape. Recommendation: keep Spec A's 2-arg API (cleaner, matches the fire-and-forget contract). Update Spec B/Plan B and rewrite the test assertions to use `mock_mark.assert_awaited_with(ticker, "convergence")`.

**A-TEST-CRIT-4 — `"recommendation"` is not a valid `Stage` Literal.**
- Spec A defines `Stage = Literal["prices", "signals", "fundamentals", "forecast", "forecast_retrain", "news", "sentiment", "convergence", "backtest"]` (9 values) — no `"recommendation"`.
- Spec B (line 578) instructs `await mark_stage_updated(db, ticker, "recommendation")`.
- Plan B Task B5.4 (line 1162) and the test in Task B5.3 (line 1083) assert `mark_stage_updated` is called for `"recommendation"`. The Literal type-check will fail in mypy/pyright; Plan A's `_STAGE_COLUMNS` lookup will `KeyError` at runtime; the unit test will pass against the mock and crash in production.
- **Fix:** Either add `"recommendation": "recommendation_updated_at"` to Spec A's enum + table column, or drop the `mark_stage_updated("recommendation")` call from Spec B. Per Spec A §A1 the table tracks ingestion stages only, so dropping it is the correct call.

**A-TEST-CRIT-5 — Plan A `test_tracked_task_marks_failed_on_exception` mocks `pipeline.async_session_factory` but the SUT imports it inside the function body.**
- Plan A line 1167-1169:
  ```python
  with patch.object(pipeline, "async_session_factory", return_value=FakeSession()):
  ```
- This patches the **module attribute** on `backend.tasks.pipeline`. That works only if `pipeline.py` does `from backend.database import async_session_factory` at module top — confirmed needed by Plan A Step 3 line 1244. Good.
- But the test substitutes a `FakeSession()` instance whose `__aenter__` returns `self` and `execute` calls `stmt.compile().params`. SQLAlchemy `update(...).values(...)` does **not** materialise `error_summary` into `compile().params` for a JSONB column the same way as for scalar columns — `params` will contain a `BindParameter` reference, not the dict. The assertion `"secret db password" not in joined` will pass trivially because the dict was never serialised. This test does **not** actually verify Hard Rule #10.
- **Fix:** Replace the AST/params interception with a direct capture: monkey-patch `pipeline.update` to a fake that records `kwargs`, or use a recording session that captures the literal call args. Better: add an assertion that the rendered SQL string `str(stmt.compile(compile_kwargs={"literal_binds": True}))` does not contain `"hunter2"`.

### HIGH

**A-TEST-HIGH-1 — Decorator tests use `patch.object(pipeline.PipelineRunner, "start_run", new=AsyncMock(...))` but `tracked_task` instantiates `PipelineRunner()` once per decorator invocation, capturing the **unpatched** instance.**
- Plan A line 1283 (`runner = PipelineRunner()` inside `decorator`) and lines 1083-1087: the patch is applied via `patch.object(pipeline.PipelineRunner, ...)`, which patches the **class attribute** — newly-created instances see the mock because they look up `start_run` via class lookup. This is correct. **But** the decorator binds `runner` at decoration time, and the tests apply the patch *before* the `@pipeline.tracked_task("p")` decoration inside the `with` block. Order is OK here.
- The risk is if a future caller decorates **at module import time** (which is the documented adoption pattern for production code in Spec D). Then `runner` is created against the unpatched class and the test pattern `patch.object(PipelineRunner, ...)` works, but `patch.object(runner, ...)` would not. The current tests don't expose this trap.
- **Fix:** Add a test that decorates outside the `with` block (mimicking production module-level decoration) and verifies the mocks still apply via class-level patching. Document the rule clearly in the test docstring.

**A-TEST-HIGH-2 — `db_session` fixture in `tests/api/test_ingestion_health_state.py` will be missing the migration unless the testcontainer runs Alembic.**
- The root conftest creates the schema via `Base.metadata.create_all` (line 106), **not** via `alembic upgrade head`. So `test_migration_025_upgrade_downgrade_clean` and `test_migration_025_backfill_populates_prices_updated_at_from_stocks` (Spec A test cases 30, 31) will not actually exercise the migration — they'll see the table that `create_all` built, which skips the `INSERT INTO ticker_ingestion_state ... SELECT FROM stocks` backfill.
- Plan A Task 1 only writes 3 schema-introspection tests and never validates the backfill.
- **Fix:** Add an explicit Alembic test using a separate engine + `alembic.command.upgrade(cfg, "head")` and `alembic.command.downgrade(cfg, "-1")`. There is precedent in tests/api/test_ingest_pipeline.py — search for an existing migration test for the pattern.

**A-TEST-HIGH-3 — Coverage gaps enumerated in the brief that the plan does not cover.**
1. **Null timestamps mid-row** — Plan A `test_get_ticker_readiness_overall_is_worst_stage` only seeds `prices` + `forecast`. It does not seed a row with mixed null and non-null columns to verify `unknown` interleaves correctly with `green/yellow/red`.
2. **Concurrent `mark_stage_updated`** — no test exercises two coroutines hitting the same `(ticker, stage)` simultaneously. Postgres `ON CONFLICT` handles it, but the *fire-and-forget logging path* could double-log. Add `asyncio.gather` test.
3. **Decorator on a non-async function** — `tracked_task` is typed as `Callable[..., Awaitable[R]]`. Confirm with a regression test that decorating a sync function raises a clear TypeError at decoration time, not at first call.
4. **Decorator with no `tickers_total` kwarg** — Plan A covers `=500` and absence (default 0). It does NOT cover `tickers_total=None` (a common Celery accidental kwarg) which the `int(tickers_total_raw)` cast would `TypeError`.
5. **`task_tracer` exception in `record_llm` itself** — Plan A only tests exception inside the `with` block. If `collector.record_request` raises (DB down), the tracer should swallow it. Test missing.
6. **`task_tracer` measure-duration** — Plan A line 1486 sleeps `0.01` and asserts `>= 0`. Trivially true; replace with `>= 5` (5ms minimum) or use `freeze_time` + `tick(...)` for a deterministic check.

### MEDIUM

**A-TEST-MED-1 — No `TickerIngestionStateFactory`.** Plan A inlines `_make_state_row` in the test file. With Spec D adoption, every admin endpoint test will need this; we should land a `TickerIngestionStateFactory` in `tests/conftest.py` next to `BacktestRunFactory`. **Fix:** add the factory in Plan A Task 1.

**A-TEST-MED-2 — `test_staleness_slas_exact_values` is a brittle change-detector with no negative case.** It only asserts the values, never asserts `forecast_retrain > forecast` (the semantic invariant). A future edit that swaps two values would still pass if both are pinned together. **Fix:** add an invariant test (`assert sla.forecast_retrain > sla.forecast`).

**A-TEST-MED-3 — `_to_row` flattens out `forecast_retrain` silently.** No test asserts the flattening rule. If a refactor accidentally adds a `forecast_retrain` column to the dashboard row, no test catches it. **Fix:** add `test_to_row_excludes_forecast_retrain_field`.

**A-TEST-MED-4 — Plan A's `mark_stage_updated` test for "swallows DB error" mocks `async_session_factory` with `side_effect=RuntimeError`.** This raises before `__aenter__` — fine for the import-error path but doesn't cover errors inside the transaction (e.g., commit failure with a connection drop). **Fix:** add a test where `__aenter__` succeeds and `commit` raises.

### LOW

**A-TEST-LOW-1 — Decorator test docstrings violate the project rule "every test function MUST have a docstring explaining what it tests."** Several plan-A tests have one-liner triple-quoted docstrings that paraphrase the test name. Acceptable but not informative — they should explain *the contract*, not restate the assertion.

**A-TEST-LOW-2 — Plan A Task 4 never lints `tests/unit/tasks/test_ticker_state.py` even though it creates it.** Cosmetic, but the lint step in Step 5 misses files.

---

## Spec / Plan B — Pipeline Completeness

### CRITICAL

**B-TEST-CRIT-1 — Plan B places DB-hitting tests under `tests/unit/` in violation of the xdist guardrail.**
- Plan B line 127 (`async def test_mark_stage_updated_called_per_ticker(db_session, ...)`), line 446 (`test_mark_stage_updated_called_on_success_only(db_session, ...)`), line 1082, 1093 — multiple new tests in `tests/unit/tasks/test_convergence_snapshot.py`, `tests/unit/tasks/test_backtest_task.py`, `tests/unit/services/test_ingest_ticker_extended.py` request the `db_session` fixture from `tests/conftest.py`.
- `db_session` is not currently banned in `tests/unit/conftest.py`, but its use is rare (only 2 files in the entire `tests/unit/` tree). It hits the same shared Postgres instance as `client`, with no per-test TRUNCATE — under `pytest-xdist -n auto` two workers seeding the same `(ticker, date)` row in `signal_convergence_daily` will race the upsert and corrupt assertions.
- The integration tests `tests/api/test_convergence_integration.py` are correctly placed in `tests/api/`. The `tests/unit/` versions should be **mock-only** (no `db_session`).
- **Fix:** For each test that needs a real DB, move to `tests/api/test_convergence_integration.py` (etc.). For each test under `tests/unit/`, replace `db_session` with an `AsyncMock` session and assert at the call-graph level (mock `pg_insert(...).on_conflict_do_update(...)` was awaited). The xdist guardrail on `db_session` should also be added to `tests/unit/conftest.py` to prevent regressions.

**B-TEST-CRIT-2 — Mocked Prophet integration test misses the actual bug.**
- Spec B test case 18 ("Model trained with sentiment on synthetic data where sentiment perfectly predicts price → prediction on historical dates matches training correlation"). Plan B Task B3.1 line 636 patches `_fetch_sentiment_regressors` to return None for a *separate* test that exercises the no-sentiment path.
- The actual KNOWN LIMITATION bug is that `predict_forecast` writes `0.0` into the `future` DataFrame for both historical and forward dates. A test that mocks `_fetch_sentiment_regressors` cannot catch this — the bug is in the producer, not the fetcher. The test must:
  1. Train a Prophet model with real (or fake) sentiment values that correlate with `y`.
  2. Capture `model.params['beta']` for the regressor.
  3. Call `predict_forecast` (after the fix) and assert `yhat[date]` differs from a manually-computed `trend(date)` by approximately `beta * sentiment[date]`.
- Plan B Task B3.1 only includes test 23 ("integration test ... verify yhat_90 differs from same model with regressors patched to 0.0") — but tests 18-22 are stubbed, not specified. Without test 18, B3 has no regression coverage for the *historical* prediction bias which is the root of the issue.
- **Fix:** Spell out test 18 in Plan B Task B3.1 with the deterministic synthetic-data construction (described above), not just the integration smoke test.

**B-TEST-CRIT-3 — `test_ingest_forecast_dispatch.py` extension is asserted to mock `news_ingest_task.delay` and `compute_convergence_snapshot_task.delay` but Plan B Task B5.3 patches them at the import site `backend.tasks.news_sentiment.news_ingest_task.delay`** (line 1068). This is the **definition site**. After the Spec B refactor `pipelines.py` will do `from backend.tasks.news_sentiment import news_ingest_task` — the lookup site is `backend.services.pipelines.news_ingest_task.delay`, not `backend.tasks.news_sentiment.news_ingest_task.delay`. Patching at the definition site **also works** when the module-level reference is dotted (because `news_ingest_task` is a module attribute), but only as long as `pipelines.py` imports the module not the symbol. Plan B Step Task B5.4 line 1120 imports the *symbol* (`from backend.tasks.news_sentiment import news_ingest_task`) — so the patch must be at `backend.services.pipelines.news_ingest_task.delay`.
- **Fix:** Re-patch at `backend.services.pipelines.news_ingest_task` and `backend.services.pipelines.compute_convergence_snapshot_task`. Reference: `~/.serena/memories/global/debugging/mock-patching-gotchas`.

### HIGH

**B-TEST-HIGH-1 — Coverage gaps enumerated in the brief.**
1. **Convergence with no news sentiment for the ticker** — Spec B test case 1-9 omits this. If `news_direction` is not in `directions`, `directions.get("news")` returns None which is fine, but the convergence label computation may regress. Add a test.
2. **Backtest with insufficient data** — covered as test 11 (`<365 days → num_windows=0`). Good. But missing: backtest where data exists for window 1 but is empty for the *test* slice (price gap). Add a test that the engine reports `num_windows=0` cleanly without zero-division.
3. **Prophet with all-zero historical sentiment** — covered (test 21 falls back to 0.0). But also need: training with sentiment all-NaN (DB returned rows but values are null) — `fillna(0.0)` should kick in. Missing.
4. **News scoring with `Semaphore(1)` (sequential)** — Spec B test 28 covers `=2`. Add `=1` to verify the semaphore actually serialises (regression catch for accidental `Semaphore(0)` typo).
5. **`ingest_ticker` dispatching news/convergence for existing tickers (should NOT)** — Spec B test 31 covers this for `is_new=False`. Good. But missing: test where `last_fetched_at` is set but `ticker_ingestion_state` row is missing — should this trigger? Spec is silent. Open question for PM.

**B-TEST-HIGH-2 — Existing test files not enumerated in Plan B.**
- `tests/unit/services/test_signal_convergence.py` exists but the plan doesn't list it as touched. Spec B's wiring of `get_bulk_convergence` may be exercised by it.
- `tests/unit/tasks/test_convergence_task.py` (existing — has 30+ classifier tests) is mentioned but the plan never specifies *which* tests get rewritten vs preserved. Spec B says "Replace stub-status assertion with real behavior" — but the existing file has zero stub-status assertions, only classifier tests. The plan needs to clarify it is *adding* a new file `test_convergence_snapshot.py`, not replacing the existing file.
- `tests/unit/services/test_sentiment_scorer.py` exists (8 tests). Plan B Task B4.2 says "uv run pytest tests/unit/services/test_sentiment_scorer.py" but never specifies which tests must be updated for `Semaphore(5)` semantics. If existing tests assume sequential dispatch they will break post-refactor.

**B-TEST-HIGH-3 — Convergence integration test in `tests/api/test_convergence_integration.py` is not specified in Plan B at all.** Spec B lists it under "New test files to create" but Plan B's Task list never creates it. Plan B Task B1.5 only runs `tests/unit/tasks/test_market_data.py`. **Fix:** Add an explicit Plan B task for the integration file (seed 3 stocks → run `compute_convergence_snapshot_task` → assert rows in `signal_convergence_daily` and `ticker_ingestion_state.convergence_updated_at` populated).

### MEDIUM

**B-TEST-MED-1 — Mock-vs-integration tradeoff for B5 dispatch test.** Spec B asks for "integration test verifying new ticker triggers all 3 dispatches". Plan B Task B5.3 line 1068-1070 mocks `.delay` at the symbol site. **Recommendation:** keep the .delay mock for the unit test (fast, hermetic) and add a separate `tests/api/test_ingest_ticker_dispatches.py` that imports the real `compute_convergence_snapshot_task` and uses `celery_app.conf.task_always_eager = True` to verify end-to-end. Real Celery worker is overkill for a 7-spec sprint.

**B-TEST-MED-2 — `BacktestRunFactory` already exists** in `tests/conftest.py:375`. Spec B says "New factory: `BacktestRunFactory` under `tests/factories/backtest.py`" — incorrect. **Fix:** Use the existing factory; do not create a duplicate. Same for `SignalConvergenceDailyFactory` (exists at `tests/conftest.py:399`).

**B-TEST-MED-3 — News scoring concurrency test will be flaky.** Plan B Task B4.1 line 820 patches `_score_single_batch` with `slow_single` then asserts wall-time. Wall-time assertions on shared CI runners flake. **Fix:** assert via a `time.perf_counter()` capture inside the mock and confirm `enter_count - exit_count` peaked at 5 (the actual semaphore-cap invariant), not the wall-clock proxy.

**B-TEST-MED-4 — `@tracked_task` adoption test (Spec B test 9 — "produces a trace with name convergence_snapshot") will require mocking `LangfuseService` at the module level.** Plan B does not show this mock. Without the mock, the test will hit the real Langfuse client (disabled in test env, so it will probably be a no-op, but the assertion itself won't run). **Fix:** patch `backend.tasks.pipeline.PipelineRunner.start_run` and assert `pipeline_name="convergence_snapshot"`.

### LOW

**B-TEST-LOW-1 — Plan B Task Final.2 runs the full unit suite but never runs `tests/api/`.** Add an explicit `uv run pytest tests/api/test_convergence_integration.py -q` at the end.

**B-TEST-LOW-2 — Test naming inconsistency.** Plan B uses `test_mark_stage_updated_called_per_ticker` (verb-passive) while Plan A uses `test_get_ticker_readiness_missing_row_returns_unknown` (subject-condition-result). Stylistic but the project rule says `test_{what}_{condition}_{expected}`.

---

## Spec / Plan C — Entry Point Unification

### CRITICAL

**C-TEST-CRIT-1 — `tests/unit/tools/test_analyze_stock.py` does not exist in the codebase; Plan C says "rewrite".**
- I grepped `tests/` for `analyze_stock` — no test file matches. Plan C Task 3 line 643 says `Modify: tests/unit/tools/test_analyze_stock.py` and "Rewrite". **Effect:** the plan will fail at the modification step because the file does not exist; no baseline tests will catch the new behavior.
- **Fix:** Change Plan C Task 3 to **Create**, and write the full test file from scratch (the spec already enumerates cases 10-12).

**C-TEST-CRIT-2 — Plan C uses an undefined fixture `seed_stock_with_last_fetched`.**
- Plan C line 502 (`test_create_transaction_existing_ticker_skips_ingest(authenticated_client, seed_stock_with_last_fetched)`) requests a fixture that does not exist in `tests/conftest.py`, `tests/api/conftest.py`, or anywhere else.
- **Fix:** Either add the fixture to `tests/api/conftest.py` (factory + insert with `last_fetched_at=now()`) or replace with inline DB seeding inside the test using `db_session`.

**C-TEST-CRIT-3 — Patching `backend.routers.portfolio.ingest_ticker` requires the router file to import the symbol** (not the module). Plan C Task 2 step 2 line 547-548 imports it correctly (`from backend.services.pipelines import ingest_ticker`). Good. But **`tests/api/test_portfolio.py`** is being extended **after** the router edit — if the test file is loaded *before* the router edit lands (e.g. failing-test step), the patch path will not exist yet. The failing-test step (Plan C Step 1) writes the test before Step 2 (router edit), so `patch("backend.routers.portfolio.ingest_ticker")` will fail with `AttributeError: module backend.routers.portfolio has no attribute ingest_ticker`. **Fix:** Reorder Plan C Task 2 to land the import first (Step 2) then write the failing tests (Step 1).

**C-TEST-CRIT-4 — Bulk CSV concurrency test missing the rate-limit interaction.**
- Spec C test case 21 ("MAX_CONCURRENT_INGESTS=5 semaphore honored"). The test is implementable, but Spec C does not enumerate "Bulk CSV with 500 rows hitting rate limits" (the gap mentioned in the brief). With `MAX_CONCURRENT_INGESTS=5` and `RATE_LIMIT_PER_HOUR=100`, a 500-row CSV will exhaust the rate limit at row 100. There is no test verifying:
  - The remaining 400 rows are queued (not lost) OR
  - The endpoint returns a partial-success response with `failed=400, ratelimited=True`.
- **Fix:** Add `test_bulk_create_with_rate_limit_returns_partial_success` to Plan C Task 5.

### HIGH

**C-TEST-HIGH-1 — Race condition: two users adding the same new ticker simultaneously.**
- Spec C C1 calls `ingest_ticker(ticker, db, user_id=...)` synchronously inside `add_to_watchlist`. If user A and user B both POST `/watchlist {"ticker": "ZZZZ"}` for an unknown ticker at the same time, both call `ingest_ticker`, which both try to `INSERT INTO stocks` — `ensure_stock_exists` should be idempotent, but does it use `ON CONFLICT`?
- No test in Plan C exercises this. **Fix:** Add `test_concurrent_watchlist_adds_for_unknown_ticker_one_ingest` using `asyncio.gather` of two `add_to_watchlist` calls; assert exactly one `Stock` row exists and both Watchlist rows are inserted.

**C-TEST-HIGH-2 — Redis SETNX debounce timing flake.**
- Spec C C4 uses Redis `set(..., nx=True, ex=300)` for debounce. Plan C Task 4 line 944 mocks `fake_redis.set` with `return_value=False`. The fake never expires the key. **Real flake risk on CI:** if the test reuses a Redis container across tests in the same xdist worker, a stale debounce key from a previous test will make `set(nx=True)` return False unexpectedly. **Fix:**
  1. Use a unique key per test (`f"refresh:{ticker}:{uuid4()}"`) — but that defeats the production behavior.
  2. Better: clear the key explicitly in test teardown.
  3. Add a `test_get_signals_stale_after_debounce_expiry_redispatches` using `freeze_time` to advance past the 300s TTL — Plan C does not have this case.

**C-TEST-HIGH-3 — Plan C `tests/unit/services/test_watchlist_ingest.py` mocks `db.execute` with a list of `MagicMock(scalar_one=...)` side_effects. The order is brittle.**
- Plan C line 95-105 sets `fake_db.execute.side_effect = [count_result, lookup_result, ...]` — but `add_to_watchlist` may call `db.execute` in a different order after the refactor (e.g., the `select(Stock)` after ingest). The test will pass once and then break on any reorder.
- **Fix:** Use a dict-routed side_effect that inspects `stmt` for the table name.

**C-TEST-HIGH-4 — Existing tests not enumerated.**
- `tests/api/test_stocks_watchlist.py` — needs review for tests that assume "Stock must exist before add_to_watchlist". Plan C says "extend if needed" but does not enumerate. Search shows it has tests for the 404 path which will now succeed (since auto-ingest catches the unknown ticker) — they MUST be updated.
- `tests/api/test_chat.py` — chat routes may exercise `analyze_stock` indirectly. Plan C does not flag it.
- `tests/unit/services/test_pipelines.py` — exists; Plan C does not list it as modified, but Spec B does. Coordination gap.

### MEDIUM

**C-TEST-MED-1 — Bulk CSV row-limit test missing.** Spec C test 20 says "row_limit_exceeded_returns_error" — which limit, what number? Plan C does not specify.

**C-TEST-MED-2 — Dialog auto-close timing.** Frontend test `frontend/src/__tests__/components/log-transaction-dialog.test.tsx` (Spec C line 983) is mentioned but not enumerated. The brief flagged "dialog auto-close timing" — needs explicit test using `act()` / `waitFor()` to flush the mutation Promise and verify `setOpen(false)` was called.

**C-TEST-MED-3 — Bulk CSV fixture not specified.** No `bulk_transactions.csv` test fixture is created. Plan C Task 5 should add `tests/fixtures/bulk_transactions_valid.csv` and `bulk_transactions_invalid.csv` so all bulk tests share the same canonical input.

**C-TEST-MED-4 — `IngestFailedError` import path.** Plan C line 285 imports `from backend.services.exceptions import IngestFailedError`. Verify the exception exists in that module today; if not, Plan C must add it (Spec C is silent).

### LOW

**C-TEST-LOW-1 — Frontend tests for `useReingestTicker` not in Plan C.** Spec D adds the hook; Plan C-D coordination missing.

**C-TEST-LOW-2 — Plan C Task 4 line 922 patches `redis_async.from_url` — the real router uses `await get_redis()` from a shared connection pool, not a per-call `from_url`. Patch site likely wrong; need to confirm against `backend/routers/stocks/data.py` after the C4 edit.**

---

## Spec / Plan D — Admin + Observability

### CRITICAL

**D-TEST-CRIT-1 — `task_tracer` is defined twice with conflicting contracts.**
- Spec A §A4 defines `trace_task` as an **async** context manager in `backend/services/observability/task_tracer.py` taking `langfuse: LangfuseService` and `collector: ObservabilityCollector` as **parameters**.
- Spec D §D5 / Plan D Task 1 defines `task_tracer` as a **sync** `@contextmanager` in `backend/tasks/tracing.py` that imports `langfuse_service` as a **module global** and takes neither `langfuse` nor `collector`.
- These are not the same primitive. The Spec D version cannot trace async code paths cleanly (sentiment scorer, Prophet training, etc. are async — sync `@contextmanager` will not yield inside an `async with` block).
- **Fix:** Pick one. Recommendation: Spec A's `async with trace_task(...)` is correct because every call site is in an async function. Update Spec D / Plan D to import from `backend.services.observability.task_tracer` and use `async with`. Delete `backend/tasks/tracing.py` from Spec D.

**D-TEST-CRIT-2 — `ticker_ingestion_state` schema mismatch between Spec A and Spec D.**
- Spec A §A1 defines 11 timestamp columns + `created_at` + `updated_at`. **No `last_error` JSONB column.**
- Spec D §D3 (line 370) defines a schema with `last_error JSONB` and uses it in `overall_health` classification (`red — 3+ stages stale OR any stage has a last_error entry`).
- Plan D Task 4 line 802 imports `TickerIngestionState` from Spec A but its `_classify_row` reads `row.last_error` which does not exist on the model.
- Effect: Plan D's `test_ingestion_health_overall_health_classification` will pass only against the Spec D phantom schema; Spec A's migration produces a model without the column; tests crash with `AttributeError: TickerIngestionState has no attribute 'last_error'`.
- **Fix:** Reconcile. Either add `last_error` to Spec A's migration 025 + model, or strip `last_error` from Spec D's classification logic. Recommendation: add it — operators *do* need the failure metadata. Update Plan A Task 1 to add `last_error JSONB NULL` to the migration and `Mapped[dict | None]` to the model.

**D-TEST-CRIT-3 — Plan D's `task_tracer` test patches `backend.tasks.tracing.langfuse_service` but no module-level `langfuse_service` singleton currently exists** in `backend/observability/langfuse.py`. I confirmed via grep — only the class is defined.
- Plan D line 215 (`patch("backend.tasks.tracing.langfuse_service") as mock_svc`) requires Plan D Task 1 Step 3 to **add the singleton** and re-export it from `backend.tasks.tracing`. The plan says "Add `update_metadata` passthrough on LangfuseService" but never says "instantiate a module-level singleton".
- **Fix:** Add an explicit Plan D Task 1 step: "Create `langfuse_service = LangfuseService(...)` at the bottom of `backend/observability/langfuse.py`, with `enabled=False` when `LANGFUSE_SECRET_KEY` is empty." Then the patch path will work.

**D-TEST-CRIT-4 — Cache invalidator AST coverage test is overly permissive and will produce false negatives.**
- Plan D line 1084-1097: the test reads file source as a string and checks `if table in src and ("add(" in src or "insert(" in src or "upsert" in src)`. **Problems:**
  1. `"add("` matches **any** call ending in `add(` (e.g., `random.add(`, `metadata.add(`, `cache.add(`). False positives → many files flagged that don't actually write the table.
  2. Substring match `table in src` matches `"signal_snapshots"` inside a docstring or comment.
  3. `assert event in src` matches the *event name as a string* — so adding `# on_signals_updated` as a comment passes the test without actually firing the invalidator.
  4. The 50-line distance constraint is not actually implemented — the assertion just checks anywhere in the file.
- **Fix:** Use real AST walking (`ast.parse` + `NodeVisitor`) to find `session.add(...)` calls whose argument's class name matches the model bound to the table, then walk forward to confirm an `await invalidator.<event_name>(...)` call exists in the same function. This is the only way to make the test catch real gaps. The current heuristic will pass without the fix being applied.

**D-TEST-CRIT-5 — Per-task trigger test for malicious task name not enumerated.**
- Spec D test 14 says "test_trigger_task_regex_rejects_shell_metacharacters". Good. But missing from the plan:
  - Path-traversal style names (`../../../etc/passwd`).
  - Names that match a real task substring but are not in the whitelist (`backend.tasks.forecasting.run_backtest_task; rm -rf /`).
  - Unicode normalization attacks (`backend\u200btasks.run_backtest_task`).
- **Fix:** Parametrize `test_trigger_task_unregistered_returns_404` with an attack vector list.

### HIGH

**D-TEST-HIGH-1 — Ingestion health endpoint with 1000 tickers (pagination boundary).**
- Spec D test 19 says "test_ingestion_health_pagination" — but Plan D's `tests/api/test_admin_ingestion_health.py` does not enumerate the case with `limit=500` (the documented max) and `total > 500`. Need to verify the second page returns the next 500.
- Also missing: behavior when `limit > 500` — should return 422, not silently cap.
- **Fix:** Add explicit pagination edge tests.

**D-TEST-HIGH-2 — Langfuse span sampling at 25%.**
- Spec D test 28 says "test_sentiment_batch_samples_io_at_25pct (hypothesis + seeded RNG)". Plan D line 1245 patches `mod.random` (whatever module that is) — but the test never seeds RNG with `random.seed(42)` then asserts a deterministic count of `should_log_io=True` over N iterations. With Hypothesis and `max_examples=20`, the binomial distribution at p=0.25 has too much variance to assert exactly `5/20`. The test will flake.
- **Fix:** Use a fixed seed and assert exact count, OR replace `random.random()` with a deterministic counter (`if batch_idx % 4 == 0`).

**D-TEST-HIGH-3 — Cache invalidator AST coverage test future-proofing.**
- Brief asks "AST test for new write sites added in future". The current test is heuristic. To be future-proof:
  1. Maintain `WRITE_SITES` registry as the source of truth.
  2. Test should *fail* when a new model is added that isn't in `WRITE_SITES` and isn't on a `# noqa: cache-audit` allowlist.
- Plan D test does only the *forward* check (existing tables → invalidator). **Fix:** Add a *reverse* check that walks all SQLAlchemy models and asserts each is in `WRITE_SITES` or explicitly excluded.

**D-TEST-HIGH-4 — Enforcement test `test_pipeline_runner_all_tasks` parses `backend/tasks/**/*.py` for `@celery_app.task`.**
- Plan D line 413 parses every file. Risk: existing tasks in `backend/tasks/audit.py`, `seed_tasks.py` are explicitly tagged `tracer=none` in the spec table. The enforcement test as written makes no exceptions — it asserts every task has `@tracked_task`. **Effect:** The test will fail for the 13+ seed/audit/portfolio tasks that the spec deliberately excludes from tracing.
- **Fix:** The test should assert presence of `@tracked_task` regardless of `tracer=none|langfuse` (the decorator is applied either way; only Langfuse is gated). Confirm the spec D adoption table — re-read line 180-188: "tracer=none" tasks DO get `@tracked_task` (just no Langfuse). Plan D Step 2/Task 2 line 320 says "All 11 seed_* tasks: tracer none". So they ARE wrapped — good. The enforcement test must therefore permit any `@tracked_task(...)` regardless of tracer arg. Verify by re-reading the parser. As written, the parser likely just checks the decorator name, which is correct.

**D-TEST-HIGH-5 — Audit log viewer SQL JOIN test.**
- Spec D test 30 ("test_audit_recent_joins_user_email") — Plan D Task 7 mocks the DB session. A mocked test cannot verify JOIN correctness; it can only verify the SQL was emitted. **Fix:** Add an integration test in `tests/api/test_admin_audit_recent.py` that seeds 3 audit log rows for 2 different users and asserts `entries[*].user_email` matches.

### MEDIUM

**D-TEST-MED-1 — `PipelineRun` factory does not exist in `tests/conftest.py`.** I checked — only `BacktestRunFactory`, `SignalConvergenceDailyFactory`, `AdminAuditLogFactory`. Plan D will need a `PipelineRunFactory` for the enforcement tests and Spec A's decorator tests too. **Fix:** Add `PipelineRunFactory` to `tests/conftest.py` in Plan A Task 5 (or Plan D Task 2).

**D-TEST-MED-2 — Langfuse spans test uses `patch("backend.tasks.market_data._nightly_chain_body")`** (Plan D line 1235). I have not verified `_nightly_chain_body` exists as a function in `market_data.py` — if `nightly_pipeline_chain_task` calls all phases inline, the patch will fail. **Fix:** Verify the helper exists or refactor the production code to extract it before writing the test.

**D-TEST-MED-3 — Cache invalidator integration test (`test_integration_signal_write_evicts_redis_end_to_end`) requires a real Redis container.** Plan D never specifies that the test goes in `tests/api/` (which has Redis). It is listed under `tests/unit/services/test_cache_invalidator_coverage.py` — wrong tier. **Fix:** Move integration test to `tests/api/test_cache_invalidator_integration.py`.

**D-TEST-MED-4 — D6 audit viewer "filter by action" test (Spec D test 31) does not specify the action enum.** If the API accepts arbitrary strings, the test should also verify a 422 for invalid actions.

### LOW

**D-TEST-LOW-1 — Frontend tests for `IngestionHealthTable renders red rows first` (Spec D test 34) needs Recharts? No — it's a TanStack Table, not a chart.** Confirm no Recharts animation flake.

**D-TEST-LOW-2 — `test_admin_ingestion_health.py` reuses `admin_client` fixture** (Plan D line 947, 977). This fixture is not defined in any conftest I've inspected; needs verification or addition.

**D-TEST-LOW-3 — Spec D test 32 ("latency_trends_groups_by_pipeline_and_hour") requires time-series data with controlled timestamps. Use `freeze_time` per test, otherwise it will flake at hour boundaries.**

---

## Cross-Cutting Findings

**X-CRIT-1 — Spec import drift (A↔B↔D).** Documented as A-TEST-CRIT-2. This is the single highest-risk issue across all 4 specs. Recommended fix order:
1. Lock canonical paths (Spec A's are correct).
2. Search-replace across Spec B/C/D specs and plans.
3. Add an import-resolution test in Plan A Task 7 that imports each primitive and asserts the module path.

**X-CRIT-2 — `mark_stage_updated` signature drift.** Documented as A-TEST-CRIT-3. Lock to Spec A's 2-arg async signature.

**X-CRIT-3 — Schema drift in `ticker_ingestion_state`.** Documented as D-TEST-CRIT-2. Add `last_error JSONB NULL` to Spec A migration 025.

**X-HIGH-1 — `tests/unit/conftest.py` needs to ban `db_session` for the same reason it bans `client`.** Currently the guardrail covers `client` and `authenticated_client` but not `db_session`. Plan B introduces 5+ unit tests that use `db_session`, which is a regression vector. **Fix:** Add a `db_session` guardrail in `tests/unit/conftest.py` *before* Plan B starts implementation; this will force the right placement.

**X-HIGH-2 — Hard Rule #10 enforcement is asserted in only 1 test (Plan A line 1180).** Multiple specs add new error paths; each should include a "no leak" assertion. Add a custom Semgrep rule or a parametrized regression test that walks the new error paths.

---

## Summary Table

| ID | Spec | Severity | Title | Required Before Merge? |
|---|---|---|---|---|
| A-TEST-CRIT-1 | A | CRITICAL | Tracer mocks vs singleton mismatch | Yes |
| A-TEST-CRIT-2 | A/B/D | CRITICAL | Spec import path drift | Yes |
| A-TEST-CRIT-3 | A/B | CRITICAL | `mark_stage_updated` signature drift | Yes |
| A-TEST-CRIT-4 | A/B | CRITICAL | `"recommendation"` not a valid Stage | Yes |
| A-TEST-CRIT-5 | A | CRITICAL | `error_summary` no-leak test is a no-op | Yes |
| A-TEST-HIGH-1 | A | HIGH | Decorator class-patching at module-level adoption | Yes |
| A-TEST-HIGH-2 | A | HIGH | Migration test does not exercise Alembic | Yes |
| A-TEST-HIGH-3 | A | HIGH | Coverage gaps (6 enumerated) | Recommended |
| A-TEST-MED-1 | A | MEDIUM | Missing `TickerIngestionStateFactory` | Recommended |
| A-TEST-MED-2 | A | MEDIUM | SLA value test brittle | No |
| A-TEST-MED-3 | A | MEDIUM | `_to_row` flatten not asserted | No |
| A-TEST-MED-4 | A | MEDIUM | `mark_stage_updated` commit-failure path | No |
| A-TEST-LOW-1 | A | LOW | Test docstring quality | No |
| A-TEST-LOW-2 | A | LOW | Lint scope misses test files | No |
| B-TEST-CRIT-1 | B | CRITICAL | DB-hitting tests under `tests/unit/` | Yes |
| B-TEST-CRIT-2 | B | CRITICAL | Prophet integration test misses the actual bug | Yes |
| B-TEST-CRIT-3 | B | CRITICAL | Mock patch at definition-site, not lookup-site | Yes |
| B-TEST-HIGH-1 | B | HIGH | Coverage gaps (5 enumerated) | Recommended |
| B-TEST-HIGH-2 | B | HIGH | Existing tests not enumerated | Yes |
| B-TEST-HIGH-3 | B | HIGH | Convergence integration test never created | Yes |
| B-TEST-MED-1 | B | MEDIUM | Mock-vs-eager Celery decision | Recommended |
| B-TEST-MED-2 | B | MEDIUM | Duplicate factories planned | Yes |
| B-TEST-MED-3 | B | MEDIUM | Wall-clock concurrency test flake | Recommended |
| B-TEST-MED-4 | B | MEDIUM | `@tracked_task` adoption test missing mock | Recommended |
| B-TEST-LOW-1 | B | LOW | Final task does not run `tests/api/` | No |
| B-TEST-LOW-2 | B | LOW | Test naming inconsistency | No |
| C-TEST-CRIT-1 | C | CRITICAL | `test_analyze_stock.py` does not exist | Yes |
| C-TEST-CRIT-2 | C | CRITICAL | Undefined fixture `seed_stock_with_last_fetched` | Yes |
| C-TEST-CRIT-3 | C | CRITICAL | Failing-test step ordering | Yes |
| C-TEST-CRIT-4 | C | CRITICAL | Bulk CSV rate-limit interaction missing | Yes |
| C-TEST-HIGH-1 | C | HIGH | Race condition on concurrent watchlist add | Recommended |
| C-TEST-HIGH-2 | C | HIGH | Redis SETNX timing flake + missing expiry test | Yes |
| C-TEST-HIGH-3 | C | HIGH | Brittle ordered side_effect mocks | Recommended |
| C-TEST-HIGH-4 | C | HIGH | Existing tests not enumerated | Yes |
| C-TEST-MED-1 | C | MEDIUM | Bulk CSV row limit unspecified | No |
| C-TEST-MED-2 | C | MEDIUM | Dialog auto-close timing test | No |
| C-TEST-MED-3 | C | MEDIUM | Bulk CSV fixture not specified | No |
| C-TEST-MED-4 | C | MEDIUM | `IngestFailedError` import path unverified | No |
| C-TEST-LOW-1 | C | LOW | `useReingestTicker` frontend test | No |
| C-TEST-LOW-2 | C | LOW | Redis patch site likely wrong | Recommended |
| D-TEST-CRIT-1 | D | CRITICAL | `task_tracer` defined twice (sync vs async) | Yes |
| D-TEST-CRIT-2 | D | CRITICAL | `ticker_ingestion_state` schema drift (last_error) | Yes |
| D-TEST-CRIT-3 | D | CRITICAL | `langfuse_service` singleton not created | Yes |
| D-TEST-CRIT-4 | D | CRITICAL | Cache invalidator AST test is heuristic and weak | Yes |
| D-TEST-CRIT-5 | D | CRITICAL | Malicious task-name attack vectors not enumerated | Recommended |
| D-TEST-HIGH-1 | D | HIGH | Pagination boundary tests missing | Recommended |
| D-TEST-HIGH-2 | D | HIGH | Sampling test will flake | Yes |
| D-TEST-HIGH-3 | D | HIGH | AST test not future-proof | Recommended |
| D-TEST-HIGH-4 | D | HIGH | Enforcement test allowlist semantics | Recommended |
| D-TEST-HIGH-5 | D | HIGH | Audit JOIN test is mock-only | Recommended |
| D-TEST-MED-1 | D | MEDIUM | `PipelineRunFactory` missing | Yes |
| D-TEST-MED-2 | D | MEDIUM | `_nightly_chain_body` patch site unverified | Recommended |
| D-TEST-MED-3 | D | MEDIUM | Integration test in wrong tier | Recommended |
| D-TEST-MED-4 | D | MEDIUM | Action enum filter test missing | No |
| D-TEST-LOW-1 | D | LOW | Recharts vs TanStack Table | No |
| D-TEST-LOW-2 | D | LOW | `admin_client` fixture undefined | Yes |
| D-TEST-LOW-3 | D | LOW | Latency-trend hour-boundary flake | No |
| X-CRIT-1 | A/B/D | CRITICAL | Cross-spec import drift | Yes |
| X-CRIT-2 | A/B | CRITICAL | Cross-spec signature drift | Yes |
| X-CRIT-3 | A/D | CRITICAL | Cross-spec schema drift | Yes |
| X-HIGH-1 | All | HIGH | `db_session` not banned in `tests/unit/conftest.py` | Yes |
| X-HIGH-2 | All | HIGH | Hard Rule #10 has only one regression test | Recommended |

**Counts:** 16 CRITICAL, 16 HIGH, 14 MEDIUM, 8 LOW. **Required-before-merge: 28 findings.**

---

## Recommended Pre-Implementation Actions

1. **Reconcile cross-spec drift first.** Hold a 30-minute session to lock the canonical paths, signatures, and schema. Search-replace across all 4 specs and plans.
2. **Add the `db_session` guardrail** to `tests/unit/conftest.py` before Plan B starts.
3. **Add factories** (`TickerIngestionStateFactory`, `PipelineRunFactory`) to `tests/conftest.py` as part of Plan A Task 1.
4. **Re-write the cache invalidator AST coverage test** with real `ast.NodeVisitor` semantics — the current heuristic is worse than no test (false sense of security).
5. **Re-write Prophet sentiment regression test** with deterministic synthetic data so the actual bug is caught at the unit level, not just at the integration smoke test.
6. **Verify or create**: `langfuse_service` module singleton, `_nightly_chain_body` helper, `seed_stock_with_last_fetched` and `admin_client` fixtures, `IngestFailedError` exception class. Each is referenced by tests but not confirmed to exist.

---

*End of Test Engineer Review.*
