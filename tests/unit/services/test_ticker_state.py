"""Unit tests for ticker_state service and staleness SLAs."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from freezegun import freeze_time

pytestmark = pytest.mark.asyncio


def test_staleness_slas_exact_values() -> None:
    """Change-detector: any SLA edit must be deliberate and reviewed.

    Spec A §A2 pins these values. Do not relax without a PR + PM approval.
    """
    from backend.config import StalenessSLAs

    sla = StalenessSLAs()
    assert sla.prices == timedelta(hours=4)
    assert sla.signals == timedelta(hours=4)
    assert sla.fundamentals == timedelta(hours=24)
    assert sla.forecast == timedelta(hours=24)
    assert sla.forecast_retrain == timedelta(days=14)
    assert sla.news == timedelta(hours=6)
    assert sla.sentiment == timedelta(hours=6)
    assert sla.convergence == timedelta(hours=24)
    assert sla.backtest == timedelta(days=7)
    assert sla.recommendation == timedelta(hours=24)


def test_settings_staleness_slas_property_returns_instance() -> None:
    """`settings.staleness_slas` must yield a StalenessSLAs instance."""
    from backend.config import StalenessSLAs, settings

    assert isinstance(settings.staleness_slas, StalenessSLAs)


def _make_state_row(**overrides):
    """Build a TickerIngestionState instance with sensible defaults."""
    from backend.models.ticker_ingestion_state import TickerIngestionState

    now = datetime(2026, 4, 6, 12, 0, tzinfo=timezone.utc)
    defaults = {
        "ticker": "AAPL",
        "prices_updated_at": None,
        "signals_updated_at": None,
        "fundamentals_updated_at": None,
        "forecast_updated_at": None,
        "forecast_retrained_at": None,
        "news_updated_at": None,
        "sentiment_updated_at": None,
        "convergence_updated_at": None,
        "backtest_updated_at": None,
        "recommendation_updated_at": None,
        "last_error": None,
        "created_at": now,
        "updated_at": now,
    }
    defaults.update(overrides)
    return TickerIngestionState(**defaults)


@freeze_time("2026-04-06 12:00:00")
async def test_get_ticker_readiness_missing_row_returns_unknown() -> None:
    """Missing row → every stage is 'unknown', overall 'unknown'."""
    from backend.services import ticker_state

    fake_session = AsyncMock()
    fake_result = MagicMock()
    fake_result.scalar_one_or_none.return_value = None
    fake_session.execute = AsyncMock(return_value=fake_result)

    with patch.object(ticker_state, "async_session_factory") as factory:
        factory.return_value.__aenter__.return_value = fake_session
        factory.return_value.__aexit__.return_value = None
        readiness = await ticker_state.get_ticker_readiness("ZZZZ")

    assert readiness.ticker == "ZZZZ"
    assert readiness.overall == "unknown"
    assert all(v == "unknown" for v in readiness.stages.values())


@freeze_time("2026-04-06 12:00:00")
async def test_get_ticker_readiness_green_when_fresh() -> None:
    """All stages fresh → green."""
    from backend.services import ticker_state

    now = datetime(2026, 4, 6, 12, 0, tzinfo=timezone.utc)
    row = _make_state_row(
        prices_updated_at=now,
        signals_updated_at=now,
        fundamentals_updated_at=now,
        forecast_updated_at=now,
        forecast_retrained_at=now,
        news_updated_at=now,
        sentiment_updated_at=now,
        convergence_updated_at=now,
        backtest_updated_at=now,
        recommendation_updated_at=now,
    )

    fake_session = AsyncMock()
    fake_result = MagicMock()
    fake_result.scalar_one_or_none.return_value = row
    fake_session.execute = AsyncMock(return_value=fake_result)

    with patch.object(ticker_state, "async_session_factory") as factory:
        factory.return_value.__aenter__.return_value = fake_session
        factory.return_value.__aexit__.return_value = None
        readiness = await ticker_state.get_ticker_readiness("AAPL")

    assert readiness.overall == "green"
    assert all(v == "green" for v in readiness.stages.values())


@freeze_time("2026-04-06 12:00:00")
async def test_get_ticker_readiness_yellow_between_1x_and_2x_sla() -> None:
    """Aged 1.5× SLA → yellow."""
    from backend.services import ticker_state

    aged = datetime(2026, 4, 6, 6, 0, tzinfo=timezone.utc)  # 6h old — prices SLA 4h
    row = _make_state_row(prices_updated_at=aged)

    fake_session = AsyncMock()
    fake_result = MagicMock()
    fake_result.scalar_one_or_none.return_value = row
    fake_session.execute = AsyncMock(return_value=fake_result)

    with patch.object(ticker_state, "async_session_factory") as factory:
        factory.return_value.__aenter__.return_value = fake_session
        factory.return_value.__aexit__.return_value = None
        readiness = await ticker_state.get_ticker_readiness("AAPL")

    assert readiness.stages["prices"] == "yellow"
    # 6h < 2x4h=8h ⇒ yellow; sanity check the math
    assert (datetime(2026, 4, 6, 12, 0, tzinfo=timezone.utc) - aged) == timedelta(hours=6)


@freeze_time("2026-04-06 12:00:00")
async def test_get_ticker_readiness_red_beyond_2x_sla() -> None:
    """Aged >2× SLA → red."""
    from backend.services import ticker_state

    aged = datetime(2026, 4, 5, 20, 0, tzinfo=timezone.utc)  # 16h old — prices SLA 4h
    row = _make_state_row(prices_updated_at=aged)

    fake_session = AsyncMock()
    fake_result = MagicMock()
    fake_result.scalar_one_or_none.return_value = row
    fake_session.execute = AsyncMock(return_value=fake_result)

    with patch.object(ticker_state, "async_session_factory") as factory:
        factory.return_value.__aenter__.return_value = fake_session
        factory.return_value.__aexit__.return_value = None
        readiness = await ticker_state.get_ticker_readiness("AAPL")

    assert readiness.stages["prices"] == "red"


@freeze_time("2026-04-06 12:00:00")
async def test_get_ticker_readiness_overall_is_worst_stage() -> None:
    """Overall is the minimum over (red<yellow<unknown<green)."""
    from backend.services import ticker_state

    now = datetime(2026, 4, 6, 12, 0, tzinfo=timezone.utc)
    row = _make_state_row(
        prices_updated_at=now,  # green
        forecast_updated_at=now,  # placeholder — will be overridden below
    )
    # forecast SLA 24h. For red we need >48h.
    row.forecast_updated_at = datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc)  # 72h

    fake_session = AsyncMock()
    fake_result = MagicMock()
    fake_result.scalar_one_or_none.return_value = row
    fake_session.execute = AsyncMock(return_value=fake_result)

    with patch.object(ticker_state, "async_session_factory") as factory:
        factory.return_value.__aenter__.return_value = fake_session
        factory.return_value.__aexit__.return_value = None
        readiness = await ticker_state.get_ticker_readiness("AAPL")

    assert readiness.stages["prices"] == "green"
    assert readiness.stages["forecast"] == "red"
    assert readiness.overall == "red"


async def test_mark_stage_updated_swallows_db_error() -> None:
    """Fire-and-forget: DB errors must never propagate."""
    from backend.services import ticker_state

    with patch.object(ticker_state, "async_session_factory", side_effect=RuntimeError("db dead")):
        # Must return None, not raise
        await ticker_state.mark_stage_updated("AAPL", "prices")


async def test_mark_stage_updated_with_db_uses_caller_session_no_commit() -> None:
    """When db is provided: execute on caller's session and DO NOT commit.

    KAN-436: ingest_ticker hot path passes its own session to avoid 3 extra
    connection checkouts. Caller owns commit semantics.
    """
    from backend.services import ticker_state

    fake_session = AsyncMock()
    fake_session.execute = AsyncMock()
    fake_session.commit = AsyncMock()

    # Factory must NOT be called when db is provided
    with patch.object(
        ticker_state,
        "async_session_factory",
        side_effect=AssertionError("factory must not be called when db is passed"),
    ):
        await ticker_state.mark_stage_updated("AAPL", "prices", db=fake_session)

    fake_session.execute.assert_awaited_once()
    fake_session.commit.assert_not_called()


async def test_mark_stages_updated_empty_list_is_noop() -> None:
    """Empty ticker list must short-circuit without touching the DB."""
    from backend.services import ticker_state

    with patch.object(
        ticker_state,
        "async_session_factory",
        side_effect=AssertionError("factory must not be called for empty list"),
    ):
        await ticker_state.mark_stages_updated([], "prices")


async def test_mark_stages_updated_bulk_single_execute_for_n_tickers() -> None:
    """KAN-436: bulk helper issues exactly ONE execute for N tickers, not N.

    The whole point of mark_stages_updated is to eliminate the per-ticker
    round-trips of looping mark_stage_updated. This pins that contract.
    """
    from backend.services import ticker_state

    fake_session = AsyncMock()
    fake_session.execute = AsyncMock()
    fake_session.commit = AsyncMock()

    factory_cm = MagicMock()
    factory_cm.__aenter__ = AsyncMock(return_value=fake_session)
    factory_cm.__aexit__ = AsyncMock(return_value=False)

    with patch.object(ticker_state, "async_session_factory", return_value=factory_cm):
        await ticker_state.mark_stages_updated(
            ["AAPL", "MSFT", "GOOG", "AMZN", "META"], "convergence"
        )

    # Exactly ONE execute call for 5 tickers (not 5).
    assert fake_session.execute.await_count == 1
    fake_session.commit.assert_awaited_once()


async def test_mark_stages_updated_with_db_uses_caller_session_no_commit() -> None:
    """When db is provided: execute on caller's session and DO NOT commit."""
    from backend.services import ticker_state

    fake_session = AsyncMock()
    fake_session.execute = AsyncMock()
    fake_session.commit = AsyncMock()

    with patch.object(
        ticker_state,
        "async_session_factory",
        side_effect=AssertionError("factory must not be called when db is passed"),
    ):
        await ticker_state.mark_stages_updated(["AAPL", "MSFT"], "signals", db=fake_session)

    fake_session.execute.assert_awaited_once()
    fake_session.commit.assert_not_called()


async def test_mark_stages_updated_swallows_db_error() -> None:
    """Fire-and-forget: bulk helper must not propagate DB errors either."""
    from backend.services import ticker_state

    with patch.object(ticker_state, "async_session_factory", side_effect=RuntimeError("db dead")):
        # Must return None, not raise
        await ticker_state.mark_stages_updated(["AAPL", "MSFT"], "prices")


async def test_mark_stages_updated_all_empty_or_whitespace_is_noop() -> None:
    """Filters out falsy entries — no statement is issued for [''] or [None]."""
    from backend.services import ticker_state

    with patch.object(
        ticker_state,
        "async_session_factory",
        side_effect=AssertionError("factory must not be called"),
    ):
        await ticker_state.mark_stages_updated(["", ""], "prices")


@freeze_time("2026-04-06 12:00:00")
async def test_get_universe_health_orders_red_yellow_unknown_green() -> None:
    """Sort order must be: red < yellow < unknown < green (then ticker ascending).

    This pins all 4 buckets. The previous test only had 3 buckets and a
    partial ordering check. Test is deterministic via @freeze_time.
    """
    from backend.services import ticker_state

    now = datetime(2026, 4, 6, 12, 0, tzinfo=timezone.utc)
    # prices SLA = 4h. 1.5x = 6h → yellow. 2.5x = 10h → red.
    aged_yellow = datetime(2026, 4, 6, 6, 0, tzinfo=timezone.utc)  # 6h old → yellow
    aged_red = datetime(2026, 4, 6, 1, 0, tzinfo=timezone.utc)  # 11h old → red (>2×4h)
    rows = [
        # GRN: all stages fresh
        _make_state_row(
            ticker="GRN",
            prices_updated_at=now,
            signals_updated_at=now,
            fundamentals_updated_at=now,
            forecast_updated_at=now,
            forecast_retrained_at=now,
            news_updated_at=now,
            sentiment_updated_at=now,
            convergence_updated_at=now,
            backtest_updated_at=now,
            recommendation_updated_at=now,
        ),
        # RED: prices aged >2×SLA (>8h) → red
        _make_state_row(ticker="RED", prices_updated_at=aged_red),
        # UNK: no timestamps at all → unknown
        _make_state_row(ticker="UNK"),
        # YLW: prices aged between 1×SLA and 2×SLA (4h–8h) → yellow
        _make_state_row(ticker="YLW", prices_updated_at=aged_yellow),
    ]

    fake_session = AsyncMock()
    fake_result = MagicMock()
    fake_result.scalars.return_value = rows
    fake_session.execute = AsyncMock(return_value=fake_result)

    with patch.object(ticker_state, "async_session_factory") as factory:
        factory.return_value.__aenter__.return_value = fake_session
        factory.return_value.__aexit__.return_value = None
        health = await ticker_state.get_universe_health()

    tickers_in_order = [r.ticker for r in health]
    # Assert exact bucket ordering: red < yellow < unknown < green
    assert tickers_in_order.index("RED") < tickers_in_order.index("YLW"), (
        f"Expected RED before YLW; got {tickers_in_order}"
    )
    assert tickers_in_order.index("YLW") < tickers_in_order.index("UNK"), (
        f"Expected YLW before UNK; got {tickers_in_order}"
    )
    assert tickers_in_order.index("UNK") < tickers_in_order.index("GRN"), (
        f"Expected UNK before GRN; got {tickers_in_order}"
    )
    # Also verify the overall status values match expectations
    status_map = {r.ticker: r.overall for r in health}
    assert status_map["RED"] == "red"
    assert status_map["YLW"] == "yellow"
    assert status_map["UNK"] == "unknown"
    assert status_map["GRN"] == "green"


async def test_get_universe_health_empty_table_returns_empty_list() -> None:
    """Empty table → empty list (not None, not error)."""
    from backend.services import ticker_state

    fake_session = AsyncMock()
    fake_result = MagicMock()
    fake_result.scalars.return_value = []
    fake_session.execute = AsyncMock(return_value=fake_result)

    with patch.object(ticker_state, "async_session_factory") as factory:
        factory.return_value.__aenter__.return_value = fake_session
        factory.return_value.__aexit__.return_value = None
        health = await ticker_state.get_universe_health()

    assert health == []
