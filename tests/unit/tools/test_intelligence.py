"""Tests for stock intelligence fetch functions."""

from unittest.mock import MagicMock, patch

import pandas as pd


class TestFetchUpgradesDowngrades:
    """Tests for analyst rating changes."""

    def test_returns_recent_grades(self) -> None:
        """Should return recent upgrade/downgrade entries."""
        from backend.tools.intelligence import fetch_upgrades_downgrades

        mock_ticker = MagicMock()
        mock_ticker.upgrades_downgrades = pd.DataFrame(
            {
                "Firm": ["UBS", "Goldman"],
                "ToGrade": ["Buy", "Neutral"],
                "FromGrade": ["Neutral", "Buy"],
                "Action": ["up", "down"],
            },
            index=pd.to_datetime(["2026-03-20", "2026-03-15"]),
        )

        with patch("backend.tools.intelligence.yf.Ticker", return_value=mock_ticker):
            result = fetch_upgrades_downgrades("AAPL")
        assert len(result) == 2
        assert result[0]["firm"] == "UBS"
        assert result[0]["action"] == "up"

    def test_no_data_returns_empty(self) -> None:
        """No upgrades data should return empty list."""
        from backend.tools.intelligence import fetch_upgrades_downgrades

        mock_ticker = MagicMock()
        mock_ticker.upgrades_downgrades = None
        with patch("backend.tools.intelligence.yf.Ticker", return_value=mock_ticker):
            result = fetch_upgrades_downgrades("AAPL")
        assert result == []


class TestFetchInsiderTransactions:
    """Tests for insider transaction data."""

    def test_returns_transactions(self) -> None:
        """Should return formatted insider transactions."""
        from backend.tools.intelligence import fetch_insider_transactions

        mock_ticker = MagicMock()
        mock_ticker.insider_transactions = pd.DataFrame(
            {
                "Insider Trading": ["Tim Cook", "Jeff Williams"],
                "Relationship": ["CEO", "COO"],
                "Transaction": ["Sale", "Purchase"],
                "Shares": [50000, 10000],
                "Value": [8500000, 1700000],
                "Start Date": ["2026-03-01", "2026-02-15"],
            }
        )
        with patch("backend.tools.intelligence.yf.Ticker", return_value=mock_ticker):
            result = fetch_insider_transactions("AAPL")
        assert len(result) == 2
        assert result[0]["insider_name"] == "Tim Cook"


class TestFetchNextEarningsDate:
    """Tests for earnings calendar."""

    def test_returns_date_string(self) -> None:
        """Should return ISO date string for next earnings."""
        from backend.tools.intelligence import fetch_next_earnings_date

        mock_ticker = MagicMock()
        mock_ticker.calendar = {"Earnings Date": [pd.Timestamp("2026-04-28")]}
        with patch("backend.tools.intelligence.yf.Ticker", return_value=mock_ticker):
            result = fetch_next_earnings_date("AAPL")
        assert result is not None
        assert "2026-04-28" in result

    def test_no_calendar_returns_none(self) -> None:
        """No calendar data should return None."""
        from backend.tools.intelligence import fetch_next_earnings_date

        mock_ticker = MagicMock()
        mock_ticker.calendar = None
        with patch("backend.tools.intelligence.yf.Ticker", return_value=mock_ticker):
            result = fetch_next_earnings_date("AAPL")
        assert result is None


class TestFetchShortInterest:
    """Tests for short interest data."""

    def test_returns_short_data(self) -> None:
        """Should return short interest metrics when available."""
        from backend.tools.intelligence import fetch_short_interest

        mock_ticker = MagicMock()
        mock_ticker.info = {
            "shortPercentOfFloat": 0.0423,
            "shortRatio": 2.5,
            "sharesShort": 15_000_000,
        }
        with patch("backend.tools.intelligence.yf.Ticker", return_value=mock_ticker):
            result = fetch_short_interest("AAPL")
        assert result is not None
        assert result["short_percent_of_float"] == 4.23
        assert result["short_ratio"] == 2.5
        assert result["shares_short"] == 15_000_000

    def test_no_short_data_returns_none(self) -> None:
        """No short interest should return None."""
        from backend.tools.intelligence import fetch_short_interest

        mock_ticker = MagicMock()
        mock_ticker.info = {}
        with patch("backend.tools.intelligence.yf.Ticker", return_value=mock_ticker):
            result = fetch_short_interest("AAPL")
        assert result is None

    def test_exception_returns_none(self) -> None:
        """Should handle yfinance errors gracefully."""
        from backend.tools.intelligence import fetch_short_interest

        with patch("backend.tools.intelligence.yf.Ticker", side_effect=Exception("API error")):
            result = fetch_short_interest("AAPL")
        assert result is None
