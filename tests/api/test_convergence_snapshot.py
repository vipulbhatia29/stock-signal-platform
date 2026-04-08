"""API-tier tests for compute_convergence_snapshot_task (B1).

Uses db_session (real DB via testcontainers) — must live under tests/api/,
not tests/unit/, per the Plan A test-placement guardrail.

Note: db_session does NOT truncate between tests (unlike the 'client' fixture).
We therefore use unique-per-test tickers generated via factory sequences to
avoid PK collisions when tests share the same container session.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from backend.models.convergence import SignalConvergenceDaily
from backend.models.price import StockPrice
from backend.models.signal import SignalSnapshot
from backend.models.stock import Stock
from backend.tasks.convergence import _compute_convergence_snapshot_async
from tests.factories.convergence import SignalConvergenceDailyFactory

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _unique_ticker(prefix: str = "CV") -> str:
    """Generate a short unique ticker so tests do not collide on shared containers."""
    return f"{prefix}{uuid.uuid4().hex[:4].upper()}"


async def _seed_stock(db_session, ticker: str) -> Stock:
    """Insert a minimal Stock row so FK constraints pass (idempotent via ON CONFLICT)."""
    now = datetime.now(timezone.utc)
    stmt = pg_insert(Stock).values(
        ticker=ticker,
        name=f"{ticker} Corp",
        exchange="NASDAQ",
        sector="Technology",
        is_active=True,
        created_at=now,
        updated_at=now,
        id=uuid.uuid4(),
    )
    stmt = stmt.on_conflict_do_nothing(index_elements=["ticker"])
    await db_session.execute(stmt)
    await db_session.flush()
    result = await db_session.execute(select(Stock).where(Stock.ticker == ticker))
    return result.scalar_one()


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
# B1 tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_universe_returns_no_tickers(db_session) -> None:
    """When the ticker universe is empty, task returns status=no_tickers with computed=0."""
    with patch(
        "backend.tasks.convergence.get_all_referenced_tickers",
        AsyncMock(return_value=[]),
    ):
        result = await _compute_convergence_snapshot_async(_db=db_session)

    assert result["status"] == "no_tickers"
    assert result["computed"] == 0


@pytest.mark.asyncio
async def test_universe_mode_inserts_one_row_per_ticker(db_session) -> None:
    """Universe mode inserts exactly one signal_convergence_daily row per ticker today."""
    today = datetime.now(timezone.utc).date()
    t1, t2, t3 = _unique_ticker(), _unique_ticker(), _unique_ticker()
    tickers = [t1, t2, t3]

    for tkr in tickers:
        await _seed_stock(db_session, tkr)
        await _seed_signal(db_session, tkr)
    await db_session.commit()

    with patch(
        "backend.tasks.convergence.get_all_referenced_tickers",
        AsyncMock(return_value=tickers),
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
    t1 = _unique_ticker("ST")
    t2 = _unique_ticker("ST")
    await _seed_stock(db_session, t1)
    await _seed_stock(db_session, t2)
    await _seed_signal(db_session, t1)
    await _seed_signal(db_session, t2)
    await db_session.commit()

    result = await _compute_convergence_snapshot_async(ticker=t1, _db=db_session)

    assert result["status"] == "ok"
    assert result["computed"] == 1

    rows_result = await db_session.execute(
        select(SignalConvergenceDaily).where(
            SignalConvergenceDaily.date == today,
            SignalConvergenceDaily.ticker.in_([t1, t2]),
        )
    )
    rows = rows_result.scalars().all()
    assert len(rows) == 1
    assert rows[0].ticker == t1


@pytest.mark.asyncio
async def test_rerun_same_day_updates_via_on_conflict(db_session) -> None:
    """Running the task twice on the same day updates the row via ON CONFLICT DO UPDATE."""
    today = datetime.now(timezone.utc).date()
    tkr = _unique_ticker("RC")
    await _seed_stock(db_session, tkr)
    await _seed_signal(db_session, tkr)
    await db_session.commit()

    await _compute_convergence_snapshot_async(ticker=tkr, _db=db_session)
    result = await _compute_convergence_snapshot_async(ticker=tkr, _db=db_session)

    assert result["status"] == "ok"

    rows_result = await db_session.execute(
        select(SignalConvergenceDaily).where(
            SignalConvergenceDaily.date == today,
            SignalConvergenceDaily.ticker == tkr,
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
    tkr = _unique_ticker("BF")
    await _seed_stock(db_session, tkr)

    # Seed a convergence row 90 days ago with NULL actual_return_90d
    row = SignalConvergenceDailyFactory.build(
        ticker=tkr,
        date=target_date,
        actual_return_90d=None,
        actual_return_180d=None,
    )
    db_session.add(row)

    # Seed prices: one at target_date (100.0), one at today (110.0)
    await _seed_price(
        db_session,
        tkr,
        100.0,
        at=datetime(target_date.year, target_date.month, target_date.day, 12, tzinfo=timezone.utc),
    )
    await _seed_price(db_session, tkr, 110.0)
    await db_session.commit()

    with patch(
        "backend.tasks.convergence.get_all_referenced_tickers",
        AsyncMock(return_value=[tkr]),
    ):
        result = await _compute_convergence_snapshot_async(ticker=tkr, _db=db_session)

    assert result["backfilled"] >= 1

    await db_session.refresh(row)
    assert row.actual_return_90d is not None
    assert abs(row.actual_return_90d - 0.10) < 0.01  # (110-100)/100 = 0.10


@pytest.mark.asyncio
async def test_backfill_noop_when_already_populated(db_session) -> None:
    """Backfill skips rows whose actual_return_90d is already set."""
    today = datetime.now(timezone.utc).date()
    target_date = today - timedelta(days=90)
    tkr = _unique_ticker("NP")
    await _seed_stock(db_session, tkr)

    # Seed row with actual_return_90d already filled
    row = SignalConvergenceDailyFactory.build(
        ticker=tkr,
        date=target_date,
        actual_return_90d=0.05,  # already set — must not be overwritten
        actual_return_180d=None,
    )
    db_session.add(row)
    await db_session.commit()

    with patch(
        "backend.tasks.convergence.get_all_referenced_tickers",
        AsyncMock(return_value=[tkr]),
    ):
        await _compute_convergence_snapshot_async(ticker=tkr, _db=db_session)

    await db_session.refresh(row)
    # Must remain unchanged
    assert row.actual_return_90d == pytest.approx(0.05)


@pytest.mark.asyncio
async def test_backfill_skips_when_historical_price_missing(db_session) -> None:
    """Backfill skips the row (no exception) when no StockPrice exists for the target date."""
    today = datetime.now(timezone.utc).date()
    target_date = today - timedelta(days=90)
    tkr = _unique_ticker("PM")
    await _seed_stock(db_session, tkr)

    # Seed row with NULL actual_return_90d but NO prices
    row = SignalConvergenceDailyFactory.build(
        ticker=tkr,
        date=target_date,
        actual_return_90d=None,
        actual_return_180d=None,
    )
    db_session.add(row)
    await db_session.commit()

    with (
        patch(
            "backend.tasks.convergence.get_all_referenced_tickers",
            AsyncMock(return_value=[tkr]),
        ),
        patch(
            "backend.tasks.convergence.mark_stage_updated",
            new_callable=AsyncMock,
        ),
    ):
        # Must not raise
        result = await _compute_convergence_snapshot_async(ticker=tkr, _db=db_session)

    # No crash — status can be ok, partial_failure, or no_tickers
    # depending on signal availability for this ticker
    assert result["status"] in ("ok", "partial_failure", "no_tickers")

    await db_session.refresh(row)
    # Still NULL — no prices available
    assert row.actual_return_90d is None


@pytest.mark.asyncio
async def test_mark_stage_updated_called_per_ticker(db_session) -> None:
    """mark_stage_updated must be called once per successfully-processed ticker."""
    t1 = _unique_ticker("MS")
    t2 = _unique_ticker("MS")
    tickers = [t1, t2]

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
    """_compute_convergence_snapshot_async must accept ticker as a keyword argument.

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


# ---------------------------------------------------------------------------
# Fix 3 regression: stage must be marked even when convergence dict is empty
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.asyncio
async def test_single_ticker_with_no_signals_still_marks_stage(db_session, monkeypatch):
    """Brand-new ticker dispatched from ingest_ticker Step 9: get_bulk_convergence
    returns empty, but the convergence stage must still be marked so the
    ticker_ingestion_state dashboard is not permanently stuck.
    """
    marked: list[tuple[str, str]] = []

    async def fake_mark(ticker: str, stage: str) -> None:
        marked.append((ticker, stage))

    monkeypatch.setattr("backend.tasks.convergence.mark_stage_updated", fake_mark)
    with patch(
        "backend.services.signal_convergence.SignalConvergenceService.get_bulk_convergence",
        AsyncMock(return_value={}),
    ):
        result = await _compute_convergence_snapshot_async(ticker="NEWCO", _db=db_session)

    assert ("NEWCO", "convergence") in marked, (
        "Stage must be marked even when convergence dict is empty"
    )
    assert result["computed"] == 0


# ---------------------------------------------------------------------------
# Fix 4 regression: bulk upsert failure must not kill backfill or stage marking
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.asyncio
async def test_get_bulk_convergence_failure_does_not_kill_backfill_or_stage(
    db_session, monkeypatch
):
    """One bad call to get_bulk_convergence must not kill the entire nightly
    Phase 3. Backfill should still run; stage should still be marked.
    """
    marked: list[tuple[str, str]] = []

    async def fake_mark(ticker: str, stage: str) -> None:
        marked.append((ticker, stage))

    monkeypatch.setattr("backend.tasks.convergence.mark_stage_updated", fake_mark)
    monkeypatch.setattr(
        "backend.tasks.convergence.get_all_referenced_tickers",
        AsyncMock(return_value=["AAPL", "MSFT"]),
    )
    with patch(
        "backend.services.signal_convergence.SignalConvergenceService.get_bulk_convergence",
        AsyncMock(side_effect=RuntimeError("simulated")),
    ):
        result = await _compute_convergence_snapshot_async(_db=db_session)

    assert result["status"] == "partial_failure"
    assert result["computed"] == 0
    # Both tickers should still have stage marked even after the failure
    assert ("AAPL", "convergence") in marked
    assert ("MSFT", "convergence") in marked
