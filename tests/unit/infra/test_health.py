"""Tests for the health check endpoint with Redis and DB checks."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.observability.routers.health import _check_database, _check_redis, health_check
from backend.schemas.health import DependencyStatus


@pytest.fixture
def mock_request_all_healthy() -> MagicMock:
    """Request with a healthy Redis cache on app.state."""
    request = MagicMock()
    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(return_value=True)
    cache = MagicMock()
    cache._redis = mock_redis
    request.app.state.cache = cache
    request.app.state.mcp_manager = None
    request.app.state.registry = None
    return request


@pytest.fixture
def mock_request_no_cache() -> MagicMock:
    """Request with no cache service on app.state."""
    request = MagicMock()
    request.app.state = MagicMock(spec=[])
    return request


# --- _check_redis ---


async def test_check_redis_healthy(mock_request_all_healthy: MagicMock) -> None:
    """Redis ping succeeds — returns healthy with latency."""
    status = await _check_redis(mock_request_all_healthy)
    assert status.healthy is True
    assert status.latency_ms is not None
    assert status.latency_ms >= 0
    assert status.error is None


async def test_check_redis_not_initialized(mock_request_no_cache: MagicMock) -> None:
    """No cache on app.state — returns unhealthy."""
    status = await _check_redis(mock_request_no_cache)
    assert status.healthy is False
    assert status.error == "Redis not initialized"


async def test_check_redis_connection_error() -> None:
    """Redis ping raises exception — returns unhealthy."""
    request = MagicMock()
    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(side_effect=ConnectionError("refused"))
    cache = MagicMock()
    cache._redis = mock_redis
    request.app.state.cache = cache

    status = await _check_redis(request)
    assert status.healthy is False
    assert status.error == "Redis connection failed"


# --- _check_database ---


async def test_check_database_healthy() -> None:
    """DB SELECT 1 succeeds — returns healthy with latency."""
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=None)
    mock_factory = AsyncMock()
    mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
    mock_factory.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "backend.observability.routers.health.async_session_factory",
        return_value=mock_factory,
    ):
        status = await _check_database()

    assert status.healthy is True
    assert status.latency_ms is not None
    assert status.latency_ms >= 0
    assert status.error is None


async def test_check_database_connection_error() -> None:
    """DB connection fails — returns unhealthy."""
    with patch(
        "backend.observability.routers.health.async_session_factory",
        side_effect=ConnectionError("cannot connect"),
    ):
        status = await _check_database()

    assert status.healthy is False
    assert status.error == "Database connection failed"


# --- health_check endpoint ---


async def test_health_all_services_ok() -> None:
    """All services healthy — status is 'ok'."""
    request = MagicMock()
    request.app.state.mcp_manager = None
    request.app.state.registry = None
    request.app.state.cache = MagicMock()

    redis_ok = DependencyStatus(healthy=True, latency_ms=0.5)
    db_ok = DependencyStatus(healthy=True, latency_ms=1.0)

    with (
        patch("backend.observability.routers.health._check_redis", return_value=redis_ok),
        patch("backend.observability.routers.health._check_database", return_value=db_ok),
        patch("backend.observability.routers.health.settings") as mock_settings,
    ):
        mock_settings.MCP_TOOLS = False
        response = await health_check(request)

    assert response.status == "ok"
    assert response.redis.healthy is True
    assert response.database.healthy is True
    assert response.mcp_tools.healthy is True


async def test_health_redis_down_returns_degraded() -> None:
    """Redis unhealthy — overall status is 'degraded'."""
    request = MagicMock()
    request.app.state.mcp_manager = None
    request.app.state.registry = None

    redis_down = DependencyStatus(healthy=False, error="Redis connection failed")
    db_ok = DependencyStatus(healthy=True, latency_ms=1.0)

    with (
        patch("backend.observability.routers.health._check_redis", return_value=redis_down),
        patch("backend.observability.routers.health._check_database", return_value=db_ok),
        patch("backend.observability.routers.health.settings") as mock_settings,
    ):
        mock_settings.MCP_TOOLS = False
        response = await health_check(request)

    assert response.status == "degraded"
    assert response.redis.healthy is False
    assert response.database.healthy is True


async def test_health_db_down_returns_degraded() -> None:
    """Database unhealthy — overall status is 'degraded'."""
    request = MagicMock()
    request.app.state.mcp_manager = None
    request.app.state.registry = None

    redis_ok = DependencyStatus(healthy=True, latency_ms=0.5)
    db_down = DependencyStatus(healthy=False, error="Database connection failed")

    with (
        patch("backend.observability.routers.health._check_redis", return_value=redis_ok),
        patch("backend.observability.routers.health._check_database", return_value=db_down),
        patch("backend.observability.routers.health.settings") as mock_settings,
    ):
        mock_settings.MCP_TOOLS = False
        response = await health_check(request)

    assert response.status == "degraded"
    assert response.redis.healthy is True
    assert response.database.healthy is False


async def test_health_both_down_returns_degraded() -> None:
    """Both Redis and DB unhealthy — status is 'degraded'."""
    request = MagicMock()
    request.app.state.mcp_manager = None
    request.app.state.registry = None

    redis_down = DependencyStatus(healthy=False, error="Redis connection failed")
    db_down = DependencyStatus(healthy=False, error="Database connection failed")

    with (
        patch("backend.observability.routers.health._check_redis", return_value=redis_down),
        patch("backend.observability.routers.health._check_database", return_value=db_down),
        patch("backend.observability.routers.health.settings") as mock_settings,
    ):
        mock_settings.MCP_TOOLS = False
        response = await health_check(request)

    assert response.status == "degraded"
    assert response.redis.healthy is False
    assert response.database.healthy is False


async def test_health_response_includes_version() -> None:
    """Health response always includes the app version."""
    request = MagicMock()
    request.app.state.mcp_manager = None
    request.app.state.registry = None

    redis_ok = DependencyStatus(healthy=True, latency_ms=0.5)
    db_ok = DependencyStatus(healthy=True, latency_ms=1.0)

    with (
        patch("backend.observability.routers.health._check_redis", return_value=redis_ok),
        patch("backend.observability.routers.health._check_database", return_value=db_ok),
        patch("backend.observability.routers.health.settings") as mock_settings,
    ):
        mock_settings.MCP_TOOLS = False
        response = await health_check(request)

    assert response.version == "0.1.0"
