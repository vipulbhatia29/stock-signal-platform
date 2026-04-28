"""Unit tests for alert generation and alert API schemas."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.schemas.alerts import (
    AlertListResponse,
    AlertResponse,
    BatchReadRequest,
    UnreadCountResponse,
)
from backend.tasks.alerts import _create_alert, _generate_alerts_async
from tests.unit.tasks._tracked_helper_bypass import bypass_tracked

# ---------------------------------------------------------------------------
# Alert generation
# ---------------------------------------------------------------------------


class TestAlertGeneration:
    """Tests for _generate_alerts_async."""

    @pytest.mark.asyncio
    @patch("backend.tasks.alerts._cleanup_old_read_alerts", new_callable=AsyncMock, return_value=0)
    @patch("backend.tasks.alerts._alert_divestment_rules", new_callable=AsyncMock, return_value=0)
    @patch("backend.tasks.alerts._alert_signal_flips", new_callable=AsyncMock, return_value=0)
    @patch(
        "backend.tasks.alerts._alert_new_buy_recommendations",
        new_callable=AsyncMock,
        return_value=2,
    )
    @patch("backend.database.async_session_factory")
    async def test_creates_alerts_for_buys(
        self, mock_factory, mock_buys, mock_flips, mock_divest, mock_cleanup
    ) -> None:
        """Should create alerts for new BUY recommendations."""
        mock_session = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value = mock_cm

        result = await bypass_tracked(_generate_alerts_async)(run_id=uuid.uuid4())

        assert result["alerts_created"] == 2
        mock_buys.assert_called_once()

    @pytest.mark.asyncio
    @patch("backend.tasks.alerts._cleanup_old_read_alerts", new_callable=AsyncMock, return_value=0)
    @patch("backend.tasks.alerts._alert_divestment_rules", new_callable=AsyncMock, return_value=0)
    @patch("backend.tasks.alerts._alert_signal_flips", new_callable=AsyncMock, return_value=0)
    @patch(
        "backend.tasks.alerts._alert_new_buy_recommendations",
        new_callable=AsyncMock,
        return_value=0,
    )
    @patch("backend.database.async_session_factory")
    async def test_drift_alerts_from_context(
        self, mock_factory, mock_buys, mock_flips, mock_divest, mock_cleanup
    ) -> None:
        """Should create drift alerts from pipeline context."""
        mock_session = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value = mock_cm

        with patch("backend.tasks.alerts._create_alert", new_callable=AsyncMock, return_value=True):
            result = await bypass_tracked(_generate_alerts_async)(
                {"degraded": ["AAPL", "TSLA"]}, run_id=uuid.uuid4()
            )

        assert result["alerts_created"] == 2

    @pytest.mark.asyncio
    @patch("backend.tasks.alerts._cleanup_old_read_alerts", new_callable=AsyncMock, return_value=0)
    @patch("backend.tasks.alerts._alert_divestment_rules", new_callable=AsyncMock, return_value=0)
    @patch("backend.tasks.alerts._alert_signal_flips", new_callable=AsyncMock, return_value=0)
    @patch(
        "backend.tasks.alerts._alert_new_buy_recommendations",
        new_callable=AsyncMock,
        return_value=0,
    )
    @patch("backend.database.async_session_factory")
    async def test_pipeline_failure_alert(
        self, mock_factory, mock_buys, mock_flips, mock_divest, mock_cleanup
    ) -> None:
        """Should create alert for pipeline partial failures."""
        mock_session = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value = mock_cm

        with patch("backend.tasks.alerts._create_alert", new_callable=AsyncMock, return_value=True):
            result = await bypass_tracked(_generate_alerts_async)(
                {"price_refresh": {"status": "partial"}}, run_id=uuid.uuid4()
            )

        assert result["alerts_created"] == 1


# ---------------------------------------------------------------------------
# Alert metadata for deep-linking
# ---------------------------------------------------------------------------


class TestAlertMetadata:
    """Tests for alert metadata deep-linking."""

    @pytest.mark.asyncio
    async def test_drift_alert_metadata(self) -> None:
        """Drift alert metadata should include ticker and route."""
        db = AsyncMock()
        await _create_alert(
            db,
            alert_type="drift",
            message="AAPL degraded",
            metadata_={"ticker": "AAPL", "route": "/stocks/AAPL"},
            user_id=uuid.uuid4(),
        )
        db.add.assert_called_once()
        added = db.add.call_args[0][0]
        assert added.metadata_["ticker"] == "AAPL"
        assert added.metadata_["route"] == "/stocks/AAPL"

    @pytest.mark.asyncio
    async def test_system_alert_creates_for_all_users(self) -> None:
        """System alert (no user_id) should create one alert per user."""
        db = AsyncMock()
        users_result = MagicMock()
        users_result.all.return_value = [(uuid.uuid4(),), (uuid.uuid4(),), (uuid.uuid4(),)]
        db.execute = AsyncMock(return_value=users_result)

        await _create_alert(
            db,
            alert_type="pipeline",
            message="System alert",
            user_id=None,
        )

        assert db.add.call_count == 3


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


class TestAlertSchemas:
    """Tests for alert Pydantic schemas."""

    def test_alert_response(self) -> None:
        """AlertResponse should serialize all fields."""
        alert = AlertResponse(
            id=uuid.uuid4(),
            alert_type="signal_change",
            severity="info",
            title="Score Upgrade",
            ticker="AAPL",
            message="AAPL BUY signal",
            metadata={"ticker": "AAPL"},
            is_read=False,
            created_at=datetime.now(timezone.utc),
        )
        assert alert.alert_type == "signal_change"
        assert alert.severity == "info"
        assert alert.title == "Score Upgrade"
        assert alert.ticker == "AAPL"
        assert alert.is_read is False

    def test_alert_list_response(self) -> None:
        """AlertListResponse should include total and unread count."""
        resp = AlertListResponse(alerts=[], total=5, unread_count=3)
        assert resp.total == 5
        assert resp.unread_count == 3

    def test_batch_read_request(self) -> None:
        """BatchReadRequest should accept list of UUIDs."""
        ids = [uuid.uuid4(), uuid.uuid4()]
        req = BatchReadRequest(alert_ids=ids)
        assert len(req.alert_ids) == 2

    def test_unread_count_response(self) -> None:
        """UnreadCountResponse should have count field."""
        resp = UnreadCountResponse(unread_count=7)
        assert resp.unread_count == 7
