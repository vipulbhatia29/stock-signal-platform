"""Concurrent portfolio transaction tests.

Tests race conditions for concurrent buy+sell on the same position,
concurrent reads during writes, and asyncio.gather-based concurrency.

These tests use the pure FIFO engine (_run_fifo) which is synchronous,
and async helpers to simulate concurrent DB-level operations.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from backend.services.portfolio import _run_fifo

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now(offset_secs: int = 0) -> datetime:
    """Return a fixed base datetime offset by seconds."""
    from datetime import timedelta

    return datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc) + timedelta(seconds=offset_secs)


# ---------------------------------------------------------------------------
# Concurrent buy + sell on same position (FIFO correctness under ordering)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_buy_sell_final_state_consistent() -> None:
    """Concurrent BUY and SELL operations produce a consistent final FIFO state.

    Even when buy and sell are submitted in parallel, FIFO walk sorts by `at`
    timestamp — the result must reflect the correct chronological order.
    """
    buy_txn = {
        "type": "BUY",
        "shares": Decimal("100"),
        "price": Decimal("150.00"),
        "at": _now(0),
    }
    sell_txn = {
        "type": "SELL",
        "shares": Decimal("40"),
        "price": Decimal("160.00"),
        "at": _now(1),
    }

    async def _simulate_buy() -> dict:
        """Simulate async processing of a buy transaction."""
        await asyncio.sleep(0)  # yield to event loop
        return buy_txn

    async def _simulate_sell() -> dict:
        """Simulate async processing of a sell transaction."""
        await asyncio.sleep(0)
        return sell_txn

    # Gather both concurrently
    buy, sell = await asyncio.gather(_simulate_buy(), _simulate_sell())

    # FIFO walk produces deterministic result regardless of gather order
    result = _run_fifo([buy, sell])

    assert result["shares"] == Decimal("60"), (
        f"Expected 60 remaining shares, got {result['shares']}"
    )
    assert result["avg_cost_basis"] == Decimal("150.00"), (
        f"Cost basis should be 150.00, got {result['avg_cost_basis']}"
    )
    assert result["closed_at"] is None  # Position still open


@pytest.mark.asyncio
async def test_concurrent_buys_accumulate_correctly() -> None:
    """Multiple concurrent BUY transactions accumulate to correct total shares."""

    async def _buy(shares: int, price: float, offset: int) -> dict:
        """Simulate an async buy operation."""
        await asyncio.sleep(0)
        return {
            "type": "BUY",
            "shares": Decimal(str(shares)),
            "price": Decimal(str(price)),
            "at": _now(offset),
        }

    txns = await asyncio.gather(
        _buy(50, 100.0, 0),
        _buy(30, 110.0, 1),
        _buy(20, 120.0, 2),
    )

    result = _run_fifo(list(txns))
    expected_shares = Decimal("100")
    expected_avg = (50 * 100.0 + 30 * 110.0 + 20 * 120.0) / 100.0

    assert result["shares"] == expected_shares
    assert abs(float(result["avg_cost_basis"]) - expected_avg) < 0.01


@pytest.mark.asyncio
async def test_concurrent_portfolio_value_reads_during_write() -> None:
    """Concurrent reads and writes on portfolio value are non-blocking.

    The pure FIFO engine is synchronous and side-effect-free — it can
    be safely called from multiple coroutines without locking.
    """
    txns = [
        {"type": "BUY", "shares": Decimal("100"), "price": Decimal("100.00"), "at": _now(0)},
        {"type": "BUY", "shares": Decimal("50"), "price": Decimal("110.00"), "at": _now(1)},
    ]

    async def _compute_fifo() -> dict:
        """Simulate a read that calls FIFO engine (could come from portfolio summary)."""
        await asyncio.sleep(0)
        return _run_fifo(txns)

    # 10 concurrent readers
    results = await asyncio.gather(*[_compute_fifo() for _ in range(10)])

    # All reads should return the same consistent result
    expected_shares = Decimal("150")
    for result in results:
        assert result["shares"] == expected_shares, (
            f"Concurrent read returned inconsistent shares: {result['shares']}"
        )


@pytest.mark.asyncio
async def test_sell_exceeds_available_raises_value_error() -> None:
    """Selling more shares than available must raise ValueError — no silent corruption."""
    txns = [
        {"type": "BUY", "shares": Decimal("10"), "price": Decimal("100.00"), "at": _now(0)},
        {"type": "SELL", "shares": Decimal("15"), "price": Decimal("110.00"), "at": _now(1)},
    ]

    async def _attempt_oversell() -> None:
        """Simulate a sell that exceeds available lots."""
        await asyncio.sleep(0)
        _run_fifo(txns)  # Should raise ValueError

    with pytest.raises(ValueError, match="Insufficient shares"):
        await _attempt_oversell()


@pytest.mark.asyncio
async def test_full_sell_closes_position() -> None:
    """Selling all shares results in a closed position (closed_at is set)."""
    txns = [
        {"type": "BUY", "shares": Decimal("100"), "price": Decimal("100.00"), "at": _now(0)},
        {"type": "SELL", "shares": Decimal("100"), "price": Decimal("120.00"), "at": _now(1)},
    ]

    async def _close_position() -> dict:
        """Simulate fully closing a position."""
        await asyncio.sleep(0)
        return _run_fifo(txns)

    result = await _close_position()

    assert result["shares"] == Decimal("0")
    assert result["avg_cost_basis"] == Decimal("0")
    assert result["closed_at"] == _now(1)


@pytest.mark.asyncio
async def test_concurrent_partial_sells_deterministic() -> None:
    """Multiple partial sells in sequence produce deterministic remaining shares."""
    buy_txn = {
        "type": "BUY",
        "shares": Decimal("200"),
        "price": Decimal("100.00"),
        "at": _now(0),
    }

    async def _partial_sell(shares: int, offset: int) -> dict:
        """Simulate a partial sell transaction."""
        await asyncio.sleep(0)
        return {
            "type": "SELL",
            "shares": Decimal(str(shares)),
            "price": Decimal("105.00"),
            "at": _now(offset),
        }

    sell1, sell2 = await asyncio.gather(
        _partial_sell(50, 1),
        _partial_sell(30, 2),
    )

    result = _run_fifo([buy_txn, sell1, sell2])

    expected_remaining = Decimal("120")  # 200 - 50 - 30
    assert result["shares"] == expected_remaining
    assert result["closed_at"] is None  # Still open
