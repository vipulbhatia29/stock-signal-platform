"""Tests for ObservabilityClient — emit, flush, kill-switch, spool recovery."""

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from backend.observability.client import ObservabilityClient
from backend.observability.schema.v1 import EventType, ObsEventBase
from backend.observability.targets.memory import MemoryTarget


def _e() -> ObsEventBase:
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


async def _make_client(tmp_path, *, enabled=True, spool=False, target=None) -> ObservabilityClient:
    """Helper to build and start a test client."""
    client = ObservabilityClient(
        target=target or MemoryTarget(),
        spool_dir=tmp_path,
        spool_enabled=spool,
        flush_interval_ms=50,
        buffer_size=100,
        enabled=enabled,
        reclaim_interval_s=0.1,  # fast reclaim for tests
    )
    await client.start()
    return client


@pytest.mark.asyncio
async def test_emit_round_trip(tmp_path):
    """Events emitted via emit() arrive at the target after flush()."""
    target = MemoryTarget()
    client = await _make_client(tmp_path, target=target)
    try:
        await client.emit(_e())
        await client.flush()
        assert len(target.events) == 1
    finally:
        await client.stop()


@pytest.mark.asyncio
async def test_emit_is_no_op_when_disabled(tmp_path):
    """OBS_ENABLED=false means emit() is a no-op; no events reach target."""
    target = MemoryTarget()
    client = await _make_client(tmp_path, enabled=False, target=target)
    try:
        await client.emit(_e())
        await client.flush()
        assert target.events == []
    finally:
        await client.stop()


@pytest.mark.asyncio
async def test_target_down_spools_and_drains(tmp_path):
    """Target failure spools events; after recovery, reclaim delivers them."""
    target = MemoryTarget(fail_next=1)
    client = await _make_client(tmp_path, spool=True, target=target)
    try:
        await client.emit(_e())
        await client.flush()
        # Give reclaim loop time to replay the spooled event.
        await asyncio.sleep(0.2)
        await client.flush()
        assert len(target.events) == 1
    finally:
        await client.stop()


@pytest.mark.asyncio
async def test_emit_never_raises(tmp_path):
    """Even with all failures + spool off, emit() must not raise."""
    target = MemoryTarget(fail_next=10_000)
    client = await _make_client(tmp_path, spool=False, target=target)
    try:
        for _ in range(100):
            await client.emit(_e())
        await client.flush()
    finally:
        await client.stop()


def test_buffer_concurrent_producers_respect_max_size():
    """10 threads × 100 events with max_size=500 → qsize ≤ 500 + drops == 500.

    Validates that queue.Queue(maxsize=N) provides a hard bound under concurrent
    producers, which is the core reason Queue was chosen over SimpleQueue.
    """
    import threading

    from backend.observability.buffer import EventBuffer

    buf = EventBuffer(max_size=500)
    barrier = threading.Barrier(10)

    def push():
        barrier.wait()
        for _ in range(100):
            buf.try_put(_e())

    threads = [threading.Thread(target=push) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    stats = buf.stats()
    assert stats.depth <= 500
    assert stats.depth + stats.drops == 1000
