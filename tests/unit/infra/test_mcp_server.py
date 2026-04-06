"""Tests for MCP server setup and auth middleware."""

import uuid
from dataclasses import dataclass
from unittest.mock import patch

import pytest
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.testclient import TestClient

from backend.mcp_server.auth import MCPAuthMiddleware
from backend.mcp_server.server import create_mcp_app
from backend.request_context import current_user_id
from backend.tools.base import BaseTool, ToolResult
from backend.tools.registry import ToolRegistry

_TEST_USER_ID = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")


@dataclass
class _FakeTokenPayload:
    """Mimics TokenPayload from dependencies."""

    user_id: uuid.UUID
    jti: str | None = None


class _DummyTool(BaseTool):
    """A minimal tool for testing MCP server registration."""

    name = "dummy_tool"
    description = "A dummy tool for testing."
    category = "testing"
    parameters: dict = {"type": "object", "properties": {}}

    async def _run(self, params: dict) -> ToolResult:
        """Return a dummy result."""
        return ToolResult(status="ok", data={"message": "hello"})


class _ContextCaptureTool(BaseTool):
    """Tool that captures current_user_id during execution."""

    name = "context_capture"
    description = "Captures context vars."
    category = "testing"
    parameters: dict = {"type": "object", "properties": {}}

    async def _run(self, params: dict) -> ToolResult:
        """Return whatever current_user_id is set to."""
        uid = current_user_id.get()
        return ToolResult(status="ok", data={"user_id": str(uid) if uid else None})


def test_mcp_app_creates():
    """MCP app can be created with a registry."""
    registry = ToolRegistry()
    mcp = create_mcp_app(registry)
    assert mcp is not None


@pytest.mark.asyncio
async def test_mcp_app_registers_tools():
    """MCP app registers all tools from the registry."""
    registry = ToolRegistry()
    tool = _DummyTool()
    registry.register(tool)

    mcp = create_mcp_app(registry)
    assert mcp is not None
    # Verify the tool was registered with FastMCP
    registered_tool = await mcp.get_tool("dummy_tool")
    assert registered_tool is not None


def test_mcp_app_empty_registry():
    """MCP app works with an empty registry."""
    registry = ToolRegistry()
    mcp = create_mcp_app(registry)
    assert mcp is not None


def test_mcp_http_app_creates():
    """FastMCP.http_app() returns a Starlette ASGI application."""
    registry = ToolRegistry()
    mcp = create_mcp_app(registry)
    http_app = mcp.http_app()
    assert http_app is not None
    # Should be a Starlette-compatible ASGI app
    assert callable(http_app)


# ---------------------------------------------------------------------------
# MCPAuthMiddleware — ContextVar tests
# ---------------------------------------------------------------------------


def _build_starlette_app_with_middleware():
    """Build a minimal Starlette app with MCPAuthMiddleware.

    Returns a Starlette app that records the ContextVar value
    seen inside the endpoint handler.
    """
    from starlette.applications import Starlette
    from starlette.routing import Route

    captured: dict = {}

    async def _endpoint(request: Request) -> Response:
        """Endpoint that captures current_user_id ContextVar."""
        uid = current_user_id.get()
        captured["user_id"] = uid
        return JSONResponse({"user_id": str(uid) if uid else None})

    app = Starlette(routes=[Route("/test", _endpoint)])
    app.add_middleware(MCPAuthMiddleware)
    return app, captured


@patch("backend.mcp_server.auth.decode_token")
def test_middleware_sets_contextvar(mock_decode):
    """MCPAuthMiddleware sets current_user_id ContextVar from JWT."""
    mock_decode.return_value = _FakeTokenPayload(user_id=_TEST_USER_ID)
    app, captured = _build_starlette_app_with_middleware()
    client = TestClient(app)

    resp = client.get("/test", headers={"Authorization": "Bearer fake-token"})

    assert resp.status_code == 200
    assert captured["user_id"] == _TEST_USER_ID
    assert resp.json()["user_id"] == str(_TEST_USER_ID)


@patch("backend.mcp_server.auth.decode_token")
def test_middleware_resets_contextvar_after_request(mock_decode):
    """ContextVar is reset after the request completes."""
    mock_decode.return_value = _FakeTokenPayload(user_id=_TEST_USER_ID)
    app, _ = _build_starlette_app_with_middleware()
    client = TestClient(app)

    # Before request, ContextVar should be None (default)
    assert current_user_id.get() is None

    client.get("/test", headers={"Authorization": "Bearer fake-token"})

    # After request, ContextVar should be reset to None
    assert current_user_id.get() is None


def test_middleware_rejects_missing_auth():
    """Requests without Authorization header get 401."""
    app, captured = _build_starlette_app_with_middleware()
    client = TestClient(app)

    resp = client.get("/test")

    assert resp.status_code == 401
    assert "user_id" not in captured


@patch("backend.mcp_server.auth.decode_token", side_effect=Exception("bad token"))
def test_middleware_rejects_invalid_token(mock_decode):
    """Requests with invalid token get 401, ContextVar not set."""
    app, captured = _build_starlette_app_with_middleware()
    client = TestClient(app)

    resp = client.get("/test", headers={"Authorization": "Bearer bad-token"})

    assert resp.status_code == 401
    assert "user_id" not in captured
    assert current_user_id.get() is None


def test_middleware_allows_options_without_auth():
    """OPTIONS requests pass through without authentication."""
    app, _ = _build_starlette_app_with_middleware()
    client = TestClient(app)

    resp = client.options("/test")

    # OPTIONS should pass through (may be 405 if route doesn't handle it,
    # but should NOT be 401)
    assert resp.status_code != 401


@patch("backend.mcp_server.auth.decode_token")
def test_middleware_contextvar_isolated_between_requests(mock_decode):
    """Each request gets its own ContextVar value, not a stale one."""
    user_1 = uuid.UUID("11111111-1111-1111-1111-111111111111")
    user_2 = uuid.UUID("22222222-2222-2222-2222-222222222222")

    app, captured = _build_starlette_app_with_middleware()
    client = TestClient(app)

    # First request with user_1
    mock_decode.return_value = _FakeTokenPayload(user_id=user_1)
    resp1 = client.get("/test", headers={"Authorization": "Bearer token-1"})
    assert resp1.json()["user_id"] == str(user_1)

    # Second request with user_2
    mock_decode.return_value = _FakeTokenPayload(user_id=user_2)
    resp2 = client.get("/test", headers={"Authorization": "Bearer token-2"})
    assert resp2.json()["user_id"] == str(user_2)

    # ContextVar should be clean after both requests
    assert current_user_id.get() is None
