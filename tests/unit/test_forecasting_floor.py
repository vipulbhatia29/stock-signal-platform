"""Regression tests for Prophet negative price floor (KAN-403).

Tests that predict_forecast() floors negative or near-zero yhat values
to max(0.01, last_known_price * 0.01) to prevent impossible negative
equity prices from poisoning downstream calculations.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from backend.tools.forecasting import predict_forecast


def _make_model_version(
    ticker: str = "TSLA",
    artifact_path: str = "/fake/model.json",
) -> MagicMock:
    """Create a mock ModelVersion with required fields."""
    mv = MagicMock()
    mv.ticker = ticker
    mv.id = uuid.uuid4()
    mv.version = 1
    mv.artifact_path = artifact_path
    return mv


def _make_mock_model(
    last_training_price: float,
    yhat_values: dict[int, float],
    yhat_lower_values: dict[int, float],
    yhat_upper_values: dict[int, float],
) -> MagicMock:
    """Create a mock Prophet model with history and predict().

    Args:
        last_training_price: The last price in model.history["y"].
        yhat_values: Mapping of horizon_days -> yhat (central forecast).
        yhat_lower_values: Mapping of horizon_days -> yhat_lower.
        yhat_upper_values: Mapping of horizon_days -> yhat_upper.

    Returns:
        Mock Prophet model with history DataFrame and predict() method.
    """
    model = MagicMock()
    model.extra_regressors = {}

    # Set up model.history with last_training_price as the final row
    history_df = pd.DataFrame(
        {"y": [last_training_price + 10, last_training_price + 5, last_training_price]}
    )
    model.history = history_df

    def make_predict(horizon: int) -> pd.DataFrame:
        """Build a forecast DataFrame for the given horizon."""
        today = datetime.now(timezone.utc).date()
        target_date = today + pd.Timedelta(days=horizon)
        return pd.DataFrame(
            {
                "ds": [pd.Timestamp(target_date)],
                "yhat": [yhat_values[horizon]],
                "yhat_lower": [yhat_lower_values[horizon]],
                "yhat_upper": [yhat_upper_values[horizon]],
            }
        )

    def side_effect_predict(future: pd.DataFrame) -> pd.DataFrame:
        """Infer horizon from future DataFrame length and return forecast row."""
        # future has periods rows; infer from the number of rows created
        # We patch make_future_dataframe to return a 1-row df with the target date
        # The model.predict is called with that df; use the last ds date to derive horizon
        today = datetime.now(timezone.utc).date()
        last_ds = future["ds"].iloc[-1].date()
        horizon = (last_ds - today).days
        return make_predict(horizon)

    model.predict.side_effect = side_effect_predict

    def make_future_df(periods: int, freq: str = "D") -> pd.DataFrame:
        """Return a single-row future DataFrame for the target date."""
        today = datetime.now(timezone.utc).date()
        target_date = today + pd.Timedelta(days=periods)
        return pd.DataFrame({"ds": [pd.Timestamp(target_date)]})

    model.make_future_dataframe.side_effect = make_future_df

    return model


class TestPredictForecastPriceFloor:
    """Tests for the price floor applied to Prophet predictions."""

    @pytest.mark.regression
    @pytest.mark.asyncio
    async def test_negative_yhat_is_floored_to_scale_minimum(self) -> None:
        """Negative yhat values are floored to max(0.01, last_price * 0.01).

        For a last training price of $100, the floor is $1.00.
        A yhat of -5.00 should become $1.00.
        """
        last_price = 100.0
        floor = max(0.01, last_price * 0.01)  # 1.00

        model = _make_mock_model(
            last_training_price=last_price,
            yhat_values={90: -5.0, 180: 150.0, 270: 160.0},
            yhat_lower_values={90: -20.0, 180: 130.0, 270: 140.0},
            yhat_upper_values={90: 5.0, 180: 170.0, 270: 180.0},
        )

        mv = _make_model_version()

        with (
            patch("builtins.open", MagicMock()),
            patch("backend.tools.forecasting.model_from_json", return_value=model),
            patch("backend.tools.forecasting.Path.exists", return_value=True),
        ):
            results = await predict_forecast(mv, AsyncMock(), horizons=[90, 180, 270])

        horizon_90 = next(r for r in results if r.horizon_days == 90)

        # yhat=-5.0 is negative → floor to 1.00
        assert horizon_90.predicted_price == round(floor, 2)
        # yhat_lower=-20.0 is negative → floor to 1.00
        assert horizon_90.predicted_lower == round(floor, 2)
        # yhat_upper=5.0 is positive and > floor → unchanged
        assert horizon_90.predicted_upper == round(5.0, 2)

    @pytest.mark.regression
    @pytest.mark.asyncio
    async def test_positive_predictions_above_floor_are_unchanged(self) -> None:
        """Positive yhat values above the floor pass through unmodified."""
        last_price = 200.0

        model = _make_mock_model(
            last_training_price=last_price,
            yhat_values={90: 210.0, 180: 220.0, 270: 230.0},
            yhat_lower_values={90: 195.0, 180: 205.0, 270: 215.0},
            yhat_upper_values={90: 225.0, 180: 235.0, 270: 245.0},
        )

        mv = _make_model_version()

        with (
            patch("builtins.open", MagicMock()),
            patch("backend.tools.forecasting.model_from_json", return_value=model),
            patch("backend.tools.forecasting.Path.exists", return_value=True),
        ):
            results = await predict_forecast(mv, AsyncMock(), horizons=[90, 180, 270])

        for result in results:
            assert result.predicted_price > 0
            assert result.predicted_lower > 0
            assert result.predicted_upper > 0

        horizon_90 = next(r for r in results if r.horizon_days == 90)
        assert horizon_90.predicted_price == round(210.0, 2)
        assert horizon_90.predicted_lower == round(195.0, 2)
        assert horizon_90.predicted_upper == round(225.0, 2)

    @pytest.mark.regression
    @pytest.mark.asyncio
    async def test_zero_yhat_is_floored(self) -> None:
        """Zero yhat value is floored since equities cannot trade at $0."""
        last_price = 50.0
        floor = max(0.01, last_price * 0.01)  # 0.50

        model = _make_mock_model(
            last_training_price=last_price,
            yhat_values={90: 0.0, 180: 55.0, 270: 60.0},
            yhat_lower_values={90: -2.0, 180: 48.0, 270: 52.0},
            yhat_upper_values={90: 0.3, 180: 62.0, 270: 68.0},
        )

        mv = _make_model_version()

        with (
            patch("builtins.open", MagicMock()),
            patch("backend.tools.forecasting.model_from_json", return_value=model),
            patch("backend.tools.forecasting.Path.exists", return_value=True),
        ):
            results = await predict_forecast(mv, AsyncMock(), horizons=[90])

        horizon_90 = results[0]
        # 0.0 < floor → floored
        assert horizon_90.predicted_price == round(floor, 2)
        # -2.0 < floor → floored
        assert horizon_90.predicted_lower == round(floor, 2)
        # 0.3 < floor (0.50) → floored
        assert horizon_90.predicted_upper == round(floor, 2)

    @pytest.mark.regression
    @pytest.mark.asyncio
    async def test_floor_uses_last_training_price_scale(self) -> None:
        """Floor is 1% of last training price, not a fixed value.

        For a penny stock (last_price=0.05), the floor falls back to 0.01.
        For a large-cap stock (last_price=500.0), the floor is 5.00.
        """
        # Penny stock case — floor clamps to minimum 0.01
        penny_model = _make_mock_model(
            last_training_price=0.05,
            yhat_values={90: -0.001},
            yhat_lower_values={90: -0.002},
            yhat_upper_values={90: -0.0005},
        )
        mv = _make_model_version()

        with (
            patch("builtins.open", MagicMock()),
            patch("backend.tools.forecasting.model_from_json", return_value=penny_model),
            patch("backend.tools.forecasting.Path.exists", return_value=True),
        ):
            results = await predict_forecast(mv, AsyncMock(), horizons=[90])

        assert results[0].predicted_price == 0.01

        # Large-cap case — floor is 1% of 500 = 5.00
        large_cap_model = _make_mock_model(
            last_training_price=500.0,
            yhat_values={90: -10.0},
            yhat_lower_values={90: -15.0},
            yhat_upper_values={90: -5.0},
        )

        with (
            patch("builtins.open", MagicMock()),
            patch("backend.tools.forecasting.model_from_json", return_value=large_cap_model),
            patch("backend.tools.forecasting.Path.exists", return_value=True),
        ):
            results = await predict_forecast(mv, AsyncMock(), horizons=[90])

        assert results[0].predicted_price == round(5.0, 2)

    @pytest.mark.regression
    @pytest.mark.asyncio
    async def test_warning_logged_when_flooring_occurs(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """logger.warning() is emitted with ticker, horizon, raw values, and floor when clamping.

        Verifies that when any of yhat/yhat_lower/yhat_upper falls below the price
        floor, a WARNING-level log entry is produced containing the ticker symbol,
        the horizon in days, the raw predicted values, and the floor value.
        """
        import logging

        last_price = 100.0  # floor = max(0.01, 100.0 * 0.01) = 1.00

        model = _make_mock_model(
            last_training_price=last_price,
            yhat_values={90: -5.0, 180: 150.0, 270: 160.0},
            yhat_lower_values={90: -20.0, 180: 130.0, 270: 140.0},
            yhat_upper_values={90: 5.0, 180: 170.0, 270: 180.0},
        )

        mv = _make_model_version(ticker="TSLA")

        with (
            patch("builtins.open", MagicMock()),
            patch("backend.tools.forecasting.model_from_json", return_value=model),
            patch("backend.tools.forecasting.Path.exists", return_value=True),
            caplog.at_level(logging.WARNING, logger="backend.tools.forecasting"),
        ):
            await predict_forecast(mv, AsyncMock(), horizons=[90, 180, 270])

        warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warning_records) == 1, (
            f"Expected 1 warning (horizon 90 triggers floor), got {len(warning_records)}"
        )

        msg = warning_records[0].message
        assert "TSLA" in msg
        assert "90" in msg
        assert "-5.0" in msg or "-5." in msg  # raw yhat value present
        assert "-20.0" in msg or "-20." in msg  # raw yhat_lower value present
        assert "1.0" in msg  # floor value (1.00) present

    @pytest.mark.regression
    @pytest.mark.asyncio
    async def test_no_warning_logged_when_no_flooring_occurs(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """No WARNING is emitted when all predicted values are above the price floor.

        Verifies that the warning is only produced when clamping is actually applied,
        not for normal predictions that stay above the floor threshold.
        """
        import logging

        last_price = 200.0  # floor = max(0.01, 200.0 * 0.01) = 2.00

        model = _make_mock_model(
            last_training_price=last_price,
            yhat_values={90: 210.0, 180: 220.0, 270: 230.0},
            yhat_lower_values={90: 195.0, 180: 205.0, 270: 215.0},
            yhat_upper_values={90: 225.0, 180: 235.0, 270: 245.0},
        )

        mv = _make_model_version(ticker="AAPL")

        with (
            patch("builtins.open", MagicMock()),
            patch("backend.tools.forecasting.model_from_json", return_value=model),
            patch("backend.tools.forecasting.Path.exists", return_value=True),
            caplog.at_level(logging.WARNING, logger="backend.tools.forecasting"),
        ):
            await predict_forecast(mv, AsyncMock(), horizons=[90, 180, 270])

        warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warning_records) == 0, (
            f"Expected no warnings when all values exceed floor, got {len(warning_records)}"
        )

    @pytest.mark.regression
    @pytest.mark.asyncio
    async def test_model_without_history_uses_absolute_minimum_floor(self) -> None:
        """Model with no history attribute falls back to absolute minimum floor (0.01)."""
        model = _make_mock_model(
            last_training_price=100.0,
            yhat_values={90: -1.0},
            yhat_lower_values={90: -2.0},
            yhat_upper_values={90: -0.5},
        )
        # Remove history attribute to simulate missing history
        del model.history

        mv = _make_model_version()

        with (
            patch("builtins.open", MagicMock()),
            patch("backend.tools.forecasting.model_from_json", return_value=model),
            patch("backend.tools.forecasting.Path.exists", return_value=True),
        ):
            results = await predict_forecast(mv, AsyncMock(), horizons=[90])

        # last_known_price=0.0 → floor=max(0.01, 0.0*0.01)=0.01
        assert results[0].predicted_price == 0.01
        assert results[0].predicted_lower == 0.01
        assert results[0].predicted_upper == 0.01
