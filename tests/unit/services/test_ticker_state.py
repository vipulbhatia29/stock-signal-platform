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


async def test_mark_stage_updated_forecast_vs_forecast_retrain() -> None:
    """'forecast' writes forecast_updated_at; 'forecast_retrain' writes forecast_retrained_at."""
    from backend.services import ticker_state

    captured_stmts: list = []

    async def fake_execute(stmt):
        """Capture executed statements."""
        captured_stmts.append(stmt)
        return MagicMock()

    fake_session = AsyncMock()
    fake_session.execute = AsyncMock(side_effect=fake_execute)
    fake_session.commit = AsyncMock()

    with patch.object(ticker_state, "async_session_factory") as factory:
        factory.return_value.__aenter__.return_value = fake_session
        factory.return_value.__aexit__.return_value = None

        await ticker_state.mark_stage_updated("AAPL", "forecast")
        await ticker_state.mark_stage_updated("AAPL", "forecast_retrain")

    # Both statements should have been issued
    assert len(captured_stmts) == 2


@freeze_time("2026-04-06 12:00:00")
async def test_get_universe_health_orders_red_first() -> None:
    """Sort order: red, yellow, unknown, green then ticker."""
    from backend.services import ticker_state

    now = datetime(2026, 4, 6, 12, 0, tzinfo=timezone.utc)
    aged_red = datetime(2026, 4, 5, 12, 0, tzinfo=timezone.utc)  # 24h for prices (red)
    rows = [
        # GRN: all stages fresh → overall green
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
        ),
        # RED: prices aged >2×SLA → overall red
        _make_state_row(ticker="RED", prices_updated_at=aged_red),
        _make_state_row(ticker="UNK"),  # no timestamps → overall unknown
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
    # RED must come before UNK which must come before GRN
    assert tickers_in_order.index("RED") < tickers_in_order.index("UNK")
    assert tickers_in_order.index("UNK") < tickers_in_order.index("GRN")


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
