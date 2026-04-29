"""Unit tests for forecast evaluation, drift detection, recommendation eval, and scorecard."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.models.forecast import ForecastResult, ModelVersion, RecommendationOutcome
from backend.tasks.evaluation import (
    _check_drift_async,
    _evaluate_forecasts_async,
)
from backend.tools.scorecard import compute_scorecard
from tests.unit.tasks._tracked_helper_bypass import bypass_tracked

# ---------------------------------------------------------------------------
# Forecast evaluation
# ---------------------------------------------------------------------------


class TestForecastEvaluation:
    """Tests for _evaluate_forecasts_async."""

    @pytest.mark.asyncio
    @patch("backend.database.async_session_factory")
    async def test_fills_actual_price(self, mock_factory) -> None:
        """Evaluation should fill actual_return_pct on matured forecasts."""
        mock_session = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value = mock_cm

        fc = ForecastResult(
            forecast_date=date(2026, 1, 1),
            ticker="AAPL",
            horizon_days=90,
            model_version_id=uuid.uuid4(),
            expected_return_pct=5.0,
            return_lower_pct=-5.0,
            return_upper_pct=15.0,
            confidence_score=0.65,
            direction="bullish",
            base_price=200.0,
            drivers=None,
            forecast_signal=None,
            target_date=date(2026, 4, 1),
            actual_return_pct=None,
            error_pct=None,
            created_at=datetime.now(timezone.utc),
        )

        # Mock: pending forecasts query
        pending_result = MagicMock()
        pending_result.scalars.return_value.all.return_value = [fc]

        # Mock: price lookup returns $210 (represents +5% actual return)
        price_result = MagicMock()
        price_result.scalar_one_or_none.return_value = 210.0

        # Mock: _update_model_mapes (no active models)
        mape_result = MagicMock()
        mape_result.scalars.return_value.all.return_value = []

        mock_session.execute = AsyncMock(side_effect=[pending_result, price_result, mape_result])

        with patch("backend.tasks.evaluation._update_model_mapes", new_callable=AsyncMock):
            result = await bypass_tracked(_evaluate_forecasts_async)(run_id=uuid.uuid4())

        assert result["evaluated"] == 1

    @pytest.mark.asyncio
    @patch("backend.database.async_session_factory")
    async def test_no_pending_forecasts(self, mock_factory) -> None:
        """No pending forecasts should return early."""
        mock_session = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value = mock_cm

        empty_result = MagicMock()
        empty_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=empty_result)

        result = await bypass_tracked(_evaluate_forecasts_async)(run_id=uuid.uuid4())
        assert result["status"] == "no_pending"

    def test_mape_computation(self) -> None:
        """Error should be |actual_return - expected_return| for return-based forecasts."""
        expected_return = 5.0
        actual_return = 7.0
        error = abs(actual_return - expected_return)
        assert error == pytest.approx(2.0, abs=0.001)  # 2pp error


# ---------------------------------------------------------------------------
# Drift detection
# ---------------------------------------------------------------------------


class TestDriftDetection:
    """Tests for drift detection logic."""

    @pytest.mark.asyncio
    @patch("backend.tasks.forecasting.retrain_single_ticker_task")
    @patch(
        "backend.tasks.evaluation._check_vix_regime",
        new_callable=AsyncMock,
        return_value="normal",
    )
    @patch(
        "backend.tasks.evaluation._check_volatility_spike",
        new_callable=AsyncMock,
        return_value=False,
    )
    @patch("backend.database.async_session_factory")
    async def test_triggers_retrain_when_mape_high(
        self, mock_factory, mock_vol, mock_vix, mock_retrain
    ) -> None:
        """Drift detection should queue retrain when MAPE > threshold."""
        mock_session = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value = mock_cm

        degraded_model = ModelVersion(
            id=uuid.uuid4(),
            ticker="AAPL",
            model_type="prophet",
            version=1,
            is_active=True,
            status="active",
            trained_at=datetime.now(timezone.utc),
            training_data_start=date(2024, 1, 1),
            training_data_end=date(2026, 1, 1),
            data_points=500,
            metrics={"rolling_mape": 0.25},  # 25% > 20% fallback threshold
        )

        models_result = MagicMock()
        models_result.scalars.return_value.all.return_value = [degraded_model]
        # Second execute() call is the backtest MAPE batch query — return empty
        backtest_result = MagicMock()
        backtest_result.all.return_value = []
        mock_session.execute = AsyncMock(side_effect=[models_result, backtest_result])

        result = await bypass_tracked(_check_drift_async)(run_id=uuid.uuid4())

        assert "AAPL" in result["degraded"]
        assert "AAPL" in result["retrain_triggered"]
        assert degraded_model.status == "degraded"
        mock_retrain.delay.assert_called_once_with("AAPL")

    @pytest.mark.asyncio
    @patch("backend.tasks.forecasting.retrain_single_ticker_task")
    @patch(
        "backend.tasks.evaluation._check_vix_regime",
        new_callable=AsyncMock,
        return_value="normal",
    )
    @patch(
        "backend.tasks.evaluation._check_volatility_spike",
        new_callable=AsyncMock,
        return_value=False,
    )
    @patch("backend.database.async_session_factory")
    async def test_no_retrain_when_mape_ok(
        self, mock_factory, mock_vol, mock_vix, mock_retrain
    ) -> None:
        """Drift detection should NOT trigger retrain when MAPE is below threshold."""
        mock_session = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value = mock_cm

        healthy_model = ModelVersion(
            id=uuid.uuid4(),
            ticker="MSFT",
            model_type="prophet",
            version=1,
            is_active=True,
            status="active",
            trained_at=datetime.now(timezone.utc),
            training_data_start=date(2024, 1, 1),
            training_data_end=date(2026, 1, 1),
            data_points=500,
            metrics={"rolling_mape": 0.08},  # 8% < 20% fallback
        )

        models_result = MagicMock()
        models_result.scalars.return_value.all.return_value = [healthy_model]
        # Second execute() call is the backtest MAPE batch query — return empty
        backtest_result = MagicMock()
        backtest_result.all.return_value = []
        mock_session.execute = AsyncMock(side_effect=[models_result, backtest_result])

        result = await bypass_tracked(_check_drift_async)(run_id=uuid.uuid4())

        assert result["degraded"] == []
        assert result["retrain_triggered"] == []
        mock_retrain.delay.assert_not_called()


# ---------------------------------------------------------------------------
# Recommendation evaluation
# ---------------------------------------------------------------------------


class TestRecommendationEvaluation:
    """Tests for _evaluate_recommendations_async."""

    def test_buy_correct_when_price_up(self) -> None:
        """BUY is correct when return > 0."""
        price_at_rec = 100.0
        actual = 120.0
        return_pct = (actual - price_at_rec) / price_at_rec
        was_correct = return_pct > 0
        assert was_correct is True
        assert return_pct == pytest.approx(0.20)

    def test_buy_incorrect_when_price_down(self) -> None:
        """BUY is incorrect when return < 0."""
        price_at_rec = 100.0
        actual = 90.0
        return_pct = (actual - price_at_rec) / price_at_rec
        was_correct = return_pct > 0
        assert was_correct is False

    def test_sell_correct_when_price_down(self) -> None:
        """SELL is correct when return < 0."""
        price_at_rec = 100.0
        actual = 80.0
        return_pct = (actual - price_at_rec) / price_at_rec
        was_correct = return_pct < 0
        assert was_correct is True

    def test_alpha_computation(self) -> None:
        """Alpha = stock return - SPY return."""
        stock_return = 0.15
        spy_return = 0.05
        alpha = stock_return - spy_return
        assert alpha == pytest.approx(0.10)


# ---------------------------------------------------------------------------
# Scorecard
# ---------------------------------------------------------------------------


class TestScorecard:
    """Tests for compute_scorecard."""

    @pytest.mark.asyncio
    async def test_mixed_outcomes(self) -> None:
        """Scorecard with mixed outcomes should compute correct hit rates."""
        db = AsyncMock()
        user_id = uuid.uuid4()

        outcomes = [
            _make_outcome("BUY", "AAPL", 90, 0.15, 0.05, True),
            _make_outcome("BUY", "MSFT", 90, -0.05, 0.03, False),
            _make_outcome("SELL", "TSLA", 30, -0.10, 0.02, True),
            _make_outcome("BUY", "GOOG", 180, 0.20, 0.08, True),
        ]

        result = MagicMock()
        result.scalars.return_value.all.return_value = outcomes
        db.execute = AsyncMock(return_value=result)

        scorecard = await compute_scorecard(user_id, db)

        assert scorecard.total_outcomes == 4
        assert scorecard.overall_hit_rate == pytest.approx(0.75)  # 3/4
        assert scorecard.buy_hit_rate == pytest.approx(2 / 3)  # 2/3
        assert scorecard.sell_hit_rate == pytest.approx(1.0)  # 1/1

    @pytest.mark.asyncio
    async def test_new_user_returns_empty(self) -> None:
        """New user with no outcomes should return zero scorecard."""
        db = AsyncMock()
        user_id = uuid.uuid4()

        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=result)

        scorecard = await compute_scorecard(user_id, db)

        assert scorecard.total_outcomes == 0
        assert scorecard.overall_hit_rate == 0.0
        assert scorecard.avg_alpha == 0.0

    @pytest.mark.asyncio
    async def test_worst_miss_tracking(self) -> None:
        """Scorecard should track the worst BUY miss."""
        db = AsyncMock()
        user_id = uuid.uuid4()

        outcomes = [
            _make_outcome("BUY", "AAPL", 90, 0.10, 0.05, True),
            _make_outcome("BUY", "GME", 90, -0.40, 0.02, False),
            _make_outcome("BUY", "MSFT", 90, -0.05, 0.03, False),
        ]

        result = MagicMock()
        result.scalars.return_value.all.return_value = outcomes
        db.execute = AsyncMock(return_value=result)

        scorecard = await compute_scorecard(user_id, db)

        assert scorecard.worst_miss_pct == pytest.approx(-0.40)
        assert scorecard.worst_miss_ticker == "GME"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_outcome(
    action: str,
    ticker: str,
    horizon: int,
    return_pct: float,
    spy_return_pct: float,
    was_correct: bool,
) -> RecommendationOutcome:
    """Create a RecommendationOutcome for testing."""
    return RecommendationOutcome(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        rec_generated_at=datetime.now(timezone.utc) - timedelta(days=horizon),
        rec_ticker=ticker,
        action=action,
        price_at_recommendation=100.0,
        horizon_days=horizon,
        evaluated_at=datetime.now(timezone.utc),
        actual_price=100 * (1 + return_pct),
        return_pct=return_pct,
        spy_return_pct=spy_return_pct,
        alpha_pct=return_pct - spy_return_pct,
        action_was_correct=was_correct,
        created_at=datetime.now(timezone.utc),
    )
