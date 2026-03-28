"""Agent guardrails — input sanitization, injection detection, PII redaction, output validation.

All functions are pure (no DB calls, no async). Called by chat router
and synthesizer to enforce safety before/after LLM calls.
"""

from __future__ import annotations

import logging
import re

from backend.validation import TICKER_RE

logger = logging.getLogger(__name__)

# ── Input length ─────────────────────────────────────────────────────────────

MAX_MESSAGE_LENGTH = 2000


def validate_input_length(message: str) -> str | None:
    """Returns error message if too long, None if OK."""
    if len(message) > MAX_MESSAGE_LENGTH:
        return f"Message too long ({len(message)} chars). Maximum is {MAX_MESSAGE_LENGTH}."
    return None


# ── Control character stripping ──────────────────────────────────────────────

_CONTROL_CHARS = re.compile(
    r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f"
    r"\u200b-\u200f"
    r"\u2028-\u2029"
    r"\u202a-\u202e"
    r"\u2060-\u2064"
    r"\ufeff"
    r"\ufff9-\ufffb]"
)


def sanitize_input(message: str) -> str:
    """Strip invisible/control characters from user message."""
    return _CONTROL_CHARS.sub("", message).strip()


# ── Prompt injection detection ───────────────────────────────────────────────

_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(a|an)\s+", re.IGNORECASE),
    re.compile(r"system\s*:\s*", re.IGNORECASE),
    re.compile(r"```\s*system", re.IGNORECASE),
    re.compile(r"(show|reveal|print|display)\s+(.+\s+)?prompt", re.IGNORECASE),
    re.compile(r"(forget|disregard|override)\s+(everything|all|your)", re.IGNORECASE),
    re.compile(r"act\s+as\s+(if\s+)?(you\s+)?(are|were)\s+", re.IGNORECASE),
    re.compile(r"pretend\s+(you\s+)?(are|to\s+be)\s+", re.IGNORECASE),
    re.compile(r"new\s+instructions?\s*:", re.IGNORECASE),
    re.compile(r"<\s*/?\s*system\s*>", re.IGNORECASE),
]


def detect_injection(message: str) -> bool:
    """Returns True if message matches known injection patterns."""
    return any(pattern.search(message) for pattern in _INJECTION_PATTERNS)


# ── PII detection and redaction ──────────────────────────────────────────────

_PII_PATTERNS = {
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "credit_card": re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b"),
    "phone": re.compile(r"\b(?:\+1[-\s]?)?\(?\d{3}\)?[-\s]?\d{3}[-\s]?\d{4}\b"),
}


def detect_and_strip_pii(message: str) -> tuple[str, list[str]]:
    """Strip PII from message. Returns (cleaned_message, list_of_pii_types_found)."""
    found: list[str] = []
    cleaned = message
    for pii_type, pattern in _PII_PATTERNS.items():
        if pattern.search(cleaned):
            found.append(pii_type)
            cleaned = pattern.sub(f"[{pii_type.upper()}_REDACTED]", cleaned)
    return cleaned, found


# ── Output validation ────────────────────────────────────────────────────────


def validate_synthesis_output(synthesis: dict) -> dict:
    """Post-process synthesis to enforce evidence requirements."""
    confidence = synthesis.get("confidence", 0)
    evidence = synthesis.get("evidence", [])

    if confidence >= 0.65 and not evidence:
        synthesis["confidence"] = 0.50
        synthesis["confidence_label"] = "medium"
        gaps = synthesis.get("gaps", [])
        gaps.append("Confidence downgraded: no tool evidence to support claims")
        synthesis["gaps"] = gaps

    return synthesis


# ── Tool parameter validation ────────────────────────────────────────────────

MAX_QUERY_LENGTH = 200

TICKER_TOOLS = frozenset(
    {
        "analyze_stock",
        "get_fundamentals",
        "get_forecast",
        "get_analyst_targets",
        "get_earnings_history",
        "get_company_profile",
        "compare_stocks",
        "dividend_sustainability",
        "risk_narrative",
        "ingest_stock",
        "get_stock_intelligence",
    }
)

SEARCH_TOOLS = frozenset({"web_search", "search_stocks"})


def validate_ticker(ticker: str) -> str | None:
    """Returns error message if ticker format is invalid."""
    if not ticker or not TICKER_RE.match(ticker):
        return f"Invalid ticker format: '{ticker}'"
    return None


def validate_search_query(query: str) -> str | None:
    """Returns error message if search query is suspicious."""
    if len(query) > MAX_QUERY_LENGTH:
        return f"Search query too long ({len(query)} chars)"
    if re.search(r"https?://", query):
        return "URLs are not allowed in search queries"
    return None


# ── Financial disclaimer ─────────────────────────────────────────────────────

DISCLAIMER = (
    "\n\n---\n*This is AI-generated analysis based on available data, "
    "not investment advice. Always do your own research before making "
    "investment decisions.*"
)
