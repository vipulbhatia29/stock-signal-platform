# Data Architecture — Stock Signal Platform

**Version:** 1.0
**Date:** March 2026

---

## 1. Design Principles

1. **Everything is traceable.** Every prediction, recommendation, and signal
   can be traced back to the exact data and model version that produced it.
2. **Immutable history.** Price data, signal snapshots, and forecasts are
   append-only. We never overwrite historical data — we add new snapshots.
3. **Single database, smart partitioning.** Postgres + TimescaleDB handles
   both operational (users, portfolios) and time-series (prices, signals) data.
   No separate analytics database until we genuinely outgrow this.
4. **Lightweight model lineage, not enterprise MLOps.** We track what matters
   (training data range, hyperparameters, metrics, which predictions came from
   which model) without the overhead of MLflow, model registries, or A/B testing
   infrastructure.

---

## 2. Data Volume Estimates

Assuming 500 tracked stocks, 10-year history, daily granularity:

| Table | Rows/Year | 10-Year Total | Row Size (est.) | Total Size |
|-------|-----------|---------------|-----------------|------------|
| StockPrice | 126,000 | 1,260,000 | ~100 bytes | ~120 MB |
| SignalSnapshot | 182,500 | 1,825,000 | ~200 bytes | ~350 MB |
| FundamentalSnapshot | 2,000 | 20,000 | ~300 bytes | ~6 MB |
| RecommendationSnapshot | 182,500 | 1,825,000 | ~300 bytes | ~520 MB |
| RecommendationOutcome | 109,500 | 1,095,000 | ~200 bytes | ~210 MB |
| PortfolioSnapshot | 365 | 3,650 | ~2 KB | ~7 MB |
| ForecastResult | 78,000 | 780,000 | ~250 bytes | ~190 MB |
| MacroSnapshot | 3,650 | 36,500 | ~150 bytes | ~5 MB |
| ModelVersion | ~2,600 | ~26,000 | ~1 KB | ~25 MB |
| **Total** | | | | **~1.4 GB** |

This is comfortably small for Postgres. Even 10x growth (5,000 stocks) stays
under 10 GB. TimescaleDB compression will shrink this further — typically 90%+
compression on time-series data older than 30 days.

---

## 3. Entity-Relationship Model

### 3.1 Operational Tables (Standard Postgres)

```
┌─────────────────────┐      ┌─────────────────────────┐
│ User                │      │ UserPreference           │
│─────────────────────│      │─────────────────────────│
│ id (PK, UUID)       │──┐   │ id (PK, UUID)           │
│ email (unique)      │  │   │ user_id (FK → User, UQ) │
│ hashed_password     │  │   │ timezone (VARCHAR)       │ ← default 'America/New_York'
│ role (enum)         │  │   │ default_stop_loss_pct    │ ← default 20.0
│ is_active           │  │   │ max_position_pct         │ ← default 5.0
│ created_at          │  │   │ max_sector_pct           │ ← default 30.0
│ updated_at          │  │   │ min_cash_reserve_pct     │ ← default 10.0
└─────────────────────┘  │   │ notify_telegram (BOOL)   │
                         │   │ notify_email (BOOL)      │
┌─────────────────────┐  │   │ quiet_hours_start (TIME) │
│ Stock               │  │   │ quiet_hours_end (TIME)   │
│─────────────────────│  │   │ composite_weights (JSONB)│ ← override defaults
│ id (PK, UUID)       │  │   │ updated_at              │
│ ticker (unique)     │  │   └─────────────────────────┘
│ name                │  │
│ exchange            │  │   ┌─────────────────────────┐
│ sector              │  │   │ Watchlist                │
│ industry            │  └──>│─────────────────────────│
│ is_in_universe(BOOL)│      │ id (PK, UUID)           │
│ is_active           │      │ user_id (FK → User)     │
│ last_fetched_at     │      │ ticker (FK → Stock)     │
│ created_at          │      │ added_at                │
│ updated_at          │      └─────────────────────────┘
└─────────────────────┘
                             ┌─────────────────────────┐
┌─────────────────────┐      │ StockIndexMembership     │
│ StockIndex          │      │─────────────────────────│
│─────────────────────│      │ id (PK, UUID)           │
│ id (PK, UUID)       │──┐   │ index_id (FK→StockIndex)│
│ name (unique)       │  └──>│ ticker (FK → Stock)     │
│ description (TEXT)  │      │ added_date (DATE)       │
│ source_url (VARCHAR)│      │ removed_date(DATE,null) │ ← null = current member
│ last_synced_at(TSTZ)│      │ created_at              │
│ created_at          │      └─────────────────────────┘
└─────────────────────┘      Unique: (index_id, ticker, added_date)
Names: "S&P 500",           Index: (index_id, removed_date)
  "NASDAQ-100", "Dow 30"      for current-members query
                             ┌─────────────────────────┐
┌─────────────────────┐      │ Portfolio               │
│ CorporateAction     │      │─────────────────────────│
│─────────────────────│      │ id (PK, UUID)           │
│ id (PK, UUID)       │      │ user_id (FK → User)     │
│ ticker (FK → Stock) │      │ name                    │
│ action_type (enum)  │      │ created_at              │
│ ex_date (DATE)      │      └───────────┬─────────────┘
│ ratio_from (INT)    │                  │
│ ratio_to (INT)      │      ┌───────────▼─────────────┐
│ created_at          │      │ Transaction             │
└─────────────────────┘      │─────────────────────────│
action_type: SPLIT,          │ id (PK, UUID)           │
  REVERSE_SPLIT              │ portfolio_id (FK)       │
ratio: e.g. 1→4 for         │ ticker (FK → Stock)     │
  4:1 split                  │ action (BUY/SELL)       │
                             │ quantity (NUMERIC)      │
┌─────────────────────┐      │ price_per_share(NUMERIC)│
│ DividendPayment     │      │ fees (NUMERIC)          │
│─────────────────────│      │ transacted_at (TSTZ)    │
│ id (PK, UUID)       │      │ notes (TEXT)            │
│ portfolio_id (FK)   │      │ created_at              │
│ ticker (FK → Stock) │      └─────────────────────────┘
│ ex_date (DATE)      │
│ pay_date (DATE)     │      ┌─────────────────────────┐
│ amount_per_share    │      │ Position (MATERIALIZED) │
│ shares_held (NUM)   │      │─────────────────────────│
│ total_amount (NUM)  │      │ portfolio_id (FK)       │
│ created_at          │      │ ticker (FK → Stock)     │
└─────────────────────┘      │ quantity (NUMERIC)      │
                             │ avg_cost (NUMERIC)      │
┌─────────────────────┐      │ total_invested (NUM)    │
│ AlertRule           │      │ realized_pnl (NUMERIC)  │
│─────────────────────│      │ last_updated (TSTZ)     │
│ id (PK, UUID)       │      └─────────────────────────┘
│ user_id (FK)        │      Refreshed on every transaction
│ ticker (FK → Stock) │      insert via DB trigger or
│ rule_type (enum)    │      application-level update
│ params (JSONB)      │
│ is_active           │      ┌─────────────────────────┐
│ created_at          │      │ AlertLog                │
└─────────────────────┘      │─────────────────────────│
                             │ id (PK, UUID)           │
┌─────────────────────┐      │ alert_rule_id (FK)      │
│ ChatSession         │      │ triggered_at            │
│─────────────────────│      │ message                 │
│ id (PK, UUID)       │      │ acknowledged            │
│ user_id (FK)        │      └─────────────────────────┘
│ agent_type          │
│ created_at          │      ┌─────────────────────────┐
│ updated_at          │      │ TaskLog                 │
└───────────┬─────────┘      │─────────────────────────│
            │                │ id (PK, UUID)           │
┌───────────▼─────────────┐  │ task_name (VARCHAR)     │
│ ChatMessage             │  │ status (enum)           │ ← STARTED, SUCCESS,
│─────────────────────────│  │ started_at (TSTZ)       │   FAILED, RETRY
│ id (PK, UUID)           │  │ finished_at (TSTZ)      │
│ session_id (FK)         │  │ error_message (TEXT)     │
│ role (user/assistant)   │  │ retry_count (INT)       │
│ content (TEXT)          │  │ ticker (VARCHAR, null)   │ ← for per-ticker tasks
│ tool_calls (JSONB)      │  │ created_at              │
│ tokens_used (INT)       │  └─────────────────────────┘
│ model_used (VARCHAR)    │
│ created_at              │
└─────────────────────────┘
```

### 3.2 Time-Series Tables (TimescaleDB Hypertables)

These tables use TimescaleDB `create_hypertable()` for automatic time-based
partitioning and compression.

```
┌──────────────────────────────────────┐
│ StockPrice (HYPERTABLE)              │
│──────────────────────────────────────│
│ time (TIMESTAMPTZ, PK part)          │
│ ticker (VARCHAR, PK part, FK→Stock)  │
│ open (NUMERIC)                       │
│ high (NUMERIC)                       │
│ low (NUMERIC)                        │
│ close (NUMERIC)                      │
│ adj_close (NUMERIC)                  │
│ volume (BIGINT)                      │
│ source (VARCHAR, default 'yfinance') │
└──────────────────────────────────────┘
Indexes: (ticker, time DESC), (time DESC)
Chunk interval: 1 month
Compression: after 30 days

┌──────────────────────────────────────┐
│ SignalSnapshot (HYPERTABLE)          │
│──────────────────────────────────────│
│ computed_at (TIMESTAMPTZ, PK part)   │
│ ticker (VARCHAR, PK part, FK→Stock)  │
│ rsi_value (FLOAT)                    │
│ rsi_signal (VARCHAR)                 │
│ macd_value (FLOAT)                   │
│ macd_histogram (FLOAT)               │
│ macd_signal_label (VARCHAR)          │
│ sma_50 (FLOAT)                       │
│ sma_200 (FLOAT)                      │
│ sma_signal (VARCHAR)                 │
│ bb_upper (FLOAT)                     │
│ bb_lower (FLOAT)                     │
│ bb_position (VARCHAR)                │
│ annual_return (FLOAT)                │
│ volatility (FLOAT)                   │
│ sharpe_ratio (FLOAT)                 │
│ composite_score (FLOAT)              │
│ composite_weights (JSONB)            │
└──────────────────────────────────────┘
Chunk interval: 1 month
Compression: after 90 days

┌──────────────────────────────────────┐
│ FundamentalSnapshot (HYPERTABLE)     │
│──────────────────────────────────────│
│ recorded_at (TIMESTAMPTZ, PK part)   │
│ ticker (VARCHAR, PK part, FK→Stock)  │
│ period (VARCHAR, e.g. '2025-Q4')     │
│ pe_ratio (FLOAT)                     │
│ pe_5y_avg (FLOAT)                    │
│ peg_ratio (FLOAT)                    │
│ fcf_yield (FLOAT)                    │
│ debt_to_equity (FLOAT)               │
│ interest_coverage (FLOAT)            │
│ piotroski_score (INT)                │
│ market_cap (BIGINT)                  │
│ revenue_growth_yoy (FLOAT)           │
│ earnings_growth_yoy (FLOAT)          │
│ source (VARCHAR)                     │
└──────────────────────────────────────┘
Chunk interval: 3 months
Compression: after 180 days

┌──────────────────────────────────────┐
│ MacroSnapshot (HYPERTABLE)           │
│──────────────────────────────────────│
│ recorded_at (TIMESTAMPTZ, PK part)   │
│ indicator (VARCHAR, PK part)         │
│ value (FLOAT)                        │
│ label (VARCHAR)                      │
│ source (VARCHAR, default 'fred')     │
└──────────────────────────────────────┘
Indicators: yield_curve_10y2y, vix, unemployment_claims,
            fed_funds_rate, market_regime
Chunk interval: 1 month
Compression: after 90 days

┌──────────────────────────────────────┐
│ RecommendationSnapshot (HYPERTABLE)  │
│──────────────────────────────────────│
│ generated_at (TIMESTAMPTZ, PK part)  │
│ ticker (VARCHAR, PK part, FK→Stock)  │
│ user_id (UUID, FK → User)            │
│ action (VARCHAR)                     │  ← BUY, SELL, HOLD, WATCH
│ confidence (VARCHAR)                 │  ← HIGH, MEDIUM, LOW
│ composite_score (FLOAT)              │
│ price_at_recommendation (NUMERIC)    │  ← closing price on recommendation date
│ portfolio_weight_pct (FLOAT, null)   │  ← current allocation if held
│ target_weight_pct (FLOAT)            │  ← suggested allocation
│ suggested_amount_usd (FLOAT, null)   │  ← dollar amount to trade
│ macro_regime (VARCHAR, null)         │  ← risk_on / neutral / risk_off
│ reasoning (JSONB)                    │  ← signals that drove the decision
│ is_actionable (BOOLEAN)             │  ← true if user needs to act
│ acknowledged (BOOLEAN, default F)    │
└──────────────────────────────────────┘
Chunk interval: 1 month
Compression: after 90 days

┌──────────────────────────────────────┐
│ PortfolioSnapshot (HYPERTABLE)       │
│──────────────────────────────────────│
│ snapshot_date (DATE, PK part)        │
│ portfolio_id (UUID, PK part, FK)     │
│ total_value (NUMERIC)                │
│ cash_value (NUMERIC)                 │
│ invested_value (NUMERIC)             │
│ day_pnl (NUMERIC)                    │
│ total_pnl (NUMERIC)                  │
│ total_pnl_pct (FLOAT)               │
│ positions_json (JSONB)               │  ← snapshot of all positions + weights
└──────────────────────────────────────┘
Chunk interval: 3 months
Compression: after 180 days

┌──────────────────────────────────────┐
│ RecommendationOutcome (HYPERTABLE)   │
│──────────────────────────────────────│
│ evaluated_at (TIMESTAMPTZ, PK part)  │
│ recommendation_id (UUID, FK)         │  ← FK → RecommendationSnapshot
│ ticker (VARCHAR, PK part, FK→Stock)  │
│ evaluation_horizon (VARCHAR)         │  ← 30d, 90d, 180d
│ price_at_recommendation (NUMERIC)    │  ← from RecommendationSnapshot
│ price_at_evaluation (NUMERIC)        │  ← actual price at horizon date
│ return_pct (FLOAT)                   │  ← stock return over period
│ benchmark_return_pct (FLOAT)         │  ← SPY return over same period
│ alpha (FLOAT)                        │  ← return_pct - benchmark_return_pct
│ action_was_correct (BOOLEAN)         │  ← BUY beat benchmark / SELL underperformed
│ action (VARCHAR)                     │  ← denormalized: BUY/SELL/HOLD
│ confidence (VARCHAR)                 │  ← denormalized: HIGH/MEDIUM/LOW
│ composite_score_at_rec (FLOAT)       │  ← denormalized for analysis
└──────────────────────────────────────┘
Chunk interval: 3 months
Compression: after 180 days
```

### 3.3 ML Model Tables

```
┌──────────────────────────────────────┐
│ ModelVersion                         │
│──────────────────────────────────────│
│ id (PK, UUID)                        │
│ model_type (VARCHAR)                 │  ← 'prophet_price', 'composite_scorer',
│                                      │     'sector_classifier', etc.
│ version (VARCHAR)                    │  ← Semantic: '1.0.0', '1.0.1', etc.
│ ticker (VARCHAR, nullable)           │  ← NULL for global models, ticker for
│                                      │     per-stock models like Prophet
│ training_data_start (TIMESTAMPTZ)    │
│ training_data_end (TIMESTAMPTZ)      │
│ hyperparameters (JSONB)              │  ← Full reproducibility: every param
│ metrics (JSONB)                      │  ← {'mape': 0.12, 'rmse': 4.3, ...}
│ artifact_path (VARCHAR, nullable)    │  ← Path to serialized model file
│ is_active (BOOLEAN)                  │  ← Only one active per (model_type, ticker)
│ promoted_at (TIMESTAMPTZ, nullable)  │  ← When it became the active version
│ retired_at (TIMESTAMPTZ, nullable)   │  ← When it was replaced
│ notes (TEXT, nullable)               │  ← Why this version was created
│ created_at (TIMESTAMPTZ)             │
└──────────────────────────────────────┘
Unique constraint: (model_type, ticker, version)
Index: (model_type, ticker, is_active) WHERE is_active = true

┌──────────────────────────────────────┐
│ ForecastResult (HYPERTABLE)          │
│──────────────────────────────────────│
│ created_at (TIMESTAMPTZ, PK part)    │
│ ticker (VARCHAR, PK part, FK→Stock)  │
│ model_version_id (FK → ModelVersion) │  ← CRITICAL: links prediction to model
│ horizon_days (INT)                   │  ← 90, 180, 270
│ target_date (DATE)                   │
│ predicted_price (FLOAT)              │
│ lower_80 (FLOAT)                     │  ← 80% confidence interval
│ upper_80 (FLOAT)                     │
│ actual_price (FLOAT, nullable)       │  ← Filled in later for evaluation
│ error_pct (FLOAT, nullable)          │  ← Filled in later: (actual-predicted)/actual
└──────────────────────────────────────┘
Chunk interval: 1 month
Compression: after 90 days
```

---

## 4. Model Versioning Strategy

### 4.1 Why Not MLflow?

MLflow is built for teams running dozens of models in production with experiment
tracking, model registries, and deployment pipelines. We have a handful of models
retraining on a schedule for personal use. The overhead isn't justified.

What we need is **traceability**, not orchestration:
- Which model version generated this forecast?
- What data was it trained on?
- How accurate has it been historically?
- Can I reproduce it?

### 4.2 What We Track

Every model version records:

| Field | Why |
|-------|-----|
| `model_type` | What kind of model (prophet_price, composite_scorer, etc.) |
| `version` | Semantic version, auto-incremented on retrain |
| `ticker` | Per-stock models (Prophet) vs global models (composite scorer) |
| `training_data_start/end` | Exact data range used for training |
| `hyperparameters` | Full JSON of every parameter — reproducibility |
| `metrics` | Training/validation metrics (MAPE, RMSE, MAE, etc.) |
| `artifact_path` | Serialized model file on disk (e.g., `models/prophet/AAPL/v1.0.2.pkl`) |
| `is_active` | Only one active version per (model_type, ticker) at any time |
| `promoted_at / retired_at` | Lifecycle tracking |

### 4.3 Model Lifecycle

```
                  ┌─────────┐
                  │ TRAINED │  ← New model version created
                  └────┬────┘
                       │
                  Validation metrics
                  meet thresholds?
                       │
              ┌────────┴────────┐
              │ NO              │ YES
              ▼                 ▼
        ┌──────────┐    ┌───────────┐
        │ ARCHIVED │    │ PROMOTED  │  ← is_active=True, old version retired
        └──────────┘    └─────┬─────┘
                              │
                         Serves predictions
                         until next retrain
                              │
                        ┌─────▼─────┐
                        │ RETIRED   │  ← is_active=False, retired_at set
                        └───────────┘
```

### 4.4 Model Types in the Platform

| Model Type | Scope | Retrain Frequency | Key Metrics |
|-----------|-------|-------------------|-------------|
| `prophet_price` | Per-ticker | Weekly | MAPE, RMSE, directional accuracy |
| `composite_scorer` | Global | Monthly | Backtested return of score ≥8 vs market |
| `sector_classifier` | Global | Quarterly (future) | Accuracy, F1 |

### 4.5 Forecast Evaluation Loop

This is where model versioning pays off. Every `ForecastResult` row has:
- `predicted_price` — what the model said
- `actual_price` — filled in later when the target date arrives
- `error_pct` — computed automatically by a nightly job

A weekly Celery task (`evaluate_forecasts.py`) does:
1. Find all ForecastResult rows where `target_date <= today AND actual_price IS NULL`
2. Fetch actual closing price from StockPrice
3. Fill in `actual_price` and `error_pct`
4. Aggregate error metrics per `model_version_id`
5. Update `ModelVersion.metrics` with rolling accuracy stats
6. If accuracy degrades below threshold → trigger retrain

This closes the feedback loop. Without model versioning, you'd have no way to
know which forecasts came from which model, and no way to measure degradation.

### 4.6 Model Artifact Storage

For local/single-user deployment:
```
data/
└── models/
    ├── prophet/
    │   ├── AAPL/
    │   │   ├── v1.0.0.pkl
    │   │   ├── v1.0.1.pkl     ← active
    │   │   └── v1.0.2.pkl     ← training
    │   ├── MSFT/
    │   │   └── v1.0.0.pkl     ← active
    │   └── ...
    └── composite_scorer/
        └── global/
            └── v2.1.0.pkl     ← active
```

For cloud deployment (Phase 6): move to Azure Blob Storage with the same
path structure. The `artifact_path` in ModelVersion simply changes from a
local path to a blob URI.

---

## 5. TimescaleDB Configuration

### 5.1 Hypertable Setup

```sql
-- Run after table creation in Alembic migration

-- StockPrice: most queried, monthly chunks
SELECT create_hypertable('stock_prices', 'time',
    chunk_time_interval => INTERVAL '1 month');

-- SignalSnapshot: monthly chunks
SELECT create_hypertable('signal_snapshots', 'computed_at',
    chunk_time_interval => INTERVAL '1 month');

-- FundamentalSnapshot: quarterly chunks (sparse data)
SELECT create_hypertable('fundamental_snapshots', 'recorded_at',
    chunk_time_interval => INTERVAL '3 months');

-- RecommendationSnapshot: monthly chunks
SELECT create_hypertable('recommendation_snapshots', 'generated_at',
    chunk_time_interval => INTERVAL '1 month');

-- PortfolioSnapshot: quarterly chunks (1 row per day)
SELECT create_hypertable('portfolio_snapshots', 'snapshot_date',
    chunk_time_interval => INTERVAL '3 months');

-- ForecastResult: monthly chunks
SELECT create_hypertable('forecast_results', 'created_at',
    chunk_time_interval => INTERVAL '1 month');

-- MacroSnapshot: monthly chunks
SELECT create_hypertable('macro_snapshots', 'recorded_at',
    chunk_time_interval => INTERVAL '1 month');

-- RecommendationOutcome: quarterly chunks (evaluated over long horizons)
SELECT create_hypertable('recommendation_outcomes', 'evaluated_at',
    chunk_time_interval => INTERVAL '3 months');
```

### 5.2 Compression Policies

```sql
-- Compress old data to save storage (90%+ reduction typical)

-- Prices older than 30 days
ALTER TABLE stock_prices SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'ticker',
    timescaledb.compress_orderby = 'time DESC'
);
SELECT add_compression_policy('stock_prices', INTERVAL '30 days');

-- Signals older than 90 days
ALTER TABLE signal_snapshots SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'ticker',
    timescaledb.compress_orderby = 'computed_at DESC'
);
SELECT add_compression_policy('signal_snapshots', INTERVAL '90 days');

-- Forecasts older than 90 days
ALTER TABLE forecast_results SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'ticker',
    timescaledb.compress_orderby = 'created_at DESC'
);
SELECT add_compression_policy('forecast_results', INTERVAL '90 days');
```

### 5.3 Retention Policies

```sql
-- We keep everything by default (for backtesting and model evaluation).
-- Only chat messages get pruned after 1 year.
-- If storage becomes a concern, add selective retention:

-- Example (NOT applied by default):
-- SELECT add_retention_policy('stock_prices', INTERVAL '20 years');
-- SELECT add_retention_policy('signal_snapshots', INTERVAL '10 years');
```

### 5.4 Continuous Aggregates (Phase 5 optimization)

```sql
-- Pre-compute weekly and monthly OHLCV rollups for faster chart rendering.
-- Only add these when dashboard performance needs it.

CREATE MATERIALIZED VIEW stock_prices_weekly
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 week', time) AS bucket,
    ticker,
    first(open, time) AS open,
    max(high) AS high,
    min(low) AS low,
    last(close, time) AS close,
    sum(volume) AS volume
FROM stock_prices
GROUP BY bucket, ticker;

SELECT add_continuous_aggregate_policy('stock_prices_weekly',
    start_offset => INTERVAL '1 month',
    end_offset => INTERVAL '1 day',
    schedule_interval => INTERVAL '1 day');
```

---

## 6. Data Flow Diagrams

### 6.1 Nightly Data Pipeline

```
┌───────────┐     ┌──────────────┐     ┌────────────────────┐
│ Celery    │     │ yfinance API │     │ StockPrice         │
│ Beat      │────>│ (free, no    │────>│ (hypertable)       │
│ (cron)    │     │  API key)    │     │ append new OHLCV   │
└───────────┘     └──────────────┘     └────────┬───────────┘
                                                │
                                    ┌───────────▼───────────┐
                                    │ signals.py            │
                                    │ compute RSI, MACD,    │
                                    │ SMA, Bollinger, etc.  │
                                    └───────────┬───────────┘
                                                │
                                    ┌───────────▼───────────┐
                                    │ SignalSnapshot        │
                                    │ (hypertable)          │
                                    │ append new row        │
                                    └───────────┬───────────┘
                                                │
                                    ┌───────────▼───────────┐
                                    │ check_alerts.py       │
                                    │ evaluate stop-loss,   │
                                    │ concentration, etc.   │
                                    └───────────┬───────────┘
                                                │
                                    ┌───────────▼───────────┐
                                    │ AlertLog              │
                                    │ + Telegram notify     │
                                    └───────────────────────┘
```

### 6.2 Weekly Forecast Pipeline

```
┌───────────┐     ┌──────────────────┐     ┌──────────────────┐
│ Celery    │     │ For each ticker: │     │ ModelVersion      │
│ Beat      │────>│ 1. Load prices   │────>│ (new row if       │
│ (weekly)  │     │ 2. Train Prophet │     │  retrained)       │
└───────────┘     │ 3. Validate      │     └────────┬─────────┘
                  └──────────────────┘              │
                                        ┌───────────▼──────────┐
                                        │ ForecastResult       │
                                        │ (hypertable)         │
                                        │ 3 rows per ticker:   │
                                        │ 90d, 180d, 270d      │
                                        └──────────────────────┘
```

### 6.3 Forecast Evaluation Loop

```
┌───────────┐     ┌───────────────────┐     ┌────────────────────┐
│ Celery    │     │ ForecastResult    │     │ ForecastResult     │
│ Beat      │────>│ WHERE target_date │────>│ UPDATE actual_price│
│ (nightly) │     │ <= today AND      │     │ and error_pct      │
└───────────┘     │ actual IS NULL    │     └────────┬───────────┘
                  └───────────────────┘              │
                                        ┌────────────▼───────────┐
                                        │ Aggregate error by     │
                                        │ model_version_id       │
                                        │ → update ModelVersion  │
                                        │   .metrics             │
                                        └────────────┬───────────┘
                                                     │
                                            Accuracy below
                                            threshold?
                                                     │
                                            ┌────────▼────────┐
                                            │ Trigger retrain  │
                                            │ for that ticker  │
                                            └─────────────────┘
```

---

## 7. Query Patterns & Indexes

### High-frequency queries and their supporting indexes:

| Query | Table | Index |
|-------|-------|-------|
| Latest price for ticker | StockPrice | `(ticker, time DESC)` — built-in from hypertable |
| Price history for chart (1Y) | StockPrice | Same index, range scan on time |
| Latest signals for watchlist | SignalSnapshot | `(ticker, computed_at DESC)` |
| Signal history for chart | SignalSnapshot | Same index, range scan |
| Today's actionable recommendations | RecommendationSnapshot | `(user_id, generated_at DESC) WHERE is_actionable` |
| Portfolio value over time | PortfolioSnapshot | `(portfolio_id, snapshot_date DESC)` |
| Current positions | Position | `(portfolio_id, ticker)` — materialized |
| Dividends for portfolio | DividendPayment | `(portfolio_id, pay_date DESC)` |
| Active model for ticker | ModelVersion | `(model_type, ticker) WHERE is_active` |
| Forecasts for ticker | ForecastResult | `(ticker, created_at DESC)` |
| Unevaluated forecasts | ForecastResult | `(target_date) WHERE actual_price IS NULL` |
| User's portfolio positions | Transaction | `(portfolio_id, ticker, transacted_at)` |
| Failed background jobs | TaskLog | `(status, created_at DESC) WHERE status = 'FAILED'` |
| Stock universe for screener | Stock | `(is_in_universe) WHERE is_in_universe AND is_active` |
| Stocks in an index | StockIndexMembership | `(index_id, removed_date) WHERE removed_date IS NULL` |
| Bulk signals for screener | SignalSnapshot | `DISTINCT ON (ticker) ORDER BY computed_at DESC` |
| Unevaluated recommendations | RecommendationSnapshot | `(generated_at) WHERE NOT EXISTS matching outcome for horizon` |
| Recommendation hit rate by action | RecommendationOutcome | `(action, action_was_correct)` — aggregate |
| Recommendation alpha by score | RecommendationOutcome | `(composite_score_at_rec, alpha)` — for calibration |

### Composite indexes to add if queries are slow:

```sql
-- Screener: sort all stocks by composite score
CREATE INDEX idx_signals_latest_score ON signal_snapshots
    (computed_at DESC, composite_score DESC);

-- Forecast evaluation: find predictions that need actuals
CREATE INDEX idx_forecasts_unevaluated ON forecast_results
    (target_date) WHERE actual_price IS NULL;
```

---

## 8. Data Seeding Strategy

### Phase 1 (initial load):
1. Populate `Stock` table with S&P 500 constituents (set `is_in_universe=True`)
   - Script: `scripts/sync_sp500.py` — fetches current S&P 500 list from
     Wikipedia or a public API, upserts into Stock table
   - Run quarterly to keep universe current

### Phase 2 (index membership):
1a. Create `StockIndex` records for S&P 500, NASDAQ-100, Dow 30
1b. Populate `StockIndexMembership` to link stocks to their indexes
   - Script: `scripts/sync_indexes.py` — syncs all three indexes
   - Each stock can belong to multiple indexes (e.g., AAPL in all three)
2. Pre-populate watchlist with ~50 starter stocks across sectors:
   - **Benchmark: SPY** (S&P 500 ETF — ALWAYS included, required for
     recommendation outcome evaluation and alpha calculations)
   - Technology: AAPL, MSFT, GOOGL, AMZN, NVDA, META, AVGO, CRM, ADBE, ORCL
   - Healthcare: UNH, JNJ, LLY, PFE, ABBV, TMO, MRK, ABT, DHR, ISRG
   - Financials: JPM, V, MA, BAC, GS, BLK, SCHW, AXP, C, MS
   - Consumer: PG, KO, PEP, COST, WMT, HD, MCD, NKE, SBUX, TGT
   - Energy/Industrial: XOM, CVX, CAT, GE, HON, UPS, LMT, RTX, DE, BA
3. Backfill `StockPrice` with 10 years of daily OHLCV via yfinance
4. Compute `SignalSnapshot` for each historical trading day (for chart history)

### Phase 3 (fundamentals + portfolio):
5. Backfill `FundamentalSnapshot` with available quarterly data from yfinance
6. Detect historical stock splits via `ticker.splits` and populate `CorporateAction`

### Phase 5 (macro):
7. Backfill `MacroSnapshot` with FRED API historical data

### Seed scripts:
- `scripts/sync_sp500.py` — stock universe sync (idempotent, quarterly)
- `scripts/seed_prices.py` — OHLCV backfill (idempotent, per-ticker)
- `scripts/seed_signals.py` — historical signal computation
- `scripts/seed_fundamentals.py` — quarterly fundamental backfill

All scripts are:
- Idempotent (safe to run multiple times)
- Show progress bar with estimated time
- Respect yfinance rate limits (2-second delay between tickers)
- Log errors per ticker without failing the entire batch

---

## 9. Backup & Recovery

### Local development:
- `pg_dump` via `run.sh backup` command
- Stored in `data/backups/` with timestamp

### Production (Phase 6):
- Azure Database for PostgreSQL automated daily backups (35-day retention)
- Point-in-time recovery enabled
- Model artifacts in Azure Blob Storage with versioning enabled

---

## 10. Phase Mapping

| Phase | New Tables | New Hypertables |
|-------|-----------|-----------------|
| 1 | User, UserPreference, Stock, Watchlist | StockPrice, SignalSnapshot |
| 2 | StockIndex, StockIndexMembership | — |
| 3 | Portfolio, Transaction, Position, DividendPayment, CorporateAction, AlertRule, AlertLog | FundamentalSnapshot, RecommendationSnapshot, PortfolioSnapshot |
| 4 | ChatSession, ChatMessage | — |
| 5 | ModelVersion, TaskLog | ForecastResult, MacroSnapshot, RecommendationOutcome |
| 6 | — (no new tables) | — |

---

## 11. Migration Strategy

All schema changes go through Alembic migrations. Rules:

1. **Never edit a migration after it's been applied.** Create a new one.
2. **Always include both upgrade() and downgrade().**
3. **TimescaleDB operations** (create_hypertable, compression policies) go in
   migrations using `op.execute()` with raw SQL.
4. **Data migrations** (backfills, transforms) are separate from schema migrations.
5. **Test migrations** against a fresh database AND against an existing one with
   data before merging.
