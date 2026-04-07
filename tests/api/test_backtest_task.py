"""API-tier tests for run_backtest_task / _run_backtest_async (B2).

Uses db_session (testcontainers) — must live under tests/api/, not tests/unit/.
Prophet is always patched here; these tests verify task orchestration only.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from backend.models.backtest import BacktestRun
from backend.services.backtesting import BacktestMetrics
from backend.tasks.forecasting import _run_backtest_async

# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------

FAKE_METRICS = BacktestMetrics(
    mape=0.05,
    mae=5.0,
    rmse=6.0,
    direction_accuracy=0.62,
    ci_containment=0.80,
    ci_bias="balanced",
    avg_interval_width=12.0,
    num_windows=8,
)


def _seed_stock_and_model(session, ticker: str) -> "uuid.UUID":
    """Seed a Stock row and an active ModelVersion for *ticker*.

    Returns the ModelVersion id for use in assertions.
    """
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

    mv_id = uuid.uuid4()
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
        )
    )
    return mv_id


# ---------------------------------------------------------------------------
# B2.2 tests — these are written against the *real* _run_backtest_async
# implementation (B2.3). Running them before B2.3 is implemented will FAIL.
# After B2.3 is merged they must all pass GREEN.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_single_ticker_inserts_one_row(db_session):
    """Calling _run_backtest_async with a single ticker inserts exactly one BacktestRun row.

    Verifies: row count, horizon_days, and result["completed"] == 1.
    """
    ticker = "AAP"
    await db_session.run_sync(lambda s: _seed_stock_and_model(s, ticker))
    await db_session.commit()

    with (
        patch(
            "backend.tasks.forecasting.BacktestEngine.run_walk_forward",
            new_callable=AsyncMock,
            return_value=FAKE_METRICS,
        ),
        patch(
            "backend.tasks.forecasting.mark_stage_updated",
            new_callable=AsyncMock,
        ),
        patch(
            "backend.tasks.forecasting.async_session_factory",
        ) as mock_factory,
    ):
        # Route the task's session to our test db_session
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=db_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value = mock_cm

        result = await _run_backtest_async(ticker, 90)

    rows = (await db_session.execute(select(BacktestRun))).scalars().all()
    assert len(rows) == 1
    assert rows[0].horizon_days == 90
    assert result["completed"] == 1
    assert result["failed"] == 0


@pytest.mark.asyncio
async def test_universe_mode_three_tickers(db_session):
    """Universe mode (ticker=None) processes all tickers returned by get_all_referenced_tickers.

    Patches get_all_referenced_tickers to return 3 tickers.
    Asserts 3 BacktestRun rows inserted and result["completed"] == 3.
    """
    tickers = ["T1A", "T2B", "T3C"]
    for tkr in tickers:
        await db_session.run_sync(lambda s, t=tkr: _seed_stock_and_model(s, t))
    await db_session.commit()

    with (
        patch(
            "backend.tasks.forecasting.BacktestEngine.run_walk_forward",
            new_callable=AsyncMock,
            return_value=FAKE_METRICS,
        ),
        patch(
            "backend.tasks.forecasting.mark_stage_updated",
            new_callable=AsyncMock,
        ),
        patch(
            "backend.tasks.forecasting.get_all_referenced_tickers",
            new_callable=AsyncMock,
            return_value=tickers,
        ),
        patch(
            "backend.tasks.forecasting.async_session_factory",
        ) as mock_factory,
    ):
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=db_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value = mock_cm

        result = await _run_backtest_async(None, 90)

    rows = (await db_session.execute(select(BacktestRun))).scalars().all()
    assert len(rows) == 3
    assert result["completed"] == 3
    assert result["failed"] == 0


@pytest.mark.asyncio
async def test_per_ticker_failure_isolated(db_session):
    """A failure for one ticker does not block others.

    MSFT raises; AAPL and GOOG succeed.
    Asserts: 2 rows inserted, result["failed"] == 1, result["completed"] == 2.
    """
    tickers = ["AAA", "BBB", "CCC"]
    for tkr in tickers:
        await db_session.run_sync(lambda s, t=tkr: _seed_stock_and_model(s, t))
    await db_session.commit()

    def _side_effect(tkr, db, **kwargs):
        if tkr == "BBB":
            raise RuntimeError("Simulated Prophet failure")

        async def _ok():
            return FAKE_METRICS

        return _ok()

    with (
        patch(
            "backend.tasks.forecasting.BacktestEngine.run_walk_forward",
            side_effect=_side_effect,
        ),
        patch(
            "backend.tasks.forecasting.mark_stage_updated",
            new_callable=AsyncMock,
        ),
        patch(
            "backend.tasks.forecasting.get_all_referenced_tickers",
            new_callable=AsyncMock,
            return_value=tickers,
        ),
        patch(
            "backend.tasks.forecasting.async_session_factory",
        ) as mock_factory,
    ):
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=db_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value = mock_cm

        result = await _run_backtest_async(None, 90)

    assert result["failed"] == 1
    assert result["completed"] == 2


@pytest.mark.asyncio
async def test_mark_stage_updated_called_on_success_only(db_session):
    """mark_stage_updated is called only for tickers that succeed, not for failing ones.

    With AAPL succeeding and MSFT failing, expects one call to mark_stage_updated.
    """
    tickers = ["SUC", "FAL"]
    for tkr in tickers:
        await db_session.run_sync(lambda s, t=tkr: _seed_stock_and_model(s, t))
    await db_session.commit()

    def _side_effect(tkr, db, **kwargs):
        if tkr == "FAL":
            raise RuntimeError("Planned failure")

        async def _ok():
            return FAKE_METRICS

        return _ok()

    mock_mark = AsyncMock()
    with (
        patch(
            "backend.tasks.forecasting.BacktestEngine.run_walk_forward",
            side_effect=_side_effect,
        ),
        patch(
            "backend.tasks.forecasting.mark_stage_updated",
            mock_mark,
        ),
        patch(
            "backend.tasks.forecasting.get_all_referenced_tickers",
            new_callable=AsyncMock,
            return_value=tickers,
        ),
        patch(
            "backend.tasks.forecasting.async_session_factory",
        ) as mock_factory,
    ):
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=db_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value = mock_cm

        await _run_backtest_async(None, 90)

    # Only the successful ticker should have triggered stage update
    assert mock_mark.call_count == 1
    called_ticker = mock_mark.call_args[0][0]
    assert called_ticker == "SUC"
