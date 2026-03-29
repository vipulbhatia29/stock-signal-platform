"""Golden dataset for agent quality assessment.

Defines 20 canonical queries (10 intent + 4 reasoning + 3 failure + 2 behavioral + 1 cross-domain)
used by the assessment runner to evaluate agent accuracy, tool selection, routing,
and error handling. Each query specifies the expected route, tools, grounding
checks, and iteration budget so the scoring engine can compute pass/fail metrics.

This module is pure data — no I/O, no side effects. Safe to import anywhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class GoldenQuery:
    """A single golden query for agent assessment.

    Attributes:
        query_text: The user query to send to the agent.
        intent_category: Semantic category (stock, portfolio, market, etc.).
        expected_tools: Tools the agent SHOULD call for this query.
        expected_route: The intent classifier route (stock/portfolio/market/
            comparison/simple_lookup/general).
        grounding_checks: Substrings that MUST appear in the response.
        max_iterations: Max ReAct loop iterations expected.
        is_reasoning: Whether this is a reasoning query (scored by LLM judge).
        is_failure_variant: Whether this tests error handling.
        mock_failures: Tool name to error message mapping for failure simulation.
    """

    query_text: str
    intent_category: str
    expected_tools: frozenset[str]
    expected_route: str
    grounding_checks: tuple[str, ...]
    max_iterations: int
    is_reasoning: bool = False
    is_failure_variant: bool = False
    mock_failures: dict[str, str] = field(default_factory=dict)


# ── 10 Intent-based queries ──────────────────────────────────────────────────

_Q01_ANALYZE_AAPL = GoldenQuery(
    query_text="Analyze AAPL stock",
    intent_category="stock",
    expected_tools=frozenset({"analyze_stock", "get_fundamentals"}),
    expected_route="stock",
    grounding_checks=("AAPL", "score"),
    max_iterations=3,
)

_Q02_PORTFOLIO = GoldenQuery(
    query_text="How is my portfolio doing?",
    intent_category="portfolio",
    expected_tools=frozenset({"get_portfolio_exposure", "portfolio_health"}),
    expected_route="portfolio",
    grounding_checks=("portfolio",),
    max_iterations=3,
)

_Q03_MARKET_BRIEFING = GoldenQuery(
    query_text="Give me a market briefing",
    intent_category="market",
    expected_tools=frozenset({"market_briefing"}),
    expected_route="market",
    grounding_checks=("market",),
    max_iterations=2,
)

_Q04_COMPARE = GoldenQuery(
    query_text="Compare AAPL and MSFT",
    intent_category="comparison",
    expected_tools=frozenset({"analyze_stock", "compare_stocks"}),
    expected_route="comparison",
    grounding_checks=("AAPL", "MSFT"),
    max_iterations=4,
)

_Q05_FORECAST = GoldenQuery(
    query_text="What's the forecast for TSLA?",
    intent_category="forecast",
    expected_tools=frozenset({"get_forecast"}),
    expected_route="stock",
    grounding_checks=("TSLA", "forecast"),
    max_iterations=2,
)

_Q06_RECOMMEND = GoldenQuery(
    query_text="What should I buy for my portfolio?",
    intent_category="recommendation",
    expected_tools=frozenset({"recommend_stocks"}),
    expected_route="portfolio",
    grounding_checks=("recommend",),
    max_iterations=3,
)

_Q07_DIVIDEND = GoldenQuery(
    query_text="Is AAPL's dividend sustainable?",
    intent_category="dividend",
    expected_tools=frozenset({"dividend_sustainability"}),
    expected_route="stock",
    grounding_checks=("AAPL", "dividend"),
    max_iterations=2,
)

_Q08_RISK = GoldenQuery(
    query_text="What are the risks of holding NVDA?",
    intent_category="risk",
    expected_tools=frozenset({"risk_narrative", "analyze_stock"}),
    expected_route="stock",
    grounding_checks=("NVDA", "risk"),
    max_iterations=3,
)

_Q09_INTELLIGENCE = GoldenQuery(
    query_text="Any news on GOOGL?",
    intent_category="intelligence",
    expected_tools=frozenset({"get_stock_intelligence"}),
    expected_route="stock",
    grounding_checks=("GOOGL",),
    max_iterations=2,
)

_Q10_SCORECARD = GoldenQuery(
    query_text="How accurate have your recent recommendations been?",
    intent_category="reasoning",
    expected_tools=frozenset({"get_recommendation_scorecard"}),
    expected_route="general",
    grounding_checks=("recommendation", "accuracy"),
    max_iterations=2,
)

# ── 4 Reasoning queries (LLM judge scored) ──────────────────────────────────

_Q11_SELL_VS_BUY = GoldenQuery(
    query_text="Should I sell AAPL and buy MSFT instead?",
    intent_category="reasoning",
    expected_tools=frozenset({"analyze_stock", "get_portfolio_exposure", "compare_stocks"}),
    expected_route="portfolio",
    grounding_checks=("AAPL", "MSFT"),
    max_iterations=5,
    is_reasoning=True,
)

_Q12_BEST_GROWTH = GoldenQuery(
    query_text="Which of my holdings has the best growth potential?",
    intent_category="reasoning",
    expected_tools=frozenset({"get_portfolio_exposure", "get_forecast", "analyze_stock"}),
    expected_route="portfolio",
    grounding_checks=("growth", "portfolio"),
    max_iterations=5,
    is_reasoning=True,
)

_Q13_DEFENSIVE = GoldenQuery(
    query_text="Build me a defensive portfolio for a recession",
    intent_category="reasoning",
    expected_tools=frozenset({"recommend_stocks", "market_briefing", "risk_narrative"}),
    expected_route="general",
    grounding_checks=("defensive", "recession"),
    max_iterations=5,
    is_reasoning=True,
)

_Q14_INTEREST_RATES = GoldenQuery(
    query_text="If interest rates rise, which of my stocks are most at risk?",
    intent_category="reasoning",
    expected_tools=frozenset(
        {"get_portfolio_exposure", "risk_narrative", "get_stock_intelligence"}
    ),
    expected_route="portfolio",
    grounding_checks=("interest rate", "risk"),
    max_iterations=5,
    is_reasoning=True,
)

# ── 3 Failure variants ──────────────────────────────────────────────────────

_Q15_ANALYZE_FAIL = GoldenQuery(
    query_text="Analyze AAPL stock",
    intent_category="stock",
    expected_tools=frozenset({"analyze_stock", "get_fundamentals"}),
    expected_route="stock",
    grounding_checks=("AAPL",),
    max_iterations=3,
    is_failure_variant=True,
    mock_failures={"analyze_stock": "API timeout"},
)

_Q16_BRIEFING_FAIL = GoldenQuery(
    query_text="Give me a market briefing",
    intent_category="market",
    expected_tools=frozenset({"market_briefing"}),
    expected_route="market",
    grounding_checks=("market",),
    max_iterations=2,
    is_failure_variant=True,
    mock_failures={"market_briefing": "Service unavailable"},
)

_Q17_FORECAST_FAIL = GoldenQuery(
    query_text="What's the forecast for TSLA?",
    intent_category="forecast",
    expected_tools=frozenset({"get_forecast"}),
    expected_route="stock",
    grounding_checks=("TSLA",),
    max_iterations=2,
    is_failure_variant=True,
    mock_failures={"get_forecast": "No forecast available"},
)

# ── Behavioral queries (spec Q8, Q9) ────────────────────────────────────────

_Q18_OUT_OF_SCOPE = GoldenQuery(
    query_text="Write me a poem about stocks",
    intent_category="out_of_scope",
    expected_tools=frozenset(),  # zero tool calls — decline path
    expected_route="general",
    grounding_checks=("can't", "sorry", "unable", "don't"),
    max_iterations=0,
)

_Q19_PRONOUN_FOLLOWUP = GoldenQuery(
    query_text="What about its dividends?",
    intent_category="dividend",
    expected_tools=frozenset({"dividend_sustainability"}),
    expected_route="stock",
    grounding_checks=("dividend",),
    max_iterations=2,
)

# ── Cross-domain queries (spec Q15, Q16) ────────────────────────────────────

_Q20_DIVIDEND_DEEP_DIVE = GoldenQuery(
    query_text="Is AAPL's dividend sustainable long term?",
    intent_category="dividend",
    expected_tools=frozenset({"dividend_sustainability", "get_fundamentals"}),
    expected_route="stock",
    grounding_checks=("AAPL", "dividend"),
    max_iterations=3,
    is_reasoning=True,
)

# ── Immutable dataset ────────────────────────────────────────────────────────

GOLDEN_DATASET: tuple[GoldenQuery, ...] = (
    _Q01_ANALYZE_AAPL,
    _Q02_PORTFOLIO,
    _Q03_MARKET_BRIEFING,
    _Q04_COMPARE,
    _Q05_FORECAST,
    _Q06_RECOMMEND,
    _Q07_DIVIDEND,
    _Q08_RISK,
    _Q09_INTELLIGENCE,
    _Q10_SCORECARD,
    _Q11_SELL_VS_BUY,
    _Q12_BEST_GROWTH,
    _Q13_DEFENSIVE,
    _Q14_INTEREST_RATES,
    _Q15_ANALYZE_FAIL,
    _Q16_BRIEFING_FAIL,
    _Q17_FORECAST_FAIL,
    _Q18_OUT_OF_SCOPE,
    _Q19_PRONOUN_FOLLOWUP,
    _Q20_DIVIDEND_DEEP_DIVE,
)
