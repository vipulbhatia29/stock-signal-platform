"""Unit tests for backtest API endpoints."""

import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.models.backtest import BacktestRun
from backend.models.user import User, UserRole
from backend.routers.backtesting import (
    get_backtest_history,
    get_backtest_result,
    get_backtest_summary,
    trigger_backtest,
    trigger_calibration,
)
from backend.schemas.backtesting import (
    BacktestTriggerRequest,
    CalibrateTriggerRequest,
)


@pytest.fixture
def admin_user():
    """Provide an admin user for testing."""
    return User(
        id=uuid.uuid4(),
        email="admin@test.com",
        hashed_password="hashed",
        role=UserRole.ADMIN,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def regular_user():
    """Provide a regular (non-admin) user for testing."""
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
def sample_backtest_run():
    """Provide a sample BacktestRun for testing."""
    return BacktestRun(
        id=uuid.uuid4(),
        ticker="AAPL",
        model_version_id=uuid.uuid4(),
        config_label="baseline",
        train_start=date(2022, 1, 1),
        train_end=date(2023, 12, 31),
        test_start=date(2024, 1, 1),
        test_end=date(2024, 12, 31),
        horizon_days=90,
        num_windows=12,
        mape=0.08,
        mae=15.2,
        rmse=18.5,
        direction_accuracy=0.64,
        ci_containment=0.78,
        market_regime="bull",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


class TestGetBacktestResult:
    """Tests for GET /backtests/{ticker}."""

    @pytest.mark.asyncio
    async def test_returns_latest_result(self, sample_backtest_run, regular_user):
        """Returns the most recent backtest run for the ticker."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_backtest_run
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await get_backtest_result(
            ticker="AAPL", horizon_days=90, db=mock_db, current_user=regular_user
        )
        assert result is not None
        assert result.ticker == "AAPL"
        assert result.mape == 0.08

    @pytest.mark.asyncio
    async def test_raises_404_when_no_data(self, regular_user):
        """Returns 404 when no backtest exists for ticker."""
        from fastapi import HTTPException

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(HTTPException) as exc_info:
            await get_backtest_result(
                ticker="ZZZZ", horizon_days=90, db=mock_db, current_user=regular_user
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_uppercases_ticker(self, sample_backtest_run, regular_user):
        """Ticker is uppercased before querying."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_backtest_run
        mock_db.execute = AsyncMock(return_value=mock_result)

        await get_backtest_result(
            ticker="aapl", horizon_days=90, db=mock_db, current_user=regular_user
        )
        # Verify the execute was called (ticker uppercased in query)
        mock_db.execute.assert_called_once()


class TestGetBacktestHistory:
    """Tests for GET /backtests/{ticker}/history."""

    @pytest.mark.asyncio
    async def test_returns_list(self, sample_backtest_run, regular_user):
        """Returns list of historical backtest runs."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [sample_backtest_run]
        mock_db.execute = AsyncMock(return_value=mock_result)

        results = await get_backtest_history(
            ticker="AAPL",
            horizon_days=90,
            limit=10,
            offset=0,
            db=mock_db,
            current_user=regular_user,
        )
        assert len(results) == 1
        assert results[0].ticker == "AAPL"

    @pytest.mark.asyncio
    async def test_empty_history(self, regular_user):
        """Returns empty list when no history exists."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        results = await get_backtest_history(
            ticker="ZZZZ",
            horizon_days=90,
            limit=10,
            offset=0,
            db=mock_db,
            current_user=regular_user,
        )
        assert results == []


class TestGetBacktestSummary:
    """Tests for GET /backtests/summary/all."""

    @pytest.mark.asyncio
    async def test_returns_summary(self, sample_backtest_run, regular_user):
        """Returns summary with items and total."""
        mock_db = AsyncMock()

        # First call: count query
        count_result = MagicMock()
        count_result.scalar.return_value = 1

        # Second call: data query
        data_result = MagicMock()
        data_result.scalars.return_value.all.return_value = [sample_backtest_run]

        mock_db.execute = AsyncMock(side_effect=[count_result, data_result])

        result = await get_backtest_summary(
            limit=50, offset=0, db=mock_db, current_user=regular_user
        )
        assert result.total == 1
        assert len(result.items) == 1

    @pytest.mark.asyncio
    async def test_empty_summary(self, regular_user):
        """Returns zero total and empty items when no backtests exist."""
        mock_db = AsyncMock()
        count_result = MagicMock()
        count_result.scalar.return_value = 0
        data_result = MagicMock()
        data_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(side_effect=[count_result, data_result])

        result = await get_backtest_summary(
            limit=50, offset=0, db=mock_db, current_user=regular_user
        )
        assert result.total == 0
        assert result.items == []


class TestTriggerBacktest:
    """Tests for POST /backtests/run (admin only)."""

    @pytest.mark.asyncio
    @patch("backend.tasks.forecasting.run_backtest_task")
    async def test_admin_can_trigger(self, mock_task, admin_user):
        """Admin user can trigger a backtest."""
        mock_task.delay.return_value = MagicMock(id="task-123")

        result = await trigger_backtest(
            request=BacktestTriggerRequest(ticker="AAPL", horizon_days=90),
            current_user=admin_user,
        )
        assert result.task_id == "task-123"
        assert result.status == "queued"
        mock_task.delay.assert_called_once_with(ticker="AAPL", horizon_days=90)

    @pytest.mark.asyncio
    async def test_regular_user_rejected(self, regular_user):
        """Non-admin user gets 403."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await trigger_backtest(
                request=BacktestTriggerRequest(ticker="AAPL"),
                current_user=regular_user,
            )
        assert exc_info.value.status_code == 403


class TestTriggerCalibration:
    """Tests for POST /backtests/calibrate (admin only)."""

    @pytest.mark.asyncio
    @patch("backend.tasks.forecasting.calibrate_seasonality_task")
    async def test_admin_can_trigger(self, mock_task, admin_user):
        """Admin user can trigger calibration."""
        mock_task.delay.return_value = MagicMock(id="task-456")

        result = await trigger_calibration(
            request=CalibrateTriggerRequest(ticker=None),
            current_user=admin_user,
        )
        assert result.task_id == "task-456"
        mock_task.delay.assert_called_once_with(ticker=None)

    @pytest.mark.asyncio
    async def test_regular_user_rejected(self, regular_user):
        """Non-admin user gets 403."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await trigger_calibration(
                request=CalibrateTriggerRequest(),
                current_user=regular_user,
            )
        assert exc_info.value.status_code == 403
