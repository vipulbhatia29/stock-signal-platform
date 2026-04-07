# Spec B: Pipeline Completeness

## Status, Date, Authors

- **Status:** Draft — for review
- **Date:** 2026-04-06
- **Authors:** Platform team (Claude + PM)
- **Supersedes:** KAN-395 (convergence stub), KAN-405 (sentiment concurrent batch)
- **Depends on:** Spec A (`tracked_task`, `mark_stage_updated`, `task_tracer`)
- **Blocks:** Spec C (entry-point unification), Spec D (admin observability)

---

## Problem Statement

Three core pipeline tasks were merged as **stubs** during Sprint 4 rush and never implemented. A fourth task (Prophet sentiment regressor) ships with a self-admitted **KNOWN LIMITATION** that silently corrupts forecast accuracy. A fifth (news scoring) runs sequentially when it should gather. As a result, multiple production dashboards render empty and forecasts are biased.

### B1. Convergence snapshot task is a stub (KAN-395)

`backend/tasks/convergence.py:143-153`:

```python
async def _compute_convergence_snapshot_async() -> dict:
    """Compute and store daily convergence snapshot.

    Returns:
        Status dict with count of computed snapshots.
    """
    # Implementation: query latest signals, classify directions,
    # compute labels, store rows, backfill actual returns.
    # Full DB wiring deferred to Sprint 4 integration.
    logger.info("Convergence snapshot task — implementation pending full wiring")
    return {"status": "ok", "computed": 0}
```

Consequences:
- `signal_convergence_daily` table has **zero rows** in production.
- `SignalConvergenceService.get_convergence_history` (`backend/services/signal_convergence.py:210-249`) — returns empty list.
- `SignalConvergenceService.compute_divergence_hit_rate` (`signal_convergence.py:251-301`) — always returns `(None, 0)` because no historical rows exist.
- Frontend convergence history chart, divergence hit-rate panel, and sector convergence panels all render placeholders.
- Classification helpers `_classify_rsi` / `_classify_macd` / `_classify_sma` / `_classify_piotroski` / `_classify_forecast` / `_compute_convergence_label` (`backend/tasks/convergence.py:11-131`) and `classify_news_sentiment` (`backend/services/signal_convergence.py:34-49`) **already exist and are correct** — only the orchestration wrapper is missing.

### B2. Backtest task is a stub

`backend/tasks/forecasting.py:225-238`:

```python
@celery_app.task(name="backend.tasks.forecasting.run_backtest_task")
def run_backtest_task(ticker: str | None = None, horizon_days: int = 90) -> dict:
    """Run walk-forward backtest for a ticker or all active tickers.
    ...
    """
    logger.info("Backtest task started: ticker=%s, horizon=%d", ticker or "all", horizon_days)
    # Full implementation wired in Sprint 4 integration
    return {"status": "ok", "ticker": ticker, "horizon_days": horizon_days}
```

`backend/services/backtesting.py` has `BacktestEngine` (172 lines total) with private helpers — `_generate_expanding_windows`, `_compute_mape`, `_compute_mae`, `_compute_rmse`, `_compute_direction_accuracy`, `_compute_ci_containment`, `_compute_ci_bias` — but **no public `run` method**. The engine is half-built.

`backend/tasks/evaluation.py:241-256` batches backtest MAPEs for drift detection:

```python
bt_result = await db.execute(
    select(
        BacktestRun.ticker,
        func.min(BacktestRun.mape).label("best_mape"),
    )
    .where(BacktestRun.ticker.in_(tickers))
    .group_by(BacktestRun.ticker)
)
backtest_mapes: dict[str, float] = {
    row.ticker: float(row.best_mape) for row in bt_result.all()
}
```

`backtest_runs` table is always empty → `backtest_mapes = {}` → every ticker falls back to the default drift threshold. Per-ticker calibration is effectively disabled.

### B3. Prophet sentiment regressor wrong at predict time (HIGH severity bug)

Training side is correct — `backend/tools/forecasting.py:78-91`:

```python
# ── Sentiment regressors (feature-flagged: only if data exists) ──
sentiment_df = await _fetch_sentiment_regressors(ticker, df["ds"].min(), df["ds"].max(), db)
if sentiment_df is not None and not sentiment_df.empty:
    df = df.merge(sentiment_df, on="ds", how="left").fillna(0.0)
    model.add_regressor("stock_sentiment")
    model.add_regressor("sector_sentiment")
    model.add_regressor("macro_sentiment")
```

Prediction side is broken — `backend/tools/forecasting.py:201-211`:

```python
# Add sentiment regressor columns to future DataFrame if model uses them.
# KNOWN LIMITATION: Historical dates also get 0.0 instead of the actual
# sentiment used during training. This underestimates the regressor effect
# in Prophet's predictions. Future work: fetch historical sentiment from DB
# (requires making predict_forecast async) or cache in model artifact.
if has_sentiment_regressors:
    future["stock_sentiment"] = 0.0
    future["sector_sentiment"] = 0.0
    future["macro_sentiment"] = 0.0
```

Prophet learns coefficients (β) for three regressors, then at prediction time multiplies them by `0.0` for every row in `future` (both historical and forecast dates). The regressor contribution is erased. Worse: Prophet's `predict()` on historical dates is used to produce model residuals and CI width calibration, so **every ForecastResult is biased**, not just the forward-looking rows.

Files with the buggy callers of `predict_forecast`:
- `backend/tasks/forecasting.py:71` (`_model_retrain_all_async`)
- `backend/tasks/forecasting.py:116` (`_forecast_refresh_async`)
- `backend/tasks/forecasting.py:211` (`retrain_single_ticker_task._retrain`)

### B4. News scoring is sequential (KAN-405)

`backend/services/news/sentiment_scorer.py:115-121`:

```python
all_scores: list[ArticleScore] = []
for i in range(0, len(articles), BATCH_SIZE):
    batch = articles[i : i + BATCH_SIZE]
    scores = await self._score_single_batch(batch)
    all_scores.extend(scores)
```

`BATCH_SIZE = 15`. At 394 unscored articles/day that's ~27 sequential calls × ~2 s each = **~54 s wall-clock per run × 4 runs/day = ~216 s/day** on OpenAI. With `asyncio.gather` and a `Semaphore(5)` it becomes ~11 s/day.

### B5. `ingest_ticker` covers 7 steps, misses news + convergence

`backend/services/pipelines.py:40-152` — `ingest_ticker` runs Steps 1–7: ensure stock, fetch prices, load history, fundamentals/earnings, compute signals, persist snapshot, update `last_fetched_at`, dispatch forecast for new tickers, and generate a portfolio-aware rec. It does **not** trigger:
- News backfill for new tickers (they start with zero articles → zero sentiment).
- Convergence seed (new ticker has no `signal_convergence_daily` row until nightly).
- Any `mark_stage_updated(...)` calls (Spec A requires these for ingestion state tracking).

### Cross-cutting effect

B1 + B2 + B3 together mean: convergence UX is dead, drift calibration is disabled, forecasts are biased. B4 is a pure ops/cost win. B5 means new tickers silently start with broken downstream.

---

## Goals

1. **G1** — `signal_convergence_daily` gets one row per universe ticker per nightly run. Convergence history, divergence hit-rate, and sector convergence queries return non-empty data within 24h of deploy.
2. **G2** — `backtest_runs` gets backfilled walk-forward rows. Drift detection (`check_drift_task`) uses per-ticker calibrated thresholds instead of the default.
3. **G3** — `predict_forecast` feeds the actual per-day historical sentiment into Prophet's future DataFrame and uses a forward projection for dates beyond training. Integration test proves the regressor effect flows through to the output.
4. **G4** — `score_batch` dispatches all OpenAI calls concurrently under a bounded semaphore. Wall-clock drops ≥5×.
5. **G5** — `ingest_ticker` triggers news, convergence, and observability state updates for newly ingested tickers.
6. **G6** — Every new/touched task gets wrapped with Spec A's `@tracked_task` decorator and calls `mark_stage_updated` on success.

## Non-Goals

- **Not** building a news sentiment backfill job separate from the existing `news_ingest_task` — we extend it with a `tickers` param.
- **Not** reworking the Prophet regressor set (no new exogenous variables).
- **Not** touching convergence UI layout (Spec G).
- **Not** adding seasonality calibration (`calibrate_seasonality_task` stays stubbed; out of scope).
- **Not** addressing the `BacktestEngine` private-helper test coverage gap beyond what B2 needs.
- **Not** upgrading news schedule cadence.

---

## Design

### B1. Convergence task real implementation

**Current stub** (see Problem Statement). Strategy: leverage existing helpers, push all DB work into a single async function with bulk queries, upsert via `pg_insert(...).on_conflict_do_update(...)`, and loop actual-return backfills.

**New function signature:**

```python
# backend/tasks/convergence.py

from backend.services.observability.task_tracer import tracked_task  # Spec A
from backend.services.ticker_state import mark_stage_updated  # Spec A

@celery_app.task(name="backend.tasks.convergence.compute_convergence_snapshot_task")
@tracked_task("convergence_snapshot")
def compute_convergence_snapshot_task(ticker: str | None = None) -> dict:
    """Compute convergence state for one ticker or the full universe.

    Args:
        ticker: If provided, computes convergence for that single ticker
            (used by ingest_ticker fire-and-forget). If None, runs over the
            full canonical universe (nightly Phase 3).

    Returns:
        Dict {status, computed, backfilled, ticker}.
    """
    return asyncio.run(_compute_convergence_snapshot_async(ticker=ticker))


async def _compute_convergence_snapshot_async(ticker: str | None = None) -> dict:
    from datetime import date, timedelta
    from sqlalchemy import select
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from backend.database import async_session_factory
    from backend.models.convergence import SignalConvergenceDaily
    from backend.models.price import StockPrice
    from backend.services.signal_convergence import SignalConvergenceService
    from backend.services.ticker_universe import get_all_referenced_tickers

    today = date.today()
    svc = SignalConvergenceService()
    computed = 0
    backfilled = 0

    async with async_session_factory() as db:
        tickers = [ticker] if ticker else await get_all_referenced_tickers(db)
        if not tickers:
            return {"status": "no_tickers", "computed": 0, "backfilled": 0}

        # Step 1: Reuse service's bulk convergence (already does DISTINCT ON queries)
        convergences = await svc.get_bulk_convergence(tickers, db)

        # Step 2: Upsert rows
        for tkr, conv in convergences.items():
            directions = {d.signal: d.direction for d in conv.signals}
            stmt = (
                pg_insert(SignalConvergenceDaily)
                .values(
                    ticker=tkr,
                    date=today,
                    convergence_label=conv.convergence_label,
                    signals_aligned=conv.signals_aligned,
                    composite_score=conv.composite_score,
                    rsi_direction=directions.get("rsi"),
                    macd_direction=directions.get("macd"),
                    sma_direction=directions.get("sma"),
                    piotroski_direction=directions.get("piotroski"),
                    forecast_direction=directions.get("forecast"),
                    news_direction=directions.get("news"),
                    is_divergent=conv.divergence.is_divergent,
                )
                .on_conflict_do_update(
                    index_elements=["ticker", "date"],
                    set_={
                        "convergence_label": conv.convergence_label,
                        "signals_aligned": conv.signals_aligned,
                        "composite_score": conv.composite_score,
                        "rsi_direction": directions.get("rsi"),
                        "macd_direction": directions.get("macd"),
                        "sma_direction": directions.get("sma"),
                        "piotroski_direction": directions.get("piotroski"),
                        "forecast_direction": directions.get("forecast"),
                        "news_direction": directions.get("news"),
                        "is_divergent": conv.divergence.is_divergent,
                    },
                )
            )
            await db.execute(stmt)
            computed += 1

        # Step 3: Backfill actual_return_90d / actual_return_180d for matured rows
        backfilled += await _backfill_actual_returns(db, tickers, today, days=90)
        backfilled += await _backfill_actual_returns(db, tickers, today, days=180)

        await db.commit()

        # Step 4: Mark ingestion stage (Spec A)
        for tkr in convergences:
            await mark_stage_updated(tkr, "convergence")
        await db.commit()

    return {
        "status": "ok",
        "computed": computed,
        "backfilled": backfilled,
        "ticker": ticker,
    }


async def _backfill_actual_returns(
    db: AsyncSession,
    tickers: list[str],
    today: date,
    days: int,
) -> int:
    """Backfill actual_return_{days}d for convergence rows from exactly {days} ago.

    For each row where date == today - days and actual_return_Nd is NULL,
    compute (price_today / price_at_date) - 1.

    Returns number of rows updated.
    """
    target_date = today - timedelta(days=days)
    col = SignalConvergenceDaily.actual_return_90d if days == 90 else SignalConvergenceDaily.actual_return_180d

    # Fetch matured rows needing backfill
    stmt = select(SignalConvergenceDaily).where(
        SignalConvergenceDaily.date == target_date,
        SignalConvergenceDaily.ticker.in_(tickers),
        col.is_(None),
    )
    rows = (await db.execute(stmt)).scalars().all()
    if not rows:
        return 0

    # Bulk-fetch prices at both dates
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

Helpers `_bulk_latest_price` and `_bulk_price_on_date` do `DISTINCT ON (ticker) ORDER BY time DESC` queries against `StockPrice` filtered to the requested date range. Returns `dict[ticker, float]`.

**Wire into nightly chain** — `backend/tasks/market_data.py:336` (Phase 3, after drift detection moves to Phase 4):

Current:
```
Phase 3: Drift detection
Phase 4: Alerts + health + rebalancing
```

New:
```
Phase 3: Convergence snapshot (needs fresh signals + forecasts from phase 2)
Phase 4: Drift detection
Phase 5: Alerts + health + rebalancing
```

Rename `phase4_tasks` → `phase5_tasks` and add:

```python
# Phase 3: Convergence (depends on signals + forecasts both updated in phase 2)
from backend.tasks.convergence import compute_convergence_snapshot_task
logger.info("Nightly chain phase 3: convergence snapshot")
results["convergence"] = compute_convergence_snapshot_task()
```

### B2. Backtest task real implementation

**Step 1: Give `BacktestEngine` a public API.** Extend `backend/services/backtesting.py` with:

```python
async def run_walk_forward(
    self,
    ticker: str,
    db: AsyncSession,
    horizon_days: int = 90,
    min_train_days: int = 365,
    step_days: int = 30,
) -> BacktestMetrics:
    """Run expanding-window walk-forward backtest for one ticker.

    For each window:
      1. Load prices[train_start : train_end] from DB
      2. Train a temporary Prophet model (no persistence, no ModelVersion row)
      3. Predict at test_date
      4. Compare against actual price at test_date
    Aggregate to BacktestMetrics and return. Caller persists to backtest_runs.
    """
```

Implementation loads prices once (single query: `StockPrice WHERE ticker == ? AND time >= data_start`), splits in-memory by `train_end`/`test_date`, calls a lightweight training helper that shares config with `train_prophet_model` but does **not** touch `ModelVersion`, `artifact_path`, or the DB beyond the initial load. Each window's Prophet fit runs inside `asyncio.to_thread` (Prophet is CPU-bound, sync). Sentiment regressors follow the same real-historical pattern from B3.

**Step 2: Real task implementation** — `backend/tasks/forecasting.py:225`:

```python
@celery_app.task(name="backend.tasks.forecasting.run_backtest_task")
@tracked_task("backtest")
def run_backtest_task(ticker: str | None = None, horizon_days: int = 90) -> dict:
    return asyncio.run(_run_backtest_async(ticker, horizon_days))


async def _run_backtest_async(ticker: str | None, horizon_days: int) -> dict:
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
                db.add(
                    BacktestRun(
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
                    )
                )
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

**Step 3: Weekly schedule** — `backend/tasks/__init__.py`:

```python
"weekly-backtest": {
    "task": "backend.tasks.forecasting.run_backtest_task",
    "schedule": crontab(hour=3, minute=0, day_of_week=6),  # Saturday 3 AM ET
},
```

Kwargs default to `ticker=None, horizon_days=90` (universe-wide, 90-day horizon).

### B3. Prophet sentiment fix at predict time

**Refactor `predict_forecast` to async** — `backend/tools/forecasting.py:149`:

```python
async def predict_forecast(
    model_version: ModelVersion,
    db: AsyncSession,
    horizons: list[int] | None = None,
) -> list[ForecastResult]:
    """Generate forecasts from a trained Prophet model.

    When the model has sentiment regressors, the future DataFrame is
    populated with real historical sentiment up to the training cutoff
    and a 7-day trailing mean projection beyond it.
    """
    ...
```

**Algorithm for populating sentiment columns on `future`:**

```python
if has_sentiment_regressors:
    training_end = model.history["ds"].max().date()
    target_date = today + timedelta(days=horizon)

    # 1. Fetch real historical sentiment for the training period
    hist_df = await _fetch_sentiment_regressors(
        model_version.ticker,
        model.history["ds"].min(),
        pd.Timestamp(target_date),
        db,
    )
    if hist_df is None:
        hist_df = pd.DataFrame(columns=["ds", "stock_sentiment", "sector_sentiment", "macro_sentiment"])

    # 2. Compute 7-day trailing mean from the most recent historical days
    hist_recent = hist_df[hist_df["ds"] >= pd.Timestamp(training_end) - pd.Timedelta(days=7)]
    projection = {
        col: float(hist_recent[col].mean()) if not hist_recent.empty else 0.0
        for col in ("stock_sentiment", "sector_sentiment", "macro_sentiment")
    }

    # 3. Merge historical values into future; fill forecast-period rows with projection
    future = future.merge(hist_df, on="ds", how="left")
    for col, fill in projection.items():
        mask = future["ds"].dt.date > training_end
        future.loc[mask, col] = fill
        future[col] = future[col].fillna(0.0)  # any historical gaps
```

**Caller updates** (all three need `await` and to pass `db`):

| File:line | Change |
|---|---|
| `backend/tasks/forecasting.py:71` (`_model_retrain_all_async`) | `forecasts = await predict_forecast(model_version, db)` |
| `backend/tasks/forecasting.py:116` (`_forecast_refresh_async`) | `forecasts = await predict_forecast(model_version, db)` |
| `backend/tasks/forecasting.py:211` (`retrain_single_ticker_task._retrain`) | `forecasts = await predict_forecast(model_version, db)` |

**Remove** the "KNOWN LIMITATION" comment block at `backend/tools/forecasting.py:201-206`.

**Delete** the `future["stock_sentiment"] = 0.0` three-line hardcode at `backend/tools/forecasting.py:207-210`.

### B4. News scoring concurrent dispatch (KAN-405)

**Current sequential loop** — `backend/services/news/sentiment_scorer.py:115-121` (see Problem Statement).

**New concurrent implementation:**

```python
# backend/config.py — new setting
NEWS_SCORING_MAX_CONCURRENCY: int = 5

# backend/services/news/sentiment_scorer.py:99
async def score_batch(self, articles: list[RawArticle]) -> list[ArticleScore]:
    if not self._api_key:
        logger.warning("OPENAI_API_KEY not set — skipping sentiment scoring")
        return []
    if not articles:
        return []

    sem = asyncio.Semaphore(settings.NEWS_SCORING_MAX_CONCURRENCY)

    async def _bounded(batch: list[RawArticle]) -> list[ArticleScore]:
        async with sem:
            with trace_task("news_sentiment_batch", metadata={"batch_size": len(batch)}):
                return await self._score_single_batch(batch)

    batches = [
        articles[i : i + BATCH_SIZE]
        for i in range(0, len(articles), BATCH_SIZE)
    ]
    results = await asyncio.gather(*(_bounded(b) for b in batches), return_exceptions=True)

    all_scores: list[ArticleScore] = []
    for idx, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error("Batch %d failed during concurrent scoring", idx, exc_info=result)
            continue
        all_scores.extend(result)
    return all_scores
```

Semaphore(5) respects OpenAI tier-1 500 RPM with a wide margin (5 concurrent × 30 req/min per slot = 150 RPM peak). `return_exceptions=True` means one failed batch does not poison others. Each batch gets its own Langfuse trace span via `trace_task` (Spec A).

### B5. `ingest_ticker` extension

**Step 8/9/10 additions** — `backend/services/pipelines.py:122+`:

```python
# ── Step 6 (existing): Update last_fetched_at ──
await update_last_fetched_at(ticker, db)

# ── Step 6b (new): Mark signals + price stages (Spec A) ──
await mark_stage_updated(ticker, "prices")
if composite_score is not None:
    await mark_stage_updated(ticker, "signals")

# ── Step 7b (existing): Dispatch forecast training for new tickers ──
if is_new:
    try:
        from backend.tasks.forecasting import retrain_single_ticker_task
        retrain_single_ticker_task.delay(ticker)
    except Exception:
        logger.warning("Failed to dispatch forecast for %s", ticker, exc_info=True)

# ── Step 8 (new): News backfill for new tickers ──
if is_new:
    try:
        from backend.tasks.news_sentiment import news_ingest_task
        news_ingest_task.delay(lookback_days=90, tickers=[ticker])
    except Exception:
        logger.warning("Failed to dispatch news backfill for %s", ticker, exc_info=True)

# ── Step 9 (new): Convergence seed for new tickers ──
if is_new:
    try:
        from backend.tasks.convergence import compute_convergence_snapshot_task
        compute_convergence_snapshot_task.delay(ticker=ticker)
    except Exception:
        logger.warning("Failed to dispatch convergence seed for %s", ticker, exc_info=True)

# ── Step 10 (new): Mark recommendation stage if generated ──
# (runs after _generate_recommendation_with_context in Step 7)
```

And place `await mark_stage_updated(ticker, "recommendation")` inside `_generate_recommendation_with_context` right after `store_recommendation(rec, user_id, db)`. (`"recommendation"` is a valid `Stage` Literal per Spec A.)

**`news_ingest_task` signature change** — `backend/tasks/news_sentiment.py:21`:

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

This is a minimal, backward-compatible override — existing callers (nightly) pass nothing and keep current behavior.

---

## Files Created

- `tests/unit/tasks/test_convergence_snapshot.py`
- `tests/api/test_convergence_integration.py` (overlaps with KAN-397)
- `tests/unit/tasks/test_backtest_task.py`
- `tests/unit/services/test_backtest_engine_walk_forward.py`
- `tests/unit/services/test_prophet_sentiment_predict.py`
- `tests/unit/services/test_sentiment_concurrent_batch.py`
- `tests/unit/services/test_ingest_ticker_extended.py`

(No new source files. All implementation lands in existing modules.)

## Files Modified

- `backend/tasks/convergence.py` — real async implementation + helpers, decorator.
- `backend/tasks/forecasting.py` — real `run_backtest_task`, await callers of `predict_forecast`, decorators.
- `backend/tools/forecasting.py` — async `predict_forecast`, sentiment merge logic.
- `backend/services/backtesting.py` — public `run_walk_forward` on `BacktestEngine`.
- `backend/services/news/sentiment_scorer.py` — `asyncio.gather` + semaphore.
- `backend/services/pipelines.py` — Steps 6b/8/9/10.
- `backend/tasks/news_sentiment.py` — `tickers` parameter.
- `backend/tasks/market_data.py` — insert convergence into nightly chain.
- `backend/tasks/__init__.py` — add weekly backtest beat schedule.
- `backend/config.py` — `NEWS_SCORING_MAX_CONCURRENCY`, `CONVERGENCE_SNAPSHOT_ENABLED`, `BACKTEST_ENABLED`, `PROPHET_REAL_SENTIMENT_ENABLED` feature flags.

---

## Upstream / Downstream Impact

### B1. Convergence
- **Reads:** `signal_snapshots`, `news_sentiment_daily`, `forecast_results`, `stock_prices`, `stocks` (via `get_all_referenced_tickers`).
- **Writes:** `signal_convergence_daily` (new rows + updates to `actual_return_{90,180}d`), `ticker_ingestion_state.convergence_updated_at`.
- **Consumers:** `SignalConvergenceService.get_convergence_history`, `compute_divergence_hit_rate`, `get_sector_convergence`, frontend convergence history chart, divergence hit-rate panel, sector convergence panel, portfolio convergence view. All currently return empty; after deploy they return data.
- **Behavior change:** the first nightly run writes 1 row/ticker, then each subsequent night overwrites today's row and backfills actual returns 90/180 days back. Historical depth builds over 6 months.

### B2. Backtest
- **Reads:** `stock_prices` (bulk load per ticker for walk-forward windows).
- **Writes:** `backtest_runs`, `ticker_ingestion_state.backtest_updated_at`.
- **Consumers:** `backend/tasks/evaluation.py:241-256` — `backtest_mapes` dict gets populated; `compute_calibrated_threshold` now uses real per-ticker MAPE baseline × 1.5 instead of the default. Drift detection becomes meaningful.
- **Load:** weekly Saturday 03:00 ET. Prophet training is CPU-bound ~5–15 s per ticker × 20 windows × ~100 tickers ≈ 3 hours max. Runs on the default worker pool off-peak.

### B3. Prophet sentiment
- **Reads:** `news_sentiment_daily` (new read inside `predict_forecast`).
- **Writes:** `forecast_results` (values change).
- **Consumers:** every `ForecastResult` consumer — frontend forecast cards, `SignalConvergenceService._fetch_latest_forecasts`, drift detection (`rolling_mape` will shift), convergence forecast classification.
- **Behavior change:** forecasts become more responsive to recent sentiment. Expected MAPE improvement modest (+1–3 pp direction accuracy per internal estimate) but the critical win is eliminating systemic bias — the model no longer claims sentiment matters then zeros it out.
- **Migration risk:** existing forecasts in `forecast_results` become stale next nightly run. No data loss; just recomputation.

### B4. News scoring
- No new reads/writes. Execution-model change only.
- **Consumers:** `news_sentiment_scoring_task` wall-clock drops from ~54 s to ~11 s per run. 4× daily × 43 s saved = ~172 s/day less Celery worker time.
- OpenAI RPM: peak 5 concurrent × ~30 RPM per slot = 150 RPM, well under tier-1 500 RPM.

### B5. `ingest_ticker` extension
- Calls `news_ingest_task`, `compute_convergence_snapshot_task` as fire-and-forget `.delay(...)`.
- **Consumers:** every entry point that calls `ingest_ticker` (router, tools, admin — enumerated in Spec C). All automatically inherit news + convergence seeding for new tickers.
- `mark_stage_updated` calls add ~4 small UPDATEs per ingest — negligible.

---

## API Contract Changes

- `backend.tasks.convergence.compute_convergence_snapshot_task` — add optional `ticker: str | None = None` parameter. Backward compatible (default is nightly universe-wide).
- `backend.tasks.news_sentiment.news_ingest_task` — add optional `tickers: list[str] | None = None` parameter.
- `backend.tools.forecasting.predict_forecast` — becomes `async`, adds `db: AsyncSession` parameter. **Breaking** to in-tree callers; three caller sites are updated in the same patch.
- No HTTP API endpoint changes.
- No frontend contract changes.

## Frontend Impact

- No direct frontend code changes in this spec (Spec G handles frontend polish).
- **Indirect:** convergence history chart, divergence hit-rate panel, and sector convergence panel start rendering real data after the first nightly run post-deploy. Forecast cards refresh with sentiment-aware values on the next retrain cycle.

---

## Test Impact

### Existing test files affected

| File | What needs to change |
|---|---|
| `tests/unit/tasks/test_convergence_task.py` | Replace stub-status assertion with real behavior (computed > 0). Add fixture seeding signal snapshots + news sentiment + forecasts, assert `signal_convergence_daily` row insertion. |
| `tests/unit/services/test_signal_convergence.py` | No signature change. Add tests that exercise `compute_divergence_hit_rate` against pre-seeded `SignalConvergenceDaily` rows — currently only tests empty case. |
| `tests/unit/routers/test_convergence_endpoints.py` | May need fixture that seeds a few convergence rows (currently uses mocks; check for `return_value=[]`). |
| `tests/unit/tasks/test_news_sentiment_tasks.py` | Update `news_ingest_task` signature tests — assert `tickers=[...]` routes correctly. |
| `tests/unit/services/test_sentiment_scorer.py` | Update `score_batch` tests — patch `asyncio.gather` vs sequential; assert concurrency cap respected; assert one failing batch does not drop all results. |
| `tests/unit/pipeline/test_forecasting.py` | Update `predict_forecast` calls to `await` and pass mock `db`. |
| `tests/unit/test_forecasting_floor.py` | Same — async refactor. |
| `tests/unit/test_forecast_new_ticker_training.py` | Same — async refactor. |
| `tests/unit/test_ingest_forecast_dispatch.py` | Add assertions that `news_ingest_task.delay` and `compute_convergence_snapshot_task.delay` are called when `is_new=True`. |
| `tests/unit/services/test_pipelines.py` | Assert `mark_stage_updated` is called for each stage. |
| `tests/unit/routers/test_backtest_router.py` | If router calls `run_backtest_task`, ensure new return shape is accepted. |

### New test files to create

- `tests/unit/tasks/test_convergence_snapshot.py`
- `tests/api/test_convergence_integration.py`
- `tests/unit/tasks/test_backtest_task.py`
- `tests/unit/services/test_backtest_engine_walk_forward.py`
- `tests/unit/services/test_prophet_sentiment_predict.py`
- `tests/unit/services/test_sentiment_concurrent_batch.py`
- `tests/unit/services/test_ingest_ticker_extended.py`

### Specific test cases (~30)

**B1. Convergence (`test_convergence_snapshot.py` + `test_convergence_integration.py`)**
1. Empty universe → returns `{"status": "no_tickers", "computed": 0}`.
2. Universe with 3 tickers, each with signals + sentiment + forecast → inserts 3 rows into `signal_convergence_daily`.
3. Re-running same day → `ON CONFLICT` updates existing rows, count unchanged.
4. Single-ticker mode (`ticker="AAPL"`) → computes only AAPL, leaves others untouched.
5. Backfill: seed a 90-day-old row with `actual_return_90d=NULL`, run task, assert field populated from today's price.
6. Backfill no-op: 90-day-old row already populated → `actual_return_90d` unchanged.
7. Backfill missing price-then: ticker had no price 90 days ago → row skipped, no exception.
8. `mark_stage_updated(ticker, "convergence")` called once per ticker.
9. `@tracked_task` wrapper produces a trace with name `convergence_snapshot`.

**B2. Backtest (`test_backtest_engine_walk_forward.py` + `test_backtest_task.py`)**
10. `BacktestEngine.run_walk_forward` with synthetic linear price series → MAPE ≈ 0.
11. Walk-forward with insufficient data (<365 days) → returns `BacktestMetrics` with `num_windows=0`.
12. Walk-forward respects `step_days` cadence — N windows matches expected generator output.
13. `run_backtest_task(ticker="AAPL")` inserts one `BacktestRun` row with correct `horizon_days`.
14. `run_backtest_task()` universe-wide over 3 tickers → 3 rows inserted.
15. Per-ticker failure is isolated — one ticker raising does not abort others; failed count incremented.
16. `mark_stage_updated(ticker, "backtest")` called on success only.
17. Weekly beat schedule entry present in `celery_app.conf.beat_schedule`.

**B3. Prophet sentiment (`test_prophet_sentiment_predict.py`)**
18. Model trained with sentiment on synthetic data where sentiment perfectly predicts price → prediction on historical dates matches training correlation (non-zero regressor coefficient actually affects `yhat`).
19. Model trained without sentiment → `predict_forecast` still works (no sentiment merge attempted).
20. Forecast period uses 7-day trailing mean projection when sentiment history exists.
21. Forecast period falls back to `0.0` when no historical sentiment rows in training window.
22. `predict_forecast` is `async` — callers must `await` (regression test catches sync accidental revert).
23. Integration test: train AAPL with real sentiment regressors, `predict_forecast(model, db)`, verify `yhat_90` differs from the same model with sentiment regressors patched to `0.0`.

**B4. Sentiment concurrent batch (`test_sentiment_concurrent_batch.py`)**
24. `score_batch` with 30 articles (2 batches of 15) → both dispatched concurrently (mock `_score_single_batch` with `asyncio.sleep`, assert total wall-time < 2× single-batch time).
25. `Semaphore` cap: 20 batches dispatched, only 5 concurrent at once (assert max in-flight).
26. One batch raises `httpx.HTTPError` → other batches still return scores, failed batch logged.
27. Empty articles list → returns `[]` without dispatching.
28. Configurable concurrency — setting `NEWS_SCORING_MAX_CONCURRENCY=2` caps to 2.

**B5. `ingest_ticker` extension (`test_ingest_ticker_extended.py`)**
29. `is_new=True` dispatches `news_ingest_task.delay(lookback_days=90, tickers=[ticker])` — mock `.delay` asserts call.
30. `is_new=True` dispatches `compute_convergence_snapshot_task.delay(ticker=ticker)`.
31. `is_new=False` does NOT dispatch news/convergence — existing ticker, nightly handles it.
32. `mark_stage_updated` called for `"prices"`, `"signals"`, `"recommendation"` stages in correct order.
33. News dispatch failure is swallowed — pipeline still returns success dict.

### Factory-boy / fixtures

- Reuse `SignalSnapshotFactory`, `ForecastResultFactory`, `NewsSentimentDailyFactory`, `StockPriceFactory`.
- New factory: `SignalConvergenceDailyFactory` in `tests/factories/convergence.py` (if not already present).
- Add `BacktestRunFactory` under `tests/factories/backtest.py`.

---

## Migration Strategy

- **No new tables.** Uses existing `signal_convergence_daily`, `backtest_runs`, `ticker_ingestion_state` (from Spec A).
- **Code-only rollout.** Merge PR → deploy → first nightly run populates fresh rows.
- **Feature flags** in `backend/config.py`:
  - `CONVERGENCE_SNAPSHOT_ENABLED: bool = True`
  - `BACKTEST_ENABLED: bool = True`
  - `PROPHET_REAL_SENTIMENT_ENABLED: bool = True`
  - `NEWS_SCORING_MAX_CONCURRENCY: int = 5`
- Each task checks its flag at the top and returns `{"status": "disabled"}` if off. Lets ops toggle without a redeploy.
- Backfill order:
  1. Deploy code.
  2. Nightly Phase 3 runs convergence on next tick → 24 h to first row.
  3. First Saturday runs backtest → drift calibration live within 7 days.
  4. Prophet sentiment takes effect immediately on next `forecast_refresh_task`.

## Risk + Rollback

| Sub-area | Risk | Mitigation | Rollback |
|---|---|---|---|
| B1 | Upsert race if two workers run concurrently | `ON CONFLICT` handles it idempotently | Flip flag OFF, `TRUNCATE signal_convergence_daily` (non-destructive — rebuilds next night) |
| B2 | Prophet CPU burn saturates worker | Weekly off-peak Saturday 03:00; monitor via Spec A tracer | Flip flag OFF, `TRUNCATE backtest_runs` |
| B3 | Prediction performance drops (extra DB read) | One query per `predict_forecast` call, already bulk-friendly | Flip flag OFF → reverts to 0.0 behavior |
| B4 | OpenAI 429 due to concurrency | Semaphore capped at 5; one-batch failure non-fatal | Set `NEWS_SCORING_MAX_CONCURRENCY=1` — exact sequential behavior |
| B5 | News/convergence dispatch storm on bulk ingest | Fire-and-forget; worker queue depth monitored | Revert pipelines.py additions |

No data loss in any rollback path — all data is rebuildable from source (prices, news articles).

## Open Questions

1. **B1 backfill horizon.** How far back to rebuild on first deploy? **Recommendation:** 90 days. Anything older has no forecast context (forecasts only go back ~6 months) and requires cross-joining historical forecasts that may not exist. PM approval needed.
2. **B3 forward projection.** Use 7-day trailing mean or 0.0? **Recommendation:** 7-day mean. Zero introduces the exact bias we're trying to fix. Alternative: linear decay from last-known-sentiment → 0 over 30 days.
3. **B5 backtest on ingest.** Should new-ticker ingest also dispatch backtest? **Recommendation:** No. Backtest is expensive (~15 s per ticker) and only needed for drift calibration, which new tickers don't need until they've accumulated forecast history.
4. **B1 convergence on weekends.** Skip Saturday/Sunday (markets closed)? **Recommendation:** Keep daily — makes the time series contiguous and simplifies hit-rate queries. Weekend rows will match Friday's data.
5. **B2 horizon coverage.** Backtest at 90d only or all `DEFAULT_HORIZONS=[90, 180, 270]`? **Recommendation:** 90 only for v1 (drift detection uses 90 exclusively). Expand to 180/270 in a follow-up once we have worker headroom data.

## Dependencies

- **Blocks:**
  - Spec C — entry-point unification consumes the extended `ingest_ticker` (needs Steps 8–10).
  - Spec D — admin dashboard surfaces backtest/convergence per-ticker status (needs task tracer + `mark_stage_updated` data).
- **Depends on:**
  - Spec A — `tracked_task` decorator, `task_tracer`, `mark_stage_updated`, `ticker_ingestion_state` table + stage columns.
- **Supersedes JIRA:**
  - KAN-395 — convergence snapshot stub.
  - KAN-405 — news sentiment concurrent dispatch.

---

*End of Spec B.*
