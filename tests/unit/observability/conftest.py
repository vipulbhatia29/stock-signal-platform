"""Fixtures for observability unit tests.

Provides a lightweight `client` fixture using httpx AsyncClient with
ASGITransport — no real database required.  The health endpoint used in
middleware tests does not hit the DB, so no session override is needed.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from backend.main import app


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Provide an httpx AsyncClient backed by the FastAPI ASGI app.

    No database connection is established — suitable for middleware-layer
    tests that only call DB-free endpoints such as /api/v1/health.
    """
    app.state.limiter.enabled = False
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.state.limiter.enabled = True
