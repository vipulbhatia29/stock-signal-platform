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
    assert resp.json()["detail"] == "unauthorized"


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
    assert resp.json()["detail"] == "unauthorized"


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
    assert resp.json()["detail"] == "batch too large"


@pytest.mark.asyncio
async def test_ingest_accepts_max_batch_size(client, monkeypatch):
    """Batch of exactly MAX_EVENTS_PER_BATCH (500) is accepted."""
    monkeypatch.setattr("backend.config.settings.OBS_INGEST_SECRET", "testsecret")
    resp = await client.post(
        "/obs/v1/events",
        json={"events": [_payload()] * 500, "schema_version": "v1"},
        headers={"X-Obs-Secret": "testsecret"},
    )
    assert resp.status_code == 202
    assert resp.json() == {"accepted": 500}


@pytest.mark.asyncio
async def test_ingest_rejects_unsupported_schema_version(client, monkeypatch):
    """Unsupported schema_version returns 422 via Pydantic validation."""
    monkeypatch.setattr("backend.config.settings.OBS_INGEST_SECRET", "testsecret")
    resp = await client.post(
        "/obs/v1/events",
        json={"events": [_payload()], "schema_version": "v99"},
        headers={"X-Obs-Secret": "testsecret"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_ingest_rejects_empty_batch(client, monkeypatch):
    """Empty events list returns 422 via Pydantic min_length validation."""
    monkeypatch.setattr("backend.config.settings.OBS_INGEST_SECRET", "testsecret")
    resp = await client.post(
        "/obs/v1/events",
        json={"events": [], "schema_version": "v1"},
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
    assert resp.json()["detail"] == "unauthorized"


@pytest.mark.asyncio
async def test_ingest_returns_503_when_writer_raises(client, monkeypatch):
    """write_batch failure surfaces as 503 for client retry."""
    monkeypatch.setattr("backend.config.settings.OBS_INGEST_SECRET", "testsecret")

    async def _boom(events):
        raise RuntimeError("db unavailable")

    monkeypatch.setattr("backend.observability.routers.ingest.write_batch", _boom)
    resp = await client.post(
        "/obs/v1/events",
        json={"events": [_payload()], "schema_version": "v1"},
        headers={"X-Obs-Secret": "testsecret"},
    )
    assert resp.status_code == 503
    assert resp.json()["detail"] == "event_writer_failure"
