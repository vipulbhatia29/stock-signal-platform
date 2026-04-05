# Pipeline Integrity — KAN-403, KAN-404

**Date:** 2026-04-05
**Bugs:** KAN-403 (Prophet negative prices), KAN-404 (missing data for non-universe tickers)
**Scope:** Backend only — no frontend changes, no migrations
**Review:** 5-persona review completed. 2 CRITICALs + 5 HIGHs addressed in v2.

---

## Problem Statement

Two data integrity bugs surfaced during the Session 95 full reseed:

1. **KAN-403 (High):** Prophet predicts negative stock prices for 6 tickers (FISV, HUM, ELV, SMCI, IT, CSGP). Negative prices are impossible for equities and poison downstream calculations (BL views, portfolio return aggregation, forecast evaluation).

2. **KAN-404 (High):** When users add positions or watchlist entries for tickers outside the index universe (S&P 500 + NASDAQ-100 + Dow 30 + ETFs), those tickers never get price/signal/forecast data because the nightly pipeline only queries watchlist tickers — and the nightly forecast refresh only regenerates predictions for tickers with existing ModelVersions.

Root cause analysis revealed 7 gaps across entry points, nightly pipelines, and downstream consumers.

---

## Fix 1: Prophet Negative Price Floor (KAN-403)

### What

Floor `predicted_price`, `predicted_lower`, `predicted_upper` using a scale-appropriate minimum: `max(0.01, last_known_price * 0.01)` (1% of last known price). Log a warning when flooring is applied. Mark floored tickers as unreliable so they are excluded from portfolio forecast aggregation (reported in `missing_tickers`).

### Where

- **`backend/tools/forecasting.py:210-222`** — after Prophet `model.predict()`, before creating `ForecastResult` objects
- **`backend/schemas/forecasts.py:10-19`** — add `Field(gt=0)` validation on `ForecastHorizon` price fields
- **`backend/models/forecast.py`** — add `is_floored: bool = False` field to `ForecastResult` (no migration — use `server_default=false` or handle in code as attribute)

### Why scale-appropriate floor

A fixed $0.01 floor on a $500 stock creates a -99.998% return that dominates portfolio aggregation. Using 1% of last known price:
- SMCI at $800 → floor at $8.00 (still very bearish, but not portfolio-destroying)
- A $2 penny stock → floor at $0.02 (reasonable)

### Floored forecasts in portfolio aggregation

Floored forecasts are treated as "unreliable" — they appear in `missing_tickers` (Fix 6) rather than silently injecting extreme outlier returns into the weighted aggregation.

### Division by zero protection

The minimum of `0.01` in the `max()` guarantees `predicted_price > 0` for evaluation (`error_pct = abs(actual - predicted) / predicted`).

---

## Fix 2: Canonical Referenced Tickers Query (KAN-404)

### What

Create a single canonical function `get_all_referenced_tickers()` that returns a deduped union of:
- Index members (current `StockIndexMembership` where `removed_date IS NULL`)
- Watchlist tickers (all users)
- Portfolio position tickers (all users, `shares > 0`)

Place it in a shared location so both `market_data.py` and `forecasting.py` use the same source of truth.

### Where

- **`backend/services/ticker_universe.py`** (NEW) — canonical query lives here
- **`backend/tasks/market_data.py`** — replace `_get_all_watchlist_tickers()` with import from ticker_universe
- **`backend/tasks/forecasting.py`** — replace `_get_all_forecast_tickers()` with import from ticker_universe
- **`backend/tasks/market_data.py:200`** — nightly pipeline uses canonical function
- **`backend/tasks/market_data.py:409`** — Beat fan-out uses canonical function

### Design

```python
# backend/services/ticker_universe.py
async def get_all_referenced_tickers(db: AsyncSession) -> list[str]:
    """Canonical query: all tickers the system actively cares about.

    Union of index members + watchlist + portfolio positions (shares > 0).
    Deduped and sorted.
    """
    from sqlalchemy import distinct, select, union

    from backend.models.index import StockIndexMembership
    from backend.models.portfolio import Position
    from backend.models.stock import Watchlist

    stmt = union(
        select(StockIndexMembership.ticker).where(
            StockIndexMembership.removed_date.is_(None)
        ),
        select(Watchlist.ticker),
        select(Position.ticker).where(Position.shares > 0),
    )
    result = await db.execute(select(stmt.subquery().c.ticker).order_by("ticker"))
    return [row[0] for row in result.all()]
```

Callers in tasks use `async_session_factory()` to get a session. One query, one source of truth.

---

## Fix 3: Nightly Forecast — Train New Tickers (KAN-404)

### What

In the nightly forecast refresh, after refreshing existing models, find referenced tickers that have prices but no active `ModelVersion`. Dispatch `retrain_single_ticker_task.delay()` for each (capped at 20 per night to avoid timeout).

### Where

- **`backend/tasks/forecasting.py:85-126`** — `_forecast_refresh_async()`, add dispatch loop after existing model refresh

### Design

After the existing-model refresh loop:
1. Get all referenced tickers via `get_all_referenced_tickers()`
2. Subtract tickers that already have active ModelVersions
3. For each remaining ticker: check if it has ≥ `MIN_DATA_POINTS` (200) days of price data (Prophet minimum from `backend/tools/forecasting.py`)
4. Dispatch `retrain_single_ticker_task.delay(ticker)` for up to 20 new tickers (cap prevents runaway nightly duration)
5. Log: "Dispatched training for {n} new tickers: {list}"

**Why dispatch instead of inline training:** Prophet fitting takes 15-30s per ticker. Inline training of 20 tickers would add 5-10 minutes to the nightly forecast refresh task. Dispatching as individual Celery tasks lets them run in parallel on available workers without blocking the nightly chain.

**Why 200 not 60:** `train_prophet_model()` enforces `MIN_DATA_POINTS = 200`. Using a lower threshold in the pre-check would cause `ValueError` at training time.

---

## Fix 4: Chat Auto-Ingest (KAN-404)

### What

When `analyze_stock` tool encounters a ticker with no price data, auto-ingest it using `ensure_stock_exists` + `fetch_prices_delta` (lightweight) instead of returning an error. Validate ticker format first. Respect per-user rate limits.

### Where

- **`backend/tools/analyze_stock.py:50-56`** — replace the error return with lightweight ingest

### Design

```python
if df.empty:
    # Validate ticker format (1-5 uppercase letters)
    import re
    if not re.match(r"^[A-Z]{1,5}$", ticker):
        return ToolResult(status="error", error="Invalid ticker format.")

    # Lightweight ingest: create stock record + fetch prices
    from backend.services.stock_data import ensure_stock_exists, fetch_prices_delta
    try:
        await ensure_stock_exists(ticker, session)
        await fetch_prices_delta(ticker, session)
        await session.commit()
    except (ValueError, Exception):
        return ToolResult(status="error", error=f"Could not fetch data for {ticker}.")

    # Re-load prices after ingest
    df = await load_prices_df(ticker, session)
    if df.empty:
        return ToolResult(status="error", error=f"No price data available for {ticker}.")
```

**Why lightweight ingest instead of full `ingest_ticker`:** `analyze_stock` has `timeout_seconds = 15.0`. Full `ingest_ticker` fetches fundamentals, analyst data, earnings (4+ yfinance calls, 10-15s). Lightweight ingest (ensure_stock + price fetch) takes 3-5s, leaving time for signal computation.

**Rate limiting:** The chat router already enforces per-user rate limits on tool execution. Additionally, `ensure_stock_exists` is idempotent — calling it twice for the same ticker is a no-op (checks DB first).

---

## Fix 5: Portfolio Transaction Auto-Ingest (KAN-404)

### What

When a portfolio transaction references a ticker not in the `stocks` table, auto-create the Stock record via `ensure_stock_exists` before the transaction, instead of returning 422. Validate ticker format.

### Where

- **`backend/routers/portfolio.py:100-124`** — add pre-check before `db.flush()`

### Design

Before creating the Transaction:

```python
import re
from backend.services.stock_data import ensure_stock_exists

# Validate ticker format
if not re.match(r"^[A-Z]{1,5}$", body.ticker.upper()):
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="Invalid ticker format. Use 1-5 uppercase letters.",
    )

# Ensure stock exists (creates from yfinance if missing)
try:
    await ensure_stock_exists(body.ticker, db)
except ValueError:
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=f"Ticker '{body.ticker}' not recognized. Verify the symbol is correct.",
    )
```

Keep the existing `IntegrityError` catch as a safety net (belt + suspenders).

**Why `ensure_stock_exists` not `ingest_ticker`:** `ensure_stock_exists` is a single yfinance call (~1s). Portfolio transactions should be fast. The nightly pipeline handles price/signal/forecast backfill since the ticker is now in a position → included in the union query.

**Bulk upload concern:** If a CSV upload creates 50 transactions with 20 new tickers, that's 20 yfinance calls. `ensure_stock_exists` is idempotent, so duplicate tickers in the CSV don't multiply calls. The endpoint is already behind auth + rate limiting.

---

## Fix 6: Portfolio Forecast — No Silent Skip (KAN-404)

### What

Add `missing_tickers` field to `PortfolioForecastResponse`. Recompute weights using only tickers that have forecasts. Include floored forecasts (Fix 1) in `missing_tickers`.

### Where

- **`backend/schemas/forecasts.py:42-48`** — add `missing_tickers: list[str] = Field(default_factory=list)`
- **`backend/routers/forecasts.py:118-158`** — track missing tickers, recompute denominator

### Design

```python
# After building forecasts_by_ticker
tickers_with_forecast = set(forecasts_by_ticker.keys())
missing_tickers = sorted(set(position_values.keys()) - tickers_with_forecast)

# Recompute total using ONLY tickers with forecasts as denominator
forecast_value = sum(v for t, v in position_values.items() if t in tickers_with_forecast)
if forecast_value == 0:
    return PortfolioForecastResponse(
        horizons=[], ticker_count=0, missing_tickers=sorted(position_values.keys())
    )

# Use forecast_value as denominator instead of total_value
for ticker, value in position_values.items():
    if ticker not in tickers_with_forecast:
        continue  # Skip — already in missing_tickers
    weight = value / forecast_value  # Weights sum to 1.0 across covered tickers
    ...
```

**Backwards compatible:** `missing_tickers` has a default of `[]`, so existing clients ignore it.

**Weight math:** If portfolio is 40% AAPL, 30% GOOG, 30% FORD, and FORD has no forecast:
- Old: AAPL weight = 0.4, GOOG weight = 0.3, FORD silently skipped → weights sum to 0.7 (wrong)
- New: AAPL weight = 0.4/0.7 = 0.57, GOOG weight = 0.3/0.7 = 0.43 → weights sum to 1.0, `missing_tickers: ["FORD"]`

---

## Fix 7: On-Ingest Forecast Dispatch (KAN-404)

### What

After a successful on-demand ingest (via endpoint or tool), dispatch `retrain_single_ticker_task.delay(ticker)` as fire-and-forget so the ticker gets a forecast soon, without blocking the ingest response.

### Where

- **`backend/services/pipelines.py:120-140`** — after step 6 (update_last_fetched_at), dispatch Celery task

### Design

```python
# ── Step 7b: Dispatch forecast training (fire-and-forget) ──
try:
    from backend.tasks.forecasting import retrain_single_ticker_task
    retrain_single_ticker_task.delay(ticker)
    logger.info("Dispatched forecast training for %s", ticker)
except Exception:
    logger.warning("Failed to dispatch forecast for %s", ticker, exc_info=True)
```

This is best-effort. If Celery is down, the nightly pipeline picks it up next run (Fix 3).

Only dispatches if the ticker has enough data — `retrain_single_ticker_task` internally calls `train_prophet_model()` which enforces `MIN_DATA_POINTS = 200`. If the ticker is brand new with no price history yet, the task will fail gracefully and the nightly pipeline will pick it up after price backfill.

---

## Files Changed Summary

| File | Fix | Change |
|---|---|---|
| `backend/services/ticker_universe.py` | 2 | NEW — canonical `get_all_referenced_tickers()` |
| `backend/tools/forecasting.py` | 1 | Scale-appropriate price floor + `is_floored` flag |
| `backend/schemas/forecasts.py` | 1, 6 | `Field(gt=0)` on prices, `missing_tickers` on portfolio response |
| `backend/tasks/market_data.py` | 2 | Use canonical ticker query, remove `_get_all_watchlist_tickers()` |
| `backend/tasks/forecasting.py` | 2, 3 | Use canonical ticker query, dispatch training for new tickers |
| `backend/tools/analyze_stock.py` | 4 | Lightweight auto-ingest on missing data |
| `backend/routers/portfolio.py` | 5 | `ensure_stock_exists` before transaction |
| `backend/routers/forecasts.py` | 6 | Track + report missing tickers, fix weight denominator |
| `backend/services/pipelines.py` | 7 | Fire-and-forget forecast dispatch |

---

## Test Plan

| Fix | Test | Type |
|---|---|---|
| 1 | Prophet output with negative yhat → floored to `max(0.01, price*0.01)` + warning logged | Unit |
| 1 | ForecastHorizon schema rejects price ≤ 0 | Unit |
| 1 | Floored forecast excluded from portfolio aggregation (in `missing_tickers`) | Unit |
| 2 | `get_all_referenced_tickers()` returns union of index + watchlist + portfolio | Unit |
| 2 | Ticker in portfolio but not in index or watchlist → included in result | Unit |
| 2 | Ticker with shares=0 → excluded from result | Unit |
| 3 | Nightly forecast dispatches training for ticker with prices but no ModelVersion | Unit |
| 3 | Ticker with < 200 data points is skipped | Unit |
| 3 | Cap of 20 new tickers per nightly run respected | Unit |
| 4 | analyze_stock auto-ingests ticker with no data (lightweight path) | Unit |
| 4 | analyze_stock rejects invalid ticker format (numbers, specials) | Unit |
| 5 | Portfolio transaction with unknown but valid ticker → auto-creates Stock record | API |
| 5 | Portfolio transaction with invalid ticker format → 422 | API |
| 5 | Portfolio transaction with unrecognized ticker (yfinance fails) → 422 | API |
| 6 | Portfolio forecast response includes `missing_tickers` for positions without forecasts | Unit |
| 6 | Weights sum to 1.0 when some tickers are missing | Unit |
| 6 | All tickers missing → empty horizons + full `missing_tickers` list | Unit |
| 7 | Ingest pipeline dispatches `retrain_single_ticker_task` on success | Unit |
| 7 | Celery failure in dispatch doesn't break ingest | Unit |

---

## Review Findings Addressed (v2)

| # | Severity | Finding | Resolution |
|---|---|---|---|
| C1 | CRITICAL | Fix 3: 60-day threshold vs `MIN_DATA_POINTS=200` | Use 200, import the constant |
| C2 | CRITICAL | Fix 1: $0.01 floor creates extreme outlier in portfolio aggregation | Scale-appropriate: `max(0.01, price*0.01)` + exclude from aggregation |
| H1 | HIGH | Duplicated ticker-set logic in market_data.py and forecasting.py | Single canonical `get_all_referenced_tickers()` in `ticker_universe.py` |
| H2 | HIGH | Prophet training inline in nightly could timeout | Dispatch as individual Celery tasks, cap at 20 |
| H3 | HIGH | Chat auto-ingest exceeds 15s tool timeout | Lightweight path: `ensure_stock_exists` + `fetch_prices_delta` only |
| H4 | HIGH | Weight recomputation denominator not explicit | Explicit: `forecast_value` as new denominator, weights sum to 1.0 |
| H5 | HIGH | No rate limiting on auto-ingest | Ticker format validation + idempotent `ensure_stock_exists` + existing auth rate limits |

---

## Out of Scope

- Frontend changes to display `missing_tickers` (separate ticket)
- Scenario modeling on portfolio (future enhancement)
- Sentiment scoring batching optimization (KAN-405)
- SPY ETF history alignment (KAN-406)
- News pipeline changes (news uses stock universe, not user-referenced tickers — different lifecycle)
- DB migration (no schema changes needed — `missing_tickers` is computed, not stored)
- Per-user auto-ingest rate limiting beyond existing auth rate limits (future if abuse detected)
