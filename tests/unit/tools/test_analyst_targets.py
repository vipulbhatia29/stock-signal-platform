"""Tests for AnalystTargetsTool."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _mock_session_with_stock(stock):
    """Create a mock async session context manager returning the given stock."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = stock
    mock_session.execute.return_value = mock_result
    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_session
    mock_cm.__aexit__.return_value = None
    return mock_cm


class FakeStock:
    """Minimal Stock stand-in for testing."""

    ticker = "PLTR"
    analyst_target_mean = 186.60
    analyst_target_high = 260.0
    analyst_target_low = 70.0
    analyst_buy = 12
    analyst_hold = 5
    analyst_sell = 2


class TestAnalystTargetsTool:
    """Tests for AnalystTargetsTool.execute."""

    @pytest.mark.asyncio
    async def test_returns_analyst_targets(self) -> None:
        """Should return target prices and buy/hold/sell counts."""
        mock_cm = _mock_session_with_stock(FakeStock())

        with patch("backend.database.async_session_factory", return_value=mock_cm):
            from backend.tools.analyst_targets_tool import AnalystTargetsTool

            tool = AnalystTargetsTool()
            result = await tool.execute({"ticker": "PLTR"})

            assert result.status == "ok"
            assert result.data["has_targets"] is True
            assert result.data["target_mean"] == 186.60
            assert result.data["target_high"] == 260.0
            assert result.data["target_low"] == 70.0
            assert result.data["buy_count"] == 12
            assert result.data["hold_count"] == 5
            assert result.data["sell_count"] == 2

    @pytest.mark.asyncio
    async def test_no_targets_available(self) -> None:
        """Should return has_targets=False when no analyst data exists."""

        class NoTargetsStock:
            ticker = "TINY"
            analyst_target_mean = None
            analyst_target_high = None
            analyst_target_low = None
            analyst_buy = None
            analyst_hold = None
            analyst_sell = None

        mock_cm = _mock_session_with_stock(NoTargetsStock())

        with patch("backend.database.async_session_factory", return_value=mock_cm):
            from backend.tools.analyst_targets_tool import AnalystTargetsTool

            tool = AnalystTargetsTool()
            result = await tool.execute({"ticker": "TINY"})

            assert result.status == "ok"
            assert result.data["has_targets"] is False

    @pytest.mark.asyncio
    async def test_ticker_not_in_db(self) -> None:
        """Should return error for unknown ticker."""
        mock_cm = _mock_session_with_stock(None)

        with patch("backend.database.async_session_factory", return_value=mock_cm):
            from backend.tools.analyst_targets_tool import AnalystTargetsTool

            tool = AnalystTargetsTool()
            result = await tool.execute({"ticker": "INVALID"})

            assert result.status == "error"
            assert "not found" in result.error

    @pytest.mark.asyncio
    async def test_empty_ticker_returns_error(self) -> None:
        """Should return error for empty ticker."""
        from backend.tools.analyst_targets_tool import AnalystTargetsTool

        tool = AnalystTargetsTool()
        result = await tool.execute({"ticker": ""})
        assert result.status == "error"
