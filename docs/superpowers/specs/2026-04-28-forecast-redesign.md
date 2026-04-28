# Spec: Forecast System Redesign — From Prophet Price Targets to Ensemble Return Forecasting

**Date:** 2026-04-28
**Status:** Draft
**Author:** Claude (Opus)
**Ticket:** TBD (KAN-5xx)
**Supersedes:** Original Prophet forecasting (Phase 5 spec)

---

## 1. Problem Statement

The current forecasting system uses Facebook Prophet to predict absolute stock prices at 90/180/270-day horizons. This produces nonsensical results — e.g., AAPL at $141 today forecasted at $317 in 90 days (+125%). The problem is fundamental, not a tuning issue:

- Prophet extrapolates a trend line fitted to 2 years of price history — it has no concept of valuation, mean reversion, or market efficiency
- Research consensus: Prophet cannot beat naive forecasting (predicting "tomorrow = today") on any horizon tested
- Displaying absolute price targets ($317) misleads part-time investors into thinking these are meaningful predictions
- The model ignores the rich signal data we already compute (RSI, MACD, convergence, sentiment) — it only sees raw price

**Goal:** Replace the forecasting engine with a system that produces defensible, interpretable, and useful forecasts for part-time investors, leveraging the signal infrastructure we've already built.

---

## 2. Design Principles

1. **Forecast returns, not prices** — "+3.2% ± 6%" is defensible; "$317" is not
2. **Ensemble over single-model** — no single model works across all market regimes
3. **Leverage existing signals** — our nightly pipeline computes 15+ features per ticker; the forecast model should consume them, not ignore them
4. **Probabilistic, not point** — always output a confidence interval and a calibrated confidence score
5. **Interpretable** — users should see *which signals* drove the forecast (feature importance)
6. **Honest about uncertainty** — when confidence is low, say so; never fabricate precision
7. **Evolutionary** — architecture supports adding TFT/LSTM models later without schema changes

---

## 3. Architecture

### 3.1 Two-Layer System

```
Layer 1: Feature Assembly (existing nightly pipeline)
  SignalSnapshot + NewsSentimentDaily + SignalConvergenceDaily + macro context
  → Feature vector per ticker per day

Layer 2: Ensemble Return Forecast (NEW)
  Feature vectors → LightGBM model → expected return % + confidence
  → Store in forecast_results (modified schema)
  → Serve via API → Display as directional outlook
```

### 3.2 Feature Vector (per ticker, per day)

All features are already computed nightly. No new data sources required.

| # | Feature | Source | Type |
|---|---------|--------|------|
| 1 | `momentum_30d` | Price history: `(price_today / price_30d_ago) - 1` | float |
| 2 | `momentum_90d` | Price history: `(price_today / price_90d_ago) - 1` | float |
| 3 | `rsi_value` | `SignalSnapshot.rsi_value` | float (0-100) |
| 4 | `macd_histogram` | `SignalSnapshot.macd_histogram` | float |
| 5 | `sma_cross` | Encode `SignalSnapshot.sma_signal`: ABOVE_200=2, ABOVE_50=1, BELOW_200=0 | int |
| 6 | `bb_position` | Encode `SignalSnapshot.bb_position`: UPPER=2, MIDDLE=1, LOWER=0 | int |
| 7 | `volatility` | `SignalSnapshot.volatility` | float |
| 8 | `sharpe_ratio` | `SignalSnapshot.sharpe_ratio` | float |
| 9 | `annual_return` | `SignalSnapshot.annual_return` | float |
| 10 | `composite_score` | `SignalSnapshot.composite_score` | float (0-10) |
| 11 | `stock_sentiment` | `NewsSentimentDaily.stock_sentiment` | float (-1 to 1) |
| 12 | `sector_sentiment` | `NewsSentimentDaily.sector_sentiment` | float (-1 to 1) |
| 13 | `macro_sentiment` | `NewsSentimentDaily.macro_sentiment` | float (-1 to 1) |
| 14 | `sentiment_confidence` | `NewsSentimentDaily.confidence` | float (0-1) |
| 15 | `signals_aligned` | `SignalConvergenceDaily.signals_aligned` | int (0-6) |
| 16 | `convergence_label` | Encode: strong_bull=2, weak_bull=1, neutral=0, weak_bear=-1, strong_bear=-2 | int |
| 17 | `vix_level` | From market data (VIX close) | float |
| 18 | `spy_momentum_30d` | SPY 30-day return | float |

### 3.3 Target Variable

**Forward N-day log return**: `ln(price[t+N] / price[t])`

- Log returns are additive, symmetric, and approximately normal — better statistical properties than raw % change
- Two horizons: **30 days** and **90 days** (drop 180d and 270d — too uncertain to be useful)
- For display, convert back to simple return: `exp(log_return) - 1`

### 3.4 Model: LightGBM + XGBoost Ensemble

**Why gradient boosting ensemble, not deep learning:**

| Factor | LightGBM + XGBoost | TFT/LSTM |
|--------|-------------------|----------|
| Training data needed | 5K-50K samples sufficient | 100K+ recommended |
| Our data size now | ~20 tickers × 500 days = 10K | Insufficient |
| Our data size at 10y | ~500 tickers × 2500 days = 1.25M | Viable at this scale |
| Training time | Seconds on CPU | Minutes-hours on GPU |
| Feature importance | Built-in (SHAP) | Requires attention analysis |
| Overfitting risk | Low with proper CV | High with small data |
| Infrastructure | No GPU needed | GPU recommended |
| Ensemble benefit | Combined outperforms either alone (research-confirmed) | N/A |

**Why both LightGBM AND XGBoost:**

Research confirms the combined model outperforms either individually. They have complementary strengths:

| | LightGBM | XGBoost |
|---|----------|---------|
| Tree growth | Leaf-wise (faster convergence) | Level-wise (more balanced) |
| Speed | Faster on large datasets | Slower but more thorough |
| Regularization | Lighter default regularization | Stronger built-in regularization |
| Bias profile | Slightly lower bias | Slightly lower variance |

By averaging their predictions (weighted by recent backtest performance), we reduce variance without adding infrastructure complexity. Each model sees the same features and targets — the ensemble is a simple weighted average, not a complex stacking architecture.

**Ensemble strategy:**

```
For each horizon (60d, 90d) × each quantile (0.1, 0.5, 0.9):
  1. Train LightGBM model → prediction_lgb
  2. Train XGBoost model → prediction_xgb
  3. Final prediction = w_lgb * prediction_lgb + w_xgb * prediction_xgb

  Weights initialized at 0.5/0.5, then adjusted weekly based on
  rolling backtest performance (last 90 days of matured forecasts).
  Better-performing model gets higher weight, clamped to [0.3, 0.7].
```

This means **6 model artifacts per horizon** (2 models × 3 quantiles), **12 total** for both horizons. Each artifact is small (~100KB for LightGBM, ~200KB for XGBoost).

**Evolution path:** When we reach 500+ tickers and 2+ years of our own signal history (est. 18-24 months), add TFT as a third model in the ensemble. The schema and API contract designed here will support this without breaking changes — just add `model_type="tft_60d"` to `model_versions` and a third weight.

**Training approach:**

- **Walk-forward cross-validation**: 12-month expanding training window, 1-month step, predict 60d and 90d forward returns
- **Retrain frequency**: Weekly (Sunday, like current Prophet retrain)
- **Per-universe model** (not per-ticker): Train one model across all tickers — each row is (ticker, date, features) → forward return. This pools data across tickers, dramatically increasing sample size
- **Quantile regression**: Train 3 quantile models per framework per horizon — median (q=0.5), lower bound (q=0.1), upper bound (q=0.9). This produces calibrated 80% prediction intervals directly from the model ensemble

**Hyperparameters:**

```python
LIGHTGBM_PARAMS = {
    "objective": "quantile",
    "metric": "quantile",
    "alpha": 0.5,                  # varies: 0.1, 0.5, 0.9
    "num_leaves": 31,
    "learning_rate": 0.05,
    "n_estimators": 500,
    "min_child_samples": 20,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "reg_alpha": 0.1,
    "reg_lambda": 0.1,
    "early_stopping_rounds": 50,
    "verbose": -1,
}

XGBOOST_PARAMS = {
    "objective": "reg:quantileerror",
    "quantile_alpha": 0.5,         # varies: 0.1, 0.5, 0.9
    "max_depth": 6,
    "learning_rate": 0.05,
    "n_estimators": 500,
    "min_child_weight": 20,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "reg_alpha": 0.1,
    "reg_lambda": 1.0,             # XGBoost benefits from stronger L2
    "early_stopping_rounds": 50,
    "verbosity": 0,
}

# Ensemble weights — initialized 50/50, adjusted weekly by backtest performance
ENSEMBLE_WEIGHTS = {
    "lightgbm": 0.5,
    "xgboost": 0.5,
}
```

### 3.5 Confidence Score

The confidence score is **not** the model's raw probability. It's a calibrated metric:

```
confidence = f(prediction_interval_width, signals_aligned, historical_accuracy_for_regime)
```

Specifically:
1. **Interval tightness**: `1 - (upper_return - lower_return) / scale_factor` — narrower intervals = higher confidence
2. **Signal agreement**: `signals_aligned / 6` — more aligned signals = higher confidence
3. **Regime match**: Historical accuracy of the model in the current VIX regime (low/normal/high)
4. **Weighted average** of the three, clamped to [0.2, 0.95]

Display tiers:
- **High** (≥ 0.70): Strong signal agreement, tight interval, good regime match
- **Medium** (0.45–0.69): Mixed signals or moderate uncertainty
- **Low** (< 0.45): Conflicting signals, wide interval, or regime mismatch

### 3.6 Feature Importance (Explainability)

For each prediction, store the **top 3 SHAP values** as a JSON field. This powers the "Drivers" display on the frontend:

```json
{
  "drivers": [
    {"feature": "macd_histogram", "direction": "bullish", "importance": 0.34},
    {"feature": "stock_sentiment", "direction": "bullish", "importance": 0.22},
    {"feature": "momentum_30d", "direction": "bearish", "importance": 0.15}
  ]
}
```

---

## 4. Schema Changes

### 4.1 `forecast_results` Table — Column Changes

The table remains a TimescaleDB hypertable with the same composite PK `(forecast_date, ticker, horizon_days)`. Column changes:

| Column | Current | New | Migration |
|--------|---------|-----|-----------|
| `predicted_price` | float, NOT NULL | **RENAME** → `expected_return_pct` (float, NOT NULL) | ALTER COLUMN RENAME |
| `predicted_lower` | float, NOT NULL | **RENAME** → `return_lower_pct` (float, NOT NULL) | ALTER COLUMN RENAME |
| `predicted_upper` | float, NOT NULL | **RENAME** → `return_upper_pct` (float, NOT NULL) | ALTER COLUMN RENAME |
| `actual_price` | float, nullable | **RENAME** → `actual_return_pct` (float, nullable) | ALTER COLUMN RENAME |
| — | — | **ADD** `confidence_score` (float, NOT NULL, default 0.5) | ADD COLUMN |
| — | — | **ADD** `direction` (varchar(10), NOT NULL, default 'neutral') | ADD COLUMN |
| — | — | **ADD** `drivers` (JSONB, nullable) | ADD COLUMN |
| `error_pct` | float, nullable | **KEEP** — recompute as `abs(actual_return_pct - expected_return_pct)` | No change |
| `target_date` | date, NOT NULL | **KEEP** | No change |
| `model_version_id` | UUID FK | **KEEP** | No change |

### 4.2 `model_versions` Table — Column Changes

| Column | Current | New | Migration |
|--------|---------|-----|-----------|
| `model_type` | varchar(20), default "prophet" | **KEEP** — new values: "lightgbm_60d", "lightgbm_90d", "xgboost_60d", "xgboost_90d" | No schema change |
| `hyperparameters` | JSONB | **KEEP** — store LightGBM params | No change |
| `metrics` | JSONB | **KEEP** — store backtest metrics (MAPE, direction_accuracy, etc.) | No change |
| `artifact_path` | varchar(255) | **KEEP** — store serialized LightGBM model (joblib) | No change |

### 4.3 `backtest_runs` Table — No Changes

The backtest schema is metric-agnostic. MAPE, MAE, RMSE, direction_accuracy, ci_containment all apply to return-based forecasts too. The only change is semantic: MAPE on returns vs MAPE on prices.

### 4.4 Migration Plan

**Single Alembic migration** with:
1. Rename columns (data-preserving)
2. Add new columns with defaults
3. Truncate existing forecast_results data (Prophet forecasts are worthless — no value in migrating)
4. Keep model_versions rows for audit trail but mark all Prophet models `status='retired'`

---

## 5. API Changes

### 5.1 `GET /forecasts/{ticker}` — Response Schema Change

**Current `ForecastHorizon`:**
```python
class ForecastHorizon(BaseModel):
    horizon_days: int
    predicted_price: float
    predicted_lower: float
    predicted_upper: float
    target_date: date
    confidence_level: str
    sharpe_direction: str
```

**New `ForecastHorizon`:**
```python
class ForecastHorizon(BaseModel):
    horizon_days: int                           # 30 or 90
    expected_return_pct: float                  # e.g., 3.2 (means +3.2%)
    return_lower_pct: float                     # e.g., -4.1 (10th percentile)
    return_upper_pct: float                     # e.g., 10.5 (90th percentile)
    target_date: date
    direction: str                              # "bullish" | "bearish" | "neutral"
    confidence: float                           # 0.0-1.0, calibrated
    confidence_level: str                       # "high" | "medium" | "low" (derived)
    drivers: list[ForecastDriver] | None        # top 3 SHAP features

class ForecastDriver(BaseModel):
    feature: str                                # e.g., "macd_histogram"
    label: str                                  # e.g., "MACD"  (human-readable)
    direction: str                              # "bullish" | "bearish"
    importance: float                           # 0.0-1.0, relative
```

**New `ForecastResponse`:**
```python
class ForecastResponse(BaseModel):
    ticker: str
    current_price: float                        # needed to compute target price for display
    horizons: list[ForecastHorizon]
    model_type: str                             # "lightgbm" | "tft" (future)
    model_accuracy: ModelAccuracy | None        # replaces model_mape

class ModelAccuracy(BaseModel):
    direction_hit_rate: float                   # 0.0-1.0
    avg_error_pct: float                        # mean |actual - predicted| return error
    ci_containment_rate: float                  # % of actuals within interval
    evaluated_count: int                        # how many matured forecasts
```

### 5.2 `GET /forecasts/{ticker}/track-record` — Adapt

Change `ForecastEvaluation`:
```python
class ForecastEvaluation(BaseModel):
    forecast_date: date
    target_date: date
    horizon_days: int
    expected_return_pct: float                  # was predicted_price
    return_lower_pct: float                     # was predicted_lower
    return_upper_pct: float                     # was predicted_upper
    actual_return_pct: float | None             # was actual_price
    error_pct: float                            # |actual_return - expected_return|
    direction_correct: bool
```

### 5.3 `GET /forecasts/portfolio` — Minor Adaptation

`PortfolioForecastHorizon` already uses `expected_return_pct` — no API change needed. The backend computation changes to use LightGBM outputs instead of Prophet, but the response shape stays the same.

### 5.4 `GET /forecasts/sector/{sector}` — Adapt

Same pattern as per-ticker: replace `predicted_price` fields with `expected_return_pct` fields.

### 5.5 Portfolio Forecast Full (`GET /portfolio/{id}/forecast`)

**Black-Litterman views** currently come from Prophet price predictions. Change the view source to LightGBM expected returns — the BL math stays the same (it takes expected returns as input). Monte Carlo and CVaR are downstream of BL and don't change.

### 5.6 Convergence / Divergence

`SignalConvergenceDaily.forecast_direction` currently comes from Prophet. Change the source to LightGBM's `direction` field. The convergence computation logic stays the same — it only needs "bullish" / "bearish" / "neutral".

---

## 6. Backend Implementation

### 6.1 New Module: `backend/services/forecast_engine.py`

```python
class ForecastEngine:
    """LightGBM-based return forecasting engine."""

    def assemble_features(self, ticker: str, date: date, db: AsyncSession) -> dict:
        """Build feature vector from existing signal/sentiment/convergence data."""

    def train(self, db: AsyncSession, horizon_days: int) -> ModelVersion:
        """Train a LightGBM quantile regression model across all tickers."""

    def predict(self, features: dict, model: lgb.Booster) -> ForecastResult:
        """Predict expected return + interval + confidence for one ticker."""

    def compute_confidence(self, prediction: dict, convergence: dict, regime: str) -> float:
        """Calibrated confidence score from interval width + signal agreement + regime."""

    def explain(self, features: dict, model: lgb.Booster) -> list[dict]:
        """Top 3 SHAP feature importances for this prediction."""
```

### 6.2 Changes to Existing Modules

| Module | Change |
|--------|--------|
| `backend/tools/forecasting.py` | **Gut and replace**: Remove Prophet training/prediction. Keep `compute_sharpe_direction()` and `compute_portfolio_correlation_matrix()`. Add `ForecastEngine` integration. |
| `backend/tasks/forecasting.py` | Change `_forecast_refresh_async()` to use `ForecastEngine.predict()`. Change `_model_retrain_all_async()` to use `ForecastEngine.train()`. |
| `backend/tasks/evaluation.py` | Change `_evaluate_forecasts_async()`: compute `actual_return_pct` instead of `actual_price`. Error metric: `abs(actual_return - expected_return)`. |
| `backend/tasks/convergence.py` | Change forecast direction source: read `forecast_results.direction` instead of computing from Prophet price vs current price. |
| `backend/services/backtesting.py` | Replace Prophet walk-forward with LightGBM walk-forward. Same metric computations, different model. |
| `backend/routers/forecasts.py` | Update response construction to use new column names. Add `current_price` to response. |
| `backend/schemas/forecasts.py` | Update `ForecastHorizon`, `ForecastResponse`, `ForecastEvaluation` per §5. |

### 6.3 Dependencies

**Add:**
- `lightgbm` — gradient boosting model (leaf-wise)
- `xgboost` — gradient boosting model (level-wise)
- `shap` — feature importance explanations

**Remove (eventually):**
- `prophet` — can be removed once migration is complete and old model artifacts are cleaned up. Not urgent — it's a large dependency but removing it is a separate cleanup task.

**Retire (internal modules):**
- `backend/services/sentiment_regressors.py` — Prophet needed this to build regressor columns for the future DataFrame. LightGBM reads today's sentiment as a plain feature; no projection needed.
- `backend/tools/forecasting.py` re-export of `fetch_sentiment_regressors` — delete the backwards-compat shim.
- `PROPHET_REAL_SENTIMENT_ENABLED` config flag — was a rollback toggle for the sentiment regressor fix. Not applicable to LightGBM.

### 6.4 Nightly Pipeline Integration

The forecast task stays in its current position in the nightly chain (Phase 2, after price refresh). The change is internal:

```
Current Phase 2:
  Load Prophet model from disk → make_future_dataframe → predict → store predicted_price

New Phase 2:
  Load LightGBM model from disk → assemble_features from DB → predict → store expected_return_pct
```

Feature assembly queries `signal_snapshots`, `news_sentiment_daily`, and `signal_convergence_daily` — all populated by Phase 1 and earlier in Phase 2. No pipeline ordering changes needed.

---

## 7. Frontend Changes

### 7.1 Type Updates (`types/api.ts`)

```typescript
// Replace ForecastHorizon
export interface ForecastHorizon {
  horizon_days: number;
  expected_return_pct: number;       // was predicted_price
  return_lower_pct: number;          // was predicted_lower
  return_upper_pct: number;          // was predicted_upper
  target_date: string;
  direction: string;                 // "bullish" | "bearish" | "neutral"
  confidence: number;                // 0.0-1.0
  confidence_level: string;          // "high" | "medium" | "low"
  drivers: ForecastDriver[] | null;
}

export interface ForecastDriver {
  feature: string;
  label: string;
  direction: string;
  importance: number;
}

export interface ForecastResponse {
  ticker: string;
  current_price: number;
  horizons: ForecastHorizon[];
  model_type: string;
  model_accuracy: ModelAccuracy | null;
}

export interface ModelAccuracy {
  direction_hit_rate: number;
  avg_error_pct: number;
  ci_containment_rate: number;
  evaluated_count: number;
}
```

### 7.2 Dashboard Bulletin Zone — FCST 90D Column

**Current:** `$317` (predicted_price)

**New:** `+3.2%` with color coding and optional confidence dot

```tsx
// Replace the FCST 90D cell
<TableCell className="py-1.5 text-right font-mono text-xs">
  {fc90 ? (
    <span className={cn(
      fc90.expected_return_pct > 0 && "text-gain",
      fc90.expected_return_pct < 0 && "text-loss",
      fc90.expected_return_pct === 0 && "text-subtle",
    )}>
      {fc90.expected_return_pct > 0 ? "+" : ""}
      {fc90.expected_return_pct.toFixed(1)}%
    </span>
  ) : "—"}
</TableCell>
```

### 7.3 Forecast Card Component — Redesign

**Current:** 3 horizon pills showing "$317" with confidence interval "$280–$350"

**New:** 2 horizon pills (30D, 90D) showing:

```
┌─────────────────────────┐
│  30D                    │
│  ▲ Bullish    72% conf  │
│  +2.1%                  │
│  -1.5% to +5.8%         │
│  MACD ↑  Sentiment ↑    │
└─────────────────────────┘
```

Each pill shows:
- Direction arrow + label (▲ Bullish / ▼ Bearish / — Neutral)
- Confidence percentage
- Expected return % (large, color-coded)
- Return range (lower to upper, muted)
- Top 2 drivers as compact chips

### 7.4 Forecast Track Record — Minor Adaptation

The chart changes from "Predicted Price vs Actual Price" to "Predicted Return vs Actual Return":
- Y-axis: percentage (not dollar)
- Confidence band: return range (not price range)
- KPI tiles stay the same: direction hit rate, avg error %, CI containment

### 7.5 Stock Detail Page — No Structural Change

`ForecastCard` and `ForecastTrackRecord` are already rendered in the stock detail page. The component internals change but the page layout doesn't.

### 7.6 Portfolio Forecast Section — No Change

BL, Monte Carlo, and CVaR components already display returns and percentages. The data source changes (LightGBM instead of Prophet) but the frontend components are unaffected.

---

## 8. Backtest Validation

### 8.1 Walk-Forward Protocol (adapted for LightGBM)

```
For each retrain window:
  1. Training set: all (ticker, date, features, forward_return) where date < window_end
  2. Train 3 LightGBM models: q=0.1, q=0.5, q=0.9
  3. Predict on (ticker, window_end) for each ticker in universe
  4. Wait N days (horizon) to observe actual return
  5. Score: MAPE on returns, direction accuracy, CI containment
```

### 8.2 Minimum Acceptance Criteria

Before deploying the new model, it must beat these baselines on the backtest set:

| Metric | Baseline (naive) | Minimum for deployment |
|--------|-------------------|----------------------|
| Direction accuracy (30d) | 50% (random) | ≥ 55% |
| Direction accuracy (90d) | 50% (random) | ≥ 53% |
| CI containment (80% interval) | 80% (by construction if calibrated) | 75-85% |
| MAPE on returns | N/A | < 50% of Prophet MAPE |

We are deliberately setting a low bar for direction accuracy. Consistently beating 55% on 30-day direction is already valuable for a signal platform — most published research achieves 52-58% on this task. The real value is the ensemble with signals, not the forecast alone.

### 8.3 What We Retire

- Prophet model training and prediction code
- Prophet model artifacts on disk (`data/models/prophet/`)
- 270-day horizon (too uncertain to be actionable)
- Absolute price display on dashboard

---

## 9. Migration and Rollout Plan

### Phase A: Build (Backend)
1. Add `lightgbm` and `shap` to `pyproject.toml`
2. Create `backend/services/forecast_engine.py`
3. Create Alembic migration for column renames + additions
4. Update `backend/schemas/forecasts.py`
5. Update `backend/routers/forecasts.py`
6. Adapt `backend/tasks/forecasting.py`
7. Adapt `backend/tasks/evaluation.py`
8. Adapt `backend/services/backtesting.py`
9. Update convergence task's forecast direction source

### Phase B: Validate (Backtest)
1. Run walk-forward backtest on historical data
2. Verify direction accuracy ≥ 55% (30d) and ≥ 53% (90d)
3. Verify CI containment in 75-85% range
4. Compare MAPE vs Prophet baseline
5. Review feature importances for sanity (no data leakage)

### Phase C: Frontend
1. Update `types/api.ts` with new types
2. Redesign `ForecastCard` component
3. Update bulletin zone FCST column
4. Adapt `ForecastTrackRecord` chart to return-based display
5. Update any tests referencing `predicted_price`

### Phase D: Deploy
1. Run migration (renames + truncate old forecast data)
2. Retire all Prophet model_versions
3. Train first LightGBM model
4. Run nightly pipeline to generate first forecasts
5. Verify frontend renders correctly
6. Monitor drift detection with new model for 1 week

---

## 10. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| LightGBM doesn't beat 55% direction accuracy | Medium | High | Fallback: display convergence signals without forecast column. The signal infrastructure (RSI, MACD, convergence) is already the primary value — forecasts are supplementary. |
| Feature leakage in training | Low | Critical | Strict walk-forward with no future data in features. All features use data available *before* the forecast date. |
| Small training set (10K rows now) | Medium | Medium | Cross-ticker pooling multiplies data. Also: model gets better over time as data accumulates. |
| Breaking API change disrupts frontend | Low | Medium | Coordinate frontend PR with backend migration. Feature-flag the new API response shape if needed. |
| SHAP computation is slow | Low | Low | Compute SHAP only during prediction (not training). For 20 tickers, SHAP adds ~2 seconds total. |

---

## 11. What This Spec Does NOT Cover

- **Recommendation engine changes** — recommendations consume forecasts but their logic (composite score thresholds, BUY/WATCH/AVOID) doesn't change
- **Prophet removal from dependencies** — separate cleanup task after migration is validated
- **TFT/LSTM addition** — future spec when we have 500+ tickers and 2+ years of signal history
- **Real-time intraday forecasts** — out of scope; we're a nightly-cycle platform

---

## 12. Files Affected (Complete List)

### Backend — Modify
| File | Change |
|------|--------|
| `backend/tools/forecasting.py` | Remove Prophet training/prediction, add ForecastEngine calls |
| `backend/tasks/forecasting.py` | Use ForecastEngine for retrain + refresh |
| `backend/tasks/evaluation.py` | Evaluate return-based forecasts |
| `backend/tasks/convergence.py` | Read forecast direction from forecast_results |
| `backend/services/backtesting.py` | LightGBM + XGBoost walk-forward instead of Prophet |
| `backend/services/signal_convergence.py` | **Line 336**: Remove `forecast.predicted_price / signal.current_price - 1.0` → use `forecast.expected_return_pct / 100` directly. Also update `_bulk_fetch_latest_forecasts()` (line 518+) which queries `ForecastResult` columns by name. |
| `backend/services/portfolio_forecast.py` | **`_fetch_prophet_views()` (line 423+)**: Rename to `_fetch_model_views()`. Remove price-to-return conversion (`predicted_price - current_price / current_price`) → use `expected_return_pct` directly. Update `model_type` filter from `"prophet"` to LightGBM/XGBoost. Still needs annualization: `(1 + return_pct/100) ** (252/90) - 1`. |
| `backend/routers/forecasts.py` | Update response construction |
| `backend/schemas/forecasts.py` | New ForecastHorizon, ForecastResponse, ForecastDriver |
| `backend/schemas/portfolio_forecast.py` | `TickerComponent`: rename `trend_pct` → `expected_return_pct`, rename sentiment fields to match new driver concept |
| `backend/models/forecast.py` | Rename columns, add confidence_score/direction/drivers/base_price/forecast_signal |
| `backend/config.py` | Remove PROPHET_* settings, add LIGHTGBM/XGBOOST settings |

### Backend — Create
| File | Purpose |
|------|---------|
| `backend/services/forecast_engine.py` | LightGBM + XGBoost ensemble training, prediction, feature assembly, SHAP |
| `backend/migrations/versions/xxx_forecast_redesign.py` | Column renames + additions |

### Frontend — Modify
| File | Change |
|------|--------|
| `frontend/src/types/api.ts` | Update ForecastHorizon, ForecastResponse, ForecastEvaluation, add ForecastDriver, ModelAccuracy |
| `frontend/src/components/forecast-card.tsx` | Redesign to show returns + drivers (currently shows `$predicted_price.toFixed(0)`, `$predicted_lower – $predicted_upper`) |
| `frontend/src/components/forecast-track-record.tsx` | Y-axis to %, chart dataKey `predicted` → `expected_return_pct`, `actual` → `actual_return_pct`, band keys change |
| `frontend/src/app/(authenticated)/dashboard/_components/bulletin-zone.tsx` | FCST column: `$317` → `+3.2%` (both WatchlistTable line 203 AND PortfolioTable line 295) |
| `frontend/src/components/convergence/accuracy-badge.tsx` | Review: MAPE semantics change (return error vs price error) — thresholds (5%/15%) may need recalibration |
| `frontend/src/components/convergence/divergence-alert.tsx` | No code change — uses `forecast_direction` string which stays the same |
| `frontend/src/components/convergence/traffic-light-row.tsx` | No code change — label "Forecast" stays the same |
| `frontend/src/app/(authenticated)/stocks/[ticker]/stock-detail-client.tsx` | Update ForecastCard props: `modelMape` → `modelAccuracy`, remove `currentPrice` (now in response) |
| `frontend/src/__tests__/components/forecast-track-record.test.tsx` | Update mock data: `predicted_price` → `expected_return_pct` etc. |
| `frontend/src/__tests__/integration/stock-detail.test.tsx` | Update mock `useForecast` return shape |
| `frontend/src/hooks/use-forecasts.ts` | No change (endpoints stay the same) |
| `frontend/src/components/portfolio/bl-forecast-card.tsx` | No change (already uses `expected_return` from BL) |
| `frontend/src/components/portfolio/monte-carlo-chart.tsx` | No change (downstream of BL) |
| `frontend/src/components/portfolio/cvar-card.tsx` | No change (downstream of BL) |

### Tests — Modify
| File | Change |
|------|--------|
| `tests/unit/tasks/test_backtest_specb_followups.py` | Adapt to return-based forecasts |
| `tests/unit/test_forecast_new_ticker_training.py` | Adapt to LightGBM |
| `tests/unit/pipeline/test_evaluation.py` | Adapt to return-based evaluation |
| `tests/unit/tasks/test_forecasting_priority_bypass.py` | Adapt model type |
| `tests/api/test_backtest_task.py` | Adapt to return-based assertions |
| Frontend test files referencing forecast types | Update field names |

---

## 13. Expert Review: Part-Time Investor Perspective

*Reviewed as an expert part-time investor who manages a 6-figure portfolio, checks the platform 2-3x/week, and makes 1-2 trades per month.*

### Flaws Found and Fixes Applied

**Flaw 1: No "implied target price" — investors think in prices, not returns**

When I see "+3.2% over 90 days" I still want to know "so... what price is that?" Removing price entirely is an overcorrection. The problem wasn't showing prices — it was showing *only* an unanchored price with no context.

**Fix:** Keep `expected_return_pct` as the primary display but also compute and show `implied_target_price = current_price * (1 + expected_return_pct/100)` as secondary context. The API should return `current_price` (already planned in §5.1) so the frontend can derive this. Add to the forecast card as muted text: "+3.2% (~$145.57)".

**Flaw 2: 30-day horizon is too noisy for part-time investors**

I check 2-3x per week. A 30-day forecast will change significantly between my visits, creating anxiety and eroding trust. Part-time investors don't trade on 30-day signals — they hold for months to years.

**Fix:** Change horizons to **60 days** and **90 days** instead of 30 and 90. The 60-day horizon gives a medium-term signal without the noise of 30-day, and 90-day is the natural planning horizon for quarterly portfolio reviews. This also means both horizons have enough time for signals to play out, reducing false-alarm churn.

**Flaw 3: "55% direction accuracy" sounds terrible to users**

If I see "our model is right 55% of the time" I'd uninstall the app. Even though 55% is statistically significant and profitable over many trades, the optics are bad for a consumer product.

**Fix:** Don't expose raw direction accuracy to users. Instead, show the **confidence score** (which already factors in accuracy) and the **track record chart** (which shows predicted vs actual visually). The raw metrics stay in the admin/observability dashboard. On the user-facing side: "High confidence" / "Medium confidence" / "Low confidence" is more trustworthy than "55% accurate."

**Flaw 4: Missing "what should I do with this?" actionability**

As an investor, I see "+3.2% with 64% confidence" and think "ok... so should I buy?" The forecast alone doesn't answer the question. We already have a recommendation engine (BUY/WATCH/AVOID) — the forecast should connect to it.

**Fix:** Add a `forecast_signal` field to the API response that maps the forecast to the recommendation context:
- High confidence + bullish + signals aligned → "Supports BUY thesis"
- Low confidence or mixed → "Insufficient conviction"
- High confidence + bearish + signals aligned → "Supports caution"

This isn't a new recommendation — it's context that connects the forecast to the action the user is already considering.

**Flaw 5: SHAP feature names are technical jargon**

"macd_histogram ↑" means nothing to a part-time investor who doesn't know what MACD is.

**Fix:** The `ForecastDriver.label` field (already in the spec) must use human-readable names. Add a mapping:

```python
FEATURE_LABELS = {
    "momentum_30d": "Recent price trend",
    "momentum_90d": "3-month momentum",
    "rsi_value": "Overbought/oversold level",
    "macd_histogram": "Trend strength",
    "sma_cross": "Moving average signal",
    "bb_position": "Price vs. trading range",
    "volatility": "Price volatility",
    "sharpe_ratio": "Risk-adjusted returns",
    "stock_sentiment": "News sentiment",
    "sector_sentiment": "Sector outlook",
    "macro_sentiment": "Economic outlook",
    "signals_aligned": "Signal agreement",
    "composite_score": "Overall signal score",
    "vix_level": "Market fear index",
    "spy_momentum_30d": "Market trend",
}
```

**Flaw 6: No handling of "model says neutral but signals say strong"**

If the model predicts +0.5% (essentially flat) but 5/6 signals are aligned bullish, the forecast card should flag this discrepancy — it's useful context, not a bug. The convergence card already does this (divergence alert) but the forecast card doesn't reference it.

**Fix:** When `abs(expected_return_pct) < 1.0` AND `signals_aligned >= 4`, add a note: "Model shows flat outlook despite strong signal alignment — signals may take longer to reflect in price." This prevents the user from dismissing strong signals just because the model is conservative.

**Flaw 7: No cold-start handling for new tickers**

HOOD, VOO, VTI have no forecast models yet. The spec says "dispatch training for new tickers" but doesn't address what the frontend shows while waiting. Currently it shows "—" which looks like broken data.

**Fix:** Add a `model_status` field to the response. When status is "training" or "pending", the frontend shows a specific message: "Forecast building — requires 2 weeks of signal data" instead of "—". The backend should set this status when a ticker enters the universe but doesn't yet have a trained model.

**Flaw 8: Evaluation task needs reference price stored at forecast time**

The spec says evaluate `actual_return_pct` against `expected_return_pct`. But to compute actual return, we need the price at forecast time (the "base price"). Currently, the forecast_results table doesn't store this — it stores `target_date` but not the price on `forecast_date`.

**Fix:** Add `base_price` column (float, NOT NULL) to `forecast_results`. Set it to the ticker's closing price on `forecast_date`. Then: `actual_return_pct = (actual_price_on_target_date / base_price) - 1`. Without this column, the evaluation task would need to look up historical prices, which is fragile (data gaps, adjusted prices).

### Revised Schema (incorporating fixes)

Additional columns for `forecast_results`:

| Column | Type | Purpose |
|--------|------|---------|
| `base_price` | float, NOT NULL | Price on forecast_date, needed to compute actual_return_pct |
| `forecast_signal` | varchar(30), nullable | "supports_buy" / "supports_caution" / "insufficient_conviction" |

Additional field in `ForecastResponse`:

```python
class ForecastResponse(BaseModel):
    # ... existing fields ...
    model_status: str   # "active" | "training" | "pending" | "degraded"
```

Additional field in `ForecastHorizon`:

```python
class ForecastHorizon(BaseModel):
    # ... existing fields ...
    implied_target_price: float | None   # current_price * (1 + expected_return_pct/100)
    forecast_signal: str | None          # "supports_buy" | "supports_caution" | "insufficient_conviction"
```

### Revised Horizons

Change from [30, 90] to [60, 90]:
- `DEFAULT_HORIZONS = [60, 90]` (was [90, 180, 270] in Prophet, proposed [30, 90])
- Dashboard bulletin column header: "FCST 90D" (unchanged)
- Stock detail card: two pills (60D, 90D) instead of three (90D, 180D, 270D)

---

## 14. Final Checklist — All Areas Requiring Changes

### Database (Migration)
- [ ] Rename 4 columns in `forecast_results`
- [ ] Add 5 new columns: `confidence_score`, `direction`, `drivers`, `base_price`, `forecast_signal`
- [ ] Truncate `forecast_results` (old Prophet data is worthless)
- [ ] Mark all Prophet `model_versions` as `status='retired'`

### Backend — Python
- [ ] New: `backend/services/forecast_engine.py`
- [ ] Modify: `backend/tools/forecasting.py` (remove Prophet, keep utility functions)
- [ ] Modify: `backend/tasks/forecasting.py` (LightGBM train + predict)
- [ ] Modify: `backend/tasks/evaluation.py` (return-based evaluation + base_price)
- [ ] Modify: `backend/tasks/convergence.py` (forecast direction source)
- [ ] Modify: `backend/services/backtesting.py` (LightGBM walk-forward)
- [ ] Modify: `backend/routers/forecasts.py` (new response shapes)
- [ ] Modify: `backend/schemas/forecasts.py` (new Pydantic schemas)
- [ ] Modify: `backend/schemas/portfolio_forecast.py` (TickerComponent → return-based)
- [ ] Modify: `backend/models/forecast.py` (column renames + additions)
- [ ] Modify: `backend/config.py` (LIGHTGBM settings, remove PROPHET settings)
- [ ] Add: `lightgbm`, `shap` to `pyproject.toml`
- [ ] Modify: `backend/services/signal_convergence.py` or wherever `forecast_direction` is derived

### Frontend — TypeScript/React
- [ ] Modify: `frontend/src/types/api.ts` (ForecastHorizon, ForecastResponse, new types)
- [ ] Modify: `frontend/src/components/forecast-card.tsx` (return-based display + drivers)
- [ ] Modify: `frontend/src/components/forecast-track-record.tsx` (return chart + % axis)
- [ ] Modify: `frontend/src/app/(authenticated)/dashboard/_components/bulletin-zone.tsx` (FCST column)
- [ ] Modify: `frontend/src/components/convergence/accuracy-badge.tsx` (if MAPE semantics change)
- [ ] No change: `frontend/src/hooks/use-forecasts.ts` (endpoints unchanged)
- [ ] No change: Portfolio forecast components (BL, Monte Carlo, CVaR — already return-based)

### Tests
- [ ] Modify: 5+ backend test files (forecasting, backtest, evaluation, pipeline runner)
- [ ] Modify: Frontend test files referencing `predicted_price`
- [ ] Add: New tests for ForecastEngine (feature assembly, prediction, confidence, SHAP)
- [ ] Add: Integration test for end-to-end forecast pipeline (train → predict → evaluate)

---

## 15. Multi-Persona Expert Review

### Persona 1: ML/Quant Engineer

**Finding Q1 (CRITICAL): Feature leakage — `composite_score` is a derived feature**

`composite_score` (feature #10) is computed FROM RSI, MACD, SMA, and Sharpe — features #3, #4, #5, #8. Including both the composite and its components gives the model redundant information and inflates the apparent importance of those signals. Worse, if `composite_score` weights change over time (which they do — the weighting logic evolved across sessions), the model learns a shifting target.

**Fix:** Remove `composite_score` from the feature vector. The model can learn its own optimal weighting of the component signals — that's literally what gradient boosting does. Keep the raw components.

**Finding Q2 (HIGH): Target leakage risk in `annual_return`**

`annual_return` (feature #9) is computed from trailing 1-year price history. If we're predicting the 90-day forward return, and the target is `ln(price[t+90] / price[t])`, then `annual_return` at time `t` partially overlaps with the target at time `t-270` (the return from 270 days ago includes part of the same price move). This is subtle lookahead bias in walk-forward validation — the model can learn to "cheat" by using `annual_return` as a proxy for the target.

**Fix:** Replace `annual_return` with `momentum_180d` = `(price_today / price_180d_ago) - 1`. This gives medium-term trend without overlapping with the 90-day forward target. Also rename `momentum_30d` to `momentum_21d` (trading days) for precision.

**Finding Q3 (MEDIUM): 12 model artifacts is management complexity**

12 models (2 frameworks × 2 horizons × 3 quantiles) means 12 `ModelVersion` rows, 12 artifact files, 12 drift checks. Each weekly retrain creates 12 new rows. After 1 year that's 624 `model_versions` rows just for the ensemble.

**Fix:** Store each ensemble as a **single artifact** — a joblib bundle containing all 3 quantile models for one framework+horizon. That's 4 artifacts total (lgb_60d, lgb_90d, xgb_60d, xgb_90d) and 4 `ModelVersion` rows per retrain. The `hyperparameters` JSONB field already stores the config; extend it to store quantile-specific metrics.

**Finding Q4 (MEDIUM): Walk-forward needs a purge buffer**

The spec says "12-month expanding training window, 1-month step." But with a 90-day horizon, the last 90 days of the training window cannot have a realized target yet. If the training code doesn't explicitly exclude rows where `forward_90d_return` is NULL, the model trains on incomplete data.

**Fix:** Add an explicit purge buffer: `training_rows = all rows where date < window_end - horizon_days`. This ensures every training row has a fully realized target. Document this invariant in the `ForecastEngine.train()` docstring.

---

### Persona 2: Backend Architect

**Finding B1 (HIGH): Feature assembly is an N+3 query pattern**

`assemble_features()` for one ticker reads from 3 tables: `signal_snapshots`, `news_sentiment_daily`, `signal_convergence_daily`. For 20 tickers, that's 60 queries. For 500 tickers at scale, 1500 queries.

**Fix:** Implement bulk feature assembly: one query per table with `WHERE ticker IN (...)`, then join in Python. This is the same pattern used by `_bulk_fetch_latest_forecasts()` in convergence. The method signature should be `assemble_features_bulk(tickers: list[str], date: date, db) -> dict[str, dict]`.

**Finding B2 (HIGH): Ensemble weight storage is unspecified**

The spec says weights are "adjusted weekly by backtest performance" but doesn't say where they're stored. Config file? Database? Redis?

**Fix:** Store ensemble weights in the `model_versions.hyperparameters` JSONB field on each new model version. When predicting, read weights from the most recent active model versions. This keeps weights versioned alongside the model artifacts and avoids a separate storage mechanism. Add a `ensemble_weight` float column to `model_versions` as a first-class field instead of burying it in JSONB.

**Finding B3 (MEDIUM): `model_version_id` FK on `forecast_results` — which model does it point to?**

With an ensemble of LightGBM + XGBoost, each forecast row is produced by TWO models. The current schema has a single `model_version_id` FK. Which model does it reference?

**Fix:** Point `model_version_id` to the **LightGBM model** (primary model in the ensemble). Add `ensemble_model_ids` as a JSONB array field listing all model version UUIDs that contributed to this prediction. This preserves full lineage without requiring a junction table.

**Finding B4 (LOW): Migration renames on TimescaleDB hypertable**

`ALTER COLUMN RENAME` on a TimescaleDB hypertable works but may require special handling for compressed chunks. If `forecast_results` has compression enabled, the rename needs to decompress first.

**Fix:** Check if compression is enabled on `forecast_results` before the migration. If so, decompress → rename → recompress. Since we're truncating anyway, just drop compression policy → truncate → rename → re-enable compression.

---

### Persona 3: Data/ML Ops

**Finding O1 (HIGH): No model registry or A/B testing path**

The spec says "weights adjusted weekly by backtest performance" but doesn't define how to compare the old ensemble against the new one. If a weekly retrain produces a worse model, do we auto-deploy it?

**Fix:** Add a **champion/challenger** pattern:
1. Weekly retrain produces a new "challenger" model
2. Run challenger on the same backtest window as the current "champion"
3. If challenger beats champion on direction accuracy by ≥ 1% OR reduces CI width by ≥ 5%, promote to champion
4. Otherwise, keep the current champion and log the comparison
5. Store comparison results in `model_versions.metrics` JSONB

This prevents model degradation from auto-deploying a bad retrain.

**Finding O2 (MEDIUM): SHAP computation at prediction time is wasteful**

Computing SHAP for every ticker on every nightly run adds latency. For 500 tickers, SHAP could take 30-60 seconds (tree SHAP is O(TLD) per sample where T=trees, L=leaves, D=depth).

**Fix:** Pre-compute SHAP on a per-model basis during training (global feature importance), then at prediction time only compute SHAP for the **top 10 tickers by portfolio weight or watchlist priority**. For other tickers, use the global feature importance as a proxy. This reduces SHAP calls from N_tickers to 10.

**Finding O3 (MEDIUM): No monitoring for feature drift**

If the signal pipeline changes (e.g., RSI calculation tweaked, sentiment model swapped), the forecast model's features shift silently. This is a major source of model degradation in production ML systems.

**Fix:** Add a nightly feature distribution check: compute mean/std of each feature across all tickers, compare to the training-time distribution. If any feature's mean shifts by > 2 standard deviations, emit a WARNING-level obs event and flag the model as potentially stale. This is a lightweight statistical process control — not a full data quality framework, but catches the most common drift scenarios.

---

### Persona 4: Frontend/UX Engineer

**Finding U1 (HIGH): Forecast card redesign needs loading/error/empty states**

The spec defines the happy path (two pills with data) but doesn't specify:
- Loading state (while queries in-flight)
- Error state (API returns 500)
- Empty state (model_status = "pending" or "training")
- Degraded state (model_status = "degraded")

**Fix:** Define all four states:
- **Loading**: Same skeleton as current (2 pill placeholders instead of 3)
- **Error**: "Forecast unavailable" with retry button (same pattern as other cards)
- **Pending**: "Forecast building — data needs 2+ weeks of signals" with a subtle progress indicator
- **Degraded**: Show forecast with an amber "Low confidence" badge + tooltip: "Model accuracy has declined — predictions may be less reliable"

**Finding U2 (MEDIUM): Column header "FCST 90D" doesn't communicate the change**

Users accustomed to seeing "$317" will suddenly see "+3.2%" in the same column. No explanation of what changed or what the number means.

**Fix:** Rename column header to "90D Outlook" (more approachable than "FCST 90D"). Add a tooltip on the header: "Expected return over the next 90 days based on signal analysis." On first visit after the change, consider a one-time tooltip/banner: "Forecasts now show expected returns instead of price targets for better accuracy."

**Finding U3 (MEDIUM): Driver chips need a tooltip for context**

Showing "Trend strength ↑" as a chip is good, but users will ask "what does that mean for me?" Each chip should have a hover tooltip explaining the signal in plain English.

**Fix:** Add tooltips to driver chips:
- "Trend strength ↑" → "MACD histogram is positive, indicating upward momentum is strengthening"
- "News sentiment ↑" → "Recent news coverage for this stock is predominantly positive"
- "Market fear ↓" → "VIX is elevated, indicating higher market uncertainty"

---

### Summary of Review Findings

| # | Persona | Severity | Finding | Status |
|---|---------|----------|---------|--------|
| Q1 | ML/Quant | CRITICAL | `composite_score` is derived from other features — remove | Must fix |
| Q2 | ML/Quant | HIGH | `annual_return` has subtle target leakage — replace with `momentum_180d` | Must fix |
| Q3 | ML/Quant | MEDIUM | 12 artifacts → bundle to 4 | Should fix |
| Q4 | ML/Quant | MEDIUM | Walk-forward needs purge buffer for unrealized targets | Must fix |
| B1 | Backend | HIGH | N+3 query pattern → bulk feature assembly | Must fix |
| B2 | Backend | HIGH | Ensemble weight storage unspecified → `model_versions` column | Must fix |
| B3 | Backend | MEDIUM | `model_version_id` FK ambiguity → primary model + JSONB lineage | Should fix |
| B4 | Backend | LOW | TimescaleDB rename + compression → decompress first | Check before migration |
| O1 | ML Ops | HIGH | No champion/challenger → add promotion gate | Must fix |
| O2 | ML Ops | MEDIUM | SHAP for all tickers is slow → top-10 only + global fallback | Should fix |
| O3 | ML Ops | MEDIUM | No feature drift monitoring → nightly distribution check | Should fix |
| U1 | Frontend | HIGH | Missing loading/error/empty/degraded states | Must fix |
| U2 | Frontend | MEDIUM | Column header doesn't communicate the change | Should fix |
| U3 | Frontend | MEDIUM | Driver chips need tooltips | Should fix |

### Revised Feature Vector (post-review)

Remove `composite_score` (Q1) and replace `annual_return` (Q2):

| # | Feature | Source | Type |
|---|---------|--------|------|
| 1 | `momentum_21d` | 21-trading-day return | float |
| 2 | `momentum_63d` | 63-trading-day (~3 month) return | float |
| 3 | `momentum_126d` | 126-trading-day (~6 month) return | float |
| 4 | `rsi_value` | `SignalSnapshot.rsi_value` | float (0-100) |
| 5 | `macd_histogram` | `SignalSnapshot.macd_histogram` | float |
| 6 | `sma_cross` | Encoded SMA signal | int (0-2) |
| 7 | `bb_position` | Encoded Bollinger position | int (0-2) |
| 8 | `volatility` | `SignalSnapshot.volatility` | float |
| 9 | `sharpe_ratio` | `SignalSnapshot.sharpe_ratio` | float |
| 10 | `stock_sentiment` | `NewsSentimentDaily.stock_sentiment` | float (-1 to 1) |
| 11 | `sector_sentiment` | `NewsSentimentDaily.sector_sentiment` | float (-1 to 1) |
| 12 | `macro_sentiment` | `NewsSentimentDaily.macro_sentiment` | float (-1 to 1) |
| 13 | `sentiment_confidence` | `NewsSentimentDaily.confidence` | float (0-1) |
| 14 | `signals_aligned` | `SignalConvergenceDaily.signals_aligned` | int (0-6) |
| 15 | `convergence_label` | Encoded convergence | int (-2 to 2) |
| 16 | `vix_level` | VIX close | float |
| 17 | `spy_momentum_21d` | SPY 21-trading-day return | float |

17 features (was 18). Removed `composite_score`, replaced `annual_return` with `momentum_126d`, aligned momentum windows to trading days.

---

## 16. Feature Availability & Sentiment Cold-Start Strategy

### The Problem

We have 10 years of price data but only 3 days of signal snapshots and sentiment scores. News sentiment cannot be backfilled — old news is priced in and LLM-scoring 2-year-old headlines today would produce unreliable results.

### Industry Approach

Quant teams treat new data signals as **incremental additions**, not prerequisites. LightGBM and XGBoost both handle NaN/missing values natively — they learn a "default branch direction" when a feature is absent. This means we can include sentiment columns from day 1, set them to NaN for historical rows, and the model learns two patterns:
- "When sentiment is available AND bullish, boost return prediction"
- "When sentiment is missing, rely on technical signals only"

As sentiment data accumulates through our nightly pipeline, the model's feature importance for sentiment naturally grows during weekly retrains.

### Three-Phase Feature Rollout

**Phase 1 — Launch (Day 1): 11 Technical Features (backfilled from price data)**

All computable retroactively from `stock_prices` using deterministic math:

| # | Feature | Backfill Method |
|---|---------|----------------|
| 1 | `momentum_21d` | `price[t] / price[t-21] - 1` |
| 2 | `momentum_63d` | `price[t] / price[t-63] - 1` |
| 3 | `momentum_126d` | `price[t] / price[t-126] - 1` |
| 4 | `rsi_value` | 14-day RSI from closing prices |
| 5 | `macd_histogram` | MACD(12,26,9) histogram |
| 6 | `sma_cross` | Compare price to SMA-50 and SMA-200 |
| 7 | `bb_position` | 20-day Bollinger Band position |
| 8 | `volatility` | 30-day annualized std dev of returns |
| 9 | `sharpe_ratio` | 30-day return / volatility |
| 10 | `vix_level` | ^VIX closing price (already in stock_prices) |
| 11 | `spy_momentum_21d` | SPY 21-day return (already in stock_prices) |

Estimated backfill: ~500 tickers × 500 trading days = **250K rows**, ~10 minutes compute time using vectorized pandas-ta.

Sentiment features (#10-13 in original spec) are included as columns but set to NaN for all historical rows. The model learns technical-only patterns from this data.

**Phase 2 — Accumulation (Week 2+): Sentiment Features Go Live**

Our nightly pipeline scores sentiment daily. As data accumulates:
- After 7 days: sentiment features have values for the most recent week
- After 30 days: enough for the model to start learning sentiment patterns
- After 90 days: sentiment becomes a meaningful feature

Each weekly retrain naturally incorporates the new sentiment data. No manual intervention needed.

**Stale sentiment rule:** If a ticker's most recent sentiment reading is >7 days old, set features to NaN. Old news is noise, not signal.

**Phase 3 — Maturity (Month 2+): Convergence as Lagged Feature**

`signals_aligned` and `convergence_label` have a circular dependency — they consume forecast direction, which the forecast model produces. Break the circularity by using **lagged convergence**: yesterday's convergence state predicts today's return.

After 60 days of forecast history, add two lagged features:
- `lag1d_signals_aligned`: previous day's signal alignment count
- `lag1d_convergence_label`: previous day's convergence label

### Backfill Implementation (PR0)

The backfill is a one-time batch job that computes technical indicators from price history. It does NOT use the existing `compute_signals()` function (which writes to `signal_snapshots` and has side effects). Instead, a standalone script:

1. Load all price data for all tickers from `stock_prices`
2. Group by ticker, compute indicators using pandas-ta (vectorized, fast)
3. Store results in a new `historical_features` table (or append to `signal_snapshots` with a `source='backfill'` marker)
4. The `ForecastEngine.assemble_features()` method reads from this table for training, and from live `signal_snapshots` for prediction

This keeps the backfill isolated from the live pipeline and avoids contaminating production signal data.

### What NOT to Backfill

| Data | Why Not |
|------|---------|
| News sentiment | Old news is priced in — LLM scoring stale headlines is unreliable |
| Convergence signals | Circular dependency with forecast direction |
| Composite score | Removed from feature vector (review finding Q1) |
| Annual return | Removed — replaced by momentum_126d (review finding Q2) |
