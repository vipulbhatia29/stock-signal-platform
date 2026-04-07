"""Spec A — @tracked_task must never persist str(exception) (Hard Rule #10).

This test uses a real database session (via async_session_factory, matching
the decorator's own session) to verify that when a task crashes with
RuntimeError("hunter2 leaked"), the persisted pipeline_runs row does NOT
contain that literal string anywhere in error_summary.

The decorator opens its own session via async_session_factory — we query
using the same factory so we see the same database row.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from backend.database import async_session_factory
from backend.models.pipeline import PipelineRun
from backend.tasks import pipeline as pipeline_mod


@pytest.mark.asyncio
async def test_tracked_task_error_summary_does_not_leak_exception_string() -> None:
    """Hard Rule #10: persisted error_summary must never contain raw exception text.

    Raises a real RuntimeError with a known string ("hunter2") and then
    queries the pipeline_runs table (via the same async_session_factory the
    decorator uses) to confirm the string is absent from error_summary.
    """

    @pipeline_mod.tracked_task("redaction_audit_spec_a")
    async def inner(*, run_id: uuid.UUID) -> None:
        """Inner task that raises with a recognisable secret in its message."""
        raise RuntimeError("db password hunter2 leaked")

    with pytest.raises(RuntimeError):
        await inner()

    # The decorator opens its own session via async_session_factory.
    # Query using the same factory to see the committed row.
    async with async_session_factory() as session:
        row = (
            await session.execute(
                select(PipelineRun)
                .where(PipelineRun.pipeline_name == "redaction_audit_spec_a")
                .order_by(PipelineRun.started_at.desc())
                .limit(1)
            )
        ).scalar_one()

    assert row.status == "failed"
    joined = str(row.error_summary or {})
    assert "hunter2" not in joined
    assert "db password" not in joined
    # error_summary must be the safe generic value, not the exception class name
    assert row.error_summary == {"_exception": "see logs"}
