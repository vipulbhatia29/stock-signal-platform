"""Unit tests for portfolio forecast API endpoints."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from backend.models.user import User, UserRole
from backend.routers.portfolio import (
    _build_forecast_response,
    get_portfolio_forecast,
    get_portfolio_forecast_components,
)
from backend.services.portfolio_forecast import (
    BLResult,
    CVaRResult,
    MonteCarloResult,
    PortfolioForecastResult,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def regular_user() -> User:
    """Provide a regular authenticated user."""
    return User(
        id=uuid.uuid4(),
        email="investor@test.com",
        hashed_password="hashed",
        role=UserRole.USER,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def mock_db() -> AsyncMock:
    """Provide a mocked async DB session with configurable scalar_one_or_none."""
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    return db


@pytest.fixture
def sample_portfolio_id() -> str:
    """Provide a sample portfolio UUID string."""
    return str(uuid.uuid4())


@pytest.fixture
def sample_forecast(sample_portfolio_id: str) -> PortfolioForecastResult:
    """Provide a realistic PortfolioForecastResult for mocking."""
    return PortfolioForecastResult(
        bl=BLResult(
            expected_returns={"AAPL": 0.12, "MSFT": 0.10},
            portfolio_expected_return=0.11,
            view_confidences={"AAPL": 0.8, "MSFT": 0.7},
            risk_free_rate=0.05,
        ),
        monte_carlo=MonteCarloResult(
            percentile_bands={
                "p5": [9500.0] * 90,
                "p25": [9800.0] * 90,
                "p50": [10200.0] * 90,
                "p75": [10500.0] * 90,
                "p95": [11000.0] * 90,
            },
            terminal_values=[10200.0] * 100,
            simulation_days=90,
            initial_value=10000.0,
        ),
        cvar=CVaRResult(
            cvar_95=-0.12,
            cvar_99=-0.18,
            var_95=-0.08,
            var_99=-0.13,
        ),
        forecast_date=date(2026, 4, 2),
        horizon_days=90,
        tickers=["AAPL", "MSFT"],
    )


def _make_mock_db_with_portfolio(portfolio_id: str, user_id: uuid.UUID) -> AsyncMock:
    """Create a mock DB that returns a matching portfolio for ownership checks."""
    from unittest.mock import MagicMock

    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()

    # Simulate a portfolio row
    fake_portfolio = MagicMock()
    fake_portfolio.id = portfolio_id
    fake_portfolio.user_id = user_id

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = fake_portfolio
    db.execute = AsyncMock(return_value=mock_result)
    return db


def _make_mock_db_no_portfolio() -> AsyncMock:
    """Create a mock DB that returns None for ownership check (portfolio not found)."""
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=mock_result)
    return db


# ---------------------------------------------------------------------------
# Tests: GET /portfolio/{portfolio_id}/forecast
# ---------------------------------------------------------------------------


class TestGetPortfolioForecast:
    """Tests for GET /portfolio/{portfolio_id}/forecast."""

    @pytest.mark.asyncio
    async def test_returns_forecast_for_valid_portfolio(
        self,
        regular_user: User,
        sample_portfolio_id: str,
        sample_forecast: PortfolioForecastResult,
    ) -> None:
        """Returns PortfolioForecastFullResponse for a valid owned portfolio."""
        db = _make_mock_db_with_portfolio(sample_portfolio_id, regular_user.id)

        mock_service = MagicMock()
        mock_service.compute_forecast = AsyncMock(return_value=sample_forecast)

        with patch(
            "backend.routers.portfolio.PortfolioForecastService",
            return_value=mock_service,
        ):
            result = await get_portfolio_forecast(
                portfolio_id=sample_portfolio_id,
                user=regular_user,
                db=db,
                horizon_days=90,
            )

        assert result.portfolio_id == sample_portfolio_id
        assert result.horizon_days == 90

    @pytest.mark.asyncio
    async def test_returns_404_for_nonexistent_portfolio(
        self,
        regular_user: User,
        sample_portfolio_id: str,
    ) -> None:
        """Returns 404 when the portfolio does not exist in the database."""
        db = _make_mock_db_no_portfolio()

        with pytest.raises(HTTPException) as exc_info:
            await get_portfolio_forecast(
                portfolio_id=sample_portfolio_id,
                user=regular_user,
                db=db,
                horizon_days=90,
            )

        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_returns_404_for_portfolio_owned_by_other_user(
        self,
        sample_portfolio_id: str,
    ) -> None:
        """Returns 404 (not 403) when portfolio belongs to a different user (IDOR check)."""
        # A different user tries to access someone else's portfolio
        other_user = User(
            id=uuid.uuid4(),
            email="attacker@test.com",
            hashed_password="hashed",
            role=UserRole.USER,
            is_active=True,
            email_verified=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        # DB returns None because user_id doesn't match the WHERE clause
        db = _make_mock_db_no_portfolio()

        with pytest.raises(HTTPException) as exc_info:
            await get_portfolio_forecast(
                portfolio_id=sample_portfolio_id,
                user=other_user,
                db=db,
                horizon_days=90,
            )

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_returns_404_when_service_raises_value_error(
        self,
        regular_user: User,
        sample_portfolio_id: str,
    ) -> None:
        """Returns 404 when service raises ValueError (no positions / insufficient data)."""
        db = _make_mock_db_with_portfolio(sample_portfolio_id, regular_user.id)

        mock_service = MagicMock()
        mock_service.compute_forecast = AsyncMock(
            side_effect=ValueError("Portfolio has no active positions")
        )

        with patch(
            "backend.routers.portfolio.PortfolioForecastService",
            return_value=mock_service,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_portfolio_forecast(
                    portfolio_id=sample_portfolio_id,
                    user=regular_user,
                    db=db,
                    horizon_days=90,
                )

        assert exc_info.value.status_code == 404
        assert "Insufficient data" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_returns_500_when_service_raises_unexpected_error(
        self,
        regular_user: User,
        sample_portfolio_id: str,
    ) -> None:
        """Returns 500 when service raises an unexpected exception."""
        db = _make_mock_db_with_portfolio(sample_portfolio_id, regular_user.id)

        mock_service = MagicMock()
        mock_service.compute_forecast = AsyncMock(side_effect=RuntimeError("NumPy explosion"))

        with patch(
            "backend.routers.portfolio.PortfolioForecastService",
            return_value=mock_service,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_portfolio_forecast(
                    portfolio_id=sample_portfolio_id,
                    user=regular_user,
                    db=db,
                    horizon_days=90,
                )

        assert exc_info.value.status_code == 500
        assert "computation failed" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_response_has_correct_schema_sections(
        self,
        regular_user: User,
        sample_portfolio_id: str,
        sample_forecast: PortfolioForecastResult,
    ) -> None:
        """Response contains all three top-level sections: bl, monte_carlo, cvar."""
        db = _make_mock_db_with_portfolio(sample_portfolio_id, regular_user.id)
        mock_service = MagicMock()
        mock_service.compute_forecast = AsyncMock(return_value=sample_forecast)

        with patch(
            "backend.routers.portfolio.PortfolioForecastService",
            return_value=mock_service,
        ):
            result = await get_portfolio_forecast(
                portfolio_id=sample_portfolio_id,
                user=regular_user,
                db=db,
                horizon_days=90,
            )

        # Verify all three forecast sections are present
        assert result.bl is not None
        assert result.monte_carlo is not None
        assert result.cvar is not None
        assert result.forecast_date is not None

    @pytest.mark.asyncio
    async def test_cvar_descriptions_have_correct_format(
        self,
        regular_user: User,
        sample_portfolio_id: str,
        sample_forecast: PortfolioForecastResult,
    ) -> None:
        """CVaR description strings match the expected format with sign and %."""
        db = _make_mock_db_with_portfolio(sample_portfolio_id, regular_user.id)
        mock_service = MagicMock()
        mock_service.compute_forecast = AsyncMock(return_value=sample_forecast)

        with patch(
            "backend.routers.portfolio.PortfolioForecastService",
            return_value=mock_service,
        ):
            result = await get_portfolio_forecast(
                portfolio_id=sample_portfolio_id,
                user=regular_user,
                db=db,
                horizon_days=90,
            )

        # cvar_95 = -0.12 → -12.0%
        assert "1-in-20" in result.cvar.description_95
        assert "-12.0%" in result.cvar.description_95
        # cvar_99 = -0.18 → -18.0%
        assert "1-in-100" in result.cvar.description_99
        assert "-18.0%" in result.cvar.description_99

    @pytest.mark.asyncio
    async def test_monte_carlo_terminal_values_populated(
        self,
        regular_user: User,
        sample_portfolio_id: str,
        sample_forecast: PortfolioForecastResult,
    ) -> None:
        """Monte Carlo summary contains correct terminal value statistics."""
        db = _make_mock_db_with_portfolio(sample_portfolio_id, regular_user.id)
        mock_service = MagicMock()
        mock_service.compute_forecast = AsyncMock(return_value=sample_forecast)

        with patch(
            "backend.routers.portfolio.PortfolioForecastService",
            return_value=mock_service,
        ):
            result = await get_portfolio_forecast(
                portfolio_id=sample_portfolio_id,
                user=regular_user,
                db=db,
                horizon_days=90,
            )

        mc = result.monte_carlo
        assert mc.simulation_days == 90
        assert mc.initial_value == 10000.0
        # All terminal values are 10200.0 so median == p5 == p95
        assert mc.terminal_median == 10200.0
        assert mc.terminal_p5 == 10200.0
        assert mc.terminal_p95 == 10200.0

    @pytest.mark.asyncio
    async def test_bl_per_ticker_matches_portfolio_tickers(
        self,
        regular_user: User,
        sample_portfolio_id: str,
        sample_forecast: PortfolioForecastResult,
    ) -> None:
        """BL per_ticker list contains one entry per portfolio ticker."""
        db = _make_mock_db_with_portfolio(sample_portfolio_id, regular_user.id)
        mock_service = MagicMock()
        mock_service.compute_forecast = AsyncMock(return_value=sample_forecast)

        with patch(
            "backend.routers.portfolio.PortfolioForecastService",
            return_value=mock_service,
        ):
            result = await get_portfolio_forecast(
                portfolio_id=sample_portfolio_id,
                user=regular_user,
                db=db,
                horizon_days=90,
            )

        tickers_in_response = {entry.ticker for entry in result.bl.per_ticker}
        assert tickers_in_response == {"AAPL", "MSFT"}
        # Check expected return values
        aapl_entry = next(e for e in result.bl.per_ticker if e.ticker == "AAPL")
        assert aapl_entry.expected_return == 0.12
        assert aapl_entry.view_confidence == 0.8

    @pytest.mark.asyncio
    async def test_bl_view_confidence_none_when_no_prophet_view(
        self,
        regular_user: User,
        sample_portfolio_id: str,
    ) -> None:
        """BL entries for tickers without Prophet views have view_confidence=None."""
        forecast = PortfolioForecastResult(
            bl=BLResult(
                expected_returns={"TSLA": 0.08},
                portfolio_expected_return=0.08,
                view_confidences={},  # no views
                risk_free_rate=0.05,
            ),
            monte_carlo=MonteCarloResult(
                percentile_bands={"p5": [], "p25": [], "p50": [], "p75": [], "p95": []},
                terminal_values=[],
                simulation_days=90,
                initial_value=5000.0,
            ),
            cvar=CVaRResult(cvar_95=0.0, cvar_99=0.0, var_95=0.0, var_99=0.0),
            forecast_date=date(2026, 4, 2),
            horizon_days=90,
            tickers=["TSLA"],
        )

        db = _make_mock_db_with_portfolio(sample_portfolio_id, regular_user.id)
        mock_service = MagicMock()
        mock_service.compute_forecast = AsyncMock(return_value=forecast)

        with patch(
            "backend.routers.portfolio.PortfolioForecastService",
            return_value=mock_service,
        ):
            result = await get_portfolio_forecast(
                portfolio_id=sample_portfolio_id,
                user=regular_user,
                db=db,
                horizon_days=90,
            )

        tsla_entry = next(e for e in result.bl.per_ticker if e.ticker == "TSLA")
        assert tsla_entry.view_confidence is None


# ---------------------------------------------------------------------------
# Tests: GET /portfolio/{portfolio_id}/forecast/components
# ---------------------------------------------------------------------------


class TestGetPortfolioForecastComponents:
    """Tests for GET /portfolio/{portfolio_id}/forecast/components."""

    @pytest.mark.asyncio
    async def test_components_endpoint_returns_empty_list(
        self,
        regular_user: User,
        sample_portfolio_id: str,
    ) -> None:
        """Returns PortfolioForecastComponentsResponse with empty components list."""
        db = _make_mock_db_with_portfolio(sample_portfolio_id, regular_user.id)

        result = await get_portfolio_forecast_components(
            portfolio_id=sample_portfolio_id,
            user=regular_user,
            db=db,
        )

        assert result.portfolio_id == sample_portfolio_id
        assert result.components == []

    @pytest.mark.asyncio
    async def test_components_returns_404_for_unknown_portfolio(
        self,
        regular_user: User,
        sample_portfolio_id: str,
    ) -> None:
        """Returns 404 when the portfolio does not belong to the user."""
        db = _make_mock_db_no_portfolio()

        with pytest.raises(HTTPException) as exc_info:
            await get_portfolio_forecast_components(
                portfolio_id=sample_portfolio_id,
                user=regular_user,
                db=db,
            )

        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# Tests: _build_forecast_response helper
# ---------------------------------------------------------------------------


class TestBuildForecastResponse:
    """Tests for the _build_forecast_response helper function."""

    def test_maps_bl_summary_correctly(
        self, sample_portfolio_id: str, sample_forecast: PortfolioForecastResult
    ) -> None:
        """Maps BL expected returns, risk-free rate, and per_ticker list correctly."""
        response = _build_forecast_response(sample_portfolio_id, sample_forecast)

        assert response.bl.portfolio_expected_return == 0.11
        assert response.bl.risk_free_rate == 0.05
        assert len(response.bl.per_ticker) == 2

    def test_cvar_percentages_are_multiplied_by_100(
        self, sample_portfolio_id: str, sample_forecast: PortfolioForecastResult
    ) -> None:
        """CVaR decimal values are converted to percentages in the response."""
        response = _build_forecast_response(sample_portfolio_id, sample_forecast)

        # cvar_95 = -0.12 → -12.0
        assert response.cvar.cvar_95_pct == -12.0
        # cvar_99 = -0.18 → -18.0
        assert response.cvar.cvar_99_pct == -18.0

    def test_empty_terminal_values_defaults_to_initial_value(
        self, sample_portfolio_id: str
    ) -> None:
        """When terminal_values is empty, terminal stats default to initial_value."""
        forecast = PortfolioForecastResult(
            bl=BLResult(
                expected_returns={},
                portfolio_expected_return=0.0,
                view_confidences={},
                risk_free_rate=0.05,
            ),
            monte_carlo=MonteCarloResult(
                percentile_bands={"p5": [], "p25": [], "p50": [], "p75": [], "p95": []},
                terminal_values=[],  # empty
                simulation_days=90,
                initial_value=8000.0,
            ),
            cvar=CVaRResult(cvar_95=0.0, cvar_99=0.0, var_95=0.0, var_99=0.0),
            forecast_date=date(2026, 4, 2),
            horizon_days=90,
        )

        response = _build_forecast_response(sample_portfolio_id, forecast)

        assert response.monte_carlo.terminal_median == 8000.0
        assert response.monte_carlo.terminal_p5 == 8000.0
        assert response.monte_carlo.terminal_p95 == 8000.0
