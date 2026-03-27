"""JWT authentication for MCP server connections.

Reuses the existing auth dependency from the main FastAPI app.
MCP auth is enforced at the FastAPI mount level via middleware,
not inside FastMCP itself (which has no concept of HTTP auth).

The middleware also sets ``current_user_id`` ContextVar so that
portfolio-related tools (portfolio_exposure, portfolio_health,
recommend_stocks) can identify the requesting user.
"""

from __future__ import annotations

import logging
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from backend.dependencies import decode_token
from backend.request_context import current_user_id

logger = logging.getLogger(__name__)


class MCPAuthMiddleware(BaseHTTPMiddleware):
    """Middleware that validates JWT tokens on MCP endpoint requests.

    Applied to the Starlette sub-app returned by FastMCP.http_app()
    before it is mounted on the main FastAPI application.

    After successful authentication the ``current_user_id`` ContextVar
    is set for the duration of the request so downstream tool handlers
    can read it.
    """

    async def dispatch(self, request: Request, call_next):
        """Validate Bearer token and set user ContextVar."""
        # Allow health checks and OPTIONS (CORS preflight)
        if request.method == "OPTIONS":
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                {"detail": "Missing or invalid Authorization header"},
                status_code=401,
            )

        token = auth_header.removeprefix("Bearer ").strip()
        try:
            token_payload = decode_token(token, expected_type="access")
            request.state.user_id = str(token_payload.user_id)
        except Exception:
            logger.exception("MCP auth failed")
            return JSONResponse(
                {"detail": "Invalid or expired token"},
                status_code=401,
            )

        # Set ContextVar so tool handlers see the authenticated user.
        ctx_token = current_user_id.set(uuid.UUID(request.state.user_id))
        try:
            return await call_next(request)
        finally:
            current_user_id.reset(ctx_token)
