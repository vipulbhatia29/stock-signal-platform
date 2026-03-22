"""Unit tests for the divestment rules engine."""

import pytest

from backend.tools.divestment import check_divestment_rules
from tests.conftest import UserPreferenceFactory


class TestCheckDivestmentRules:
    """Tests for the pure check_divestment_rules function."""

    @pytest.fixture
    def default_prefs(self):
        """UserPreference with default thresholds."""
        return UserPreferenceFactory.build(
            default_stop_loss_pct=20.0,
            max_position_pct=5.0,
            max_sector_pct=30.0,
        )

    @pytest.fixture
    def healthy_position(self):
        """Position within all limits — no alerts expected."""
        return {
            "ticker": "AAPL",
            "unrealized_pnl_pct": 5.0,
            "allocation_pct": 3.0,
            "sector": "Technology",
        }

    @pytest.fixture
    def sector_allocations(self):
        """Sector allocations where Technology is under limit."""
        return [
            {"sector": "Technology", "pct": 25.0},
            {"sector": "Healthcare", "pct": 15.0},
        ]

    @pytest.fixture
    def healthy_signal(self):
        """Signal with a composite score above threshold."""
        return {"composite_score": 7.0}

    def test_no_alerts_healthy_position(
        self, default_prefs, healthy_position, sector_allocations, healthy_signal
    ):
        """A position within all limits should produce zero alerts."""
        alerts = check_divestment_rules(
            healthy_position, sector_allocations, healthy_signal, default_prefs
        )
        assert alerts == []

    def test_stop_loss_fires(self, default_prefs, sector_allocations, healthy_signal):
        """P&L below stop-loss threshold should produce a critical alert."""
        position = {
            "ticker": "TSLA",
            "unrealized_pnl_pct": -23.4,
            "allocation_pct": 3.0,
            "sector": "Technology",
        }
        alerts = check_divestment_rules(position, sector_allocations, healthy_signal, default_prefs)
        stop_loss = [a for a in alerts if a["rule"] == "stop_loss"]
        assert len(stop_loss) == 1
        assert stop_loss[0]["severity"] == "critical"
        assert stop_loss[0]["value"] == -23.4
        assert stop_loss[0]["threshold"] == 20.0

    def test_stop_loss_at_boundary(self, default_prefs, sector_allocations, healthy_signal):
        """Exactly at stop-loss threshold (<=) should fire the alert."""
        position = {
            "ticker": "TSLA",
            "unrealized_pnl_pct": -20.0,
            "allocation_pct": 3.0,
            "sector": "Technology",
        }
        alerts = check_divestment_rules(position, sector_allocations, healthy_signal, default_prefs)
        stop_loss = [a for a in alerts if a["rule"] == "stop_loss"]
        assert len(stop_loss) == 1

    def test_position_concentration_fires(self, default_prefs, sector_allocations, healthy_signal):
        """Allocation above max_position_pct should produce a warning."""
        position = {
            "ticker": "AAPL",
            "unrealized_pnl_pct": 5.0,
            "allocation_pct": 7.2,
            "sector": "Technology",
        }
        alerts = check_divestment_rules(position, sector_allocations, healthy_signal, default_prefs)
        conc = [a for a in alerts if a["rule"] == "position_concentration"]
        assert len(conc) == 1
        assert conc[0]["severity"] == "warning"
        assert conc[0]["value"] == 7.2
        assert conc[0]["threshold"] == 5.0

    def test_sector_concentration_fires(self, default_prefs, healthy_signal):
        """Sector above max_sector_pct should produce a warning."""
        position = {
            "ticker": "AAPL",
            "unrealized_pnl_pct": 5.0,
            "allocation_pct": 3.0,
            "sector": "Technology",
        }
        sector_allocs = [{"sector": "Technology", "pct": 35.1}]
        alerts = check_divestment_rules(position, sector_allocs, healthy_signal, default_prefs)
        sector = [a for a in alerts if a["rule"] == "sector_concentration"]
        assert len(sector) == 1
        assert sector[0]["severity"] == "warning"
        assert "35.1%" in sector[0]["message"]

    def test_weak_composite_fires(self, default_prefs, sector_allocations):
        """Composite score < 3 should produce a warning."""
        position = {
            "ticker": "F",
            "unrealized_pnl_pct": 2.0,
            "allocation_pct": 3.0,
            "sector": "Consumer Cyclical",
        }
        signal = {"composite_score": 1.8}
        alerts = check_divestment_rules(position, sector_allocations, signal, default_prefs)
        weak = [a for a in alerts if a["rule"] == "weak_fundamentals"]
        assert len(weak) == 1
        assert weak[0]["severity"] == "warning"
        assert weak[0]["value"] == 1.8

    def test_multiple_alerts_stack(self, default_prefs):
        """A position violating 3 rules should produce 3 alerts."""
        position = {
            "ticker": "DANGER",
            "unrealized_pnl_pct": -25.0,
            "allocation_pct": 8.0,
            "sector": "Energy",
        }
        sector_allocs = [{"sector": "Energy", "pct": 40.0}]
        signal = {"composite_score": 2.0}
        alerts = check_divestment_rules(position, sector_allocs, signal, default_prefs)
        rules = {a["rule"] for a in alerts}
        assert "stop_loss" in rules
        assert "position_concentration" in rules
        assert "sector_concentration" in rules
        # weak_fundamentals would make 4, but sector is Energy not in the
        # original sector_allocations fixture — we use inline one here
        assert len(alerts) == 4  # all 4 fire

    def test_null_signal_skips_fundamentals(self, default_prefs, sector_allocations):
        """When signal is None, no fundamentals alert should fire."""
        position = {
            "ticker": "NEWCO",
            "unrealized_pnl_pct": 5.0,
            "allocation_pct": 3.0,
            "sector": "Technology",
        }
        alerts = check_divestment_rules(position, sector_allocations, None, default_prefs)
        assert all(a["rule"] != "weak_fundamentals" for a in alerts)

    def test_custom_thresholds(self):
        """Non-default prefs should change which alerts fire."""
        prefs = UserPreferenceFactory.build(
            default_stop_loss_pct=10.0,
            max_position_pct=3.0,
            max_sector_pct=20.0,
        )
        position = {
            "ticker": "AAPL",
            "unrealized_pnl_pct": -12.0,
            "allocation_pct": 4.0,
            "sector": "Technology",
        }
        sector_allocs = [{"sector": "Technology", "pct": 25.0}]
        signal = {"composite_score": 5.0}
        alerts = check_divestment_rules(position, sector_allocs, signal, prefs)
        rules = {a["rule"] for a in alerts}
        assert "stop_loss" in rules  # -12% <= -10%
        assert "position_concentration" in rules  # 4% > 3%
        assert "sector_concentration" in rules  # 25% > 20%
        assert "weak_fundamentals" not in rules  # 5.0 >= 3

    def test_null_pnl_skips_stop_loss(self, default_prefs, sector_allocations, healthy_signal):
        """When unrealized_pnl_pct is None, stop-loss should not fire."""
        position = {
            "ticker": "AAPL",
            "unrealized_pnl_pct": None,
            "allocation_pct": 3.0,
            "sector": "Technology",
        }
        alerts = check_divestment_rules(position, sector_allocations, healthy_signal, default_prefs)
        assert all(a["rule"] != "stop_loss" for a in alerts)

    def test_null_allocation_skips_concentration(
        self, default_prefs, sector_allocations, healthy_signal
    ):
        """When allocation_pct is None, position concentration should not fire."""
        position = {
            "ticker": "AAPL",
            "unrealized_pnl_pct": 5.0,
            "allocation_pct": None,
            "sector": "Technology",
        }
        alerts = check_divestment_rules(position, sector_allocations, healthy_signal, default_prefs)
        assert all(a["rule"] != "position_concentration" for a in alerts)
