"""Unit tests for the champion/challenger model promotion gate."""

from unittest.mock import patch

from backend.tasks.forecasting import _should_promote_challenger


class TestChampionChallenger:
    def test_challenger_promoted_when_direction_improves(self) -> None:
        """Challenger promoted when direction accuracy improves ≥1%."""
        champion = {"direction_accuracy": 0.55, "ci_containment": 0.80}
        challenger = {"direction_accuracy": 0.57, "ci_containment": 0.80}
        result = _should_promote_challenger(champion, challenger)
        assert result["promote"] is True
        assert "direction_accuracy" in result["reason"]

    def test_challenger_promoted_when_ci_improves(self) -> None:
        """Challenger promoted when CI containment improves ≥5%."""
        champion = {"direction_accuracy": 0.55, "ci_containment": 0.75}
        challenger = {"direction_accuracy": 0.55, "ci_containment": 0.81}
        result = _should_promote_challenger(champion, challenger)
        assert result["promote"] is True
        assert "ci_containment" in result["reason"]

    def test_challenger_rejected_when_worse(self) -> None:
        """Neither threshold met → keep champion."""
        champion = {"direction_accuracy": 0.58, "ci_containment": 0.82}
        challenger = {"direction_accuracy": 0.58, "ci_containment": 0.83}
        result = _should_promote_challenger(champion, challenger)
        assert result["promote"] is False

    def test_no_champion_always_promotes(self) -> None:
        """No existing champion → always promote."""
        result = _should_promote_challenger(
            None, {"direction_accuracy": 0.52, "ci_containment": 0.70}
        )
        assert result["promote"] is True
        assert "no existing champion" in result["reason"]

    def test_disabled_via_config(self) -> None:
        """CHAMPION_CHALLENGER_ENABLED=False → always promote."""
        champion = {"direction_accuracy": 0.90, "ci_containment": 0.95}
        challenger = {"direction_accuracy": 0.50, "ci_containment": 0.50}
        with patch("backend.tasks.forecasting.settings") as mock_settings:
            mock_settings.CHAMPION_CHALLENGER_ENABLED = False
            result = _should_promote_challenger(champion, challenger)
        assert result["promote"] is True
        assert "disabled" in result["reason"]

    def test_challenger_promoted_when_both_improve(self) -> None:
        """Both metrics improve → promote with combined reason."""
        champion = {"direction_accuracy": 0.55, "ci_containment": 0.70}
        challenger = {"direction_accuracy": 0.57, "ci_containment": 0.76}
        result = _should_promote_challenger(champion, challenger)
        assert result["promote"] is True
        assert "direction_accuracy" in result["reason"]
        assert "ci_containment" in result["reason"]

    def test_direction_exactly_at_threshold_promotes(self) -> None:
        """Direction delta exactly equal to threshold should promote."""
        champion = {"direction_accuracy": 0.55, "ci_containment": 0.80}
        challenger = {"direction_accuracy": 0.56, "ci_containment": 0.80}
        result = _should_promote_challenger(champion, challenger)
        assert result["promote"] is True

    def test_ci_exactly_at_threshold_promotes(self) -> None:
        """CI delta exactly equal to threshold should promote."""
        champion = {"direction_accuracy": 0.55, "ci_containment": 0.75}
        challenger = {"direction_accuracy": 0.55, "ci_containment": 0.80}
        result = _should_promote_challenger(champion, challenger)
        assert result["promote"] is True

    def test_challenger_worse_on_both_metrics(self) -> None:
        """Challenger worse on both → keep champion with delta info in reason."""
        champion = {"direction_accuracy": 0.60, "ci_containment": 0.85}
        challenger = {"direction_accuracy": 0.55, "ci_containment": 0.80}
        result = _should_promote_challenger(champion, challenger)
        assert result["promote"] is False
        assert "direction_accuracy" in result["reason"]
        assert "ci_containment" in result["reason"]

    def test_challenger_missing_metrics_defaults_to_zero(self) -> None:
        """Missing metrics keys default to 0.0 — gate still functions."""
        champion = {"direction_accuracy": 0.55, "ci_containment": 0.80}
        challenger: dict = {}  # no metrics at all
        result = _should_promote_challenger(champion, challenger)
        # 0.0 - 0.55 = -0.55, not ≥ threshold; 0.0 - 0.80 = -0.80, not ≥ threshold
        assert result["promote"] is False

    def test_champion_missing_metrics_defaults_to_zero(self) -> None:
        """Champion with missing keys defaults to 0.0 — challenger always beats it."""
        champion: dict = {}  # no metrics at all
        challenger = {"direction_accuracy": 0.52, "ci_containment": 0.70}
        result = _should_promote_challenger(champion, challenger)
        # challenger beats 0.0 baseline on ci_containment (0.70 - 0.0 = 0.70 ≥ 0.05)
        assert result["promote"] is True
