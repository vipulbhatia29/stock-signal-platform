"""Tests for Fidelity CSV parser."""

from __future__ import annotations

from decimal import Decimal

from backend.services.portfolio.csv_parser import parse_fidelity_csv

# --- Fixtures ---

# Shared header line used across many test CSVs
_HDR = (
    '"Symbol","Description","Qty (Quantity)","Price",'
    '"Cost Basis","Mkt Val (Market Value)","Asset Type"\n'
)

VALID_CSV = (
    '"Positions for account Designated Bene Individual'
    ' as of 02:41 AM ET, 2026/04/30"\n'
    "\n" + _HDR + '"AAPL","APPLE INC","27.4355","270.84","$2,989.79","$7,430.63","Equity"\n'
    '"MSFT","MICROSOFT CORP","10.0","420.50","$3,500.00","$4,205.00","Equity"\n'
)

DOLLAR_SIGNS_CSV = (
    _HDR + '"AAPL","APPLE INC","27.4355","$270.84","$2,989.79","$7,430.63","Equity"\n'
)

MISSING_QTY_COLUMN_CSV = (
    '"Symbol","Description","Price","Cost Basis"\n"AAPL","APPLE INC","270.84","$2,989.79"\n'
)

EMPTY_SYMBOL_CSV = _HDR + '"","APPLE INC","27.4355","270.84","$2,989.79","$7,430.63","Equity"\n'

BAD_QTY_CSV = _HDR + '"AAPL","APPLE INC","--","270.84","$2,989.79","$7,430.63","Equity"\n'

CASH_ROW_CSV = (
    _HDR + '"AAPL","APPLE INC","27.4355","270.84","$2,989.79","$7,430.63","Equity"\n'
    '"Cash & Cash Investments","","","","","$1,234.56","Cash and Money Market"\n'
    '"Positions Total","","","","","$8,665.19",""\n'
)

DUPLICATE_TICKER_CSV = (
    _HDR + '"AAPL","APPLE INC","27.4355","270.84","$2,989.79","$7,430.63","Equity"\n'
    '"AAPL","APPLE INC","10.0","270.84","$2,708.40","$2,708.40","Equity"\n'
)

LOWERCASE_TICKER_CSV = (
    _HDR + '"aapl","APPLE INC","27.4355","270.84","$2,989.79","$7,430.63","Equity"\n'
)

NO_HEADER_CSV = "just some random text\nwith no recognizable columns\n"

COST_BASIS_MISSING_CSV = _HDR + '"AAPL","APPLE INC","10.0","270.84","--","$2,708.40","Equity"\n'


# --- Tests ---


class TestParseFidelityCsv:
    """CSV parser tests."""

    def test_valid_csv_parses_correctly(self) -> None:
        """Two-row valid CSV returns two rows with correct field values."""
        rows, warnings, errors = parse_fidelity_csv(VALID_CSV)
        assert len(rows) == 2
        assert rows[0].ticker == "AAPL"
        assert rows[0].shares == Decimal("27.4355")
        assert rows[0].price == Decimal("270.84")
        assert rows[0].avg_cost_basis == Decimal("2989.79") / Decimal("27.4355")
        assert rows[1].ticker == "MSFT"
        assert len(errors) == 0

    def test_strips_dollar_signs_and_commas(self) -> None:
        """Dollar signs and commas in numeric fields are stripped correctly."""
        rows, warnings, errors = parse_fidelity_csv(DOLLAR_SIGNS_CSV)
        assert len(rows) == 1
        assert rows[0].cost_basis == Decimal("2989.79")

    def test_missing_required_column_returns_error(self) -> None:
        """Missing Qty column produces a fatal validation error."""
        rows, warnings, errors = parse_fidelity_csv(MISSING_QTY_COLUMN_CSV)
        assert len(rows) == 0
        assert len(errors) == 1
        assert "qty" in errors[0].message.lower()

    def test_empty_symbol_skipped(self) -> None:
        """Rows with blank symbol are silently skipped."""
        rows, warnings, errors = parse_fidelity_csv(EMPTY_SYMBOL_CSV)
        assert len(rows) == 0

    def test_bad_qty_skipped_with_warning(self) -> None:
        """Rows with unparseable Qty produce a warning and are excluded."""
        rows, warnings, errors = parse_fidelity_csv(BAD_QTY_CSV)
        assert len(rows) == 0
        assert any("not a valid number" in w.message for w in warnings)

    def test_cash_and_summary_rows_skipped(self) -> None:
        """Cash and Positions Total rows are excluded; equity rows are kept."""
        rows, warnings, errors = parse_fidelity_csv(CASH_ROW_CSV)
        assert len(rows) == 1
        assert rows[0].ticker == "AAPL"

    def test_duplicate_ticker_warns(self) -> None:
        """Second occurrence of a ticker emits a warning; first row is kept."""
        rows, warnings, errors = parse_fidelity_csv(DUPLICATE_TICKER_CSV)
        assert len(rows) == 1
        assert any("appears twice" in w.message for w in warnings)

    def test_lowercase_ticker_uppercased(self) -> None:
        """Lowercase tickers are normalized to uppercase."""
        rows, warnings, errors = parse_fidelity_csv(LOWERCASE_TICKER_CSV)
        assert len(rows) == 1
        assert rows[0].ticker == "AAPL"

    def test_no_header_returns_error(self) -> None:
        """CSV with no recognizable header row returns a fatal error."""
        rows, warnings, errors = parse_fidelity_csv(NO_HEADER_CSV)
        assert len(rows) == 0
        assert len(errors) == 1
        assert "header" in errors[0].message.lower()

    def test_cost_basis_missing_derived_from_price(self) -> None:
        """Missing cost basis is estimated from Price × Qty with a warning."""
        rows, warnings, errors = parse_fidelity_csv(COST_BASIS_MISSING_CSV)
        assert len(rows) == 1
        assert rows[0].cost_basis == Decimal("270.84") * Decimal("10.0")
        assert any("cost basis" in w.message.lower() for w in warnings)

    def test_empty_string_returns_error(self) -> None:
        """Empty string input returns at least one fatal error."""
        rows, warnings, errors = parse_fidelity_csv("")
        assert len(rows) == 0
        assert len(errors) >= 1

    def test_header_on_different_row(self) -> None:
        """Header not on row 1 — parser scans first 10 rows to find it."""
        csv_content = (
            "Account summary info\n"
            "More info\n"
            "Even more info\n"
            "And more\n"
            + _HDR
            + '"AAPL","APPLE INC","10.0","270.84","$2,708.40","$2,708.40","Equity"\n'
        )
        rows, warnings, errors = parse_fidelity_csv(csv_content)
        assert len(rows) == 1
        assert rows[0].ticker == "AAPL"

    def test_bom_stripped(self) -> None:
        """UTF-8 BOM at start of file is stripped before parsing."""
        csv_content = (
            "\ufeff"
            + _HDR
            + '"AAPL","APPLE INC","10.0","270.84","$2,708.40","$2,708.40","Equity"\n'
        )
        rows, warnings, errors = parse_fidelity_csv(csv_content)
        assert len(rows) == 1

    def test_percentage_signs_stripped(self) -> None:
        """Percentage signs in numeric fields are stripped correctly."""
        csv_content = (
            _HDR + '"AAPL","APPLE INC","10.0","270.84%","$2,708.40","$2,708.40","Equity"\n'
        )
        rows, warnings, errors = parse_fidelity_csv(csv_content)
        assert len(rows) == 1
        assert rows[0].price == Decimal("270.84")
