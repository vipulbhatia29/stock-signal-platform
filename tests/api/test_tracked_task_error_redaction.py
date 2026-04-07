"""Spec A — @tracked_task must never persist str(exception) (Hard Rule #10).

This test patches async_session_factory in backend.tasks.pipeline to use the
testcontainers DB so all sessions (decorator writes + test reads) share the
same isolated database. Raises a real RuntimeError("hunter2 leaked") and then
queries the pipeline_runs row to confirm the string is absent from
error_summary.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.models.pipeline import PipelineRun
from backend.tasks import pipeline as pipeline_mod


@pytest.mark.asyncio
async def test_tracked_task_error_summary_does_not_leak_exception_string(
    db_url: str,
) -> None:
    """Hard Rule #10: persisted error_summary must never contain raw exception text.

    Patches async_session_factory in the pipeline module to use the
    testcontainers DB so both the decorator's write and the test's read
    see the same row. Raises a real RuntimeError with "hunter2" and asserts
    that string is absent from the persisted error_summary.
    """
    engine = create_async_engine(db_url, echo=False)
    test_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    @asynccontextmanager
    async def _test_session_factory():
        """Yield a testcontainers-backed session."""
        async with test_factory() as session:
            yield session

    with patch.object(pipeline_mod, "async_session_factory", _test_session_factory):

        @pipeline_mod.tracked_task("redaction_audit_spec_a")
        async def inner(*, run_id: uuid.UUID) -> None:
            """Inner task that raises with a recognisable secret in its message."""
            raise RuntimeError("db password hunter2 leaked")

        with pytest.raises(RuntimeError):
            await inner()

        # Read back from the same testcontainers DB to verify the row.
        async with _test_session_factory() as session:
            row = (
                await session.execute(
                    select(PipelineRun)
                    .where(PipelineRun.pipeline_name == "redaction_audit_spec_a")
                    .order_by(PipelineRun.started_at.desc())
                    .limit(1)
                )
            ).scalar_one()

    await engine.dispose()

    assert row.status == "failed"
    joined = str(row.error_summary or {})
    assert "hunter2" not in joined
    assert "db password" not in joined
    # error_summary must be the safe generic value, not the raw exception type
    assert row.error_summary == {"_exception": "see logs"}
