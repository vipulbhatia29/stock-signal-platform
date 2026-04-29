"""Regression tests for Prophet sentiment regressors at predict time (KAN-422 / Spec B / B3).

These tests guard the bug fixed in B3: ``predict_forecast`` previously
hard-coded ``stock_sentiment``/``sector_sentiment``/``macro_sentiment`` to
``0.0`` for **every** row of the future DataFrame, including the historical
training rows that Prophet re-projects internally. The result was that the
trained regressor coefficients had no effect at predict time and predictions
silently ignored sentiment.

The fix (hybrid source):
- Historical rows are read from ``model.history`` — the exact values Prophet
  was fit on. This is skew-proof by construction and removes the need to
  re-query the DB for dates already in the training window.
- Post-training rows ``(training_end, today]`` come from a fresh DB query
  on ``NewsSentimentDaily``. These dates were never in the training frame,
  so there is no training-serving skew risk.
- Forecast-horizon rows ``(today, ...)`` get a 7-day trailing mean anchored
  to the most recent available sentiment (training + post-training), so
  stale models still project a reasonably fresh signal.

Tests marked ``slow``/``timeout(180)`` because Prophet fitting takes a few
seconds per call. Tests live in ``tests/api/`` because they use a real
``db_session`` (sequential, no xdist) per the Spec A guardrail.
"""

from __future__ import annotations

import inspect
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np
import pytest
from freezegun import freeze_time

from tests.conftest import NewsSentimentDailyFactory, StockFactory, StockPriceFactory

SENTIMENT_COLS = ["stock_sentiment", "sector_sentiment", "macro_sentiment"]


async def _seed_stock(db_session, ticker: str) -> None:
    """Seed a Stock row so price/sentiment FKs are satisfied."""
    db_session.add(StockFactory.build(ticker=ticker, name=f"Test {ticker}"))
    await db_session.flush()


async def _seed_synthetic_series(
    db_session,
    *,
    ticker: str,
    days: int,
    beta: float,
    seed: int,
    end_date: Any = None,
    seed_sentiment: bool = True,
    constant_sentiment: float | None = None,
    tail_zero_days: int = 0,
) -> None:
    """Seed Stock + StockPrice + (optionally) NewsSentimentDaily rows.

    The price series is a noisy random walk whose drift is driven by a sinusoid
    sentiment signal. With a known beta, Prophet should learn a non-trivial
    regressor coefficient.

    Args:
        db_session: Live async session.
        ticker: Ticker symbol for the rows.
        days: Number of days to seed (>= MIN_DATA_POINTS).
        beta: Sensitivity of price drift to sentiment.
        seed: numpy RNG seed for determinism.
        end_date: Last day to seed; defaults to today (UTC).
        seed_sentiment: When False, no NewsSentimentDaily rows are seeded
            (model will train without sentiment regressors).
        constant_sentiment: When set, overrides the sinusoid and uses this
            value for every day (useful for projection-collapse tests).
        tail_zero_days: Force the last N days of seeded sentiment (and the
            corresponding price drift contribution) to exactly 0.0. Used
            by the stale-model test to deterministically pin the 7-day
            trailing-mean fallback at 0, eliminating phase-dependent flakiness.
    """
    await _seed_stock(db_session, ticker)
    rng = np.random.default_rng(seed)

    if constant_sentiment is not None:
        sentiment = np.full(days, float(constant_sentiment))
    else:
        sentiment = 0.5 * np.sin(np.linspace(0, 6 * np.pi, days)) + rng.normal(0, 0.05, days)

    if tail_zero_days > 0:
        sentiment[-tail_zero_days:] = 0.0

    drift = beta * sentiment + rng.normal(0, 0.2, days)
    prices = 100.0 + np.cumsum(drift)

    end = end_date if end_date is not None else datetime.now(timezone.utc).date()
    for i, (p, s) in enumerate(zip(prices, sentiment, strict=True)):
        day = end - timedelta(days=days - 1 - i)
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
        if seed_sentiment:
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

    Pre-fix it was a sync function. Asserting the function is a coroutine
    catches accidental reverts to the sync signature.
    """
    from backend.tools.forecasting import predict_forecast

    assert inspect.iscoroutinefunction(predict_forecast), (
        "predict_forecast must be async after the B3 fix — see KAN-422 Spec B."
    )


@pytest.mark.asyncio
@pytest.mark.regression
@pytest.mark.timeout(180)
@pytest.mark.xfail(reason="KAN-550: PROPHET_REAL_SENTIMENT_ENABLED=False (deprecated)")
async def test_predict_uses_model_history_sentiment_not_zero(db_session, monkeypatch) -> None:
    """Predict-time sentiment must come from ``model.history``, not hard-coded zero.

    This is the direct regression test for the KAN-422 B3 bug. Pre-fix,
    ``predict_forecast`` wrote ``future[col] = 0.0`` for every sentiment
    column, silently zeroing the trained regressor beta. Post-fix, historical
    rows in the future frame get their values from ``model.history`` — the
    exact snapshot Prophet was fit on.

    Strategy: train Prophet on a synthetic series with known non-zero
    sentiment, then monkey-patch ``model_from_json`` so the loaded model has
    its ``history`` sentiment columns zeroed. This models EXACTLY the pre-fix
    behavior (sentiment → 0.0 at predict time) without depending on an
    internal code path that the fix may have restructured. Forecasts from
    the real model must differ meaningfully from forecasts from the zeroed
    model; if they don't, the fix has regressed.
    """
    from backend.tools import forecasting as f_mod

    await _seed_synthetic_series(db_session, ticker="FOO", days=200, beta=10.0, seed=42)
    await db_session.commit()

    model_version = await f_mod.train_prophet_model("FOO", db_session)

    forecasts_real = await f_mod.predict_forecast(model_version, db_session)

    # Now patch the model loader so subsequent predict_forecast calls see
    # a model whose history sentiment columns are zeroed. This reproduces
    # the pre-fix bug at the source.
    original_load = f_mod.model_from_json

    def zeroed_loader(json_str):
        m = original_load(json_str)
        for col in SENTIMENT_COLS:
            if col in m.history.columns:
                m.history[col] = 0.0
        return m

    monkeypatch.setattr(f_mod, "model_from_json", zeroed_loader)
    forecasts_zeroed = await f_mod.predict_forecast(model_version, db_session)

    assert len(forecasts_real) == len(forecasts_zeroed) == 2

    deltas = [
        abs(real.expected_return_pct - zeroed.expected_return_pct)
        for real, zeroed in zip(forecasts_real, forecasts_zeroed, strict=True)
    ]
    assert max(deltas) > 0.5, (
        f"Predict-time sentiment from model.history had no effect on yhat "
        f"(max delta={max(deltas):.4f}). The KAN-422 B3 fix has regressed — "
        f"sentiment columns are likely being zeroed again. deltas={deltas}"
    )


@pytest.mark.asyncio
@pytest.mark.regression
@pytest.mark.timeout(180)
async def test_predict_forecast_without_sentiment_still_works(db_session) -> None:
    """Models trained without sentiment regressors must still predict cleanly.

    Some tickers have no NewsSentimentDaily history — for those, the sentiment
    branch is skipped at training time and the model has no extra regressors.
    The post-fix predict path must not crash trying to read from a
    non-existent regressor column or merge on an empty frame.
    """
    from backend.tools.forecasting import predict_forecast, train_prophet_model

    await _seed_synthetic_series(
        db_session, ticker="BAR", days=200, beta=0.0, seed=7, seed_sentiment=False
    )
    await db_session.commit()

    model_version = await train_prophet_model("BAR", db_session)
    forecasts = await predict_forecast(model_version, db_session)

    assert len(forecasts) == 2
    assert all(isinstance(f.expected_return_pct, float) for f in forecasts)


@pytest.mark.asyncio
@pytest.mark.regression
@pytest.mark.timeout(240)
@pytest.mark.xfail(reason="KAN-550: PROPHET_REAL_SENTIMENT_ENABLED=False (deprecated)")
async def test_stale_model_fetches_post_training_sentiment(db_session) -> None:
    """A model older than ``today`` must pull fresh post-training sentiment.

    This is the direct regression test for review finding C1: the earlier
    implementation clobbered real post-training sentiment values with a
    7-day trailing mean projection anchored to training_end. The fix reads
    those post-training days from a fresh DB query and passes them into the
    future frame intact.

    Strategy:
    1. Freeze time at ``2026-01-15`` and seed 200 days of training data
       ending on that date; train the model. ``training_end = 2026-01-15``.
    2. Advance time to ``2026-01-25`` (10 days later) and seed 10 new
       NewsSentimentDaily rows in the ``(training_end, today]`` window
       with a strong constant positive sentiment (+0.9).
    3. Advance time to ``2026-01-25`` (no frozen date arg, uses the frozen
       one from step 2) and call predict_forecast. The post-training fetch
       should pull the +0.9 rows and the 7-day trailing mean projection
       should reflect them.
    4. Repeat step 3 BUT with a broken DB session that returns empty rows
       for the post-training fetch. Without post-training data, the
       projection will fall back to the training-window tail (which is
       closer to zero). Forecasts from the two runs should differ.
    """
    from backend.tools.forecasting import predict_forecast, train_prophet_model

    training_end_date = datetime(2026, 1, 15, tzinfo=timezone.utc).date()

    with freeze_time("2026-01-15 12:00:00"):
        # Seed sine sentiment for 193 days so Prophet learns a non-trivial
        # beta, then force the last 7 days to exactly 0.0. This pins the
        # stale-fallback trailing-mean baseline at 0 deterministically,
        # eliminating flakiness from sine-phase dependence on the seed (TQ1).
        await _seed_synthetic_series(
            db_session,
            ticker="STALE",
            days=200,
            beta=10.0,
            seed=101,
            end_date=training_end_date,
            tail_zero_days=7,
        )
        await db_session.commit()
        model_version = await train_prophet_model("STALE", db_session)

    # Seed strongly-positive post-training sentiment for the 10-day window.
    for i in range(10):
        day = training_end_date + timedelta(days=i + 1)
        db_session.add(
            NewsSentimentDailyFactory.build(
                ticker="STALE",
                date=day,
                stock_sentiment=0.9,
                sector_sentiment=0.9,
                macro_sentiment=0.0,
            )
        )
    await db_session.commit()

    with freeze_time("2026-01-25 12:00:00"):
        forecasts_with_post = await predict_forecast(model_version, db_session)

        # Second run: patch fetch_sentiment_regressors to return None so the
        # post-training fetch is empty. The projection then falls back to the
        # training-window tail only, which lacks the +0.9 spike.
        from unittest.mock import AsyncMock, patch

        with patch(
            "backend.tools.forecasting.fetch_sentiment_regressors",
            AsyncMock(return_value=None),
        ):
            forecasts_without_post = await predict_forecast(model_version, db_session)

    deltas = [
        abs(a.expected_return_pct - b.expected_return_pct)
        for a, b in zip(forecasts_with_post, forecasts_without_post, strict=True)
    ]
    # beta=10 × sentiment delta of ~0.9 gives a clear return impact.
    assert max(deltas) > 0.3, (
        f"Post-training sentiment should meaningfully change forecasts "
        f"(max delta={max(deltas):.4f}). If this is near zero, the fix is "
        f"ignoring post-training sentiment — regression of C1. deltas={deltas}"
    )


@pytest.mark.asyncio
@pytest.mark.regression
@pytest.mark.timeout(180)
@pytest.mark.xfail(reason="KAN-550: PROPHET_REAL_SENTIMENT_ENABLED=False (deprecated)")
async def test_projection_collapse_logs_error(db_session, caplog: pytest.LogCaptureFixture) -> None:
    """All-zero sentiment projection must log ERROR so operators see it.

    Review finding C2: if the model was trained with sentiment regressors but
    the computed projection is all-zero (e.g., ingestion broken, all training
    sentiment is zero), the fix must log loudly. A silent 0.0 fallback
    reintroduces the exact bug B3 was supposed to eliminate. This test is
    the meta-guardrail that fails if the silent failure comes back.
    """
    from backend.tools.forecasting import predict_forecast, train_prophet_model

    # Train with constant 0.0 sentiment — model has regressors but the
    # learned beta and the projection will both be degenerate.
    await _seed_synthetic_series(
        db_session,
        ticker="ZEROSENT",
        days=200,
        beta=0.0,  # no price-sentiment correlation
        seed=17,
        constant_sentiment=0.0,
    )
    await db_session.commit()

    model_version = await train_prophet_model("ZEROSENT", db_session)

    with caplog.at_level(logging.ERROR, logger="backend.tools.forecasting"):
        forecasts = await predict_forecast(model_version, db_session)

    assert len(forecasts) == 2

    matching = [
        rec
        for rec in caplog.records
        if rec.levelno == logging.ERROR and "projection collapsed" in rec.message
    ]
    assert matching, (
        "Expected an ERROR log for all-zero sentiment projection, but none "
        "was emitted. The silent-failure guard from review finding C2 is "
        f"not active. Captured records: {[r.message for r in caplog.records]}"
    )
    assert "ZEROSENT" in matching[0].message


# Note: the RuntimeError guard for NaN-after-merge in predict_forecast is a
# defensive safety net — not reachable in normal production paths because
# every row of combined_sentiment_df is non-null by construction. We
# deliberately do NOT add a test for the raise path because any test that
# forces it through has to contrive a broken pd.concat result or a
# schema-mismatched post_df, neither of which reflects a real regression
# mode. The guard is defense-in-depth; the C3 "fillna(0.0) silently zeros
# weekends" bug is structurally prevented by sourcing historical rows from
# model.history (which contains only market days — no weekend rows to fill).
