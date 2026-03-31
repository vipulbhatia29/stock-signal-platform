"""PII sanitization utility for safe logging and observability output."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_BLOCKED_KEYS: frozenset[str] = frozenset(
    {"user_id", "email", "password", "token", "api_key", "secret", "authorization"}
)

_EMAIL_RE: re.Pattern[str] = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")


def _redact_structure(obj: Any) -> Any:
    """Recursively walk dict/list and redact values for blocked keys.

    Args:
        obj: Arbitrary nested structure to sanitize.

    Returns:
        A new structure with PII values replaced by ``[REDACTED]``.
    """
    if isinstance(obj, dict):
        return {
            k: "[REDACTED]" if k in _BLOCKED_KEYS else _redact_structure(v) for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_redact_structure(item) for item in obj]
    return obj


def sanitize_summary(raw: Any, max_length: int = 300) -> str:
    """Sanitize an arbitrary value into a safe, truncated string for logging.

    Accepts any input type (dict, list, str, None, or other).  PII fields are
    redacted in-structure before serialization; email addresses in string
    values are masked with a regex pass on the final serialized string.

    Sanitization order:
    1. Structural redaction — blocked keys replaced with ``[REDACTED]``.
    2. Email regex — occurrences of ``user@host.tld`` replaced with ``[EMAIL]``.
    3. JSON serialization.
    4. Truncation to *max_length* characters.

    Args:
        raw: Any value to sanitize.  Dicts and lists are processed
            structurally; a plain string is attempted as JSON first, then
            treated as literal text.  ``None`` and non-serializable types are
            handled gracefully.
        max_length: Maximum character length of the returned string.
            Defaults to 300.

    Returns:
        A sanitized, truncated string safe for log output or observability
        ingestion.  Returns ``"[SANITIZE_ERROR]"`` if an unexpected error
        occurs during processing.
    """
    try:
        # Normalise input to a structure we can walk
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                # Plain text — skip structural redaction, apply email regex only
                masked = _EMAIL_RE.sub("[EMAIL]", raw)
                return masked[:max_length]
        else:
            parsed = raw

        # Structural redaction (dicts and lists)
        redacted = _redact_structure(parsed)

        # Serialize to string
        try:
            serialized = json.dumps(redacted)
        except (TypeError, ValueError):
            serialized = str(redacted)

        # Email regex pass on the serialized string
        sanitized = _EMAIL_RE.sub("[EMAIL]", serialized)

        return sanitized[:max_length]

    except Exception:
        logger.exception("Unexpected error in sanitize_summary")
        return "[SANITIZE_ERROR]"
