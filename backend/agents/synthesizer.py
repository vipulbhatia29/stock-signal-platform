"""Synthesizer node for Agent V2 — produces final analysis from tool results.

Takes validated tool results + user context, calls an LLM to produce
confidence scoring, bull/base/bear scenarios, and an evidence tree
grounded in tool data.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent / "prompts" / "synthesizer.md"


def _load_prompt() -> str:
    """Load the synthesizer prompt template."""
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _format_tool_results(results: list[dict[str, Any]]) -> str:
    """Format validated tool results for the synthesizer prompt."""
    lines = []
    for r in results:
        status = r.get("status", "unknown")
        tool = r.get("tool", "unknown")
        source = r.get("source", "")
        ts = r.get("timestamp", "")

        if status == "unavailable":
            reason = r.get("reason", "unknown error")
            lines.append(f"- **{tool}** [UNAVAILABLE]: {reason}")
        elif status == "stale":
            reason = r.get("reason", "")
            data_summary = _summarize_data(r.get("data"))
            lines.append(
                f"- **{tool}** [STALE — {reason}] (source: {source}, at {ts}):\n  {data_summary}"
            )
        else:
            data_summary = _summarize_data(r.get("data"))
            lines.append(f"- **{tool}** (source: {source}, at {ts}):\n  {data_summary}")

    return "\n".join(lines) if lines else "No tool results available."


def _summarize_data(data: Any) -> str:
    """Summarize tool data for prompt injection (keep it concise)."""
    if data is None:
        return "No data"
    if isinstance(data, dict):
        # JSON dump but cap at 500 chars
        text = json.dumps(data, default=str)
        return text[:500] + "..." if len(text) > 500 else text
    if isinstance(data, list):
        text = json.dumps(data[:5], default=str)  # cap list items
        suffix = f" (+{len(data) - 5} more)" if len(data) > 5 else ""
        return text + suffix
    return str(data)[:500]


def build_synthesizer_prompt(
    tool_results: list[dict[str, Any]],
    user_context: dict[str, Any],
) -> str:
    """Build the full synthesizer prompt with injected data.

    Args:
        tool_results: List of validated tool result dicts from the executor.
        user_context: Dict from build_user_context().

    Returns:
        Complete prompt string ready for LLM call.
    """
    template = _load_prompt()
    results_str = _format_tool_results(tool_results)

    ctx_lines = []
    if user_context.get("held_tickers"):
        ctx_lines.append(f"User holds: {', '.join(user_context['held_tickers'])}")
        for pos in user_context.get("positions", []):
            ctx_lines.append(f"  - {pos['ticker']}: {pos.get('allocation_pct', 0):.1f}% allocation")
    if user_context.get("preferences"):
        prefs = user_context["preferences"]
        ctx_lines.append(
            f"Preferences: max position {prefs.get('max_position_pct', 5)}%, "
            f"max sector {prefs.get('max_sector_pct', 25)}%"
        )
    ctx_str = "\n".join(ctx_lines) if ctx_lines else "No portfolio data available."

    return template.replace("{{tool_results}}", results_str).replace("{{user_context}}", ctx_str)


def parse_synthesis_response(response_text: str) -> dict[str, Any]:
    """Parse the LLM's synthesis JSON response.

    Args:
        response_text: Raw LLM response text.

    Returns:
        Parsed synthesis dict with confidence, scenarios, evidence, gaps.

    Raises:
        ValueError: If the response cannot be parsed.
    """
    text = response_text.strip()

    # Strip markdown code fences
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [line for line in lines if not line.strip().startswith("```")]
        text = "\n".join(lines).strip()

    try:
        synthesis = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse synthesizer response: {e}") from e

    # Validate and normalize
    synthesis.setdefault("confidence", 0.5)
    synthesis.setdefault("confidence_label", _label_confidence(synthesis["confidence"]))
    synthesis.setdefault("summary", "Analysis complete.")
    synthesis.setdefault("scenarios", {})
    synthesis.setdefault("evidence", [])
    synthesis.setdefault("gaps", [])
    synthesis.setdefault("portfolio_note", None)

    return synthesis


def _label_confidence(score: float) -> str:
    """Convert numeric confidence to label."""
    if score >= 0.65:
        return "high"
    if score >= 0.40:
        return "medium"
    return "low"


async def synthesize_results(
    tool_results: list[dict[str, Any]],
    user_context: dict[str, Any],
    llm_chat: Any,
) -> dict[str, Any]:
    """Synthesize tool results into a structured analysis.

    Args:
        tool_results: Validated tool result dicts from the executor.
        user_context: Dict from build_user_context().
        llm_chat: Callable async function(messages, tools) -> LLMResponse.

    Returns:
        Parsed synthesis dict with confidence, scenarios, evidence, gaps.
    """
    prompt = build_synthesizer_prompt(tool_results, user_context)

    messages = [
        {"role": "user", "content": prompt},
    ]

    response = await llm_chat(messages=messages, tools=[])

    return parse_synthesis_response(response.content)
