"""Unit tests for convergence API endpoints.

Tests call endpoint functions directly (without a running HTTP server).
Service layer and DB I/O are mocked.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from backend.models.user import User, UserRole
from backend.routers.convergence import (
    get_convergence_history,
    get_portfolio_convergence,
    get_sector_convergence,
    get_ticker_convergence,
)
from backend.services.signal_convergence import (
    DivergenceInfo,
    SignalDirection,
    TickerConvergence,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

PORTFOLIO_ID = str(uuid.uuid4())


@pytest.fixture()
def regular_user() -> User:
    """Provide an authenticated regular user for testing."""
    return User(
        id=uuid.uuid4(),
        email="user@test.com",
        hashed_password="hashed",
        role=UserRole.USER,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture()
def mock_db() -> AsyncMock:
    """Provide a mocked async DB session."""
    return AsyncMock()


def _make_ticker_convergence(
    ticker: str = "AAPL",
    label: str = "strong_bull",
    aligned: int = 5,
    divergent: bool = False,
) -> TickerConvergence:
    """Build a TickerConvergence result for testing.

    Args:
        ticker: Stock ticker.
        label: Convergence label.
        aligned: Signals aligned count.
        divergent: Whether to include divergence.

    Returns:
        TickerConvergence dataclass.
    """
    signals = [
        SignalDirection("rsi", "bullish", 35.0),
        SignalDirection("macd", "bullish", 0.05),
        SignalDirection("sma", "bullish", 200.0),
        SignalDirection("piotroski", "bullish", 7.0),
        SignalDirection(
            "forecast",
            "bearish" if divergent else "bullish",
            -0.05 if divergent else 0.08,
        ),
        SignalDirection("news", "neutral", 0.1),
    ]
    divergence = DivergenceInfo(
        is_divergent=divergent,
        forecast_direction="bearish" if divergent else None,
        technical_majority="bullish" if divergent else None,
    )
    return TickerConvergence(
        ticker=ticker,
        date=date.today(),
        signals=signals,
        signals_aligned=aligned,
        convergence_label=label,
        composite_score=8.5,
        divergence=divergence,
    )


# ---------------------------------------------------------------------------
# GET /convergence/{ticker}
# ---------------------------------------------------------------------------


class TestGetTickerConvergence:
    """Tests for the single-ticker convergence endpoint."""

    @pytest.mark.asyncio()
    async def test_returns_convergence_for_valid_ticker(
        self, regular_user: User, mock_db: AsyncMock
    ) -> None:
        """Happy path — returns convergence data for a valid ticker."""
        conv = _make_ticker_convergence("AAPL")

        with (
            patch("backend.routers.convergence.SignalConvergenceService") as MockService,
            patch("backend.routers.convergence.RationaleGenerator") as MockRationale,
        ):
            svc = MockService.return_value
            svc.get_ticker_convergence = AsyncMock(return_value=conv)
            svc.compute_divergence_hit_rate = AsyncMock(return_value=(None, 0))

            rat = MockRationale.return_value
            rat.generate = AsyncMock(return_value="5 of 6 signals align bullish.")

            result = await get_ticker_convergence("aapl", regular_user, mock_db)

        assert result.ticker == "AAPL"
        assert result.convergence_label.value == "strong_bull"
        assert result.rationale == "5 of 6 signals align bullish."
        assert len(result.signals) == 6

    @pytest.mark.asyncio()
    async def test_returns_404_for_unknown_ticker(
        self, regular_user: User, mock_db: AsyncMock
    ) -> None:
        """Returns 404 when no signal data exists for the ticker."""
        with patch("backend.routers.convergence.SignalConvergenceService") as MockService:
            svc = MockService.return_value
            svc.get_ticker_convergence = AsyncMock(return_value=None)

            with pytest.raises(HTTPException) as exc_info:
                await get_ticker_convergence("FAKE", regular_user, mock_db)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio()
    async def test_divergence_enriched_with_hit_rate(
        self, regular_user: User, mock_db: AsyncMock
    ) -> None:
        """Divergent tickers get historical hit rate enrichment."""
        conv = _make_ticker_convergence("AAPL", label="weak_bull", aligned=4, divergent=True)

        with (
            patch("backend.routers.convergence.SignalConvergenceService") as MockService,
            patch("backend.routers.convergence.RationaleGenerator") as MockRationale,
        ):
            svc = MockService.return_value
            svc.get_ticker_convergence = AsyncMock(return_value=conv)
            svc.compute_divergence_hit_rate = AsyncMock(return_value=(0.61, 23))

            rat = MockRationale.return_value
            rat.generate = AsyncMock(return_value="Divergence detected.")

            result = await get_ticker_convergence("AAPL", regular_user, mock_db)

        assert result.divergence.is_divergent is True
        assert result.divergence.historical_hit_rate == 0.61
        assert result.divergence.sample_count == 23


# ---------------------------------------------------------------------------
# GET /convergence/portfolio/{portfolio_id}
# ---------------------------------------------------------------------------


class TestGetPortfolioConvergence:
    """Tests for the portfolio convergence endpoint."""

    @pytest.mark.asyncio()
    async def test_returns_portfolio_convergence(
        self, regular_user: User, mock_db: AsyncMock
    ) -> None:
        """Happy path — returns convergence for all portfolio positions."""
        conv1 = _make_ticker_convergence("AAPL", "strong_bull", 5)
        conv2 = _make_ticker_convergence("MSFT", "weak_bear", 3)

        # Mock portfolio ownership check
        mock_portfolio = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_portfolio
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("backend.routers.convergence.SignalConvergenceService") as MockService:
            svc = MockService.return_value
            svc.get_portfolio_convergence = AsyncMock(return_value=[(conv1, 0.6), (conv2, 0.4)])

            result = await get_portfolio_convergence(PORTFOLIO_ID, regular_user, mock_db)

        assert result.portfolio_id == PORTFOLIO_ID
        assert len(result.positions) == 2
        assert result.bullish_pct == pytest.approx(0.6, abs=0.01)
        assert result.bearish_pct == pytest.approx(0.4, abs=0.01)

    @pytest.mark.asyncio()
    async def test_returns_404_for_nonexistent_portfolio(
        self, regular_user: User, mock_db: AsyncMock
    ) -> None:
        """Returns 404 when portfolio doesn't exist or belongs to another user."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(HTTPException) as exc_info:
            await get_portfolio_convergence(PORTFOLIO_ID, regular_user, mock_db)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio()
    async def test_empty_portfolio_returns_zeros(
        self, regular_user: User, mock_db: AsyncMock
    ) -> None:
        """Empty portfolio returns zero percentages."""
        mock_portfolio = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_portfolio
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("backend.routers.convergence.SignalConvergenceService") as MockService:
            svc = MockService.return_value
            svc.get_portfolio_convergence = AsyncMock(return_value=[])

            result = await get_portfolio_convergence(PORTFOLIO_ID, regular_user, mock_db)

        assert result.bullish_pct == 0.0
        assert result.bearish_pct == 0.0
        assert result.mixed_pct == 0.0
        assert len(result.positions) == 0

    @pytest.mark.asyncio()
    async def test_divergent_positions_listed(self, regular_user: User, mock_db: AsyncMock) -> None:
        """Divergent positions appear in the divergent_positions list."""
        conv1 = _make_ticker_convergence("AAPL", "weak_bull", 4, divergent=True)
        conv2 = _make_ticker_convergence("MSFT", "strong_bull", 5, divergent=False)

        mock_portfolio = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_portfolio
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("backend.routers.convergence.SignalConvergenceService") as MockService:
            svc = MockService.return_value
            svc.get_portfolio_convergence = AsyncMock(return_value=[(conv1, 0.5), (conv2, 0.5)])

            result = await get_portfolio_convergence(PORTFOLIO_ID, regular_user, mock_db)

        assert "AAPL" in result.divergent_positions
        assert "MSFT" not in result.divergent_positions


# ---------------------------------------------------------------------------
# GET /convergence/{ticker}/history
# ---------------------------------------------------------------------------


class TestGetConvergenceHistory:
    """Tests for the convergence history endpoint."""

    @pytest.mark.asyncio()
    async def test_returns_paginated_history(self, regular_user: User, mock_db: AsyncMock) -> None:
        """Happy path — returns paginated convergence history."""
        mock_rows = [
            MagicMock(
                date=date(2024, 3, i),
                convergence_label="strong_bull",
                signals_aligned=5,
                composite_score=8.0,
                actual_return_90d=0.05 if i < 10 else None,
                actual_return_180d=None,
            )
            for i in range(1, 11)
        ]

        with patch("backend.routers.convergence.SignalConvergenceService") as MockService:
            svc = MockService.return_value
            svc.get_convergence_history = AsyncMock(return_value=(mock_rows, 30))

            result = await get_convergence_history("aapl", 90, 10, 0, regular_user, mock_db)

        assert result.ticker == "AAPL"
        assert len(result.data) == 10
        assert result.total == 30
        assert result.limit == 10
        assert result.offset == 0

    @pytest.mark.asyncio()
    async def test_empty_history_returns_empty_list(
        self, regular_user: User, mock_db: AsyncMock
    ) -> None:
        """No history data returns empty list with total=0."""
        with patch("backend.routers.convergence.SignalConvergenceService") as MockService:
            svc = MockService.return_value
            svc.get_convergence_history = AsyncMock(return_value=([], 0))

            result = await get_convergence_history("AAPL", 90, 50, 0, regular_user, mock_db)

        assert result.data == []
        assert result.total == 0

    @pytest.mark.asyncio()
    async def test_service_error_returns_500(self, regular_user: User, mock_db: AsyncMock) -> None:
        """DB error in service raises 500."""
        with patch("backend.routers.convergence.SignalConvergenceService") as MockService:
            svc = MockService.return_value
            svc.get_convergence_history = AsyncMock(side_effect=RuntimeError("DB error"))

            with pytest.raises(HTTPException) as exc_info:
                await get_convergence_history("AAPL", 90, 50, 0, regular_user, mock_db)

        assert exc_info.value.status_code == 500


# ---------------------------------------------------------------------------
# GET /sectors/{sector}/convergence
# ---------------------------------------------------------------------------


class TestGetSectorConvergence:
    """Tests for the sector convergence endpoint."""

    @pytest.mark.asyncio()
    async def test_returns_sector_convergence(self, regular_user: User, mock_db: AsyncMock) -> None:
        """Happy path — returns equal-weight sector convergence."""
        conv1 = _make_ticker_convergence("AAPL", "strong_bull", 5)
        conv2 = _make_ticker_convergence("MSFT", "strong_bull", 5)
        conv3 = _make_ticker_convergence("GOOGL", "weak_bear", 3)

        with patch("backend.routers.convergence.SignalConvergenceService") as MockService:
            svc = MockService.return_value
            svc.get_sector_convergence = AsyncMock(return_value=[conv1, conv2, conv3])

            result = await get_sector_convergence("Technology", regular_user, mock_db)

        assert result.sector == "Technology"
        assert result.ticker_count == 3
        # 2 bullish / 3 total ≈ 0.6667
        assert result.bullish_pct == pytest.approx(0.6667, abs=0.01)
        # 1 bearish / 3 total ≈ 0.3333
        assert result.bearish_pct == pytest.approx(0.3333, abs=0.01)
        assert len(result.tickers) == 3

    @pytest.mark.asyncio()
    async def test_empty_sector_returns_zeros(self, regular_user: User, mock_db: AsyncMock) -> None:
        """Empty sector returns zero counts."""
        with patch("backend.routers.convergence.SignalConvergenceService") as MockService:
            svc = MockService.return_value
            svc.get_sector_convergence = AsyncMock(return_value=[])

            result = await get_sector_convergence("Nonexistent", regular_user, mock_db)

        assert result.ticker_count == 0
        assert result.bullish_pct == 0.0
        assert result.bearish_pct == 0.0
        assert result.tickers == []
