"""Tests for PortfolioAnalyticsTool agent tool."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from backend.tools.portfolio_analytics import PortfolioAnalyticsTool


class TestPortfolioAnalyticsTool:
    """Tests for PortfolioAnalyticsTool.execute()."""

    @pytest.mark.asyncio
    async def test_no_user_context_returns_error(self):
        """No user_id in ContextVar → error."""
        tool = PortfolioAnalyticsTool()
        with patch("backend.request_context.current_user_id") as mock_ctx:
            mock_ctx.get.return_value = None
            result = await tool.execute({})
        assert result.status == "error"
        assert "No user context" in (result.error or "")

    @pytest.mark.asyncio
    async def test_no_snapshots_returns_message(self):
        """No portfolio snapshots → informational message."""
        tool = PortfolioAnalyticsTool()
        user_id = uuid4()
        portfolio = MagicMock(id=uuid4())
        mock_session = AsyncMock()

        snap_result = MagicMock()
        snap_result.scalar_one_or_none.return_value = None

        with (
            patch("backend.request_context.current_user_id") as mock_ctx,
            patch("backend.database.async_session_factory") as mock_factory,
            patch(
                "backend.tools.portfolio.get_or_create_portfolio",
                new_callable=AsyncMock,
            ) as mock_portfolio,
        ):
            mock_ctx.get.return_value = user_id
            mock_portfolio.return_value = portfolio
            cm = AsyncMock()
            cm.__aenter__.return_value = mock_session
            cm.__aexit__.return_value = False
            mock_factory.return_value = cm
            mock_session.execute.return_value = snap_result

            result = await tool.execute({})

        assert result.status == "ok"
        assert "No portfolio snapshots" in str(result.data)

    @pytest.mark.asyncio
    async def test_with_data_returns_metrics(self):
        """Snapshot with QuantStats data → metrics returned."""
        tool = PortfolioAnalyticsTool()
        user_id = uuid4()
        portfolio = MagicMock(id=uuid4())

        snapshot = MagicMock()
        snapshot.sharpe = 1.5
        snapshot.sortino = 2.0
        snapshot.max_drawdown = 0.12
        snapshot.max_drawdown_duration = 15
        snapshot.calmar = 3.0
        snapshot.alpha = 0.05
        snapshot.beta = 0.9
        snapshot.var_95 = 0.02
        snapshot.cagr = 0.15
        snapshot.data_days = 180

        mock_session = AsyncMock()
        snap_result = MagicMock()
        snap_result.scalar_one_or_none.return_value = snapshot

        with (
            patch("backend.request_context.current_user_id") as mock_ctx,
            patch("backend.database.async_session_factory") as mock_factory,
            patch(
                "backend.tools.portfolio.get_or_create_portfolio",
                new_callable=AsyncMock,
            ) as mock_portfolio,
        ):
            mock_ctx.get.return_value = user_id
            mock_portfolio.return_value = portfolio
            cm = AsyncMock()
            cm.__aenter__.return_value = mock_session
            cm.__aexit__.return_value = False
            mock_factory.return_value = cm
            mock_session.execute.return_value = snap_result

            result = await tool.execute({})

        assert result.status == "ok"
        assert result.data["sharpe"] == 1.5
        assert result.data["data_days"] == 180
