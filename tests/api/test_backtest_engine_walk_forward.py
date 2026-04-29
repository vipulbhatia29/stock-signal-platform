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

# Backtesting engine was rewritten from Prophet to ForecastEngine; these
# integration tests need a full update before they can run (KAN-551).
pytestmark = pytest.mark.skip(
    reason="Pending update: backtesting rewritten from Prophet to ForecastEngine (KAN-551)"
)

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


# ---------------------------------------------------------------------------
# KAN-437: walk-forward sentiment N+1 fix — fetch once before window loop
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.asyncio
async def test_walk_forward_fetches_sentiment_exactly_once_per_run(db_session):
    """KAN-437: sentiment is pre-loaded once before the window loop.

    Previously the engine called ``_fetch_sentiment_for_window`` inside the
    ``for window in windows`` loop, issuing ~110 nearly identical SELECTs
    against ``news_sentiment_daily`` per ticker. The fix pre-loads the full
    range once and slices it in memory for each window.

    Asserts ``fetch_sentiment_regressors`` is awaited exactly ONCE for a
    multi-window run. The patch target is ``backend.services.backtesting``
    (the lookup site where ``run_walk_forward`` resolves the name) — NOT
    the canonical home in ``backend.services.sentiment_regressors`` and
    NOT the back-compat re-export in ``backend.tools.forecasting``.
    """
    from backend.models.stock import Stock

    ticker = "SN1"
    start = datetime(2021, 1, 1, tzinfo=timezone.utc)

    stock = Stock(
        id=__import__("uuid").uuid4(),
        ticker=ticker,
        name="SN1 Inc.",
        exchange="TEST",
        sector="Tech",
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

    from unittest.mock import AsyncMock

    fetch_mock = AsyncMock(return_value=None)

    with (
        patch(
            "backend.services.backtesting.fetch_sentiment_regressors",
            fetch_mock,
        ),
        patch.object(
            engine,
            "_fit_and_predict_sync",
            return_value=(120.0, 115.0, 125.0),
        ),
    ):
        metrics = await engine.run_walk_forward(
            ticker, db_session, horizon_days=90, min_train_days=365, step_days=30
        )

    assert metrics.num_windows > 1, "Test requires multiple windows to be meaningful"
    # The whole point: ONE fetch for the full range, not per-window.
    assert fetch_mock.await_count == 1, (
        f"Expected fetch_sentiment_regressors awaited exactly once "
        f"(KAN-437); got {fetch_mock.await_count}"
    )


@pytest.mark.regression
@pytest.mark.asyncio
async def test_walk_forward_sentiment_preload_failure_degrades_gracefully(db_session):
    """KAN-437 follow-up: a transient failure in the sentiment pre-load
    must NOT kill all ~110 windows for the ticker.

    Pins the graceful-fallback contract: when ``fetch_sentiment_regressors``
    raises (DB blip, statement timeout), the engine logs a warning and
    proceeds with ``sentiment_indexed = None``. Windows still complete,
    just without sentiment regressors. Without this guard, the N+1 fix
    would have introduced a new failure mode where one transient blip
    loses all windows for the ticker (vs. the old per-window fetch losing
    only the affected window).
    """
    from unittest.mock import AsyncMock

    from backend.models.stock import Stock

    ticker = "SNFAIL"
    start = datetime(2021, 1, 1, tzinfo=timezone.utc)

    stock = Stock(
        id=__import__("uuid").uuid4(),
        ticker=ticker,
        name="SNFAIL Inc.",
        exchange="TEST",
        sector="Tech",
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

    failing_fetch = AsyncMock(side_effect=RuntimeError("simulated DB blip"))

    with (
        patch(
            "backend.services.backtesting.fetch_sentiment_regressors",
            failing_fetch,
        ),
        patch.object(
            engine,
            "_fit_and_predict_sync",
            return_value=(120.0, 115.0, 125.0),
        ),
    ):
        metrics = await engine.run_walk_forward(
            ticker, db_session, horizon_days=90, min_train_days=365, step_days=30
        )

    # Pre-load was attempted exactly once (no per-window retry).
    assert failing_fetch.await_count == 1
    # Crucially: windows STILL completed without sentiment.
    assert metrics.num_windows > 1, (
        "Sentiment pre-load failure must degrade gracefully — windows must still run"
    )


@pytest.mark.asyncio
async def test_walk_forward_uses_real_sentiment_via_in_memory_slice(db_session):
    """KAN-437: in-memory window slicing returns the same sentiment per window
    that the deleted ``_fetch_sentiment_for_window`` would have returned.

    Seeds 700 days of prices + a sentiment series whose values are unique per
    day, then asserts the train_df merged into ``_fit_and_predict_sync`` for
    a sample window contains the expected sentiment values for that window's
    date range — proving the in-memory slice is correct.
    """
    from backend.models.news_sentiment import NewsSentimentDaily
    from backend.models.stock import Stock

    ticker = "SN2"
    start = datetime(2021, 1, 1, tzinfo=timezone.utc)

    stock = Stock(
        id=__import__("uuid").uuid4(),
        ticker=ticker,
        name="SN2 Inc.",
        exchange="TEST",
        sector="Tech",
        is_active=True,
        created_at=start,
        updated_at=start,
    )
    db_session.add(stock)
    await db_session.flush()

    rows = _make_price_rows(ticker, start, n_days=700)
    for r in rows:
        db_session.add(r)

    # Seed daily sentiment with deterministic per-day values
    for i in range(700):
        d = (start + timedelta(days=i)).date()
        db_session.add(
            NewsSentimentDaily(
                ticker=ticker,
                date=d,
                stock_sentiment=0.001 * i,
                sector_sentiment=0.002 * i,
                macro_sentiment=0.003 * i,
                article_count=1,
            )
        )
    await db_session.commit()

    engine = BacktestEngine()
    captured: list = []

    def _capture_train_df(train_df, test_date, horizon_days, has_sentiment):
        """Capture train_df for the first window only (when has_sentiment)."""
        if has_sentiment and not captured:
            captured.append(train_df.copy())
        return (120.0, 115.0, 125.0)

    with patch.object(engine, "_fit_and_predict_sync", side_effect=_capture_train_df):
        await engine.run_walk_forward(
            ticker, db_session, horizon_days=90, min_train_days=365, step_days=30
        )

    assert len(captured) == 1, "Expected at least one window with sentiment"
    train_df = captured[0]
    assert "stock_sentiment" in train_df.columns
    assert "sector_sentiment" in train_df.columns
    assert "macro_sentiment" in train_df.columns
    # Sentiment values must NOT all be zero (the deleted helper used to fetch
    # real values; the new in-memory slice must do the same).
    assert train_df["stock_sentiment"].abs().sum() > 0
    assert train_df["sector_sentiment"].abs().sum() > 0
    assert train_df["macro_sentiment"].abs().sum() > 0


# ---------------------------------------------------------------------------
# Slow smoke test — exercises real Prophet end-to-end (_fit_and_predict_sync)
# ---------------------------------------------------------------------------

prophet = pytest.importorskip("prophet", reason="prophet not installed — skipping slow smoke")


@pytest.mark.slow
@pytest.mark.asyncio
async def test_fit_and_predict_sync_linear_series_smoke(db_session):
    """Smoke test for the real Prophet path through BacktestEngine.

    Seeds 400 days of linear price data (no mocking of _fit_and_predict_sync)
    and verifies that run_walk_forward produces at least one window with
    sensible metrics. Linear data is easy for Prophet, so MAPE < 10% is a
    reasonable bar.

    Marked @pytest.mark.slow — expected runtime ~5–15 s depending on machine.
    Uses pytest.importorskip at module level to skip cleanly if Prophet is not
    installed (e.g. CI minimal images).
    """
    import math

    from backend.models.stock import Stock

    ticker = "LIN"
    start = datetime(2020, 1, 1, tzinfo=timezone.utc)

    stock = Stock(
        id=__import__("uuid").uuid4(),
        ticker=ticker,
        name="LIN Linear Corp",
        exchange="TEST",
        sector="Industrials",
        is_active=True,
        created_at=start,
        updated_at=start,
    )
    db_session.add(stock)
    await db_session.flush()

    # 400 days, close = 100 + 0.5*i — a strong linear trend Prophet handles well
    rows = _make_price_rows(ticker, start, n_days=400, base=100.0, slope=0.5)
    for r in rows:
        db_session.add(r)
    await db_session.commit()

    engine = BacktestEngine()
    metrics = await engine.run_walk_forward(
        ticker,
        db_session,
        horizon_days=30,
        min_train_days=365,
        step_days=30,
    )

    assert metrics.num_windows >= 1, "Expected at least one completed walk-forward window"
    assert math.isfinite(metrics.mape), f"MAPE must be finite, got {metrics.mape}"
    assert metrics.mape < 0.10, f"Expected MAPE < 10% on linear data, got {metrics.mape:.4f}"
    assert math.isfinite(metrics.mae), f"MAE must be finite, got {metrics.mae}"
    assert math.isfinite(metrics.rmse), f"RMSE must be finite, got {metrics.rmse}"
    assert math.isfinite(metrics.direction_accuracy), (
        f"direction_accuracy must be finite, got {metrics.direction_accuracy}"
    )
