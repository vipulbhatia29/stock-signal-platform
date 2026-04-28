"""Spec A — @tracked_task must never persist str(exception) (Hard Rule #10).

Uses the testcontainers `db_session` fixture and patches the decorator's
`async_session_factory` lookup to share that single session for both the
start-run write, the recovery error update, and the test's verification
read. One engine, one session, no asyncpg pool conflicts when running
inside the full API suite.

Raises a real RuntimeError("db password hunter2 leaked") and asserts the
literal does not appear anywhere in the persisted error_summary.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.pipeline import PipelineRun
from backend.tasks import pipeline as pipeline_mod


@pytest.mark.asyncio
async def test_tracked_task_error_summary_does_not_leak_exception_string(
    db_session: AsyncSession,
) -> None:
    """Hard Rule #10: persisted error_summary must never contain raw exception text.

    Patches `async_session_factory` in the pipeline module so the decorator's
    start-run insert and recovery update both land on the test's `db_session`
    (testcontainers-backed). Then reads back from the same session and asserts
    the literal "hunter2" and "db password" are absent and that error_summary
    is the safe generic value `{"_exception": "see logs"}`.
    """

    @asynccontextmanager
    async def _shared_session_factory():
        """Yield the shared db_session for every decorator call."""
        yield db_session

    with patch("backend.database.async_session_factory", _shared_session_factory):

        @pipeline_mod.tracked_task("redaction_audit_spec_a")
        async def inner(*, run_id: uuid.UUID) -> None:
            """Inner task that raises with a recognisable secret in its message."""
            raise RuntimeError("db password hunter2 leaked")

        with pytest.raises(RuntimeError):
            await inner()

    row = (
        await db_session.execute(
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
    assert row.error_summary == {"_exception": "see logs"}
