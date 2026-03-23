"""Unit tests for FIFO cost basis and portfolio P&L computation."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from backend.tools.portfolio import _run_fifo


def _dt(day: int) -> datetime:
    """Helper: create a UTC datetime at day N of 2026."""
    return datetime(2026, 1, day, tzinfo=timezone.utc)


def test_fifo_single_buy_no_sells():
    """Single BUY with no SELLs → full shares at cost."""
    txns = [
        {"type": "BUY", "shares": Decimal("10"), "price": Decimal("100"), "at": _dt(1)},
    ]
    result = _run_fifo(txns)
    assert result["shares"] == Decimal("10")
    assert result["avg_cost_basis"] == Decimal("100")
    assert result["closed_at"] is None


def test_fifo_multiple_buys_weighted_average():
    """Multiple BUYs → weighted average cost of remaining lots."""
    txns = [
        {"type": "BUY", "shares": Decimal("10"), "price": Decimal("100"), "at": _dt(1)},
        {"type": "BUY", "shares": Decimal("10"), "price": Decimal("200"), "at": _dt(2)},
    ]
    result = _run_fifo(txns)
    assert result["shares"] == Decimal("20")
    assert result["avg_cost_basis"] == Decimal("150")  # (10*100 + 10*200) / 20


def test_fifo_partial_sell_consumes_oldest_lots():
    """SELL of 5 shares against 10-share BUY lot → 5 shares remain."""
    txns = [
        {"type": "BUY", "shares": Decimal("10"), "price": Decimal("100"), "at": _dt(1)},
        {"type": "SELL", "shares": Decimal("5"), "price": Decimal("150"), "at": _dt(2)},
    ]
    result = _run_fifo(txns)
    assert result["shares"] == Decimal("5")
    assert result["avg_cost_basis"] == Decimal("100")


def test_fifo_full_sell_closes_position():
    """SELL of all shares → shares=0, closed_at set."""
    txns = [
        {"type": "BUY", "shares": Decimal("10"), "price": Decimal("100"), "at": _dt(1)},
        {"type": "SELL", "shares": Decimal("10"), "price": Decimal("150"), "at": _dt(2)},
    ]
    result = _run_fifo(txns)
    assert result["shares"] == Decimal("0")
    assert result["closed_at"] == _dt(2)


def test_fifo_oversell_raises():
    """SELL exceeding available shares raises ValueError."""
    txns = [
        {"type": "BUY", "shares": Decimal("5"), "price": Decimal("100"), "at": _dt(1)},
        {"type": "SELL", "shares": Decimal("10"), "price": Decimal("150"), "at": _dt(2)},
    ]
    with pytest.raises(ValueError, match="Insufficient shares"):
        _run_fifo(txns)


def test_fifo_multiple_tickers_isolated():
    """FIFO for one ticker does not affect another."""
    aapl_txns = [
        {"type": "BUY", "shares": Decimal("10"), "price": Decimal("100"), "at": _dt(1)},
        {"type": "SELL", "shares": Decimal("10"), "price": Decimal("150"), "at": _dt(2)},
    ]
    msft_txns = [
        {"type": "BUY", "shares": Decimal("5"), "price": Decimal("300"), "at": _dt(1)},
    ]
    aapl = _run_fifo(aapl_txns)
    msft = _run_fifo(msft_txns)
    assert aapl["shares"] == Decimal("0")
    assert msft["shares"] == Decimal("5")


def test_fifo_out_of_order_entry_reorders():
    """BUY entered with a past date is sorted into correct FIFO order."""
    txns = [
        # SELL logged first in list but FIFO sorts by transacted_at
        {"type": "SELL", "shares": Decimal("5"), "price": Decimal("150"), "at": _dt(3)},
        # This BUY happened before the SELL — FIFO should consume it
        {"type": "BUY", "shares": Decimal("10"), "price": Decimal("100"), "at": _dt(1)},
    ]
    result = _run_fifo(txns)
    assert result["shares"] == Decimal("5")


def test_fifo_delete_simulation_raises_on_invalid():
    """Simulating removal of a BUY that underlies a SELL should raise ValueError."""
    all_txns = [
        {"type": "BUY", "shares": Decimal("10"), "price": Decimal("100"), "at": _dt(1)},
        {"type": "SELL", "shares": Decimal("10"), "price": Decimal("150"), "at": _dt(2)},
    ]
    # Simulate removing the BUY
    remaining = [t for t in all_txns if not (t["type"] == "BUY" and t["at"] == _dt(1))]
    with pytest.raises(ValueError, match="Insufficient shares"):
        _run_fifo(remaining)


def test_fifo_null_sector_grouped_as_unknown():
    """Null sector on a stock is bucketed as 'Unknown' (tested via summary helper)."""
    from backend.tools.portfolio import _group_sectors

    positions = [
        {"ticker": "AAPL", "sector": None, "market_value": 1000.0},
        {"ticker": "MSFT", "sector": "Technology", "market_value": 2000.0},
    ]
    result = _group_sectors(positions, total_value=3000.0)
    sectors = {s["sector"]: s for s in result}
    assert "Unknown" in sectors
    assert sectors["Unknown"]["pct"] == pytest.approx(33.33, abs=0.01)
    assert "Technology" in sectors
    assert sectors["Technology"]["over_limit"] is True  # 66.7% > 30% threshold
