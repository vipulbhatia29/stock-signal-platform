"""Unit tests for seed_portfolio — CSV parsing and position import logic."""

from __future__ import annotations

from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_HEADER = (
    '"Symbol","Description","Qty (Quantity)",'
    '"Theme Qty (Theme Quantity)","Non-Theme Qty (Non-Theme Quantity)",'
    '"Price","Price Chng $ (Price Change $)",'
    '"Price Chng % (Price Change %)","Mkt Val (Market Value)",'
    '"Day Chng $ (Day Change $)","Day Chng % (Day Change %)",'
    '"Cost Basis","Gain % (Gain/Loss %)","Gain $ (Gain/Loss $)",'
    '"Ratings","Reinvest?","Reinvest Capital Gains?",'
    '"% of Acct (% of Account)","Asset Type",'
)

_ROWS = [
    # Equity
    (
        '"AAPL","APPLE INC","27.4355","--","27.4355","270.84",'
        '"0.67","0.25%","$7,430.63","$18.38","0.25%","$2,989.79",'
        '"148.53%","$4,440.84","A","Yes","N/A","8.77%","Equity",'
    ),
    # ETF — VOO has "Incomplete" cost basis
    (
        '"VOO","VANGUARD S&P 500 ETF","37.2628","--","--","656.17",'
        '"1.93","0.29%","$24,450.73","$71.92","0.3%","Incomplete",'
        '"N/A","N/A","--","Yes","N/A","28.85%","ETFs & Closed End Funds",'
    ),
    # ETF — QQQ
    (
        '"QQQ","INVESCO QQQ TR","4.1364","--","--","666.79",'
        '"5.22","0.79%","$2,758.11","$21.59","0.79%","$1,048.62",'
        '"163.02%","$1,709.49","--","Yes","N/A","3.25%",'
        '"ETFs & Closed End Funds",'
    ),
    # Cash — should be skipped
    (
        '"Cash & Cash Investments","--","--","--","--","--",'
        '"--","--","$578.57","$0.00","0%","--","--","--","--",'
        '"--","--","0.68%","Cash and Money Market",'
    ),
]


def _build_sample_csv() -> str:
    """Build a Fidelity-format CSV string for testing."""
    account_line = (
        '"Positions for account Designated Bene Individual ...063 as of 02:41 AM ET, 2026/04/30"'
    )
    lines = [account_line, "", _HEADER] + _ROWS + [""]
    return "\n".join(lines)


@pytest.fixture
def csv_file(tmp_path: Path) -> str:
    """Create a temporary CSV file with mixed asset types."""
    p = tmp_path / "positions.csv"
    p.write_text(_build_sample_csv(), encoding="utf-8")
    return str(p)


# ---------------------------------------------------------------------------
# Tests: parse_fidelity_csv
# ---------------------------------------------------------------------------


class TestParseFidelityCsv:
    """Tests for the CSV parser accepting equities and ETFs."""

    def test_includes_equities(self, csv_file: str) -> None:
        """Equity rows like AAPL are included in parsed output."""
        from scripts.seed_portfolio import parse_fidelity_csv

        positions = parse_fidelity_csv(csv_file)
        tickers = [p["ticker"] for p in positions]
        assert "AAPL" in tickers

    def test_includes_etfs(self, csv_file: str) -> None:
        """ETF rows like VOO and QQQ are included in parsed output."""
        from scripts.seed_portfolio import parse_fidelity_csv

        positions = parse_fidelity_csv(csv_file)
        tickers = [p["ticker"] for p in positions]
        assert "VOO" in tickers
        assert "QQQ" in tickers

    def test_excludes_cash_rows(self, csv_file: str) -> None:
        """Cash and Money Market rows are excluded."""
        from scripts.seed_portfolio import parse_fidelity_csv

        positions = parse_fidelity_csv(csv_file)
        tickers = [p["ticker"] for p in positions]
        assert "Cash & Cash Investments" not in tickers

    def test_total_count_is_correct(self, csv_file: str) -> None:
        """All non-cash positions (equities + ETFs) are parsed."""
        from scripts.seed_portfolio import parse_fidelity_csv

        positions = parse_fidelity_csv(csv_file)
        # AAPL + VOO + QQQ = 3 positions (cash excluded)
        assert len(positions) == 3

    def test_etf_with_incomplete_cost_basis_uses_price(self, csv_file: str) -> None:
        """VOO has 'Incomplete' cost basis — should use price * shares as fallback."""
        from scripts.seed_portfolio import parse_fidelity_csv

        positions = parse_fidelity_csv(csv_file)
        voo = next(p for p in positions if p["ticker"] == "VOO")
        # price=656.17, shares=37.2628 → avg_cost_basis = 656.17
        assert abs(float(voo["avg_cost_basis"]) - 656.17) < 0.01

    def test_position_fields_populated(self, csv_file: str) -> None:
        """Each parsed position has all required fields."""
        from scripts.seed_portfolio import parse_fidelity_csv

        positions = parse_fidelity_csv(csv_file)
        for pos in positions:
            assert "ticker" in pos
            assert "description" in pos
            assert "shares" in pos
            assert "avg_cost_basis" in pos
            assert "price" in pos
            assert pos["shares"] > 0
            assert pos["avg_cost_basis"] > 0
