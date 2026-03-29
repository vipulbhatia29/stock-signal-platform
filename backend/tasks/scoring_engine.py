"""5-dimension scoring engine for agent quality assessment.

Provides deterministic scorers for tool selection, grounding, termination,
and external resilience, plus an LLM-as-judge scorer for reasoning coherence.
The aggregate ``score_query`` function combines all dimensions into a single
result dict suitable for storage in eval_results.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from typing import Any

from backend.tasks.golden_dataset import GoldenQuery

logger = logging.getLogger(__name__)

# Pattern for suspiciously specific numeric data (e.g. "$152.34", "28.5%", "3.14")
_SPECIFIC_NUMBER_RE = re.compile(r"\$?\d+\.\d{2,}%?|\d+\.\d+%")


# ── Deterministic Scorers ────────────────────────────────────────────────────


def score_tool_selection(expected: frozenset[str], actual: set[str]) -> bool:
    """Check whether all expected tools were called.

    Args:
        expected: Tools that MUST be called.
        actual: Tools that WERE called.

    Returns:
        True if expected is a subset of actual.
    """
    return expected <= actual


def score_grounding(response: str, checks: tuple[str, ...]) -> float:
    """Compute the fraction of grounding checks found in the response.

    Args:
        response: The agent's response text.
        checks: Substrings that should appear in the response.

    Returns:
        Ratio of found checks to total checks (0.0-1.0).
    """
    if not checks:
        return 1.0

    lower_response = response.lower()
    found = sum(1 for check in checks if check.lower() in lower_response)
    return found / len(checks)


def score_termination(
    iterations: int,
    max_expected: int,
    tools_called: list[str],
) -> bool:
    """Check that the agent terminated within budget and without loops.

    Args:
        iterations: Number of ReAct loop iterations used.
        max_expected: Maximum iterations allowed for this query.
        tools_called: Ordered list of tool names called.

    Returns:
        True if within budget AND no consecutive duplicate tool calls.
    """
    if iterations > max_expected:
        return False

    # Check for consecutive duplicate tool calls
    for i in range(1, len(tools_called)):
        if tools_called[i] == tools_called[i - 1]:
            return False

    return True


def score_external_resilience(
    response: str,
    mock_failures: dict[str, str],
) -> bool:
    """Check that the response does not hallucinate data for failed tools.

    Args:
        response: The agent's response text.
        mock_failures: Mapping of tool name to simulated error message.

    Returns:
        True if the response is clean (no hallucinated specifics for failed tools).
    """
    if not mock_failures:
        return True

    # If any tools failed and response contains suspiciously specific numbers,
    # that suggests hallucinated data
    specific_numbers = _SPECIFIC_NUMBER_RE.findall(response)
    if specific_numbers:
        logger.debug(
            "Resilience check: found specific numbers %s with failures %s",
            specific_numbers,
            list(mock_failures.keys()),
        )
        return False

    return True


# ── LLM-as-Judge Scorer ──────────────────────────────────────────────────────


async def score_reasoning_coherence(
    response: str,
    tool_outputs: list[str],
    llm_chat: Callable[..., Any],
) -> float:
    """Rate reasoning coherence using an LLM judge.

    Sends a scoring prompt to the provided LLM callable and parses the
    numeric rating (1-5) from the response.

    Args:
        response: The agent's response text.
        tool_outputs: Raw outputs from tools the agent called.
        llm_chat: Async callable that accepts a prompt string and returns text.

    Returns:
        Numeric score (1.0-5.0), or 0.0 on any error.
    """
    prompt = (
        "Rate the reasoning coherence of the following agent response from 1 to 5.\n\n"
        "Criteria:\n"
        "- Does the response logically connect tool outputs to the conclusion?\n"
        "- Does it acknowledge limitations?\n"
        "- Is the reasoning chain clear and well-structured?\n\n"
        f"Tool outputs:\n{chr(10).join(tool_outputs)}\n\n"
        f"Agent response:\n{response}\n\n"
        "Reply with a single digit (1-5) followed by a brief justification."
    )
    try:
        result = await llm_chat(prompt)
        # Parse the first digit from the LLM response
        match = re.search(r"[1-5]", str(result))
        if match:
            return float(match.group())
        logger.warning("No valid score digit found in LLM response: %s", result)
        return 0.0
    except Exception:
        logger.exception("Reasoning coherence scoring failed")
        return 0.0


# ── Aggregate Scorer ──────────────────────────────────────────────────────────


async def score_query(
    golden: GoldenQuery,
    response: str,
    tools_called: list[str],
    iterations: int,
    llm_chat: Callable[..., Any] | None = None,
) -> dict[str, float | bool | None]:
    """Score an agent response against a golden query across all 5 dimensions.

    Args:
        golden: The golden query definition.
        response: The agent's response text.
        tools_called: Ordered list of tool names called.
        iterations: Number of ReAct loop iterations used.
        llm_chat: Optional async callable for LLM-as-judge scoring.

    Returns:
        Dict with keys: tool_selection, grounding, termination,
        external_resilience, reasoning_coherence (None if not reasoning query).
    """
    result: dict[str, float | bool | None] = {
        "tool_selection": score_tool_selection(golden.expected_tools, set(tools_called)),
        "grounding": score_grounding(response, golden.grounding_checks),
        "termination": score_termination(iterations, golden.max_iterations, tools_called),
        "external_resilience": score_external_resilience(response, golden.mock_failures),
        "reasoning_coherence": None,
    }

    if golden.is_reasoning and llm_chat is not None:
        result["reasoning_coherence"] = await score_reasoning_coherence(
            response=response,
            tool_outputs=[f"Tool call: {t}" for t in tools_called],
            llm_chat=llm_chat,
        )

    return result
