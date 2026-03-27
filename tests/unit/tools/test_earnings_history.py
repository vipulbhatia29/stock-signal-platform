"""Tests for EarningsHistoryTool and earnings ingestion helpers."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _mock_session_with_snapshots(snapshots):
    """Create a mock async session context manager returning earnings snapshots."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = snapshots
    mock_result.scalars.return_value = mock_scalars
    mock_session.execute.return_value = mock_result
    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_session
    mock_cm.__aexit__.return_value = None
    return mock_cm


class FakeEarningsSnapshot:
    """Minimal EarningsSnapshot stand-in."""

    def __init__(
        self,
        quarter: str,
        eps_estimate: float | None,
        eps_actual: float | None,
        surprise_pct: float | None,
    ):
        """Initialize snapshot."""
        self.quarter = quarter
        self.eps_estimate = eps_estimate
        self.eps_actual = eps_actual
        self.surprise_pct = surprise_pct


class TestEarningsHistoryTool:
    """Tests for EarningsHistoryTool.execute."""

    @pytest.mark.asyncio
    async def test_returns_earnings_with_beat_summary(self) -> None:
        """Should return earnings list and beat count summary."""
        snapshots = [
            FakeEarningsSnapshot("2025-12-31", 0.10, 0.13, 30.0),
            FakeEarningsSnapshot("2025-09-30", 0.09, 0.10, 11.0),
            FakeEarningsSnapshot("2025-06-30", 0.08, 0.07, -12.5),
            FakeEarningsSnapshot("2025-03-31", 0.07, 0.09, 28.0),
        ]
        mock_cm = _mock_session_with_snapshots(snapshots)

        with patch("backend.database.async_session_factory", return_value=mock_cm):
            from backend.tools.earnings_history_tool import EarningsHistoryTool

            tool = EarningsHistoryTool()
            result = await tool.execute({"ticker": "PLTR"})

            assert result.status == "ok"
            assert result.data["has_earnings"] is True
            assert len(result.data["quarters"]) == 4
            assert result.data["beat_count"] == 3
            assert result.data["total_quarters"] == 4
            assert "Beat 3 of last 4" in result.data["summary"]

    @pytest.mark.asyncio
    async def test_no_earnings_data(self) -> None:
        """Should return has_earnings=False when no data exists."""
        mock_cm = _mock_session_with_snapshots([])

        with patch("backend.database.async_session_factory", return_value=mock_cm):
            from backend.tools.earnings_history_tool import EarningsHistoryTool

            tool = EarningsHistoryTool()
            result = await tool.execute({"ticker": "NEW"})

            assert result.status == "ok"
            assert result.data["has_earnings"] is False

    @pytest.mark.asyncio
    async def test_empty_ticker_returns_error(self) -> None:
        """Should return error for empty ticker."""
        from backend.tools.earnings_history_tool import EarningsHistoryTool

        tool = EarningsHistoryTool()
        result = await tool.execute({"ticker": ""})
        assert result.status == "error"


class TestFetchEarningsHistory:
    """Tests for fetch_earnings_history helper."""

    def test_returns_earnings_list(self) -> None:
        """Should parse yfinance earnings_history DataFrame."""
        import pandas as pd

        # yfinance returns quarter as the DataFrame index (Timestamps), not a column
        mock_df = pd.DataFrame(
            {
                "epsEstimate": [0.10, 0.09],
                "epsActual": [0.13, 0.10],
                "surprisePercent": [30.0, 11.0],
            },
            index=pd.to_datetime(["2025-12-31", "2025-09-30"]),
        )
        mock_df.index.name = "quarter"

        with patch("backend.services.stock_data.yf.Ticker") as mock_ticker:
            mock_ticker.return_value.earnings_history = mock_df

            from backend.tools.fundamentals import fetch_earnings_history

            result = fetch_earnings_history("PLTR")

            assert len(result) == 2
            assert result[0]["quarter"] == "2025Q4"
            assert result[1]["quarter"] == "2025Q3"
            assert result[0]["eps_actual"] == 0.13

    def test_yfinance_failure_returns_empty(self) -> None:
        """Should return empty list on yfinance error."""
        with patch("backend.services.stock_data.yf.Ticker", side_effect=Exception("boom")):
            from backend.tools.fundamentals import fetch_earnings_history

            result = fetch_earnings_history("BAD")
            assert result == []
