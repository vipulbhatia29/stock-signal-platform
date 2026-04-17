"""POST /obs/v1/events — validates ingest-endpoint contract."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from backend.observability.schema.v1 import EventType, ObsEventBase


def _payload() -> dict:
    """Create a minimal valid event payload dict."""
    return ObsEventBase(
        event_type=EventType.LLM_CALL,
        trace_id=uuid4(),
        span_id=uuid4(),
        parent_span_id=None,
        ts=datetime.now(timezone.utc),
        env="dev",
        git_sha=None,
        user_id=None,
        session_id=None,
        query_id=None,
    ).model_dump(mode="json")


@pytest.mark.asyncio
async def test_ingest_accepts_valid_batch(client, monkeypatch):
    """Valid batch with correct secret returns 202 with accepted count."""
    monkeypatch.setattr("backend.config.settings.OBS_INGEST_SECRET", "testsecret")
    resp = await client.post(
        "/obs/v1/events",
        json={"events": [_payload()], "schema_version": "v1"},
        headers={"X-Obs-Secret": "testsecret"},
    )
    assert resp.status_code == 202
    assert resp.json() == {"accepted": 1}


@pytest.mark.asyncio
async def test_ingest_rejects_missing_secret(client, monkeypatch):
    """Request without X-Obs-Secret header returns 401."""
    monkeypatch.setattr("backend.config.settings.OBS_INGEST_SECRET", "testsecret")
    resp = await client.post(
        "/obs/v1/events",
        json={"events": [_payload()], "schema_version": "v1"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_ingest_rejects_wrong_secret(client, monkeypatch):
    """Request with wrong X-Obs-Secret returns 401."""
    monkeypatch.setattr("backend.config.settings.OBS_INGEST_SECRET", "testsecret")
    resp = await client.post(
        "/obs/v1/events",
        json={"events": [_payload()], "schema_version": "v1"},
        headers={"X-Obs-Secret": "wrong"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_ingest_rejects_oversized_batch(client, monkeypatch):
    """Batch exceeding MAX_EVENTS_PER_BATCH returns 413."""
    monkeypatch.setattr("backend.config.settings.OBS_INGEST_SECRET", "testsecret")
    resp = await client.post(
        "/obs/v1/events",
        json={"events": [_payload()] * 501, "schema_version": "v1"},
        headers={"X-Obs-Secret": "testsecret"},
    )
    assert resp.status_code == 413


@pytest.mark.asyncio
async def test_ingest_rejects_unsupported_schema_version(client, monkeypatch):
    """Unsupported schema_version returns 422."""
    monkeypatch.setattr("backend.config.settings.OBS_INGEST_SECRET", "testsecret")
    resp = await client.post(
        "/obs/v1/events",
        json={"events": [_payload()], "schema_version": "v99"},
        headers={"X-Obs-Secret": "testsecret"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_ingest_rejects_when_secret_unset(client, monkeypatch):
    """Fail-closed: if OBS_INGEST_SECRET is None, all requests return 401."""
    monkeypatch.setattr("backend.config.settings.OBS_INGEST_SECRET", None)
    resp = await client.post(
        "/obs/v1/events",
        json={"events": [_payload()], "schema_version": "v1"},
        headers={"X-Obs-Secret": "anything"},
    )
    assert resp.status_code == 401
