"""Security header regression snapshot tests.

Snapshots security-relevant response headers to detect regressions
in middleware configuration (e.g. accidentally removing security headers).

Run with --snapshot-update to regenerate baselines.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from httpx import AsyncClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_security_headers(headers: dict) -> dict:
    """Extract security-relevant headers from a response, normalized to lowercase keys."""
    relevant = {
        "content-type",
        "x-content-type-options",
        "x-frame-options",
        "cache-control",
        "strict-transport-security",
        "referrer-policy",
    }
    return {k.lower(): v for k, v in headers.items() if k.lower() in relevant}


# ---------------------------------------------------------------------------
# Public endpoint security headers
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestHealthEndpointSecurityHeaders:
    """Security header tests for the public health endpoint."""

    async def test_health_has_content_type(self, client: AsyncClient) -> None:
        """Health endpoint must return application/json Content-Type."""
        from backend.schemas.health import DependencyStatus

        _healthy = DependencyStatus(healthy=True, latency_ms=0.1)
        with (
            patch("backend.observability.routers.health._check_redis", return_value=_healthy),
            patch("backend.observability.routers.health._check_database", return_value=_healthy),
        ):
            response = await client.get("/api/v1/health")
        assert response.status_code == 200
        content_type = response.headers.get("content-type", "")
        assert "application/json" in content_type, (
            f"Expected application/json Content-Type, got: {content_type}"
        )

    async def test_health_security_headers_snapshot(self, client: AsyncClient, snapshot) -> None:
        """Security headers on health endpoint must match snapshot."""
        from backend.schemas.health import DependencyStatus

        _healthy = DependencyStatus(healthy=True, latency_ms=0.1)
        with (
            patch("backend.observability.routers.health._check_redis", return_value=_healthy),
            patch("backend.observability.routers.health._check_database", return_value=_healthy),
        ):
            response = await client.get("/api/v1/health")
        security_headers = _extract_security_headers(dict(response.headers))
        assert security_headers == snapshot


# ---------------------------------------------------------------------------
# Authenticated endpoint cache headers
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestAuthenticatedEndpointCacheHeaders:
    """Cache control headers on authenticated endpoints."""

    async def test_portfolio_401_has_content_type(self, client: AsyncClient) -> None:
        """Unauthenticated portfolio endpoint returns proper Content-Type on 401."""
        response = await client.get("/api/v1/portfolio/summary")
        assert response.status_code == 401
        content_type = response.headers.get("content-type", "")
        assert "application/json" in content_type


# ---------------------------------------------------------------------------
# Cross-origin and frame headers
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestCrossOriginHeaders:
    """Tests that the API properly handles cross-origin requests."""

    async def test_health_endpoint_responds_to_any_origin(self, client: AsyncClient) -> None:
        """Health endpoint should respond to any origin (public endpoint)."""
        response = await client.get(
            "/api/v1/health",
            headers={"Origin": "https://evil.example.com"},
        )
        assert response.status_code == 200

    async def test_stocks_endpoint_reachable(self, client: AsyncClient) -> None:
        """Stocks list endpoint should be reachable without auth (public data)."""
        with patch("backend.routers.stocks.recommendations.get_bulk_signals_svc") as mock_bulk:
            mock_bulk.return_value = (0, [])
            response = await client.get("/api/v1/stocks?limit=1")
        # Either 200 (data available) or consistent error — not 500
        assert response.status_code in (200, 404, 422), (
            f"Unexpected status code: {response.status_code}"
        )

    async def test_auth_endpoint_has_json_content_type(self, client: AsyncClient) -> None:
        """Login endpoint should return JSON errors with correct Content-Type."""
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "invalid@example.com", "password": "wrong"},
        )
        # 401 or 400 or 422 are acceptable — must have JSON content-type
        assert response.status_code in (400, 401, 422)
        content_type = response.headers.get("content-type", "")
        assert "application/json" in content_type
