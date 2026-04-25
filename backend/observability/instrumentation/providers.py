"""External provider and error-reason enumerations for API call observability.

These enums are the canonical vocabulary for classifying outbound HTTP calls
logged in ``observability.external_api_call_log``. They are also used by the
``ObservedHttpClient`` wrapper to populate the ``provider`` and ``error_reason``
columns automatically.

Usage::

    from backend.observability.instrumentation.providers import ExternalProvider, ErrorReason

    provider = ExternalProvider.YFINANCE
    reason = ErrorReason.RATE_LIMIT_429
"""

from __future__ import annotations

import logging
from enum import Enum

logger = logging.getLogger(__name__)


class ExternalProvider(str, Enum):
    """Canonical names for external services called by the platform.

    String enum so values serialise cleanly to/from JSON and database TEXT columns
    without extra conversion steps.

    Attributes:
        YFINANCE: Yahoo Finance data library (wraps finance.yahoo.com).
        FINNHUB: Finnhub.io market-data REST API.
        EDGAR: SEC EDGAR XBRL/filing REST API.
        FRED: Federal Reserve Economic Data (FRED) REST API.
        GOOGLE_NEWS: Google News RSS / scrape endpoint.
        OPENAI: OpenAI Chat Completions and Embeddings API.
        ANTHROPIC: Anthropic Messages API (Claude models).
        GROQ: Groq fast-inference API.
        RESEND: Resend transactional email API.
        GOOGLE_OAUTH: Google OAuth 2.0 token and user-info endpoints.
        JIRA: Atlassian JIRA Cloud REST API.
    """

    YFINANCE = "yfinance"
    FINNHUB = "finnhub"
    EDGAR = "edgar"
    FRED = "fred"
    GOOGLE_NEWS = "google_news"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GROQ = "groq"
    RESEND = "resend"
    GOOGLE_OAUTH = "google_oauth"
    JIRA = "jira"


class ErrorReason(str, Enum):
    """Structured classification of outbound-call failures.

    Used as the ``error_reason`` value in ``external_api_call_log`` rows.
    String enum so values serialise cleanly to/from JSON and database TEXT columns.

    Attributes:
        RATE_LIMIT_429: Provider returned HTTP 429 Too Many Requests.
        SERVER_ERROR_5XX: Provider returned an HTTP 5xx server error.
        CLIENT_ERROR_4XX: Provider returned a non-429 HTTP 4xx client error.
        TIMEOUT: The request exceeded the configured timeout.
        CONNECTION_REFUSED: TCP connection was refused or DNS resolution failed.
        MALFORMED_RESPONSE: Response body could not be parsed as expected.
        AUTH_FAILURE: Provider returned 401/403 (invalid API key or insufficient scope).
        CIRCUIT_OPEN: Internal circuit breaker is open; call was not attempted.
    """

    RATE_LIMIT_429 = "rate_limit_429"
    SERVER_ERROR_5XX = "server_error_5xx"
    CLIENT_ERROR_4XX = "client_error_4xx"
    TIMEOUT = "timeout"
    CONNECTION_REFUSED = "connection_refused"
    MALFORMED_RESPONSE = "malformed_response"
    AUTH_FAILURE = "auth_failure"
    CIRCUIT_OPEN = "circuit_open"
