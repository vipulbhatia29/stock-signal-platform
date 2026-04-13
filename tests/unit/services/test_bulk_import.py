"""Unit tests for backend.services.portfolio.bulk_import — CSV parsing and ingest."""

from __future__ import annotations

from decimal import Decimal
from textwrap import dedent
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.schemas.portfolio import BulkTransactionRow
from backend.services.portfolio.bulk_import import (
    MAX_ROWS,
    ingest_new_tickers,
    parse_csv,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_CSV = dedent("""\
    ticker,transaction_type,shares,price_per_share,transacted_at,notes
    AAPL,BUY,10,150.50,2024-01-15T10:00:00,Initial position
    MSFT,SELL,5,380.00,2024-02-01T14:30:00,
""")


# ---------------------------------------------------------------------------
# parse_csv
# ---------------------------------------------------------------------------


def test_parse_csv_valid_rows() -> None:
    """Happy path: all rows parse into valid BulkTransactionRow objects."""
    rows, errors = parse_csv(VALID_CSV)

    assert len(rows) == 2
    assert len(errors) == 0

    assert rows[0].ticker == "AAPL"
    assert rows[0].transaction_type == "BUY"
    assert rows[0].shares == Decimal("10")
    assert rows[0].price_per_share == Decimal("150.50")
    assert rows[0].notes == "Initial position"

    assert rows[1].ticker == "MSFT"
    assert rows[1].transaction_type == "SELL"
    assert rows[1].notes is None


def test_parse_csv_missing_columns() -> None:
    """CSV missing required columns returns a single row-0 error listing missing fields."""
    csv_content = "ticker,shares\nAAPL,10\n"
    rows, errors = parse_csv(csv_content)

    assert rows == []
    assert len(errors) == 1
    assert errors[0].row == 0
    assert "transaction_type" in errors[0].error
    assert "price_per_share" in errors[0].error


def test_parse_csv_invalid_ticker() -> None:
    """Rows with invalid ticker formats are skipped with a per-row error."""
    csv_content = dedent("""\
        ticker,transaction_type,shares,price_per_share,transacted_at,notes
        123BAD,BUY,10,100.00,2024-01-01T00:00:00,
    """)
    rows, errors = parse_csv(csv_content)

    assert rows == []
    assert len(errors) == 1
    assert errors[0].row == 2
    assert "ticker" in errors[0].error.lower()


def test_parse_csv_invalid_transaction_type() -> None:
    """Rows with transaction_type not BUY or SELL are skipped with an error."""
    csv_content = dedent("""\
        ticker,transaction_type,shares,price_per_share,transacted_at,notes
        AAPL,HOLD,10,100.00,2024-01-01T00:00:00,
    """)
    rows, errors = parse_csv(csv_content)

    assert rows == []
    assert len(errors) == 1
    assert errors[0].row == 2
    assert "BUY or SELL" in errors[0].error


def test_parse_csv_invalid_shares() -> None:
    """Rows with zero, negative, or non-numeric shares produce a per-row error."""
    csv_content = dedent("""\
        ticker,transaction_type,shares,price_per_share,transacted_at,notes
        AAPL,BUY,0,100.00,2024-01-01T00:00:00,
        MSFT,BUY,-5,100.00,2024-01-01T00:00:00,
        GOOG,BUY,abc,100.00,2024-01-01T00:00:00,
    """)
    rows, errors = parse_csv(csv_content)

    assert rows == []
    assert len(errors) == 3
    assert all("shares" in e.error for e in errors)


def test_parse_csv_invalid_price() -> None:
    """Rows with zero, negative, or non-numeric price_per_share produce a per-row error."""
    csv_content = dedent("""\
        ticker,transaction_type,shares,price_per_share,transacted_at,notes
        AAPL,BUY,10,0,2024-01-01T00:00:00,
        MSFT,BUY,10,-1.00,2024-01-01T00:00:00,
        GOOG,BUY,10,notanumber,2024-01-01T00:00:00,
    """)
    rows, errors = parse_csv(csv_content)

    assert rows == []
    assert len(errors) == 3
    assert all("price_per_share" in e.error for e in errors)


def test_parse_csv_invalid_date() -> None:
    """Rows with a non-ISO-8601 transacted_at are skipped with an error."""
    csv_content = dedent("""\
        ticker,transaction_type,shares,price_per_share,transacted_at,notes
        AAPL,BUY,10,100.00,not-a-date,
    """)
    rows, errors = parse_csv(csv_content)

    assert rows == []
    assert len(errors) == 1
    assert errors[0].row == 2
    assert "ISO 8601" in errors[0].error


def test_parse_csv_max_rows_exceeded() -> None:
    """CSVs with more than MAX_ROWS data rows produce a truncation error."""
    header = "ticker,transaction_type,shares,price_per_share,transacted_at,notes\n"
    data_row = "AAPL,BUY,1,100.00,2024-01-01T00:00:00,\n"
    csv_content = header + data_row * (MAX_ROWS + 1)

    rows, errors = parse_csv(csv_content)

    # Exactly MAX_ROWS valid rows
    assert len(rows) == MAX_ROWS
    # One error for the exceeding row
    assert any("Exceeds maximum" in e.error for e in errors)


def test_parse_csv_empty_file() -> None:
    """An empty CSV string produces a single row-0 error about missing header."""
    rows, errors = parse_csv("")

    assert rows == []
    assert len(errors) == 1
    assert errors[0].row == 0


# ---------------------------------------------------------------------------
# ingest_new_tickers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingest_new_tickers_skips_existing() -> None:
    """Tickers already in the DB are not passed to ingest_ticker."""
    rows = [
        BulkTransactionRow(
            ticker="AAPL",
            transaction_type="BUY",
            shares=Decimal("10"),
            price_per_share=Decimal("150"),
            transacted_at=__import__("datetime").datetime(2024, 1, 1),
        )
    ]

    # Mock DB session to return AAPL as existing
    mock_result = MagicMock()
    mock_result.all.return_value = [("AAPL",)]
    mock_db = AsyncMock()
    mock_db.execute.return_value = mock_result

    with patch("backend.services.pipelines.ingest_ticker") as mock_ingest:
        errors = await ingest_new_tickers(rows, mock_db, "user-123")

    assert errors == []
    mock_ingest.assert_not_called()
