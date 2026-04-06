"""Unit tests for ErrorHandlerMiddleware.

Uses httpx.ASGITransport with a minimal FastAPI app to verify the middleware
converts DomainError subclasses into structured JSON responses without leaking
internal details.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI

from backend.exceptions import (
    ConflictError,
    DomainError,
    ResourceNotFoundError,
    ServiceUnavailableError,
    ValidationError,
)
from backend.middleware.error_handler import ErrorHandlerMiddleware
from backend.services.exceptions import (
    DuplicateWatchlistError,
    IngestFailedError,
    PortfolioNotFoundError,
    ServiceError,
    StockNotFoundError,
)

# ---------------------------------------------------------------------------
# Minimal test app
# ---------------------------------------------------------------------------


def _make_app(*routes: tuple[str, Exception]) -> FastAPI:
    """Build a minimal FastAPI app with ErrorHandlerMiddleware.

    Each route raises the provided exception when hit.

    Args:
        routes: Pairs of (path, exception_instance) to register.

    Returns:
        A FastAPI app with the middleware attached.
    """
    app = FastAPI()
    app.add_middleware(ErrorHandlerMiddleware)

    for path, exc in routes:
        # Capture exc in closure — use a factory to avoid late-binding
        def _make_handler(captured: Exception):  # noqa: ANN202
            async def _endpoint() -> None:
                raise captured

            return _endpoint

        app.add_api_route(path, _make_handler(exc), methods=["GET"])

    return app


async def _get(app: FastAPI, path: str) -> httpx.Response:
    """Send a GET request to the test app via ASGITransport.

    Args:
        app: The FastAPI test application.
        path: URL path to request.

    Returns:
        The httpx Response.
    """
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path)


# ---------------------------------------------------------------------------
# DomainError base class
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_domain_error_base_returns_500() -> None:
    """DomainError with default status_code=500 returns 500."""
    app = _make_app(("/err", DomainError()))
    resp = await _get(app, "/err")
    assert resp.status_code == 500
    assert resp.json() == {"detail": "An unexpected error occurred."}


@pytest.mark.asyncio
async def test_domain_error_custom_message() -> None:
    """DomainError safe_message override is passed through."""
    app = _make_app(("/err", DomainError("Custom safe message")))
    resp = await _get(app, "/err")
    assert resp.json()["detail"] == "Custom safe message"


# ---------------------------------------------------------------------------
# DomainError subclasses
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resource_not_found_returns_404() -> None:
    """ResourceNotFoundError returns 404 with safe_message."""
    app = _make_app(("/err", ResourceNotFoundError("No backtest found for ticker")))
    resp = await _get(app, "/err")
    assert resp.status_code == 404
    assert resp.json() == {"detail": "No backtest found for ticker"}


@pytest.mark.asyncio
async def test_validation_error_returns_422() -> None:
    """ValidationError returns 422 with safe_message."""
    app = _make_app(("/err", ValidationError("Invalid ticker format")))
    resp = await _get(app, "/err")
    assert resp.status_code == 422
    assert resp.json() == {"detail": "Invalid ticker format"}


@pytest.mark.asyncio
async def test_conflict_error_returns_409() -> None:
    """ConflictError returns 409 with safe_message."""
    app = _make_app(("/err", ConflictError("Already exists")))
    resp = await _get(app, "/err")
    assert resp.status_code == 409
    assert resp.json() == {"detail": "Already exists"}


@pytest.mark.asyncio
async def test_service_unavailable_returns_503() -> None:
    """ServiceUnavailableError returns 503 with safe_message."""
    app = _make_app(("/err", ServiceUnavailableError()))
    resp = await _get(app, "/err")
    assert resp.status_code == 503
    assert resp.json() == {"detail": "Service temporarily unavailable."}


# ---------------------------------------------------------------------------
# ServiceError subclasses (via DomainError inheritance)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_service_error_caught_by_middleware() -> None:
    """ServiceError (base) is caught by middleware as a DomainError."""
    app = _make_app(("/err", ServiceError()))
    resp = await _get(app, "/err")
    assert resp.status_code == 500
    assert "detail" in resp.json()


@pytest.mark.asyncio
async def test_stock_not_found_error_returns_404() -> None:
    """StockNotFoundError propagates as 404 via middleware."""
    app = _make_app(("/err", StockNotFoundError("AAPL")))
    resp = await _get(app, "/err")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Stock not found: AAPL"


@pytest.mark.asyncio
async def test_portfolio_not_found_error_returns_404() -> None:
    """PortfolioNotFoundError propagates as 404 via middleware."""
    app = _make_app(("/err", PortfolioNotFoundError("user-123")))
    resp = await _get(app, "/err")
    assert resp.status_code == 404
    # Message contains user_id — acceptable as safe_message since it's
    # the value the caller passed in (no internal paths / stack traces)
    assert resp.json()["detail"] == "Portfolio not found for user: user-123"


@pytest.mark.asyncio
async def test_duplicate_watchlist_error_returns_409() -> None:
    """DuplicateWatchlistError propagates as 409 via middleware."""
    app = _make_app(("/err", DuplicateWatchlistError("TSLA")))
    resp = await _get(app, "/err")
    assert resp.status_code == 409
    assert resp.json()["detail"] == "Already on watchlist: TSLA"


@pytest.mark.asyncio
async def test_ingest_failed_error_returns_404() -> None:
    """IngestFailedError propagates as 404 via middleware."""
    app = _make_app(("/err", IngestFailedError("MSFT", "price_fetch")))
    resp = await _get(app, "/err")
    assert resp.status_code == 404
    assert "MSFT" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Safety: internal details not leaked
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_internal_detail_not_leaked() -> None:
    """DomainError response uses safe_message, not the Exception args repr."""

    class _InternalError(DomainError):
        status_code = 500
        safe_message = "An unexpected error occurred."

        def __init__(self) -> None:
            # Simulate an internal detail in the exception args
            super().__init__()
            # Override args to simulate accidental internal detail
            self.args = ("Internal path: /etc/passwd", "traceback here")

    app = _make_app(("/err", _InternalError()))
    resp = await _get(app, "/err")
    body = resp.json()
    assert body["detail"] == "An unexpected error occurred."
    assert "/etc/passwd" not in body["detail"]
    assert "traceback" not in body["detail"]


@pytest.mark.asyncio
async def test_response_format_matches_fastapi_http_exception() -> None:
    """Response JSON uses 'detail' key, matching FastAPI's HTTPException format."""
    from fastapi import HTTPException

    http_exc = HTTPException(status_code=404, detail="Not here")
    app = _make_app(
        ("/domain", ResourceNotFoundError("Not here")),
        ("/http", http_exc),
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        domain_resp = await client.get("/domain")
        http_resp = await client.get("/http")

    # Both should have the same JSON structure
    assert set(domain_resp.json().keys()) == set(http_resp.json().keys())
    assert domain_resp.json()["detail"] == http_resp.json()["detail"]


# ---------------------------------------------------------------------------
# Non-DomainError is NOT caught by middleware
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_plain_exception_not_caught_by_middleware() -> None:
    """A plain ValueError is NOT intercepted by ErrorHandlerMiddleware.

    Starlette's BaseHTTPMiddleware re-raises unhandled exceptions (not
    wrapped as 500 responses). This test verifies that ValueError propagates
    rather than being silently swallowed or converted by our middleware.
    """
    app = _make_app(("/err", ValueError("raw internal error")))
    transport = httpx.ASGITransport(app=app)
    with pytest.raises(ValueError, match="raw internal error"):
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            await client.get("/err")
