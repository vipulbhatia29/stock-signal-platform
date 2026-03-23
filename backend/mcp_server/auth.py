"""JWT authentication for MCP server connections.

Reuses the existing auth dependency from the main FastAPI app.
MCP auth is enforced at the FastAPI mount level via middleware,
not inside FastMCP itself (which has no concept of HTTP auth).
"""

from __future__ import annotations

import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from backend.dependencies import decode_token

logger = logging.getLogger(__name__)


class MCPAuthMiddleware(BaseHTTPMiddleware):
    """Middleware that validates JWT tokens on MCP endpoint requests.

    Applied to the Starlette sub-app returned by FastMCP.http_app()
    before it is mounted on the main FastAPI application.
    """

    async def dispatch(self, request: Request, call_next):
        """Validate Bearer token before forwarding to MCP handler."""
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

        return await call_next(request)
