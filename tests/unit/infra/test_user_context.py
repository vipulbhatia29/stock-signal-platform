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

        # Mock preferences query
        mock_pref = MagicMock()
        mock_pref.max_position_pct = 5.0
        mock_pref.max_sector_pct = 25.0
        mock_pref.default_stop_loss_pct = 8.0

        pref_result = MagicMock()
        pref_result.scalar_one_or_none.return_value = mock_pref

        # Mock watchlist query
        watchlist_result = MagicMock()
        watchlist_result.all.return_value = [("AAPL",), ("PLTR",), ("MSFT",)]

        mock_db.execute = AsyncMock(side_effect=[pref_result, watchlist_result])

        with (
            patch(
                "backend.tools.portfolio.get_or_create_portfolio",
                new_callable=AsyncMock,
                return_value=FakePortfolio(),
            ),
            patch(
                "backend.tools.portfolio.get_positions_with_pnl",
                new_callable=AsyncMock,
                return_value=positions,
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

        mock_db.execute = AsyncMock(side_effect=[pref_result, watchlist_result])

        with (
            patch(
                "backend.tools.portfolio.get_or_create_portfolio",
                new_callable=AsyncMock,
                return_value=FakePortfolio(),
            ),
            patch(
                "backend.tools.portfolio.get_positions_with_pnl",
                new_callable=AsyncMock,
                return_value=[],
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

        mock_db.execute = AsyncMock(side_effect=[pref_result, watchlist_result])

        with patch(
            "backend.tools.portfolio.get_or_create_portfolio",
            new_callable=AsyncMock,
            side_effect=Exception("DB error"),
        ):
            from backend.agents.user_context import build_user_context

            ctx = await build_user_context(user_id, mock_db)

        assert ctx["positions"] == []
        assert ctx["watchlist"] == ["TSLA"]
