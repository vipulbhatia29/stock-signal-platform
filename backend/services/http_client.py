"""Shared async HTTP connection pool.

Single httpx.AsyncClient instance reused across all providers and tools.
Avoids per-request TCP connection + TLS handshake overhead.

``get_observed_http_client`` returns a new ``ObservedHttpClient`` per call —
it is NOT a singleton, unlike ``get_http_client``.  Use it when you want
automatic EXTERNAL_API_CALL event emission for a specific provider.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from backend.observability.instrumentation.external_api import ObservedHttpClient
    from backend.observability.instrumentation.providers import ExternalProvider

_client: httpx.AsyncClient | None = None

_DEFAULT_TIMEOUT = 30.0
_DEFAULT_LIMITS = httpx.Limits(max_connections=100, max_keepalive_connections=20)


def get_http_client() -> httpx.AsyncClient:
    """Return the shared async HTTP client.

    Lazily creates the client if startup_http_client() hasn't been called yet
    (e.g. in test fixtures that skip the full lifespan).

    Returns:
        The module-level httpx.AsyncClient singleton. Caller must NOT close it.
    """
    global _client  # noqa: PLW0603
    if _client is None:
        _client = httpx.AsyncClient(
            timeout=_DEFAULT_TIMEOUT,
            limits=_DEFAULT_LIMITS,
        )
    return _client


async def startup_http_client() -> None:
    """Initialise the shared HTTP client on application startup."""
    global _client  # noqa: PLW0603
    if _client is None:
        _client = httpx.AsyncClient(
            timeout=_DEFAULT_TIMEOUT,
            limits=_DEFAULT_LIMITS,
        )


async def shutdown_http_client() -> None:
    """Close the shared HTTP client on application shutdown."""
    global _client  # noqa: PLW0603
    if _client is not None:
        await _client.aclose()
        _client = None


def get_observed_http_client(provider: ExternalProvider, **kwargs: object) -> ObservedHttpClient:
    """Return a new ObservedHttpClient tagged with the given provider.

    Unlike ``get_http_client()`` which returns a module-level singleton, this
    function returns a *new* client on every call.  Callers that pass the client
    to an SDK (e.g. ``openai.AsyncOpenAI(http_client=...)``) own the lifecycle
    and should close it when done.

    Timeout and connection-limit defaults mirror the shared singleton so that
    observed clients behave consistently with the rest of the platform.

    Args:
        provider: The ExternalProvider enum member for the upstream service.
        **kwargs: Optional overrides forwarded to ``httpx.AsyncClient.__init__``
            (e.g. ``timeout=60.0``).

    Returns:
        A fresh ObservedHttpClient for the specified provider.

    Example::

        client = get_observed_http_client(ExternalProvider.OPENAI)
        openai_sdk = openai.AsyncOpenAI(http_client=client, api_key=settings.OPENAI_API_KEY)
    """
    from backend.observability.instrumentation.external_api import build_observed_http_client

    kwargs.setdefault("timeout", _DEFAULT_TIMEOUT)
    kwargs.setdefault("limits", _DEFAULT_LIMITS)
    return build_observed_http_client(provider, **kwargs)
