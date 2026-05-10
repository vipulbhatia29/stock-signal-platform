"""Tests for snapshot import service."""

from __future__ import annotations

from decimal import Decimal

from backend.services.portfolio.snapshot_import import (
    _classify_action,
    _compute_diffs,
)


class TestClassifyAction:
    """Unit tests for action classification logic."""

    def test_open_new_position(self) -> None:
        assert _classify_action(prev=Decimal("0"), new=Decimal("10")) == "OPEN"

    def test_add_to_position(self) -> None:
        assert _classify_action(prev=Decimal("10"), new=Decimal("20")) == "ADD"

    def test_trim_position(self) -> None:
        assert _classify_action(prev=Decimal("20"), new=Decimal("10")) == "TRIM"

    def test_close_position(self) -> None:
        assert _classify_action(prev=Decimal("10"), new=Decimal("0")) == "CLOSE"

    def test_no_change_returns_none(self) -> None:
        assert _classify_action(prev=Decimal("10"), new=Decimal("10")) is None


class TestComputeDiffs:
    """Unit tests for diff computation between two snapshot sets."""

    def test_new_ticker_is_open(self) -> None:
        prev: dict[str, tuple[Decimal, Decimal]] = {}
        curr = {"AAPL": (Decimal("10"), Decimal("150.00"))}
        diffs = _compute_diffs(prev, curr)
        assert len(diffs) == 1
        assert diffs[0]["ticker"] == "AAPL"
        assert diffs[0]["implied_action"] == "OPEN"
        assert diffs[0]["prev_shares"] == Decimal("0")

    def test_removed_ticker_is_close(self) -> None:
        prev = {"AAPL": (Decimal("10"), Decimal("150.00"))}
        curr: dict[str, tuple[Decimal, Decimal]] = {}
        diffs = _compute_diffs(prev, curr)
        assert len(diffs) == 1
        assert diffs[0]["implied_action"] == "CLOSE"
        assert diffs[0]["new_shares"] == Decimal("0")

    def test_increased_shares_is_add(self) -> None:
        prev = {"AAPL": (Decimal("10"), Decimal("150.00"))}
        curr = {"AAPL": (Decimal("20"), Decimal("155.00"))}
        diffs = _compute_diffs(prev, curr)
        assert len(diffs) == 1
        assert diffs[0]["implied_action"] == "ADD"
        assert diffs[0]["delta_shares"] == Decimal("10")

    def test_decreased_shares_is_trim(self) -> None:
        prev = {"AAPL": (Decimal("20"), Decimal("150.00"))}
        curr = {"AAPL": (Decimal("10"), Decimal("150.00"))}
        diffs = _compute_diffs(prev, curr)
        assert len(diffs) == 1
        assert diffs[0]["implied_action"] == "TRIM"

    def test_unchanged_shares_no_diff(self) -> None:
        prev = {"AAPL": (Decimal("10"), Decimal("150.00"))}
        curr = {"AAPL": (Decimal("10"), Decimal("150.00"))}
        diffs = _compute_diffs(prev, curr)
        assert len(diffs) == 0

    def test_multiple_changes(self) -> None:
        prev = {
            "AAPL": (Decimal("10"), Decimal("150.00")),
            "MSFT": (Decimal("5"), Decimal("400.00")),
        }
        curr = {
            "AAPL": (Decimal("20"), Decimal("155.00")),
            "NVDA": (Decimal("3"), Decimal("900.00")),
        }
        diffs = _compute_diffs(prev, curr)
        tickers = {d["ticker"] for d in diffs}
        assert tickers == {"AAPL", "MSFT", "NVDA"}
        actions = {d["ticker"]: d["implied_action"] for d in diffs}
        assert actions["AAPL"] == "ADD"
        assert actions["MSFT"] == "CLOSE"
        assert actions["NVDA"] == "OPEN"
