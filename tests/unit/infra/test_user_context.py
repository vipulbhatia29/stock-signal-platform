"""Tests for user context builder."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class FakePosition:
    """Minimal position stand-in."""

    def __init__(self, ticker: str, shares: float, avg_cost: float, alloc: float):
        """Initialize position."""
        self.ticker = ticker
        self.shares = shares
        self.avg_cost_basis = avg_cost
        self.allocation_pct = alloc
        self.sector = "Technology"


class FakePortfolio:
    """Minimal portfolio stand-in."""

    id = uuid.uuid4()


def _mock_session_factory(execute_side_effects: list[MagicMock]) -> AsyncMock:
    """Build a mock async_session_factory that yields sessions with preset results.

    Each call to async_session_factory() returns a new context manager whose
    session.execute returns the next side_effect in order.
    """
    call_idx = {"i": 0}

    def _factory() -> AsyncMock:
        idx = call_idx["i"]
        call_idx["i"] += 1
        mock_session = AsyncMock()
        if idx < len(execute_side_effects):
            mock_session.execute = AsyncMock(return_value=execute_side_effects[idx])
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=mock_session)
        cm.__aexit__ = AsyncMock(return_value=False)
        return cm

    return _factory


class TestBuildUserContext:
    """Tests for build_user_context."""

    @pytest.mark.asyncio
    async def test_returns_positions_and_watchlist(self) -> None:
        """Should return portfolio positions, preferences, and watchlist."""
        user_id = uuid.uuid4()
        mock_db = AsyncMock()

        positions = [
            FakePosition("AAPL", 10.0, 150.0, 35.0),
            FakePosition("PLTR", 100.0, 25.0, 65.0),
        ]

        # Mock preferences query result
        mock_pref = MagicMock()
        mock_pref.max_position_pct = 5.0
        mock_pref.max_sector_pct = 25.0
        mock_pref.default_stop_loss_pct = 8.0

        pref_result = MagicMock()
        pref_result.scalar_one_or_none.return_value = mock_pref

        # Mock watchlist query result
        watchlist_result = MagicMock()
        watchlist_result.all.return_value = [("AAPL",), ("PLTR",), ("MSFT",)]

        factory = _mock_session_factory([pref_result, watchlist_result])

        with (
            patch(
                "backend.services.portfolio.get_or_create_portfolio",
                new_callable=AsyncMock,
                return_value=FakePortfolio(),
            ),
            patch(
                "backend.services.portfolio.get_positions_with_pnl",
                new_callable=AsyncMock,
                return_value=positions,
            ),
            patch(
                "backend.database.async_session_factory",
                new=factory,
            ),
        ):
            from backend.agents.user_context import build_user_context

            ctx = await build_user_context(user_id, mock_db)

        assert len(ctx["positions"]) == 2
        assert ctx["held_tickers"] == ["AAPL", "PLTR"]
        assert ctx["sector_allocation"]["Technology"] == 100.0
        assert ctx["preferences"]["max_position_pct"] == 5.0
        assert ctx["watchlist"] == ["AAPL", "PLTR", "MSFT"]

    @pytest.mark.asyncio
    async def test_new_user_returns_empty_context(self) -> None:
        """New user with no portfolio should return empty defaults."""
        user_id = uuid.uuid4()
        mock_db = AsyncMock()

        # Preferences: none
        pref_result = MagicMock()
        pref_result.scalar_one_or_none.return_value = None
        # Watchlist: empty
        watchlist_result = MagicMock()
        watchlist_result.all.return_value = []

        factory = _mock_session_factory([pref_result, watchlist_result])

        with (
            patch(
                "backend.services.portfolio.get_or_create_portfolio",
                new_callable=AsyncMock,
                return_value=FakePortfolio(),
            ),
            patch(
                "backend.services.portfolio.get_positions_with_pnl",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "backend.database.async_session_factory",
                new=factory,
            ),
        ):
            from backend.agents.user_context import build_user_context

            ctx = await build_user_context(user_id, mock_db)

        assert ctx["positions"] == []
        assert ctx["held_tickers"] == []
        assert ctx["preferences"] == {}
        assert ctx["watchlist"] == []

    @pytest.mark.asyncio
    async def test_portfolio_failure_returns_partial_context(self) -> None:
        """If portfolio query fails, other fields still populated."""
        user_id = uuid.uuid4()
        mock_db = AsyncMock()

        pref_result = MagicMock()
        pref_result.scalar_one_or_none.return_value = None
        watchlist_result = MagicMock()
        watchlist_result.all.return_value = [("TSLA",)]

        factory = _mock_session_factory([pref_result, watchlist_result])

        with (
            patch(
                "backend.services.portfolio.get_or_create_portfolio",
                new_callable=AsyncMock,
                side_effect=Exception("DB error"),
            ),
            patch(
                "backend.database.async_session_factory",
                new=factory,
            ),
        ):
            from backend.agents.user_context import build_user_context

            ctx = await build_user_context(user_id, mock_db)

        assert ctx["positions"] == []
        assert ctx["watchlist"] == ["TSLA"]
