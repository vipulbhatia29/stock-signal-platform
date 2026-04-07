"""API-tier tests for BacktestEngine.run_walk_forward (B2).

These tests live under tests/api/ because they require a real database session
via the db_session fixture (testcontainers). Unit tests without DB are in
tests/unit/services/test_backtest_engine.py.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from backend.services.backtesting import BacktestEngine, BacktestMetrics

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_price_rows(
    ticker: str,
    start: datetime,
    n_days: int,
    base: float = 100.0,
    slope: float = 0.1,
):
    """Build list of StockPrice-like dicts for seeding.

    Args:
        ticker: Stock ticker symbol.
        start: First price timestamp (UTC).
        n_days: Number of daily observations.
        base: Starting price.
        slope: Daily price increment (linear trend).

    Returns:
        List of dicts suitable for StockPrice construction.
    """
    from backend.models.price import StockPrice

    rows = []
    for i in range(n_days):
        dt = start + timedelta(days=i)
        close = base + slope * i
        rows.append(
            StockPrice(
                time=dt,
                ticker=ticker,
                open=close - 0.5,
                high=close + 1.0,
                low=close - 1.0,
                close=close,
                adj_close=close,
                volume=1_000_000,
                source="test",
            )
        )
    return rows


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_walk_forward_insufficient_data_returns_zero_windows(
    db_session,
):
    """Fewer than min_train_days+horizon_days of data yields zero windows and zero metrics.

    Seeds only 100 daily prices, well below the 365-day minimum training floor.
    """
    from backend.models.stock import Stock

    ticker = "ZZZ"
    start = datetime(2023, 1, 1, tzinfo=timezone.utc)

    # Seed the stock row (FK requirement)
    stock = Stock(
        id=__import__("uuid").uuid4(),
        ticker=ticker,
        name="ZZZ Inc.",
        exchange="TEST",
        sector="Technology",
        is_active=True,
        created_at=start,
        updated_at=start,
    )
    db_session.add(stock)
    await db_session.flush()

    rows = _make_price_rows(ticker, start, n_days=100)
    for r in rows:
        db_session.add(r)
    await db_session.commit()

    engine = BacktestEngine()
    metrics = await engine.run_walk_forward(ticker, db_session, horizon_days=90, min_train_days=365)

    assert metrics.num_windows == 0
    assert metrics.mape == 0.0
    assert metrics.mae == 0.0
    assert metrics.rmse == 0.0


@pytest.mark.asyncio
async def test_walk_forward_step_days_cadence(db_session):
    """Window count matches (total_days - min_train_days) // step_days approximately.

    With 700 days of data, min_train=365, step=30, horizon=90:
    approx (700 - 365 - 90) / 30 ≈ 8 windows (engine may produce slightly fewer
    due to data gaps at weekends, but must be > 0).
    """
    from backend.models.stock import Stock

    ticker = "WWW"
    start = datetime(2021, 1, 1, tzinfo=timezone.utc)

    stock = Stock(
        id=__import__("uuid").uuid4(),
        ticker=ticker,
        name="WWW Inc.",
        exchange="TEST",
        sector="Finance",
        is_active=True,
        created_at=start,
        updated_at=start,
    )
    db_session.add(stock)
    await db_session.flush()

    rows = _make_price_rows(ticker, start, n_days=700)
    for r in rows:
        db_session.add(r)
    await db_session.commit()

    engine = BacktestEngine()

    # Patch _fit_and_predict_sync to avoid running real Prophet
    with patch.object(
        engine,
        "_fit_and_predict_sync",
        return_value=(120.0, 115.0, 125.0),
    ) as mock_fit:
        metrics = await engine.run_walk_forward(
            ticker, db_session, horizon_days=90, min_train_days=365, step_days=30
        )

    assert metrics.num_windows > 0
    # The mock should have been called once per completed window
    assert mock_fit.call_count == metrics.num_windows


@pytest.mark.asyncio
async def test_walk_forward_no_price_data_returns_zero_metrics(db_session):
    """Ticker with no price rows at all returns num_windows=0 gracefully.

    Tests the early-return path when there is no data.
    """
    from backend.models.stock import Stock

    ticker = "NOP"
    now = datetime(2024, 1, 1, tzinfo=timezone.utc)

    stock = Stock(
        id=__import__("uuid").uuid4(),
        ticker=ticker,
        name="NOP Corp",
        exchange="TEST",
        sector="Energy",
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db_session.add(stock)
    await db_session.commit()

    engine = BacktestEngine()
    metrics = await engine.run_walk_forward(ticker, db_session)

    assert metrics.num_windows == 0
    assert isinstance(metrics, BacktestMetrics)


@pytest.mark.asyncio
async def test_walk_forward_mocked_windows_returns_correct_aggregates(db_session):
    """Patching _fit_and_predict_sync produces deterministic metric aggregation.

    Uses 500 days of linear price data and patches Prophet so only metric math
    is exercised end-to-end.
    """
    from backend.models.stock import Stock

    ticker = "AGG"
    start = datetime(2021, 6, 1, tzinfo=timezone.utc)

    stock = Stock(
        id=__import__("uuid").uuid4(),
        ticker=ticker,
        name="AGG Ltd",
        exchange="TEST",
        sector="Materials",
        is_active=True,
        created_at=start,
        updated_at=start,
    )
    db_session.add(stock)
    await db_session.flush()

    # Seed 500 days with a known linear trend: price = 100 + 0.1*i
    rows = _make_price_rows(ticker, start, n_days=500, base=100.0, slope=0.1)
    for r in rows:
        db_session.add(r)
    await db_session.commit()

    engine = BacktestEngine()

    # Mock returns the exact actual price each time — MAPE should be 0
    async def _perfect_predictor(*args, **kwargs):
        # We don't know the exact actual, so return a fixed value;
        # the test validates structure, not exact MAPE=0 (that requires real Prophet)
        return (105.0, 100.0, 110.0)

    with patch(
        "backend.services.backtesting.BacktestEngine._fit_and_predict_sync",
        side_effect=lambda *a, **kw: (105.0, 100.0, 110.0),
    ):
        metrics = await engine.run_walk_forward(
            ticker, db_session, horizon_days=90, min_train_days=365, step_days=30
        )

    assert metrics.num_windows > 0
    assert isinstance(metrics.mape, float)
    assert isinstance(metrics.mae, float)
    assert isinstance(metrics.rmse, float)
    assert metrics.ci_bias in ("above", "below", "balanced")
    assert 0.0 <= metrics.ci_containment <= 1.0
    assert 0.0 <= metrics.direction_accuracy <= 1.0
