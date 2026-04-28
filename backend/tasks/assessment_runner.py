"""Assessment runner — executes golden dataset against agent, scores, persists results.

Provides ``run_assessment()`` which iterates over the golden dataset,
runs each query through the ReAct agent (or a dry-run stub), scores the
response with the scoring engine, and writes ``AssessmentRun`` +
``AssessmentResult`` rows to the database.

CLI usage::

    uv run python -m backend.tasks.assessment_runner            # live run
    uv run python -m backend.tasks.assessment_runner --dry-run   # skip LLM calls
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select

import backend.database as _db
from backend.models.assessment import AssessmentResult, AssessmentRun
from backend.models.portfolio import Portfolio, Position
from backend.models.stock import Stock
from backend.models.user import User
from backend.tasks.golden_dataset import GOLDEN_DATASET, GoldenQuery
from backend.tasks.scoring_engine import score_query

logger = logging.getLogger(__name__)

_RESULTS_FILE = Path("assessment-results.json")

# ── Dry-run stubs ────────────────────────────────────────────────────────────

# Maps intent_category to (response_text, tools_called, iterations).
# Used in dry-run mode to test scoring logic without LLM calls.
_DRY_RUN_RESPONSES: dict[str, tuple[str, list[str], int]] = {
    "stock": (
        "AAPL has a composite score of 8.2. The fundamentals look solid.",
        ["analyze_stock", "get_fundamentals"],
        2,
    ),
    "portfolio": (
        "Your portfolio is well-diversified. Total exposure across 3 positions.",
        ["get_portfolio_exposure", "portfolio_health"],
        2,
    ),
    "market": (
        "The market is showing mixed signals today.",
        ["market_briefing"],
        1,
    ),
    "comparison": (
        "Comparing AAPL and MSFT: both are strong but differ in growth trajectory.",
        ["analyze_stock", "compare_stocks"],
        3,
    ),
    "forecast": (
        "TSLA forecast shows moderate upside potential over the next 30 days.",
        ["get_forecast"],
        1,
    ),
    "recommendation": (
        "Based on your portfolio, I recommend considering defensive positions.",
        ["recommend_stocks"],
        2,
    ),
    "dividend": (
        "AAPL's dividend payout ratio is sustainable at current levels.",
        ["dividend_sustainability"],
        1,
    ),
    "risk": (
        "NVDA faces concentration risk in the AI chip market.",
        ["risk_narrative", "analyze_stock"],
        2,
    ),
    "intelligence": (
        "GOOGL has recent news about cloud computing growth.",
        ["get_stock_intelligence"],
        1,
    ),
    "reasoning": (
        "After analyzing both AAPL and MSFT, considering your portfolio "
        "exposure and growth potential, I recommend holding AAPL and adding "
        "to MSFT for better diversification.",
        ["analyze_stock", "get_portfolio_exposure", "compare_stocks"],
        4,
    ),
}

# Failure variants return a graceful degradation message (no hallucinated numbers).
_DRY_RUN_FAILURE_RESPONSE = (
    "I was unable to retrieve the requested data due to a service issue. Please try again later.",
    [],
    1,
)


def _get_dry_run_response(
    golden: GoldenQuery,
) -> tuple[str, list[str], int]:
    """Return a predetermined response for dry-run mode.

    Args:
        golden: The golden query being tested.

    Returns:
        Tuple of (response_text, tools_called, iterations).
    """
    if golden.is_failure_variant:
        # For failure variants, return tools that were attempted but failed
        return (
            _DRY_RUN_FAILURE_RESPONSE[0],
            list(golden.expected_tools),
            _DRY_RUN_FAILURE_RESPONSE[2],
        )

    base = _DRY_RUN_RESPONSES.get(golden.intent_category)
    if base is not None:
        return base

    # Fallback: return expected tools with generic response
    return (
        f"Analysis complete for: {golden.query_text}",
        list(golden.expected_tools),
        2,
    )


# ── Test user seeding ────────────────────────────────────────────────────────

_TEST_EMAIL = "assessment@stocksignal.test"
_TEST_POSITIONS = [
    ("AAPL", Decimal("10"), Decimal("150.00")),
    ("MSFT", Decimal("5"), Decimal("300.00")),
    ("GOOGL", Decimal("8"), Decimal("140.00")),
]


async def _ensure_stocks_exist(session: Any) -> None:
    """Ensure required stock tickers exist in the stocks table.

    Args:
        session: Async SQLAlchemy session.
    """
    for ticker, _, _ in _TEST_POSITIONS:
        result = await session.execute(select(Stock).where(Stock.ticker == ticker))
        if result.scalar_one_or_none() is None:
            session.add(
                Stock(
                    ticker=ticker,
                    name=f"{ticker} Inc.",
                    is_active=True,
                )
            )
    await session.flush()


async def _seed_test_user(session: Any) -> User:
    """Create or retrieve the assessment test user with portfolio and positions.

    Idempotent — reuses existing user if found.

    Args:
        session: Async SQLAlchemy session.

    Returns:
        The test User object.
    """
    # Lazy import to avoid circular dependency at module level
    from backend.dependencies import hash_password

    result = await session.execute(select(User).where(User.email == _TEST_EMAIL))
    user = result.scalar_one_or_none()

    if user is not None:
        logger.info("Reusing existing assessment test user: %s", user.id)
        return user

    # Ensure stock tickers exist (FK constraint)
    await _ensure_stocks_exist(session)

    user = User(
        email=_TEST_EMAIL,
        hashed_password=hash_password("assessment-runner-dummy-pw"),
        is_active=True,
    )
    session.add(user)
    await session.flush()

    portfolio = Portfolio(user_id=user.id, name="Assessment Portfolio")
    session.add(portfolio)
    await session.flush()

    now = datetime.now(timezone.utc)
    for ticker, shares, cost in _TEST_POSITIONS:
        session.add(
            Position(
                portfolio_id=portfolio.id,
                ticker=ticker,
                shares=shares,
                avg_cost_basis=cost,
                opened_at=now,
            )
        )
    await session.flush()

    logger.info("Seeded assessment test user: %s", user.id)
    return user


# ── Live agent execution ─────────────────────────────────────────────────────


async def _run_query_live(
    golden: GoldenQuery,
    user: User,
    session: Any,
) -> tuple[str, list[str], int, uuid.UUID]:
    """Run a single query through the live ReAct agent.

    Args:
        golden: The golden query to execute.
        user: The test user for context.
        session: Async SQLAlchemy session.

    Returns:
        Tuple of (response_text, tools_called, iterations, query_id).
    """
    from backend.request_context import current_query_id

    query_id = uuid.uuid4()
    current_query_id.set(query_id)

    # Lazy imports — only needed for live runs, avoids requiring LLM keys on import
    from backend.agents.react_loop import react_loop
    from backend.tools.registry import ToolRegistry

    registry = ToolRegistry()
    tool_schemas = registry.get_tool_schemas()

    tools_called: list[str] = []
    response_parts: list[str] = []
    iterations = 0

    async def _tool_executor(name: str, params: dict[str, Any]) -> Any:
        """Execute a tool, injecting mock failures if specified."""
        from backend.tools.base import ToolResult

        if golden.mock_failures and name in golden.mock_failures:
            return ToolResult(error=golden.mock_failures[name])
        return await registry.execute(name, params, session=session, user_id=user.id)

    async def _llm_chat(
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> Any:
        """Proxy to the LLM client."""
        nonlocal iterations
        iterations += 1
        from backend.agents.llm_client import LLMClient

        client = LLMClient()
        return await client.chat(messages=messages, tools=tools)

    user_context: dict[str, Any] = {
        "positions": [{"ticker": t, "shares": str(s)} for t, s, _ in _TEST_POSITIONS],
    }

    async for event in react_loop(
        query=golden.query_text,
        session_messages=[],
        tools=tool_schemas,
        tool_executor=_tool_executor,
        llm_chat=_llm_chat,
        user_context=user_context,
        max_iterations=golden.max_iterations,
    ):
        if event.type == "tool_start":
            if event.metadata and "tool" in event.metadata:
                tools_called.append(event.metadata["tool"])
        elif event.type == "token":
            response_parts.append(event.content or "")
        elif event.type == "tool_result":
            if event.metadata and "tool" in event.metadata:
                if event.metadata["tool"] not in tools_called:
                    tools_called.append(event.metadata["tool"])

    response_text = "".join(response_parts)
    return response_text, tools_called, iterations, query_id


# ── Core runner ──────────────────────────────────────────────────────────────


async def run_assessment(
    trigger: str = "local",
    dry_run: bool = False,
) -> dict[str, Any]:
    """Execute the full golden dataset assessment.

    Creates an AssessmentRun, iterates over all golden queries, scores each,
    persists results, and writes a JSON summary.

    Args:
        trigger: Source of the run (local, ci, scheduled).
        dry_run: If True, use predetermined responses instead of LLM calls.

    Returns:
        Summary dict with run_id, pass counts, and per-query results.
    """
    run_id = uuid.uuid4()
    started_at = datetime.now(timezone.utc)
    results: list[dict[str, Any]] = []
    deterministic_failures = 0
    reasoning_scores: list[float] = []

    logger.info(
        "Starting assessment run %s (trigger=%s, dry_run=%s, queries=%d)",
        run_id,
        trigger,
        dry_run,
        len(GOLDEN_DATASET),
    )

    async with _db.async_session_factory() as session:
        user = await _seed_test_user(session)
        await session.commit()

        for idx, golden in enumerate(GOLDEN_DATASET):
            query_start = time.monotonic()
            logger.info(
                "Running query %d/%d: %s",
                idx + 1,
                len(GOLDEN_DATASET),
                golden.query_text[:60],
            )

            try:
                if dry_run:
                    response_text, tools_called, iterations = _get_dry_run_response(golden)
                    query_id = uuid.uuid4()  # dry run: generate placeholder
                else:
                    response_text, tools_called, iterations, query_id = await _run_query_live(
                        golden, user, session
                    )
            except Exception:
                logger.exception("Query %d failed during execution", idx + 1)
                response_text = ""
                tools_called = []
                iterations = 0
                query_id = uuid.uuid4()  # error fallback

            duration_ms = int((time.monotonic() - query_start) * 1000)

            # Score
            scores = await score_query(
                golden=golden,
                response=response_text,
                tools_called=tools_called,
                iterations=iterations,
                llm_chat=None,  # Skip LLM-as-judge for now
            )

            # Determine pass/fail based on deterministic scores
            tool_ok = bool(scores["tool_selection"])
            grounding_ok = scores["grounding"] >= 0.8
            termination_ok = bool(scores["termination"])
            resilience_ok = bool(scores["external_resilience"])
            passed = tool_ok and grounding_ok and termination_ok and resilience_ok

            if not passed:
                deterministic_failures += 1

            if scores["reasoning_coherence"] is not None:
                reasoning_scores.append(float(scores["reasoning_coherence"]))

            # Persist result
            result_row = AssessmentResult(
                run_id=run_id,
                query_index=idx + 1,
                query_text=golden.query_text,
                intent_category=golden.intent_category,
                agent_type="react_v2",
                tool_selection_pass=tool_ok,
                grounding_score=float(scores["grounding"]),
                termination_pass=termination_ok,
                external_resilience_pass=resilience_ok if golden.is_failure_variant else None,
                reasoning_coherence_score=(
                    float(scores["reasoning_coherence"])
                    if scores["reasoning_coherence"] is not None
                    else None
                ),
                tools_called={"tools": tools_called},
                iteration_count=iterations,
                total_cost_usd=0.0,
                total_duration_ms=duration_ms,
                query_id=query_id,
            )
            session.add(result_row)

            results.append(
                {
                    "query": golden.query_text,
                    "category": golden.intent_category,
                    "tool_selection": tool_ok,
                    "grounding": float(scores["grounding"]),
                    "termination": termination_ok,
                    "external_resilience": resilience_ok,
                    "reasoning_coherence": scores["reasoning_coherence"],
                    "passed": passed,
                }
            )

            logger.info(
                "Query %d/%d: passed=%s (tools=%s ground=%.1f term=%s resil=%s)",
                idx + 1,
                len(GOLDEN_DATASET),
                passed,
                tool_ok,
                float(scores["grounding"]),
                termination_ok,
                resilience_ok,
            )

        # Aggregate stats
        total = len(GOLDEN_DATASET)
        passed_count = total - deterministic_failures
        pass_rate = passed_count / total if total > 0 else 0.0
        avg_reasoning = sum(reasoning_scores) / len(reasoning_scores) if reasoning_scores else None
        completed_at = datetime.now(timezone.utc)

        # Persist run
        run_row = AssessmentRun(
            id=run_id,
            trigger=trigger,
            total_queries=total,
            passed_queries=passed_count,
            pass_rate=pass_rate,
            total_cost_usd=0.0,
            started_at=started_at,
            completed_at=completed_at,
        )
        session.add(run_row)
        await session.commit()

    # Build summary
    summary: dict[str, Any] = {
        "run_id": str(run_id),
        "trigger": trigger,
        "total_queries": total,
        "passed": passed_count,
        "failed": deterministic_failures,
        "all_passed": deterministic_failures == 0,
        "deterministic_pass_rate": round(pass_rate, 2),
        "avg_reasoning_coherence": round(avg_reasoning, 1) if avg_reasoning is not None else None,
        "results": results,
    }

    # Write to file
    try:
        _RESULTS_FILE.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        logger.info("Assessment results written to %s", _RESULTS_FILE)
    except OSError:
        logger.exception("Failed to write assessment results file")

    # Print to stdout
    print(json.dumps(summary, indent=2))  # noqa: T201

    logger.info(
        "Assessment complete: %d/%d passed (%.0f%%)",
        passed_count,
        total,
        pass_rate * 100,
    )

    return summary


# ── CLI entry point ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import asyncio
    import sys

    parser = argparse.ArgumentParser(description="Run agent quality assessment")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip LLM calls; use predetermined responses for scoring logic tests",
    )
    parser.add_argument(
        "--trigger",
        default="local",
        help="Run trigger label (local, ci, scheduled)",
    )
    args = parser.parse_args()

    result = asyncio.run(run_assessment(trigger=args.trigger, dry_run=args.dry_run))
    sys.exit(0 if result.get("all_passed", False) else 1)
