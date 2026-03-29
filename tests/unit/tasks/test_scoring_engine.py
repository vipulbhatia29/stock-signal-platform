"""Tests for the 5-dimension scoring engine.

TDD — tests written before implementation.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from backend.tasks.golden_dataset import GoldenQuery
from backend.tasks.scoring_engine import (
    score_external_resilience,
    score_grounding,
    score_query,
    score_reasoning_coherence,
    score_termination,
    score_tool_selection,
)

# ── Tool Selection ────────────────────────────────────────────────────────────


def test_tool_selection_pass() -> None:
    """Expected tools are a subset of actual tools called."""
    expected = frozenset({"analyze_stock", "get_fundamentals"})
    actual = {"analyze_stock", "get_fundamentals"}
    assert score_tool_selection(expected, actual) is True


def test_tool_selection_fail() -> None:
    """Missing an expected tool returns False."""
    expected = frozenset({"analyze_stock", "get_fundamentals"})
    actual = {"analyze_stock"}
    assert score_tool_selection(expected, actual) is False


def test_tool_selection_superset_ok() -> None:
    """Extra tools beyond expected is fine — still passes."""
    expected = frozenset({"analyze_stock"})
    actual = {"analyze_stock", "get_fundamentals", "search_stocks"}
    assert score_tool_selection(expected, actual) is True


# ── Grounding ─────────────────────────────────────────────────────────────────


def test_grounding_all_present() -> None:
    """All grounding checks found → 1.0."""
    response = "AAPL has a composite score of 8.5 out of 10."
    checks = ("AAPL", "score")
    assert score_grounding(response, checks) == 1.0


def test_grounding_partial() -> None:
    """Only 1 of 2 checks found → 0.5."""
    response = "The stock looks interesting."
    checks = ("AAPL", "stock")
    assert score_grounding(response, checks) == 0.5


def test_grounding_none() -> None:
    """No checks found → 0.0."""
    response = "I don't have that information."
    checks = ("AAPL", "score")
    assert score_grounding(response, checks) == 0.0


def test_grounding_case_insensitive() -> None:
    """Case-insensitive matching: 'AAPL' matches 'aapl'."""
    response = "aapl is trading at $150."
    checks = ("AAPL",)
    assert score_grounding(response, checks) == 1.0


# ── Termination ───────────────────────────────────────────────────────────────


def test_termination_pass() -> None:
    """Within iteration budget, no consecutive duplicates."""
    tools_called = ["analyze_stock", "get_fundamentals", "compare_stocks"]
    assert score_termination(iterations=3, max_expected=4, tools_called=tools_called) is True


def test_termination_too_many_iterations() -> None:
    """Exceeded iteration budget → False."""
    tools_called = ["analyze_stock", "get_fundamentals"]
    assert score_termination(iterations=5, max_expected=3, tools_called=tools_called) is False


def test_termination_consecutive_duplicates() -> None:
    """Consecutive duplicate tool calls → False."""
    tools_called = ["analyze_stock", "analyze_stock", "get_fundamentals"]
    assert score_termination(iterations=2, max_expected=4, tools_called=tools_called) is False


# ── External Resilience ───────────────────────────────────────────────────────


def test_resilience_no_failures() -> None:
    """Empty mock_failures always returns True."""
    assert score_external_resilience("Any response text", {}) is True


def test_resilience_hallucination_detected() -> None:
    """Response contains specific data for a failed tool → False."""
    response = "The stock price is $152.34 with a P/E ratio of 28.5%."
    mock_failures = {"get_stock_price": "API timeout"}
    assert score_external_resilience(response, mock_failures) is False


# ── Reasoning Coherence (LLM-as-Judge) ────────────────────────────────────────


@pytest.mark.asyncio
async def test_reasoning_coherence_happy_path() -> None:
    """Mock LLM returns '4' → score is 4.0."""
    mock_llm = AsyncMock(return_value="4 - The response logically connects outputs.")
    score = await score_reasoning_coherence(
        response="AAPL looks strong based on fundamentals.",
        tool_outputs=["analyze_stock returned score 8.5"],
        llm_chat=mock_llm,
    )
    assert score == 4.0
    mock_llm.assert_awaited_once()


@pytest.mark.asyncio
async def test_reasoning_coherence_error() -> None:
    """LLM raises exception → returns 0.0 (fail-safe)."""
    mock_llm = AsyncMock(side_effect=RuntimeError("LLM unavailable"))
    score = await score_reasoning_coherence(
        response="Some response.",
        tool_outputs=["some output"],
        llm_chat=mock_llm,
    )
    assert score == 0.0


# ── Aggregate score_query ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_score_query_non_reasoning() -> None:
    """Aggregate scorer for a non-reasoning query (no LLM judge)."""
    golden = GoldenQuery(
        query_text="Analyze AAPL stock",
        intent_category="stock",
        expected_tools=frozenset({"analyze_stock"}),
        expected_route="stock",
        grounding_checks=("AAPL", "score"),
        max_iterations=3,
        is_reasoning=False,
        mock_failures={},
    )
    result = await score_query(
        golden=golden,
        response="AAPL has a composite score of 8.5.",
        tools_called=["analyze_stock", "get_fundamentals"],
        iterations=2,
    )
    assert result["tool_selection"] is True
    assert result["grounding"] == 1.0
    assert result["termination"] is True
    assert result["external_resilience"] is True
    assert result["reasoning_coherence"] is None


@pytest.mark.asyncio
async def test_score_query_reasoning() -> None:
    """Aggregate scorer for a reasoning query includes LLM judge."""
    golden = GoldenQuery(
        query_text="Why is AAPL a good investment?",
        intent_category="stock",
        expected_tools=frozenset({"analyze_stock"}),
        expected_route="stock",
        grounding_checks=("AAPL",),
        max_iterations=4,
        is_reasoning=True,
        mock_failures={},
    )
    mock_llm = AsyncMock(return_value="5 - Excellent coherence")
    result = await score_query(
        golden=golden,
        response="AAPL is a strong buy because of solid fundamentals.",
        tools_called=["analyze_stock"],
        iterations=2,
        llm_chat=mock_llm,
    )
    assert result["tool_selection"] is True
    assert result["grounding"] == 1.0
    assert result["termination"] is True
    assert result["external_resilience"] is True
    assert result["reasoning_coherence"] == 5.0
