"""API-tier tests for run_backtest_task / _run_backtest_async (B2).

Uses db_session (testcontainers) — must live under tests/api/, not tests/unit/.
Prophet is always patched here; these tests verify task orchestration only.

Note on test isolation: db_session does NOT truncate between tests (only the
'client' fixture does). Each test uses unique ticker symbols to avoid cross-test
contamination.
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
from tests.unit.tasks._tracked_helper_bypass import bypass_tracked

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


async def _seed_stock_and_model(session, ticker: str) -> uuid.UUID:
    """Seed a Stock row and an active ModelVersion for *ticker*.

    Args:
        session: Async database session.
        ticker: Stock ticker symbol.

    Returns:
        The ModelVersion UUID for use in assertions.
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
    await session.flush()

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
    await session.flush()
    return mv_id


def _make_mock_factory(db_session):
    """Create a mock async_session_factory context manager backed by db_session.

    Args:
        db_session: The test async session to inject.

    Returns:
        Mock that behaves like async_session_factory().
    """
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=db_session)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    return mock_cm


# ---------------------------------------------------------------------------
# B2.2/B2.3 tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_single_ticker_inserts_one_row(db_session):
    """Calling _run_backtest_async with a single ticker inserts exactly one BacktestRun row.

    Verifies: row is for the correct ticker, horizon_days matches, completed == 1.
    """
    ticker = "XQ1"
    await _seed_stock_and_model(db_session, ticker)
    await db_session.commit()

    with (
        patch(
            "backend.tasks.forecasting.BacktestEngine.run_walk_forward",
            new_callable=AsyncMock,
            return_value=FAKE_METRICS,
        ),
        patch(
            "backend.tasks.forecasting.mark_stages_updated",
            new_callable=AsyncMock,
        ),
        patch(
            "backend.tasks.forecasting.async_session_factory",
            return_value=_make_mock_factory(db_session),
        ),
    ):
        result = await bypass_tracked(_run_backtest_async)(ticker, 90, run_id=uuid.uuid4())

    rows = (
        (await db_session.execute(select(BacktestRun).where(BacktestRun.ticker == ticker)))
        .scalars()
        .all()
    )
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
    tickers = ["XU1", "XU2", "XU3"]
    for tkr in tickers:
        await _seed_stock_and_model(db_session, tkr)
    await db_session.commit()

    with (
        patch(
            "backend.tasks.forecasting.BacktestEngine.run_walk_forward",
            new_callable=AsyncMock,
            return_value=FAKE_METRICS,
        ),
        patch(
            "backend.tasks.forecasting.mark_stages_updated",
            new_callable=AsyncMock,
        ),
        patch(
            "backend.tasks.forecasting.get_all_referenced_tickers",
            new_callable=AsyncMock,
            return_value=tickers,
        ),
        patch(
            "backend.tasks.forecasting.async_session_factory",
            return_value=_make_mock_factory(db_session),
        ),
    ):
        result = await bypass_tracked(_run_backtest_async)(None, 90, run_id=uuid.uuid4())

    rows = (
        (await db_session.execute(select(BacktestRun).where(BacktestRun.ticker.in_(tickers))))
        .scalars()
        .all()
    )
    assert len(rows) == 3
    assert result["completed"] == 3
    assert result["failed"] == 0


@pytest.mark.asyncio
async def test_per_ticker_failure_isolated(db_session):
    """A failure for one ticker does not block others.

    XF2 raises; XF1 and XF3 succeed.
    Asserts: 2 rows inserted for succeeding tickers, failed == 1, completed == 2.
    """
    tickers = ["XF1", "XF2", "XF3"]
    for tkr in tickers:
        await _seed_stock_and_model(db_session, tkr)
    await db_session.commit()

    async def _walk_forward_side_effect(tkr, db, **kwargs):
        if tkr == "XF2":
            raise RuntimeError("Simulated Prophet failure for XF2")
        return FAKE_METRICS

    with (
        patch(
            "backend.tasks.forecasting.BacktestEngine.run_walk_forward",
            side_effect=_walk_forward_side_effect,
        ),
        patch(
            "backend.tasks.forecasting.mark_stages_updated",
            new_callable=AsyncMock,
        ),
        patch(
            "backend.tasks.forecasting.get_all_referenced_tickers",
            new_callable=AsyncMock,
            return_value=tickers,
        ),
        patch(
            "backend.tasks.forecasting.async_session_factory",
            return_value=_make_mock_factory(db_session),
        ),
    ):
        result = await bypass_tracked(_run_backtest_async)(None, 90, run_id=uuid.uuid4())

    assert result["failed"] == 1
    assert result["completed"] == 2
    # Succeeding tickers got rows; failing ticker did not
    success_rows = (
        (
            await db_session.execute(
                select(BacktestRun).where(BacktestRun.ticker.in_(["XF1", "XF3"]))
            )
        )
        .scalars()
        .all()
    )
    assert len(success_rows) == 2
    failure_rows = (
        (await db_session.execute(select(BacktestRun).where(BacktestRun.ticker == "XF2")))
        .scalars()
        .all()
    )
    assert len(failure_rows) == 0


@pytest.mark.regression
@pytest.mark.asyncio
async def test_mark_stages_updated_called_with_successful_tickers_only(db_session):
    """KAN-438: bulk-mark backtest stage covers successful tickers only.

    XM1 succeeds, XM2 fails. Expects exactly ONE bulk
    ``mark_stages_updated`` call after the loop, with the ticker list
    containing only XM1 — failed tickers must NOT be in the bulk payload.
    """
    tickers = ["XM1", "XM2"]
    for tkr in tickers:
        await _seed_stock_and_model(db_session, tkr)
    await db_session.commit()

    async def _walk_forward_side_effect(tkr, db, **kwargs):
        if tkr == "XM2":
            raise RuntimeError("Planned failure for XM2")
        return FAKE_METRICS

    mock_mark = AsyncMock()
    with (
        patch(
            "backend.tasks.forecasting.BacktestEngine.run_walk_forward",
            side_effect=_walk_forward_side_effect,
        ),
        patch(
            "backend.tasks.forecasting.mark_stages_updated",
            mock_mark,
        ),
        patch(
            "backend.tasks.forecasting.get_all_referenced_tickers",
            new_callable=AsyncMock,
            return_value=tickers,
        ),
        patch(
            "backend.tasks.forecasting.async_session_factory",
            return_value=_make_mock_factory(db_session),
        ),
    ):
        await bypass_tracked(_run_backtest_async)(None, 90, run_id=uuid.uuid4())

    # Single bulk call after the loop, only with the successful ticker.
    assert mock_mark.await_count == 1
    call = mock_mark.await_args
    assert list(call.args[0]) == ["XM1"]
    assert call.args[1] == "backtest"


# ---------------------------------------------------------------------------
# KAN-438: per-ticker session — session-acquisition resilience + isolation
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.asyncio
async def test_session_acquisition_failure_for_one_ticker_does_not_kill_run(db_session):
    """C2 / KAN-438: a transient session-acquisition failure on one
    iteration must NOT abort the entire weekly backtest run.

    Patches async_session_factory so the SECOND iteration (XS2) raises
    OperationalError on `__aenter__`. Asserts XS1 and XS3 still complete,
    XS2 lands in `failed`, and the run as a whole returns normally.
    """
    from sqlalchemy.exc import OperationalError

    tickers = ["XS1", "XS2", "XS3"]
    for tkr in tickers:
        await _seed_stock_and_model(db_session, tkr)
    await db_session.commit()

    # Successful CMs share db_session; the bad one raises on __aenter__.
    good_cm = _make_mock_factory(db_session)
    bad_cm = MagicMock()
    bad_cm.__aenter__ = AsyncMock(
        side_effect=OperationalError("pool exhausted", {}, Exception("nope"))
    )
    bad_cm.__aexit__ = AsyncMock(return_value=False)

    call_index = {"n": 0}

    def _factory(*args, **kwargs):
        # Call sequence: 1 resolve + 3 per-ticker iterations.
        # n=0 → resolve (good); n=1,2,3 → XS1, XS2, XS3.
        call_index["n"] += 1
        if call_index["n"] == 3:  # XS2 iteration
            return bad_cm
        return good_cm

    with (
        patch(
            "backend.tasks.forecasting.BacktestEngine.run_walk_forward",
            new_callable=AsyncMock,
            return_value=FAKE_METRICS,
        ),
        patch(
            "backend.tasks.forecasting.mark_stages_updated",
            new_callable=AsyncMock,
        ),
        patch(
            "backend.tasks.forecasting.get_all_referenced_tickers",
            new_callable=AsyncMock,
            return_value=tickers,
        ),
        patch(
            "backend.tasks.forecasting.async_session_factory",
            side_effect=_factory,
        ),
    ):
        result = await bypass_tracked(_run_backtest_async)(None, 90, run_id=uuid.uuid4())

    # XS1 and XS3 succeeded; XS2 was skipped due to acquisition failure.
    assert result["completed"] == 2
    assert result["failed"] == 1


@pytest.mark.regression
@pytest.mark.asyncio
async def test_per_ticker_session_isolation_against_pending_rollback(db_session):
    """KAN-438: a SQLAlchemy PendingRollbackError on ticker N must NOT
    bleed into ticker N+1.

    The previous test using a plain RuntimeError did not actually exercise
    the session-isolation contract — RuntimeError doesn't corrupt SA
    session state. PendingRollbackError DOES, and is the failure mode the
    per-ticker pattern is supposed to defend against.
    """
    from sqlalchemy.exc import PendingRollbackError

    tickers = ["PI1", "PI2", "PI3"]
    for tkr in tickers:
        await _seed_stock_and_model(db_session, tkr)
    await db_session.commit()

    async def _walk_forward_side_effect(tkr, db, **kwargs):
        if tkr == "PI2":
            raise PendingRollbackError(
                "session is in a failed transaction state",
                None,
                None,
            )
        return FAKE_METRICS

    with (
        patch(
            "backend.tasks.forecasting.BacktestEngine.run_walk_forward",
            side_effect=_walk_forward_side_effect,
        ),
        patch(
            "backend.tasks.forecasting.mark_stages_updated",
            new_callable=AsyncMock,
        ),
        patch(
            "backend.tasks.forecasting.get_all_referenced_tickers",
            new_callable=AsyncMock,
            return_value=tickers,
        ),
        patch(
            "backend.tasks.forecasting.async_session_factory",
            return_value=_make_mock_factory(db_session),
        ),
    ):
        result = await bypass_tracked(_run_backtest_async)(None, 90, run_id=uuid.uuid4())

    # PI1 + PI3 must complete; PI2 must be in failed (not blocking PI3).
    assert result["completed"] == 2
    assert result["failed"] == 1
    success_rows = (
        (
            await db_session.execute(
                select(BacktestRun).where(BacktestRun.ticker.in_(["PI1", "PI3"]))
            )
        )
        .scalars()
        .all()
    )
    assert len(success_rows) == 2


# ---------------------------------------------------------------------------
# KAN-438: per-ticker session — session is opened fresh for every iteration
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.asyncio
async def test_per_ticker_session_factory_called_once_per_iteration(db_session):
    """KAN-438: a fresh session is acquired per ticker iteration.

    NB: this test verifies *call count* only, not session-state isolation.
    See ``test_per_ticker_session_isolation_against_pending_rollback`` for
    the actual isolation contract.


    Previously the ticker loop ran inside a single ``async with
    async_session_factory()`` block, holding one connection open for the
    entire weekly run (~500 tickers × ~110 windows). The fix opens a fresh
    session per ticker.

    Asserts the factory is invoked N+1 times for N tickers (1 for the initial
    ticker-list resolution + N for the iterations).
    """
    tickers = ["PT1", "PT2", "PT3"]
    for tkr in tickers:
        await _seed_stock_and_model(db_session, tkr)
    await db_session.commit()

    # Wrap the existing mock factory in a MagicMock that records calls
    inner_cm = _make_mock_factory(db_session)
    factory_call_count = 0

    def _counting_factory(*args, **kwargs):
        nonlocal factory_call_count
        factory_call_count += 1
        return inner_cm

    with (
        patch(
            "backend.tasks.forecasting.BacktestEngine.run_walk_forward",
            new_callable=AsyncMock,
            return_value=FAKE_METRICS,
        ),
        patch(
            "backend.tasks.forecasting.mark_stages_updated",
            new_callable=AsyncMock,
        ),
        patch(
            "backend.tasks.forecasting.get_all_referenced_tickers",
            new_callable=AsyncMock,
            return_value=tickers,
        ),
        patch(
            "backend.tasks.forecasting.async_session_factory",
            side_effect=_counting_factory,
        ),
    ):
        await bypass_tracked(_run_backtest_async)(None, 90, run_id=uuid.uuid4())

    # 1 for initial ticker-list resolution + 1 per ticker iteration
    assert factory_call_count == len(tickers) + 1, (
        f"Expected {len(tickers) + 1} session factory invocations "
        f"(1 resolve + {len(tickers)} per-ticker), got {factory_call_count}"
    )


# ---------------------------------------------------------------------------
# B2 regression: no active ModelVersion must not count as success
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.asyncio
async def test_no_active_model_version_skips_row_and_marks_failed(db_session):
    """When no active ModelVersion exists for a ticker, the task must not
    persist a BacktestRun row, must not include the ticker in the bulk
    stage-mark, and must count the ticker as failed (not completed).

    Regression for the placement bug where mark_stage_updated and completed+=1
    were called unconditionally outside the success branch.
    """
    from backend.models.backtest import BacktestRun
    from backend.models.stock import Stock

    ticker = "NOMV"
    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)

    # Seed Stock row only — intentionally NO ModelVersion for this ticker
    stock_id = __import__("uuid").uuid4()
    db_session.add(
        Stock(
            id=stock_id,
            ticker=ticker,
            name="NOMV Corp",
            exchange="TEST",
            sector="Technology",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
    )
    await db_session.commit()

    mock_mark = AsyncMock()
    with (
        patch(
            "backend.tasks.forecasting.BacktestEngine.run_walk_forward",
            new_callable=AsyncMock,
            return_value=FAKE_METRICS,
        ),
        patch(
            "backend.tasks.forecasting.mark_stages_updated",
            mock_mark,
        ),
        patch(
            "backend.tasks.forecasting.async_session_factory",
            return_value=_make_mock_factory(db_session),
        ),
    ):
        result = await bypass_tracked(_run_backtest_async)(ticker, 90, run_id=uuid.uuid4())

    # No BacktestRun row should have been written
    rows = (
        (await db_session.execute(select(BacktestRun).where(BacktestRun.ticker == ticker)))
        .scalars()
        .all()
    )
    assert len(rows) == 0, "BacktestRun row must NOT be written when ModelVersion is missing"

    # Counts must reflect failure, not success
    assert result["completed"] == 0, "completed must be 0 when no ModelVersion found"
    assert result["failed"] == 1, "failed must be 1 when no ModelVersion found"

    # Bulk stage mark must NOT be called — successful_tickers is empty,
    # so the post-loop `if successful_tickers:` short-circuits.
    mock_mark.assert_not_called()
