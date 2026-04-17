"""Tests for ObservabilityTarget implementations (MemoryTarget, DirectTarget)."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from backend.observability.schema.v1 import EventType, ObsEventBase
from backend.observability.targets.base import BatchResult
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
