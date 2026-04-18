"""ObservedHttpClient — httpx.AsyncClient subclass that emits observability events.

Every HTTP call made through ObservedHttpClient is wrapped with:
- Monotonic latency timing
- HTTP status classification → ErrorReason
- Transport-error classification (timeout, connection refused)
- Rate-limit header parsing (X-RateLimit-*)
- Non-blocking event emission via ObservabilityClient.emit_sync

**Critical safety invariant:** emission failures MUST NEVER mask the real HTTP
response or exception.  All emission code is wrapped in a broad try/except that
logs and swallows.

Design note: We subclass ``httpx.AsyncClient`` and override ``send()`` rather
than using a custom transport.  This lets us pass an ``ObservedHttpClient``
directly as the ``http_client=`` parameter accepted by the OpenAI, Anthropic,
and Groq SDKs, which all accept an ``httpx.AsyncClient`` instance.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import httpx
from uuid_utils import uuid7

from backend.config import settings
from backend.observability.bootstrap import _maybe_get_obs_client
from backend.observability.context import current_span_id, current_trace_id
from backend.observability.instrumentation.providers import ErrorReason, ExternalProvider
from backend.observability.schema.external_api_events import ExternalApiCallEvent
from backend.observability.schema.v1 import EventType

logger = logging.getLogger(__name__)

# Headers that carry rate-limit metadata — checked in order.
_RATE_LIMIT_HEADERS = frozenset(
    {
        "x-ratelimit-limit",
        "x-ratelimit-remaining",
        "x-ratelimit-reset",
        "x-ratelimit-reset-requests",
        "x-ratelimit-reset-tokens",
        "ratelimit-limit",
        "ratelimit-remaining",
        "ratelimit-reset",
        "retry-after",
    }
)


def _map_env(environment: str) -> str:
    """Map settings.ENVIRONMENT to the ObsEventBase env literal.

    Args:
        environment: Value from ``settings.ENVIRONMENT`` (e.g. "development").

    Returns:
        One of "dev", "staging", or "prod".
    """
    mapping: dict[str, str] = {
        "development": "dev",
        "dev": "dev",
        "staging": "staging",
        "production": "prod",
        "prod": "prod",
    }
    return mapping.get(environment.lower(), "dev")


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


def _parse_rate_limit_headers(headers: httpx.Headers) -> dict[str, str]:
    """Extract rate-limit related headers from a response.

    Args:
        headers: httpx response headers.

    Returns:
        Dict of lowercased header name → value for all recognised rate-limit headers.
    """
    return {
        name.lower(): value
        for name, value in headers.items()
        if name.lower() in _RATE_LIMIT_HEADERS
    }


def _parse_rate_limit_remaining(rl_headers: dict[str, str]) -> int | None:
    """Parse X-RateLimit-Remaining or ratelimit-remaining from headers.

    Args:
        rl_headers: Normalised rate-limit header dict from _parse_rate_limit_headers.

    Returns:
        Integer remaining count, or None if not present or not parseable.
    """
    for key in ("x-ratelimit-remaining", "ratelimit-remaining"):
        raw = rl_headers.get(key)
        if raw is not None:
            try:
                return int(raw)
            except ValueError:
                pass
    return None


def _parse_rate_limit_reset_ts(rl_headers: dict[str, str]) -> datetime | None:
    """Parse X-RateLimit-Reset from headers as a tz-aware UTC datetime.

    Providers encode this as a Unix epoch int/float.  Returns None when the
    header is absent or the value is not a valid epoch number.

    Args:
        rl_headers: Normalised rate-limit header dict.

    Returns:
        UTC datetime, or None.
    """
    for key in ("x-ratelimit-reset", "ratelimit-reset", "x-ratelimit-reset-requests"):
        raw = rl_headers.get(key)
        if raw is not None:
            try:
                return datetime.fromtimestamp(float(raw), tz=timezone.utc)
            except (ValueError, OSError, OverflowError):
                pass
    return None


class ObservedHttpClient(httpx.AsyncClient):
    """httpx.AsyncClient subclass that emits an EXTERNAL_API_CALL event per request.

    Instantiate with a provider tag; all other kwargs are forwarded to
    ``httpx.AsyncClient.__init__``.  The ``send()`` override is transparent —
    callers see the same ``httpx.Response`` (or the same exception) as if they
    were using a plain ``httpx.AsyncClient``.

    Args:
        provider: The ExternalProvider enum member identifying the upstream service.
        **kwargs: Forwarded to ``httpx.AsyncClient.__init__``.

    Example::

        client = ObservedHttpClient(provider=ExternalProvider.OPENAI)
        response = await client.get("https://api.openai.com/v1/models")
    """

    def __init__(self, provider: ExternalProvider, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._provider = provider

    async def send(self, request: httpx.Request, **kwargs: Any) -> httpx.Response:
        """Wrap httpx.AsyncClient.send() with latency timing and event emission.

        The real response (or exception) is ALWAYS returned/raised.  Emission
        errors are silently swallowed — they MUST NOT mask real HTTP errors.

        Args:
            request: The prepared httpx.Request to send.
            **kwargs: Forwarded to ``httpx.AsyncClient.send()``.

        Returns:
            The httpx.Response from the upstream server.

        Raises:
            httpx.TimeoutException: On request timeout (re-raised after emission).
            httpx.ConnectError: On connection failure (re-raised after emission).
            Any other httpx transport-level exception (re-raised after emission).
        """
        start = time.monotonic()
        response: httpx.Response | None = None
        error_reason: str | None = None
        exc_to_raise: BaseException | None = None

        try:
            response = await super().send(request, **kwargs)
            error_reason = _classify_status(response.status_code)
        except httpx.TimeoutException as exc:
            error_reason = ErrorReason.TIMEOUT.value
            exc_to_raise = exc
        except httpx.ConnectError as exc:
            error_reason = ErrorReason.CONNECTION_REFUSED.value
            exc_to_raise = exc
        except Exception as exc:
            # Unexpected transport errors — do not classify, re-raise.
            exc_to_raise = exc
        finally:
            latency_ms = int((time.monotonic() - start) * 1000)
            self._emit_event(
                request=request,
                response=response,
                error_reason=error_reason,
                latency_ms=latency_ms,
            )

        if exc_to_raise is not None:
            raise exc_to_raise

        # response is not None here (assigned before any exception path above).
        assert response is not None  # noqa: S101 — type narrowing for pyright
        return response

    def _emit_event(
        self,
        *,
        request: httpx.Request,
        response: httpx.Response | None,
        error_reason: str | None,
        latency_ms: int,
    ) -> None:
        """Build and emit an ExternalApiCallEvent — NEVER raises.

        Wrapped entirely in a broad try/except so that any bug in event
        construction cannot surface as an HTTP error to the caller.

        Args:
            request: The original httpx.Request.
            response: The httpx.Response, or None on transport error.
            error_reason: ErrorReason value string, or None for success.
            latency_ms: Call duration in milliseconds.
        """
        try:
            obs_client = _maybe_get_obs_client()
            if obs_client is None:
                return

            # --- Envelope fields ---
            ambient_trace = current_trace_id()
            trace_id: UUID = (
                ambient_trace if ambient_trace is not None else UUID(bytes=uuid7().bytes)
            )
            span_id: UUID = UUID(bytes=uuid7().bytes)
            parent_span_id: UUID | None = current_span_id()

            env_str = _map_env(settings.ENVIRONMENT)
            git_sha: str | None = getattr(settings, "GIT_SHA", None)

            # --- Request metadata ---
            url = request.url
            endpoint = url.path or "/"
            method = request.method.upper()

            # Request body size from Content-Length header.
            request_bytes: int | None = None
            raw_content_length = request.headers.get("content-length")
            if raw_content_length is not None:
                try:
                    request_bytes = int(raw_content_length)
                except ValueError:
                    pass

            # --- Response metadata ---
            status_code: int | None = None
            response_bytes: int | None = None
            rl_headers: dict[str, str] = {}
            rate_limit_remaining: int | None = None
            rate_limit_reset_ts: datetime | None = None

            if response is not None:
                status_code = response.status_code
                raw_resp_cl = response.headers.get("content-length")
                if raw_resp_cl is not None:
                    try:
                        response_bytes = int(raw_resp_cl)
                    except ValueError:
                        pass
                rl_headers = _parse_rate_limit_headers(response.headers)
                rate_limit_remaining = _parse_rate_limit_remaining(rl_headers)
                rate_limit_reset_ts = _parse_rate_limit_reset_ts(rl_headers)

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
                provider=self._provider.value,
                endpoint=endpoint,
                method=method,
                status_code=status_code,
                error_reason=error_reason,
                latency_ms=latency_ms,
                request_bytes=request_bytes,
                response_bytes=response_bytes,
                rate_limit_headers=rl_headers if rl_headers else None,
                rate_limit_remaining=rate_limit_remaining,
                rate_limit_reset_ts=rate_limit_reset_ts,
            )
            obs_client.emit_sync(event)

        except Exception:  # noqa: BLE001 — emission MUST NOT mask HTTP errors
            logger.warning("obs.external_api.emit_failed", exc_info=True)


def build_observed_http_client(provider: ExternalProvider, **kwargs: Any) -> ObservedHttpClient:
    """Factory for SDK integrations — each call returns a new ObservedHttpClient.

    Unlike ``get_http_client()`` which is a singleton, each call returns a fresh
    instance.  Timeout and limit defaults mirror the shared client defaults for
    consistency.

    Args:
        provider: The ExternalProvider enum member for the upstream service.
        **kwargs: Forwarded to ``httpx.AsyncClient.__init__`` (timeout, limits, …).

    Returns:
        A new ObservedHttpClient configured for the given provider.

    Example::

        client = build_observed_http_client(ExternalProvider.ANTHROPIC, timeout=60.0)
    """
    return ObservedHttpClient(provider=provider, **kwargs)
