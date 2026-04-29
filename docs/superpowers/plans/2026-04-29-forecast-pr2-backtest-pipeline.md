# KAN-551 PR2: Backtest Validation + Daily Pipeline + Champion/Challenger

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Prophet-based backtesting with ForecastEngine walk-forward, add daily feature population, champion/challenger model promotion, and feature drift monitoring.

**Architecture:** BacktestEngine is rewritten to use historical_features + ForecastEngine.train() for per-window walk-forward. A new nightly Celery task computes today's feature row per ticker. Weekly retrain gains a champion/challenger gate. A separate nightly task checks feature distribution drift.

**Tech Stack:** Python, SQLAlchemy async, Celery Beat, LightGBM/XGBoost (via ForecastEngine), yfinance (VIX), pandas

**Baseline:** 2677 unit tests (0 failures), Alembic head: 042 (`286eaa38beab`)

---

## Fact Sheet (grepped 2026-04-29)

### Callers of BacktestEngine / BacktestMetrics

| Import site | What it uses |
|---|---|
| `backend/tasks/forecasting.py:17` | `from backend.services.backtesting import BacktestEngine` |
| `backend/tasks/forecasting.py:470` | `engine = BacktestEngine()` then `engine.run_walk_forward(tkr, db, horizon_days=...)` |
| `tests/unit/services/test_backtest_engine.py:8` | `BacktestEngine, WindowSpec` — pure unit tests on windows + metrics |
| `tests/api/test_backtest_task.py:21` | `BacktestMetrics` — mocks `BacktestEngine.run_walk_forward` |
| `tests/api/test_backtest_engine_walk_forward.py:15` | `BacktestEngine, BacktestMetrics` — integration tests with real DB |

### BacktestMetrics fields (unchanged contract)

```python
@dataclass
class BacktestMetrics:
    mape: float
    mae: float
    rmse: float
    direction_accuracy: float
    ci_containment: float
    ci_bias: str  # "above", "below", "balanced"
    avg_interval_width: float
    num_windows: int
    per_window_results: list[dict] = field(default_factory=list)
```

### BacktestRun persistence in `_run_backtest_async` (lines 492-546)

Consumer reads: `metrics.mape`, `metrics.mae`, `metrics.rmse`, `metrics.direction_accuracy`, `metrics.ci_containment`, `metrics.num_windows`. Persists via `pg_insert(BacktestRun)`. **No change needed to consumer** — we preserve the same BacktestMetrics interface.

### ForecastEngine.train() return contract

```python
def train(self, features_df, horizon_days, weights=None) -> tuple[bytes, dict]:
    # returns (artifact_bytes, {"direction_accuracy": float, "mean_absolute_error": float, "ci_containment": float})
```

### ForecastEngine.predict() return contract

```python
def predict(self, features, model_artifact, weights=None, compute_shap=True) -> dict:
    # returns {"expected_return_pct", "return_lower_pct", "return_upper_pct", "direction", "confidence", ...}
```

### Beat schedule time slots in use

- 21:30 — nightly pipeline chain (prices + signals)
- 2:00 Sun — model retrain + institutional holders
- 3:00-3:45 — audit purges + forecast/news retention
- 4:00-9:00 — DQ scan + retention purges

**Available slots for new tasks:** 22:00-23:59 (after nightly pipeline), 1:00-1:59 (before retrain).

### Config settings

```python
BACKTEST_MIN_TRAIN_DAYS: int = 365
BACKTEST_STEP_DAYS: int = 30
BACKTEST_MIN_WINDOWS: int = 12
DEFAULT_FORECAST_HORIZONS: list[int] = [60, 90]
FORECAST_ENSEMBLE_WEIGHTS: dict = {"lightgbm": 0.5, "xgboost": 0.5}
BACKTEST_ENABLED: bool = True
```

### Bug found: `evaluation.py:235` filters `model_type == "prophet"`

`_check_drift_async` only checks Prophet models. Must update to also check LightGBM.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `backend/services/backtesting.py` | **Rewrite** | Replace Prophet walk-forward with ForecastEngine-based walk-forward. Keep WindowSpec, BacktestMetrics, metric helper methods. Remove _fit_and_predict_sync. |
| `backend/tasks/forecasting.py` | **Modify** | Add `populate_daily_features_task`. Add champion/challenger gate in `_model_retrain_all_async`. |
| `backend/tasks/evaluation.py` | **Modify** | Fix prophet-only filter in `_check_drift_async`. Add `_check_feature_drift_async` + `check_feature_drift_task`. |
| `backend/tasks/__init__.py` | **Modify** | Wire 2 new beat schedule entries: daily feature population + nightly feature drift check. |
| `backend/config.py` | **Modify** | Add `FEATURE_DRIFT_ENABLED`, `CHAMPION_CHALLENGER_ENABLED`, `DAILY_FEATURES_ENABLED` kill switches. Add `CHAMPION_DIRECTION_THRESHOLD`, `CHAMPION_CI_THRESHOLD`. |
| `tests/unit/services/test_backtest_engine.py` | **Modify** | Update imports, add tests for new walk-forward approach. Preserve existing window + metric tests. |
| `tests/unit/tasks/test_daily_features.py` | **Create** | Tests for daily feature population task. |
| `tests/unit/tasks/test_champion_challenger.py` | **Create** | Tests for champion/challenger promotion gate. |
| `tests/unit/tasks/test_feature_drift.py` | **Create** | Tests for feature drift monitoring. |

---

## Task 1: Add config settings

**Files:**
- Modify: `backend/config.py:144-147`

- [ ] **Step 1: Add kill switches and thresholds to config**

In `backend/config.py`, after the existing `BACKTEST_ENABLED` line (144), add:

```python
    # --- Daily Feature Population ---
    DAILY_FEATURES_ENABLED: bool = True
    # --- Champion/Challenger ---
    CHAMPION_CHALLENGER_ENABLED: bool = True
    CHAMPION_DIRECTION_THRESHOLD: float = 0.01  # challenger must beat by ≥1%
    CHAMPION_CI_THRESHOLD: float = 0.05  # challenger CI width must improve by ≥5%
    # --- Feature Drift ---
    FEATURE_DRIFT_ENABLED: bool = True
    FEATURE_DRIFT_SIGMA_THRESHOLD: float = 2.0  # flag if mean shifts >2σ
```

- [ ] **Step 2: Verify config loads**

Run: `uv run python -c "from backend.config import settings; print(settings.CHAMPION_DIRECTION_THRESHOLD)"`
Expected: `0.01`

- [ ] **Step 3: Commit**

```bash
git add backend/config.py
git commit -m "feat(config): add kill switches for daily features, champion/challenger, feature drift"
```

---

## Task 2: Rewrite BacktestEngine to use ForecastEngine

**Files:**
- Modify: `backend/services/backtesting.py`
- Test: `tests/unit/services/test_backtest_engine.py`

This is the core change. The new `run_walk_forward` loads historical_features from DB, generates expanding windows by date, calls `ForecastEngine.train()` per window on the training slice, then uses `ForecastEngine.predict()` on each ticker's latest feature row within the test window to compute metrics against actual returns.

### Key design decisions:
- **Keep** `WindowSpec`, `BacktestMetrics`, `_generate_expanding_windows`, all `_compute_*` metric methods, `_safe_float`
- **Remove** `_fit_and_predict_sync` (Prophet-specific)
- **New** `_train_and_predict_window` — per-window: train ForecastEngine on features up to window.train_end, predict for features at window.test_date, compare predicted return vs actual return
- The backtest operates on **returns** (log returns from historical_features), not absolute prices. This aligns with ForecastEngine's target column (`forward_return_60d` / `forward_return_90d`).
- Direction accuracy: predicted return sign vs actual return sign (simpler than price-based: no need for base_price)
- CI containment: actual return within [q0.1, q0.9] predicted interval

- [ ] **Step 1: Write failing test for new run_walk_forward**

In `tests/unit/services/test_backtest_engine.py`, add a new test class after the existing ones:

```python
class TestRunWalkForwardEngine:
    """Tests for ForecastEngine-based walk-forward."""

    @pytest.mark.asyncio
    async def test_run_walk_forward_returns_backtest_metrics(self):
        """run_walk_forward returns BacktestMetrics with correct fields."""
        from unittest.mock import AsyncMock, MagicMock, patch

        import numpy as np
        import pandas as pd

        from backend.services.backtesting import BacktestEngine, BacktestMetrics

        engine = BacktestEngine()

        # Build fake historical_features rows (2 years of daily data, 2 tickers)
        dates = pd.date_range("2023-01-01", periods=600, freq="D")
        rng = np.random.default_rng(42)
        rows = []
        for d in dates:
            for tkr in ["AAPL", "MSFT"]:
                rows.append(MagicMock(
                    date=d.date(),
                    ticker=tkr,
                    momentum_21d=rng.normal(0, 0.1),
                    momentum_63d=rng.normal(0, 0.1),
                    momentum_126d=rng.normal(0, 0.1),
                    rsi_value=rng.uniform(30, 70),
                    macd_histogram=rng.normal(0, 0.5),
                    sma_cross=rng.choice([0, 1, 2]),
                    bb_position=rng.choice([0, 1, 2]),
                    volatility=rng.uniform(0.1, 0.4),
                    sharpe_ratio=rng.normal(0.5, 0.3),
                    vix_level=rng.uniform(12, 30),
                    spy_momentum_21d=rng.normal(0, 0.05),
                    stock_sentiment=None,
                    sector_sentiment=None,
                    macro_sentiment=None,
                    sentiment_confidence=None,
                    signals_aligned=None,
                    convergence_label=None,
                    forward_return_60d=rng.normal(0, 0.05) if d.date() < dates[-60].date() else None,
                    forward_return_90d=rng.normal(0, 0.05) if d.date() < dates[-90].date() else None,
                ))

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = rows
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Mock ForecastEngine.train to return fake artifact + metrics
        fake_artifact = b"fake_model_bytes"
        fake_train_metrics = {
            "direction_accuracy": 0.58,
            "mean_absolute_error": 0.03,
            "ci_containment": 0.80,
        }

        # Mock ForecastEngine.predict to return fake predictions
        fake_prediction = {
            "expected_return_pct": 2.5,
            "return_lower_pct": -3.0,
            "return_upper_pct": 8.0,
            "direction": "UP",
            "confidence": 0.65,
        }

        with (
            patch("backend.services.backtesting.ForecastEngine") as MockEngine,
            patch("backend.services.backtesting.asyncio.to_thread") as mock_to_thread,
        ):
            mock_engine_instance = MagicMock()
            MockEngine.return_value = mock_engine_instance

            # to_thread calls: train returns (artifact, metrics), predict returns dict
            async def fake_to_thread(fn, *args, **kwargs):
                if fn == mock_engine_instance.train:
                    return (fake_artifact, fake_train_metrics)
                elif fn == mock_engine_instance.predict:
                    return fake_prediction
                return fn(*args, **kwargs)

            mock_to_thread.side_effect = fake_to_thread

            metrics = await engine.run_walk_forward("AAPL", mock_db, horizon_days=60)

        assert isinstance(metrics, BacktestMetrics)
        assert metrics.num_windows > 0
        assert 0.0 <= metrics.direction_accuracy <= 1.0
        assert 0.0 <= metrics.ci_containment <= 1.0
        assert metrics.mape >= 0.0

    @pytest.mark.asyncio
    async def test_run_walk_forward_no_data_returns_empty_metrics(self):
        """run_walk_forward with no historical features returns zero metrics."""
        from unittest.mock import AsyncMock, MagicMock

        from backend.services.backtesting import BacktestEngine

        engine = BacktestEngine()
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        metrics = await engine.run_walk_forward("AAPL", mock_db, horizon_days=60)

        assert metrics.num_windows == 0
        assert metrics.direction_accuracy == 0.0

    @pytest.mark.asyncio
    async def test_run_walk_forward_insufficient_data_returns_empty(self):
        """run_walk_forward with too little data for even one window returns empty."""
        from unittest.mock import AsyncMock, MagicMock

        import numpy as np
        import pandas as pd

        from backend.services.backtesting import BacktestEngine

        engine = BacktestEngine()

        # Only 100 days of data — not enough for min_train_days=365
        dates = pd.date_range("2024-01-01", periods=100, freq="D")
        rng = np.random.default_rng(42)
        rows = []
        for d in dates:
            rows.append(MagicMock(
                date=d.date(),
                ticker="AAPL",
                momentum_21d=rng.normal(0, 0.1),
                momentum_63d=rng.normal(0, 0.1),
                momentum_126d=rng.normal(0, 0.1),
                rsi_value=50.0,
                macd_histogram=0.0,
                sma_cross=1,
                bb_position=1,
                volatility=0.2,
                sharpe_ratio=0.5,
                vix_level=18.0,
                spy_momentum_21d=0.01,
                stock_sentiment=None,
                sector_sentiment=None,
                macro_sentiment=None,
                sentiment_confidence=None,
                signals_aligned=None,
                convergence_label=None,
                forward_return_60d=0.02,
                forward_return_90d=0.03,
            ))

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = rows
        mock_db.execute = AsyncMock(return_value=mock_result)

        metrics = await engine.run_walk_forward("AAPL", mock_db, horizon_days=60)
        assert metrics.num_windows == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/services/test_backtest_engine.py::TestRunWalkForwardEngine -v`
Expected: FAIL — `ForecastEngine` not imported in backtesting.py yet

- [ ] **Step 3: Rewrite backtesting.py**

Replace the entire file content. **Keep**: `WindowSpec`, `BacktestMetrics`, `_generate_expanding_windows`, `_safe_float`, `_compute_mape`, `_compute_mae`, `_compute_rmse`, `_compute_direction_accuracy`, `_compute_ci_containment`, `_compute_ci_bias`. **Remove**: `_fit_and_predict_sync`. **Add**: new `run_walk_forward` implementation.

New imports (replace old ones):

```python
"""Walk-forward backtesting engine for ForecastEngine model validation."""

import asyncio
import logging
import math
from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.historical_feature import HistoricalFeature
from backend.services.forecast_engine import FEATURE_NAMES, ForecastEngine

logger = logging.getLogger(__name__)
```

Remove the old `StockPrice` and `sentiment_regressors` imports.

New `run_walk_forward` method body (replaces lines 239-466):

```python
    async def run_walk_forward(
        self,
        ticker: str,
        db: AsyncSession,
        horizon_days: int = 60,
        min_train_days: int = 365,
        step_days: int = 30,
    ) -> "BacktestMetrics":
        """Run walk-forward validation for a ticker using ForecastEngine.

        Loads historical_features for ALL tickers (cross-ticker training),
        generates expanding windows by date, trains a ForecastEngine per
        window, and predicts the target ticker's forward return at each
        test_date.

        Args:
            ticker: Stock ticker to evaluate predictions for.
            db: Async database session.
            horizon_days: Days ahead to forecast (60 or 90).
            min_train_days: Minimum training period in days.
            step_days: Days to advance between walk-forward windows.

        Returns:
            BacktestMetrics aggregating all windows.
        """
        target_col = f"forward_return_{horizon_days}d"

        # ── 1. Load all historical features (cross-ticker) ──────────────
        result = await db.execute(
            select(HistoricalFeature).order_by(HistoricalFeature.date)
        )
        all_rows = result.scalars().all()

        if not all_rows:
            logger.warning("run_walk_forward: no historical features found")
            return self._empty_metrics()

        # Build DataFrame from ORM rows
        records = []
        for row in all_rows:
            record: dict = {"date": row.date, "ticker": row.ticker}
            for name in FEATURE_NAMES:
                record[name] = getattr(row, name, None)
            record["forward_return_60d"] = row.forward_return_60d
            record["forward_return_90d"] = row.forward_return_90d
            records.append(record)
        features_df = pd.DataFrame(records)

        # Filter to rows that have the target return
        features_df = features_df.dropna(subset=[target_col])
        if features_df.empty:
            logger.warning(
                "run_walk_forward: no rows with %s for any ticker", target_col
            )
            return self._empty_metrics()

        # Get date range for the target ticker
        ticker_dates = sorted(
            features_df.loc[features_df["ticker"] == ticker, "date"].unique()
        )
        if not ticker_dates:
            logger.warning(
                "run_walk_forward: ticker %s not found in historical features", ticker
            )
            return self._empty_metrics()

        data_start = features_df["date"].min()
        data_end = features_df["date"].max()

        # ── 2. Generate windows ─────────────────────────────────────────
        windows = self._generate_expanding_windows(
            data_start=data_start,
            data_end=data_end,
            min_train_days=min_train_days,
            step_days=step_days,
            horizon_days=horizon_days,
        )

        if not windows:
            logger.info(
                "run_walk_forward: insufficient data for %s (%d days, need %d + %d)",
                ticker,
                (data_end - data_start).days,
                min_train_days,
                horizon_days,
            )
            return self._empty_metrics()

        # ── 3. Walk through windows ─────────────────────────────────────
        engine = ForecastEngine()
        actuals: list[float] = []
        predicted: list[float] = []
        lowers: list[float] = []
        uppers: list[float] = []

        for window in windows:
            # Training slice: all tickers, dates up to train_end
            # Purge buffer: exclude rows where the target would be unknown
            # (date must be < train_end - horizon_days for the target to be realised)
            train_cutoff = window.train_end - timedelta(days=horizon_days)
            train_slice = features_df[features_df["date"] <= train_cutoff]
            if len(train_slice) < 10:
                continue

            # Test: get target ticker's feature row at test_date
            test_rows = features_df[
                (features_df["ticker"] == ticker)
                & (features_df["date"] == window.test_date)
            ]
            if test_rows.empty:
                # Try nearest date within ±5 days
                for offset in range(1, 6):
                    for delta in [timedelta(days=offset), timedelta(days=-offset)]:
                        candidate = window.test_date + delta
                        test_rows = features_df[
                            (features_df["ticker"] == ticker)
                            & (features_df["date"] == candidate)
                        ]
                        if not test_rows.empty:
                            break
                    if not test_rows.empty:
                        break
            if test_rows.empty:
                continue

            test_row = test_rows.iloc[0]
            actual_return = test_row[target_col]
            if actual_return is None or (isinstance(actual_return, float) and math.isnan(actual_return)):
                continue

            # Train model on the training slice
            try:
                artifact_bytes, _train_metrics = await asyncio.to_thread(
                    engine.train, train_slice, horizon_days
                )
            except Exception:
                logger.exception(
                    "ForecastEngine train failed for window %s–%s; skipping",
                    window.train_start,
                    window.train_end,
                )
                continue

            # Predict for the test row
            feature_dict = {
                name: test_row.get(name) for name in FEATURE_NAMES
            }
            try:
                pred = await asyncio.to_thread(
                    engine.predict, feature_dict, artifact_bytes, None, False
                )
            except Exception:
                logger.exception(
                    "ForecastEngine predict failed for %s at %s; skipping",
                    ticker,
                    window.test_date,
                )
                continue

            # pred returns percentages; actual_return is log return
            # Convert predicted return from percentage to log return for comparison
            pred_return = math.log(1.0 + pred["expected_return_pct"] / 100.0)
            pred_lower = math.log(1.0 + pred["return_lower_pct"] / 100.0)
            pred_upper = math.log(1.0 + pred["return_upper_pct"] / 100.0)

            actuals.append(float(actual_return))
            predicted.append(pred_return)
            lowers.append(pred_lower)
            uppers.append(pred_upper)

        # ── 4. Aggregate metrics ────────────────────────────────────────
        if not actuals:
            return self._empty_metrics()

        # For direction accuracy with returns: base is 0 (positive = up, negative = down)
        base_prices = [0.0] * len(actuals)
        avg_width = (
            sum(hi - lo for lo, hi in zip(lowers, uppers)) / len(lowers)
            if lowers
            else 0.0
        )

        return BacktestMetrics(
            mape=self._compute_mape(actuals, predicted),
            mae=self._compute_mae(actuals, predicted),
            rmse=self._compute_rmse(actuals, predicted),
            direction_accuracy=self._compute_direction_accuracy(
                base_prices, actuals, predicted
            ),
            ci_containment=self._compute_ci_containment(actuals, lowers, uppers),
            ci_bias=self._compute_ci_bias(actuals, predicted),
            avg_interval_width=self._safe_float(avg_width),
            num_windows=len(actuals),
        )

    def _empty_metrics(self) -> "BacktestMetrics":
        """Return zeroed BacktestMetrics for no-data cases."""
        return BacktestMetrics(
            mape=0.0,
            mae=0.0,
            rmse=0.0,
            direction_accuracy=0.0,
            ci_containment=0.0,
            ci_bias="balanced",
            avg_interval_width=0.0,
            num_windows=0,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/services/test_backtest_engine.py -v`
Expected: All existing window/metric tests PASS (unchanged), new walk-forward tests PASS.

- [ ] **Step 5: Run full unit suite to check for regressions**

Run: `uv run pytest tests/unit/ -q --tb=short`
Expected: 2677+ passed, 0 failures

- [ ] **Step 6: Commit**

```bash
git add backend/services/backtesting.py tests/unit/services/test_backtest_engine.py
git commit -m "feat(backtesting): replace Prophet walk-forward with ForecastEngine

BacktestEngine.run_walk_forward now:
- Loads historical_features (cross-ticker)
- Generates expanding windows by date
- Trains ForecastEngine per window with purge buffer
- Predicts target ticker's return at test_date
- Computes same metrics (MAPE, direction accuracy, CI containment)

Removes Prophet dependency from backtesting entirely."
```

---

## Task 3: Daily Feature Population Task

**Files:**
- Modify: `backend/tasks/forecasting.py`
- Modify: `backend/tasks/__init__.py`
- Create: `tests/unit/tasks/test_daily_features.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/tasks/test_daily_features.py`:

```python
"""Tests for daily feature population task."""

import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pandas as pd
import pytest


class TestPopulateDailyFeatures:
    """Tests for _populate_daily_features_async."""

    @pytest.mark.asyncio
    async def test_populates_features_for_all_tickers(self):
        """Task computes and upserts feature rows for each ticker."""
        from backend.tasks.forecasting import _populate_daily_features_async

        mock_tickers = ["AAPL", "MSFT"]
        run_id = uuid.uuid4()

        # Build fake price data (250+ days needed for SMA warmup)
        dates = pd.date_range("2024-01-01", periods=300, freq="D")
        rng = np.random.default_rng(42)

        async def mock_execute(stmt):
            result = MagicMock()
            # Detect which query this is by checking the statement
            return result

        with (
            patch("backend.tasks.forecasting._db") as mock_db_module,
            patch("backend.tasks.forecasting.get_all_referenced_tickers") as mock_get_tickers,
            patch("backend.tasks.forecasting._fetch_ticker_prices") as mock_prices,
            patch("backend.tasks.forecasting._fetch_vix_and_spy") as mock_vix_spy,
            patch("backend.tasks.forecasting.build_feature_dataframe") as mock_build,
            patch("backend.tasks.forecasting._upsert_daily_feature_row") as mock_upsert,
        ):
            mock_get_tickers.return_value = mock_tickers
            # Fake price series
            fake_closes = pd.Series(
                rng.normal(150, 5, 300), index=dates, name="close"
            )
            mock_prices.return_value = fake_closes
            # Fake VIX + SPY
            fake_vix = pd.Series(rng.uniform(12, 25, 300), index=dates)
            fake_spy = pd.Series(rng.normal(450, 10, 300), index=dates)
            mock_vix_spy.return_value = (fake_vix, fake_spy)
            # Fake feature DataFrame
            mock_build.return_value = pd.DataFrame(
                {"momentum_21d": [0.05], "rsi_value": [55.0]},
                index=pd.DatetimeIndex([dates[-1]]),
            )

            mock_session = AsyncMock()
            mock_db_module.async_session_factory.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_db_module.async_session_factory.return_value.__aexit__ = AsyncMock(
                return_value=False
            )

            result = await _populate_daily_features_async(run_id=run_id)

        assert result["status"] == "ok"
        assert result["populated"] == 2
        assert mock_upsert.call_count == 2

    @pytest.mark.asyncio
    async def test_disabled_via_config(self):
        """Task returns early when DAILY_FEATURES_ENABLED=False."""
        from backend.tasks.forecasting import _populate_daily_features_async

        with patch("backend.tasks.forecasting.settings") as mock_settings:
            mock_settings.DAILY_FEATURES_ENABLED = False
            result = await _populate_daily_features_async(run_id=uuid.uuid4())

        assert result["status"] == "disabled"

    @pytest.mark.asyncio
    async def test_handles_ticker_failure_gracefully(self):
        """Task continues processing remaining tickers when one fails."""
        from backend.tasks.forecasting import _populate_daily_features_async

        with (
            patch("backend.tasks.forecasting._db") as mock_db_module,
            patch("backend.tasks.forecasting.get_all_referenced_tickers") as mock_get_tickers,
            patch("backend.tasks.forecasting._fetch_ticker_prices") as mock_prices,
            patch("backend.tasks.forecasting._fetch_vix_and_spy") as mock_vix_spy,
        ):
            mock_get_tickers.return_value = ["AAPL", "MSFT"]
            mock_prices.side_effect = [RuntimeError("no data"), pd.Series(dtype=float)]

            fake_vix = pd.Series(dtype=float)
            fake_spy = pd.Series(dtype=float)
            mock_vix_spy.return_value = (fake_vix, fake_spy)

            mock_session = AsyncMock()
            mock_db_module.async_session_factory.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_db_module.async_session_factory.return_value.__aexit__ = AsyncMock(
                return_value=False
            )

            result = await _populate_daily_features_async(run_id=uuid.uuid4())

        assert result["failed"] >= 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/tasks/test_daily_features.py -v`
Expected: FAIL — `_populate_daily_features_async` does not exist yet

- [ ] **Step 3: Implement helper functions and task in tasks/forecasting.py**

Add these functions after the existing imports at the top of `backend/tasks/forecasting.py`. Add new imports:

```python
from backend.services.feature_engineering import build_feature_dataframe
```

Add helper functions before `_model_retrain_all_async`:

```python
async def _fetch_ticker_prices(ticker: str, db: AsyncSession) -> pd.Series:
    """Load closing prices for a ticker from stock_prices.

    Returns:
        Series of close prices with DatetimeIndex (UTC).
    """
    from backend.models.price import StockPrice

    result = await db.execute(
        select(StockPrice.time, StockPrice.close)
        .where(StockPrice.ticker == ticker)
        .order_by(StockPrice.time)
    )
    rows = result.all()
    if not rows:
        raise ValueError(f"No price data for {ticker}")
    dates = pd.DatetimeIndex([r.time for r in rows], tz="UTC")
    closes = pd.Series([float(r.close) for r in rows], index=dates, name="close")
    return closes


async def _fetch_vix_and_spy(db: AsyncSession) -> tuple[pd.Series, pd.Series]:
    """Load VIX + SPY closing prices.

    VIX: from yfinance (not in stock_prices).
    SPY: from stock_prices table.

    Returns:
        Tuple of (vix_closes, spy_closes) as Series with DatetimeIndex.
    """
    import yfinance as yf

    from backend.models.price import StockPrice

    # VIX from yfinance (30 days lookback is sufficient for daily features)
    vix_data = yf.download("^VIX", period="1y", progress=False)
    if isinstance(vix_data.columns, pd.MultiIndex):
        vix_data.columns = vix_data.columns.get_level_values(0)
    vix_closes = vix_data["Close"].copy()
    if vix_closes.index.tz is None:
        vix_closes.index = vix_closes.index.tz_localize("UTC")

    # SPY from stock_prices
    result = await db.execute(
        select(StockPrice.time, StockPrice.close)
        .where(StockPrice.ticker == "SPY")
        .order_by(StockPrice.time)
    )
    spy_rows = result.all()
    if spy_rows:
        spy_dates = pd.DatetimeIndex([r.time for r in spy_rows], tz="UTC")
        spy_closes = pd.Series([float(r.close) for r in spy_rows], index=spy_dates)
    else:
        # Fallback: download SPY from yfinance
        spy_data = yf.download("SPY", period="2y", progress=False)
        if isinstance(spy_data.columns, pd.MultiIndex):
            spy_data.columns = spy_data.columns.get_level_values(0)
        spy_closes = spy_data["Close"].copy()
        if spy_closes.index.tz is None:
            spy_closes.index = spy_closes.index.tz_localize("UTC")

    return vix_closes, spy_closes


async def _upsert_daily_feature_row(
    ticker: str,
    features_df: pd.DataFrame,
    db: AsyncSession,
) -> None:
    """Upsert the most recent feature row for a ticker.

    Takes the last row from features_df and inserts/updates
    into historical_features.
    """
    from backend.models.historical_feature import HistoricalFeature
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    if features_df.empty:
        return

    row = features_df.iloc[-1]
    idx = features_df.index[-1]
    dt = idx.date() if hasattr(idx, "date") else idx

    values = {
        "date": dt,
        "ticker": ticker,
        "momentum_21d": round(float(row["momentum_21d"]), 6),
        "momentum_63d": round(float(row["momentum_63d"]), 6),
        "momentum_126d": round(float(row["momentum_126d"]), 6),
        "rsi_value": round(float(row["rsi_value"]), 2),
        "macd_histogram": round(float(row["macd_histogram"]), 6),
        "sma_cross": int(row["sma_cross"]),
        "bb_position": int(row["bb_position"]),
        "volatility": round(float(row["volatility"]), 6),
        "sharpe_ratio": round(float(row["sharpe_ratio"]), 6),
        "vix_level": round(float(row["vix_level"]), 2),
        "spy_momentum_21d": round(float(row["spy_momentum_21d"]), 6),
        "stock_sentiment": None,
        "sector_sentiment": None,
        "macro_sentiment": None,
        "sentiment_confidence": None,
        "signals_aligned": None,
        "convergence_label": None,
        # No forward returns for today's row — targets are unknown
        "forward_return_60d": None,
        "forward_return_90d": None,
    }

    stmt = pg_insert(HistoricalFeature).values(values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["date", "ticker"],
        set_={k: stmt.excluded[k] for k in values if k not in ("date", "ticker")},
    )
    await db.execute(stmt)
    await db.commit()
```

Add the main task function:

```python
@tracked_task("daily_features", trigger="scheduled")
async def _populate_daily_features_async(*, run_id: uuid.UUID) -> dict:
    """Compute today's feature row for each ticker and upsert into historical_features.

    Runs nightly after the price pipeline completes. For each ticker:
    1. Load full price history from stock_prices
    2. Download VIX + SPY data
    3. Compute features via build_feature_dataframe
    4. Upsert the latest row into historical_features

    Returns:
        Dict with status, populated count, failed count.
    """
    if not settings.DAILY_FEATURES_ENABLED:
        logger.info("DAILY_FEATURES_ENABLED=False — skipping")
        return {"status": "disabled"}

    populated = 0
    failed: list[str] = []

    async with _db.async_session_factory() as db:
        tickers = await get_all_referenced_tickers(db)

    if not tickers:
        logger.info("No tickers for daily feature population")
        return {"status": "ok", "populated": 0, "failed": 0}

    # Fetch VIX + SPY once (shared across all tickers)
    async with _db.async_session_factory() as db:
        try:
            vix_closes, spy_closes = await _fetch_vix_and_spy(db)
        except Exception:
            logger.exception("Failed to fetch VIX/SPY data — aborting daily features")
            return {"status": "error", "populated": 0, "failed": len(tickers)}

    # Process each ticker
    for tkr in tickers:
        try:
            async with _db.async_session_factory() as db:
                closes = await _fetch_ticker_prices(tkr, db)

                if len(closes) < 250:
                    logger.warning(
                        "Insufficient price data for %s (%d rows, need 250+)",
                        tkr, len(closes),
                    )
                    failed.append(tkr)
                    continue

                features_df = await asyncio.to_thread(
                    build_feature_dataframe,
                    closes,
                    vix_closes=vix_closes,
                    spy_closes=spy_closes,
                )

                if features_df.empty:
                    logger.warning("Empty feature DataFrame for %s", tkr)
                    failed.append(tkr)
                    continue

                await _upsert_daily_feature_row(tkr, features_df, db)
                populated += 1
        except Exception:
            logger.exception("Daily feature population failed for %s", tkr)
            failed.append(tkr)

    status = "degraded" if failed else "ok"
    return {"status": status, "populated": populated, "failed": len(failed), "failed_tickers": failed}


@celery_app.task(name="backend.tasks.forecasting.populate_daily_features_task")
def populate_daily_features_task() -> dict:
    """Celery entry point for daily feature population."""
    return asyncio.run(_populate_daily_features_async(run_id=uuid.uuid4()))
```

Add `import asyncio` at the top if not already present (it is — line 1 of forecasting.py).

- [ ] **Step 4: Wire into beat schedule**

In `backend/tasks/__init__.py`, add after `"model-retrain-weekly"` entry (line 96):

```python
    "daily-feature-population": {
        "task": "backend.tasks.forecasting.populate_daily_features_task",
        "schedule": crontab(hour=22, minute=30),  # 10:30 PM ET — after nightly pipeline
    },
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/unit/tasks/test_daily_features.py -v`
Expected: PASS

Run: `uv run pytest tests/unit/ -q --tb=short`
Expected: 2680+ passed, 0 failures

- [ ] **Step 6: Commit**

```bash
git add backend/tasks/forecasting.py backend/tasks/__init__.py tests/unit/tasks/test_daily_features.py
git commit -m "feat(tasks): add daily feature population task

Nightly task at 22:30 ET (after price pipeline):
- Fetches VIX from yfinance, SPY from stock_prices
- Computes features via build_feature_dataframe per ticker
- Upserts latest row into historical_features
- Kill switch: DAILY_FEATURES_ENABLED"
```

---

## Task 4: Champion/Challenger Promotion Gate

**Files:**
- Modify: `backend/tasks/forecasting.py` (inside `_model_retrain_all_async`)
- Create: `tests/unit/tasks/test_champion_challenger.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/tasks/test_champion_challenger.py`:

```python
"""Tests for champion/challenger model promotion gate."""

import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestChampionChallenger:
    """Tests for champion/challenger logic in _model_retrain_all_async."""

    @pytest.mark.asyncio
    async def test_challenger_promoted_when_better(self):
        """Challenger replaces champion when direction accuracy improves ≥1%."""
        from backend.tasks.forecasting import _should_promote_challenger

        champion_metrics = {
            "direction_accuracy": 0.55,
            "ci_containment": 0.80,
        }
        challenger_metrics = {
            "direction_accuracy": 0.57,  # +2% improvement
            "mean_absolute_error": 0.03,
            "ci_containment": 0.82,
        }

        result = _should_promote_challenger(champion_metrics, challenger_metrics)
        assert result["promote"] is True
        assert "direction_accuracy" in result["reason"]

    @pytest.mark.asyncio
    async def test_challenger_promoted_when_ci_improves(self):
        """Challenger promoted when CI containment improves by ≥5%."""
        from backend.tasks.forecasting import _should_promote_challenger

        champion_metrics = {
            "direction_accuracy": 0.55,
            "ci_containment": 0.75,
        }
        challenger_metrics = {
            "direction_accuracy": 0.55,  # same
            "mean_absolute_error": 0.03,
            "ci_containment": 0.81,  # +6% improvement
        }

        result = _should_promote_challenger(champion_metrics, challenger_metrics)
        assert result["promote"] is True
        assert "ci_containment" in result["reason"]

    @pytest.mark.asyncio
    async def test_challenger_rejected_when_worse(self):
        """Challenger is NOT promoted when neither threshold is met."""
        from backend.tasks.forecasting import _should_promote_challenger

        champion_metrics = {
            "direction_accuracy": 0.58,
            "ci_containment": 0.82,
        }
        challenger_metrics = {
            "direction_accuracy": 0.58,  # same — no improvement
            "mean_absolute_error": 0.04,
            "ci_containment": 0.83,  # +1% — below 5% threshold
        }

        result = _should_promote_challenger(champion_metrics, challenger_metrics)
        assert result["promote"] is False

    @pytest.mark.asyncio
    async def test_no_champion_always_promotes(self):
        """When no existing champion, challenger is always promoted."""
        from backend.tasks.forecasting import _should_promote_challenger

        challenger_metrics = {
            "direction_accuracy": 0.52,
            "mean_absolute_error": 0.05,
            "ci_containment": 0.70,
        }

        result = _should_promote_challenger(None, challenger_metrics)
        assert result["promote"] is True
        assert "no existing champion" in result["reason"]

    @pytest.mark.asyncio
    async def test_disabled_via_config(self):
        """When CHAMPION_CHALLENGER_ENABLED=False, always promotes."""
        from backend.tasks.forecasting import _should_promote_challenger

        with patch("backend.tasks.forecasting.settings") as mock_settings:
            mock_settings.CHAMPION_CHALLENGER_ENABLED = False
            mock_settings.CHAMPION_DIRECTION_THRESHOLD = 0.01
            mock_settings.CHAMPION_CI_THRESHOLD = 0.05

            champion = {"direction_accuracy": 0.90, "ci_containment": 0.95}
            challenger = {"direction_accuracy": 0.50, "ci_containment": 0.50}

            result = _should_promote_challenger(champion, challenger)
        assert result["promote"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/tasks/test_champion_challenger.py -v`
Expected: FAIL — `_should_promote_challenger` does not exist

- [ ] **Step 3: Implement `_should_promote_challenger` function**

Add to `backend/tasks/forecasting.py`, before `_model_retrain_all_async`:

```python
def _should_promote_challenger(
    champion_metrics: dict | None,
    challenger_metrics: dict,
) -> dict:
    """Decide whether a challenger model should replace the current champion.

    Promotion criteria (spec review O1):
    - Direction accuracy improves by ≥ CHAMPION_DIRECTION_THRESHOLD (default 1%)
    - OR CI containment improves by ≥ CHAMPION_CI_THRESHOLD (default 5%)
    - If no existing champion, always promote.

    Args:
        champion_metrics: Current champion's metrics dict, or None if no champion.
        challenger_metrics: New challenger's metrics dict from training.

    Returns:
        Dict with "promote" (bool) and "reason" (str).
    """
    if not settings.CHAMPION_CHALLENGER_ENABLED:
        return {"promote": True, "reason": "champion/challenger disabled"}

    if champion_metrics is None:
        return {"promote": True, "reason": "no existing champion"}

    champ_dir = champion_metrics.get("direction_accuracy", 0.0)
    chall_dir = challenger_metrics.get("direction_accuracy", 0.0)
    dir_improvement = chall_dir - champ_dir

    champ_ci = champion_metrics.get("ci_containment", 0.0)
    chall_ci = challenger_metrics.get("ci_containment", 0.0)
    ci_improvement = chall_ci - champ_ci

    reasons: list[str] = []
    if dir_improvement >= settings.CHAMPION_DIRECTION_THRESHOLD:
        reasons.append(
            f"direction_accuracy improved by {dir_improvement:.3f} "
            f"({champ_dir:.3f} → {chall_dir:.3f})"
        )
    if ci_improvement >= settings.CHAMPION_CI_THRESHOLD:
        reasons.append(
            f"ci_containment improved by {ci_improvement:.3f} "
            f"({champ_ci:.3f} → {chall_ci:.3f})"
        )

    if reasons:
        return {"promote": True, "reason": "; ".join(reasons)}

    return {
        "promote": False,
        "reason": (
            f"direction_accuracy delta={dir_improvement:.3f} "
            f"(need ≥{settings.CHAMPION_DIRECTION_THRESHOLD}), "
            f"ci_containment delta={ci_improvement:.3f} "
            f"(need ≥{settings.CHAMPION_CI_THRESHOLD})"
        ),
    }
```

- [ ] **Step 4: Integrate into `_model_retrain_all_async`**

In `_model_retrain_all_async`, after training the models (section "2. Train one model bundle per horizon"), add champion/challenger check before the "3. Persist" section.

Replace the section that unconditionally retires old models (the `for horizon, (artifact_bytes, metrics) in trained_models.items():` loop inside the second session) with logic that:

1. Loads the current champion's metrics for this model_type
2. Calls `_should_promote_challenger(champion_metrics, metrics)`
3. If promote=True: proceed as before (retire old, activate new)
4. If promote=False: log the comparison, store comparison in a non-active ModelVersion row, skip activation

The key change inside the `for horizon` loop in section 3:

```python
        for horizon, (artifact_bytes, metrics) in trained_models.items():
            model_type = f"lightgbm_{horizon}d"

            # ── Champion/Challenger gate ──
            # Load current champion's metrics
            champ_result = await db.execute(
                select(ModelVersion).where(
                    ModelVersion.model_type == model_type,
                    ModelVersion.is_active.is_(True),
                )
            )
            champion = champ_result.scalar_one_or_none()
            champion_metrics = champion.metrics if champion else None

            promotion = _should_promote_challenger(champion_metrics, metrics)

            if not promotion["promote"]:
                logger.info(
                    "Champion/challenger: keeping champion for %s — %s",
                    model_type,
                    promotion["reason"],
                )
                # Store comparison in metrics for audit trail
                if champion:
                    updated_metrics = dict(champion.metrics or {})
                    updated_metrics["last_challenger_comparison"] = {
                        "challenger_metrics": metrics,
                        "decision": "kept_champion",
                        "reason": promotion["reason"],
                        "compared_at": datetime.now(timezone.utc).isoformat(),
                    }
                    champion.metrics = updated_metrics
                continue

            logger.info(
                "Champion/challenger: promoting challenger for %s — %s",
                model_type,
                promotion["reason"],
            )

            # ── Proceed with existing promotion logic ──
            # (bump version, retire old, create new ModelVersion, predict)
            # ... existing code from here ...
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/unit/tasks/test_champion_challenger.py -v`
Expected: PASS

Run: `uv run pytest tests/unit/ -q --tb=short`
Expected: 2685+ passed, 0 failures

- [ ] **Step 6: Commit**

```bash
git add backend/tasks/forecasting.py tests/unit/tasks/test_champion_challenger.py
git commit -m "feat(forecasting): add champion/challenger model promotion gate

Weekly retrain now compares challenger vs champion:
- Direction accuracy must improve ≥1% OR CI containment ≥5%
- If neither threshold met, champion is kept
- Comparison logged in ModelVersion.metrics for audit trail
- Kill switch: CHAMPION_CHALLENGER_ENABLED"
```

---

## Task 5: Feature Drift Monitoring

**Files:**
- Modify: `backend/tasks/evaluation.py`
- Modify: `backend/tasks/__init__.py`
- Create: `tests/unit/tasks/test_feature_drift.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/tasks/test_feature_drift.py`:

```python
"""Tests for feature drift monitoring."""

import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest


class TestFeatureDrift:
    """Tests for _check_feature_drift_async."""

    @pytest.mark.asyncio
    async def test_no_drift_returns_clean(self):
        """When feature distributions are stable, no warnings emitted."""
        from backend.tasks.evaluation import _check_feature_drift_async

        with (
            patch("backend.tasks.evaluation._db") as mock_db_module,
            patch("backend.tasks.evaluation._load_current_feature_stats") as mock_current,
            patch("backend.tasks.evaluation._load_training_feature_stats") as mock_training,
        ):
            # Current stats match training stats
            stats = {
                "momentum_21d": {"mean": 0.02, "std": 0.05},
                "rsi_value": {"mean": 50.0, "std": 10.0},
            }
            mock_current.return_value = stats
            mock_training.return_value = stats

            mock_session = AsyncMock()
            mock_db_module.async_session_factory.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_db_module.async_session_factory.return_value.__aexit__ = AsyncMock(
                return_value=False
            )

            result = await _check_feature_drift_async(run_id=uuid.uuid4())

        assert result["drifted_features"] == []
        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_drift_detected_when_mean_shifts(self):
        """When a feature mean shifts >2σ, it is flagged."""
        from backend.tasks.evaluation import _check_feature_drift_async

        with (
            patch("backend.tasks.evaluation._db") as mock_db_module,
            patch("backend.tasks.evaluation._load_current_feature_stats") as mock_current,
            patch("backend.tasks.evaluation._load_training_feature_stats") as mock_training,
        ):
            mock_training.return_value = {
                "momentum_21d": {"mean": 0.02, "std": 0.05},
                "rsi_value": {"mean": 50.0, "std": 10.0},
            }
            # momentum_21d shifted by 3σ (0.02 + 3*0.05 = 0.17)
            mock_current.return_value = {
                "momentum_21d": {"mean": 0.20, "std": 0.06},
                "rsi_value": {"mean": 51.0, "std": 10.5},  # within 2σ
            }

            mock_session = AsyncMock()
            mock_db_module.async_session_factory.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_db_module.async_session_factory.return_value.__aexit__ = AsyncMock(
                return_value=False
            )

            result = await _check_feature_drift_async(run_id=uuid.uuid4())

        assert "momentum_21d" in result["drifted_features"]
        assert result["status"] == "drift_detected"

    @pytest.mark.asyncio
    async def test_disabled_via_config(self):
        """Task returns early when FEATURE_DRIFT_ENABLED=False."""
        from backend.tasks.evaluation import _check_feature_drift_async

        with patch("backend.tasks.evaluation.settings") as mock_settings:
            mock_settings.FEATURE_DRIFT_ENABLED = False
            result = await _check_feature_drift_async(run_id=uuid.uuid4())

        assert result["status"] == "disabled"

    @pytest.mark.asyncio
    async def test_zero_std_skipped(self):
        """Features with zero training std are skipped (no division by zero)."""
        from backend.tasks.evaluation import _check_feature_drift_async

        with (
            patch("backend.tasks.evaluation._db") as mock_db_module,
            patch("backend.tasks.evaluation._load_current_feature_stats") as mock_current,
            patch("backend.tasks.evaluation._load_training_feature_stats") as mock_training,
        ):
            mock_training.return_value = {
                "sma_cross": {"mean": 1.0, "std": 0.0},  # constant feature
            }
            mock_current.return_value = {
                "sma_cross": {"mean": 2.0, "std": 0.1},  # shifted but std=0 at training
            }

            mock_session = AsyncMock()
            mock_db_module.async_session_factory.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_db_module.async_session_factory.return_value.__aexit__ = AsyncMock(
                return_value=False
            )

            result = await _check_feature_drift_async(run_id=uuid.uuid4())

        assert result["status"] == "ok"
        assert "sma_cross" not in result["drifted_features"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/tasks/test_feature_drift.py -v`
Expected: FAIL — `_check_feature_drift_async` does not exist

- [ ] **Step 3: Implement feature drift monitoring in evaluation.py**

Add to `backend/tasks/evaluation.py`. New imports at top:

```python
from backend.services.forecast_engine import FEATURE_NAMES
```

Add helper functions and the task:

```python
async def _load_current_feature_stats(db: AsyncSession) -> dict[str, dict[str, float]]:
    """Compute current mean/std of each feature across all tickers.

    Queries the last 30 days of historical_features to get recent
    feature distributions.

    Returns:
        Dict mapping feature_name → {"mean": float, "std": float}.
    """
    from backend.models.historical_feature import HistoricalFeature

    thirty_days_ago = datetime.now(timezone.utc).date() - timedelta(days=30)
    result = await db.execute(
        select(HistoricalFeature).where(HistoricalFeature.date >= thirty_days_ago)
    )
    rows = result.scalars().all()

    if not rows:
        return {}

    # Numeric features only (skip convergence_label which is string)
    numeric_features = [f for f in FEATURE_NAMES if f != "convergence_label"]
    stats: dict[str, dict[str, float]] = {}

    for feat in numeric_features:
        values = [
            float(getattr(row, feat))
            for row in rows
            if getattr(row, feat, None) is not None
            and not (isinstance(getattr(row, feat), float) and math.isnan(getattr(row, feat)))
        ]
        if len(values) >= 10:
            stats[feat] = {
                "mean": float(np.mean(values)),
                "std": float(np.std(values)),
            }

    return stats


async def _load_training_feature_stats(db: AsyncSession) -> dict[str, dict[str, float]]:
    """Load training-time feature statistics from the active model's metrics.

    Returns:
        Dict mapping feature_name → {"mean": float, "std": float},
        or empty dict if no active model with stored stats.
    """
    from backend.models.forecast import ModelVersion

    result = await db.execute(
        select(ModelVersion).where(
            ModelVersion.is_active.is_(True),
            ModelVersion.model_type.like("lightgbm_%"),
        ).limit(1)
    )
    mv = result.scalar_one_or_none()
    if mv is None:
        return {}

    metrics = mv.metrics or {}
    return metrics.get("training_feature_stats", {})


@tracked_task("feature_drift_check")
async def _check_feature_drift_async(*, run_id: uuid.UUID) -> dict:
    """Check for feature distribution drift vs training-time baseline.

    Compares current 30-day feature mean to training-time mean. If any
    feature's mean shifts by more than FEATURE_DRIFT_SIGMA_THRESHOLD
    standard deviations, emits a WARNING and flags the model as
    potentially stale.

    Returns:
        Dict with status and list of drifted features.
    """
    if not settings.FEATURE_DRIFT_ENABLED:
        logger.info("FEATURE_DRIFT_ENABLED=False — skipping")
        return {"status": "disabled"}

    async with _db.async_session_factory() as db:
        training_stats = await _load_training_feature_stats(db)
        if not training_stats:
            logger.info("No training-time feature stats found — skipping drift check")
            return {"status": "no_baseline", "drifted_features": []}

        current_stats = await _load_current_feature_stats(db)
        if not current_stats:
            logger.warning("No current feature data for drift check")
            return {"status": "no_data", "drifted_features": []}

        drifted: list[str] = []
        threshold = settings.FEATURE_DRIFT_SIGMA_THRESHOLD

        for feat, train_stat in training_stats.items():
            if feat not in current_stats:
                continue
            train_mean = train_stat["mean"]
            train_std = train_stat["std"]

            if train_std == 0.0:
                # Constant feature at training time — skip
                continue

            current_mean = current_stats[feat]["mean"]
            z_score = abs(current_mean - train_mean) / train_std

            if z_score > threshold:
                drifted.append(feat)
                logger.warning(
                    "Feature drift detected: %s — current_mean=%.4f, "
                    "train_mean=%.4f, train_std=%.4f, z=%.2f (threshold=%.1f)",
                    feat,
                    current_mean,
                    train_mean,
                    train_std,
                    z_score,
                    threshold,
                )

        # Flag active models as potentially stale if drift detected
        if drifted:
            from backend.models.forecast import ModelVersion

            result = await db.execute(
                select(ModelVersion).where(
                    ModelVersion.is_active.is_(True),
                    ModelVersion.model_type.like("lightgbm_%"),
                )
            )
            for mv in result.scalars().all():
                metrics = dict(mv.metrics or {})
                metrics["feature_drift_detected"] = {
                    "features": drifted,
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                }
                mv.metrics = metrics
            await db.commit()

    status = "drift_detected" if drifted else "ok"
    logger.info("Feature drift check: %s — %d features drifted", status, len(drifted))
    return {"status": status, "drifted_features": drifted}


@celery_app.task(name="backend.tasks.evaluation.check_feature_drift_task")
def check_feature_drift_task() -> dict:
    """Celery entry point for feature drift monitoring."""
    return asyncio.run(_check_feature_drift_async(run_id=uuid.uuid4()))
```

- [ ] **Step 4: Store training-time feature stats during model training**

In `_model_retrain_all_async` in `backend/tasks/forecasting.py`, after training the models (after the `for horizon in settings.DEFAULT_FORECAST_HORIZONS` loop), compute and store feature stats in the metrics dict:

Add this code right after training completes and before the "Persist" section:

```python
    # Compute training-time feature stats for drift monitoring
    numeric_features = [f for f in FEATURE_NAMES if f != "convergence_label"]
    training_feature_stats: dict[str, dict[str, float]] = {}
    for feat in numeric_features:
        if feat in features_df.columns:
            values = features_df[feat].dropna()
            if len(values) >= 10:
                training_feature_stats[feat] = {
                    "mean": round(float(values.mean()), 6),
                    "std": round(float(values.std()), 6),
                }
```

Then when creating the ModelVersion row, include the stats in metrics:

```python
            metrics_with_stats = {
                **metrics,
                "training_feature_stats": training_feature_stats,
            }
```

And use `metrics_with_stats` instead of `metrics` in the `ModelVersion(...)` constructor.

- [ ] **Step 5: Wire into beat schedule**

In `backend/tasks/__init__.py`, add:

```python
    "feature-drift-check-daily": {
        "task": "backend.tasks.evaluation.check_feature_drift_task",
        "schedule": crontab(hour=23, minute=0),  # 11 PM ET — after daily features
    },
```

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/unit/tasks/test_feature_drift.py -v`
Expected: PASS

Run: `uv run pytest tests/unit/ -q --tb=short`
Expected: 2690+ passed, 0 failures

- [ ] **Step 7: Commit**

```bash
git add backend/tasks/evaluation.py backend/tasks/forecasting.py backend/tasks/__init__.py tests/unit/tasks/test_feature_drift.py
git commit -m "feat(evaluation): add feature drift monitoring

Nightly at 23:00 ET:
- Computes mean/std of each feature across all tickers (last 30 days)
- Compares to training-time distribution stored in ModelVersion.metrics
- Flags model as potentially stale if any feature shifts >2σ
- Training stats computed and stored during model training
- Kill switch: FEATURE_DRIFT_ENABLED"
```

---

## Task 6: Fix `evaluation.py` Prophet-Only Filter

**Files:**
- Modify: `backend/tasks/evaluation.py:235`
- Modify: `tests/unit/tasks/` (existing drift check tests, if any)

- [ ] **Step 1: Write a test for LightGBM drift detection**

Add to an existing test file or create a focused test. The key assertion: `_check_drift_async` should find and check models with `model_type` starting with `"lightgbm_"`, not just `"prophet"`.

```python
# In a new or existing test file
class TestDriftCheckModelTypes:
    """Verify drift check covers LightGBM models, not just Prophet."""

    @pytest.mark.asyncio
    async def test_drift_check_includes_lightgbm_models(self):
        """_check_drift_async should check lightgbm models."""
        from backend.tasks.evaluation import _check_drift_async

        mock_mv = MagicMock()
        mock_mv.ticker = "__universe__"
        mock_mv.is_active = True
        mock_mv.model_type = "lightgbm_60d"
        mock_mv.status = "active"
        mock_mv.metrics = {"rolling_mape": 0.15}

        with (
            patch("backend.tasks.evaluation._db") as mock_db_module,
            patch("backend.tasks.evaluation._check_volatility_spike") as mock_vol,
            patch("backend.tasks.evaluation._check_vix_regime") as mock_vix,
        ):
            mock_vol.return_value = False
            mock_vix.return_value = "normal"

            mock_session = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = [mock_mv]

            # For backtest MAPE query
            mock_bt_result = MagicMock()
            mock_bt_result.all.return_value = []

            mock_session.execute = AsyncMock(side_effect=[mock_result, mock_bt_result])
            mock_session.commit = AsyncMock()

            mock_db_module.async_session_factory.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_db_module.async_session_factory.return_value.__aexit__ = AsyncMock(
                return_value=False
            )

            result = await _check_drift_async(run_id=uuid.uuid4())

        # The model should have been checked (not skipped due to type filter)
        assert result is not None
```

- [ ] **Step 2: Fix the filter in `_check_drift_async`**

In `backend/tasks/evaluation.py`, line 235, change:

```python
                ModelVersion.model_type == "prophet",
```

to:

```python
                ModelVersion.model_type.in_(["prophet", "lightgbm_60d", "lightgbm_90d"]),
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/unit/ -q --tb=short`
Expected: All pass

- [ ] **Step 4: Commit**

```bash
git add backend/tasks/evaluation.py tests/unit/tasks/
git commit -m "fix(evaluation): drift check now includes LightGBM model types

_check_drift_async was filtering for model_type='prophet' only,
silently skipping all LightGBM models from drift detection."
```

---

## Task 7: Lint, Format, Full Test Suite

- [ ] **Step 1: Run ruff check + format on all changed files**

```bash
uv run ruff check --fix backend/services/backtesting.py backend/tasks/forecasting.py backend/tasks/evaluation.py backend/tasks/__init__.py backend/config.py
uv run ruff format backend/services/backtesting.py backend/tasks/forecasting.py backend/tasks/evaluation.py backend/tasks/__init__.py backend/config.py
uv run ruff check --fix tests/unit/services/test_backtest_engine.py tests/unit/tasks/test_daily_features.py tests/unit/tasks/test_champion_challenger.py tests/unit/tasks/test_feature_drift.py
uv run ruff format tests/unit/services/test_backtest_engine.py tests/unit/tasks/test_daily_features.py tests/unit/tasks/test_champion_challenger.py tests/unit/tasks/test_feature_drift.py
```

- [ ] **Step 2: Run full unit test suite**

```bash
uv run pytest tests/unit/ -q --tb=short
```

Expected: 2690+ passed, 0 failures

- [ ] **Step 3: Run full ruff on codebase (Hard Rule: lint full scope)**

```bash
uv run ruff check backend/ tests/ --fix
uv run ruff format backend/ tests/
git diff --stat  # verify only expected files changed
```

- [ ] **Step 4: Final commit if lint produced changes**

```bash
git add -u
git commit -m "style: lint + format for PR2 changes"
```

---

## Summary of Beat Schedule Changes

| Entry | Task | Schedule | Notes |
|---|---|---|---|
| `daily-feature-population` | `populate_daily_features_task` | 22:30 ET daily | After nightly pipeline (21:30) |
| `feature-drift-check-daily` | `check_feature_drift_task` | 23:00 ET daily | After daily features (22:30) |
| `model-retrain-weekly` | (existing, modified) | Sun 2:00 AM ET | Now with champion/challenger gate |

## Test Coverage Summary

| Test File | What it covers |
|---|---|
| `tests/unit/services/test_backtest_engine.py` | Window generation, metric computation (unchanged), new walk-forward tests |
| `tests/unit/tasks/test_daily_features.py` | Daily feature population: happy path, disabled, ticker failure |
| `tests/unit/tasks/test_champion_challenger.py` | Promotion gate: better/worse/no-champion/disabled |
| `tests/unit/tasks/test_feature_drift.py` | Drift detection: clean/drifted/disabled/zero-std |

## Files Modified (10 total)

| File | Lines changed (est.) |
|---|---|
| `backend/config.py` | +8 |
| `backend/services/backtesting.py` | ~-180, +130 |
| `backend/tasks/forecasting.py` | +200 |
| `backend/tasks/evaluation.py` | +120 |
| `backend/tasks/__init__.py` | +8 |
| `tests/unit/services/test_backtest_engine.py` | +120 |
| `tests/unit/tasks/test_daily_features.py` | +90 (new) |
| `tests/unit/tasks/test_champion_challenger.py` | +100 (new) |
| `tests/unit/tasks/test_feature_drift.py` | +110 (new) |
| Total | ~490 lines of diff |
