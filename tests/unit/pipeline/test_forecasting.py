"""Unit tests for Prophet forecasting engine — training, prediction, Sharpe, correlation."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pandas as pd
import pytest
from freezegun import freeze_time

from backend.models.forecast import ForecastResult, ModelVersion
from backend.tools.forecasting import (
    DEFAULT_HORIZONS,
    compute_portfolio_correlation_matrix,
    compute_sharpe_direction,
    predict_forecast,
    train_prophet_model,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_model_version(
    ticker: str = "AAPL",
    version: int = 1,
    artifact_path: str | None = None,
) -> ModelVersion:
    """Create a ModelVersion for testing."""
    return ModelVersion(
        id=uuid.uuid4(),
        ticker=ticker,
        model_type="prophet",
        version=version,
        is_active=True,
        trained_at=datetime.now(timezone.utc),
        training_data_start=date(2024, 1, 1),
        training_data_end=date(2026, 3, 1),
        data_points=500,
        hyperparameters={},
        metrics={},
        status="active",
        artifact_path=artifact_path or f"data/models/prophet/{ticker}_prophet_v{version}.json",
    )


def _make_price_rows(n: int = 500, start_price: float = 150.0) -> list:
    """Generate mock StockPrice (time, adj_close) rows."""
    dates = pd.bdate_range(end=datetime.now(), periods=n)
    prices = [start_price + i * 0.1 + np.random.normal(0, 2) for i in range(n)]
    return [(d.to_pydatetime(), p) for d, p in zip(dates, prices)]


def _make_prophet_forecast_df(horizons: list[int]) -> pd.DataFrame:
    """Create a mock Prophet forecast DataFrame."""
    today = date.today()
    rows = []
    for h in horizons:
        target = today + timedelta(days=h)
        rows.append(
            {
                "ds": pd.Timestamp(target),
                "yhat": 200.0 + h * 0.1,
                "yhat_lower": 180.0 + h * 0.05,
                "yhat_upper": 220.0 + h * 0.15,
            }
        )
    # Add some historical rows too
    for i in range(10):
        rows.append(
            {
                "ds": pd.Timestamp(today - timedelta(days=i)),
                "yhat": 195.0,
                "yhat_lower": 175.0,
                "yhat_upper": 215.0,
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# train_prophet_model
# ---------------------------------------------------------------------------


class TestTrainProphetModel:
    """Tests for train_prophet_model."""

    @pytest.mark.asyncio
    @patch("backend.tools.forecasting.Prophet")
    async def test_trains_and_creates_model_version(self, mock_prophet_cls) -> None:
        """Training should create a ModelVersion row and serialize the model."""
        mock_model = MagicMock()
        mock_model.fit.return_value = mock_model
        mock_prophet_cls.return_value = mock_model

        db = AsyncMock()
        price_rows = _make_price_rows(500)

        # Mock DB calls
        price_result = MagicMock()
        price_result.all.return_value = price_rows

        version_result = MagicMock()
        version_result.scalar_one_or_none.return_value = None  # First version

        # Call order: prices, sentiment regressors, version lookup, retire update
        sentiment_result = MagicMock()
        sentiment_result.all.return_value = []  # No sentiment data — regressors skipped

        db.execute = AsyncMock(
            side_effect=[price_result, sentiment_result, version_result, MagicMock()]
        )

        with patch("backend.tools.forecasting.model_to_json", return_value='{"mock": true}'):
            with patch("builtins.open", MagicMock()):
                mv = await train_prophet_model("AAPL", db)

        assert mv.ticker == "AAPL"
        assert mv.version == 1
        assert mv.is_active is True
        assert mv.status == "active"
        assert mv.data_points == 500
        db.add.assert_called_once()
        db.flush.assert_called_once()
        mock_model.fit.assert_called_once()

    @pytest.mark.asyncio
    async def test_insufficient_data_raises(self) -> None:
        """Training with < MIN_DATA_POINTS rows should raise ValueError."""
        db = AsyncMock()
        price_result = MagicMock()
        price_result.all.return_value = _make_price_rows(50)  # Too few
        db.execute = AsyncMock(return_value=price_result)

        with pytest.raises(ValueError, match="Insufficient data"):
            await train_prophet_model("AAPL", db)

    @pytest.mark.asyncio
    @patch("backend.tools.forecasting.Prophet")
    async def test_version_auto_increment(self, mock_prophet_cls) -> None:
        """Second training should create v2 and retire v1."""
        mock_model = MagicMock()
        mock_model.fit.return_value = mock_model
        mock_prophet_cls.return_value = mock_model

        db = AsyncMock()
        price_rows = _make_price_rows(500)

        price_result = MagicMock()
        price_result.all.return_value = price_rows

        version_result = MagicMock()
        version_result.scalar_one_or_none.return_value = 1  # Existing v1

        # Call order: prices, sentiment regressors, version lookup, retire update
        sentiment_result = MagicMock()
        sentiment_result.all.return_value = []  # No sentiment data — regressors skipped

        db.execute = AsyncMock(
            side_effect=[price_result, sentiment_result, version_result, MagicMock()]
        )

        with patch("backend.tools.forecasting.model_to_json", return_value="{}"):
            with patch("builtins.open", MagicMock()):
                mv = await train_prophet_model("AAPL", db)

        assert mv.version == 2


# ---------------------------------------------------------------------------
# predict_forecast
# ---------------------------------------------------------------------------


class TestPredictForecast:
    """Tests for predict_forecast."""

    @pytest.mark.asyncio
    @patch("backend.tools.forecasting.model_from_json")
    @patch("backend.tools.forecasting.settings")
    async def test_returns_3_forecast_results(self, mock_settings, mock_from_json) -> None:
        """predict_forecast should return one ForecastResult per horizon."""
        mock_settings.PROPHET_REAL_SENTIMENT_ENABLED = False
        mock_model = MagicMock()
        mock_model.extra_regressors = {}
        mock_model.make_future_dataframe.return_value = pd.DataFrame({"ds": []})
        mock_model.predict.return_value = _make_prophet_forecast_df(DEFAULT_HORIZONS)
        mock_from_json.return_value = mock_model

        mv = _make_model_version()

        with patch("builtins.open", MagicMock()):
            with patch.object(Path, "exists", return_value=True):
                results = await predict_forecast(mv, AsyncMock())

        assert len(results) == len(DEFAULT_HORIZONS)
        assert all(isinstance(r, ForecastResult) for r in results)
        horizons = [r.horizon_days for r in results]
        assert horizons == DEFAULT_HORIZONS

    @pytest.mark.asyncio
    @freeze_time("2026-04-13 23:59:00", tz_offset=0)
    @patch("backend.tools.forecasting.model_from_json")
    @patch("backend.tools.forecasting.settings")
    async def test_forecast_has_correct_fields(self, mock_settings, mock_from_json) -> None:
        """Each ForecastResult should have expected_return_pct, bounds, target date."""
        mock_settings.PROPHET_REAL_SENTIMENT_ENABLED = False
        mock_model = MagicMock()
        mock_model.extra_regressors = {}
        mock_model.make_future_dataframe.return_value = pd.DataFrame({"ds": []})
        mock_model.predict.return_value = _make_prophet_forecast_df([90])
        mock_from_json.return_value = mock_model

        mv = _make_model_version()

        with patch("builtins.open", MagicMock()):
            with patch.object(Path, "exists", return_value=True):
                results = await predict_forecast(mv, AsyncMock(), horizons=[90])

        fc = results[0]
        assert fc.ticker == "AAPL"
        assert fc.return_lower_pct < fc.return_upper_pct
        assert fc.target_date == date(2026, 7, 12)  # 2026-04-13 + 90d
        assert fc.actual_return_pct is None
        assert fc.model_version_id == mv.id

    @pytest.mark.asyncio
    async def test_missing_artifact_raises(self) -> None:
        """predict_forecast should raise FileNotFoundError if artifact is missing."""
        mv = _make_model_version(artifact_path="/nonexistent/path.json")

        with pytest.raises(FileNotFoundError, match="Model artifact not found"):
            await predict_forecast(mv, AsyncMock())


# ---------------------------------------------------------------------------
# compute_sharpe_direction
# ---------------------------------------------------------------------------


class TestComputeSharpeDirection:
    """Tests for compute_sharpe_direction."""

    @pytest.mark.asyncio
    async def test_improving(self) -> None:
        """Sharpe increasing by > 0.1 should return 'improving'."""
        db = AsyncMock()
        now = datetime.now(timezone.utc)

        latest = MagicMock()
        latest.sharpe_ratio = 1.5
        latest.computed_at = now

        latest_result = MagicMock()
        latest_result.first.return_value = latest

        past_result = MagicMock()
        past_result.scalar_one_or_none.return_value = 1.2  # diff = 0.3 > 0.1

        db.execute = AsyncMock(side_effect=[latest_result, past_result])

        direction = await compute_sharpe_direction("AAPL", db)
        assert direction == "improving"

    @pytest.mark.asyncio
    async def test_declining(self) -> None:
        """Sharpe decreasing by > 0.1 should return 'declining'."""
        db = AsyncMock()
        now = datetime.now(timezone.utc)

        latest = MagicMock()
        latest.sharpe_ratio = 0.5
        latest.computed_at = now

        latest_result = MagicMock()
        latest_result.first.return_value = latest

        past_result = MagicMock()
        past_result.scalar_one_or_none.return_value = 1.0  # diff = -0.5 < -0.1

        db.execute = AsyncMock(side_effect=[latest_result, past_result])

        direction = await compute_sharpe_direction("AAPL", db)
        assert direction == "declining"

    @pytest.mark.asyncio
    async def test_flat(self) -> None:
        """Sharpe change within ±0.1 should return 'flat'."""
        db = AsyncMock()
        now = datetime.now(timezone.utc)

        latest = MagicMock()
        latest.sharpe_ratio = 1.0
        latest.computed_at = now

        latest_result = MagicMock()
        latest_result.first.return_value = latest

        past_result = MagicMock()
        past_result.scalar_one_or_none.return_value = 0.95  # diff = 0.05

        db.execute = AsyncMock(side_effect=[latest_result, past_result])

        direction = await compute_sharpe_direction("AAPL", db)
        assert direction == "flat"

    @pytest.mark.asyncio
    async def test_no_data_returns_flat(self) -> None:
        """No signal data should default to 'flat'."""
        db = AsyncMock()
        result = MagicMock()
        result.first.return_value = None
        db.execute = AsyncMock(return_value=result)

        direction = await compute_sharpe_direction("AAPL", db)
        assert direction == "flat"

    @pytest.mark.asyncio
    async def test_no_historical_returns_flat(self) -> None:
        """No 30-day-ago snapshot should return 'flat'."""
        db = AsyncMock()
        now = datetime.now(timezone.utc)

        latest = MagicMock()
        latest.sharpe_ratio = 1.5
        latest.computed_at = now

        latest_result = MagicMock()
        latest_result.first.return_value = latest

        past_result = MagicMock()
        past_result.scalar_one_or_none.return_value = None

        db.execute = AsyncMock(side_effect=[latest_result, past_result])

        direction = await compute_sharpe_direction("AAPL", db)
        assert direction == "flat"


# ---------------------------------------------------------------------------
# compute_portfolio_correlation_matrix
# ---------------------------------------------------------------------------


class TestPortfolioCorrelationMatrix:
    """Tests for compute_portfolio_correlation_matrix."""

    @pytest.mark.asyncio
    async def test_symmetric_matrix(self) -> None:
        """Correlation matrix should be symmetric."""
        db = AsyncMock()

        # Generate correlated price data
        dates = pd.bdate_range(end=datetime.now(), periods=60)
        rows = []
        for d in dates:
            for ticker, base in [("AAPL", 150), ("MSFT", 300), ("GOOG", 140)]:
                rows.append((ticker, d.to_pydatetime(), base + np.random.normal(0, 5)))

        result = MagicMock()
        result.all.return_value = rows
        db.execute = AsyncMock(return_value=result)

        corr = await compute_portfolio_correlation_matrix(["AAPL", "MSFT", "GOOG"], db)

        assert corr.shape[0] == corr.shape[1]
        # Symmetric: corr[i,j] == corr[j,i]
        np.testing.assert_array_almost_equal(corr.values, corr.values.T)

    @pytest.mark.asyncio
    async def test_diagonal_is_one(self) -> None:
        """Diagonal of correlation matrix should be 1.0."""
        db = AsyncMock()

        dates = pd.bdate_range(end=datetime.now(), periods=60)
        rows = []
        for d in dates:
            for ticker, base in [("AAPL", 150), ("MSFT", 300)]:
                rows.append((ticker, d.to_pydatetime(), base + np.random.normal(0, 5)))

        result = MagicMock()
        result.all.return_value = rows
        db.execute = AsyncMock(return_value=result)

        corr = await compute_portfolio_correlation_matrix(["AAPL", "MSFT"], db)

        for i in range(len(corr)):
            assert abs(corr.iloc[i, i] - 1.0) < 0.001

    @pytest.mark.asyncio
    async def test_empty_data_returns_empty(self) -> None:
        """No price data should return empty DataFrame."""
        db = AsyncMock()
        result = MagicMock()
        result.all.return_value = []
        db.execute = AsyncMock(return_value=result)

        corr = await compute_portfolio_correlation_matrix(["AAPL", "MSFT"], db)
        assert corr.empty
