"""CSRF middleware — double-submit cookie pattern.

Enforces CSRF token validation only on cookie-authenticated mutating
requests (POST, PUT, PATCH, DELETE). Requests with an Authorization
header (Bearer token) are CSRF-safe and skip validation.
"""

from __future__ import annotations

import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


class CSRFMiddleware(BaseHTTPMiddleware):
    """Validate double-submit CSRF token on cookie-authenticated mutations.

    Args:
        app: The ASGI application.
        csrf_exempt_paths: Set of URL paths that skip CSRF validation.
    """

    def __init__(self, app, csrf_exempt_paths: set[str] | None = None) -> None:
        super().__init__(app)
        self.csrf_exempt_paths: set[str] = csrf_exempt_paths or set()

    async def dispatch(self, request: Request, call_next) -> Response:
        """Process request, enforcing CSRF on cookie-auth mutations."""
        # Safe methods never need CSRF
        if request.method in _SAFE_METHODS:
            return await call_next(request)

        # Exempt paths skip CSRF
        if request.url.path in self.csrf_exempt_paths:
            return await call_next(request)

        # Bearer auth is CSRF-safe — skip
        auth_header = request.headers.get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            return await call_next(request)

        # No auth cookies at all → not cookie-auth → skip
        # Check both access_token AND refresh_token — a request with only
        # refresh_token is still cookie-auth (access may have expired mid-flight).
        access_cookie = request.cookies.get("access_token")
        refresh_cookie = request.cookies.get("refresh_token")
        if not access_cookie and not refresh_cookie:
            return await call_next(request)

        # Cookie-auth mutating request → validate CSRF token
        csrf_cookie = request.cookies.get("csrf_token", "")
        csrf_header = request.headers.get("x-csrf-token", "")

        if not csrf_cookie or not csrf_header or csrf_cookie != csrf_header:
            logger.warning(
                "CSRF validation failed: path=%s method=%s",
                request.url.path,
                request.method,
            )
            return JSONResponse(
                status_code=403,
                content={"detail": "CSRF token validation failed"},
            )

        return await call_next(request)
