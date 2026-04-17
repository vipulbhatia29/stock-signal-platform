"""Tests for ObservabilityClient.emit_sync — sync emission from worker threads."""

import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
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


@pytest.mark.asyncio
async def test_emit_sync_from_thread(tmp_path):
    """emit_sync called from a worker thread delivers events after flush."""
    target = MemoryTarget()
    client = ObservabilityClient(
        target=target,
        spool_dir=tmp_path,
        spool_enabled=False,
        flush_interval_ms=50,
        buffer_size=100,
        enabled=True,
    )
    await client.start()
    try:

        def push():
            for _ in range(10):
                client.emit_sync(_e())

        t = threading.Thread(target=push)
        t.start()
        t.join()
        await client.flush()
        assert len(target.events) == 10
    finally:
        await client.stop()


def test_emit_sync_never_raises():
    """Rate-limiter + yfinance call this from sync hot paths — MUST NOT raise."""
    tmp = Path(tempfile.mkdtemp())
    client = ObservabilityClient(
        target=MemoryTarget(fail_next=99999),
        spool_dir=tmp,
        spool_enabled=False,
        flush_interval_ms=50,
        buffer_size=1,
        enabled=True,
    )
    # No start() — still must not raise.
    for _ in range(100):
        client.emit_sync(_e())
