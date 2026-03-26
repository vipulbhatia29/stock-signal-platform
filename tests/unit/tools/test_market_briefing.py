"""Tests for market briefing tool."""

from unittest.mock import patch

import pandas as pd
import pytest


class TestFetchIndexPerformance:
    """Tests for index data fetching."""

    def test_returns_index_data(self) -> None:
        """Should return formatted index performance."""
        from backend.tools.market_briefing import _fetch_index_performance

        mock_data = pd.DataFrame(
            {"Close": [5000.0, 5050.0]},
            index=pd.date_range("2026-03-24", periods=2),
        )
        with patch("backend.tools.market_briefing.yf.download", return_value=mock_data):
            result = _fetch_index_performance("^GSPC", "S&P 500")
        assert result is not None
        assert result["name"] == "S&P 500"
        assert result["change_pct"] == pytest.approx(1.0, abs=0.1)

    def test_empty_data_returns_none(self) -> None:
        """Empty yfinance data should return None."""
        from backend.tools.market_briefing import _fetch_index_performance

        with patch("backend.tools.market_briefing.yf.download", return_value=pd.DataFrame()):
            result = _fetch_index_performance("^GSPC", "S&P 500")
        assert result is None

    def test_single_day_returns_none(self) -> None:
        """Only 1 day of data should return None (can't compute change)."""
        from backend.tools.market_briefing import _fetch_index_performance

        mock_data = pd.DataFrame(
            {"Close": [5000.0]},
            index=pd.date_range("2026-03-25", periods=1),
        )
        with patch("backend.tools.market_briefing.yf.download", return_value=mock_data):
            result = _fetch_index_performance("^GSPC", "S&P 500")
        assert result is None

    def test_exception_returns_none(self) -> None:
        """yfinance exception should return None."""
        from backend.tools.market_briefing import _fetch_index_performance

        with patch(
            "backend.tools.market_briefing.yf.download",
            side_effect=Exception("API down"),
        ):
            result = _fetch_index_performance("^GSPC", "S&P 500")
        assert result is None
