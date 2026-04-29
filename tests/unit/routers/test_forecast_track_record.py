"""Unit tests for GET /forecasts/{ticker}/track-record endpoint."""

import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.models.user import User, UserRole


@pytest.fixture
def regular_user():
    """Provide a regular user for testing."""
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


@pytest.fixture
def mock_forecast_rows():
    """Evaluated forecast rows with matching stock prices."""

    class Row:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    return [
        Row(
            forecast_date=date(2026, 1, 1),
            ticker="AAPL",
            horizon_days=90,
            expected_return_pct=3.17,
            return_lower_pct=-2.65,
            return_upper_pct=8.47,
            confidence_score=0.65,
            direction="bullish",
            base_price=189.0,
            target_date=date(2026, 4, 1),
            actual_return_pct=1.59,
            error_pct=0.0156,
        ),
        Row(
            forecast_date=date(2026, 1, 15),
            ticker="AAPL",
            horizon_days=90,
            expected_return_pct=4.21,
            return_lower_pct=-1.05,
            return_upper_pct=9.47,
            confidence_score=0.70,
            direction="bullish",
            base_price=190.0,
            target_date=date(2026, 4, 15),
            actual_return_pct=5.79,
            error_pct=0.0152,
        ),
    ]


@pytest.fixture
def mock_price_map():
    """Price at forecast_date for direction computation."""
    return {
        date(2026, 1, 1): 189.0,
        date(2026, 1, 15): 190.0,
    }


@pytest.fixture
def mock_request():
    """Provide a mock FastAPI request with cache disabled."""
    req = MagicMock()
    req.app.state.cache = None
    return req


class TestForecastTrackRecord:
    """Tests for get_forecast_track_record handler."""

    @pytest.mark.asyncio
    async def test_returns_evaluations_with_summary(
        self, regular_user, mock_request, mock_forecast_rows, mock_price_map
    ):
        """Returns evaluated forecasts with correct summary statistics."""
        from backend.routers.forecasts import get_forecast_track_record

        mock_db = AsyncMock()

        with (
            patch(
                "backend.routers.forecasts._fetch_evaluated_forecasts",
                new_callable=AsyncMock,
                return_value=mock_forecast_rows,
            ),
            patch(
                "backend.routers.forecasts._fetch_forecast_date_prices",
                new_callable=AsyncMock,
                return_value=mock_price_map,
            ),
        ):
            result = await get_forecast_track_record(
                ticker="AAPL",
                request=mock_request,
                days=365,
                current_user=regular_user,
                session=mock_db,
            )

        assert result.ticker == "AAPL"
        assert len(result.evaluations) == 2
        assert result.summary.total_evaluated == 2
        assert 0.0 <= result.summary.direction_hit_rate <= 1.0
        assert result.summary.avg_error_pct > 0

    @pytest.mark.asyncio
    async def test_empty_track_record(self, regular_user, mock_request):
        """Returns zero summary when no evaluated forecasts exist."""
        from backend.routers.forecasts import get_forecast_track_record

        mock_db = AsyncMock()

        with (
            patch(
                "backend.routers.forecasts._fetch_evaluated_forecasts",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "backend.routers.forecasts._fetch_forecast_date_prices",
                new_callable=AsyncMock,
                return_value={},
            ),
        ):
            result = await get_forecast_track_record(
                ticker="AAPL",
                request=mock_request,
                days=365,
                current_user=regular_user,
                session=mock_db,
            )

        assert result.summary.total_evaluated == 0
        assert result.summary.direction_hit_rate == 0.0
        assert result.summary.avg_error_pct == 0.0

    @pytest.mark.asyncio
    async def test_direction_correct_calculation(
        self, regular_user, mock_request, mock_forecast_rows, mock_price_map
    ):
        """Correctly computes direction_correct from forecast vs actual prices."""
        from backend.routers.forecasts import get_forecast_track_record

        mock_db = AsyncMock()

        with (
            patch(
                "backend.routers.forecasts._fetch_evaluated_forecasts",
                new_callable=AsyncMock,
                return_value=mock_forecast_rows,
            ),
            patch(
                "backend.routers.forecasts._fetch_forecast_date_prices",
                new_callable=AsyncMock,
                return_value=mock_price_map,
            ),
        ):
            result = await get_forecast_track_record(
                ticker="AAPL",
                request=mock_request,
                days=365,
                current_user=regular_user,
                session=mock_db,
            )

        # Row 1: expected_return_pct=3.17 (>0 → bullish), actual_return_pct=1.59 (>0) → correct
        assert result.evaluations[0].direction_correct is True
        # Row 2: expected_return_pct=4.21 (>0 → bullish), actual_return_pct=5.79 (>0) → correct
        assert result.evaluations[1].direction_correct is True

    @pytest.mark.asyncio
    async def test_ci_containment(
        self, regular_user, mock_request, mock_forecast_rows, mock_price_map
    ):
        """Correctly computes CI containment rate."""
        from backend.routers.forecasts import get_forecast_track_record

        mock_db = AsyncMock()

        with (
            patch(
                "backend.routers.forecasts._fetch_evaluated_forecasts",
                new_callable=AsyncMock,
                return_value=mock_forecast_rows,
            ),
            patch(
                "backend.routers.forecasts._fetch_forecast_date_prices",
                new_callable=AsyncMock,
                return_value=mock_price_map,
            ),
        ):
            result = await get_forecast_track_record(
                ticker="AAPL",
                request=mock_request,
                days=365,
                current_user=regular_user,
                session=mock_db,
            )

        # Row 1: actual_return=1.59, band=[-2.65, 8.47] → inside
        # Row 2: actual_return=5.79, band=[-1.05, 9.47] → inside
        assert result.summary.ci_containment_rate == 1.0
