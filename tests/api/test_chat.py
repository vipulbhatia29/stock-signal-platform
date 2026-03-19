"""API tests for chat endpoints."""

import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_chat_stream_requires_auth(client: AsyncClient):
    """POST /chat/stream returns 401 without auth."""
    resp = await client.post("/api/v1/chat/stream", json={"message": "Hi"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_chat_stream_new_session_requires_agent_type(
    authenticated_client: AsyncClient,
):
    """POST /chat/stream without session_id requires agent_type."""
    resp = await authenticated_client.post(
        "/api/v1/chat/stream",
        json={"message": "Hi"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_chat_sessions_list_requires_auth(client: AsyncClient):
    """GET /chat/sessions returns 401 without auth."""
    resp = await client.get("/api/v1/chat/sessions")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_chat_sessions_list(authenticated_client: AsyncClient):
    """GET /chat/sessions returns user's sessions."""
    resp = await authenticated_client.get("/api/v1/chat/sessions")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_chat_session_delete_requires_auth(client: AsyncClient):
    """DELETE /chat/sessions/{id} returns 401 without auth."""
    fake_id = uuid.uuid4()
    resp = await client.delete(f"/api/v1/chat/sessions/{fake_id}")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_chat_session_delete_not_found(authenticated_client: AsyncClient):
    """DELETE /chat/sessions/{id} returns 404 for non-existent session."""
    fake_id = uuid.uuid4()
    resp = await authenticated_client.delete(f"/api/v1/chat/sessions/{fake_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_chat_session_messages_requires_auth(client: AsyncClient):
    """GET /chat/sessions/{id}/messages returns 401 without auth."""
    fake_id = uuid.uuid4()
    resp = await client.get(f"/api/v1/chat/sessions/{fake_id}/messages")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_chat_session_messages_empty(authenticated_client: AsyncClient):
    """GET /chat/sessions/{id}/messages returns empty list for unknown session."""
    fake_id = uuid.uuid4()
    resp = await authenticated_client.get(f"/api/v1/chat/sessions/{fake_id}/messages")
    assert resp.status_code == 200
    assert resp.json() == []
