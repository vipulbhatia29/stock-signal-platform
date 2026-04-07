# Spec E: Forecast Quality & Scale

**Status:** Draft
**Date:** 2026-04-06
**Authors:** Pipeline Overhaul team
**Part of:** Pipeline Architecture Overhaul Epic

---

## Problem Statement

Three pipeline scaling and quality issues that aren't blocking but degrade the product:

1. **20-new-models-per-night cap is too low for new portfolio uploads.** A user uploading a 97-ticker portfolio (real number from Session 95) waits **5 nights** for all positions to have forecasts. Cap is intended for opportunistic background sweep, not for explicit user actions. Evidence: `backend/tasks/forecasting.py:21` `MAX_NEW_MODELS_PER_NIGHT = 20`.

2. **Biweekly full retrain leaves models stale for up to 14 days** even when drift detection isn't triggered. Drift detection (`tasks/evaluation.py:_check_drift_async`) catches sudden degradation but not gradual concept drift. Evidence: `backend/tasks/__init__.py:79-83` schedules `model_retrain_all_task` weekly with task-level biweekly filter.

3. **Intraday refresh is sequential and runs heavy operations on every cycle.** With 600 tickers × ~5 sec each (prices + signals + QuantStats + yfinance info refresh + dividends), each cycle takes ~50 minutes. Beat schedule fires every 30 minutes — next cycle queues before previous finishes → cascading backup. Evidence: `backend/tasks/market_data.py:219-228` (sequential loop), `backend/tasks/__init__.py:38-41` (30-min schedule).

---

## Goals

- New-ticker forecast availability ≤ 24h after add (vs current ≤ 5d for large portfolios)
- Forecast freshness ≤ 7 days (vs current ≤ 14d worst case)
- Intraday refresh cycle time ≤ 15 min (vs current 50 min) so the 30-min beat schedule has headroom
- Reduce Celery worker queue depth during intraday refresh

## Non-Goals

- Adding model ensemble (Prophet + ARIMA + LSTM) — defer to a future spec when we have backtest baselines to compare
- Changing forecast horizons (90/180/270d stay)
- Replacing Prophet — out of scope

---

## Design

### E1. Raise new-ticker forecast cap + bypass for user-initiated

**Files modified:**
- `backend/tasks/forecasting.py:21` — `MAX_NEW_MODELS_PER_NIGHT = 100` (up from 20)
- `backend/tasks/forecasting.py:retrain_single_ticker_task` — add `priority: bool = False` parameter; user-initiated calls pass `priority=True` and bypass any cap. The cap only applies to the opportunistic nightly sweep in `_forecast_refresh_async:130-162`.

**Rationale for 100:**
- Prophet training takes ~30-90 sec per ticker (depends on data points)
- 100 × 60s avg = 100 minutes; nightly sweep runs in `_forecast_refresh_async` Phase 2 of nightly chain
- 100 fits within an hour budget without dominating the nightly window
- User-initiated bypass ensures portfolio uploads aren't gated by sweep queue

**Caller updates:**
- `backend/services/pipelines.py:127-132` — `ingest_ticker` already calls `retrain_single_ticker_task.delay(ticker)` for `is_new` tickers; add `priority=True` arg so user-driven adds bypass any future cap logic
- `backend/tasks/forecasting.py:_forecast_refresh_async:140-150` — sweep loop unchanged (cap still applies here)

**Upstream:** None.
**Downstream:** Portfolio upload UX (Spec C5 bulk upload) gets full forecast coverage in 1 night for portfolios up to ~100 new tickers.

---

### E2. Weekly Prophet retrain (was biweekly)

**Files modified:**
- `backend/tasks/__init__.py:79-83` — change beat schedule:
```python
"model-retrain-weekly": {
    "task": "backend.tasks.forecasting.model_retrain_all_task",
    "schedule": crontab(hour=2, minute=0, day_of_week=0),  # Sunday 02:00 ET
},
```
- `backend/tasks/forecasting.py:_model_retrain_all_async` — remove the biweekly filtering logic at the task level (currently the beat fires weekly but the task self-filters to every other week)

**Rationale:**
- Biweekly is too long for concept drift on volatile stocks
- Drift detection (Spec B2 calibrated, in our overhaul) catches acute drift between retrains
- Weekly retrain is the right balance between freshness and compute cost
- 580 tickers × ~60s = ~10 hours. Sunday 02:00 ET runs through to ~12:00 ET — fine for off-hours

**Upstream:** None.
**Downstream:** Sunday morning admins should expect higher Celery worker load. Existing alerting (in-app pipeline alerts) catches failures.

---

### E3. Split intraday refresh into fast/slow paths + parallelize fast path

**Files modified:**
- `backend/tasks/market_data.py:30-100` — refactor `_refresh_ticker_async` into two functions:

```python
async def _refresh_ticker_fast(ticker: str, spy_closes: pd.Series | None = None) -> dict:
    """Fast path: prices + signals + QuantStats only. Used by intraday refresh."""
    async with async_session_factory() as db:
        await fetch_prices_delta(ticker, db)
        full_df = await load_prices_df(ticker, db)
        if full_df.empty:
            return {"ticker": ticker, "status": "no_data"}
        signal_result = compute_signals(ticker, full_df)
        if spy_closes is not None and not spy_closes.empty:
            # QuantStats inline (it's fast — already computed in memory)
            ...
        await store_signal_snapshot(signal_result, db)
        await mark_stage_updated(ticker, "signals", db)  # from Spec A
        await db.commit()
    return {"ticker": ticker, "status": "ok"}


async def _refresh_ticker_slow(ticker: str) -> dict:
    """Slow path: yfinance info refresh + dividends sync. Used nightly."""
    async with async_session_factory() as db:
        # ... existing yfinance info + dividends logic from current _refresh_ticker_async
        ...
    return {"ticker": ticker, "status": "ok"}
```

- `backend/tasks/market_data.py:_nightly_price_refresh_async` — internal parallelization:

```python
async def _nightly_price_refresh_async() -> dict:
    # ... existing setup (gap detection, SPY refresh, run tracking)
    tickers = await _get_all_referenced_tickers()
    spy_closes = await _load_spy_closes()
    run_id = await _runner.start_run("price_refresh", "scheduled", len(tickers))

    # Parallelize via asyncio.gather with semaphore to bound DB connections.
    # The Postgres pool is configured as pool_size=5, max_overflow=10 (effective
    # 15 connections peak — NOT 20). Semaphore(5) = pool_size leaves all
    # overflow connections free for other tasks running alongside the nightly
    # refresh and avoids SQLAlchemy `QueuePool timeout` under contention.
    sem = asyncio.Semaphore(5)
    async def _bounded(ticker):
        async with sem:
            try:
                result = await _refresh_ticker_fast(ticker, spy_closes=spy_closes)
                if result["status"] == "ok":
                    await _runner.record_ticker_success(run_id, ticker)
                else:
                    await _runner.record_ticker_failure(run_id, ticker, result["status"])
            except Exception:
                await _runner.record_ticker_failure(run_id, ticker, "refresh failed")
                logger.exception("Failed to refresh %s", ticker)

    await asyncio.gather(*[_bounded(t) for t in tickers])

    status = await _runner.complete_run(run_id)
    await _runner.update_watermark("price_refresh", datetime.now(timezone.utc).date())
    return {"status": status, "run_id": str(run_id), "tickers_total": len(tickers)}
```

- `backend/tasks/market_data.py:nightly_pipeline_chain_task` — Phase 1.5 calls `_refresh_ticker_slow_all` (new helper) for the slow path, which runs sequentially since it's only nightly:

```python
# Phase 1: fast path (already populated by intraday or runs explicitly here)
results["price_refresh"] = nightly_price_refresh_task()
# Phase 1.5: slow path — yfinance info + dividends (nightly only)
results["slow_path"] = await _refresh_all_slow_async()
```

- New helper `_refresh_all_slow_async`:
```python
async def _refresh_all_slow_async() -> dict:
    tickers = await _get_all_referenced_tickers()
    succeeded = 0
    for ticker in tickers:
        try:
            await _refresh_ticker_slow(ticker)
            succeeded += 1
        except Exception:
            logger.exception("slow path failed for %s", ticker)
    return {"status": "ok", "tickers": len(tickers), "succeeded": succeeded}
```

**Concurrency choice:** `asyncio.Semaphore(5)` chosen because:
- Each call needs 1 DB connection from `async_session_factory()`.
- Postgres pool is `pool_size=5, max_overflow=10` in `backend/database.py`
  — effective peak 15 connections, NOT 20. Semaphore(5) matches `pool_size`
  so we never trigger overflow during the refresh and leave all 10 overflow
  slots available for other tasks + API traffic.
- Going higher (e.g., 10) risks `QueuePool timeout` for the API layer when a
  large intraday refresh collides with user requests on the nightly box.

**Per-cycle time estimate after fix:**
- 600 tickers × ~1s (fast path: just prices + signals + store) ÷ 5 concurrency = ~120s
- Plus ~10s startup (SPY refresh, runner setup, gap detection)
- Total: ~130-140s per intraday cycle vs current ~50min — still a >20x win.

**Upstream:** None.
**Downstream:**
- Nightly chain Phase 1.5 (`_refresh_all_slow_async`) consumes additional time but only once nightly
- yfinance API call rate during nightly Phase 1.5 — apply rate limiter from Spec F3
- Postgres connection pool may need tuning if 10 concurrent doesn't leave headroom

---

## Files Created

(none — pure refactor)

## Files Modified

| File | What changes |
|---|---|
| `backend/tasks/forecasting.py` | E1: cap to 100, add `priority` param to `retrain_single_ticker_task`; E2: remove biweekly self-filter |
| `backend/services/pipelines.py` | E1: pass `priority=True` from `ingest_ticker` |
| `backend/tasks/market_data.py` | E3: split fast/slow paths, parallelize intraday refresh, add Phase 1.5 to nightly chain |
| `backend/tasks/__init__.py` | E2: rename biweekly entry to weekly |

---

## API Contract Changes

**None.** Pure backend refactor. No HTTP API changes, no schema changes.

## Frontend Impact

**None.** Pure backend refactor.

---

## Test Impact

### Existing test files affected

Grep evidence:

- `tests/unit/tasks/test_celery_tasks.py` — covers `refresh_ticker_task`, `nightly_price_refresh_task`, `model_retrain_all_task`. **Will need updates** because the underlying functions are split.
- `tests/unit/services/test_pipelines.py` — covers `ingest_ticker`. **Add test** for `retrain_single_ticker_task.delay(ticker, priority=True)` dispatch.
- `tests/unit/tasks/test_seed_tasks.py` — references task registration. Verify rename of beat entry doesn't break.
- `tests/unit/portfolio/test_portfolio_forecast.py` — covers forecast pipeline. Verify Prophet retrain interactions still work.

### New test files

- `tests/unit/tasks/test_market_data_fast_slow_split.py`
  - test_refresh_ticker_fast_no_yfinance_call (verify slow ops not invoked)
  - test_refresh_ticker_slow_no_signal_compute (verify fast ops not invoked)
  - test_nightly_price_refresh_uses_concurrent_gather
  - test_intraday_refresh_completes_under_2min (timed test)
  - test_phase_1_5_slow_path_called_only_in_nightly_chain
- `tests/unit/tasks/test_forecasting_priority_bypass.py`
  - test_retrain_single_ticker_task_priority_arg
  - test_user_initiated_ingest_passes_priority_true
  - test_nightly_sweep_respects_max_new_models_cap

### Specific test cases enumerated

1. `test_refresh_ticker_fast_only_writes_signals` — assert `compute_quantstats_stock` not called, assert no yfinance.Ticker.info call
2. `test_refresh_ticker_slow_only_does_yfinance_info` — assert `store_signal_snapshot` not called
3. `test_nightly_price_refresh_concurrent_semaphore` — patch `Semaphore` and assert it's used with limit 5
4. `test_nightly_price_refresh_records_per_ticker_success` — verify PipelineRunner integration unchanged
5. `test_phase_1_5_slow_path_runs_in_nightly_chain` — assert `_refresh_all_slow_async` is called from `nightly_pipeline_chain_task`
6. `test_phase_1_5_slow_path_failure_logged` — sequential failures don't crash the chain
7. `test_max_new_models_per_night_is_100` — constant value
8. `test_retrain_single_ticker_task_priority_default_false` — backward-compat
9. `test_retrain_single_ticker_task_priority_true_bypasses_cap` — when forecast_refresh sweep would hit the cap, priority=True still gets dispatched
10. `test_ingest_ticker_passes_priority_true` — verify `services/pipelines.py:127` change
11. `test_weekly_retrain_beat_schedule_present` — assert `crontab(hour=2, minute=0, day_of_week=0)` for `model_retrain_all_task`
12. `test_biweekly_self_filter_removed` — assert `_model_retrain_all_async` no longer skips alternate weeks
13. `test_intraday_refresh_completes_with_100_tickers_under_2min` — performance regression guard, marked `@pytest.mark.slow`
14. `test_intraday_refresh_marks_signals_stage_updated` — verify Spec A integration: `mark_stage_updated(ticker, "signals")` called
15. `test_db_connection_pool_not_exhausted_during_intraday` — integration test with 30 simulated tickers, assert no connection pool errors

---

## Migration Strategy

- Pure code change, no migrations
- Feature flag: `INTRADAY_REFRESH_CONCURRENCY` env var (default 10) for emergency tuning
- Rollback: revert PR; sequential loop is preserved in git history

## Risk + Rollback

| Risk | Mitigation | Rollback |
|---|---|---|
| Concurrency exhausts DB connection pool | Semaphore=5 (= pool_size); monitor pool stats | Reduce semaphore to 3; revert PR |
| 100-ticker forecast retrain dominates Sunday | Already weekly, off-hours | Cap back to 50 |
| Drift detection misses pattern between weekly retrains | Drift task already runs nightly via Spec B2 calibrated | Increase retrain cadence |
| yfinance rate limit during Phase 1.5 slow path | Apply Spec F3 rate limiter | Sequentialize Phase 1.5 |

## Open Questions

1. **Concurrency value:** semaphore=10 vs 20? Recommendation: 10 for safety. Can tune via env var.
2. **Phase 1.5 placement:** Should slow path run **before** Phase 2 (so Phase 2 has fresh dividend data) or **after** Phase 4 (so Phase 2 isn't blocked)? Recommendation: **before Phase 2** so QuantStats / fundamentals downstream see fresh data.
3. **Cap value:** 100 vs 200? Recommendation: 100. Can be revisited if portfolio uploads exceed it consistently.

---

## Dependencies

- **Blocks:** None — purely a refactor for scale
- **Depends on:** Spec A (`mark_stage_updated` in fast path), Spec F3 (yfinance rate limiter for slow path)
- **Supersedes JIRA:** None directly. Indirectly improves outcomes for KAN-405 (sentiment scoring is a different bottleneck) and KAN-406 (SPY 2y data — same task touches SPY).

---

## Doc Delta

To be added at phase closeout:
- `docs/TDD.md`: update intraday refresh section to reflect fast/slow split + concurrency
- `docs/PRD.md`: no change
- `docs/FSD.md`: no change
- README: no change
- ADR: optional ADR-012 "Intraday refresh concurrency model"
