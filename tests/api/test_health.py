"""Tests for the health check endpoints."""

from unittest.mock import AsyncMock, patch

from httpx import AsyncClient

from backend.schemas.health import DependencyStatus

_HEALTHY_DEP = DependencyStatus(healthy=True, latency_ms=0.1)


def _patch_deps_healthy():
    """Patch Redis and DB checks to return healthy for MCP-focused tests."""
    return (
        patch("backend.observability.routers.health._check_redis", return_value=_HEALTHY_DEP),
        patch("backend.observability.routers.health._check_database", return_value=_HEALTHY_DEP),
    )


class TestPublicHealthEndpoint:
    """Tests for GET /api/v1/health — public, no auth required."""

    async def test_health_returns_200(self, client: AsyncClient) -> None:
        """Public health endpoint returns 200."""
        response = await client.get("/api/v1/health")
        assert response.status_code == 200

    async def test_health_returns_status_and_version_only(self, client: AsyncClient) -> None:
        """Public endpoint exposes only status and version — no dependency details."""
        response = await client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert set(data.keys()) == {"status", "version"}

    async def test_health_does_not_expose_redis(self, client: AsyncClient) -> None:
        """Public endpoint must not include redis key (KAN-314 regression)."""
        response = await client.get("/api/v1/health")
        assert "redis" not in response.json()

    async def test_health_does_not_expose_database(self, client: AsyncClient) -> None:
        """Public endpoint must not include database key (KAN-314 regression)."""
        response = await client.get("/api/v1/health")
        assert "database" not in response.json()

    async def test_health_does_not_expose_mcp_tools(self, client: AsyncClient) -> None:
        """Public endpoint must not include mcp_tools key (KAN-314 regression)."""
        response = await client.get("/api/v1/health")
        assert "mcp_tools" not in response.json()

    async def test_health_returns_version(self, client: AsyncClient) -> None:
        """Public endpoint returns the application version string."""
        response = await client.get("/api/v1/health")
        assert response.json()["version"] == "0.1.0"

    async def test_health_no_auth_required(self, client: AsyncClient) -> None:
        """Public health endpoint does not require authentication."""
        response = await client.get("/api/v1/health")
        assert response.status_code == 200

    async def test_health_ok_when_all_healthy(self, client: AsyncClient) -> None:
        """Status is 'ok' when all dependencies are healthy."""
        redis_p, db_p = _patch_deps_healthy()
        with redis_p, db_p, patch("backend.observability.routers.health.settings") as mock_settings:
            mock_settings.MCP_TOOLS = False
            response = await client.get("/api/v1/health")
        assert response.json()["status"] == "ok"

    async def test_health_degraded_when_redis_down(self, client: AsyncClient) -> None:
        """Status is 'degraded' when Redis is unhealthy."""
        unhealthy_redis = DependencyStatus(healthy=False, error="Redis connection failed")
        with (
            patch(
                "backend.observability.routers.health._check_redis",
                return_value=unhealthy_redis,
            ),
            patch(
                "backend.observability.routers.health._check_database",
                return_value=_HEALTHY_DEP,
            ),
        ):
            response = await client.get("/api/v1/health")
        assert response.json()["status"] == "degraded"


class TestDetailHealthEndpoint:
    """Tests for GET /api/v1/health/detail — authenticated only."""

    async def test_detail_requires_auth(self, client: AsyncClient) -> None:
        """Detail endpoint returns 401 without a valid token (KAN-314 regression)."""
        response = await client.get("/api/v1/health/detail")
        assert response.status_code == 401

    async def test_detail_returns_full_response_when_authenticated(
        self, authenticated_client: AsyncClient
    ) -> None:
        """Authenticated request to /health/detail returns all dependency fields."""
        redis_p, db_p = _patch_deps_healthy()
        with redis_p, db_p, patch("backend.observability.routers.health.settings") as mock_settings:
            mock_settings.MCP_TOOLS = False
            response = await authenticated_client.get("/api/v1/health/detail")
        assert response.status_code == 200
        data = response.json()
        assert "redis" in data
        assert "database" in data
        assert "mcp_tools" in data
        assert "version" in data
        assert "status" in data

    async def test_detail_mcp_disabled_shows_direct(
        self, authenticated_client: AsyncClient
    ) -> None:
        """When MCP_TOOLS=False, detail shows mode 'direct' and healthy=True."""
        redis_p, db_p = _patch_deps_healthy()
        with redis_p, db_p, patch("backend.observability.routers.health.settings") as mock_settings:
            mock_settings.MCP_TOOLS = False
            response = await authenticated_client.get("/api/v1/health/detail")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        mcp = data["mcp_tools"]
        assert mcp["enabled"] is False
        assert mcp["mode"] == "direct"
        assert mcp["healthy"] is True

    async def test_detail_mcp_enabled_no_manager(self, authenticated_client: AsyncClient) -> None:
        """When MCP enabled but manager missing, detail shows disabled+unhealthy."""
        redis_p, db_p = _patch_deps_healthy()
        with redis_p, db_p, patch("backend.observability.routers.health.settings") as mock_settings:
            mock_settings.MCP_TOOLS = True
            if hasattr(authenticated_client._transport.app.state, "mcp_manager"):
                delattr(authenticated_client._transport.app.state, "mcp_manager")
            response = await authenticated_client.get("/api/v1/health/detail")
        assert response.status_code == 200
        data = response.json()
        mcp = data["mcp_tools"]
        assert mcp["enabled"] is True
        assert mcp["mode"] == "disabled"
        assert mcp["healthy"] is False

    async def test_detail_degraded_when_fallback(self, authenticated_client: AsyncClient) -> None:
        """When MCP manager is in fallback mode, detail status is 'degraded'."""
        mock_manager = AsyncMock()
        mock_manager.mode = "fallback_direct"
        mock_manager.healthy = False
        mock_manager.restart_count = 3
        mock_manager.uptime_seconds = None
        mock_manager.last_error = "subprocess exited"
        mock_manager.fallback_since = "2026-03-23T20:00:00Z"

        authenticated_client._transport.app.state.mcp_manager = mock_manager

        redis_p, db_p = _patch_deps_healthy()
        with redis_p, db_p, patch("backend.observability.routers.health.settings") as mock_settings:
            mock_settings.MCP_TOOLS = True
            response = await authenticated_client.get("/api/v1/health/detail")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"
        mcp = data["mcp_tools"]
        assert mcp["mode"] == "fallback_direct"
        assert mcp["healthy"] is False
        assert mcp["restarts"] == 3
        assert mcp["last_error"] == "subprocess exited"

        # Cleanup
        delattr(authenticated_client._transport.app.state, "mcp_manager")
