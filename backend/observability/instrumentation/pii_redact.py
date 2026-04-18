"""PII redaction for observability event fields.

Shared by all 1b instrumentation layers. Gated by OBS_REDACT_PII config.
"""

from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from backend.config import settings

# Whitelisted URL query params (safe to store)
_SAFE_PARAMS = {"page", "limit", "sort", "ticker", "tab", "order", "q", "status", "type"}

# PII patterns for message redaction
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_JWT_RE = re.compile(r"eyJ[a-zA-Z0-9_-]+\.eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+")
_CC_RE = re.compile(r"\b\d{13,19}\b")


def redact_url(url: str) -> str:
    """Redact non-whitelisted query params from URL.

    Args:
        url: URL string to redact.

    Returns:
        URL with non-whitelisted query params replaced by "REDACTED".
        Returns url unchanged if OBS_REDACT_PII is False or no query string.
    """
    if not settings.OBS_REDACT_PII:
        return url
    parsed = urlparse(url)
    if not parsed.query:
        return url
    params = parse_qs(parsed.query, keep_blank_values=True)
    redacted = {k: v if k in _SAFE_PARAMS else ["REDACTED"] for k, v in params.items()}
    return urlunparse(parsed._replace(query=urlencode(redacted, doseq=True)))


def redact_message(msg: str) -> str:
    """Redact common PII patterns from error messages.

    Args:
        msg: Message string to redact.

    Returns:
        Message with emails replaced by [EMAIL], JWTs by [JWT], and
        credit card-like numbers by [REDACTED]. Returns msg unchanged if
        OBS_REDACT_PII is False or msg is empty/None.
    """
    if not settings.OBS_REDACT_PII or not msg:
        return msg
    msg = _EMAIL_RE.sub("[EMAIL]", msg)
    msg = _JWT_RE.sub("[JWT]", msg)
    msg = _CC_RE.sub("[REDACTED]", msg)
    return msg


def hash_email(email: str) -> str:
    """SHA256 hash of lowercased email for pseudonymization.

    Args:
        email: Email address to hash.

    Returns:
        64-char hex SHA-256 digest of the lowercased email.
    """
    return hashlib.sha256(email.lower().encode()).hexdigest()
