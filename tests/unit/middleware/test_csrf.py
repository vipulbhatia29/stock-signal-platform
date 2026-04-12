"""Tests for CSRF middleware — double-submit cookie pattern."""

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route
from starlette.testclient import TestClient

from backend.middleware.csrf import CSRFMiddleware


def _make_app(exempt_paths: set[str] | None = None) -> Starlette:
    """Create a minimal Starlette app with CSRF middleware for testing."""

    async def echo(request: Request) -> Response:
        return JSONResponse({"ok": True})

    app = Starlette(
        routes=[
            Route("/protected", echo, methods=["POST", "GET", "DELETE"]),
            Route("/exempt", echo, methods=["POST"]),
            Route("/health", echo, methods=["GET"]),
        ]
    )
    app.add_middleware(
        CSRFMiddleware,
        csrf_exempt_paths=exempt_paths or {"/exempt"},
    )
    return app


class TestCSRFMiddleware:
    """CSRF double-submit cookie validation."""

    def test_get_request_always_passes(self) -> None:
        """GET requests are safe methods — skip CSRF check."""
        client = TestClient(_make_app())
        response = client.get("/protected")
        assert response.status_code == 200

    def test_post_with_bearer_auth_skips_csrf(self) -> None:
        """Requests with Authorization header bypass CSRF (header auth is CSRF-safe)."""
        client = TestClient(_make_app())
        response = client.post(
            "/protected",
            headers={"Authorization": "Bearer some-token"},
        )
        assert response.status_code == 200

    def test_post_cookie_auth_missing_csrf_token_returns_403(self) -> None:
        """Cookie-auth POST without X-CSRF-Token header → 403."""
        client = TestClient(_make_app())
        client.cookies.set("access_token", "fake-jwt")
        response = client.post("/protected")
        assert response.status_code == 403
        assert "CSRF" in response.json()["detail"]

    def test_post_cookie_auth_mismatched_csrf_token_returns_403(self) -> None:
        """Cookie-auth POST with wrong X-CSRF-Token → 403."""
        client = TestClient(_make_app())
        client.cookies.set("access_token", "fake-jwt")
        client.cookies.set("csrf_token", "correct-token")
        response = client.post(
            "/protected",
            headers={"X-CSRF-Token": "wrong-token"},
        )
        assert response.status_code == 403

    def test_post_cookie_auth_valid_csrf_token_passes(self) -> None:
        """Cookie-auth POST with matching X-CSRF-Token → passes through."""
        client = TestClient(_make_app())
        client.cookies.set("access_token", "fake-jwt")
        client.cookies.set("csrf_token", "valid-token")
        response = client.post(
            "/protected",
            headers={"X-CSRF-Token": "valid-token"},
        )
        assert response.status_code == 200

    def test_exempt_path_skips_csrf(self) -> None:
        """Paths in csrf_exempt_paths skip CSRF check."""
        client = TestClient(_make_app(exempt_paths={"/exempt"}))
        client.cookies.set("access_token", "fake-jwt")
        response = client.post("/exempt")
        assert response.status_code == 200

    def test_options_request_always_passes(self) -> None:
        """OPTIONS requests (CORS preflight) skip CSRF."""
        client = TestClient(_make_app())
        client.cookies.set("access_token", "fake-jwt")
        response = client.options("/protected")
        # Starlette returns 400 for OPTIONS on non-CORS routes, but the point is
        # CSRF middleware should NOT block it with 403
        assert response.status_code != 403

    def test_delete_cookie_auth_valid_csrf_passes(self) -> None:
        """DELETE with valid CSRF token passes."""
        client = TestClient(_make_app())
        client.cookies.set("access_token", "fake-jwt")
        client.cookies.set("csrf_token", "delete-token")
        response = client.delete(
            "/protected",
            headers={"X-CSRF-Token": "delete-token"},
        )
        assert response.status_code == 200

    def test_empty_csrf_header_returns_403(self) -> None:
        """Empty X-CSRF-Token header is treated as missing."""
        client = TestClient(_make_app())
        client.cookies.set("access_token", "fake-jwt")
        client.cookies.set("csrf_token", "real-token")
        response = client.post(
            "/protected",
            headers={"X-CSRF-Token": ""},
        )
        assert response.status_code == 403

    def test_no_cookies_at_all_passes(self) -> None:
        """Request with no cookies at all is not cookie-auth — skip CSRF."""
        client = TestClient(_make_app())
        response = client.post("/protected")
        assert response.status_code == 200

    def test_refresh_only_cookie_still_enforces_csrf(self) -> None:
        """Request with only refresh_token cookie (no access_token) is still cookie-auth."""
        client = TestClient(_make_app())
        client.cookies.set("refresh_token", "fake-refresh")
        response = client.post("/protected")
        assert response.status_code == 403

    def test_lowercase_bearer_auth_skips_csrf(self) -> None:
        """Authorization scheme check is case-insensitive."""
        client = TestClient(_make_app())
        client.cookies.set("access_token", "fake-jwt")
        response = client.post(
            "/protected",
            headers={"Authorization": "bearer lowercase-token"},
        )
        assert response.status_code == 200

    def test_cookie_auth_header_present_but_missing_cookie_returns_403(self) -> None:
        """Attacker with forged header but no csrf cookie → 403."""
        client = TestClient(_make_app())
        client.cookies.set("access_token", "fake-jwt")
        # No csrf_token cookie set
        response = client.post(
            "/protected",
            headers={"X-CSRF-Token": "forged-header-value"},
        )
        assert response.status_code == 403
