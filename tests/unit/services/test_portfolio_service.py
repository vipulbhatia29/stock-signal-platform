"""Unit tests for backend.services.portfolio."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.services.portfolio import (
    _run_fifo,
    delete_transaction,
    get_or_create_portfolio,
    get_positions_with_pnl,
)

# ---------------------------------------------------------------------------
# _run_fifo (pure function — no mocks needed)
# ---------------------------------------------------------------------------


class TestRunFifo:
    """Tests for the pure FIFO calculation engine."""

    def test_single_buy_returns_shares_and_cost(self) -> None:
        """A single BUY should return shares held at purchase price."""
        txns = [
            {
                "type": "BUY",
                "shares": Decimal("10"),
                "price": Decimal("50.00"),
                "at": datetime(2024, 1, 1),
            },
        ]
        result = _run_fifo(txns)
        assert result["shares"] == Decimal("10")
        assert result["avg_cost_basis"] == Decimal("50.00")
        assert result["closed_at"] is None

    def test_buy_then_full_sell_returns_zero(self) -> None:
        """BUY then SELL of same quantity should return zero shares."""
        txns = [
            {
                "type": "BUY",
                "shares": Decimal("10"),
                "price": Decimal("50.00"),
                "at": datetime(2024, 1, 1),
            },
            {
                "type": "SELL",
                "shares": Decimal("10"),
                "price": Decimal("60.00"),
                "at": datetime(2024, 2, 1),
            },
        ]
        result = _run_fifo(txns)
        assert result["shares"] == Decimal("0")
        assert result["avg_cost_basis"] == Decimal("0")
        assert result["closed_at"] == datetime(2024, 2, 1)

    def test_fifo_order_two_lots(self) -> None:
        """FIFO should consume the oldest lot first."""
        txns = [
            {
                "type": "BUY",
                "shares": Decimal("5"),
                "price": Decimal("40.00"),
                "at": datetime(2024, 1, 1),
            },
            {
                "type": "BUY",
                "shares": Decimal("5"),
                "price": Decimal("60.00"),
                "at": datetime(2024, 2, 1),
            },
            {
                "type": "SELL",
                "shares": Decimal("5"),
                "price": Decimal("70.00"),
                "at": datetime(2024, 3, 1),
            },
        ]
        result = _run_fifo(txns)
        # After selling the first lot of 5@40, remaining is 5@60
        assert result["shares"] == Decimal("5")
        assert result["avg_cost_basis"] == Decimal("60.00")
        assert result["closed_at"] is None

    def test_sell_exceeds_lots_raises_value_error(self) -> None:
        """Selling more than available should raise ValueError."""
        txns = [
            {
                "type": "BUY",
                "shares": Decimal("5"),
                "price": Decimal("40.00"),
                "at": datetime(2024, 1, 1),
            },
            {
                "type": "SELL",
                "shares": Decimal("10"),
                "price": Decimal("50.00"),
                "at": datetime(2024, 2, 1),
            },
        ]
        with pytest.raises(ValueError, match="Insufficient shares"):
            _run_fifo(txns)


# ---------------------------------------------------------------------------
# get_or_create_portfolio
# ---------------------------------------------------------------------------


class TestGetOrCreatePortfolio:
    """Tests for get_or_create_portfolio."""

    @pytest.mark.asyncio
    async def test_returns_existing_portfolio(self) -> None:
        """When a portfolio already exists, return it without creating."""
        user_id = uuid.uuid4()
        mock_portfolio = MagicMock()
        mock_portfolio.user_id = user_id
        mock_portfolio.name = "My Portfolio"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_portfolio

        db = AsyncMock()
        db.execute.return_value = mock_result

        portfolio = await get_or_create_portfolio(user_id, db)

        assert portfolio is mock_portfolio
        db.add.assert_not_called()
        db.flush.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_creates_new_portfolio_when_missing(self) -> None:
        """When no portfolio exists, create one and flush."""
        user_id = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        db = AsyncMock()
        db.execute.return_value = mock_result

        portfolio = await get_or_create_portfolio(user_id, db)

        assert portfolio.user_id == user_id
        assert portfolio.name == "My Portfolio"
        db.add.assert_called_once()
        db.flush.assert_awaited_once()


# ---------------------------------------------------------------------------
# get_positions_with_pnl
# ---------------------------------------------------------------------------


class TestGetPositionsWithPnl:
    """Tests for get_positions_with_pnl with FIFO-computed positions."""

    @pytest.mark.asyncio
    async def test_returns_pnl_for_open_positions(self) -> None:
        """Should compute unrealized P&L from positions and latest prices."""
        portfolio_id = uuid.uuid4()

        # Mock position
        mock_pos = MagicMock()
        mock_pos.ticker = "AAPL"
        mock_pos.shares = Decimal("10")
        mock_pos.avg_cost_basis = Decimal("150.00")
        mock_pos.closed_at = None

        # Mock DB responses: positions query, sector query, price query
        pos_result = MagicMock()
        pos_result.scalars.return_value.all.return_value = [mock_pos]

        sector_row = MagicMock()
        sector_row.ticker = "AAPL"
        sector_row.sector = "Technology"
        sector_result = MagicMock()
        sector_result.__iter__ = MagicMock(return_value=iter([sector_row]))

        price_row = MagicMock()
        price_row.ticker = "AAPL"
        price_row.adj_close = Decimal("170.00")
        price_result = MagicMock()
        price_result.__iter__ = MagicMock(return_value=iter([price_row]))

        db = AsyncMock()
        db.execute.side_effect = [pos_result, sector_result, price_result]

        responses = await get_positions_with_pnl(portfolio_id, db)

        assert len(responses) == 1
        resp = responses[0]
        assert resp.ticker == "AAPL"
        assert resp.shares == 10.0
        assert resp.avg_cost_basis == 150.0
        assert resp.current_price == 170.0
        assert resp.market_value == 1700.0
        assert resp.unrealized_pnl == 200.0  # (170-150)*10
        assert resp.sector == "Technology"


# ---------------------------------------------------------------------------
# delete_transaction
# ---------------------------------------------------------------------------


class TestDeleteTransaction:
    """Tests for delete_transaction."""

    @pytest.mark.asyncio
    async def test_not_found_raises_error(self) -> None:
        """Should raise PortfolioNotFoundError when transaction doesn't exist."""
        from backend.services.exceptions import PortfolioNotFoundError

        portfolio_id = uuid.uuid4()
        txn_id = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        db = AsyncMock()
        db.execute.return_value = mock_result

        with pytest.raises(PortfolioNotFoundError):
            await delete_transaction(portfolio_id, txn_id, db)

    @pytest.mark.asyncio
    async def test_delete_breaks_fifo_raises_value_error(self) -> None:
        """Should raise ValueError if deleting a BUY would strand a SELL."""
        portfolio_id = uuid.uuid4()
        txn_id = uuid.uuid4()
        buy_id = uuid.uuid4()

        # The transaction to delete is a BUY
        mock_txn = MagicMock()
        mock_txn.id = buy_id
        mock_txn.ticker = "AAPL"
        mock_txn.transaction_type = "BUY"

        # First call: find transaction
        find_result = MagicMock()
        find_result.scalar_one_or_none.return_value = mock_txn

        # Second call: _get_transactions_for_ticker returns BUY + SELL
        # but removing the BUY leaves only the SELL which breaks FIFO
        txn_rows = MagicMock()
        sell_txn = MagicMock()
        sell_txn.id = uuid.uuid4()
        sell_txn.transaction_type = "SELL"
        sell_txn.shares = Decimal("10")
        sell_txn.price_per_share = Decimal("60")
        sell_txn.transacted_at = datetime(2024, 3, 1, tzinfo=timezone.utc)
        sell_txn.ticker = "AAPL"

        buy_txn = MagicMock()
        buy_txn.id = buy_id
        buy_txn.transaction_type = "BUY"
        buy_txn.shares = Decimal("10")
        buy_txn.price_per_share = Decimal("50")
        buy_txn.transacted_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
        buy_txn.ticker = "AAPL"

        txn_rows.scalars.return_value.all.return_value = [buy_txn, sell_txn]

        db = AsyncMock()
        db.execute.side_effect = [find_result, txn_rows]

        with pytest.raises(ValueError, match="Insufficient shares"):
            await delete_transaction(portfolio_id, txn_id, db)
