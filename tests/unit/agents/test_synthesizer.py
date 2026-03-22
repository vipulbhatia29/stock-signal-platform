"""Tests for synthesizer node."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.agents.synthesizer import (
    build_synthesizer_prompt,
    parse_synthesis_response,
    synthesize_results,
)


class TestBuildSynthesizerPrompt:
    """Tests for prompt construction."""

    def test_injects_tool_results(self) -> None:
        """Tool results should appear in the prompt."""
        results = [
            {
                "tool": "analyze_stock",
                "status": "ok",
                "data": {"ticker": "PLTR", "composite_score": 8.2},
                "source": "TimescaleDB",
                "timestamp": "2026-03-20T14:30:00Z",
            }
        ]
        prompt = build_synthesizer_prompt(results, {})
        assert "analyze_stock" in prompt
        assert "PLTR" in prompt

    def test_marks_unavailable_results(self) -> None:
        """Unavailable results should be clearly marked."""
        results = [
            {
                "tool": "get_fundamentals",
                "status": "unavailable",
                "data": None,
                "reason": "API timeout",
            }
        ]
        prompt = build_synthesizer_prompt(results, {})
        assert "UNAVAILABLE" in prompt
        assert "API timeout" in prompt

    def test_injects_portfolio_context(self) -> None:
        """User portfolio should appear in context."""
        ctx = {
            "held_tickers": ["PLTR"],
            "positions": [{"ticker": "PLTR", "allocation_pct": 15.0}],
            "preferences": {"max_position_pct": 5, "max_sector_pct": 25},
        }
        prompt = build_synthesizer_prompt([], ctx)
        assert "PLTR" in prompt
        assert "15.0%" in prompt


class TestParseSynthesisResponse:
    """Tests for synthesis response parsing."""

    def test_parses_valid_synthesis(self) -> None:
        """Valid JSON synthesis should parse correctly."""
        response = json.dumps(
            {
                "confidence": 0.78,
                "confidence_label": "high",
                "summary": "PLTR is bullish.",
                "scenarios": {
                    "bull": {"thesis": "AI growth", "probability": 0.35},
                    "base": {"thesis": "Steady", "probability": 0.45},
                    "bear": {"thesis": "Slowdown", "probability": 0.20},
                },
                "evidence": [
                    {
                        "claim": "Score 8.2",
                        "source_tool": "analyze_stock",
                        "value": "8.2",
                        "timestamp": "2026-03-20T14:30:00Z",
                    }
                ],
                "gaps": [],
                "portfolio_note": None,
            }
        )
        result = parse_synthesis_response(response)
        assert result["confidence"] == 0.78
        assert result["confidence_label"] == "high"
        assert len(result["evidence"]) == 1

    def test_handles_partial_data(self) -> None:
        """Missing fields should get defaults."""
        response = json.dumps({"confidence": 0.5, "summary": "Partial."})
        result = parse_synthesis_response(response)
        assert result["scenarios"] == {}
        assert result["evidence"] == []
        assert result["gaps"] == []

    def test_strips_markdown_fences(self) -> None:
        """Should handle ```json wrapping."""
        inner = json.dumps({"confidence": 0.65, "summary": "Test"})
        response = f"```json\n{inner}\n```"
        result = parse_synthesis_response(response)
        assert result["confidence"] == 0.65

    def test_rejects_invalid_json(self) -> None:
        """Non-JSON should raise ValueError."""
        with pytest.raises(ValueError, match="Failed to parse"):
            parse_synthesis_response("not json")

    def test_auto_labels_confidence(self) -> None:
        """If confidence_label missing, it's computed from score."""
        response = json.dumps({"confidence": 0.80})
        result = parse_synthesis_response(response)
        assert result["confidence_label"] == "high"

        response = json.dumps({"confidence": 0.50})
        result = parse_synthesis_response(response)
        assert result["confidence_label"] == "medium"

        response = json.dumps({"confidence": 0.30})
        result = parse_synthesis_response(response)
        assert result["confidence_label"] == "low"


class TestSynthesizeResults:
    """Tests for the full synthesize_results function."""

    @pytest.mark.asyncio
    async def test_calls_llm_and_parses(self) -> None:
        """Should call LLM with prompt and parse JSON response."""
        mock_response = MagicMock()
        mock_response.content = json.dumps(
            {
                "confidence": 0.72,
                "confidence_label": "high",
                "summary": "PLTR looks strong.",
                "scenarios": {
                    "bull": {"thesis": "Growth", "probability": 0.4},
                    "base": {"thesis": "Steady", "probability": 0.4},
                    "bear": {"thesis": "Risk", "probability": 0.2},
                },
                "evidence": [
                    {
                        "claim": "Score 8.2",
                        "source_tool": "analyze_stock",
                        "value": "8.2",
                        "timestamp": "2026-03-20T14:30:00Z",
                    }
                ],
                "gaps": [],
                "portfolio_note": None,
            }
        )
        mock_llm = AsyncMock(return_value=mock_response)

        tool_results = [
            {
                "tool": "analyze_stock",
                "status": "ok",
                "data": {"ticker": "PLTR", "composite_score": 8.2},
                "source": "TimescaleDB",
                "timestamp": "2026-03-20T14:30:00Z",
            }
        ]

        result = await synthesize_results(tool_results, {}, mock_llm)
        assert result["confidence"] == 0.72
        assert result["confidence_label"] == "high"
        mock_llm.assert_called_once()

    @pytest.mark.asyncio
    async def test_includes_gaps_for_unavailable_tools(self) -> None:
        """Synthesis should include gaps when tools failed."""
        mock_response = MagicMock()
        mock_response.content = json.dumps(
            {
                "confidence": 0.45,
                "summary": "Partial analysis.",
                "gaps": ["Fundamental data unavailable"],
            }
        )
        mock_llm = AsyncMock(return_value=mock_response)

        results = [
            {"tool": "analyze_stock", "status": "ok", "data": {}, "source": "DB", "timestamp": "t"},
            {
                "tool": "get_fundamentals",
                "status": "unavailable",
                "data": None,
                "reason": "timeout",
            },
        ]

        synthesis = await synthesize_results(results, {}, mock_llm)
        assert len(synthesis["gaps"]) == 1
