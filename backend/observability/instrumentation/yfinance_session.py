"""Observed session for yfinance — emits EXTERNAL_API_CALL events.

yfinance >= 1.0 switched from ``requests`` to ``curl_cffi`` for HTTP.  This
module detects which backend is active and subclasses the right session type
so the ``session=`` argument to ``yf.Ticker()`` / ``yf.download()`` still
works and every HTTP call is instrumented with an observability event.

Usage::

    from backend.observability.instrumentation.yfinance_session import get_yfinance_session
    import yfinance as yf

    session = get_yfinance_session()
    ticker = yf.Ticker("AAPL", session=session)

**Critical safety invariant:** emission failures MUST NEVER break the actual
yfinance call — all emission code is wrapped in a broad try/except that logs
and swallows.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from uuid_utils import uuid7

from backend.config import settings
from backend.observability.bootstrap import _maybe_get_obs_client
from backend.observability.context import current_span_id, current_trace_id
from backend.observability.instrumentation.providers import ErrorReason, ExternalProvider
from backend.observability.schema.external_api_events import ExternalApiCallEvent
from backend.observability.schema.v1 import EventType

logger = logging.getLogger(__name__)

_ENV_MAPPING: dict[str, str] = {
    "development": "dev",
    "dev": "dev",
    "staging": "staging",
    "production": "prod",
    "prod": "prod",
}

# ---------------------------------------------------------------------------
# Detect which HTTP backend yfinance uses
# ---------------------------------------------------------------------------
_USE_CURL_CFFI: bool = False
try:
    from curl_cffi.requests import Session as CurlSession  # noqa: F401
    from yfinance.data import YfData  # noqa: F401

    _USE_CURL_CFFI = True
except ImportError:
    pass

if _USE_CURL_CFFI:
    from curl_cffi.requests import Session as _BaseSession
else:
    import requests

    _BaseSession = requests.Session  # type: ignore[assignment,misc]


def _classify_status(status_code: int) -> str | None:
    """Return an ErrorReason value for an HTTP status code, or None on success.

    Args:
        status_code: HTTP response status code.

    Returns:
        ErrorReason string value, or None for 1xx/2xx/3xx responses.
    """
    if status_code == 429:
        return ErrorReason.RATE_LIMIT_429.value
    if status_code in (401, 403):
        return ErrorReason.AUTH_FAILURE.value
    if 400 <= status_code < 500:
        return ErrorReason.CLIENT_ERROR_4XX.value
    if status_code >= 500:
        return ErrorReason.SERVER_ERROR_5XX.value
    return None


def _emit_event(
    method: str,
    url: str,
    response: Any | None,
    error_reason: str | None,
    latency_ms: int,
) -> None:
    """Build and emit an ExternalApiCallEvent — NEVER raises.

    Args:
        method: HTTP verb string.
        url: Full request URL.
        response: Response object (requests or curl_cffi) if available, else None.
        error_reason: ErrorReason value string on failure, or None on success.
        latency_ms: Call duration in milliseconds.
    """
    try:
        obs_client = _maybe_get_obs_client()
        if obs_client is None:
            return

        ambient_trace = current_trace_id()
        trace_id: UUID = ambient_trace if ambient_trace is not None else UUID(bytes=uuid7().bytes)
        span_id: UUID = UUID(bytes=uuid7().bytes)
        parent_span_id: UUID | None = current_span_id()

        env_str = _ENV_MAPPING.get(settings.ENVIRONMENT.lower(), "dev")
        git_sha: str | None = getattr(settings, "GIT_SHA", None)

        try:
            from urllib.parse import urlparse

            parsed = urlparse(url)
            endpoint = parsed.path or "/"
        except Exception:
            endpoint = "/"

        status_code: int | None = None
        if response is not None:
            status_code = response.status_code

        event = ExternalApiCallEvent(
            event_type=EventType.EXTERNAL_API_CALL,
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            ts=datetime.now(timezone.utc),
            env=env_str,  # type: ignore[arg-type]
            git_sha=git_sha,
            user_id=None,
            session_id=None,
            query_id=None,
            provider=ExternalProvider.YFINANCE.value,
            endpoint=endpoint,
            method=method.upper(),
            status_code=status_code,
            error_reason=error_reason,
            latency_ms=latency_ms,
        )
        obs_client.emit_sync(event)

    except Exception:  # noqa: BLE001 — emission MUST NOT mask yfinance errors
        logger.warning("obs.yfinance.emit_failed", exc_info=True)


class YfinanceObservedSession(_BaseSession):  # type: ignore[misc]
    """Session subclass that emits EXTERNAL_API_CALL events per request.

    Automatically subclasses the correct base (``curl_cffi.requests.Session``
    when yfinance uses curl_cffi, otherwise ``requests.Session``).

    When using curl_cffi, the session is initialized with
    ``impersonate="chrome"`` to match yfinance's default TLS fingerprint —
    without this, Yahoo Finance rate-limits the connection.

    Pass an instance as the ``session=`` argument to ``yf.Ticker()`` or
    ``yf.download()`` to instrument all yfinance HTTP traffic.

    All emission is wrapped in try/except — a bug in the observability path
    will never raise an exception visible to yfinance callers.
    """

    def __init__(self, **kwargs: Any) -> None:
        if _USE_CURL_CFFI:
            kwargs.setdefault("impersonate", "chrome")
        super().__init__(**kwargs)

    def request(self, method: Any, url: Any, **kwargs: Any) -> Any:  # type: ignore[override]
        """Wrap the base session's request() with latency timing and event emission.

        Args:
            method: HTTP method string (GET, POST, …).
            url: Request URL.
            **kwargs: Forwarded to the base session's ``request()``.

        Returns:
            The response from the upstream server.

        Raises:
            Any exception raised by the base ``request()`` — re-raised
            after emission so the caller always sees the real error.
        """
        start = time.monotonic()
        response: Any = None
        error_reason: str | None = None

        try:
            response = super().request(method, url, **kwargs)
            error_reason = _classify_status(response.status_code)
            return response
        except Exception as exc:  # noqa: BLE001 — classify then re-raise; emission in finally
            # Classify known error types for observability tagging
            if _USE_CURL_CFFI:
                from curl_cffi.requests.errors import RequestsError  # type: ignore[import-untyped]

                if isinstance(exc, RequestsError) and "timeout" in str(exc).lower():
                    error_reason = ErrorReason.TIMEOUT.value
                else:
                    error_reason = ErrorReason.CONNECTION_REFUSED.value
            else:
                import requests as _req

                if isinstance(exc, _req.Timeout):
                    error_reason = ErrorReason.TIMEOUT.value
                elif isinstance(exc, _req.ConnectionError):
                    error_reason = ErrorReason.CONNECTION_REFUSED.value
            raise
        finally:
            latency_ms = int((time.monotonic() - start) * 1000)
            _url_str = url if isinstance(url, str) else str(url)
            _method_str = method if isinstance(method, str) else str(method)
            _emit_event(_method_str, _url_str, response, error_reason, latency_ms)


_yfinance_session: YfinanceObservedSession | None = None


def get_yfinance_session() -> YfinanceObservedSession:
    """Return a module-level YfinanceObservedSession (lazy singleton).

    The session is created once and reused across all yfinance calls within a
    process.  This mirrors how yfinance itself reuses sessions internally.

    Returns:
        The shared YfinanceObservedSession instance.
    """
    global _yfinance_session  # noqa: PLW0603
    if _yfinance_session is None:
        _yfinance_session = YfinanceObservedSession()
    return _yfinance_session
