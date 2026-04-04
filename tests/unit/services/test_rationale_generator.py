"""Unit tests for RationaleGenerator — template selection, output format, LLM fallback.

Tests cover the pure template logic without any DB or LLM interaction.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.services.rationale import RationaleGenerator
from backend.services.signal_convergence import DivergenceInfo, SignalDirection

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def generator() -> RationaleGenerator:
    """RationaleGenerator without LLM (template-only)."""
    return RationaleGenerator(llm_client=None)


def _make_signals(
    rsi: str = "neutral",
    macd: str = "neutral",
    sma: str = "neutral",
    piotroski: str = "neutral",
    forecast: str = "neutral",
    news: str = "neutral",
) -> list[SignalDirection]:
    """Build a list of 6 SignalDirection objects.

    Args:
        rsi: RSI direction.
        macd: MACD direction.
        sma: SMA direction.
        piotroski: Piotroski direction.
        forecast: Forecast direction.
        news: News direction.

    Returns:
        List of 6 SignalDirection objects with sample values.
    """
    val_map: dict[str, dict[str, float]] = {
        "rsi": {"bullish": 42.0, "bearish": 75.0, "neutral": 55.0},
        "macd": {"bullish": 0.03, "bearish": -0.03, "neutral": 0.0},
        "piotroski": {"bullish": 7, "bearish": 2, "neutral": 5},
        "forecast": {"bullish": 0.08, "bearish": -0.05, "neutral": 0.01},
        "news": {"bullish": 0.5, "bearish": -0.5, "neutral": 0.0},
    }
    return [
        SignalDirection("rsi", rsi, val_map["rsi"].get(rsi, 55.0)),
        SignalDirection("macd", macd, val_map["macd"].get(macd, 0.0)),
        SignalDirection("sma", sma, 100.0),
        SignalDirection("piotroski", piotroski, val_map["piotroski"].get(piotroski, 5)),
        SignalDirection("forecast", forecast, val_map["forecast"].get(forecast, 0.01)),
        SignalDirection("news", news, val_map["news"].get(news, 0.0)),
    ]


# ---------------------------------------------------------------------------
# Template: all agree
# ---------------------------------------------------------------------------


class TestTemplateAllAgree:
    """Tests for the all-agree template path."""

    @pytest.mark.asyncio()
    async def test_all_bullish_mentions_count(self, generator: RationaleGenerator) -> None:
        """All-bullish rationale mentions signal count."""
        signals = _make_signals(
            rsi="bullish",
            macd="bullish",
            sma="bullish",
            piotroski="bullish",
            forecast="bullish",
            news="bullish",
        )
        div = DivergenceInfo()
        result = await generator.generate(signals, "strong_bull", div, "AAPL")

        assert "6 of 6" in result
        assert "bullish" in result.lower()

    @pytest.mark.asyncio()
    async def test_mostly_bullish_with_neutrals(self, generator: RationaleGenerator) -> None:
        """Bullish majority with neutrals mentions neutral signals."""
        signals = _make_signals(
            rsi="bullish",
            macd="bullish",
            sma="bullish",
            piotroski="bullish",
            forecast="neutral",
            news="neutral",
        )
        div = DivergenceInfo()
        result = await generator.generate(signals, "strong_bull", div, "AAPL")

        assert "4 of 6" in result
        assert "neutral" in result.lower()

    @pytest.mark.asyncio()
    async def test_all_bearish(self, generator: RationaleGenerator) -> None:
        """All-bearish rationale mentions bearish direction."""
        signals = _make_signals(
            rsi="bearish",
            macd="bearish",
            sma="bearish",
            piotroski="bearish",
            forecast="bearish",
            news="bearish",
        )
        div = DivergenceInfo()
        result = await generator.generate(signals, "strong_bear", div, "AAPL")

        assert "6 of 6" in result
        assert "bearish" in result.lower()


# ---------------------------------------------------------------------------
# Template: one disagrees
# ---------------------------------------------------------------------------


class TestTemplateOneDisagrees:
    """Tests for the one-disagrees template path."""

    @pytest.mark.asyncio()
    async def test_one_bearish_dissenter_named(self, generator: RationaleGenerator) -> None:
        """One bearish signal among bullish → names the dissenter."""
        signals = _make_signals(
            rsi="bullish",
            macd="bullish",
            sma="bullish",
            piotroski="bullish",
            forecast="bearish",
            news="neutral",
        )
        div = DivergenceInfo(
            is_divergent=True,
            forecast_direction="bearish",
            technical_majority="bullish",
        )
        result = await generator.generate(signals, "weak_bull", div, "AAPL")

        assert "4 of 6" in result
        assert "However" in result
        assert "forecast" in result.lower() or "Forecast" in result

    @pytest.mark.asyncio()
    async def test_hit_rate_included_when_available(self, generator: RationaleGenerator) -> None:
        """Hit rate is mentioned when divergence has historical data."""
        signals = _make_signals(
            rsi="bullish",
            macd="bullish",
            sma="bullish",
            piotroski="bullish",
            forecast="bearish",
            news="neutral",
        )
        div = DivergenceInfo(
            is_divergent=True,
            forecast_direction="bearish",
            technical_majority="bullish",
            historical_hit_rate=0.61,
            sample_count=23,
        )
        result = await generator.generate(signals, "weak_bull", div, "AAPL")

        assert "61%" in result
        assert "23 cases" in result

    @pytest.mark.asyncio()
    async def test_no_hit_rate_when_none(self, generator: RationaleGenerator) -> None:
        """No hit rate text when not available."""
        signals = _make_signals(
            rsi="bullish",
            macd="bullish",
            sma="bullish",
            piotroski="bullish",
            forecast="bearish",
            news="neutral",
        )
        div = DivergenceInfo(
            is_divergent=True,
            forecast_direction="bearish",
            technical_majority="bullish",
        )
        result = await generator.generate(signals, "weak_bull", div, "AAPL")

        assert "cases" not in result


# ---------------------------------------------------------------------------
# Template: complex divergence
# ---------------------------------------------------------------------------


class TestTemplateComplexDivergence:
    """Tests for the complex divergence fallback template."""

    @pytest.mark.asyncio()
    async def test_mixed_signals_template(self, generator: RationaleGenerator) -> None:
        """2+ disagreements without LLM → falls back to complex template."""
        signals = _make_signals(
            rsi="bullish",
            macd="bullish",
            sma="bearish",
            piotroski="bearish",
            forecast="neutral",
            news="neutral",
        )
        div = DivergenceInfo()
        result = await generator.generate(signals, "mixed", div, "AAPL")

        assert "mixed" in result.lower() or "Mixed" in result
        assert "2 bullish" in result
        assert "2 bearish" in result
        assert "Consider" in result


# ---------------------------------------------------------------------------
# LLM fallback
# ---------------------------------------------------------------------------


class TestLlmFallback:
    """Tests for LLM rationale generation path."""

    @pytest.mark.asyncio()
    async def test_llm_called_for_complex_divergence(self) -> None:
        """LLM is invoked when 2+ signals disagree."""
        mock_response = MagicMock()
        mock_response.content = "This is an LLM-generated rationale."
        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(return_value=mock_response)

        gen = RationaleGenerator(llm_client=mock_llm)
        signals = _make_signals(
            rsi="bullish",
            macd="bullish",
            sma="bearish",
            piotroski="bearish",
            forecast="neutral",
            news="neutral",
        )
        div = DivergenceInfo()
        result = await gen.generate(signals, "mixed", div, "AAPL")

        assert result == "This is an LLM-generated rationale."
        mock_llm.chat.assert_called_once()

    @pytest.mark.asyncio()
    async def test_llm_failure_falls_back_to_template(self) -> None:
        """LLM error → gracefully falls back to template."""
        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(side_effect=RuntimeError("LLM unavailable"))

        gen = RationaleGenerator(llm_client=mock_llm)
        signals = _make_signals(
            rsi="bullish",
            macd="bullish",
            sma="bearish",
            piotroski="bearish",
            forecast="neutral",
            news="neutral",
        )
        div = DivergenceInfo()
        result = await gen.generate(signals, "mixed", div, "AAPL")

        # Should get template output, not crash
        assert "mixed" in result.lower() or "Bullish" in result
        assert len(result) > 10

    @pytest.mark.asyncio()
    async def test_no_llm_uses_template_always(self, generator: RationaleGenerator) -> None:
        """Without LLM client, always uses templates even for complex cases."""
        signals = _make_signals(
            rsi="bullish",
            macd="bearish",
            sma="bullish",
            piotroski="bearish",
            forecast="bullish",
            news="bearish",
        )
        div = DivergenceInfo()
        result = await generator.generate(signals, "mixed", div, "AAPL")

        assert isinstance(result, str)
        assert len(result) > 10


# ---------------------------------------------------------------------------
# Signal detail formatting
# ---------------------------------------------------------------------------


class TestSignalDetail:
    """Tests for the _signal_detail formatter."""

    def test_rsi_detail(self) -> None:
        """RSI detail shows value as integer."""
        gen = RationaleGenerator()
        detail = gen._signal_detail(SignalDirection("rsi", "bullish", 42.3))
        assert "42" in detail

    def test_forecast_detail_with_percentage(self) -> None:
        """Forecast detail shows percentage with sign."""
        gen = RationaleGenerator()
        detail = gen._signal_detail(SignalDirection("forecast", "bullish", 0.08))
        assert "+8.0%" in detail

    def test_piotroski_detail(self) -> None:
        """Piotroski detail shows score out of 9."""
        gen = RationaleGenerator()
        detail = gen._signal_detail(SignalDirection("piotroski", "bullish", 7))
        assert "7/9" in detail

    def test_news_detail(self) -> None:
        """News detail shows sentiment score with sign."""
        gen = RationaleGenerator()
        detail = gen._signal_detail(SignalDirection("news", "bullish", 0.5))
        assert "+0.50" in detail

    def test_none_value_returns_empty(self) -> None:
        """None value produces empty detail string."""
        gen = RationaleGenerator()
        detail = gen._signal_detail(SignalDirection("rsi", "neutral", None))
        assert detail == ""


# ---------------------------------------------------------------------------
# LLM prompt content inspection
# ---------------------------------------------------------------------------


class TestLlmPromptContent:
    """Tests that the prompt sent to the LLM contains the expected content.

    These tests assert that ticker symbol, signal names, and score values
    are all present in the prompt — ensuring the LLM has full context.
    """

    @pytest.mark.asyncio()
    @pytest.mark.regression
    async def test_llm_prompt_contains_ticker_symbol(self) -> None:
        """Prompt sent to LLM includes the ticker symbol for context."""
        captured_messages: list[list[dict]] = []

        mock_response = MagicMock()
        mock_response.content = "LLM rationale."
        mock_llm = AsyncMock()

        async def capture_chat(messages, **_kwargs):
            captured_messages.append(messages)
            return mock_response

        mock_llm.chat = capture_chat

        gen = RationaleGenerator(llm_client=mock_llm)
        signals = _make_signals(
            rsi="bullish",
            macd="bullish",
            sma="bearish",
            piotroski="bearish",
            forecast="neutral",
            news="neutral",
        )
        div = DivergenceInfo()
        await gen.generate(signals, "mixed", div, "MSFT")

        assert len(captured_messages) == 1
        prompt_text = captured_messages[0][0]["content"]
        assert "MSFT" in prompt_text

    @pytest.mark.asyncio()
    @pytest.mark.regression
    async def test_llm_prompt_contains_all_signal_names(self) -> None:
        """Prompt sent to LLM lists all 6 signal names so the model can reason about each."""
        captured_messages: list[list[dict]] = []

        mock_response = MagicMock()
        mock_response.content = "LLM rationale."
        mock_llm = AsyncMock()

        async def capture_chat(messages, **_kwargs):
            captured_messages.append(messages)
            return mock_response

        mock_llm.chat = capture_chat

        gen = RationaleGenerator(llm_client=mock_llm)
        signals = _make_signals(
            rsi="bullish",
            macd="bullish",
            sma="bearish",
            piotroski="bearish",
            forecast="neutral",
            news="neutral",
        )
        div = DivergenceInfo()
        await gen.generate(signals, "mixed", div, "AAPL")

        prompt_text = captured_messages[0][0]["content"]
        # All six signal display names must appear in the prompt
        expected_names = (
            "RSI",
            "MACD",
            "SMA-200",
            "Piotroski F-Score",
            "90-day forecast",
            "News sentiment",
        )
        for expected_name in expected_names:
            assert expected_name in prompt_text, f"Expected '{expected_name}' in prompt"

    @pytest.mark.asyncio()
    @pytest.mark.regression
    async def test_llm_prompt_contains_convergence_label(self) -> None:
        """Prompt sent to LLM includes the convergence label so model understands overall state."""
        captured_messages: list[list[dict]] = []

        mock_response = MagicMock()
        mock_response.content = "LLM rationale."
        mock_llm = AsyncMock()

        async def capture_chat(messages, **_kwargs):
            captured_messages.append(messages)
            return mock_response

        mock_llm.chat = capture_chat

        gen = RationaleGenerator(llm_client=mock_llm)
        signals = _make_signals(
            rsi="bullish",
            macd="bullish",
            sma="bearish",
            piotroski="bearish",
            forecast="neutral",
            news="neutral",
        )
        div = DivergenceInfo()
        await gen.generate(signals, "mixed", div, "AAPL")

        prompt_text = captured_messages[0][0]["content"]
        assert "mixed" in prompt_text

    @pytest.mark.asyncio()
    @pytest.mark.regression
    async def test_llm_prompt_contains_signal_directions(self) -> None:
        """Prompt includes per-signal direction labels (bullish/bearish/neutral) for each signal."""
        captured_messages: list[list[dict]] = []

        mock_response = MagicMock()
        mock_response.content = "LLM rationale."
        mock_llm = AsyncMock()

        async def capture_chat(messages, **_kwargs):
            captured_messages.append(messages)
            return mock_response

        mock_llm.chat = capture_chat

        gen = RationaleGenerator(llm_client=mock_llm)
        signals = _make_signals(
            rsi="bullish",
            macd="bullish",
            sma="bearish",
            piotroski="bearish",
            forecast="neutral",
            news="neutral",
        )
        div = DivergenceInfo()
        await gen.generate(signals, "mixed", div, "AAPL")

        prompt_text = captured_messages[0][0]["content"]
        assert "bullish" in prompt_text
        assert "bearish" in prompt_text

    @pytest.mark.asyncio()
    @pytest.mark.regression
    async def test_llm_prompt_contains_signal_values(self) -> None:
        """Prompt includes raw signal values so model can cite specific numbers."""
        captured_messages: list[list[dict]] = []

        mock_response = MagicMock()
        mock_response.content = "LLM rationale."
        mock_llm = AsyncMock()

        async def capture_chat(messages, **_kwargs):
            captured_messages.append(messages)
            return mock_response

        mock_llm.chat = capture_chat

        gen = RationaleGenerator(llm_client=mock_llm)
        # Use distinctive values that can be verified in the prompt
        signals = [
            SignalDirection("rsi", "bullish", 42.0),
            SignalDirection("macd", "bullish", 0.03),
            SignalDirection("sma", "bearish", 195.0),
            SignalDirection("piotroski", "bearish", 2),
            SignalDirection("forecast", "neutral", 0.01),
            SignalDirection("news", "neutral", 0.0),
        ]
        div = DivergenceInfo()
        await gen.generate(signals, "mixed", div, "AAPL")

        prompt_text = captured_messages[0][0]["content"]
        # The prompt includes "value: X" for signals with non-None values
        assert "42.0" in prompt_text or "42" in prompt_text
        assert "0.03" in prompt_text

    @pytest.mark.asyncio()
    @pytest.mark.regression
    async def test_llm_prompt_contains_historical_hit_rate_when_divergent(self) -> None:
        """Prompt includes historical hit-rate context when forecast diverges from technicals."""
        captured_messages: list[list[dict]] = []

        mock_response = MagicMock()
        mock_response.content = "LLM rationale."
        mock_llm = AsyncMock()

        async def capture_chat(messages, **_kwargs):
            captured_messages.append(messages)
            return mock_response

        mock_llm.chat = capture_chat

        gen = RationaleGenerator(llm_client=mock_llm)
        signals = _make_signals(
            rsi="bullish",
            macd="bullish",
            sma="bearish",
            piotroski="bearish",
            forecast="neutral",
            news="neutral",
        )
        div = DivergenceInfo(
            is_divergent=True,
            forecast_direction="neutral",
            technical_majority="bullish",
            historical_hit_rate=0.72,
            sample_count=31,
        )
        await gen.generate(signals, "mixed", div, "AAPL")

        prompt_text = captured_messages[0][0]["content"]
        assert "72%" in prompt_text
        assert "31" in prompt_text
