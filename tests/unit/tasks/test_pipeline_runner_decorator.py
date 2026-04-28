"""Unit tests for the @tracked_task decorator on PipelineRunner."""

from __future__ import annotations

import typing
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
    """Inner raises → PipelineRun marked failed; exception re-raised.

    Asserts that exactly one UPDATE statement was issued and one commit,
    verifying the failure path hits the DB. The authoritative leak-guard test
    (Hard Rule #10) lives in tests/api/test_tracked_task_error_redaction.py
    with a real DB — that test is the source of truth for str(e) redaction.
    """
    from backend.tasks import pipeline

    run_id = uuid.uuid4()
    fake_session = AsyncMock()
    fake_session.execute = AsyncMock(return_value=MagicMock())
    fake_session.commit = AsyncMock()

    with (
        patch.object(pipeline.PipelineRunner, "start_run", new=AsyncMock(return_value=run_id)),
        patch.object(pipeline.PipelineRunner, "complete_run", new=AsyncMock()) as complete_mock,
        patch("backend.database.async_session_factory") as factory_mock,
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
    # Session was used to mark the row failed — one execute + one commit
    fake_session.execute.assert_awaited_once()
    fake_session.commit.assert_awaited_once()


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


def test_ticker_failure_reason_is_literal_type() -> None:
    """TickerFailureReason must be a typing.Literal — enforces Hard Rule #10 at type-check time.

    Verifies that get_origin(TickerFailureReason) returns typing.Literal so
    pyright/mypy can reject callers that pass dynamic strings (e.g. str(e)).
    """
    from backend.tasks.pipeline import TickerFailureReason

    assert typing.get_origin(TickerFailureReason) is typing.Literal, (
        "TickerFailureReason must be a typing.Literal so pyright can enforce Hard Rule #10"
    )
