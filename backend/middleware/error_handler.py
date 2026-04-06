"""Centralized DomainError middleware for FastAPI exception handling.

Catches DomainError (and all subclasses, including ServiceError) that
propagate out of routers and converts them to structured JSON responses
matching FastAPI's HTTPException response format (``{"detail": "..."}`}).

Intentionally does NOT add a catch-all ``Exception`` handler — FastAPI's
default 500 handling and the observability middleware cover unhandled errors.
"""

from __future__ import annotations

import logging

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from backend.exceptions import DomainError

logger = logging.getLogger(__name__)


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """Translate DomainError subclasses into safe HTTP JSON responses.

    Catches any DomainError that propagates out of a route handler and
    returns a JSON response with the safe_message. Internal exception
    details are logged at WARNING level but never sent to the client.
    """

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        """Process the request, converting DomainErrors to JSON responses.

        Args:
            request: The incoming HTTP request.
            call_next: The next middleware or route handler.

        Returns:
            A JSONResponse with the safe_message if a DomainError is
            raised, otherwise the normal response from the route.
        """
        try:
            return await call_next(request)
        except DomainError as exc:
            logger.warning(
                "domain_error",
                extra={
                    "error_type": type(exc).__name__,
                    "status_code": exc.status_code,
                    "path": request.url.path,
                    "method": request.method,
                },
            )
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.safe_message},
            )
