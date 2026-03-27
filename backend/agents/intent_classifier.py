"""Rule-based intent classifier with ticker extraction for the stock analysis agent.

Classifies user queries into intent categories before routing to the appropriate
agent path. Uses regex-based rules with deterministic confidence=1.0.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from backend.agents.guards import detect_injection

logger = logging.getLogger(__name__)

# ── Ticker extraction ─────────────────────────────────────────────────────────

_TICKER_RE = re.compile(r"\b([A-Z]{1,5})\b")

_STOP_WORDS: frozenset[str] = frozenset(
    {
        "AND",
        "THE",
        "FOR",
        "ARE",
        "HOW",
        "BUT",
        "ALL",
        "CAN",
        "VS",
        "NOT",
        "HIS",
        "HER",
        "WHO",
        "MAY",
        "ITS",
        "HAS",
        "WAS",
        "GET",
        "LET",
        "SET",
        "NEW",
        "OLD",
        "ANY",
        "FEW",
    }
)

_MAX_COMPARISON_TICKERS = 3


def _extract_tickers(query: str) -> list[str]:
    """Extract uppercase ticker-like tokens from query, excluding stop words.

    Args:
        query: Raw user query string.

    Returns:
        Ordered list of unique ticker candidates, preserving first-seen order.
    """
    seen: dict[str, None] = {}
    for match in _TICKER_RE.finditer(query):
        token = match.group(1)
        if token not in _STOP_WORDS and token not in seen:
            seen[token] = None
    return list(seen)


# ── Out-of-scope keyword detection ───────────────────────────────────────────

_OOS_KEYWORDS = re.compile(
    r"\b("
    r"weather|forecast\s+for\s+(tomorrow|today|week)|temperature|rain|snow|humidity"
    r"|history\s+of\s+(?!stock|share|trading)|world\s+war|ancient|medieval|roman\s+empire"
    r"|geography|capital\s+of|continent|country\s+of"
    r"|write\s+(me\s+)?(a\s+)?(python|javascript|java|code|script|function|program)"
    r"|debug\s+(this\s+)?(code|script|function)"
    r"|recipe|cook|bake|ingredient"
    r"|poem|song\s+lyrics|write\s+a\s+story"
    r")\b",
    re.IGNORECASE,
)

# ── Intent keyword patterns ───────────────────────────────────────────────────

_PRICE_KEYWORDS = re.compile(
    r"\b(price|quote|trading\s+at|current\s+value|stock\s+price|share\s+price|how\s+much\s+is)\b",
    re.IGNORECASE,
)

_COMPARISON_KEYWORDS = re.compile(
    r"\b(compare|vs\.?|versus)\b",
    re.IGNORECASE,
)

_PORTFOLIO_KEYWORDS = re.compile(
    r"\b(portfolio|holdings|positions?|rebalance|my\s+stocks?|my\s+holdings?|my\s+biggest\s+(position|holding))\b",
    re.IGNORECASE,
)

_MARKET_KEYWORDS = re.compile(
    r"\b(market|sectors?|S&P|briefing|overview|market\s+overview|market\s+briefing)\b",
    re.IGNORECASE,
)

_ANALYSIS_KEYWORDS = re.compile(
    r"\b(analy[sz]e|analysis|deep\s+dive|fundamental|technical|recommend|buy|sell|hold|valuation|signal|score|breakdown)\b",
    re.IGNORECASE,
)

_PRONOUN_KEYWORDS = re.compile(
    r"\b(it|its|this\s+stock|that\s+stock|what\s+about\s+it)\b",
    re.IGNORECASE,
)

_DECLINE_MESSAGE = (
    "I can only help with stock analysis, portfolio insights, and market information. "
    "Please ask me about stocks, investments, or financial markets."
)


# ── ClassifiedIntent ──────────────────────────────────────────────────────────


@dataclass
class ClassifiedIntent:
    """Result of rule-based intent classification.

    Attributes:
        intent: Classified intent category.
        tickers: Extracted ticker symbols (max 3 for comparison).
        fast_path: If True, bypass the LangGraph agent entirely.
        confidence: Always 1.0 for rule-based classifier; reserved for future LLM fallback.
        decline_message: Human-readable decline reason for out_of_scope intents.
    """

    intent: str
    tickers: list[str] = field(default_factory=list)
    fast_path: bool = False
    confidence: float = 1.0
    decline_message: str | None = None


# ── Main classifier ───────────────────────────────────────────────────────────


def classify_intent(
    query: str,
    held_tickers: list[str] | None = None,
    entity_context: list[str] | None = None,
) -> ClassifiedIntent:
    """Classify the user query into an intent category with extracted tickers.

    Rules are evaluated in priority order:
    1. Empty query → out_of_scope
    2. Out-of-scope keywords (weather, geography, code) → out_of_scope, fast_path=True
    3. Injection patterns → out_of_scope, fast_path=True
    4. Simple lookup (price keywords + single ticker, or bare ticker)
       → simple_lookup, fast_path=True
    5. Comparison ("compare"/"vs"/"versus" + 2+ tickers) → comparison
    6. Portfolio keywords or held_ticker references → portfolio
    7. Market/sector keywords → market
    8. Single ticker + analysis keywords → stock
    9. Fallback → general

    Args:
        query: Raw user message.
        held_tickers: Tickers the user currently holds; used to resolve
            possessive phrases like "my biggest holding".
        entity_context: Tickers mentioned in recent conversation turns; used
            to resolve pronoun references like "What about it?".

    Returns:
        ClassifiedIntent with intent, tickers, fast_path, confidence, and
        optional decline_message.
    """
    held_tickers = held_tickers or []
    entity_context = entity_context or []

    stripped = query.strip()

    # ── Rule 1: empty query ───────────────────────────────────────────────────
    if not stripped:
        logger.debug("classify_intent: empty query → out_of_scope")
        return ClassifiedIntent(
            intent="out_of_scope",
            fast_path=True,
            decline_message=_DECLINE_MESSAGE,
        )

    tickers = _extract_tickers(stripped)

    # ── Rule 2: out-of-scope keywords ─────────────────────────────────────────
    if _OOS_KEYWORDS.search(stripped):
        logger.debug("classify_intent: OOS keyword match → out_of_scope")
        return ClassifiedIntent(
            intent="out_of_scope",
            fast_path=True,
            decline_message=_DECLINE_MESSAGE,
        )

    # ── Rule 3: injection ─────────────────────────────────────────────────────
    if detect_injection(stripped):
        logger.debug("classify_intent: injection detected → out_of_scope")
        return ClassifiedIntent(
            intent="out_of_scope",
            fast_path=True,
            decline_message=_DECLINE_MESSAGE,
        )

    # ── Pronoun resolution ────────────────────────────────────────────────────
    # If the query is a pronoun reference and we have entity context, inject
    # the prior ticker so downstream rules can match.
    if not tickers and _PRONOUN_KEYWORDS.search(stripped) and entity_context:
        tickers = [entity_context[-1]]
        logger.debug(
            "classify_intent: pronoun resolved to entity_context ticker %s",
            tickers[0],
        )

    # ── Rule 4: simple lookup ─────────────────────────────────────────────────
    if len(tickers) == 1 and _PRICE_KEYWORDS.search(stripped):
        logger.debug("classify_intent: price keyword + single ticker → simple_lookup")
        return ClassifiedIntent(
            intent="simple_lookup",
            tickers=tickers,
            fast_path=True,
        )

    # Bare single ticker (no other intent signals)
    if len(tickers) == 1 and stripped == tickers[0]:
        logger.debug("classify_intent: bare single ticker → simple_lookup")
        return ClassifiedIntent(
            intent="simple_lookup",
            tickers=tickers,
            fast_path=True,
        )

    # ── Rule 5: comparison ────────────────────────────────────────────────────
    if _COMPARISON_KEYWORDS.search(stripped) and len(tickers) >= 2:
        capped = tickers[:_MAX_COMPARISON_TICKERS]
        logger.debug("classify_intent: comparison → %s", capped)
        return ClassifiedIntent(
            intent="comparison",
            tickers=capped,
        )

    # Also treat 2+ tickers without explicit comparison keyword as comparison
    if len(tickers) >= 2:
        capped = tickers[:_MAX_COMPARISON_TICKERS]
        logger.debug("classify_intent: multiple tickers → comparison %s", capped)
        return ClassifiedIntent(
            intent="comparison",
            tickers=capped,
        )

    # ── Rule 6: portfolio ─────────────────────────────────────────────────────
    if _PORTFOLIO_KEYWORDS.search(stripped):
        resolved = tickers if tickers else held_tickers
        logger.debug("classify_intent: portfolio keyword → portfolio")
        return ClassifiedIntent(
            intent="portfolio",
            tickers=resolved,
        )

    # Possessive held_ticker references without explicit portfolio keyword
    _POSSESSIVE_RE = re.compile(r"\bmy\b", re.IGNORECASE)
    if _POSSESSIVE_RE.search(stripped) and held_tickers and not tickers:
        logger.debug("classify_intent: 'my' + held_tickers → portfolio")
        return ClassifiedIntent(
            intent="portfolio",
            tickers=held_tickers,
        )

    # ── Rule 7: market ────────────────────────────────────────────────────────
    if _MARKET_KEYWORDS.search(stripped):
        logger.debug("classify_intent: market keyword → market")
        return ClassifiedIntent(
            intent="market",
            tickers=tickers,
        )

    # ── Rule 8: stock analysis ────────────────────────────────────────────────
    if len(tickers) == 1 and _ANALYSIS_KEYWORDS.search(stripped):
        logger.debug("classify_intent: analysis keyword + single ticker → stock")
        return ClassifiedIntent(
            intent="stock",
            tickers=tickers,
        )

    # Single ticker with no specific intent signals → stock
    if len(tickers) == 1:
        logger.debug("classify_intent: single ticker (no price kw) → stock")
        return ClassifiedIntent(
            intent="stock",
            tickers=tickers,
        )

    # ── Rule 9: general fallback ──────────────────────────────────────────────
    logger.debug("classify_intent: no rules matched → general")
    return ClassifiedIntent(
        intent="general",
        tickers=tickers,
    )
