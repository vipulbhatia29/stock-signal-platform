"""Mechanical executor for Agent V2 — runs tool plan without LLM.

Executes each step from the planner's plan in order, resolving
$PREV_RESULT references, validating results, and handling failures
with retries and a circuit breaker.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone
from typing import Any

from backend.agents.result_validator import validate_tool_result
from backend.tools.base import ToolResult

logger = logging.getLogger(__name__)

# Executor limits
MAX_TOOL_CALLS = 10
WALL_CLOCK_TIMEOUT_S = 45.0
MAX_RETRIES = 1
CIRCUIT_BREAKER_THRESHOLD = 3

# Regex for $PREV_RESULT references
_PREV_REF = re.compile(r"\$PREV_RESULT(?:\.(\w+))?")


def _resolve_prev_result(
    value: Any,
    prev_results: list[dict[str, Any]],
) -> Any:
    """Resolve $PREV_RESULT references in a parameter value.

    Supports:
      - $PREV_RESULT → data from last successful result
      - $PREV_RESULT.ticker → specific key from last result's data
      - $PREV_RESULT.0.ticker → specific key from list item

    Args:
        value: The parameter value (may contain $PREV_RESULT).
        prev_results: List of validated results from prior steps.

    Returns:
        Resolved value, or original if no reference found.
    """
    if not isinstance(value, str) or "$PREV_RESULT" not in value:
        return value

    # Find the last successful result with data
    last_data = None
    for r in reversed(prev_results):
        if r.get("status") == "ok" and r.get("data") is not None:
            last_data = r["data"]
            break

    if last_data is None:
        return value

    def _replace(match: re.Match) -> str:
        path = match.group(1)
        if path is None:
            # $PREV_RESULT with no path
            return str(last_data)

        # Walk the path
        current = last_data
        # If data is a list, default to first element for key access
        if isinstance(current, list) and current:
            current = current[0]

        for segment in path.split("."):
            if isinstance(current, dict) and segment in current:
                current = current[segment]
            elif isinstance(current, list):
                try:
                    idx = int(segment)
                    current = current[idx]
                except (IndexError, ValueError):
                    # Try first element for key access on list
                    if current and isinstance(current[0], dict) and segment in current[0]:
                        current = current[0][segment]
                    else:
                        return match.group(0)
            else:
                return match.group(0)
        return str(current)

    return _PREV_REF.sub(_replace, value)


def _resolve_params(
    params: dict[str, Any],
    prev_results: list[dict[str, Any]],
) -> dict[str, Any]:
    """Resolve all $PREV_RESULT references in a step's params."""
    return {k: _resolve_prev_result(v, prev_results) for k, v in params.items()}


async def execute_plan(
    steps: list[dict[str, Any]],
    tool_executor: Any,
    on_step: Any | None = None,
) -> dict[str, Any]:
    """Execute a tool plan mechanically (no LLM).

    Args:
        steps: List of plan steps from the planner.
        tool_executor: Callable(tool_name, params) -> ToolResult.
        on_step: Optional async callback(step_index, tool_name, status)
            for streaming progress events.

    Returns:
        Dict with:
          - results: list of validated tool results
          - needs_replan: bool (if search returned empty)
          - timed_out: bool
          - circuit_broken: bool
          - tool_calls: int
    """
    results: list[dict[str, Any]] = []
    consecutive_failures = 0
    tool_calls = 0
    needs_replan = False
    timed_out = False
    circuit_broken = False
    start_time = time.monotonic()

    for i, step in enumerate(steps[:MAX_TOOL_CALLS]):
        # Wall clock timeout
        elapsed = time.monotonic() - start_time
        if elapsed >= WALL_CLOCK_TIMEOUT_S:
            logger.warning(
                "executor_timeout",
                extra={"elapsed": elapsed, "completed_steps": i},
            )
            timed_out = True
            break

        tool_name = step["tool"]
        raw_params = step.get("params", {})
        params = _resolve_params(raw_params, results)

        # Execute with retry
        result: ToolResult | None = None
        for attempt in range(1 + MAX_RETRIES):
            try:
                result = await tool_executor(tool_name, params)
                break
            except Exception as e:
                logger.warning(
                    "executor_tool_error",
                    extra={
                        "tool": tool_name,
                        "attempt": attempt + 1,
                        "error": str(e),
                    },
                )
                if attempt == MAX_RETRIES:
                    result = ToolResult(status="error", error=str(e))

        tool_calls += 1

        # Validate result
        validated = validate_tool_result(
            result or ToolResult(status="error", error="No result"),
            tool_name,
            timestamp=datetime.now(timezone.utc),
        )
        results.append(validated)

        # Emit step progress
        if on_step is not None:
            try:
                await on_step(i, tool_name, validated["status"])
            except Exception:
                pass

        # Track consecutive failures for circuit breaker
        if validated["status"] in ("unavailable", "error"):
            consecutive_failures += 1
            if consecutive_failures >= CIRCUIT_BREAKER_THRESHOLD:
                logger.warning(
                    "executor_circuit_breaker",
                    extra={"failures": consecutive_failures},
                )
                circuit_broken = True
                break
        else:
            consecutive_failures = 0

        # Check for replan signal (empty search results)
        if (
            tool_name == "search_stocks"
            and validated["status"] == "ok"
            and isinstance(validated.get("data"), list)
            and len(validated["data"]) == 0
        ):
            needs_replan = True
            break

    return {
        "results": results,
        "needs_replan": needs_replan,
        "timed_out": timed_out,
        "circuit_broken": circuit_broken,
        "tool_calls": tool_calls,
    }
