"""Tests for GetRecommendationScorecardTool."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from backend.tools.scorecard import HorizonBreakdown, ScorecardData


class TestGetRecommendationScorecardTool:
    """Tests for the scorecard agent tool."""

    @pytest.mark.asyncio
    async def test_formats_scorecard_correctly(self) -> None:
        """Should return formatted scorecard data."""
        from backend.tools.scorecard_tool import GetRecommendationScorecardTool

        scorecard = ScorecardData(
            total_outcomes=50,
            overall_hit_rate=0.78,
            avg_alpha=0.032,
            buy_hit_rate=0.82,
            sell_hit_rate=0.65,
            worst_miss_pct=-0.15,
            worst_miss_ticker="SNAP",
            horizons=[
                HorizonBreakdown(
                    horizon_days=90,
                    total=20,
                    correct=16,
                    hit_rate=0.8,
                    avg_alpha=0.04,
                ),
            ],
        )

        mock_session = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_session
        mock_cm.__aexit__.return_value = None

        with (
            patch(
                "backend.database.async_session_factory",
                return_value=mock_cm,
            ),
            patch(
                "backend.tools.scorecard.compute_scorecard",
                new_callable=AsyncMock,
                return_value=scorecard,
            ),
        ):
            tool = GetRecommendationScorecardTool()
            result = await tool.execute({"user_id": "12345678-1234-5678-1234-567812345678"})

        assert result.status == "ok"
        assert result.data["total_outcomes"] == 50
        assert result.data["overall_hit_rate_pct"] == 78.0
        assert result.data["avg_alpha_pct"] == 3.2
        assert result.data["worst_miss"]["ticker"] == "SNAP"
        assert len(result.data["horizons"]) == 1

    @pytest.mark.asyncio
    async def test_no_outcomes_returns_message(self) -> None:
        """Should return informational message when no outcomes exist."""
        from backend.tools.scorecard_tool import GetRecommendationScorecardTool

        scorecard = ScorecardData()  # All defaults (0)

        mock_session = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_session
        mock_cm.__aexit__.return_value = None

        with (
            patch(
                "backend.database.async_session_factory",
                return_value=mock_cm,
            ),
            patch(
                "backend.tools.scorecard.compute_scorecard",
                new_callable=AsyncMock,
                return_value=scorecard,
            ),
        ):
            tool = GetRecommendationScorecardTool()
            result = await tool.execute({"user_id": "12345678-1234-5678-1234-567812345678"})

        assert result.status == "ok"
        assert result.data["total_outcomes"] == 0
        assert "No evaluated" in result.data["message"]

    @pytest.mark.asyncio
    async def test_missing_user_id_returns_error(self) -> None:
        """Should return error for missing user_id."""
        from backend.tools.scorecard_tool import GetRecommendationScorecardTool

        tool = GetRecommendationScorecardTool()
        result = await tool.execute({})

        assert result.status == "error"
        assert "Missing" in result.error
