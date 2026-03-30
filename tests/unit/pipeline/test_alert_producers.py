"""Unit tests for alert producers — dedup, field mapping, edge cases."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from backend.schemas.alerts import AlertResponse
from backend.tasks.alerts import _create_alert, _is_downgrade

# ---------------------------------------------------------------------------
# AlertResponse schema validation
# ---------------------------------------------------------------------------


class TestAlertResponseSchema:
    """Tests for AlertResponse Pydantic schema with new fields."""

    def test_includes_severity_title_ticker(self) -> None:
        """AlertResponse must include severity, title, ticker."""
        resp = AlertResponse(
            id=uuid.uuid4(),
            alert_type="divestment",
            severity="critical",
            title="Stop-Loss Triggered",
            ticker="TSLA",
            message="Down 18%",
            is_read=False,
            created_at=datetime.now(timezone.utc),
        )
        assert resp.severity == "critical"
        assert resp.title == "Stop-Loss Triggered"
        assert resp.ticker == "TSLA"

    def test_rejects_invalid_severity(self) -> None:
        """Literal type should reject typos like 'critcal'."""
        with pytest.raises(ValidationError):
            AlertResponse(
                id=uuid.uuid4(),
                alert_type="test",
                severity="critcal",
                title="Test",
                ticker=None,
                message="test",
                is_read=False,
                created_at=datetime.now(timezone.utc),
            )

    def test_allows_null_ticker(self) -> None:
        """Pipeline alerts have no ticker."""
        resp = AlertResponse(
            id=uuid.uuid4(),
            alert_type="pipeline",
            severity="warning",
            title="Pipeline Issue",
            ticker=None,
            message="Partial failure",
            is_read=False,
            created_at=datetime.now(timezone.utc),
        )
        assert resp.ticker is None

    def test_all_severity_values_accepted(self) -> None:
        """All three severity values should be valid."""
        for sev in ("critical", "warning", "info"):
            resp = AlertResponse(
                id=uuid.uuid4(),
                alert_type="test",
                severity=sev,
                title="Test",
                ticker=None,
                message="test",
                is_read=False,
                created_at=datetime.now(timezone.utc),
            )
            assert resp.severity == sev


# ---------------------------------------------------------------------------
# _is_downgrade helper
# ---------------------------------------------------------------------------


class TestIsDowngrade:
    """Tests for the _is_downgrade helper function."""

    def test_buy_to_watch_is_downgrade(self) -> None:
        """BUY→WATCH is a downgrade."""
        assert _is_downgrade("BUY", "WATCH") is True

    def test_buy_to_avoid_is_downgrade(self) -> None:
        """BUY→AVOID is a downgrade."""
        assert _is_downgrade("BUY", "AVOID") is True

    def test_watch_to_avoid_is_downgrade(self) -> None:
        """WATCH→AVOID is a downgrade."""
        assert _is_downgrade("WATCH", "AVOID") is True

    def test_avoid_to_buy_is_upgrade(self) -> None:
        """AVOID→BUY is not a downgrade."""
        assert _is_downgrade("AVOID", "BUY") is False

    def test_watch_to_buy_is_upgrade(self) -> None:
        """WATCH→BUY is not a downgrade."""
        assert _is_downgrade("WATCH", "BUY") is False

    def test_same_action_is_not_downgrade(self) -> None:
        """Same action is not a downgrade."""
        assert _is_downgrade("WATCH", "WATCH") is False

    def test_unknown_action_defaults_to_zero(self) -> None:
        """Unknown actions get rank 0 via .get() default."""
        assert _is_downgrade("BUY", "UNKNOWN") is True
        assert _is_downgrade("UNKNOWN", "BUY") is False


# ---------------------------------------------------------------------------
# Dedup key format
# ---------------------------------------------------------------------------


class TestCreateAlertDedupKeys:
    """Tests that _create_alert sets correct dedup_key on InAppAlert."""

    @pytest.mark.asyncio
    async def test_create_alert_sets_dedup_key(self) -> None:
        """_create_alert should pass dedup_key to InAppAlert."""
        from unittest.mock import MagicMock

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)
        uid = uuid.uuid4()
        result = await _create_alert(
            db,
            alert_type="divestment",
            message="Down 18%",
            user_id=uid,
            severity="critical",
            title="Stop-Loss Triggered",
            ticker="TSLA",
            dedup_key="divestment:stop_loss:TSLA",
        )
        assert result is True
        added_alert = db.add.call_args[0][0]
        assert added_alert.dedup_key == "divestment:stop_loss:TSLA"
        assert added_alert.severity == "critical"
        assert added_alert.title == "Stop-Loss Triggered"
        assert added_alert.ticker == "TSLA"

    @pytest.mark.asyncio
    async def test_create_alert_without_dedup_key(self) -> None:
        """_create_alert without dedup_key should still create alert."""
        db = AsyncMock()
        uid = uuid.uuid4()
        result = await _create_alert(
            db,
            alert_type="test",
            message="Test",
            user_id=uid,
        )
        assert result is True
        added_alert = db.add.call_args[0][0]
        assert added_alert.dedup_key is None
        assert added_alert.severity == "info"

    @pytest.mark.asyncio
    async def test_create_alert_skips_if_dedup_exists(self) -> None:
        """_create_alert should return False if dedup match found."""
        db = AsyncMock()
        uid = uuid.uuid4()
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.return_value = uid
        db.execute = AsyncMock(return_value=mock_result)

        result = await _create_alert(
            db,
            alert_type="divestment",
            message="Down 18%",
            user_id=uid,
            dedup_key="divestment:stop_loss:TSLA",
        )
        assert result is False
        db.add.assert_not_called()
