"""Tests for the health check endpoint."""

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


class TestHealthEndpoint:
    """Tests for GET /api/v1/health."""

    async def test_health_returns_ok(self, client: AsyncClient) -> None:
        """Health endpoint returns 200 with status and version."""
        response = await client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["version"] == "0.1.0"
        assert "mcp_tools" in data
        assert "redis" in data
        assert "database" in data

    async def test_health_mcp_disabled_shows_direct(self, client: AsyncClient) -> None:
        """When MCP_TOOLS=False, mode is 'direct' and healthy=True."""
        redis_p, db_p = _patch_deps_healthy()
        with patch("backend.observability.routers.health.settings") as mock_settings, redis_p, db_p:
            mock_settings.MCP_TOOLS = False
            response = await client.get("/api/v1/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        mcp = data["mcp_tools"]
        assert mcp["enabled"] is False
        assert mcp["mode"] == "direct"
        assert mcp["healthy"] is True

    async def test_health_mcp_enabled_no_manager(self, client: AsyncClient) -> None:
        """When MCP enabled but manager missing, shows disabled+unhealthy."""
        redis_p, db_p = _patch_deps_healthy()
        with patch("backend.observability.routers.health.settings") as mock_settings, redis_p, db_p:
            mock_settings.MCP_TOOLS = True
            # Ensure no mcp_manager on app state
            if hasattr(client._transport.app.state, "mcp_manager"):
                delattr(client._transport.app.state, "mcp_manager")
            response = await client.get("/api/v1/health")

        assert response.status_code == 200
        data = response.json()
        mcp = data["mcp_tools"]
        assert mcp["enabled"] is True
        assert mcp["mode"] == "disabled"
        assert mcp["healthy"] is False

    async def test_health_degraded_when_fallback(self, client: AsyncClient) -> None:
        """When MCP manager is in fallback mode, status is 'degraded'."""
        mock_manager = AsyncMock()
        mock_manager.mode = "fallback_direct"
        mock_manager.healthy = False
        mock_manager.restart_count = 3
        mock_manager.uptime_seconds = None
        mock_manager.last_error = "subprocess exited"
        mock_manager.fallback_since = "2026-03-23T20:00:00Z"

        client._transport.app.state.mcp_manager = mock_manager

        redis_p, db_p = _patch_deps_healthy()
        with patch("backend.observability.routers.health.settings") as mock_settings, redis_p, db_p:
            mock_settings.MCP_TOOLS = True
            response = await client.get("/api/v1/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"
        mcp = data["mcp_tools"]
        assert mcp["mode"] == "fallback_direct"
        assert mcp["healthy"] is False
        assert mcp["restarts"] == 3
        assert mcp["last_error"] == "subprocess exited"

        # Cleanup
        delattr(client._transport.app.state, "mcp_manager")

    async def test_health_no_auth_required(self, client: AsyncClient) -> None:
        """Health endpoint does not require authentication."""
        response = await client.get("/api/v1/health")
        assert response.status_code == 200
