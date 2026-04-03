"""Rationale generator — template-based for common patterns, LLM for complex divergences."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.agents.llm_client import LLMClient

from backend.services.signal_convergence import (
    DivergenceInfo,
    SignalDirection,
)

logger = logging.getLogger(__name__)

# Signal display names for human-readable output
_SIGNAL_NAMES: dict[str, str] = {
    "rsi": "RSI",
    "macd": "MACD",
    "sma": "SMA-200",
    "piotroski": "Piotroski F-Score",
    "forecast": "90-day forecast",
    "news": "News sentiment",
}

_DIRECTION_LABELS: dict[str, str] = {
    "bullish": "bullish",
    "bearish": "bearish",
    "neutral": "neutral",
}


class RationaleGenerator:
    """Generates human-readable rationale for convergence state.

    Template-based for ~90% of cases (all-agree, one-disagrees).
    Falls back to LLM for complex multi-signal divergences.
    """

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        """Initialize the generator.

        Args:
            llm_client: Optional LLM client for complex rationale generation.
                       If None, falls back to template even for complex cases.
        """
        self._llm = llm_client

    async def generate(
        self,
        signals: list[SignalDirection],
        convergence_label: str,
        divergence: DivergenceInfo,
        ticker: str,
    ) -> str:
        """Generate rationale for the convergence state of a ticker.

        Args:
            signals: List of signal directions with values.
            convergence_label: The computed convergence label.
            divergence: Divergence detection info.
            ticker: Stock ticker for context.

        Returns:
            Human-readable rationale string.
        """
        bullish = [s for s in signals if s.direction == "bullish"]
        bearish = [s for s in signals if s.direction == "bearish"]
        neutral = [s for s in signals if s.direction == "neutral"]

        disagreeing_count = min(len(bullish), len(bearish))

        # Route: all agree or nearly all agree → template
        if disagreeing_count == 0:
            return self._template_all_agree(signals, convergence_label, bullish, bearish, neutral)

        if disagreeing_count == 1:
            return self._template_one_disagrees(
                signals, convergence_label, bullish, bearish, divergence
            )

        # 2+ signals disagree — try LLM, fall back to template
        if self._llm is not None:
            try:
                return await self._llm_rationale(signals, convergence_label, divergence, ticker)
            except Exception:
                logger.exception("LLM rationale generation failed for %s, using template", ticker)

        return self._template_complex_divergence(signals, convergence_label, bullish, bearish)

    # ------------------------------------------------------------------
    # Template generators
    # ------------------------------------------------------------------

    def _template_all_agree(
        self,
        signals: list[SignalDirection],
        label: str,
        bullish: list[SignalDirection],
        bearish: list[SignalDirection],
        neutral: list[SignalDirection],
    ) -> str:
        """Template for when all non-neutral signals agree.

        Args:
            signals: All signal directions.
            label: Convergence label.
            bullish: Bullish signals.
            bearish: Bearish signals.
            neutral: Neutral signals.

        Returns:
            Rationale string.
        """
        dominant = bullish if len(bullish) >= len(bearish) else bearish
        direction_word = "bullish" if dominant is bullish else "bearish"
        total = len(signals)
        aligned = len(dominant)

        parts = [f"{aligned} of {total} signals align {direction_word}."]

        for sig in dominant:
            detail = self._signal_detail(sig)
            if detail:
                parts.append(detail)

        if neutral:
            neutral_names = [_SIGNAL_NAMES.get(s.signal, s.signal) for s in neutral]
            verb = "is" if len(neutral) == 1 else "are"
            parts.append(f"{', '.join(neutral_names)} {verb} neutral.")

        return " ".join(parts)

    def _template_one_disagrees(
        self,
        signals: list[SignalDirection],
        label: str,
        bullish: list[SignalDirection],
        bearish: list[SignalDirection],
        divergence: DivergenceInfo,
    ) -> str:
        """Template for when one signal disagrees with the majority.

        Args:
            signals: All signal directions.
            label: Convergence label.
            bullish: Bullish signals.
            bearish: Bearish signals.
            divergence: Divergence info (may include hit rate).

        Returns:
            Rationale string.
        """
        majority = bullish if len(bullish) > len(bearish) else bearish
        minority = bearish if majority is bullish else bullish
        majority_word = "bullish" if majority is bullish else "bearish"
        total = len(signals)

        parts = [f"{len(majority)} of {total} signals are {majority_word}."]

        # Describe the dissenter
        if minority:
            dissenter = minority[0]
            name = _SIGNAL_NAMES.get(dissenter.signal, dissenter.signal)
            detail = self._signal_detail(dissenter)
            dissent_text = f"However, {name} is {dissenter.direction}"
            if detail:
                dissent_text += f" ({detail.rstrip('.')})"
            dissent_text += "."
            parts.append(dissent_text)

        # Add hit rate if we have divergence data
        if divergence.is_divergent and divergence.historical_hit_rate is not None:
            hit_pct = round(divergence.historical_hit_rate * 100)
            parts.append(
                f"When the forecast disagreed with technicals like this, "
                f"the forecast was right {hit_pct}% of the time "
                f"({divergence.sample_count} cases)."
            )

        return " ".join(parts)

    def _template_complex_divergence(
        self,
        signals: list[SignalDirection],
        label: str,
        bullish: list[SignalDirection],
        bearish: list[SignalDirection],
    ) -> str:
        """Fallback template for complex divergences (2+ disagree).

        Args:
            signals: All signal directions.
            label: Convergence label.
            bullish: Bullish signals.
            bearish: Bearish signals.

        Returns:
            Rationale string.
        """
        total = len(signals)
        n_bull, n_bear = len(bullish), len(bearish)
        parts = [f"Signals are mixed ({n_bull} bullish, {n_bear} bearish out of {total})."]

        if bullish:
            bull_names = [_SIGNAL_NAMES.get(s.signal, s.signal) for s in bullish]
            parts.append(f"Bullish: {', '.join(bull_names)}.")

        if bearish:
            bear_names = [_SIGNAL_NAMES.get(s.signal, s.signal) for s in bearish]
            parts.append(f"Bearish: {', '.join(bear_names)}.")

        parts.append("Consider waiting for clearer alignment before acting.")
        return " ".join(parts)

    # ------------------------------------------------------------------
    # Signal detail formatter
    # ------------------------------------------------------------------

    @staticmethod
    def _signal_detail(sig: SignalDirection) -> str:
        """Format a human-readable detail for a signal's raw value.

        Args:
            sig: Signal direction with optional value.

        Returns:
            Detail string or empty string if no value.
        """
        if sig.value is None:
            return ""

        match sig.signal:
            case "rsi":
                return f"RSI at {sig.value:.0f}."
            case "macd":
                return f"MACD histogram at {sig.value:.4f}."
            case "sma":
                return f"SMA-200 at {sig.value:.2f}."
            case "piotroski":
                return f"F-Score {int(sig.value)}/9."
            case "forecast":
                pct = sig.value * 100
                sign = "+" if pct > 0 else ""
                return f"Forecast predicts {sign}{pct:.1f}%."
            case "news":
                return f"Sentiment score {sig.value:+.2f}."
            case _:
                return ""

    # ------------------------------------------------------------------
    # LLM fallback
    # ------------------------------------------------------------------

    async def _llm_rationale(
        self,
        signals: list[SignalDirection],
        label: str,
        divergence: DivergenceInfo,
        ticker: str,
    ) -> str:
        """Generate rationale via LLM for complex divergence patterns.

        Args:
            signals: All signal directions.
            label: Convergence label.
            divergence: Divergence info.
            ticker: Stock ticker.

        Returns:
            LLM-generated rationale string.
        """
        assert self._llm is not None  # noqa: S101

        signal_summary = "\n".join(
            f"- {_SIGNAL_NAMES.get(s.signal, s.signal)}: {s.direction}"
            + (f" (value: {s.value})" if s.value is not None else "")
            for s in signals
        )

        hit_rate_ctx = ""
        if divergence.is_divergent and divergence.historical_hit_rate is not None:
            hit_rate_ctx = (
                f"\nHistorical context: when the forecast disagreed with technicals "
                f"in this pattern, the forecast was correct "
                f"{divergence.historical_hit_rate:.0%} of the time "
                f"({divergence.sample_count} cases)."
            )

        prompt = (
            f"You are a financial analyst writing a brief convergence rationale for {ticker}.\n"
            f"The convergence label is: {label}\n\n"
            f"Signal directions:\n{signal_summary}\n"
            f"{hit_rate_ctx}\n\n"
            f"Write 2-3 sentences explaining why signals disagree and what it means "
            f"for the investor. Be factual and concise. Do not give investment advice."
        )

        response = await self._llm.chat(
            messages=[{"role": "user", "content": prompt}],
            tools=[],
            stream=False,
        )
        return response.content.strip()
