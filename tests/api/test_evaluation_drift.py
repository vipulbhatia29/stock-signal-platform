"""Regression test: drift detection reads BacktestRun rows when populated (B2.5).

Verifies that _check_drift_async calls compute_calibrated_threshold with the
actual backtest MAPE seeded in the DB, not with the fallback None value.

This test lives under tests/api/ because it requires db_session.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.tasks.evaluation import DRIFT_FALLBACK_THRESHOLD, compute_calibrated_threshold

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_stock_model_and_backtest(
    session,
    ticker: str,
    mape: float,
) -> None:
    """Seed Stock, ModelVersion (active, with rolling_mape), and BacktestRun.

    Args:
        session: Async database session.
        ticker: Stock ticker symbol.
        mape: MAPE value to store in the BacktestRun row.
    """
    from backend.models.backtest import BacktestRun
    from backend.models.forecast import ModelVersion
    from backend.models.stock import Stock

    now = datetime.now(timezone.utc)

    stock_id = uuid.uuid4()
    session.add(
        Stock(
            id=stock_id,
            ticker=ticker,
            name=f"{ticker} Corp",
            exchange="TEST",
            sector="Technology",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
    )
    await session.flush()

    mv_id = uuid.uuid4()
    # Rolling MAPE above the calibrated threshold so drift fires
    rolling_mape = mape * 2.0  # e.g. 2× the backtest baseline → always triggers
    session.add(
        ModelVersion(
            id=mv_id,
            ticker=ticker,
            model_type="prophet",
            version=1,
            is_active=True,
            trained_at=now,
            training_data_start=date(2022, 1, 1),
            training_data_end=date(2023, 12, 31),
            data_points=500,
            status="active",
            metrics={"rolling_mape": rolling_mape},
        )
    )
    await session.flush()

    session.add(
        BacktestRun(
            id=uuid.uuid4(),
            ticker=ticker,
            model_version_id=mv_id,
            config_label="walk_forward",
            train_start=date(2022, 1, 1),
            train_end=date(2023, 12, 31),
            test_start=date(2024, 1, 1),
            test_end=date(2024, 12, 31),
            horizon_days=90,
            num_windows=10,
            mape=mape,
            mae=5.0,
            rmse=7.0,
            direction_accuracy=0.60,
            ci_containment=0.78,
        )
    )
    await session.flush()


# ---------------------------------------------------------------------------
# Regression test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.regression
async def test_drift_detection_uses_backtest_mapes_when_rows_exist(db_session):
    """compute_calibrated_threshold receives the seeded backtest MAPE, not None.

    Seeds a BacktestRun for DRF1 with mape=0.08 (8%).
    Runs _check_drift_async with async_session_factory mocked to use db_session.
    Asserts compute_calibrated_threshold is called with 0.08 (not None / fallback).

    The fallback threshold is 0.20; a 0.08 baseline gives 0.12 threshold.
    By seeding rolling_mape = 0.16 (> 0.12 calibrated), drift is triggered,
    which means compute_calibrated_threshold must have received the real MAPE.
    """
    ticker = "DRF1"
    seeded_mape = 0.08
    await _seed_stock_model_and_backtest(db_session, ticker, mape=seeded_mape)
    await db_session.commit()

    # Patch _check_vix_regime and retrain dispatch to keep the test self-contained
    with (
        patch(
            "backend.tasks.evaluation._check_vix_regime",
            new_callable=AsyncMock,
            return_value="normal",
        ),
        patch(
            "backend.tasks.forecasting.retrain_single_ticker_task",
        ),
        patch(
            "backend.tasks.evaluation.async_session_factory",
        ) as mock_factory,
        patch(
            "backend.tasks.evaluation.compute_calibrated_threshold",
            wraps=compute_calibrated_threshold,
        ) as spy_threshold,
    ):
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=db_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value = mock_cm

        from backend.tasks.evaluation import _check_drift_async

        await _check_drift_async()

    # compute_calibrated_threshold must have been called with the seeded MAPE
    assert spy_threshold.call_count >= 1, "compute_calibrated_threshold was never called"
    called_args = [call.args[0] for call in spy_threshold.call_args_list]
    # At least one call should have received our seeded_mape (not None)
    assert any(arg is not None and abs(arg - seeded_mape) < 1e-6 for arg in called_args), (
        f"Expected compute_calibrated_threshold to be called with {seeded_mape}, "
        f"but got calls with: {called_args}. "
        f"This indicates the drift query is NOT reading BacktestRun rows."
    )


@pytest.mark.asyncio
@pytest.mark.regression
async def test_drift_uses_fallback_when_no_backtest_rows_exist(db_session):
    """compute_calibrated_threshold receives None when no BacktestRun rows exist.

    Seeds a ModelVersion with rolling_mape but NO BacktestRun row for DRF2.
    Asserts compute_calibrated_threshold is called with None, triggering the
    0.20 fallback rather than a calibrated threshold.
    """
    from backend.models.forecast import ModelVersion
    from backend.models.stock import Stock

    ticker = "DRF2"
    now = datetime.now(timezone.utc)

    db_session.add(
        Stock(
            id=uuid.uuid4(),
            ticker=ticker,
            name="DRF2 Corp",
            exchange="TEST",
            sector="Finance",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
    )
    await db_session.flush()
    db_session.add(
        ModelVersion(
            id=uuid.uuid4(),
            ticker=ticker,
            model_type="prophet",
            version=1,
            is_active=True,
            trained_at=now,
            training_data_start=date(2022, 1, 1),
            training_data_end=date(2023, 12, 31),
            data_points=500,
            status="active",
            metrics={"rolling_mape": 0.25},  # above fallback threshold
        )
    )
    await db_session.commit()

    with (
        patch(
            "backend.tasks.evaluation._check_vix_regime",
            new_callable=AsyncMock,
            return_value="normal",
        ),
        patch("backend.tasks.forecasting.retrain_single_ticker_task"),
        patch(
            "backend.tasks.evaluation.async_session_factory",
        ) as mock_factory,
        patch(
            "backend.tasks.evaluation.compute_calibrated_threshold",
            wraps=compute_calibrated_threshold,
        ) as spy_threshold,
    ):
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=db_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value = mock_cm

        from backend.tasks.evaluation import _check_drift_async

        await _check_drift_async()

    assert spy_threshold.call_count >= 1
    called_args = [call.args[0] for call in spy_threshold.call_args_list]
    # With no BacktestRun rows, arg should be None → fallback used
    assert any(arg is None for arg in called_args), (
        f"Expected at least one call with None (fallback path), but got calls with: {called_args}"
    )
    # And the fallback threshold should be 0.20
    assert compute_calibrated_threshold(None) == DRIFT_FALLBACK_THRESHOLD
