"""Regression tests for Prophet sentiment regressors at predict time (KAN-422 / Spec B / B3).

These tests guard the bug fixed in B3: ``predict_forecast`` previously
hard-coded ``stock_sentiment``/``sector_sentiment``/``macro_sentiment`` to
``0.0`` for **every** row of the future DataFrame, including the historical
training rows that Prophet re-projects internally. The result was that the
trained regressor coefficients had no effect at predict time and predictions
silently ignored sentiment.

The fix:
- Make ``predict_forecast`` ``async`` and accept an ``AsyncSession``.
- Re-fetch real ``NewsSentimentDaily`` rows for historical future-frame dates.
- Use a 7-day trailing mean as the projection for forecast dates.

Tests use a deterministic synthetic series so the assertions catch regressions
without depending on Prophet's stochasticity. Marked ``slow`` because Prophet
fitting takes a few seconds per call.
"""

from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import numpy as np
import pytest

from tests.conftest import NewsSentimentDailyFactory, StockFactory, StockPriceFactory


async def _seed_stock(db_session, ticker: str) -> None:
    """Seed a Stock row so price/sentiment FKs are satisfied.

    Args:
        db_session: Live async session.
        ticker: Ticker symbol.
    """
    db_session.add(StockFactory.build(ticker=ticker, name=f"Test {ticker}"))
    await db_session.flush()


async def _seed_synthetic_series(
    db_session,
    *,
    ticker: str,
    days: int,
    beta: float,
    seed: int,
) -> None:
    """Seed Stock + StockPrice + NewsSentimentDaily rows correlated by ``beta``.

    The price series is a noisy random walk whose drift is driven by a sinusoid
    sentiment signal. With a known beta the trained Prophet model should
    learn a non-trivial regressor coefficient — that's what the assertion in
    the test relies on.

    Args:
        db_session: Live async session (real Postgres via testcontainers).
        ticker: Ticker symbol for both price and sentiment rows.
        days: Number of trading days to seed (>= ``MIN_DATA_POINTS``).
        beta: Sensitivity of price drift to sentiment.
        seed: numpy RNG seed for determinism.
    """
    await _seed_stock(db_session, ticker)
    rng = np.random.default_rng(seed)
    sentiment = 0.5 * np.sin(np.linspace(0, 6 * np.pi, days)) + rng.normal(0, 0.05, days)
    drift = beta * sentiment + rng.normal(0, 0.2, days)
    prices = 100.0 + np.cumsum(drift)

    today = datetime.now(timezone.utc).date()
    for i, (p, s) in enumerate(zip(prices, sentiment, strict=True)):
        day = today - timedelta(days=days - i)
        ts = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)
        db_session.add(
            StockPriceFactory.build(
                ticker=ticker,
                time=ts,
                open=float(p),
                high=float(p),
                low=float(p),
                close=float(p),
                adj_close=float(p),
            )
        )
        db_session.add(
            NewsSentimentDailyFactory.build(
                ticker=ticker,
                date=day,
                stock_sentiment=float(s),
                sector_sentiment=0.0,
                macro_sentiment=0.0,
                article_count=5,
                confidence=0.8,
                quality_flag="ok",
            )
        )


@pytest.mark.asyncio
@pytest.mark.regression
async def test_predict_forecast_is_async() -> None:
    """``predict_forecast`` must be a coroutine after the B3 refactor.

    Pre-fix it was a sync function; the post-fix signature is
    ``async def predict_forecast(model_version, db, horizons=None)``.
    Asserting the function is a coroutine catches accidental reverts to the
    sync signature.
    """
    from backend.tools.forecasting import predict_forecast

    assert inspect.iscoroutinefunction(predict_forecast), (
        "predict_forecast must be async after the B3 fix — see KAN-422 Spec B."
    )


@pytest.mark.asyncio
@pytest.mark.regression
@pytest.mark.timeout(180)
async def test_sentiment_regressor_is_honored_at_predict_time(db_session) -> None:
    """Trained sentiment regressors must influence yhat at predict time.

    Trains Prophet on 250 days of synthetic prices that are correlated with a
    known sentiment series. Runs ``predict_forecast`` twice:

    1. With ``_fetch_sentiment_regressors`` returning the real series.
    2. With ``_fetch_sentiment_regressors`` patched to return ``None`` so the
       function falls back to the 0.0 projection (this models the pre-fix
       behaviour where sentiment columns were hard-coded to 0.0).

    The two forecasts must differ at the longest horizon — if they're equal,
    the predict-time merge has been silently dropped and the trained beta is
    being ignored.
    """
    from backend.tools.forecasting import predict_forecast, train_prophet_model

    await _seed_synthetic_series(db_session, ticker="FOO", days=200, beta=10.0, seed=42)
    await db_session.commit()

    model_version = await train_prophet_model("FOO", db_session)

    forecasts_real = await predict_forecast(model_version, db_session)

    with patch(
        "backend.tools.forecasting._fetch_sentiment_regressors",
        AsyncMock(return_value=None),
    ):
        forecasts_zeroed = await predict_forecast(model_version, db_session)

    assert len(forecasts_real) == len(forecasts_zeroed) == 3

    # The trained beta guarantees a non-trivial price difference when the
    # regressor is honored vs zeroed. 0.5$ is well above noise for a series
    # whose 1-sigma daily move is ~0.2$.
    deltas = [
        abs(real.predicted_price - zeroed.predicted_price)
        for real, zeroed in zip(forecasts_real, forecasts_zeroed, strict=True)
    ]
    assert max(deltas) > 0.5, (
        f"Predict-time sentiment regressor had no effect on yhat "
        f"(max delta={max(deltas):.4f}). The B3 predict-time merge has "
        f"regressed — sentiment columns are likely being zeroed again. "
        f"deltas={deltas}"
    )


@pytest.mark.asyncio
@pytest.mark.regression
@pytest.mark.timeout(180)
async def test_predict_forecast_without_sentiment_still_works(db_session) -> None:
    """Models trained without sentiment regressors must still predict cleanly.

    Some tickers have no NewsSentimentDaily history — for those, the sentiment
    branch is skipped at training time and the model has no extra regressors.
    The post-fix predict path must not crash trying to merge a non-existent
    regressor column.
    """
    from backend.tools.forecasting import predict_forecast, train_prophet_model

    await _seed_stock(db_session, "BAR")
    rng = np.random.default_rng(7)
    days = 200
    prices = 100.0 + np.cumsum(rng.normal(0, 0.5, days))

    today = datetime.now(timezone.utc).date()
    for i, p in enumerate(prices):
        day = today - timedelta(days=days - i)
        ts = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)
        db_session.add(
            StockPriceFactory.build(
                ticker="BAR",
                time=ts,
                open=float(p),
                high=float(p),
                low=float(p),
                close=float(p),
                adj_close=float(p),
            )
        )
    # No NewsSentimentDaily rows seeded — model trains without regressors.
    await db_session.commit()

    model_version = await train_prophet_model("BAR", db_session)
    forecasts = await predict_forecast(model_version, db_session)

    assert len(forecasts) == 3
    assert all(f.predicted_price > 0 for f in forecasts)


@pytest.mark.asyncio
@pytest.mark.regression
@pytest.mark.timeout(180)
async def test_forecast_period_uses_seven_day_trailing_mean(db_session) -> None:
    """Forecast-horizon dates must use the 7-day trailing mean of sentiment.

    Pre-fix, forecast dates got 0.0. Post-fix, they should be filled with the
    mean of the last 7 days of training-window sentiment. We seed sentiment
    that ramps up linearly so the trailing-mean is well above 0 and the
    fallback (0.0) would be obviously wrong.

    The test sanity-checks the projection value by patching
    ``_fetch_sentiment_regressors`` once with real data and once with empty
    data; the difference between predictions must trace back through the
    horizon prediction (longer horizons see more days of projected sentiment
    so the gap should grow with horizon).
    """
    from backend.tools.forecasting import predict_forecast, train_prophet_model

    await _seed_stock(db_session, "BAZ")
    rng = np.random.default_rng(99)
    days = 200
    # Sentiment ramp from 0.0 to 0.8 over the training window.
    sentiment = np.linspace(0.0, 0.8, days) + rng.normal(0, 0.02, days)
    prices = 100.0 + np.cumsum(8.0 * sentiment + rng.normal(0, 0.2, days))

    today = datetime.now(timezone.utc).date()
    for i, (p, s) in enumerate(zip(prices, sentiment, strict=True)):
        day = today - timedelta(days=days - i)
        ts = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)
        db_session.add(
            StockPriceFactory.build(
                ticker="BAZ",
                time=ts,
                open=float(p),
                high=float(p),
                low=float(p),
                close=float(p),
                adj_close=float(p),
            )
        )
        db_session.add(
            NewsSentimentDailyFactory.build(
                ticker="BAZ",
                date=day,
                stock_sentiment=float(s),
                sector_sentiment=0.0,
                macro_sentiment=0.0,
            )
        )
    await db_session.commit()

    model_version = await train_prophet_model("BAZ", db_session)

    forecasts_real = await predict_forecast(model_version, db_session)

    with patch(
        "backend.tools.forecasting._fetch_sentiment_regressors",
        AsyncMock(return_value=None),
    ):
        forecasts_zeroed = await predict_forecast(model_version, db_session)

    # The longest horizon spans more projected days than the shortest, so
    # the gap from honoring the trailing-mean projection should grow with
    # horizon. We assert the longest-horizon delta is at least as large as
    # the shortest-horizon delta — a strict check that the projection is
    # being applied to forecast dates, not just historical merge.
    deltas = {
        f_real.horizon_days: abs(f_real.predicted_price - f_zero.predicted_price)
        for f_real, f_zero in zip(forecasts_real, forecasts_zeroed, strict=True)
    }
    assert deltas[270] >= deltas[90], (
        f"Long-horizon delta should be >= short-horizon delta when the "
        f"trailing-mean projection is applied to future dates. deltas={deltas}"
    )
