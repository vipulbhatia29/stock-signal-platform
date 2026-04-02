"""Unit tests for BacktestRun model instantiation."""

import uuid
from datetime import date

from backend.models.backtest import BacktestRun


def test_backtest_run_instantiation():
    run = BacktestRun(
        id=uuid.uuid4(),
        ticker="AAPL",
        model_version_id=uuid.uuid4(),
        config_label="baseline",
        train_start=date(2022, 1, 1),
        train_end=date(2023, 12, 31),
        test_start=date(2024, 1, 1),
        test_end=date(2024, 12, 31),
        horizon_days=90,
        num_windows=12,
        mape=0.08,
        mae=15.2,
        rmse=18.5,
        direction_accuracy=0.64,
        ci_containment=0.78,
        market_regime="bull",
        metadata_={"ci_bias": "above", "avg_interval_width": 0.15},
    )
    assert run.ticker == "AAPL"
    assert run.mape == 0.08
    assert run.config_label == "baseline"
    assert run.metadata_ == {"ci_bias": "above", "avg_interval_width": 0.15}


def test_backtest_run_repr():
    run = BacktestRun(ticker="TSLA", horizon_days=180, mape=0.123)
    assert "TSLA" in repr(run)
    assert "180" in repr(run)
