"""Tests for snapshot import service."""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.schemas.attribution import SnapshotRowSchema
from backend.services.portfolio.snapshot_import import (
    _classify_action,
    _compute_diffs,
    compute_csv_hash,
    import_portfolio_snapshot,
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


class TestComputeCsvHash:
    """Unit tests for CSV hash computation."""

    def test_deterministic_hash(self) -> None:
        """Same content produces same hash."""
        content = "Symbol,Qty\nAAPL,10"
        assert compute_csv_hash(content) == compute_csv_hash(content)

    def test_different_content_different_hash(self) -> None:
        """Different content produces different hashes."""
        assert compute_csv_hash("abc") != compute_csv_hash("def")


def _make_rows(*tickers: str) -> list[SnapshotRowSchema]:
    """Helper to create SnapshotRowSchema list for testing."""
    return [
        SnapshotRowSchema(
            ticker=t,
            description=f"{t} INC",
            shares=Decimal("10"),
            price=Decimal("100"),
            cost_basis=Decimal("1000"),
            market_value=Decimal("1000"),
            avg_cost_basis=Decimal("100"),
        )
        for t in tickers
    ]


def _mock_db_for_dedup(has_dup: bool = False) -> AsyncMock:
    """Create a mock DB session for dedup check.

    The service runs several queries sequentially. We mock execute()
    to return appropriate results for each call.
    """
    db = AsyncMock()

    # Track call count to return different results per query
    call_results = []

    if has_dup:
        # Query 1: dedup check — found existing
        dup_result = MagicMock()
        dup_result.scalar_one_or_none.return_value = "2026-05-01T00:00:00"
        call_results.append(dup_result)
    else:
        # Query 1: dedup check — not found
        no_dup_result = MagicMock()
        no_dup_result.scalar_one_or_none.return_value = None
        call_results.append(no_dup_result)

        # Query 2: previous snapshot imported_at — none (baseline)
        no_prev = MagicMock()
        no_prev.scalar_one_or_none.return_value = None
        call_results.append(no_prev)

        # Query 3: baseline check — no positions
        no_positions = MagicMock()
        no_positions.scalars.return_value.all.return_value = []
        call_results.append(no_positions)

        # Query 4: batch stock pre-check — all exist
        stock_result = MagicMock()
        stock_result.all.return_value = [("AAPL",)]
        call_results.append(stock_result)

        # Query 5+: remaining queries (position sync, watchlist, etc.)
        # Return empty results for all subsequent queries
        default = MagicMock()
        default.scalars.return_value.all.return_value = []
        default.all.return_value = []
        default.scalar_one_or_none.return_value = None
        for _ in range(10):
            call_results.append(default)

    db.execute = AsyncMock(side_effect=call_results)
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.mark.anyio
class TestImportPortfolioSnapshot:
    """Async tests for the import_portfolio_snapshot service function."""

    async def test_dedup_returns_is_duplicate(self) -> None:
        """Importing a CSV with a hash that already exists returns is_duplicate."""
        db = _mock_db_for_dedup(has_dup=True)
        rows = _make_rows("AAPL")

        result = await import_portfolio_snapshot(
            portfolio_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            rows=rows,
            csv_hash="abc123",
            db=db,
        )

        assert result.is_duplicate is True
        assert result.imported == 0
        # Should NOT have called commit (early return)
        db.commit.assert_not_called()

    async def test_baseline_first_import(self) -> None:
        """First import with no prior snapshots sets is_baseline=True."""
        db = _mock_db_for_dedup(has_dup=False)
        rows = _make_rows("AAPL")

        result = await import_portfolio_snapshot(
            portfolio_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            rows=rows,
            csv_hash="first_import",
            db=db,
        )

        assert result.is_baseline is True
        assert result.imported == 1
        assert result.changes_detected == 0
        db.commit.assert_called_once()

    async def test_failed_ticker_skipped_with_warning(self) -> None:
        """Unknown tickers produce warnings and are excluded from import."""
        db = AsyncMock()

        call_results = []
        # Query 1: dedup — not found
        r1 = MagicMock()
        r1.scalar_one_or_none.return_value = None
        call_results.append(r1)
        # Query 2: prev snapshot — none
        r2 = MagicMock()
        r2.scalar_one_or_none.return_value = None
        call_results.append(r2)
        # Query 3: baseline positions — none
        r3 = MagicMock()
        r3.scalars.return_value.all.return_value = []
        call_results.append(r3)
        # Query 4: batch stock check — AAPL exists, FXAIX does not
        r4 = MagicMock()
        r4.all.return_value = [("AAPL",)]
        call_results.append(r4)
        # Remaining queries
        default = MagicMock()
        default.scalars.return_value.all.return_value = []
        default.all.return_value = []
        default.scalar_one_or_none.return_value = None
        for _ in range(10):
            call_results.append(default)

        db.execute = AsyncMock(side_effect=call_results)
        db.flush = AsyncMock()
        db.commit = AsyncMock()
        db.add = MagicMock()

        rows = _make_rows("AAPL", "FXAIX")

        with patch(
            "backend.services.portfolio.snapshot_import.ensure_stock_exists",
            side_effect=ValueError("not found"),
        ):
            result = await import_portfolio_snapshot(
                portfolio_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
                rows=rows,
                csv_hash="with_bad_ticker",
                db=db,
            )

        # FXAIX should be skipped
        assert result.imported == 1  # only AAPL
        assert len(result.warnings) == 1
        assert "FXAIX" in result.warnings[0].message

    async def test_csv_hash_is_deterministic(self) -> None:
        """compute_csv_hash returns consistent SHA-256."""
        h1 = compute_csv_hash("test content")
        h2 = compute_csv_hash("test content")
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex digest length
