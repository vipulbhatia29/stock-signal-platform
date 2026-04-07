# Spec B: Pipeline Completeness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace stubs with real implementations and fix the Prophet sentiment predict-time bug.

**Architecture:** Five sub-areas — convergence task implementation, backtest task implementation, Prophet sentiment fix at predict time, news scoring concurrent dispatch, ingest_ticker extension to news+convergence.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async, Postgres/TimescaleDB, Celery, Prophet, asyncio, pytest

**Spec:** `docs/superpowers/specs/2026-04-06-pipeline-overhaul-spec-B-completeness.md`

**Depends on:** Spec A plan must complete first (this plan uses `@tracked_task`, `mark_stage_updated`, `task_tracer` from Spec A)

---

## File Structure

### Source files modified (no new source files)
```
backend/tasks/convergence.py          # MODIFY — real async implementation + bulk helpers + decorator
backend/tasks/forecasting.py          # MODIFY — real run_backtest_task, await predict_forecast callers
backend/tools/forecasting.py          # MODIFY — async predict_forecast + real sentiment merge
backend/services/backtesting.py       # MODIFY — add public BacktestEngine.run_walk_forward
backend/services/news/sentiment_scorer.py  # MODIFY — asyncio.gather + semaphore
backend/services/pipelines.py         # MODIFY — ingest_ticker Steps 6b/8/9/10
backend/tasks/news_sentiment.py       # MODIFY — add tickers parameter
backend/tasks/market_data.py          # MODIFY — convergence in nightly chain (Phase 3)
backend/tasks/__init__.py             # MODIFY — weekly backtest beat schedule
backend/config.py                     # MODIFY — feature flags + NEWS_SCORING_MAX_CONCURRENCY
```

### Test files created

> **IMPORTANT (review finding) — `db_session` guardrail under `tests/unit/`.**
> Plan A adds a `db_session` ban to `tests/unit/conftest.py`. Any test file
> below that uses the `db_session` fixture MUST live under `tests/api/`
> (sequential, no xdist). The paths below are the CORRECTED locations;
> the earlier draft of this plan placed them under `tests/unit/` which
> would fail the guardrail at fixture setup time.

```
tests/api/test_convergence_snapshot_task.py          # NEW (moved from tests/unit/tasks/)
tests/api/test_convergence_integration.py            # NEW
tests/api/test_backtest_task.py                      # NEW (moved from tests/unit/tasks/)
tests/api/test_backtest_engine_walk_forward.py       # NEW (moved from tests/unit/services/)
tests/api/test_prophet_sentiment_predict.py          # NEW (moved from tests/unit/services/)
tests/unit/services/test_sentiment_concurrent_batch.py    # NEW (no DB — stays in unit)
tests/api/test_ingest_ticker_extended.py             # NEW (moved from tests/unit/services/)
tests/factories/convergence.py                       # NEW (if not present) — SignalConvergenceDailyFactory
tests/factories/backtest.py                          # NEW — BacktestRunFactory
```

Every "Create `tests/unit/...`" step below for a test that takes
`db_session` must be read as "Create `tests/api/...`" with the basename
preserved.

### Test files modified
```
tests/unit/tasks/test_convergence_task.py            # stub → real assertions
tests/unit/services/test_signal_convergence.py       # add divergence hit-rate with seeded rows
tests/unit/routers/test_convergence_endpoints.py     # seed convergence rows
tests/unit/tasks/test_news_sentiment_tasks.py        # tickers= routing
tests/unit/services/test_sentiment_scorer.py         # concurrency assertions
tests/unit/pipeline/test_forecasting.py              # async predict_forecast
tests/unit/test_forecasting_floor.py                 # async predict_forecast
tests/unit/test_forecast_new_ticker_training.py      # async predict_forecast
tests/unit/test_ingest_forecast_dispatch.py          # news + convergence dispatch assertions
tests/unit/services/test_pipelines.py                # mark_stage_updated assertions
tests/unit/routers/test_backtest_router.py           # new return shape
```

---

## Task B1.1: Convergence — Write failing tests

**Files:**
- Create: `tests/unit/tasks/test_convergence_snapshot.py`
- Create: `tests/factories/convergence.py` (if not present)

- [ ] **Step 1: Add `SignalConvergenceDailyFactory` if missing**

Check for `tests/factories/convergence.py`. If missing, create a factory-boy `AsyncSQLAlchemyFactory` against `SignalConvergenceDaily` with sane defaults (today, convergence_label="BULLISH", composite_score=7.5, etc.).

- [ ] **Step 2: Write the failing tests in `tests/unit/tasks/test_convergence_snapshot.py`**

```python
"""Unit tests for compute_convergence_snapshot_task (B1)."""

from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from backend.models.convergence import SignalConvergenceDaily
from backend.tasks.convergence import _compute_convergence_snapshot_async


@pytest.mark.asyncio
async def test_empty_universe_returns_no_tickers(db_session):
    with patch(
        "backend.tasks.convergence.get_all_referenced_tickers",
        AsyncMock(return_value=[]),
    ):
        result = await _compute_convergence_snapshot_async()
    assert result["status"] == "no_tickers"
    assert result["computed"] == 0


@pytest.mark.asyncio
async def test_universe_mode_inserts_one_row_per_ticker(db_session, signal_snapshot_factory, ...):
    # Seed signals/sentiment/forecast for AAPL, MSFT, GOOG via factories.
    # Run task, assert 3 new signal_convergence_daily rows for today.

@pytest.mark.asyncio
async def test_single_ticker_mode(db_session, ...):
    # ticker="AAPL" inserts only AAPL row.

@pytest.mark.asyncio
async def test_rerun_same_day_updates_via_on_conflict(db_session, ...):
    # Run twice; second run updates in place.

@pytest.mark.asyncio
async def test_backfill_actual_return_90d(db_session, ...):
    # Seed row at date=today-90 with actual_return_90d=NULL.
    # Seed StockPrice for today and today-90.
    # Run task, assert row.actual_return_90d is populated.

@pytest.mark.asyncio
async def test_backfill_noop_when_already_populated(db_session, ...):
    # Seed row with existing actual_return_90d; run → value unchanged.

@pytest.mark.asyncio
async def test_backfill_skips_when_historical_price_missing(db_session, ...):
    # No StockPrice 90 days ago → row skipped, no exception.

@pytest.mark.asyncio
async def test_mark_stage_updated_called_per_ticker(db_session, ...):
    # Patch mark_stage_updated; assert called once per ticker with stage="convergence".
```

- [ ] **Step 3: Run tests, confirm RED**

```bash
uv run pytest tests/unit/tasks/test_convergence_snapshot.py -q
```
Expected: all fail / import errors because `_compute_convergence_snapshot_async` is still the stub.

- [ ] **Step 4: Commit**

```bash
git add tests/unit/tasks/test_convergence_snapshot.py tests/factories/convergence.py
git commit -m "test(convergence): add failing tests for real snapshot task (B1)"
```

---

## Task B1.2: Convergence — Implement universe mode

**Files:**
- Modify: `backend/tasks/convergence.py`

- [ ] **Step 1: Replace the stub with real implementation**

Add imports, rewrite `compute_convergence_snapshot_task` to accept `ticker: str | None = None`, replace `_compute_convergence_snapshot_async` with the full async body from the spec. Leverage existing classification helpers in the same file and `SignalConvergenceService.get_bulk_convergence` for bulk DISTINCT ON queries.

Key pieces:
- Import `pg_insert` from `sqlalchemy.dialects.postgresql`.
- Import `async_session_factory`, `SignalConvergenceDaily`, `SignalConvergenceService`, `get_all_referenced_tickers`.
- `tickers = [ticker] if ticker else await get_all_referenced_tickers(db)`.
- `convergences = await svc.get_bulk_convergence(tickers, db)`.
- Loop convergences, build `pg_insert(...).on_conflict_do_update(index_elements=["ticker", "date"], set_={...})`.
- `await db.commit()` at end.

- [ ] **Step 2: Run the non-backfill tests**

```bash
uv run pytest tests/unit/tasks/test_convergence_snapshot.py::test_empty_universe_returns_no_tickers tests/unit/tasks/test_convergence_snapshot.py::test_universe_mode_inserts_one_row_per_ticker tests/unit/tasks/test_convergence_snapshot.py::test_single_ticker_mode tests/unit/tasks/test_convergence_snapshot.py::test_rerun_same_day_updates_via_on_conflict -q
```
Expected: 4 passing.

- [ ] **Step 3: Commit**

```bash
git add backend/tasks/convergence.py
git commit -m "feat(convergence): implement real snapshot task universe+single mode (B1)"
```

---

## Task B1.3: Convergence — Actual return backfill helpers

**Files:**
- Modify: `backend/tasks/convergence.py`

- [ ] **Step 1: Add `_backfill_actual_returns`, `_bulk_latest_price`, `_bulk_price_on_date`**

```python
async def _backfill_actual_returns(
    db: AsyncSession,
    tickers: list[str],
    today: date,
    days: int,
) -> int:
    target_date = today - timedelta(days=days)
    col = (
        SignalConvergenceDaily.actual_return_90d
        if days == 90
        else SignalConvergenceDaily.actual_return_180d
    )
    stmt = select(SignalConvergenceDaily).where(
        SignalConvergenceDaily.date == target_date,
        SignalConvergenceDaily.ticker.in_(tickers),
        col.is_(None),
    )
    rows = (await db.execute(stmt)).scalars().all()
    if not rows:
        return 0

    prices_now = await _bulk_latest_price(db, [r.ticker for r in rows], today)
    prices_then = await _bulk_price_on_date(db, [r.ticker for r in rows], target_date)

    updated = 0
    for row in rows:
        p_now = prices_now.get(row.ticker)
        p_then = prices_then.get(row.ticker)
        if p_now and p_then and p_then > 0:
            if days == 90:
                row.actual_return_90d = (p_now / p_then) - 1.0
            else:
                row.actual_return_180d = (p_now / p_then) - 1.0
            updated += 1
    return updated
```

`_bulk_latest_price` and `_bulk_price_on_date` use `DISTINCT ON (ticker) ORDER BY ticker, time DESC` against `StockPrice` filtered to a narrow window around the target date. Return `dict[ticker, float]`.

Wire the calls into `_compute_convergence_snapshot_async` right before the final commit:
```python
backfilled += await _backfill_actual_returns(db, tickers, today, days=90)
backfilled += await _backfill_actual_returns(db, tickers, today, days=180)
```

- [ ] **Step 2: Run backfill tests**

```bash
uv run pytest tests/unit/tasks/test_convergence_snapshot.py -k backfill -q
```
Expected: 3 passing.

- [ ] **Step 3: Commit**

```bash
git add backend/tasks/convergence.py
git commit -m "feat(convergence): backfill actual_return_90d/180d from prices (B1)"
```

---

## Task B1.4: Convergence — Wire `mark_stage_updated` and `@tracked_task`

**Files:**
- Modify: `backend/tasks/convergence.py`

- [ ] **Step 1: Decorate and mark stages**

```python
from backend.services.observability.task_tracer import tracked_task  # Spec A
from backend.services.ticker_state import mark_stage_updated  # Spec A

@celery_app.task(name="backend.tasks.convergence.compute_convergence_snapshot_task")
@tracked_task("convergence_snapshot")
def compute_convergence_snapshot_task(ticker: str | None = None) -> dict:
    return asyncio.run(_compute_convergence_snapshot_async(ticker=ticker))
```

Add inside `_compute_convergence_snapshot_async` after the main upsert commit:
```python
for tkr in convergences:
    await mark_stage_updated(tkr, "convergence")
await db.commit()
```

- [ ] **Step 2: Run the mark_stage tests**

```bash
uv run pytest tests/unit/tasks/test_convergence_snapshot.py::test_mark_stage_updated_called_per_ticker -q
```
Expected: pass.

- [ ] **Step 3: Full convergence test file green**

```bash
uv run pytest tests/unit/tasks/test_convergence_snapshot.py -q
```

- [ ] **Step 4: Commit**

```bash
git add backend/tasks/convergence.py
git commit -m "feat(convergence): wire tracked_task + mark_stage_updated (B1)"
```

---

## Task B1.5: Convergence — Wire into nightly chain

**Files:**
- Modify: `backend/tasks/market_data.py`

- [ ] **Step 1: Insert Phase 3 convergence step**

In `nightly_pipeline_chain_task`, locate the existing Phase 3 (drift detection) and insert convergence ahead of it. Rename what was Phase 3 → Phase 4 and Phase 4 → Phase 5 in logging strings and in `phase4_tasks` / `phase5_tasks` variables.

```python
# Phase 3: Convergence (depends on signals + forecasts from phase 2)
from backend.tasks.convergence import compute_convergence_snapshot_task
logger.info("Nightly chain phase 3: convergence snapshot")
results["convergence"] = compute_convergence_snapshot_task()
```

- [ ] **Step 2: Run market_data task tests**

```bash
uv run pytest tests/unit/tasks/test_market_data.py -q
```

- [ ] **Step 3: Commit**

```bash
git add backend/tasks/market_data.py
git commit -m "feat(pipeline): add convergence to nightly chain Phase 3 (B1)"
```

---

## Task B2.1: Backtest — Add `BacktestEngine.run_walk_forward`

**Files:**
- Modify: `backend/services/backtesting.py`
- Create: `tests/unit/services/test_backtest_engine_walk_forward.py`

- [ ] **Step 1: Write failing tests first**

```python
"""Unit tests for BacktestEngine.run_walk_forward (B2)."""

import pytest
from backend.services.backtesting import BacktestEngine


@pytest.mark.asyncio
async def test_walk_forward_linear_series_low_mape(db_session, stock_price_factory):
    # Seed 500 daily prices with a linear trend for FOO.
    engine = BacktestEngine()
    metrics = await engine.run_walk_forward("FOO", db_session, horizon_days=90)
    assert metrics.num_windows > 0
    assert metrics.mape < 0.05  # near-zero for linear data


@pytest.mark.asyncio
async def test_walk_forward_insufficient_data_returns_zero_windows(db_session, ...):
    # Seed only 100 daily prices (<365 min_train_days) → num_windows == 0.

@pytest.mark.asyncio
async def test_walk_forward_step_days_cadence(db_session, ...):
    # Verify N windows matches (total_days - min_train_days) // step_days approximately.
```

Run: `uv run pytest tests/unit/services/test_backtest_engine_walk_forward.py -q` → RED (method does not exist).

- [ ] **Step 2: Implement `run_walk_forward` on `BacktestEngine`**

Signature:
```python
async def run_walk_forward(
    self,
    ticker: str,
    db: AsyncSession,
    horizon_days: int = 90,
    min_train_days: int = 365,
    step_days: int = 30,
) -> BacktestMetrics:
```

Behavior:
1. Bulk query `StockPrice` for ticker (`select(StockPrice).where(ticker==ticker).order_by(time)`). Load into DataFrame.
2. Use existing `_generate_expanding_windows(data_start, data_end, min_train_days, step_days, horizon_days)` to get windows.
3. For each window, slice train / target, call a private `_fit_prophet_sync(train_df)` using `asyncio.to_thread(...)` (Prophet is CPU-bound sync). Produce prediction for `test_date`.
4. Compare against actual price; accumulate to pass into existing `_compute_mape`, `_compute_mae`, `_compute_rmse`, `_compute_direction_accuracy`, `_compute_ci_containment`, `_compute_ci_bias`.
5. Return `BacktestMetrics(mape=..., mae=..., rmse=..., direction_accuracy=..., ci_containment=..., ci_bias=..., num_windows=len(windows))`.

The training helper shares Prophet config with `train_prophet_model` but does NOT touch `ModelVersion` or `artifact_path` — backtest windows are throwaway.

Sentiment regressors follow the same real-historical merge pattern as B3 (via `_fetch_sentiment_regressors`).

- [ ] **Step 3: Run tests green**

```bash
uv run pytest tests/unit/services/test_backtest_engine_walk_forward.py -q
```

- [ ] **Step 4: Commit**

```bash
git add backend/services/backtesting.py tests/unit/services/test_backtest_engine_walk_forward.py
git commit -m "feat(backtest): public BacktestEngine.run_walk_forward (B2)"
```

---

## Task B2.2: Backtest — Failing task tests

**Files:**
- Create: `tests/unit/tasks/test_backtest_task.py`
- Create: `tests/factories/backtest.py` (if not present)

- [ ] **Step 1: Add `BacktestRunFactory`**

Factory-boy over `BacktestRun` with sane defaults (`mape=0.12, direction_accuracy=0.55, num_windows=10`).

- [ ] **Step 2: Write failing tests**

```python
"""Unit tests for run_backtest_task (B2)."""

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from backend.models.backtest import BacktestRun
from backend.tasks.forecasting import _run_backtest_async


@pytest.mark.asyncio
async def test_single_ticker_inserts_one_row(db_session, ...):
    # Patch BacktestEngine.run_walk_forward to return BacktestMetrics.
    result = await _run_backtest_async("AAPL", 90)
    rows = (await db_session.execute(select(BacktestRun))).scalars().all()
    assert len(rows) == 1
    assert rows[0].horizon_days == 90
    assert result["completed"] == 1


@pytest.mark.asyncio
async def test_universe_mode_three_tickers(db_session, ...):
    # Patch get_all_referenced_tickers → [AAPL, MSFT, GOOG], patch engine.
    # Assert 3 rows.

@pytest.mark.asyncio
async def test_per_ticker_failure_isolated(db_session, ...):
    # Patch engine.run_walk_forward to raise for MSFT only.
    # Assert AAPL and GOOG succeed; result["failed"] == 1, completed == 2.

@pytest.mark.asyncio
async def test_mark_stage_updated_called_on_success_only(db_session, ...):
    # Patch mark_stage_updated; assert called only for succeeding tickers.
```

Run → RED.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/tasks/test_backtest_task.py tests/factories/backtest.py
git commit -m "test(backtest): failing tests for run_backtest_task (B2)"
```

---

## Task B2.3: Backtest — Replace stub with real implementation

**Files:**
- Modify: `backend/tasks/forecasting.py`

- [ ] **Step 1: Replace `run_backtest_task` stub**

```python
from backend.services.observability.task_tracer import tracked_task
from backend.services.ticker_state import mark_stage_updated

@celery_app.task(name="backend.tasks.forecasting.run_backtest_task")
@tracked_task("backtest")
def run_backtest_task(ticker: str | None = None, horizon_days: int = 90) -> dict:
    return asyncio.run(_run_backtest_async(ticker, horizon_days))


async def _run_backtest_async(ticker: str | None, horizon_days: int) -> dict:
    from datetime import date
    from backend.database import async_session_factory
    from backend.models.backtest import BacktestRun
    from backend.services.backtesting import BacktestEngine
    from backend.services.ticker_universe import get_all_referenced_tickers

    engine = BacktestEngine()
    completed = 0
    failed: list[str] = []

    async with async_session_factory() as db:
        tickers = [ticker] if ticker else await get_all_referenced_tickers(db)
        for tkr in tickers:
            try:
                metrics = await engine.run_walk_forward(tkr, db, horizon_days=horizon_days)
                db.add(BacktestRun(
                    ticker=tkr,
                    horizon_days=horizon_days,
                    run_date=date.today(),
                    mape=metrics.mape,
                    mae=metrics.mae,
                    rmse=metrics.rmse,
                    direction_accuracy=metrics.direction_accuracy,
                    ci_containment=metrics.ci_containment,
                    ci_bias=metrics.ci_bias,
                    num_windows=metrics.num_windows,
                ))
                await db.commit()
                await mark_stage_updated(tkr, "backtest")
                await db.commit()
                completed += 1
            except Exception:
                await db.rollback()
                logger.exception("Backtest failed for %s", tkr)
                failed.append(tkr)

    return {
        "status": "ok",
        "completed": completed,
        "failed": len(failed),
        "horizon_days": horizon_days,
        "ticker": ticker,
    }
```

- [ ] **Step 2: Run tests green**

```bash
uv run pytest tests/unit/tasks/test_backtest_task.py -q
```

- [ ] **Step 3: Commit**

```bash
git add backend/tasks/forecasting.py
git commit -m "feat(backtest): real run_backtest_task implementation (B2)"
```

---

## Task B2.4: Backtest — Weekly beat schedule

**Files:**
- Modify: `backend/tasks/__init__.py`

- [ ] **Step 1: Add beat entry**

```python
from celery.schedules import crontab  # if not already imported

celery_app.conf.beat_schedule.update({
    "weekly-backtest": {
        "task": "backend.tasks.forecasting.run_backtest_task",
        "schedule": crontab(hour=3, minute=0, day_of_week=6),  # Saturday 03:00
    },
})
```

- [ ] **Step 2: Add assertion test**

In `tests/unit/tasks/test_backtest_task.py`:

```python
def test_weekly_beat_schedule_registered():
    from backend.tasks import celery_app
    assert "weekly-backtest" in celery_app.conf.beat_schedule
    entry = celery_app.conf.beat_schedule["weekly-backtest"]
    assert entry["task"] == "backend.tasks.forecasting.run_backtest_task"
```

Run: `uv run pytest tests/unit/tasks/test_backtest_task.py::test_weekly_beat_schedule_registered -q`.

- [ ] **Step 3: Commit**

```bash
git add backend/tasks/__init__.py tests/unit/tasks/test_backtest_task.py
git commit -m "feat(backtest): weekly Saturday 03:00 beat schedule (B2)"
```

---

## Task B2.5: Backtest — Verify drift detection consumes new rows

**Files:**
- Modify: `tests/unit/tasks/test_evaluation.py` (or equivalent drift test file)

- [ ] **Step 1: Read `backend/tasks/evaluation.py:241-256`** to confirm the existing query batches backtest MAPEs by ticker via `func.min(BacktestRun.mape)`. No code change needed here — the task already consumes these rows.

- [ ] **Step 2: Add regression test**

```python
@pytest.mark.asyncio
async def test_drift_detection_uses_backtest_mapes_when_rows_exist(db_session, backtest_run_factory):
    # Seed BacktestRun rows for AAPL with mape=0.08.
    # Run check_drift_task / _check_drift_async.
    # Assert compute_calibrated_threshold called with mape=0.08, not default.
```

Run: `uv run pytest tests/unit/tasks/test_evaluation.py -k drift -q`.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/tasks/test_evaluation.py
git commit -m "test(drift): verify consumer reads backtest_runs when populated (B2)"
```

---

## Task B3.1: Prophet sentiment — Write failing predict-time test

**Files:**
- Create: `tests/unit/services/test_prophet_sentiment_predict.py`

- [ ] **Step 1: Write the regression test demonstrating the bug**

```python
"""Regression test: Prophet sentiment regressors must flow through at predict time (B3)."""

import pandas as pd
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.tools.forecasting import predict_forecast, train_prophet_model


@pytest.mark.asyncio
async def test_sentiment_regressor_is_honored_at_predict_time(
    db_session, stock_price_factory, news_sentiment_daily_factory
):
    """Deterministic synthetic test: 200 days of prices correlated with sentiment.

    Trains Prophet with sentiment regressors and asserts the predict-time
    forecast respects the training-time correlation. The pre-fix behaviour
    (hard-coded 0.0 regressor) would break this invariant.
    """
    import numpy as np

    rng = np.random.default_rng(42)
    days = 200
    # Synthetic sentiment series with structure (sinusoid + small noise).
    sentiment = 0.5 * np.sin(np.linspace(0, 6 * np.pi, days)) + rng.normal(0, 0.05, days)
    # Prices correlated with sentiment via a known beta.
    beta = 10.0
    base = 100.0
    prices = base + np.cumsum(beta * sentiment + rng.normal(0, 0.2, days))

    for i, (p, s) in enumerate(zip(prices, sentiment, strict=True)):
        await stock_price_factory(ticker="FOO", day_offset=-(days - i), close=float(p))
        await news_sentiment_daily_factory(ticker="FOO", day_offset=-(days - i), stock_sentiment=float(s))

    mv = await train_prophet_model("FOO", db_session)
    forecasts_real = await predict_forecast(mv, db_session)

    # Simulate the bug: force _fetch_sentiment_regressors to return None so the
    # sentiment column degrades to the 0.0 fallback. A predict run that ignores
    # the regressor must produce materially different yhat values.
    with patch(
        "backend.tools.forecasting._fetch_sentiment_regressors", AsyncMock(return_value=None)
    ):
        forecasts_zeroed = await predict_forecast(mv, db_session)

    # At least one horizon must move by more than noise (>0.5 $) when sentiment
    # is honored vs zeroed — the trained beta guarantees it.
    deltas = [abs(a.yhat_90 - b.yhat_90) for a, b in zip(forecasts_real, forecasts_zeroed, strict=True)]
    assert max(deltas) > 0.5, (
        "Predict-time sentiment regressor had no effect on yhat — regression."
    )


@pytest.mark.asyncio
async def test_predict_forecast_without_sentiment_still_works(db_session, stock_price_factory):
    # Train without sentiment.
    mv = await train_prophet_model("FOO", db_session)
    forecasts = await predict_forecast(mv, db_session)
    assert len(forecasts) > 0


@pytest.mark.asyncio
async def test_forecast_period_uses_7day_trailing_mean(db_session, ...):
    # Seed sentiment; assert future[mask_future_dates]["stock_sentiment"]
    # equals the mean of last 7 training days' values.

@pytest.mark.asyncio
async def test_forecast_period_falls_back_to_zero_when_no_sentiment(db_session, ...):
    # Model has regressors but _fetch_sentiment_regressors → empty; projection == 0.0.

@pytest.mark.asyncio
async def test_predict_forecast_is_async(db_session, ...):
    import inspect
    assert inspect.iscoroutinefunction(predict_forecast)
```

- [ ] **Step 2: Run → RED**

```bash
uv run pytest tests/unit/services/test_prophet_sentiment_predict.py -q
```

Currently `predict_forecast` is sync, so `await` + `inspect.iscoroutinefunction` both fail.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/services/test_prophet_sentiment_predict.py
git commit -m "test(forecast): failing sentiment predict-time regression (B3)"
```

---

## Task B3.2: Prophet sentiment — Make `predict_forecast` async

**Files:**
- Modify: `backend/tools/forecasting.py`

- [ ] **Step 1: Change signature**

```python
async def predict_forecast(
    model_version: ModelVersion,
    db: AsyncSession,
    horizons: list[int] | None = None,
) -> list[ForecastResult]:
    ...
```

Do NOT yet change the sentiment logic — that's the next task. Just add `async` and the `db` parameter; internal body remains sync logic wrapped appropriately (pandas / Prophet `predict` are CPU-bound but fine to call inline for now).

- [ ] **Step 2: Update the three callers to `await`**

`backend/tasks/forecasting.py`:
- Line ~71 (`_model_retrain_all_async`): `forecasts = await predict_forecast(model_version, db)`
- Line ~116 (`_forecast_refresh_async`): `forecasts = await predict_forecast(model_version, db)`
- Line ~211 (`retrain_single_ticker_task._retrain`): `forecasts = await predict_forecast(model_version, db)`

- [ ] **Step 3: Update existing test files for async**

`tests/unit/pipeline/test_forecasting.py`, `tests/unit/test_forecasting_floor.py`, `tests/unit/test_forecast_new_ticker_training.py`: change `predict_forecast(mv)` to `await predict_forecast(mv, db_session)`.

- [ ] **Step 4: Run existing suite**

```bash
uv run pytest tests/unit/pipeline/test_forecasting.py tests/unit/test_forecasting_floor.py tests/unit/test_forecast_new_ticker_training.py -q
```
Expected: passing (behavior unchanged, just async).

- [ ] **Step 5: Commit**

```bash
git add backend/tools/forecasting.py backend/tasks/forecasting.py tests/unit/pipeline/test_forecasting.py tests/unit/test_forecasting_floor.py tests/unit/test_forecast_new_ticker_training.py
git commit -m "refactor(forecast): make predict_forecast async + db param (B3)"
```

---

## Task B3.3: Prophet sentiment — Real historical merge + 7-day projection

**Files:**
- Modify: `backend/tools/forecasting.py`

- [ ] **Step 1: Delete the KNOWN LIMITATION hardcode**

Remove the comment block and these three lines at roughly `backend/tools/forecasting.py:201-211`:
```python
future["stock_sentiment"] = 0.0
future["sector_sentiment"] = 0.0
future["macro_sentiment"] = 0.0
```

- [ ] **Step 2: Replace with real sentiment merge**

```python
if has_sentiment_regressors:
    training_end = model.history["ds"].max().date()
    max_horizon = max(horizons or DEFAULT_HORIZONS)
    target_date = date.today() + timedelta(days=max_horizon)

    hist_df = await _fetch_sentiment_regressors(
        model_version.ticker,
        model.history["ds"].min(),
        pd.Timestamp(target_date),
        db,
    )
    if hist_df is None or hist_df.empty:
        hist_df = pd.DataFrame(
            columns=["ds", "stock_sentiment", "sector_sentiment", "macro_sentiment"]
        )

    # 7-day trailing mean projection for forecast dates
    cutoff = pd.Timestamp(training_end) - pd.Timedelta(days=7)
    hist_recent = hist_df[hist_df["ds"] >= cutoff]
    projection = {
        col: float(hist_recent[col].mean()) if not hist_recent.empty else 0.0
        for col in ("stock_sentiment", "sector_sentiment", "macro_sentiment")
    }

    future = future.merge(hist_df, on="ds", how="left")
    for col, fill in projection.items():
        mask = future["ds"].dt.date > training_end
        future.loc[mask, col] = fill
        future[col] = future[col].fillna(0.0)
```

- [ ] **Step 3: Run the B3 tests**

```bash
uv run pytest tests/unit/services/test_prophet_sentiment_predict.py -q
```
Expected: all green.

- [ ] **Step 4: Commit**

```bash
git add backend/tools/forecasting.py
git commit -m "fix(forecast): real sentiment values in predict future frame (B3)"
```

---

## Task B4.1: News scoring — Failing concurrency test

**Files:**
- Create: `tests/unit/services/test_sentiment_concurrent_batch.py`

- [ ] **Step 1: Write the wall-clock bound test**

```python
"""Tests for concurrent score_batch dispatch (B4)."""

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest

from backend.services.news.sentiment_scorer import SentimentScorer


@pytest.mark.asyncio
async def test_score_batch_runs_concurrently():
    scorer = SentimentScorer(api_key="fake")
    articles = [object()] * 30  # 2 batches of 15

    async def slow_single(batch):
        await asyncio.sleep(0.3)
        return [object()] * len(batch)

    with patch.object(scorer, "_score_single_batch", side_effect=slow_single):
        t0 = time.monotonic()
        result = await scorer.score_batch(articles)
        elapsed = time.monotonic() - t0

    assert len(result) == 30
    # Concurrent: ~0.3s; sequential would be ~0.6s. Allow headroom.
    assert elapsed < 0.5


@pytest.mark.asyncio
async def test_score_batch_semaphore_cap():
    scorer = SentimentScorer(api_key="fake")
    articles = [object()] * (15 * 20)  # 20 batches
    in_flight = 0
    max_in_flight = 0
    lock = asyncio.Lock()

    async def track(batch):
        nonlocal in_flight, max_in_flight
        async with lock:
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
        await asyncio.sleep(0.05)
        async with lock:
            in_flight -= 1
        return [object()] * len(batch)

    with patch.object(scorer, "_score_single_batch", side_effect=track):
        await scorer.score_batch(articles)

    assert max_in_flight <= 5  # default NEWS_SCORING_MAX_CONCURRENCY


@pytest.mark.asyncio
async def test_score_batch_one_failure_does_not_poison_others():
    scorer = SentimentScorer(api_key="fake")
    articles = [object()] * 45  # 3 batches
    calls = {"n": 0}

    async def flaky(batch):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("simulated")
        return [object()] * len(batch)

    with patch.object(scorer, "_score_single_batch", side_effect=flaky):
        result = await scorer.score_batch(articles)
    assert len(result) == 30  # only 2 good batches returned


@pytest.mark.asyncio
async def test_empty_articles_returns_empty():
    scorer = SentimentScorer(api_key="fake")
    assert await scorer.score_batch([]) == []


@pytest.mark.asyncio
async def test_configurable_concurrency(monkeypatch):
    from backend.config import settings
    monkeypatch.setattr(settings, "NEWS_SCORING_MAX_CONCURRENCY", 2)
    # Re-run the semaphore cap assertion with max_in_flight <= 2.
```

Run → RED (sequential impl fails wall-clock bound).

- [ ] **Step 2: Commit**

```bash
git add tests/unit/services/test_sentiment_concurrent_batch.py
git commit -m "test(news): failing concurrent score_batch tests (B4)"
```

---

## Task B4.2: News scoring — Implement `asyncio.gather` + semaphore

**Files:**
- Modify: `backend/config.py`
- Modify: `backend/services/news/sentiment_scorer.py`

- [ ] **Step 1: Add setting**

In `backend/config.py`, add:
```python
NEWS_SCORING_MAX_CONCURRENCY: int = 5
```

- [ ] **Step 2: Rewrite `score_batch`**

```python
async def score_batch(self, articles: list[RawArticle]) -> list[ArticleScore]:
    if not self._api_key:
        logger.warning("OPENAI_API_KEY not set — skipping sentiment scoring")
        return []
    if not articles:
        return []

    sem = asyncio.Semaphore(settings.NEWS_SCORING_MAX_CONCURRENCY)

    async def _bounded(batch: list[RawArticle]) -> list[ArticleScore]:
        async with sem:
            with task_tracer.trace("news_sentiment_batch", metadata={"batch_size": len(batch)}):
                return await self._score_single_batch(batch)

    batches = [
        articles[i : i + BATCH_SIZE]
        for i in range(0, len(articles), BATCH_SIZE)
    ]
    results = await asyncio.gather(
        *(_bounded(b) for b in batches), return_exceptions=True
    )

    all_scores: list[ArticleScore] = []
    for idx, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(
                "Batch %d failed during concurrent scoring", idx, exc_info=result
            )
            continue
        all_scores.extend(result)
    return all_scores
```

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/unit/services/test_sentiment_concurrent_batch.py -q
uv run pytest tests/unit/services/test_sentiment_scorer.py -q
```
Expected: both green.

- [ ] **Step 4: Commit**

```bash
git add backend/config.py backend/services/news/sentiment_scorer.py
git commit -m "perf(news): concurrent score_batch with Semaphore(5) (B4)"
```

---

## Task B5.1: ingest_ticker — Extend `news_ingest_task` with `tickers` param

**Files:**
- Modify: `backend/tasks/news_sentiment.py`
- Modify: `tests/unit/tasks/test_news_sentiment_tasks.py`

- [ ] **Step 1: Write failing test**

```python
@pytest.mark.asyncio
async def test_news_ingest_task_routes_explicit_tickers(monkeypatch):
    captured = {}
    async def fake_fetch(ticker, **kwargs):
        captured.setdefault("tickers", []).append(ticker)
        return []
    monkeypatch.setattr("backend.tasks.news_sentiment._fetch_articles_for_ticker", fake_fetch)
    await _ingest_news(lookback_days=30, tickers=["FOO", "BAR"])
    assert sorted(captured["tickers"]) == ["BAR", "FOO"]
```

- [ ] **Step 2: Add parameter**

```python
@celery_app.task(bind=True, name="backend.tasks.news_sentiment.news_ingest_task")
def news_ingest_task(
    self,
    lookback_days: int = NEWS_LOOKBACK_DAYS,
    tickers: list[str] | None = None,
) -> dict:
    return asyncio.run(_ingest_news(lookback_days, tickers=tickers))


async def _ingest_news(lookback_days: int, tickers: list[str] | None = None) -> dict:
    ...
    async with async_session_factory() as session:
        if tickers:
            ticker_list = [t.upper() for t in tickers]
        else:
            result = await session.execute(
                select(Stock.ticker).where(Stock.is_active.is_(True)).limit(50)
            )
            ticker_list = [row[0] for row in result.all()]
    ...
```

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/unit/tasks/test_news_sentiment_tasks.py -q
```

- [ ] **Step 4: Commit**

```bash
git add backend/tasks/news_sentiment.py tests/unit/tasks/test_news_sentiment_tasks.py
git commit -m "feat(news): tickers param for news_ingest_task (B5)"
```

---

## Task B5.2: ingest_ticker — `compute_convergence_snapshot_task` single-ticker mode

**Files:** Already done in Task B1.2 (the task accepts `ticker=None`). This task is verification-only.

- [ ] **Step 1: Verify `compute_convergence_snapshot_task.delay(ticker="AAPL")` works**

Add to `tests/unit/tasks/test_convergence_snapshot.py`:

```python
def test_task_signature_accepts_ticker_kwarg():
    from backend.tasks.convergence import compute_convergence_snapshot_task
    import inspect
    sig = inspect.signature(compute_convergence_snapshot_task)
    assert "ticker" in sig.parameters
    assert sig.parameters["ticker"].default is None
```

Run: `uv run pytest tests/unit/tasks/test_convergence_snapshot.py::test_task_signature_accepts_ticker_kwarg -q`.

- [ ] **Step 2: Commit (only if test was added)**

```bash
git add tests/unit/tasks/test_convergence_snapshot.py
git commit -m "test(convergence): assert ticker kwarg present on task (B5)"
```

---

## Task B5.3: ingest_ticker — Failing extension tests

**Files:**
- Create: `tests/unit/services/test_ingest_ticker_extended.py`

- [ ] **Step 1: Write tests for dispatch + mark_stage_updated**

```python
"""Tests for ingest_ticker Steps 6b/8/9/10 (B5)."""

from unittest.mock import AsyncMock, patch

import pytest

from backend.services.pipelines import ingest_ticker


@pytest.mark.asyncio
async def test_new_ticker_dispatches_news_backfill(db_session, monkeypatch):
    # Patch at the pipelines.py lookup site — pipelines.py does
    # `from backend.tasks.news_sentiment import news_ingest_task` etc.,
    # so the symbol lives on `backend.services.pipelines`.
    with patch("backend.services.pipelines.news_ingest_task.delay") as mock_news, \
         patch("backend.services.pipelines.compute_convergence_snapshot_task.delay") as mock_conv, \
         patch("backend.services.pipelines.retrain_single_ticker_task.delay"):
        # Configure ingest_ticker internals so is_new=True path is taken.
        await ingest_ticker("NEWCO", db_session)
    mock_news.assert_called_once_with(lookback_days=90, tickers=["NEWCO"])
    mock_conv.assert_called_once_with(ticker="NEWCO")


@pytest.mark.asyncio
async def test_existing_ticker_skips_news_and_convergence(db_session, ...):
    # is_new=False → neither .delay is called.

@pytest.mark.asyncio
async def test_mark_stage_updated_called_for_prices_signals_recommendation(db_session, ...):
    with patch("backend.services.pipelines.mark_stage_updated", AsyncMock()) as mock_mark:
        await ingest_ticker("AAPL", db_session)
    stages = [c.kwargs.get("stage") or c.args[2] for c in mock_mark.call_args_list]
    assert "prices" in stages
    assert "signals" in stages
    assert "recommendation" in stages


@pytest.mark.asyncio
async def test_news_dispatch_failure_does_not_abort_pipeline(db_session, monkeypatch):
    with patch(
        "backend.services.pipelines.news_ingest_task.delay",
        side_effect=RuntimeError("broker down"),
    ):
        result = await ingest_ticker("NEWCO", db_session)
    assert result["status"] == "ok"
```

Run → RED.

- [ ] **Step 2: Commit**

```bash
git add tests/unit/services/test_ingest_ticker_extended.py
git commit -m "test(pipelines): failing ingest_ticker extension tests (B5)"
```

---

## Task B5.4: ingest_ticker — Add Steps 6b/8/9/10

**Files:**
- Modify: `backend/services/pipelines.py`

- [ ] **Step 1: Add imports**

```python
from backend.services.ticker_state import mark_stage_updated  # Spec A
```

- [ ] **Step 2: Add Step 6b after `update_last_fetched_at`**

```python
# ── Step 6 (existing): Update last_fetched_at ──
await update_last_fetched_at(ticker, db)

# ── Step 6b (new): Mark stage timestamps (Spec A) ──
await mark_stage_updated(ticker, "prices")
if composite_score is not None:
    await mark_stage_updated(ticker, "signals")
```

- [ ] **Step 3: Add Step 8 (news backfill) and Step 9 (convergence seed) for new tickers**

After the existing forecast dispatch (Step 7b):

```python
if is_new:
    try:
        from backend.tasks.news_sentiment import news_ingest_task
        news_ingest_task.delay(lookback_days=90, tickers=[ticker])
    except Exception:
        logger.warning(
            "Failed to dispatch news backfill for %s", ticker, exc_info=True
        )

    try:
        from backend.tasks.convergence import compute_convergence_snapshot_task
        compute_convergence_snapshot_task.delay(ticker=ticker)
    except Exception:
        logger.warning(
            "Failed to dispatch convergence seed for %s", ticker, exc_info=True
        )
```

- [ ] **Step 4: Add Step 10 — mark `recommendation` stage inside `_generate_recommendation_with_context`**

Right after `store_recommendation(rec, user_id, db)`:
```python
await mark_stage_updated(ticker, "recommendation")
```

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/unit/services/test_ingest_ticker_extended.py tests/unit/services/test_pipelines.py tests/unit/test_ingest_forecast_dispatch.py -q
```
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add backend/services/pipelines.py
git commit -m "feat(pipelines): ingest_ticker Steps 6b/8/9/10 news+convergence+stages (B5)"
```

---

## Task Final.1: Feature flags

**Files:**
- Modify: `backend/config.py`
- Modify: `backend/tasks/convergence.py`, `backend/tasks/forecasting.py`, `backend/tools/forecasting.py`

- [ ] **Step 1: Add flags to `backend/config.py`**

```python
CONVERGENCE_SNAPSHOT_ENABLED: bool = True
BACKTEST_ENABLED: bool = True
PROPHET_REAL_SENTIMENT_ENABLED: bool = True
# NEWS_SCORING_MAX_CONCURRENCY already added in B4.2
```

- [ ] **Step 2: Add early-return guards**

- `compute_convergence_snapshot_task`: `if not settings.CONVERGENCE_SNAPSHOT_ENABLED: return {"status": "disabled"}`
- `run_backtest_task`: `if not settings.BACKTEST_ENABLED: return {"status": "disabled"}`
- `predict_forecast` sentiment branch: wrap `has_sentiment_regressors` block with `if settings.PROPHET_REAL_SENTIMENT_ENABLED and has_sentiment_regressors:` — else fall back to zeroing (pre-fix behavior, for emergency rollback).

- [ ] **Step 3: Commit**

```bash
git add backend/config.py backend/tasks/convergence.py backend/tasks/forecasting.py backend/tools/forecasting.py
git commit -m "feat(config): feature flags for B1/B2/B3 rollback (Spec B)"
```

---

## Task Final.2: Lint + full test run

- [ ] **Step 1: Ruff lint and format**

```bash
uv run ruff check --fix backend/ tests/
uv run ruff format backend/ tests/
uv run ruff check backend/ tests/
```
Expected: zero errors.

- [ ] **Step 2: Full unit test run**

```bash
uv run pytest tests/unit/ -q --tb=short
```
Expected: all green, no regressions from Spec A baseline.

- [ ] **Step 3: API integration tests (sequential)**

```bash
uv run pytest tests/api/test_convergence_integration.py -q
```

- [ ] **Step 4: Pyright delta (changed files only)**

```bash
uv run pyright backend/tasks/convergence.py backend/tasks/forecasting.py backend/tools/forecasting.py backend/services/backtesting.py backend/services/news/sentiment_scorer.py backend/services/pipelines.py backend/tasks/news_sentiment.py
```
Expected: no new errors above baseline.

- [ ] **Step 5: Commit any formatting-only fixups**

```bash
git add -A
git commit -m "chore(spec-b): ruff format + lint pass"
```

---

## Constraints

Same as Plan A:
- `uv run` only; never bare `python` or `pip`.
- One task = one commit. Commit message references `(B1)`..`(B5)`.
- TDD order: failing test → implementation → green test → commit.
- Every new/touched Celery task uses `@tracked_task` from Spec A.
- Every stage-completion point calls `mark_stage_updated` from Spec A.
- Never bypass hooks (`--no-verify`).
- No `str(e)` in user-facing output (Hard Rule 10).
- Edit existing files; create new files only where explicitly listed under File Structure.
- Branch from `develop`; PR targets `develop`.

---

*End of Plan B.*
