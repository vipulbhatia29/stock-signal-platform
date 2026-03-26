"""Tests for portfolio health score computation."""


class TestHealthScoreComponents:
    """Tests for individual score component calculations."""

    def test_hhi_score_well_diversified(self) -> None:
        """HHI < 500 should score 10."""
        from backend.tools.portfolio_health import _score_diversification

        assert _score_diversification(400) == 10.0

    def test_hhi_score_concentrated(self) -> None:
        """HHI > 2500 should score 0."""
        from backend.tools.portfolio_health import _score_diversification

        assert _score_diversification(3000) == 0.0

    def test_hhi_score_moderate(self) -> None:
        """HHI between 500-2500 should score linearly."""
        from backend.tools.portfolio_health import _score_diversification

        score = _score_diversification(1500)
        assert 0 < score < 10

    def test_sharpe_score_excellent(self) -> None:
        """Sharpe > 1.5 should score 10."""
        from backend.tools.portfolio_health import _score_risk

        assert _score_risk(2.0) == 10.0

    def test_sharpe_score_negative(self) -> None:
        """Sharpe < 0 should score 0."""
        from backend.tools.portfolio_health import _score_risk

        assert _score_risk(-0.5) == 0.0

    def test_sharpe_score_moderate(self) -> None:
        """Sharpe 0.75 should score ~5."""
        from backend.tools.portfolio_health import _score_risk

        score = _score_risk(0.75)
        assert 4.0 <= score <= 6.0

    def test_yield_score_optimal(self) -> None:
        """Yield 2-4% should score 10."""
        from backend.tools.portfolio_health import _score_income

        assert _score_income(0.03) == 10.0

    def test_yield_score_zero(self) -> None:
        """Yield 0% should score 3 (not terrible, just no income)."""
        from backend.tools.portfolio_health import _score_income

        assert _score_income(0.0) == 3.0

    def test_yield_score_high(self) -> None:
        """Yield > 8% should score 5 (suspiciously high)."""
        from backend.tools.portfolio_health import _score_income

        assert _score_income(0.10) == 5.0

    def test_sector_balance_good(self) -> None:
        """Max sector < 25% should score 10."""
        from backend.tools.portfolio_health import _score_sector_balance

        assert _score_sector_balance(20.0) == 10.0

    def test_sector_balance_concentrated(self) -> None:
        """Max sector > 50% should score 0."""
        from backend.tools.portfolio_health import _score_sector_balance

        assert _score_sector_balance(55.0) == 0.0

    def test_sector_balance_moderate(self) -> None:
        """Max sector 37.5% should score ~5."""
        from backend.tools.portfolio_health import _score_sector_balance

        assert _score_sector_balance(37.5) == 5.0


class TestGradeAssignment:
    """Tests for score-to-grade mapping."""

    def test_grade_a_plus(self) -> None:
        """Score >= 9.5 should be A+."""
        from backend.tools.portfolio_health import _score_to_grade

        assert _score_to_grade(9.7) == "A+"

    def test_grade_b(self) -> None:
        """Score 7.0-7.4 should be B."""
        from backend.tools.portfolio_health import _score_to_grade

        assert _score_to_grade(7.2) == "B"

    def test_grade_f(self) -> None:
        """Score < 3.0 should be F."""
        from backend.tools.portfolio_health import _score_to_grade

        assert _score_to_grade(2.5) == "F"


class TestCompositeHealth:
    """Tests for weighted composite calculation."""

    def test_all_perfect_scores_10(self) -> None:
        """All component scores at 10 should give composite 10."""
        from backend.tools.portfolio_health import _compute_composite

        components = {
            "diversification": 10.0,
            "signal_quality": 10.0,
            "risk": 10.0,
            "income": 10.0,
            "sector_balance": 10.0,
        }
        assert _compute_composite(components) == 10.0

    def test_all_zero_scores_0(self) -> None:
        """All component scores at 0 should give composite 0."""
        from backend.tools.portfolio_health import _compute_composite

        components = {
            "diversification": 0.0,
            "signal_quality": 0.0,
            "risk": 0.0,
            "income": 0.0,
            "sector_balance": 0.0,
        }
        assert _compute_composite(components) == 0.0

    def test_mixed_scores(self) -> None:
        """Mixed scores should compute weighted average."""
        from backend.tools.portfolio_health import _compute_composite

        components = {
            "diversification": 8.0,
            "signal_quality": 6.0,
            "risk": 7.0,
            "income": 5.0,
            "sector_balance": 9.0,
        }
        result = _compute_composite(components)
        assert 6.0 < result < 8.0
