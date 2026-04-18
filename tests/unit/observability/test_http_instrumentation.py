"""Tests for HTTP observability middleware."""

from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from backend.observability.schema.v1 import EventType


def _make_test_app(status_code: int = 200) -> Starlette:
    """Build a minimal Starlette app with ObsHttpMiddleware for testing."""
    from backend.observability.instrumentation.http import ObsHttpMiddleware

    async def homepage(request: Request) -> JSONResponse:
        """Simple test endpoint."""
        if status_code >= 500:
            raise RuntimeError("Internal server error")
        return JSONResponse({"ok": True}, status_code=status_code)

    app = Starlette(routes=[Route("/api/v1/test", homepage)])
    app.add_middleware(ObsHttpMiddleware)
    return app


@pytest.fixture
def mock_obs_client() -> MagicMock:
    """Return a mock ObservabilityClient with emit_sync tracked."""
    client = MagicMock()
    client.emit_sync = MagicMock()
    return client


@pytest.mark.asyncio
async def test_request_log_emitted_on_success(mock_obs_client: MagicMock) -> None:
    """Successful request should emit a REQUEST_LOG event."""
    app = _make_test_app(200)
    app.state.obs_client = mock_obs_client

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/v1/test")

    assert resp.status_code == 200

    # Find the REQUEST_LOG emit call
    calls = [
        c
        for c in mock_obs_client.emit_sync.call_args_list
        if c.args
        and hasattr(c.args[0], "event_type")
        and c.args[0].event_type == EventType.REQUEST_LOG
    ]
    assert len(calls) >= 1
    event = calls[0].args[0]
    assert event.method == "GET"
    assert event.status_code == 200
    assert event.latency_ms >= 0


@pytest.mark.asyncio
async def test_request_log_skipped_when_obs_disabled() -> None:
    """When OBS_ENABLED=false, no REQUEST_LOG emission should occur."""
    mock_client = MagicMock()
    mock_client.emit_sync = MagicMock()

    with patch("backend.observability.instrumentation.http.settings") as mock_settings:
        mock_settings.OBS_ENABLED = False

        app = _make_test_app(200)
        app.state.obs_client = mock_client

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            await ac.get("/api/v1/test")

    # emit_sync should NOT have been called for REQUEST_LOG
    request_log_calls = [
        c
        for c in mock_client.emit_sync.call_args_list
        if c.args
        and hasattr(c.args[0], "event_type")
        and c.args[0].event_type == EventType.REQUEST_LOG
    ]
    assert len(request_log_calls) == 0


@pytest.mark.asyncio
async def test_api_error_log_emitted_on_4xx(mock_obs_client: MagicMock) -> None:
    """4xx response should emit an API_ERROR_LOG event."""
    app = _make_test_app(404)
    app.state.obs_client = mock_obs_client

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/v1/test")

    assert resp.status_code == 404

    error_calls = [
        c
        for c in mock_obs_client.emit_sync.call_args_list
        if c.args
        and hasattr(c.args[0], "event_type")
        and c.args[0].event_type == EventType.API_ERROR_LOG
    ]
    assert len(error_calls) >= 1
    event = error_calls[0].args[0]
    assert event.status_code == 404


@pytest.mark.asyncio
async def test_no_emission_when_obs_client_missing() -> None:
    """When obs_client is not on app.state, middleware should not raise."""
    from backend.observability.instrumentation.http import ObsHttpMiddleware

    async def homepage(request: Request) -> JSONResponse:
        """Simple test endpoint."""
        return JSONResponse({"ok": True})

    app = Starlette(routes=[Route("/api/v1/test", homepage)])
    app.add_middleware(ObsHttpMiddleware)
    # No obs_client set on app.state

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/v1/test")

    assert resp.status_code == 200  # Should not blow up
