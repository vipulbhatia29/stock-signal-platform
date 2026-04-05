"""Tests for nightly forecast dispatch of new-ticker training (KAN-404).

Verifies that _forecast_refresh_async() Phase 2 correctly:
- Dispatches retrain_single_ticker_task for tickers with enough data but no ModelVersion
- Skips tickers with < MIN_DATA_POINTS price data
- Caps dispatches at MAX_NEW_MODELS_PER_NIGHT (20)
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.tasks.forecasting import MAX_NEW_MODELS_PER_NIGHT, _forecast_refresh_async


def _make_model_version(ticker: str) -> MagicMock:
    """Create a mock active ModelVersion for a given ticker.

    Args:
        ticker: Stock ticker symbol the model version belongs to.

    Returns:
        MagicMock with id, ticker, is_active, and model_type set.
    """
    mv = MagicMock()
    mv.id = uuid.uuid4()
    mv.ticker = ticker
    mv.is_active = True
    mv.model_type = "prophet"
    return mv


def _make_db_session(active_models: list) -> tuple[MagicMock, MagicMock]:
    """Build a mock async DB session and session context manager.

    Args:
        active_models: List of ModelVersion mocks to return from the initial query.

    Returns:
        Tuple of (mock_session_ctx, mock_db) for use in patches.
    """
    mock_db_result = MagicMock()
    mock_db_result.scalars.return_value.all.return_value = active_models

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_db_result)
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()

    mock_session_ctx = MagicMock()
    mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
    mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

    return mock_session_ctx, mock_db


class TestForecastNewTickerDispatch:
    """Tests for Phase 2 of _forecast_refresh_async: new-ticker training dispatch."""

    @pytest.mark.asyncio
    async def test_dispatches_training_for_new_ticker_with_enough_data(self) -> None:
        """Dispatches retrain_single_ticker_task for a new ticker with >= 200 data points.

        A ticker referenced in a portfolio but absent from active_models receives
        a Celery dispatch when it has sufficient price history (>= MIN_DATA_POINTS).
        """
        existing_mv = _make_model_version("AAPL")
        new_ticker = "NVDA"
        mock_session_ctx, _ = _make_db_session([existing_mv])

        with (
            patch(
                "backend.tasks.forecasting.async_session_factory",
                return_value=mock_session_ctx,
            ),
            patch(
                "backend.tasks.forecasting._runner.start_run",
                new_callable=AsyncMock,
                return_value="run-1",
            ),
            patch(
                "backend.tasks.forecasting._runner.record_ticker_success",
                new_callable=AsyncMock,
            ),
            patch(
                "backend.tasks.forecasting._runner.complete_run",
                new_callable=AsyncMock,
                return_value="ok",
            ),
            patch("backend.tools.forecasting.predict_forecast", return_value=[]),
            patch(
                "backend.services.ticker_universe.get_all_referenced_tickers",
                new_callable=AsyncMock,
                return_value=["AAPL", new_ticker],
            ),
            patch(
                "backend.tasks.forecasting._get_price_data_counts",
                new_callable=AsyncMock,
                return_value={new_ticker: 250},  # Above MIN_DATA_POINTS=200
            ),
            patch("backend.tasks.forecasting.retrain_single_ticker_task") as mock_retrain_task,
        ):
            result = await _forecast_refresh_async()

        mock_retrain_task.delay.assert_called_once_with(new_ticker)
        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_skips_ticker_with_insufficient_data(self) -> None:
        """Does not dispatch training for a ticker with < MIN_DATA_POINTS price data points.

        If the pre-flight data check finds fewer than 200 data points, the ticker
        must be skipped to avoid a guaranteed ValueError inside train_prophet_model.
        """
        existing_mv = _make_model_version("AAPL")
        new_ticker = "NEWCO"
        mock_session_ctx, _ = _make_db_session([existing_mv])

        with (
            patch(
                "backend.tasks.forecasting.async_session_factory",
                return_value=mock_session_ctx,
            ),
            patch(
                "backend.tasks.forecasting._runner.start_run",
                new_callable=AsyncMock,
                return_value="run-1",
            ),
            patch(
                "backend.tasks.forecasting._runner.record_ticker_success",
                new_callable=AsyncMock,
            ),
            patch(
                "backend.tasks.forecasting._runner.complete_run",
                new_callable=AsyncMock,
                return_value="ok",
            ),
            patch("backend.tools.forecasting.predict_forecast", return_value=[]),
            patch(
                "backend.services.ticker_universe.get_all_referenced_tickers",
                new_callable=AsyncMock,
                return_value=["AAPL", new_ticker],
            ),
            patch(
                "backend.tasks.forecasting._get_price_data_counts",
                new_callable=AsyncMock,
                return_value={new_ticker: 50},  # Below MIN_DATA_POINTS=200
            ),
            patch("backend.tasks.forecasting.retrain_single_ticker_task") as mock_retrain_task,
        ):
            result = await _forecast_refresh_async()

        mock_retrain_task.delay.assert_not_called()
        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_caps_dispatch_at_max_new_models_per_night(self) -> None:
        """Dispatches at most MAX_NEW_MODELS_PER_NIGHT (20) new-ticker training tasks per run.

        When there are more new tickers than the nightly cap, only the first 20
        should be dispatched to prevent overloading Celery workers in a single run.
        """
        existing_mv = _make_model_version("AAPL")

        # 25 new tickers, all with enough data — only 20 should be dispatched
        new_tickers = [f"TICK{i:02d}" for i in range(25)]
        all_tickers = ["AAPL"] + new_tickers
        mock_session_ctx, _ = _make_db_session([existing_mv])

        with (
            patch(
                "backend.tasks.forecasting.async_session_factory",
                return_value=mock_session_ctx,
            ),
            patch(
                "backend.tasks.forecasting._runner.start_run",
                new_callable=AsyncMock,
                return_value="run-1",
            ),
            patch(
                "backend.tasks.forecasting._runner.record_ticker_success",
                new_callable=AsyncMock,
            ),
            patch(
                "backend.tasks.forecasting._runner.complete_run",
                new_callable=AsyncMock,
                return_value="ok",
            ),
            patch("backend.tools.forecasting.predict_forecast", return_value=[]),
            patch(
                "backend.services.ticker_universe.get_all_referenced_tickers",
                new_callable=AsyncMock,
                return_value=all_tickers,
            ),
            patch(
                "backend.tasks.forecasting._get_price_data_counts",
                new_callable=AsyncMock,
                return_value={t: 300 for t in new_tickers},  # All tickers have sufficient data
            ),
            patch("backend.tasks.forecasting.retrain_single_ticker_task") as mock_retrain_task,
        ):
            result = await _forecast_refresh_async()

        assert mock_retrain_task.delay.call_count == MAX_NEW_MODELS_PER_NIGHT
        dispatched_tickers = {call.args[0] for call in mock_retrain_task.delay.call_args_list}
        assert dispatched_tickers.issubset(set(new_tickers))
        assert result["status"] == "ok"
