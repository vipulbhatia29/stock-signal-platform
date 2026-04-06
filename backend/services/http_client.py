"""Shared async HTTP connection pool.

Single httpx.AsyncClient instance reused across all providers and tools.
Avoids per-request TCP connection + TLS handshake overhead.
"""

from __future__ import annotations

import httpx

_client: httpx.AsyncClient | None = None

_DEFAULT_TIMEOUT = 30.0
_DEFAULT_LIMITS = httpx.Limits(max_connections=100, max_keepalive_connections=20)


def get_http_client() -> httpx.AsyncClient:
    """Return the shared async HTTP client.

    Returns:
        The module-level httpx.AsyncClient singleton. Caller must NOT close it.

    Raises:
        RuntimeError: If called before startup_http_client().
    """
    if _client is None:
        raise RuntimeError("HTTP client not initialised — call startup_http_client() first")
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
