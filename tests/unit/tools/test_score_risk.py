"""Tests for _score_risk() with QuantStats enhancement."""

import pytest

from backend.tools.portfolio_health import _score_risk


class TestScoreRisk:
    """Tests for the enhanced _score_risk with Sortino/drawdown inputs."""

    def test_sharpe_only_when_no_quantstats(self):
        """None sortino/drawdown → Sharpe-only scoring."""
        assert _score_risk(1.5) == 10.0
        assert _score_risk(0.0) == 0.0
        assert _score_risk(0.75) == pytest.approx(5.0, abs=0.1)

    def test_negative_sharpe_floors_at_zero(self):
        """Negative Sharpe → 0 score."""
        assert _score_risk(-0.5) == 0.0

    def test_three_param_combines_all(self):
        """Three inputs → blended score."""
        score = _score_risk(1.0, 1.5, 0.10)
        assert 0 <= score <= 10

    def test_high_drawdown_lowers_score(self):
        """High drawdown should reduce risk score."""
        low_dd = _score_risk(1.0, 1.0, 0.05)
        high_dd = _score_risk(1.0, 1.0, 0.25)
        assert low_dd > high_dd

    def test_high_sortino_boosts_score(self):
        """High sortino should increase risk score."""
        low_sort = _score_risk(1.0, 0.5, 0.10)
        high_sort = _score_risk(1.0, 2.0, 0.10)
        assert high_sort > low_sort

    def test_none_sortino_only_drawdown_uses_three_way(self):
        """None sortino but non-None drawdown → uses 3-way with 0 sortino."""
        score = _score_risk(1.0, None, 0.10)
        # When sortino is None but drawdown is not, still 3-way
        assert 0 <= score <= 10

    def test_zero_values_are_valid_not_sentinel(self):
        """sortino=0.0 and drawdown=0.0 are valid, not treated as 'no data'."""
        # With explicit 0.0 values, should use 3-way blend (not Sharpe-only)
        three_way = _score_risk(1.5, 0.0, 0.0)
        sharpe_only = _score_risk(1.5)
        # 3-way with sortino=0 gets lower score than Sharpe-only at 10.0
        assert three_way < sharpe_only
