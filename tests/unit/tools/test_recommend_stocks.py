"""Tests for multi-signal recommendation engine."""


class TestConsensusScoring:
    """Tests for multi-source consensus scoring."""

    def test_four_source_consensus_scores_highest(self) -> None:
        """Candidate appearing in all 4 sources should score highest."""
        from backend.tools.recommend_stocks import _compute_recommendation_score

        score = _compute_recommendation_score(
            signal_score=8.5,
            fundamental_score=8.0,
            momentum_score=7.5,
            portfolio_fit_score=9.0,
        )
        assert score > 8.0

    def test_single_source_scores_lower(self) -> None:
        """Candidate from only one source should score lower."""
        from backend.tools.recommend_stocks import _compute_recommendation_score

        score = _compute_recommendation_score(
            signal_score=8.5,
            fundamental_score=0.0,
            momentum_score=0.0,
            portfolio_fit_score=0.0,
        )
        assert score < 5.0

    def test_weights_sum_to_one(self) -> None:
        """Recommendation weights should sum to 1.0."""
        from backend.tools.recommend_stocks import RECOMMENDATION_WEIGHTS

        assert abs(sum(RECOMMENDATION_WEIGHTS.values()) - 1.0) < 0.01


class TestFundamentalScoring:
    """Tests for fundamental quality scoring."""

    def test_low_pe_high_roe_scores_well(self) -> None:
        """Low P/E + high ROE should score highly."""
        from backend.tools.recommend_stocks import _score_fundamentals

        score = _score_fundamentals(forward_pe=12.0, return_on_equity=0.25, piotroski=8)
        assert score > 7.0

    def test_high_pe_low_roe_scores_poorly(self) -> None:
        """High P/E + low ROE should score poorly."""
        from backend.tools.recommend_stocks import _score_fundamentals

        score = _score_fundamentals(forward_pe=50.0, return_on_equity=0.02, piotroski=3)
        assert score < 5.0

    def test_none_values_default_to_neutral(self) -> None:
        """None values should default to neutral score."""
        from backend.tools.recommend_stocks import _score_fundamentals

        score = _score_fundamentals(forward_pe=None, return_on_equity=None, piotroski=None)
        assert score == 5.0
