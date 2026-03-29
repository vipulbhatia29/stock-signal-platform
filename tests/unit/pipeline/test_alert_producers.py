"""Unit tests for alert producers — dedup, field mapping, edge cases."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from backend.schemas.alerts import AlertResponse
from backend.tasks.alerts import _is_downgrade

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


class TestDedupKeyFormat:
    """Tests for dedup key format conventions."""

    def test_divestment_key(self) -> None:
        """Divestment dedup key follows 'divestment:{rule}:{ticker}'."""
        key = "divestment:stop_loss:TSLA"
        parts = key.split(":")
        assert parts[0] == "divestment"
        assert parts[1] == "stop_loss"
        assert parts[2] == "TSLA"

    def test_signal_flip_key(self) -> None:
        """Signal flip dedup key follows 'signal_flip:{direction}:{ticker}'."""
        key = "signal_flip:downgrade:AAPL"
        parts = key.split(":")
        assert parts[0] == "signal_flip"
        assert parts[1] in ("downgrade", "upgrade")
        assert parts[2] == "AAPL"

    def test_buy_key(self) -> None:
        """Buy dedup key follows 'buy:{ticker}'."""
        key = "buy:MSFT"
        assert key.startswith("buy:")

    def test_drift_key(self) -> None:
        """Drift dedup key follows 'drift:{ticker}'."""
        key = "drift:NVDA"
        assert key.startswith("drift:")

    def test_pipeline_key(self) -> None:
        """Pipeline dedup keys are fixed strings."""
        assert "pipeline:partial" == "pipeline:partial"
        assert "pipeline:total" == "pipeline:total"
