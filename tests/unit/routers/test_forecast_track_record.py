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
            predicted_price=195.0,
            predicted_lower=185.0,
            predicted_upper=205.0,
            target_date=date(2026, 4, 1),
            actual_price=192.0,
            error_pct=0.0156,  # decimal fraction: (195-192)/195
        ),
        Row(
            forecast_date=date(2026, 1, 15),
            ticker="AAPL",
            horizon_days=90,
            predicted_price=198.0,
            predicted_lower=188.0,
            predicted_upper=208.0,
            target_date=date(2026, 4, 15),
            actual_price=201.0,
            error_pct=0.0152,  # decimal fraction: (201-198)/198
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

        # Row 1: forecast_date_price=189, predicted=195 (up), actual=192 (up) → correct
        assert result.evaluations[0].direction_correct is True
        # Row 2: forecast_date_price=190, predicted=198 (up), actual=201 (up) → correct
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

        # Row 1: actual=192.0, band=[185, 205] → inside
        # Row 2: actual=201.0, band=[188, 208] → inside
        assert result.summary.ci_containment_rate == 1.0
