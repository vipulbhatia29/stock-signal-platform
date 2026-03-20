"""Tests for CompanyProfileTool."""

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
    name = "Palantir Technologies"
    business_summary = (
        "Palantir builds software platforms for the "
        "intelligence community and commercial enterprises."
    )
    sector = "Technology"
    industry = "Software - Infrastructure"
    employees = 3800
    website = "https://palantir.com"
    market_cap = 362_000_000_000


class TestCompanyProfileTool:
    """Tests for CompanyProfileTool.execute."""

    @pytest.mark.asyncio
    async def test_returns_company_profile(self) -> None:
        """Should return full profile data from DB."""
        mock_cm = _mock_session_with_stock(FakeStock())

        with patch("backend.database.async_session_factory", return_value=mock_cm):
            from backend.tools.company_profile_tool import CompanyProfileTool

            tool = CompanyProfileTool()
            result = await tool.execute({"ticker": "PLTR"})

            assert result.status == "ok"
            assert result.data["ticker"] == "PLTR"
            assert result.data["name"] == "Palantir Technologies"
            assert result.data["sector"] == "Technology"
            assert result.data["employees"] == 3800
            assert result.data["market_cap"] == 362_000_000_000

    @pytest.mark.asyncio
    async def test_truncates_long_summary(self) -> None:
        """Should truncate business_summary to 500 chars."""

        class LongSummaryStock(FakeStock):
            business_summary = "A" * 600

        mock_cm = _mock_session_with_stock(LongSummaryStock())

        with patch("backend.database.async_session_factory", return_value=mock_cm):
            from backend.tools.company_profile_tool import CompanyProfileTool

            tool = CompanyProfileTool()
            result = await tool.execute({"ticker": "PLTR"})

            assert result.status == "ok"
            assert len(result.data["summary"]) == 500
            assert result.data["summary"].endswith("...")

    @pytest.mark.asyncio
    async def test_ticker_not_in_db(self) -> None:
        """Should return error for unknown ticker."""
        mock_cm = _mock_session_with_stock(None)

        with patch("backend.database.async_session_factory", return_value=mock_cm):
            from backend.tools.company_profile_tool import CompanyProfileTool

            tool = CompanyProfileTool()
            result = await tool.execute({"ticker": "DELISTED"})

            assert result.status == "error"
            assert "not found" in result.error

    @pytest.mark.asyncio
    async def test_empty_ticker_returns_error(self) -> None:
        """Should return error for empty ticker."""
        from backend.tools.company_profile_tool import CompanyProfileTool

        tool = CompanyProfileTool()
        result = await tool.execute({"ticker": ""})
        assert result.status == "error"
