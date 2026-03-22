"""LLM-as-Judge — calls a cheap LLM to score agent responses against the rubric."""

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


async def judge_response(
    prompt: str,
    agent_response: str,
    tool_results: list[dict[str, Any]],
    rubric: str,
) -> dict[str, Any] | None:
    """Score an agent response using an LLM judge.

    Args:
        prompt: The original user query.
        agent_response: The agent's final text response.
        tool_results: List of tool execution results (for fact-checking).
        rubric: The scoring rubric prompt text.

    Returns:
        Dict of dimension → score, or None if no API key available.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning("No ANTHROPIC_API_KEY — skipping LLM judge evaluation")
        return None

    try:
        import anthropic
    except ImportError:
        logger.warning("anthropic package not installed — skipping LLM judge")
        return None

    tool_summary = _format_tool_results(tool_results)

    judge_prompt = f"""You are an expert evaluator for a financial AI assistant.

## Task
Evaluate the assistant's response to a user query. Score each dimension per the rubric below.

## User Query
{prompt}

## Tool Results (ground truth data the assistant had access to)
{tool_summary}

## Assistant Response
{agent_response}

{rubric}

## Instructions
Return ONLY a JSON object with dimension keys and numeric scores. Example:
{{"factual_grounding": 4, "hallucination": 1, "actionability": 3, ...}}

Do NOT include any text outside the JSON object."""

    client = anthropic.AsyncAnthropic(api_key=api_key)

    try:
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            messages=[{"role": "user", "content": judge_prompt}],
        )
        content = response.content[0].text.strip()

        # Strip markdown fences if present
        if content.startswith("```"):
            lines = content.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            content = "\n".join(lines)

        scores = json.loads(content)
        return scores

    except Exception:
        logger.exception("LLM judge call failed")
        return None


def _format_tool_results(results: list[dict[str, Any]]) -> str:
    """Format tool results for the judge prompt."""
    if not results:
        return "(No tool results available)"

    lines = []
    for r in results:
        tool = r.get("tool", "unknown")
        status = r.get("status", "unknown")
        data = r.get("data", {})
        # Truncate data to 500 chars for judge context
        data_str = json.dumps(data, default=str)[:500]
        lines.append(f"- **{tool}** [{status}]: {data_str}")
    return "\n".join(lines)
