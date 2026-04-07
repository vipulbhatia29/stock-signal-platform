"""API-tier tests for compute_convergence_snapshot_task (B1).

Uses db_session (real DB via testcontainers) — must live under tests/api/,
not tests/unit/, per the Plan A test-placement guardrail.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from backend.models.convergence import SignalConvergenceDaily
from backend.models.price import StockPrice
from backend.models.signal import SignalSnapshot
from backend.models.stock import Stock
from backend.tasks.convergence import _compute_convergence_snapshot_async
from tests.factories.convergence import SignalConvergenceDailyFactory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_stock(db_session, ticker: str) -> Stock:
    """Insert a minimal Stock row so FK constraints pass."""
    stock = Stock(
        ticker=ticker,
        name=f"{ticker} Corp",
        exchange="NASDAQ",
        sector="Technology",
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(stock)
    await db_session.flush()
    return stock


async def _seed_signal(db_session, ticker: str) -> SignalSnapshot:
    """Insert a minimal SignalSnapshot row for ticker."""
    snap = SignalSnapshot(
        computed_at=datetime.now(timezone.utc),
        ticker=ticker,
        rsi_value=50.0,
        rsi_signal="NEUTRAL",
        macd_value=0.0,
        macd_histogram=0.1,
        macd_signal_label="NEUTRAL",
        sma_50=100.0,
        sma_200=98.0,
        sma_signal="ABOVE_200",
        bb_upper=110.0,
        bb_lower=90.0,
        bb_position="MIDDLE",
        annual_return=0.10,
        volatility=0.20,
        sharpe_ratio=0.5,
        change_pct=0.5,
        current_price=100.0,
        composite_score=6.0,
        composite_weights={"rsi": 1.0},
    )
    db_session.add(snap)
    await db_session.flush()
    return snap


async def _seed_price(
    db_session,
    ticker: str,
    price: float,
    at: datetime | None = None,
) -> StockPrice:
    """Insert a StockPrice row for ticker at the given datetime."""
    ts = at or datetime.now(timezone.utc)
    sp = StockPrice(
        time=ts,
        ticker=ticker,
        open=price,
        high=price * 1.01,
        low=price * 0.99,
        close=price,
        adj_close=price,
        volume=1_000_000,
        source="yfinance",
    )
    db_session.add(sp)
    await db_session.flush()
    return sp


# ---------------------------------------------------------------------------
# B1.1 tests — these must be RED before B1.2 implementation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_universe_returns_no_tickers(db_session) -> None:
    """When the ticker universe is empty, task returns status=no_tickers with computed=0."""
    with patch(
        "backend.tasks.convergence.get_all_referenced_tickers",
        AsyncMock(return_value=[]),
    ):
        result = await _compute_convergence_snapshot_async()

    assert result["status"] == "no_tickers"
    assert result["computed"] == 0


@pytest.mark.asyncio
async def test_universe_mode_inserts_one_row_per_ticker(db_session) -> None:
    """Universe mode inserts exactly one signal_convergence_daily row per ticker today."""
    today = datetime.now(timezone.utc).date()
    tickers = ["AAPL", "MSFT", "GOOG"]

    # Seed stocks + signals so convergence service finds signal data
    for tkr in tickers:
        await _seed_stock(db_session, tkr)
        await _seed_signal(db_session, tkr)
    await db_session.commit()

    with (
        patch(
            "backend.tasks.convergence.get_all_referenced_tickers",
            AsyncMock(return_value=tickers),
        ),
        patch(
            "backend.tasks.convergence.mark_stage_updated",
            new_callable=AsyncMock,
        ),
        patch(
            "backend.tasks.convergence.async_session_factory",
            return_value=db_session,
        ),
    ):
        result = await _compute_convergence_snapshot_async(_db=db_session)

    assert result["status"] == "ok"
    assert result["computed"] == len(tickers)

    rows_result = await db_session.execute(
        select(SignalConvergenceDaily).where(
            SignalConvergenceDaily.date == today,
            SignalConvergenceDaily.ticker.in_(tickers),
        )
    )
    rows = rows_result.scalars().all()
    assert len(rows) == len(tickers)
    inserted_tickers = {r.ticker for r in rows}
    assert inserted_tickers == set(tickers)


@pytest.mark.asyncio
async def test_single_ticker_mode(db_session) -> None:
    """Single-ticker mode inserts only the specified ticker's row."""
    today = datetime.now(timezone.utc).date()
    await _seed_stock(db_session, "AAPL")
    await _seed_stock(db_session, "MSFT")
    await _seed_signal(db_session, "AAPL")
    await _seed_signal(db_session, "MSFT")
    await db_session.commit()

    with patch(
        "backend.tasks.convergence.mark_stage_updated",
        new_callable=AsyncMock,
    ):
        result = await _compute_convergence_snapshot_async(ticker="AAPL", _db=db_session)

    assert result["status"] == "ok"
    assert result["computed"] == 1

    rows_result = await db_session.execute(
        select(SignalConvergenceDaily).where(SignalConvergenceDaily.date == today)
    )
    rows = rows_result.scalars().all()
    assert len(rows) == 1
    assert rows[0].ticker == "AAPL"


@pytest.mark.asyncio
async def test_rerun_same_day_updates_via_on_conflict(db_session) -> None:
    """Running the task twice on the same day updates the row via ON CONFLICT DO UPDATE."""
    today = datetime.now(timezone.utc).date()
    await _seed_stock(db_session, "AAPL")
    await _seed_signal(db_session, "AAPL")
    await db_session.commit()

    with patch(
        "backend.tasks.convergence.mark_stage_updated",
        new_callable=AsyncMock,
    ):
        await _compute_convergence_snapshot_async(ticker="AAPL", _db=db_session)
        result = await _compute_convergence_snapshot_async(ticker="AAPL", _db=db_session)

    assert result["status"] == "ok"

    rows_result = await db_session.execute(
        select(SignalConvergenceDaily).where(
            SignalConvergenceDaily.date == today,
            SignalConvergenceDaily.ticker == "AAPL",
        )
    )
    rows = rows_result.scalars().all()
    # ON CONFLICT DO UPDATE — still only one row
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_backfill_actual_return_90d(db_session) -> None:
    """Backfill populates actual_return_90d for rows whose target date has elapsed."""
    today = datetime.now(timezone.utc).date()
    target_date = today - timedelta(days=90)

    await _seed_stock(db_session, "AAPL")

    # Seed a convergence row 90 days ago with NULL actual_return_90d
    row = SignalConvergenceDailyFactory.build(
        ticker="AAPL",
        date=target_date,
        actual_return_90d=None,
    )
    db_session.add(row)

    # Seed prices: one at target_date (100.0), one at today (110.0)
    await _seed_price(
        db_session,
        "AAPL",
        100.0,
        at=datetime(target_date.year, target_date.month, target_date.day, 12, tzinfo=timezone.utc),
    )
    await _seed_price(db_session, "AAPL", 110.0)
    await db_session.commit()

    with (
        patch(
            "backend.tasks.convergence.get_all_referenced_tickers",
            AsyncMock(return_value=["AAPL"]),
        ),
        patch(
            "backend.tasks.convergence.mark_stage_updated",
            new_callable=AsyncMock,
        ),
    ):
        result = await _compute_convergence_snapshot_async(ticker="AAPL", _db=db_session)

    assert result["backfilled"] >= 1

    await db_session.refresh(row)
    assert row.actual_return_90d is not None
    assert abs(row.actual_return_90d - 0.10) < 0.01  # (110-100)/100 = 0.10


@pytest.mark.asyncio
async def test_backfill_noop_when_already_populated(db_session) -> None:
    """Backfill skips rows whose actual_return_90d is already set."""
    today = datetime.now(timezone.utc).date()
    target_date = today - timedelta(days=90)

    await _seed_stock(db_session, "AAPL")

    # Seed row with actual_return_90d already filled
    row = SignalConvergenceDailyFactory.build(
        ticker="AAPL",
        date=target_date,
        actual_return_90d=0.05,  # already set
    )
    db_session.add(row)
    await db_session.commit()

    with (
        patch(
            "backend.tasks.convergence.get_all_referenced_tickers",
            AsyncMock(return_value=["AAPL"]),
        ),
        patch(
            "backend.tasks.convergence.mark_stage_updated",
            new_callable=AsyncMock,
        ),
    ):
        await _compute_convergence_snapshot_async(ticker="AAPL", _db=db_session)

    await db_session.refresh(row)
    # Must remain unchanged
    assert row.actual_return_90d == pytest.approx(0.05)


@pytest.mark.asyncio
async def test_backfill_skips_when_historical_price_missing(db_session) -> None:
    """Backfill skips the row (no exception) when no StockPrice exists for the target date."""
    today = datetime.now(timezone.utc).date()
    target_date = today - timedelta(days=90)

    await _seed_stock(db_session, "AAPL")

    # Seed row with NULL actual_return_90d but NO prices
    row = SignalConvergenceDailyFactory.build(
        ticker="AAPL",
        date=target_date,
        actual_return_90d=None,
    )
    db_session.add(row)
    await db_session.commit()

    with (
        patch(
            "backend.tasks.convergence.get_all_referenced_tickers",
            AsyncMock(return_value=["AAPL"]),
        ),
        patch(
            "backend.tasks.convergence.mark_stage_updated",
            new_callable=AsyncMock,
        ),
    ):
        # Must not raise
        result = await _compute_convergence_snapshot_async(ticker="AAPL", _db=db_session)

    assert result["status"] in ("ok", "no_tickers")

    await db_session.refresh(row)
    # Still NULL — no prices available
    assert row.actual_return_90d is None


@pytest.mark.asyncio
async def test_mark_stage_updated_called_per_ticker(db_session) -> None:
    """mark_stage_updated must be called once per successfully-processed ticker."""
    tickers = ["AAPL", "MSFT"]

    for tkr in tickers:
        await _seed_stock(db_session, tkr)
        await _seed_signal(db_session, tkr)
    await db_session.commit()

    with (
        patch(
            "backend.tasks.convergence.get_all_referenced_tickers",
            AsyncMock(return_value=tickers),
        ),
        patch(
            "backend.tasks.convergence.mark_stage_updated",
            new_callable=AsyncMock,
        ) as mock_mark,
    ):
        await _compute_convergence_snapshot_async(_db=db_session)

    assert mock_mark.call_count == len(tickers)
    called_tickers = {call.args[0] for call in mock_mark.call_args_list}
    assert called_tickers == set(tickers)
    for call in mock_mark.call_args_list:
        assert call.args[1] == "convergence"


@pytest.mark.asyncio
async def test_task_signature_accepts_ticker_kwarg() -> None:
    """compute_convergence_snapshot_task must accept ticker as a keyword argument.

    Does not use db_session — pure introspection test.
    """
    import inspect

    from backend.tasks.convergence import _compute_convergence_snapshot_async

    sig = inspect.signature(_compute_convergence_snapshot_async)
    assert "ticker" in sig.parameters, (
        "_compute_convergence_snapshot_async must accept 'ticker' kwarg"
    )
    param = sig.parameters["ticker"]
    assert param.default is None, "ticker param default must be None (optional)"
