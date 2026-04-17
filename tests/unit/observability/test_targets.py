"""Tests for ObservabilityTarget implementations (MemoryTarget, DirectTarget)."""

import json
from datetime import datetime, timezone
from uuid import uuid4

import httpx
import pytest

from backend.observability.schema.v1 import EventType, ObsEventBase
from backend.observability.targets.base import BatchResult
from backend.observability.targets.internal_http import OBS_AUTH_HEADER, InternalHTTPTarget
from backend.observability.targets.memory import MemoryTarget


def _event() -> ObsEventBase:
    """Create a minimal valid event for testing."""
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
    )


@pytest.mark.asyncio
async def test_memory_target_accepts_batch():
    """MemoryTarget stores events and reports correct sent count."""
    target = MemoryTarget()
    result = await target.send_batch([_event(), _event()])
    assert result == BatchResult(sent=2, failed=0)
    assert len(target.events) == 2


@pytest.mark.asyncio
async def test_memory_target_health_ok():
    """MemoryTarget always reports healthy."""
    assert (await MemoryTarget().health()).healthy is True


@pytest.mark.asyncio
async def test_memory_target_fail_next():
    """MemoryTarget simulates failures when fail_next > 0, then recovers."""
    target = MemoryTarget(fail_next=1)
    assert (await target.send_batch([_event()])).failed == 1
    assert (await target.send_batch([_event()])).sent == 1


# --- InternalHTTPTarget tests ---


class _StubTransport(httpx.MockTransport):
    """Captures the last request for assertion."""

    def __init__(self, status: int = 202):
        self._status = status
        super().__init__(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.last_request = request  # type: ignore[attr-defined]
        return httpx.Response(self._status, json={"accepted": 1})


@pytest.mark.asyncio
async def test_internal_http_target_sends_batch():
    """InternalHTTPTarget POSTs batch with X-Obs-Secret to /obs/v1/events."""
    transport = _StubTransport(status=202)
    client = httpx.AsyncClient(transport=transport)
    target = InternalHTTPTarget(
        base_url="http://localhost:8181",
        secret="s3cret",
        client=client,
    )
    result = await target.send_batch([_event()])
    assert result.sent == 1
    assert result.failed == 0
    assert target.last_error is None
    assert transport.last_request.headers.get(OBS_AUTH_HEADER) == "s3cret"
    assert transport.last_request.url.path == "/obs/v1/events"
    # Verify request body contains events + schema_version
    body = json.loads(transport.last_request.content)
    assert body["schema_version"] == "v1"
    assert len(body["events"]) == 1
    assert body["events"][0]["event_type"] == "llm_call"


@pytest.mark.asyncio
async def test_internal_http_target_populates_last_success_ts():
    """InternalHTTPTarget populates last_success_ts on 202 for health reporting."""
    transport = _StubTransport(status=202)
    target = InternalHTTPTarget(
        base_url="http://localhost:8181",
        secret="s3cret",
        client=httpx.AsyncClient(transport=transport),
    )
    await target.send_batch([_event()])
    health = await target.health()
    assert health.healthy is True
    assert health.last_success_ts is not None


@pytest.mark.asyncio
async def test_internal_http_target_handles_5xx():
    """InternalHTTPTarget classifies 5xx as failure with status_NNN error."""
    transport = _StubTransport(status=503)
    target = InternalHTTPTarget(
        base_url="http://localhost:8181",
        secret="s3cret",
        client=httpx.AsyncClient(transport=transport),
    )
    result = await target.send_batch([_event(), _event()])
    assert result.failed == 2
    assert result.error == "status_503"
    assert target.last_error == "status_503"


@pytest.mark.asyncio
async def test_internal_http_target_handles_connection_error():
    """InternalHTTPTarget classifies connection errors as failures."""

    async def _raise(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    target = InternalHTTPTarget(
        base_url="http://localhost:8181",
        secret="s3cret",
        client=httpx.AsyncClient(transport=httpx.MockTransport(_raise)),
    )
    result = await target.send_batch([_event()])
    assert result.failed == 1
    assert result.error == "ConnectError"
    assert target.last_error == "ConnectError"


@pytest.mark.asyncio
async def test_internal_http_target_aclose_owned_client():
    """aclose() closes the client when InternalHTTPTarget owns it."""
    target = InternalHTTPTarget(
        base_url="http://localhost:8181",
        secret="s3cret",
    )
    assert target._owns_client is True
    await target.aclose()


@pytest.mark.asyncio
async def test_internal_http_target_aclose_injected_client():
    """aclose() skips closing when client was injected externally."""
    transport = _StubTransport(status=202)
    ext_client = httpx.AsyncClient(transport=transport)
    target = InternalHTTPTarget(
        base_url="http://localhost:8181",
        secret="s3cret",
        client=ext_client,
    )
    assert target._owns_client is False
    await target.aclose()
    # External client should still be usable
    assert not ext_client.is_closed


# --- DirectTarget tests ---


@pytest.mark.asyncio
async def test_direct_target_delegates_to_writer():
    """DirectTarget delegates to a custom writer function and reports sent count."""
    from backend.observability.targets.direct import DirectTarget

    called: list[list[ObsEventBase]] = []

    async def fake_writer(events: list[ObsEventBase]) -> None:
        called.append(list(events))

    result = await DirectTarget(event_writer=fake_writer).send_batch([_event(), _event()])
    assert result.sent == 2 and result.failed == 0
    assert len(called) == 1 and len(called[0]) == 2
