"""Planner node for Agent V2 — classifies intent and generates tool plan.

The planner receives a user query + context and produces a structured plan
that the mechanical executor will follow. It uses an LLM (tier=planner)
to decide which tools to call and in what order.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent / "prompts" / "planner.md"

# Valid intent types
VALID_INTENTS = {
    "stock_analysis",
    "portfolio",
    "market_overview",
    "simple_lookup",
    "out_of_scope",
}


def _load_prompt() -> str:
    """Load the planner prompt template."""
    return _PROMPT_PATH.read_text(encoding="utf-8")


def build_planner_prompt(
    query: str,
    tools_description: str,
    user_context: dict[str, Any],
) -> str:
    """Build the full planner prompt with injected context.

    Args:
        query: The user's natural language query.
        tools_description: Formatted string of available tool descriptions.
        user_context: Dict from build_user_context().

    Returns:
        Complete prompt string ready for LLM call.
    """
    template = _load_prompt()
    ctx_lines = []
    if user_context.get("held_tickers"):
        ctx_lines.append(f"User holds: {', '.join(user_context['held_tickers'])}")
    if user_context.get("watchlist"):
        ctx_lines.append(f"Watchlist: {', '.join(user_context['watchlist'])}")
    if user_context.get("preferences"):
        prefs = user_context["preferences"]
        ctx_lines.append(
            f"Preferences: max position {prefs.get('max_position_pct', 5)}%, "
            f"max sector {prefs.get('max_sector_pct', 25)}%"
        )
    # Entity registry context (recently discussed tickers)
    if user_context.get("entity_context"):
        ctx_lines.append(user_context["entity_context"])
    if user_context.get("resolved_pronouns"):
        tickers = ", ".join(user_context["resolved_pronouns"])
        ctx_lines.append(f"Pronoun resolution: user likely refers to {tickers}")

    ctx_str = "\n".join(ctx_lines) if ctx_lines else "No portfolio data available."

    return (
        template.replace("{{query}}", query)
        .replace("{{tools_description}}", tools_description)
        .replace("{{user_context}}", ctx_str)
    )


def parse_plan_response(response_text: str) -> dict[str, Any]:
    """Parse the LLM's JSON plan response.

    Handles common LLM quirks: markdown code fences, trailing text.

    Args:
        response_text: Raw LLM response text.

    Returns:
        Parsed plan dict with intent, steps, skip_synthesis, reasoning.

    Raises:
        ValueError: If the response cannot be parsed as a valid plan.
    """
    text = response_text.strip()

    # Strip markdown code fences
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first line (```json) and last line (```)
        lines = [line for line in lines if not line.strip().startswith("```")]
        text = "\n".join(lines).strip()

    try:
        plan = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse planner response as JSON: {e}") from e

    # Validate required fields
    intent = plan.get("intent")
    if intent not in VALID_INTENTS:
        raise ValueError(f"Invalid intent '{intent}'. Must be one of: {VALID_INTENTS}")

    # Normalize
    plan.setdefault("steps", [])
    plan.setdefault("skip_synthesis", False)
    plan.setdefault("reasoning", "")

    # Validate steps
    for i, step in enumerate(plan["steps"]):
        if "tool" not in step:
            raise ValueError(f"Step {i} missing 'tool' key")
        step.setdefault("params", {})

    # Cap at 10 steps
    if len(plan["steps"]) > 10:
        logger.warning("plan_truncated", extra={"original_steps": len(plan["steps"])})
        plan["steps"] = plan["steps"][:10]

    return plan


async def plan_query(
    query: str,
    tools_description: str,
    user_context: dict[str, Any],
    llm_chat: Any,
) -> dict[str, Any]:
    """Generate a tool execution plan for a user query.

    Args:
        query: The user's natural language query.
        tools_description: Formatted tool descriptions from the registry.
        user_context: Dict from build_user_context().
        llm_chat: Callable async function(messages, tools) -> LLMResponse.

    Returns:
        Parsed plan dict with intent, steps, skip_synthesis, reasoning.
    """
    prompt = build_planner_prompt(query, tools_description, user_context)

    messages = [
        {"role": "user", "content": prompt},
    ]

    response = await llm_chat(messages=messages, tools=[])

    return parse_plan_response(response.content)
