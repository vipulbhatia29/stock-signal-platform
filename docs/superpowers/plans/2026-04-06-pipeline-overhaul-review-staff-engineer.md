# Pipeline Overhaul — Staff Engineer Review (Specs A–D)

**Reviewer:** Staff Engineer (Opus 4.6)
**Date:** 2026-04-06
**Scope:** Specs A/B/C/D and the matching plans for the Pipeline Overhaul epic.

This review focuses on architectural soundness, backward compatibility, concurrency, missing concerns, security, plan-vs-spec coverage, and test gaps. Findings are graded CRITICAL / HIGH / MEDIUM / LOW per spec; a summary table appears at the bottom.

> **Headline.** The four specs are coherent and mostly land in the right place, but Spec D's `task_tracer` *contract* (`backend/tasks/tracing.py`, `start_span` / `start_generation` on `LangfuseService`) **does not match** Spec A's `task_tracer` (`backend/services/observability/task_tracer.py`, uses `create_trace`). Spec B then imports a third path (`backend.observability.task_tracer`). All four specs reference the same primitive but cannot all be right. This is the largest blocker. There are also several missing rate-limit / authorization gaps in Spec C and D, and one wrong codebase assumption in Plan D (Langfuse SDK methods that do not exist today).

---

## Codebase verifications performed

| Assertion in spec | Verified? | File |
|---|---|---|
| Alembic head is `b2351fa2d293` | ✅ confirmed | `backend/migrations/versions/b2351fa2d293_024_forecast_intelligence_tables.py` |
| `PipelineRunner` has `start_run`/`complete_run` etc. | ✅ confirmed | `backend/tasks/pipeline.py:24` (class), `:27` (start_run), `:132` (complete_run) |
| `LangfuseService.create_trace(trace_id, session_id, user_id, metadata)` | ✅ confirmed | `backend/observability/langfuse.py:40` |
| `LangfuseService.start_span` / `start_generation` exist | ❌ **DO NOT EXIST** — only `create_trace`, `create_span`, `end_span`, `record_generation`, `get_trace_ref`, `flush`, `shutdown` | `backend/observability/langfuse.py:16` |
| `ObservabilityCollector.record_request(... langfuse_trace_id ...)` | ✅ confirmed | `backend/observability/collector.py:52,63` |
| `ingest_ticker` exists with `is_new`/`composite_score` | ✅ confirmed | `backend/services/pipelines.py:40,87,113,149` |
| `IngestFailedError` exists | ✅ confirmed | `backend/services/exceptions.py:69` |
| `SignalConvergenceService.get_bulk_convergence` exists | ✅ confirmed | `backend/services/signal_convergence.py:109` |
| `get_all_referenced_tickers` exists | ✅ confirmed | `backend/services/ticker_universe.py:18` |
| `AdminAuditLog` model exists | ✅ confirmed | `backend/models/audit.py:12` |
| `CacheInvalidator` events listed in Spec D | ✅ all 7 confirmed; no `on_convergence_updated` / `on_recommendations_updated` / `on_drift_detected` / `on_ticker_state_updated` | `backend/services/cache_invalidator.py` |
| Watchlist router uses slowapi `@limiter.limit` | ✅ confirmed (`@limiter.limit("2/minute")` on the unrelated bulk path; `POST /watchlist` itself has no decorator) | `backend/routers/stocks/watchlist.py:139` |

---

# Spec A: Ingestion Foundation

Strong, additive, ships without call sites. The biggest risks are around the `task_tracer` contract being unstable (Spec B/D import it from different paths) and a couple of subtle correctness issues in `mark_stage_updated` and the `tracked_task` decorator.

## CRITICAL

### A-CRIT-1 — `task_tracer` location is contradictory across specs
Spec A places `task_tracer` and `TaskTraceHandle` in `backend/services/observability/task_tracer.py` (Spec A §A4, Plan A Task 6). Spec B's example imports it as `from backend.observability.task_tracer import tracked_task` (sic — wrong symbol *and* wrong path; see B-CRIT-2). Spec D §D5 places `task_tracer` in `backend/tasks/tracing.py` (Plan D Task 1). All three specs depend on Spec A's primitive, but only one can be correct.

**Evidence:**
- Spec A Plan, Task 6 — creates `backend/services/observability/task_tracer.py`
- Spec B, design B1 line ~171 — `from backend.observability.task_tracer import tracked_task`
- Spec D, files-created list — creates `backend/tasks/tracing.py` with the same context manager
- Plan D Task 1 — implements `task_tracer` in `backend/tasks/tracing.py` against `langfuse_service.start_span` / `start_generation`

**Recommended fix:** Pick one canonical location (recommend `backend/services/observability/task_tracer.py` per Spec A) and update Specs B and D to import from there. Delete the `backend/tasks/tracing.py` task in Plan D and rename `task_tracer` references in Plan D Tasks 2-12 to use the Spec A path. Add a "Spec A symbol map" appendix to Spec A so subsequent plans cannot diverge.

## HIGH

### A-HIGH-1 — `mark_stage_updated` upsert sets `created_at` to "now" on update path
Spec A §A1 service code:
```python
values = {"ticker": ticker, col: now, "created_at": now, "updated_at": now}
stmt = insert(...).values(**values).on_conflict_do_update(set_={col: now, "updated_at": now})
```
The insert path correctly sets `created_at = now`. But the `set_` clause is fine — it doesn't touch `created_at` on conflict. **However** the `values` dict still passes `created_at=now` which is correct for the insert side. Real bug: the migration adds `server_default=sa.text("now()")` (Plan A Task 1 step 5), so the model declares `created_at` as `nullable=False` with no client default. If a future code path constructs a `TickerIngestionState(ticker=...)` directly via SQLAlchemy ORM (not through this upsert), the insert will fail unless `created_at` is set. The model in Spec A has no `default=` on `created_at`/`updated_at`. Direct ORM inserts will break.

**Evidence:** `backend/models/ticker_ingestion_state.py` proposed code; Plan A Task 1 Step 4 model definition lacks `default=func.now()` or `server_default`.

**Recommended fix:** Either (a) add `server_default=func.now()` on the model `created_at` and `updated_at` mapped_column declarations (mirrors the migration), or (b) declare them with a Python `default=lambda: datetime.now(timezone.utc)`. Otherwise the test in Plan A Task 1 Step 2 (`TickerIngestionState(ticker="TSTA", prices_updated_at=now, created_at=now, updated_at=now)`) only passes because the test author manually sets the timestamps.

### A-HIGH-2 — `tracked_task` decorator: `@celery_app.task` ordering matters
Spec A §A3 shows usage as:
```python
@celery_app.task(name="...")
def nightly_news_sentiment_task() -> dict:
    return asyncio.run(_run())

@tracked_task("news_sentiment")
async def _run(*, run_id: uuid.UUID) -> dict: ...
```
That works because `@tracked_task` wraps `_run`, not the Celery task. **But** Spec D §D1 shows the inverse pattern:
```python
@tracked_task(name="generate_alerts", scope="per_ticker", tracer="langfuse")
@celery_app.task(name="backend.tasks.alerts.generate_alerts_task")
def generate_alerts_task():
    return asyncio.run(_generate_alerts_async())
```
This stacks `tracked_task` *outside* the Celery task — but `tracked_task` is async (Spec A) and `generate_alerts_task` is sync (it does `asyncio.run`). The wrapper would try to `await` a sync function. The two specs disagree on the decorator's stacking and on whether it wraps the async helper or the celery task body.

**Recommended fix:** Spec A should explicitly document the canonical stacking: `@celery_app.task(...) def task(): return asyncio.run(_async_helper())` and `@tracked_task("name") async def _async_helper(*, run_id): ...`. Update Spec D §D1 example to match. Add a unit test that asserts `tracked_task` raises `TypeError` if applied to a sync function.

### A-HIGH-3 — Spec A's `tracked_task` parameter list does not match Spec D's call sites
Spec A's signature is `tracked_task(pipeline_name: str, *, trigger: str = "scheduled")`. Spec D §D1 example uses `@tracked_task(name="generate_alerts", scope="per_ticker", tracer="langfuse")`. None of `name`, `scope`, `tracer` exist in Spec A's contract.

**Recommended fix:** Either (a) extend Spec A to include `scope` and `tracer` keyword arguments now (cheaper to do once) and document the `name=` alias, or (b) Spec D drops the `scope`/`tracer` kwargs and uses Spec A's API verbatim. Recommendation: (a) — `scope="per_ticker" | "global"` is essential for Spec D's enforcement test and aligns with the per-ticker recording semantics in Spec D §D1.

### A-HIGH-4 — `task_tracer` reuses `trace_id` as `session_id` and `user_id` — Langfuse cardinality risk
Spec A §A4 / Plan A Task 6 code:
```python
trace = langfuse.create_trace(
    trace_id=trace_id,
    session_id=trace_id,   # ⚠ different UUID per task run
    user_id=trace_id,      # ⚠ same
    metadata={"task": name, ...},
)
```
Each task invocation creates a brand-new `session_id` and `user_id`. In Langfuse, sessions and users are aggregation dimensions. Doing this means every nightly task run pollutes the user/session list with single-use UUIDs. After 30 days the Langfuse user list will contain ~30 × N tasks × N tickers entries — unusable for slicing.

**Recommended fix:** Use stable synthetic identifiers like `session_id=uuid.UUID(int=0)` (or a per-task constant `uuid.uuid5(NAMESPACE, name)`) and `user_id=uuid.UUID(int=0)`. Document the convention in Spec A §A4. Better: extend `LangfuseService` with a `create_task_trace(name, metadata)` method that handles this internally so the convention cannot drift.

## MEDIUM

### A-MED-1 — DB-hitting tests in `tests/unit/services/test_ticker_state.py`
Plan A Task 4 places service tests in `tests/unit/` but they patch `async_session_factory` rather than hit the DB. Acceptable, but the test file imports `backend.models.ticker_ingestion_state` which forces SQLAlchemy metadata registration. With `pytest-xdist -n auto`, model registration is fine but the project's `tests/unit/conftest.py` guardrail (per CLAUDE.md) blocks `async_session_factory` usage in `tests/unit/`. Verify the test passes the `tests/unit/conftest.py` import-time check before merging. Tests may need to move to `tests/api/` if the guardrail trips on the `from backend.services import ticker_state` import alone.

**Recommended fix:** During implementation, run `uv run pytest tests/unit/services/test_ticker_state.py -q` immediately after creating the file. If the conftest guardrail trips, move to `tests/api/` (the project rule per CLAUDE.md is "new DB-hitting tests must go in tests/api/").

### A-MED-2 — `_worst()` `min` with iterator may exhaust iterable; defaults are wrong
`_worst()` uses `min(values, key=..., default="unknown")`. If `values` is an iterator (it is — `stages.values()`) `min` iterates once which is fine. But the `default="unknown"` only kicks in when the iterable is empty — `stages` always has 9 entries. The default is unreachable in practice and hides the intent. Cosmetic but worth a comment.

### A-MED-3 — `ReadinessRow` drops `forecast_retrain` silently
The dashboard row deliberately omits `forecast_retrain` (Plan A `_to_row`). Operators will see "forecast OK" while a 30-day-old retrain is hidden. Spec A acknowledges this (open question 1) and recommends keeping it separate. Fine, but Spec D's dashboard column list (D3) does not surface `forecast_retrain` either — there is no place in the UI to ever see it. The signal is collected and never displayed.

**Recommended fix:** Either show a small badge in the forecast cell when `forecast_retrain` is red, or remove `forecast_retrain` from the model entirely and reconsider in a follow-up.

### A-MED-4 — `mark_stage_updated` opens its own session; cannot participate in caller's tx
Spec A's `mark_stage_updated` always opens its own `async_session_factory()` and commits. If a Celery task wants to roll back atomically (e.g., a backtest writes rows and then the stage mark fails), the stage mark is already committed and the rollback only undoes the backtest. End state: inconsistent. Spec B's plan (Task B1.4, B2.3) calls `await mark_stage_updated(db, ticker, "convergence")` passing the existing session — but Spec A's `mark_stage_updated` signature is `mark_stage_updated(ticker, stage)` with no `db` parameter. **Spec A and Spec B disagree on the signature.**

**Recommended fix:** Spec A should add an optional `session: AsyncSession | None = None` parameter — when None, open a new session (current behavior); when supplied, use the caller's session and skip the inner commit. Update Spec B to consistently pass `db`.

## LOW

### A-LOW-1 — Plan A Task 5 imports `update`, `PipelineRun`, `async_session_factory` at module top of `backend/tasks/pipeline.py`
Plan A Task 5 step 3 instructs to add these imports at the top. Verify they're not already imported (likely not — current `pipeline.py` is self-contained). Existing module is small enough that the addition is fine.

### A-LOW-2 — `StalenessSLAs` is "frozen-class-but-mutable"
Plain class with `timedelta` defaults. A test or import side effect could mutate `StalenessSLAs.prices = timedelta(hours=1)`. Use `@dataclass(frozen=True, slots=True)` for true immutability.

### A-LOW-3 — `test_staleness_slas_exact_values` uses `StalenessSLAs()` instance attributes
Spec A defines `prices: timedelta = timedelta(hours=4)` as a class attribute. The test reads `sla = StalenessSLAs(); sla.prices`. This works because plain Python class attrs are accessed via instance. Won't break, but contrast with the @dataclass recommendation in A-LOW-2.

---

# Spec B: Pipeline Completeness

Three real bug fixes (B1, B2, B3) and two perf wins (B4, B5). The Prophet sentiment fix (B3) is correct in principle but the merge ordering has a subtle bug. The convergence and backtest implementations correctly leverage existing helpers.

## CRITICAL

### B-CRIT-1 — `predict_forecast` 7-day trailing mean uses `model.history` cutoff but applies it to the entire `future` DataFrame
Spec B §B3 algorithm:
```python
training_end = model.history["ds"].max().date()
hist_recent = hist_df[hist_df["ds"] >= pd.Timestamp(training_end) - pd.Timedelta(days=7)]
projection = {col: hist_recent[col].mean() ...}
future = future.merge(hist_df, on="ds", how="left")
for col, fill in projection.items():
    mask = future["ds"].dt.date > training_end
    future.loc[mask, col] = fill
    future[col] = future[col].fillna(0.0)
```
**Bug:** the final `.fillna(0.0)` runs after `loc[mask]` — but `loc[mask] = projection` only writes to the future-mask rows. Historical rows (`ds <= training_end`) that have *missing* sentiment in `hist_df` (gaps) will get filled with `0.0` — exactly the bias we are trying to remove. The Prophet model was trained on `df.merge(sentiment_df, ...).fillna(0.0)` (lines 78-91 of forecasting.py), which means **training also imputes 0.0 on gap days**. So this is not a new bias — it's consistent. But the test in Plan B (`test_sentiment_regressor_affects_yhat`) compares `predict_forecast` to a mocked `_fetch_sentiment_regressors=None` path. Both paths will use the same fillna(0.0) for gaps — but the path-with-data vs no-data differ in *non-gap* days. The test will pass.

The actual subtle issue: the trailing mean uses `>= training_end - 7d`. If the news system has gaps (frequent in practice), the 7-day window may contain only 1-2 actual data points. The mean is then noisy and biased towards whichever scattered days had news. This is acceptable but should be documented.

**Recommended fix:** Document the gap-fill semantics in `predict_forecast` docstring. Add a test with sparse sentiment data (1 of 7 days populated) to confirm the projection is the single value, not its average with implicit zeros.

### B-CRIT-2 — Spec B imports `task_tracer` from `backend.observability.task_tracer` but Spec A puts it in `backend.services.observability.task_tracer`
Spec B §B1 example:
```python
from backend.observability.task_tracer import tracked_task  # Spec A
from backend.services.ingestion_state import mark_stage_updated  # Spec A
```
Both paths are wrong:
- `backend.observability.task_tracer` does not exist in Spec A; Spec A creates `backend.services.observability.task_tracer`.
- `backend.services.ingestion_state` does not exist; Spec A creates `backend.services.ticker_state` with `mark_stage_updated`.

**Evidence:** Spec A files-created list explicitly names `backend/services/ticker_state.py` (not `ingestion_state.py`) and `backend/services/observability/task_tracer.py` (not `backend/observability/...`).

**Recommended fix:** Spec B must use `from backend.services.observability.task_tracer import tracked_task` and `from backend.services.ticker_state import mark_stage_updated`. Update Plan B Tasks B1.4, B2.3, B5.4 accordingly.

## HIGH

### B-HIGH-1 — Backtest Prophet training on the worker pool will block other Celery tasks
Spec B §B2 uses `asyncio.to_thread` for Prophet fits. Default Celery prefork pool spawns N processes; asyncio runs inside each process. Inside a Celery process, `asyncio.to_thread` schedules to a default `concurrent.futures.ThreadPoolExecutor` whose worker count is `min(32, os.cpu_count()+4)`. Prophet is single-threaded, CPU-heavy. Running ~100 tickers × 20 windows on a single Celery worker process saturates one core for ~3 hours and starves any other task that lands on the same worker. Spec B mentions "Saturday 03:00 ET" but the production deploy may have only one worker process, in which case no other tasks run during the backtest window.

**Recommended fix:** Document that the backtest task should be routed to a dedicated Celery queue (`backtest`) bound to a separate worker pool with `--concurrency=1` or `--pool=solo`. Add a beat schedule note. Alternatively, run backtests via Celery task chunking — submit one task per ticker so the broker spreads load.

### B-HIGH-2 — Concurrency risk: `predict_forecast` becoming async creates a race with `train_prophet_model`
The user prompt asked specifically about this. Today, `predict_forecast` is sync and `train_prophet_model` is async. The sync `predict_forecast` is called inside `_model_retrain_all_async` (line 71) and `_forecast_refresh_async` (line 116), both of which already hold an `AsyncSession`. Making `predict_forecast` async and adding a `db` parameter is fine **as long as `predict_forecast` never opens a new session for the same ticker concurrently with the train path**. Spec B's design has `predict_forecast` call `_fetch_sentiment_regressors(..., db)` which reads `news_sentiment_daily` — a read, not a write. No race against `train_prophet_model` (which writes `forecast_results` and `model_versions`).

**However**, if `predict_forecast` is called from a different process (e.g., admin endpoint) while the nightly retrain is running for the same ticker, both will read the same `model_version` row. The `model_version.history` reference is in-memory inside the Prophet object, so there's no DB contention — but the `predict_forecast` caller may be predicting against an older model artifact than the one that's about to be persisted. Acceptable race, but worth a docstring note.

**Recommended fix:** Add a docstring on `predict_forecast` documenting that it is read-only against the DB and is safe to call concurrently with `train_prophet_model`. No code change required.

### B-HIGH-3 — Test plan B references `db_session` fixture for tests in `tests/unit/`
Plan B Task B1.1 puts `tests/unit/tasks/test_convergence_snapshot.py` in `tests/unit/` but uses `db_session` and `signal_snapshot_factory` fixtures. Per CLAUDE.md, DB-hitting tests must live in `tests/api/`. The unit conftest guardrail will trip.

**Evidence:** Plan B Task B1.1 step 2:
```python
async def test_universe_mode_inserts_one_row_per_ticker(db_session, signal_snapshot_factory, ...):
```

**Recommended fix:** Move the DB-touching scenarios to `tests/api/test_convergence_snapshot.py`. Keep mocked unit tests (e.g., `test_empty_universe_returns_no_tickers`, the `mark_stage_updated` patch tests) in `tests/unit/`. Same applies to `tests/unit/tasks/test_backtest_task.py` (B2.2), `tests/unit/services/test_backtest_engine_walk_forward.py` (B2.1), `tests/unit/services/test_prophet_sentiment_predict.py` (B3.1), `tests/unit/services/test_ingest_ticker_extended.py` (B5.3) — every test that takes `db_session`.

### B-HIGH-4 — Convergence task uses `date.today()` (system local time) — should be `datetime.now(UTC).date()`
Plan B Task B1.2 / Spec B §B1:
```python
today = date.today()
```
The platform stores all timestamps in TZ-aware UTC. `date.today()` is local time. On a worker in a non-UTC timezone, the row written into `signal_convergence_daily.date` will be off by a day around midnight local — same bug class as KAN-401 / KAN-402 in MEMORY.md.

**Recommended fix:** Use `today = datetime.now(timezone.utc).date()` in `_compute_convergence_snapshot_async` and the backfill helpers. Add a regression test that freezes time to 00:30 UTC and confirms the date is the UTC date, not the local date.

### B-HIGH-5 — News scoring concurrent dispatch may exceed OpenAI tier-1 RPM under burst
Spec B §B4 claims Semaphore(5) × 30 RPM/slot = 150 RPM. The math is wrong — `Semaphore(5)` controls *concurrent in-flight requests*, not RPM. With 5 concurrent batches × ~2s latency = ~150 RPM steady state. But `asyncio.gather` with 27 batches and `Semaphore(5)` will dispatch the first 5 simultaneously, then immediately backfill as each completes. In the first 1 s window we may issue 5 requests; after 2 s another 5; over a 5 s burst that's 25 requests, well over the 60-req-per-second tier-1 limit (500 RPM ÷ 60 ≈ 8.3 req/sec). Borderline but likely fine — worth a token-bucket rate-limiter rather than a raw semaphore.

**Recommended fix:** Replace the Semaphore with a token-bucket (e.g., aiolimiter `AsyncLimiter(8, 1)` for 8 req/sec). Or document the math and assert the RPM bound in a unit test.

### B-HIGH-6 — `ingest_ticker` Step 6b passes `db` to `mark_stage_updated` but Spec A signature is `(ticker, stage)`
Spec B §B5 / Plan B Task B5.4:
```python
await mark_stage_updated(db, ticker, "prices")
```
Spec A signature is `mark_stage_updated(ticker: str, stage: Stage)` — no `db` parameter, opens its own session. Same divergence as A-MED-4.

**Recommended fix:** Adopt Spec A's signature (no db) or fix Spec A to accept an optional db. Pick one and propagate.

## MEDIUM

### B-MED-1 — `_compute_convergence_snapshot_async` does not call `mark_stage_updated` for tickers that succeeded the upsert before a downstream failure
The Spec B code calls `mark_stage_updated` only after the loop completes and after the `db.commit()`. If the bulk loop crashes mid-way, no stages are marked — even though some rows have already been upserted. Acceptable since the next nightly will retry, but worth noting.

### B-MED-2 — Backtest task isolates per-ticker failures but commits after every ticker
Plan B Task B2.3:
```python
for tkr in tickers:
    try:
        ...
        await db.commit()
        await mark_stage_updated(db, tkr, "backtest")
        await db.commit()
        completed += 1
    except Exception:
        await db.rollback()
```
Two commits per ticker is fine, but on a 100-ticker run that's 200 commits + 100 stage updates. Acceptable. The `rollback()` after a per-ticker exception will roll back nothing meaningful (the prior commits are already persisted) — defensive but harmless.

### B-MED-3 — `weekly-backtest` beat schedule conflicts with `nightly_pipeline_chain_task` if Saturday 03:00 ET overlaps
Spec B §B2 schedules `crontab(hour=3, minute=0, day_of_week=6)`. The existing nightly chain runs at 21:30 ET (`backend/tasks/__init__.py`). Saturday 03:00 ET is well clear of the nightly chain. Fine.

But the `crontab(hour=3, minute=0)` is in **Celery beat's timezone** — which defaults to UTC unless explicitly set. 03:00 UTC is 22:00 ET (the previous day) in winter, 23:00 ET in summer. That collides with the nightly chain. Verify Celery's timezone setting before merging.

**Recommended fix:** Plan B should explicitly read `backend/tasks/__init__.py` for the beat timezone setting and document the actual run time. If Celery is on UTC, schedule the backtest at 08:00 UTC (= 03:00 ET winter, 04:00 ET summer).

### B-MED-4 — `news_ingest_task(tickers=[...])` does not change the lookback default
Spec B §B5 ingest_ticker calls `news_ingest_task.delay(lookback_days=90, tickers=[ticker])`. The existing `_ingest_news` reads articles for the universe and limits to 50 (Plan B Task B5.1 step 2). When `tickers=[ticker]` is supplied, the limit-50 fallback is bypassed — good — but the function still uses the existing `NEWS_LOOKBACK_DAYS` default (likely 7 or 14). Passing `lookback_days=90` overrides correctly. Verify the existing `_ingest_news` honors a non-default `lookback_days` instead of always using `NEWS_LOOKBACK_DAYS`.

### B-MED-5 — Test gap: no test that the convergence task records `pipeline_runs` row with correct status
The decorator wires this for free, but the tests (Plan B Task B1.2-B1.4) only assert behavior of the task body. Add one test that asserts a `PipelineRun` row exists with `status="success"` after a happy run.

## LOW

### B-LOW-1 — `_backfill_actual_returns` rounds price ratios with no `Decimal` conversion
`(p_now / p_then) - 1.0` uses Python floats. Negligible for return calc, but the existing platform uses `Decimal` for monetary fields. Cosmetic.

### B-LOW-2 — `BACKTEST_ENABLED` flag check happens inside the task body, not via `@tracked_task`
If `BACKTEST_ENABLED=False`, the task still creates a `PipelineRun` row (because `@tracked_task` wraps the body) and returns `{"status": "disabled"}`. Acceptable, but produces noise in the runs table. Consider checking the flag in the celery task wrapper before calling the async helper.

---

# Spec C: Entry Point Unification

The most user-facing spec. Generally well-thought-out, but it has a real authorization gap on the new bulk endpoint, no rate-limiting on auto-ingest pathways, and a concurrency landmine on the watchlist `add_to_watchlist` path that can stampede yfinance with parallel requests for the same new ticker.

## CRITICAL

### C-CRIT-1 — No rate limit / dedup on auto-ingest from concurrent users adding the same new ticker
The user prompt called this out specifically. Scenario: a viral story breaks at 09:30 ET about ticker `XYZQ`. 200 users hit "Add to watchlist" within 60 s. Each request enters `add_to_watchlist`, hits the duplicate check (no row exists for that user), then calls `await ingest_ticker("XYZQ", db, user_id=...)`. `ingest_ticker` calls `ensure_stock_exists` (which has a `INSERT ... ON CONFLICT DO NOTHING`-style guard) but then unconditionally calls `fetch_prices_delta` → 200 simultaneous yfinance requests for XYZQ. yfinance has no internal dedup. Result: 200 redundant API calls, possible IP ban from Yahoo, multiple workers rebuilding the same Stock row.

Same exact issue applies to Spec C2 (portfolio sync ingest), C3 (chat analyze_stock), and C5 (bulk CSV).

**Evidence:** `backend/services/pipelines.py:40-152` — `ingest_ticker` has no caller dedup. `backend/routers/stocks/watchlist.py` already has `@limiter.limit("2/minute")` on a different path but no decorator on `POST /watchlist`.

**Recommended fix:**
1. Add per-ticker in-flight dedup: a Redis SETNX `ingest:lock:{ticker}` with 30s TTL. If lock not acquired, await the existing in-flight ingest (or return immediately and let the user retry). Spec A's `task_tracer` doesn't help here — this needs to be inside `ingest_ticker` itself.
2. Add `@limiter.limit("10/minute")` (or similar) on the watchlist POST and portfolio create-transaction routes.
3. The bulk endpoint already has a `MAX_CONCURRENT_INGESTS=5` semaphore for *its own* batch — but does not coordinate across requests.

### C-CRIT-2 — `IngestFailedError` message includes the failing step in the user-facing 404
Spec C router handler:
```python
except IngestFailedError:
    raise HTTPException(status_code=404, detail=f"Ticker '{body.ticker.upper()}' not recognized by data provider.")
```
This is fine and respects Hard Rule #10. **However**, the spec also handles `ValueError` from `ensure_stock_exists` with a message that includes the ticker — fine — and `IngestFailedError` itself stores `step` (`exc.step`). Spec C never logs `exc.step` to Sentry/logs in the watchlist path (only the chat path does). Operators will not know *why* the ingest failed.

**Recommended fix:** `logger.warning("Watchlist ingest failed for %s step=%s", ticker, exc.step, exc_info=True)` inside the except handler. The spec already has the warning log; verify Plan C wires it.

## HIGH

### C-HIGH-1 — Bulk CSV upload writes admin-equivalent endpoint without per-row authorization beyond `require_verified_email`
Spec C §C5 uses `Depends(get_current_user)` + `require_verified_email`. There's no admin gate, which is correct (regular users own their portfolios). But there is no enforcement that each `transaction.ticker` is allowed for that user, no check that `portfolio_id` belongs to that user (the code uses `get_or_create_portfolio(user_id, db)` so this is fine), and no check on unrealistically large `shares` or `price_per_share` values. A user uploading a CSV with `shares=1e308` could brick their position recompute or cause a Decimal overflow.

**Recommended fix:** Pydantic validation on `TransactionCreate`: `shares: condecimal(gt=0, lt=Decimal("1e9"))`, `price_per_share: condecimal(gt=0, lt=Decimal("1e9"))`. Add explicit validation in `parse_csv_to_transactions` before letting Pydantic do its thing.

### C-HIGH-2 — Bulk CSV CSV reader uses `utf-8-sig` decode but no `errors=` mode
`io.StringIO(file_bytes.decode("utf-8-sig"))` will raise `UnicodeDecodeError` on non-UTF-8 input. Spec C has no try/except wrapping the decode — the FastAPI endpoint will return a 500 with the raw error. Hard Rule #10 violation.

**Recommended fix:** Wrap the decode in try/except and return 415 "CSV must be UTF-8 encoded".

### C-HIGH-3 — Stock detail debounced refresh: Redis SETNX without `last_attempt_at` race
Spec C §C4:
```python
acquired = await client.set(key, now_iso, ex=300, nx=True)
if acquired:
    refresh_ticker_task.delay(ticker.upper())
    return True, datetime.now(timezone.utc)
existing = await client.get(key)
```
Two requests racing: A wins SETNX, dispatches task, returns. B loses SETNX, reads `existing`. Between A's `set` and B's `get`, **A's value is in Redis** — fine. But if a third request C comes in *after* the 300s TTL expires but *before* the actual refresh task completes (refresh_ticker_task can take 30+ s), C wins SETNX and dispatches a *second* refresh task. The debounce is per-attempt, not per-completion. Acceptable for "5-min debounce" semantics; just be aware.

**Recommended fix:** Document this in the spec. If overlap matters, use a short SETNX (30s) for in-flight detection plus a longer refresh-completed marker (300s) written by the task itself on success.

### C-HIGH-4 — Test plan C places `tests/unit/services/test_watchlist_ingest.py` as a unit test but mocks `db` poorly
Plan C Task 1 step 1 builds a `MagicMock` `fake_db.execute.side_effect = [...]` with 3 results. The real `add_to_watchlist` flow — even after Spec C's rewrite — calls `db.execute` an unknown number of times depending on `ingest_ticker` internals. Since `ingest_ticker` is patched, the mock count is correct: count, dup, stock-after-ingest. But this is fragile — any future change in the function adds another `db.execute` call and breaks the mock without breaking the function.

**Recommended fix:** Use `MagicMock(spec=AsyncSession)` and set up specific return values per query type rather than positional `side_effect`. Better: lift the test to `tests/api/` against testcontainers and let the real DB drive it.

### C-HIGH-5 — Auto-ingest on `add_to_watchlist` shares `db` session across `ingest_ticker` and the subsequent watchlist insert
Spec C §C1:
```python
await ingest_ticker(ticker, db, user_id=str(user_id))
# ... db.execute(select(Stock)...) ...
db.add(Watchlist(...))
await db.commit()
```
`ingest_ticker` performs internal commits (Spec C explicitly notes this). After those commits, the outer `db` session has fresh state. The `Watchlist` row insert is a separate transaction. The spec accepts this trade-off ("ingest data is reusable, not user-scoped") — fine for watchlist. **But Spec C2's portfolio path uses the same pattern**: `await ingest_ticker(...) ; db.add(Transaction(...)) ; await db.commit()`. If the transaction commit fails (e.g., FK violation), the user sees an error but the ingest already wrote stock metadata. That's actually OK — inconsistent data isn't user-visible. Document the convention.

## MEDIUM

### C-MED-1 — `_try_dispatch_refresh` opens a new Redis client per request
`redis_async.from_url(settings.REDIS_URL)` constructs a fresh client every call. The platform has a `backend/services/redis_pool.py` with a shared client. Use it.

### C-MED-2 — Bulk CSV `parse_csv_to_transactions` row limit check is off-by-one
```python
for i, row in enumerate(reader, start=1):
    if i > 500:
        errors.append(...)
        break
```
The 501st row triggers the break — so the user can submit 500 rows correctly but the 501st is not parsed. Document the behavior. Better: enforce in the upload handler before parsing (count newlines).

### C-MED-3 — Spec C C4 caches signals but doesn't bust on `is_refreshing` state change
"do not cache when `is_stale=True`" — but the cache key is keyed only on ticker and not on user. After the refresh completes, the next request gets `is_stale=False` and the response *is* cached for `STANDARD` TTL. Subsequent requests serve the cached response without `is_refreshing=False, last_refresh_attempt=...` accuracy. Acceptable since `is_refreshing` flips back to false. Test 13 (`test_get_signals_stale_dispatches_refresh_task`) needs to also assert that a non-stale follow-up call returns the cached response without re-dispatching.

### C-MED-4 — Chat tool `analyze_stock` reload of snapshot uses `get_latest_signals` which may return None on race
Spec C C3 logic: `await ingest_ticker(...)` writes snapshot, then `await get_latest_signals(ticker, session)` reads it. With sub-second latency this is fine in the same session, but `ingest_ticker` may use a different inner session and the read may miss the write due to AsyncSession isolation. Test 11 (`analyze_stock_reloads_snapshot_after_ingest`) covers this by mocking — but the integration path has not been verified.

### C-MED-5 — `bulk_create_transactions` recomputes positions sequentially after the bulk insert
`for t in affected_tickers: await recompute_position(...)` — for a 50-ticker upload that's 50 sequential DB updates. Acceptable for v1 (the user just uploaded 50 transactions and waits 5 s). But if `recompute_position` itself does multiple queries, the wall-clock cost adds up. Worth a benchmark.

## LOW

### C-LOW-1 — `useSignals` `refetchInterval` returning false vs 5000 may flicker
TanStack Query v5: `refetchInterval: (q) => q.state.data?.is_refreshing ? 5000 : false`. Once the server returns `is_refreshing=false`, the interval drops to false. Verify there's no race where the server returns `is_refreshing=true` but the next poll catches the cached `is_refreshing=false` response (C-MED-3).

### C-LOW-2 — Bulk CSV template file lives at `frontend/public/portfolio-template.csv`
Will be served at `/portfolio-template.csv` — public endpoint, no auth. Fine since it's a static example, but flag for security review (template files are sometimes used to fingerprint app versions).

### C-LOW-3 — Acceptable but undocumented: `ingest_ticker` failure during bulk upload causes the row to vanish from results
`bulk_create_transactions` removes failed-ticker rows from `survivors`. Plan C does not explicitly say "failed rows are excluded from `success_tickers`". Document.

---

# Spec D: Admin + Observability

The most ambitious spec. Has the most architectural drift relative to Spec A and the most codebase mismatches. Per-task trigger endpoint security is *almost* right but has gaps.

## CRITICAL

### D-CRIT-1 — Plan D's `task_tracer` calls `langfuse_service.start_span` and `start_generation` — these methods do not exist
Verified against `backend/observability/langfuse.py` (lines 16-144). The class exposes `create_trace`, `get_trace_ref`, `record_generation`, `create_span`, `end_span`, `flush`, `shutdown`. No `start_span` or `start_generation`.

**Evidence:** Plan D Task 1 step 2:
```python
span = langfuse_service.start_span(name=name, parent=parent, metadata=metadata or {})
```

**Recommended fix:** Either (a) extend `LangfuseService` with `start_span`/`start_generation` methods that wrap `create_span` + `end_span` and `record_generation`, or (b) rewrite `task_tracer` to use the existing `create_span` / `record_generation` API. Spec A's `task_tracer` (which uses `create_trace`) is the only one that matches today's codebase. Pick the Spec A version, drop Plan D's reimplementation.

### D-CRIT-2 — D1 enforcement test (`test_every_celery_task_is_tracked`) will fail on Day 1 unless every task is migrated in the same PR
Spec D §D1: "we require a single PR for D1 so the enforcement test is green at merge". Plan D Tasks 2-12 each migrate one task module. The enforcement test is added "last" (Plan D Task ?). If a developer merges Plan D Task 2 (market_data.py) but not yet Task 3 (forecasting.py), CI will fail — but the plan says they merge in one PR. Practically, the PR is enormous (~25 task migrations) and impossible to review in one go.

**Recommended fix:** Add a temporary allowlist file (`tests/data/tracked_task_allowlist.txt`) listing tasks not yet wrapped. Each task migration removes its entry. The enforcement test reads the allowlist and only enforces for non-allowlisted tasks. After the final task migration, the allowlist is empty and can be deleted. This unblocks incremental landings.

## HIGH

### D-HIGH-1 — `task_name` whitelist is registry-based but `task_name` is taken from a regex-validated path param — no actual whitelist
Spec D §D2:
```python
task_name: Annotated[str, Path(pattern=r"^[a-zA-Z0-9_.]+$", max_length=100)],
...
task_def = registry.get_task(task_name)
if task_def is None:
    raise HTTPException(404, "Task not registered")
```
This relies on the `pipeline_registry_config.py` registry containing only safe tasks. Verify that registry has *exactly* the user-triggerable tasks and no others (e.g., does not include `purge_login_attempts_task` which would let an admin nuke audit data on demand). Audit the registry contents before shipping.

**Recommended fix:** Add an explicit `TRIGGERABLE_TASKS: set[str]` constant in `admin_pipelines.py` that the endpoint checks against, independent of whatever ends up in the registry. Belt and braces.

### D-HIGH-2 — Per-task trigger endpoint accepts `extra_kwargs: dict[str, Any]` — arbitrary kwarg injection
```python
class PipelineTaskTriggerRequest(BaseModel):
    extra_kwargs: dict[str, Any] = Field(default_factory=dict)
```
An admin can pass `extra_kwargs={"horizon_days": 999999}` (Prophet eats memory) or `extra_kwargs={"recursion_depth": ...}` to any task that takes `**kwargs`. Some tasks may accept dangerous parameters.

**Recommended fix:** Validate `extra_kwargs` against a per-task schema (e.g., `extra_kwargs: Literal["horizon_days"] | dict[str, int|str]` constrained per task). Or remove `extra_kwargs` entirely and rely on hardcoded per-task parameter sets. Recommend the latter for v1.

### D-HIGH-3 — `latency-trends` SQL uses `pipeline_runs.total_duration_seconds` — column may not exist
The column name `total_duration_seconds` is not verified against `backend/models/pipeline.py`. The standard PipelineRun fields are `started_at`, `completed_at`, status, etc. — duration may need to be computed via `EXTRACT(EPOCH FROM (completed_at - started_at))`.

**Recommended fix:** Verify the column name during implementation. If absent, use `EXTRACT(EPOCH FROM (completed_at - started_at))` or add a generated column in a migration.

### D-HIGH-4 — Concurrency: Redis state under concurrent writes from multiple workers (per user prompt)
Spec D §D5 and PipelineRunner adoption use `mark_stage_updated` and `pipeline_runs` writes. These are atomic via DB. Redis writes (cache invalidation) happen *after* `db.commit()` (Spec D §D4 explicitly enforces this order). Multiple workers running the same task name in parallel write to overlapping Redis keys. Redis `DELETE` and `SETNX` are atomic per-key — no corruption risk. The actual concurrency hazard is the *order*: worker A commits then evicts, worker B commits then evicts, both may evict each other's already-updated cache. Acceptable since the worst case is a redundant cache miss; correctness is preserved.

**No code change needed.** Document the "evict-after-commit" pattern in the cache_invalidator docstring.

### D-HIGH-5 — Cache invalidator AST coverage test uses 50-line-distance heuristic — false positives for big functions
Spec D §D4 plans an AST walk asserting that within 50 lines of every write to one of 6 tables, a matching invalidator is called. False positives: a write inside a 200-line function with the invalidator near the bottom will be flagged. False negatives: an invalidator call in a sibling helper function won't be detected.

**Recommended fix:** Use a per-function heuristic (any write inside `def f` must have the invalidator inside the same `def f`, regardless of line distance). Better: a Semgrep rule, since the project already has `.semgrep/stock-signal-rules.yml`.

### D-HIGH-6 — `tracked_task` decorator wrapping `nightly_pipeline_chain_task` creates a single PipelineRun for the entire chain
Spec D §D1 places `nightly_pipeline_chain_task` at `scope="global"`. But the chain calls 5 phase tasks each of which is also `@tracked_task` decorated → 1 root PipelineRun + 5 phase PipelineRuns. The frontend will need to know how to display nested runs. Currently `pipeline_runs` has no `parent_id`. The runs will appear as siblings in the admin UI, not as a tree.

**Recommended fix:** Either (a) add `parent_run_id: UUID | None` to `pipeline_runs` (new migration — not in scope for Spec D as stated), or (b) document that the nightly chain produces 6 sibling rows and the UI must render them by name+timestamp grouping.

## MEDIUM

### D-MED-1 — `task_tracer` `kind="generation"` path uses `model`, `usage`, `input_data` parameters that have no equivalent in `LangfuseService.record_generation`
`backend/observability/langfuse.py:71` — `record_generation` signature unknown without reading the body, but Plan D Task 1 invents kwargs that may not match. Verify before implementing.

### D-MED-2 — D5.3 sentiment scorer span uses `random.random() < SAMPLING_RATE` — not deterministic
Tests will be flaky. Use a seeded RNG or `hypothesis`.

### D-MED-3 — D6 audit recent endpoint joins `users` for email — N+1 protected by single JOIN
Verified the spec uses a single JOIN. Fine. But the response includes `user_email` for users that may have been deleted (`ON DELETE SET NULL` on the FK?). Verify `AdminAuditLog.user_id` FK behavior; the response should handle null email gracefully.

### D-MED-4 — Latency trends use `PERCENTILE_CONT(0.5)` and `0.95` over hour buckets — small sample sizes give noisy p95
With ~1 nightly run per pipeline per day, the hour bucket has 0 or 1 samples. p95 of 1 sample is the sample itself. The chart will look misleadingly flat. Consider day buckets, not hour buckets.

### D-MED-5 — Plan D Task 1 modifies `backend/observability/langfuse.py` — but D1's enforcement test runs against the unmodified module first
If the test discovers a task missing `@tracked_task` before the langfuse changes land, CI fails. Order matters in the PR.

### D-MED-6 — `LANGFUSE_TRACK_TASKS=false` in tests vs prod
Spec D says default false in tests. This is correct for hermeticity, but the same flag controls whether `pipeline_runs` rows are written. Verify the decorator separates "create PipelineRun row" (always on) from "create Langfuse trace" (gated by flag).

## LOW

### D-LOW-1 — `Path(pattern=r"^[a-zA-Z0-9_.]+$")` is correct but missing `^` and `$` anchors in spec doc
Spec D §D2 example shows `pattern=r"^[a-zA-Z0-9_.]+$"` — anchors are present, good. Verify Plan D matches.

### D-LOW-2 — D3 `ReingestResponse` schema is mentioned in API contracts but not defined
Spec D mentions `ReingestResponse` in the table but the type definition is only in the JSON example. Define the Pydantic class.

### D-LOW-3 — D6 `metadata_` vs `metadata` field name inconsistency
`AdminAuditLog.metadata_` (with trailing underscore to avoid SQLAlchemy reserved name) vs JSON response field `metadata` — verify the schema alias.

---

## Cross-cutting concerns (apply to all 4 specs)

| Concern | Spec | Severity | Fix |
|---|---|---|---|
| `task_tracer` import path inconsistent (3 different paths) | A, B, D | CRITICAL | Spec A is canonical: `backend/services/observability/task_tracer.py`. B and D must update. |
| `mark_stage_updated` signature inconsistent (with vs without `db`) | A, B | HIGH | Spec A signature should accept optional `session: AsyncSession | None`. |
| `tracked_task` parameters inconsistent (Spec A has `pipeline_name, trigger`; Spec D has `name, scope, tracer`) | A, D | HIGH | Spec A extends to include `scope`, `tracer`, accept `name=` alias. |
| Tests with DB fixtures placed in `tests/unit/` (CLAUDE.md guardrail) | A, B, C, D | HIGH | Move every `db_session`-using test to `tests/api/`. |
| No coordinated rate limit on auto-ingest entry points (C1, C2, C3, C5) | C | CRITICAL | Add Redis SETNX in-flight dedup inside `ingest_ticker` + slowapi limits on the routes. |
| `date.today()` vs UTC date in nightly tasks | B, D | HIGH | Always `datetime.now(timezone.utc).date()`. |
| Hard Rule #10 (`str(e)` leakage) — handlers in C and D need explicit verification | C, D | HIGH | Add a Semgrep rule (already in `.semgrep/`) for `HTTPException(.*str(.*e.*))` and run it on the new code. |

---

## Summary table

| Spec | CRITICAL | HIGH | MEDIUM | LOW |
|---|---|---|---|---|
| **A — Foundation** | 1 | 4 | 4 | 3 |
| **B — Completeness** | 2 | 6 | 5 | 2 |
| **C — Entry Points** | 2 | 5 | 5 | 3 |
| **D — Admin/Obs** | 2 | 6 | 6 | 3 |
| **Cross-cutting** | 2 | 5 | — | — |
| **TOTAL** | **9** | **26** | **20** | **11** |

## Top 5 must-fix before implementation starts

1. **Pin one canonical `task_tracer` location and rewrite Specs B/D imports** (A-CRIT-1, B-CRIT-2). Otherwise four parallel implementations land at four different paths.
2. **Add Redis SETNX in-flight dedup to `ingest_ticker`** (C-CRIT-1). Without this, the watchlist/portfolio/chat auto-ingest paths will hammer yfinance with N parallel calls for the same new ticker on viral events.
3. **Fix Plan D's `task_tracer` to use the actual Langfuse SDK methods** (D-CRIT-1). `start_span`/`start_generation` do not exist on `LangfuseService`. Either add them or rewrite `task_tracer`.
4. **Resolve the `mark_stage_updated(db, ...)` vs `mark_stage_updated(...)` signature mismatch** between Spec A and Spec B (A-MED-4, B-HIGH-6).
5. **Add temporary allowlist file** for the `test_every_celery_task_is_tracked` enforcement test (D-CRIT-2) so Plan D can land incrementally rather than as a single 25-task PR.

## Notes for Test Engineer review

- Every test file currently planned in `tests/unit/` that uses `db_session`, `signal_snapshot_factory`, etc. must move to `tests/api/`. Affects A, B, C, D plans.
- Plan B's `test_drift_detection_uses_backtest_mapes_when_rows_exist` is a regression test — make sure `@pytest.mark.regression` is applied.
- Plan D's `test_sentiment_batch_samples_io_at_25pct` should use Hypothesis with a fixed seed, not `random.random()` (D-MED-2).
- No test coverage anywhere for "concurrent users adding the same ticker" — add an integration test in Spec C that fires 10 concurrent `add_to_watchlist("XYZQ")` calls and asserts only one yfinance call was made (mocked at the lookup site).

*End of review.*
