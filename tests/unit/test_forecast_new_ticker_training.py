"""Tests for nightly forecast dispatch of new-ticker training (KAN-404).

Verifies that _forecast_refresh_async() Phase 2 correctly:
- Dispatches retrain_single_ticker_task for tickers with enough data but no HistoricalFeature row
- Skips tickers with < MIN_DATA_POINTS price data
- Caps dispatches at MAX_NEW_MODELS_PER_NIGHT (100)
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.tasks.forecasting import MAX_NEW_MODELS_PER_NIGHT, _forecast_refresh_async
from tests.unit.tasks._tracked_helper_bypass import bypass_tracked


def _make_model_version(ticker: str) -> MagicMock:
    """Create a mock active ModelVersion for a given ticker.

    Uses model_type="lightgbm_60d" (parseable horizon) and no artifact_b64 so
    Phase 1 prediction is skipped — tests focus exclusively on Phase 2 dispatch.

    Args:
        ticker: Stock ticker symbol the model version belongs to.

    Returns:
        MagicMock with id, ticker, is_active, model_type, and hyperparameters set.
    """
    mv = MagicMock()
    mv.id = uuid.uuid4()
    mv.ticker = ticker
    mv.is_active = True
    mv.model_type = "lightgbm_60d"
    mv.hyperparameters = None  # No artifact → Phase 1 skips all predictions
    return mv


def _make_db_session(
    active_models: list,
    feature_tickers: list[str] | None = None,
) -> tuple[MagicMock, MagicMock]:
    """Build a mock async DB session with ordered side_effect for multiple execute() calls.

    The new _forecast_refresh_async() issues these execute() calls in order:
      1. select(ModelVersion).where(is_active) — scalars().all() → active_models
      2. select(HistoricalFeature).distinct(...) — scalars().all() → feature rows
      3. select(StockPrice.ticker, StockPrice.close).distinct(...) — .all() → prices

    Note: get_all_referenced_tickers(db) and _get_price_data_counts() are patched
    separately and do NOT add execute() calls here.

    Args:
        active_models: List of ModelVersion mocks for the first execute() call.
        feature_tickers: Tickers that should appear to have HistoricalFeature rows.
            Defaults to the ticker of the first active_model (i.e. the "known" ticker).

    Returns:
        Tuple of (mock_session_ctx, mock_db) for use in patches.
    """
    if feature_tickers is None:
        feature_tickers = [mv.ticker for mv in active_models]

    # Result 1: ModelVersion query — uses scalars().all()
    mock_mv_result = MagicMock()
    mock_mv_result.scalars.return_value.all.return_value = active_models

    # Result 2: HistoricalFeature DISTINCT ON query — uses scalars().all()
    # Each "row" needs a .ticker attribute so the dict comprehension builds correctly.
    feat_rows = []
    for t in feature_tickers:
        row = MagicMock()
        row.ticker = t
        feat_rows.append(row)
    mock_feat_result = MagicMock()
    mock_feat_result.scalars.return_value.all.return_value = feat_rows

    # Result 3: StockPrice DISTINCT ON query — uses .all() (no .scalars())
    price_rows = []
    for t in feature_tickers:
        row = MagicMock()
        row.ticker = t
        row.close = 150.0
        price_rows.append(row)
    mock_price_result = MagicMock()
    mock_price_result.all.return_value = price_rows

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=[mock_mv_result, mock_feat_result, mock_price_result])
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

        A ticker returned by get_all_referenced_tickers() but absent from
        HistoricalFeature rows is identified as a "new ticker" and receives a
        Celery dispatch when it has sufficient price history (>= MIN_DATA_POINTS).
        """
        existing_mv = _make_model_version("AAPL")
        new_ticker = "NVDA"
        # feature_tickers=["AAPL"] so NVDA has no feature row → triggers Phase 2
        mock_session_ctx, _ = _make_db_session([existing_mv], feature_tickers=["AAPL"])

        with (
            patch(
                "backend.database.async_session_factory",
                return_value=mock_session_ctx,
            ),
            patch(
                "backend.tasks.forecasting._runner.record_ticker_success",
                new_callable=AsyncMock,
            ),
            patch(
                "backend.tasks.forecasting.get_all_referenced_tickers",
                new_callable=AsyncMock,
                return_value=["AAPL", new_ticker],
            ),
            patch(
                "backend.tasks.forecasting._get_price_data_counts",
                new_callable=AsyncMock,
                return_value={new_ticker: 250},  # Above MIN_DATA_POINTS=200
            ),
            patch("backend.tasks.forecasting.retrain_single_ticker_task") as mock_retrain_task,
            patch("backend.tasks.forecasting.mark_stages_updated", new_callable=AsyncMock),
        ):
            result = await bypass_tracked(_forecast_refresh_async)(run_id=uuid.uuid4())

        mock_retrain_task.delay.assert_called_once_with(new_ticker)
        # Phase 1 skipped predictions (no artifact_b64) but still counted AAPL as
        # "refreshed" because it had both a feature row and a price row.
        assert result["refreshed"] == 1

    @pytest.mark.asyncio
    async def test_skips_ticker_with_insufficient_data(self) -> None:
        """Does not dispatch training for a ticker with < MIN_DATA_POINTS price data points.

        If the pre-flight data check finds fewer than 200 data points, the ticker
        must be skipped to avoid a guaranteed training failure.
        """
        existing_mv = _make_model_version("AAPL")
        new_ticker = "NEWCO"
        mock_session_ctx, _ = _make_db_session([existing_mv], feature_tickers=["AAPL"])

        with (
            patch(
                "backend.database.async_session_factory",
                return_value=mock_session_ctx,
            ),
            patch(
                "backend.tasks.forecasting._runner.record_ticker_success",
                new_callable=AsyncMock,
            ),
            patch(
                "backend.tasks.forecasting.get_all_referenced_tickers",
                new_callable=AsyncMock,
                return_value=["AAPL", new_ticker],
            ),
            patch(
                "backend.tasks.forecasting._get_price_data_counts",
                new_callable=AsyncMock,
                return_value={new_ticker: 50},  # Below MIN_DATA_POINTS=200
            ),
            patch("backend.tasks.forecasting.retrain_single_ticker_task") as mock_retrain_task,
            patch("backend.tasks.forecasting.mark_stages_updated", new_callable=AsyncMock),
        ):
            result = await bypass_tracked(_forecast_refresh_async)(run_id=uuid.uuid4())

        mock_retrain_task.delay.assert_not_called()
        # AAPL had a feature row + price row so it's counted as refreshed even though
        # no artifact_b64 meant no actual prediction was produced.
        assert result["refreshed"] == 1

    @pytest.mark.asyncio
    async def test_caps_dispatch_at_max_new_models_per_night(self) -> None:
        """Dispatches at most MAX_NEW_MODELS_PER_NIGHT (100) new-ticker training tasks per run.

        When there are more new tickers than the nightly cap, only the first 100
        should be dispatched to prevent overloading Celery workers in a single run.
        """
        existing_mv = _make_model_version("AAPL")

        # 120 new tickers, all with enough data — only 100 should be dispatched
        new_tickers = [f"TICK{i:03d}" for i in range(120)]
        all_tickers = ["AAPL"] + new_tickers
        # Only AAPL has feature rows; all new_tickers are "new" (no feature row)
        mock_session_ctx, _ = _make_db_session([existing_mv], feature_tickers=["AAPL"])

        with (
            patch(
                "backend.database.async_session_factory",
                return_value=mock_session_ctx,
            ),
            patch(
                "backend.tasks.forecasting._runner.record_ticker_success",
                new_callable=AsyncMock,
            ),
            patch(
                "backend.tasks.forecasting.get_all_referenced_tickers",
                new_callable=AsyncMock,
                return_value=all_tickers,
            ),
            patch(
                "backend.tasks.forecasting._get_price_data_counts",
                new_callable=AsyncMock,
                return_value={t: 300 for t in new_tickers},  # All tickers have sufficient data
            ),
            patch("backend.tasks.forecasting.retrain_single_ticker_task") as mock_retrain_task,
            patch("backend.tasks.forecasting.mark_stages_updated", new_callable=AsyncMock),
        ):
            result = await bypass_tracked(_forecast_refresh_async)(run_id=uuid.uuid4())

        assert mock_retrain_task.delay.call_count == MAX_NEW_MODELS_PER_NIGHT
        dispatched_tickers = {call.args[0] for call in mock_retrain_task.delay.call_args_list}
        assert dispatched_tickers.issubset(set(new_tickers))
        # Only AAPL had feature+price rows, so Phase 1 counted exactly 1 refreshed ticker.
        assert result["refreshed"] == 1

    @pytest.mark.asyncio
    async def test_phase2_exception_does_not_break_phase1_results(self) -> None:
        """Phase 2 exception in _get_price_data_counts is caught — Phase 1 results preserved.

        If _get_price_data_counts raises during Phase 2, the try/except block at
        line 348 of forecasting.py swallows the exception and the function returns
        Phase 1 results intact (refreshed == 0 since no artifact was present).
        """
        existing_mv = _make_model_version("AAPL")
        new_ticker = "NVDA"
        mock_session_ctx, _ = _make_db_session([existing_mv], feature_tickers=["AAPL"])

        with (
            patch(
                "backend.database.async_session_factory",
                return_value=mock_session_ctx,
            ),
            patch(
                "backend.tasks.forecasting._runner.record_ticker_success",
                new_callable=AsyncMock,
            ),
            patch(
                "backend.tasks.forecasting.get_all_referenced_tickers",
                new_callable=AsyncMock,
                return_value=["AAPL", new_ticker],
            ),
            patch(
                "backend.tasks.forecasting._get_price_data_counts",
                new_callable=AsyncMock,
                side_effect=Exception("DB connection lost"),
            ),
            patch("backend.tasks.forecasting.retrain_single_ticker_task") as mock_retrain_task,
            patch("backend.tasks.forecasting.mark_stages_updated", new_callable=AsyncMock),
        ):
            # Should NOT raise — Phase 2 exception is caught by the try/except at line 348
            result = await bypass_tracked(_forecast_refresh_async)(run_id=uuid.uuid4())

        # Phase 1 completed normally (refreshed == 1 for AAPL); Phase 2 failure did not propagate
        assert result["refreshed"] == 1
        # No new-ticker dispatch should have occurred
        mock_retrain_task.delay.assert_not_called()
