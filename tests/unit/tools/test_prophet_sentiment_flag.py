"""Unit test for PROPHET_REAL_SENTIMENT_ENABLED feature flag (Spec B Final.1).

Verifies that when the flag is False the predict-time sentiment columns are
zeroed (rollback path) rather than fetching real values from the DB.

No database session is required — the test patches the model artifact I/O,
the Prophet model object, and settings so no real file or DB call is made.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest


@pytest.mark.asyncio
async def test_prophet_sentiment_flag_disabled_zeros_regressors() -> None:
    """When PROPHET_REAL_SENTIMENT_ENABLED=False, sentiment columns are zeroed.

    Uses a fully-mocked Prophet model that reports 3 sentiment regressors so
    the has_sentiment_regressors flag is True. Verifies the rollback else-branch
    runs and that the make_future_dataframe result has 0.0 for all sentiment cols.
    """

    # Build a minimal future DataFrame that the mocked model will "return"
    today = date(2026, 4, 7)
    future_dates = pd.date_range(
        start=datetime(2025, 10, 1, tzinfo=timezone.utc), periods=10, freq="D"
    )
    future_df = pd.DataFrame({"ds": future_dates})

    SENTIMENT_COLS = ["stock_sentiment", "sector_sentiment", "macro_sentiment"]

    # Prophet model mock — has 3 sentiment extra_regressors, no history (flag
    # check uses `settings.PROPHET_REAL_SENTIMENT_ENABLED` before the history
    # access, so no history is needed for the rollback path).
    mock_model = MagicMock()
    mock_model.extra_regressors = {col: {} for col in SENTIMENT_COLS}
    mock_model.make_future_dataframe.return_value = future_df.copy()

    # Capture the DataFrame passed to model.predict so we can inspect it.
    predict_calls: list[pd.DataFrame] = []

    async def fake_to_thread(fn: object, df: pd.DataFrame) -> pd.DataFrame:
        """Intercept asyncio.to_thread(model.predict, future) call."""
        predict_calls.append(df.copy())
        # Return a minimal forecast DataFrame.
        rows = []
        for ds in df["ds"]:
            rows.append(
                {
                    "ds": ds,
                    "yhat": 150.0,
                    "yhat_lower": 140.0,
                    "yhat_upper": 160.0,
                    "trend": 150.0,
                }
            )
        return pd.DataFrame(rows)

    # ModelVersion mock
    mock_mv = MagicMock()
    mock_mv.ticker = "TSLA"
    mock_mv.version = 1
    mock_mv.artifact_path = "/fake/path/model.json"
    mock_mv.training_data_start = date(2025, 1, 1)
    mock_mv.training_data_end = today

    db_mock = AsyncMock()

    with (
        patch("backend.tools.forecasting.settings") as mock_settings,
        patch("backend.tools.forecasting.Path.exists", return_value=True),
        patch("builtins.open", MagicMock()),
        patch("backend.tools.forecasting.model_from_json", return_value=mock_model),
        patch("backend.tools.forecasting.asyncio.to_thread", side_effect=fake_to_thread),
    ):
        mock_settings.PROPHET_REAL_SENTIMENT_ENABLED = False

        from backend.tools.forecasting import predict_forecast

        await predict_forecast(mock_mv, db_mock, horizons=[90])

    # The predict call must have happened exactly once (one horizon).
    assert len(predict_calls) == 1, f"Expected 1 predict call, got {len(predict_calls)}"

    called_df = predict_calls[0]

    # All three sentiment columns must exist and be zeroed — this is the
    # pre-B3 rollback behavior the flag restores for emergency use.
    for col in SENTIMENT_COLS:
        assert col in called_df.columns, f"Missing column {col} in future DataFrame"
        assert (called_df[col] == 0.0).all(), (
            f"{col} not zeroed in rollback mode; values: {called_df[col].tolist()}"
        )
