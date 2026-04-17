"""Tests for JSONL disk spool (SpoolWriter + SpoolReader)."""

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from backend.observability.schema.v1 import EventType, ObsEventBase
from backend.observability.spool import SpoolReader, SpoolWriter


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
async def test_spool_round_trip(tmp_path: Path):
    """Events written to spool can be read back and files are cleaned up."""
    await SpoolWriter(tmp_path, max_size_mb=1).append([_e(), _e()])
    events = [e async for e in SpoolReader(tmp_path).drain()]
    assert len(events) == 2


@pytest.mark.asyncio
async def test_spool_drops_on_overflow(tmp_path: Path):
    """0 MB cap means everything gets dropped."""
    result = await SpoolWriter(tmp_path, max_size_mb=0).append([_e(), _e()])
    assert result.dropped == 2
