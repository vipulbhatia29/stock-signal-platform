"""Tests for the S&P 500 sync script."""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd

from scripts.sync_sp500 import fetch_sp500_tickers

# ---------------------------------------------------------------------------
# fetch_sp500_tickers — scrapes Wikipedia S&P 500 table
# ---------------------------------------------------------------------------

MOCK_HTML_TABLE = pd.DataFrame(
    {
        "Symbol": ["AAPL", "MSFT", "BRK.B", " GOOGL "],
        "Security": ["Apple Inc.", "Microsoft Corp", "Berkshire Hathaway", " Alphabet Inc. "],
        "GICS Sector": [
            "Information Technology",
            "Information Technology",
            "Financials",
            " Communication Services ",
        ],
        "GICS Sub-Industry": [
            "Technology Hardware",
            "Systems Software",
            "Multi-Sector Holdings",
            " Interactive Media ",
        ],
    }
)


@patch("scripts.sync_sp500.pd.read_html", return_value=[MOCK_HTML_TABLE])
def test_fetch_sp500_tickers_returns_dataframe(mock_read_html):
    """fetch_sp500_tickers should return a DataFrame with standardized columns."""
    df = fetch_sp500_tickers()

    assert isinstance(df, pd.DataFrame)
    assert set(df.columns) == {"ticker", "name", "sector", "industry", "exchange"}
    assert len(df) == 4


@patch("scripts.sync_sp500.pd.read_html", return_value=[MOCK_HTML_TABLE])
def test_fetch_sp500_tickers_strips_whitespace(mock_read_html):
    """Ticker names and sectors should be stripped of leading/trailing whitespace."""
    df = fetch_sp500_tickers()

    assert df.iloc[3]["ticker"] == "GOOGL"
    assert df.iloc[3]["name"] == "Alphabet Inc."
    assert df.iloc[3]["sector"] == "Communication Services"
    assert df.iloc[3]["industry"] == "Interactive Media"


@patch("scripts.sync_sp500.pd.read_html", return_value=[MOCK_HTML_TABLE])
def test_fetch_sp500_tickers_replaces_dots_with_dashes(mock_read_html):
    """Tickers like BRK.B should become BRK-B (yfinance format)."""
    df = fetch_sp500_tickers()

    assert "BRK-B" in df["ticker"].values
    assert "BRK.B" not in df["ticker"].values


@patch("scripts.sync_sp500.pd.read_html", return_value=[MOCK_HTML_TABLE])
def test_fetch_sp500_tickers_exchange_is_none(mock_read_html):
    """Exchange column should be None (Wikipedia doesn't provide it)."""
    df = fetch_sp500_tickers()

    assert df["exchange"].isna().all()


@patch("scripts.sync_sp500.pd.read_html", return_value=[MOCK_HTML_TABLE])
def test_fetch_sp500_tickers_all_tickers_present(mock_read_html):
    """All tickers from the mock data should appear in the result."""
    df = fetch_sp500_tickers()
    tickers = set(df["ticker"].values)

    assert tickers == {"AAPL", "MSFT", "BRK-B", "GOOGL"}
