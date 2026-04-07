"""Unit tests for the @tracked_task decorator on PipelineRunner."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.asyncio


async def test_tracked_task_happy_path_calls_start_and_complete() -> None:
    """Decorator runs start_run → fn → complete_run on success."""
    from backend.tasks import pipeline

    run_id = uuid.uuid4()

    with (
        patch.object(
            pipeline.PipelineRunner, "start_run", new=AsyncMock(return_value=run_id)
        ) as start_mock,
        patch.object(pipeline.PipelineRunner, "complete_run", new=AsyncMock()) as complete_mock,
    ):

        @pipeline.tracked_task("unit_test_pipeline")
        async def inner(*, run_id: uuid.UUID) -> dict[str, bool]:
            """Inner task that returns a success dict."""
            assert isinstance(run_id, uuid.UUID)
            return {"ok": True}

        result = await inner()

    assert result == {"ok": True}
    start_mock.assert_awaited_once()
    complete_mock.assert_awaited_once_with(run_id)


async def test_tracked_task_injects_run_id_kwarg() -> None:
    """Inner fn must receive `run_id` as a kwarg."""
    from backend.tasks import pipeline

    run_id = uuid.uuid4()
    received: dict[str, uuid.UUID] = {}

    with (
        patch.object(pipeline.PipelineRunner, "start_run", new=AsyncMock(return_value=run_id)),
        patch.object(pipeline.PipelineRunner, "complete_run", new=AsyncMock()),
    ):

        @pipeline.tracked_task("p")
        async def inner(*, run_id: uuid.UUID) -> None:
            """Inner task that captures run_id."""
            received["run_id"] = run_id

        await inner()

    assert received["run_id"] == run_id


async def test_tracked_task_forwards_tickers_total() -> None:
    """`tickers_total` is consumed by the decorator, not forwarded to inner."""
    from backend.tasks import pipeline

    run_id = uuid.uuid4()
    start_mock = AsyncMock(return_value=run_id)

    with (
        patch.object(pipeline.PipelineRunner, "start_run", new=start_mock),
        patch.object(pipeline.PipelineRunner, "complete_run", new=AsyncMock()),
    ):

        @pipeline.tracked_task("p")
        async def inner(*, run_id: uuid.UUID) -> None:
            """Inner task that would raise TypeError if tickers_total leaked through."""
            pass

        await inner(tickers_total=500)

    call_kwargs = start_mock.await_args.kwargs
    assert call_kwargs["tickers_total"] == 500
    assert call_kwargs["pipeline_name"] == "p"


async def test_tracked_task_marks_failed_on_exception() -> None:
    """Inner raises → PipelineRun marked failed; exception re-raised."""
    from backend.tasks import pipeline

    run_id = uuid.uuid4()
    fake_session = AsyncMock()
    fake_session.execute = AsyncMock(return_value=MagicMock())
    fake_session.commit = AsyncMock()

    with (
        patch.object(pipeline.PipelineRunner, "start_run", new=AsyncMock(return_value=run_id)),
        patch.object(pipeline.PipelineRunner, "complete_run", new=AsyncMock()) as complete_mock,
        patch.object(pipeline, "async_session_factory") as factory_mock,
    ):
        factory_mock.return_value.__aenter__.return_value = fake_session
        factory_mock.return_value.__aexit__.return_value = None

        @pipeline.tracked_task("p")
        async def inner(*, run_id: uuid.UUID) -> None:
            """Inner task that raises."""
            raise ValueError("secret db password hunter2")

        with pytest.raises(ValueError):
            await inner()

    # complete_run must NOT be called on exception path
    complete_mock.assert_not_awaited()
    # Session was used to mark the row failed
    fake_session.execute.assert_awaited_once()
    fake_session.commit.assert_awaited_once()

    # Hard Rule #10: error_summary must never carry the raw exception string.
    # Inspect what was passed in the update statement's values.
    stmt = fake_session.execute.await_args[0][0]
    compiled = str(stmt)
    assert "hunter2" not in compiled
    assert "secret db password" not in compiled


async def test_tracked_task_no_str_e_leakage() -> None:
    """Regression for Hard Rule #10: exception message must not appear in DB write."""
    from backend.tasks import pipeline

    run_id = uuid.uuid4()
    execute_args_list: list = []
    fake_session = AsyncMock()

    async def capture_execute(stmt):
        """Capture and return mock result."""
        execute_args_list.append(str(stmt))
        return MagicMock()

    fake_session.execute = AsyncMock(side_effect=capture_execute)
    fake_session.commit = AsyncMock()

    with (
        patch.object(pipeline.PipelineRunner, "start_run", new=AsyncMock(return_value=run_id)),
        patch.object(pipeline.PipelineRunner, "complete_run", new=AsyncMock()),
        patch.object(pipeline, "async_session_factory") as factory_mock,
    ):
        factory_mock.return_value.__aenter__.return_value = fake_session
        factory_mock.return_value.__aexit__.return_value = None

        @pipeline.tracked_task("p")
        async def inner(*, run_id: uuid.UUID) -> None:
            """Inner task with a secret in its error message."""
            raise RuntimeError("hunter2 is my real password")

        with pytest.raises(RuntimeError):
            await inner()

    # Check nothing leaked through the SQL statement
    all_sql = " ".join(execute_args_list)
    assert "hunter2" not in all_sql
    assert "real password" not in all_sql


async def test_tracked_task_default_trigger_is_scheduled() -> None:
    """Default trigger is 'scheduled'."""
    from backend.tasks import pipeline

    run_id = uuid.uuid4()
    start_mock = AsyncMock(return_value=run_id)

    with (
        patch.object(pipeline.PipelineRunner, "start_run", new=start_mock),
        patch.object(pipeline.PipelineRunner, "complete_run", new=AsyncMock()),
    ):

        @pipeline.tracked_task("p")
        async def inner(*, run_id: uuid.UUID) -> None:
            """Inner task."""
            pass

        await inner()

    assert start_mock.await_args.kwargs["trigger"] == "scheduled"


async def test_tracked_task_custom_trigger_passthrough() -> None:
    """Custom trigger flows through to start_run."""
    from backend.tasks import pipeline

    run_id = uuid.uuid4()
    start_mock = AsyncMock(return_value=run_id)

    with (
        patch.object(pipeline.PipelineRunner, "start_run", new=start_mock),
        patch.object(pipeline.PipelineRunner, "complete_run", new=AsyncMock()),
    ):

        @pipeline.tracked_task("p", trigger="manual")
        async def inner(*, run_id: uuid.UUID) -> None:
            """Inner task."""
            pass

        await inner()

    assert start_mock.await_args.kwargs["trigger"] == "manual"
