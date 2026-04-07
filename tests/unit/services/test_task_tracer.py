"""Unit tests for trace_task async context manager."""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.asyncio


def _make_langfuse(trace_obj=None):
    """Build a MagicMock LangfuseService. trace_obj=None simulates disabled."""
    svc = MagicMock()
    svc.create_trace = MagicMock(return_value=trace_obj)
    return svc


def _make_collector():
    """Build a MagicMock ObservabilityCollector."""
    collector = MagicMock()
    collector.record_request = AsyncMock()
    return collector


async def test_trace_task_creates_langfuse_trace_with_task_metadata() -> None:
    """create_trace called with metadata containing task name + extras."""
    from backend.services.observability.task_tracer import trace_task

    trace_obj = MagicMock()
    langfuse = _make_langfuse(trace_obj)
    collector = _make_collector()

    async with trace_task(
        "nightly_sentiment",
        langfuse=langfuse,
        collector=collector,
        metadata={"ticker_count": 500},
    ) as handle:
        assert handle.name == "nightly_sentiment"

    langfuse.create_trace.assert_called_once()
    call_kwargs = langfuse.create_trace.call_args.kwargs
    assert call_kwargs["metadata"]["task"] == "nightly_sentiment"
    assert call_kwargs["metadata"]["ticker_count"] == 500


async def test_trace_task_handles_disabled_langfuse() -> None:
    """Disabled Langfuse (create_trace → None) must not raise."""
    from backend.services.observability.task_tracer import trace_task

    langfuse = _make_langfuse(trace_obj=None)
    collector = _make_collector()

    async with trace_task("x", langfuse=langfuse, collector=collector) as handle:
        assert handle._trace is None


async def test_trace_task_records_llm_via_collector() -> None:
    """handle.record_llm delegates to collector.record_request."""
    from backend.services.observability.task_tracer import trace_task

    trace_obj = MagicMock()
    langfuse = _make_langfuse(trace_obj)
    collector = _make_collector()

    async with trace_task("x", langfuse=langfuse, collector=collector) as handle:
        await handle.record_llm(
            model="gpt-4o-mini",
            provider="openai",
            tier="cheap",
            latency_ms=450,
            prompt_tokens=300,
            completion_tokens=40,
            cost_usd=0.0012,
        )

    collector.record_request.assert_awaited_once()
    kwargs = collector.record_request.await_args.kwargs
    assert kwargs["model"] == "gpt-4o-mini"
    assert kwargs["langfuse_trace_id"] == handle.trace_id
    assert isinstance(handle.trace_id, uuid.UUID)


async def test_trace_task_exception_sets_error_status() -> None:
    """Exception inside context → status=error, re-raised."""
    from backend.services.observability.task_tracer import TaskTraceHandle, trace_task

    trace_obj = MagicMock()
    langfuse = _make_langfuse(trace_obj)
    collector = _make_collector()
    captured: dict[str, TaskTraceHandle] = {}

    with pytest.raises(ValueError):
        async with trace_task("x", langfuse=langfuse, collector=collector) as handle:
            captured["handle"] = handle
            raise ValueError("boom")

    assert captured["handle"]._status == "error"
    assert captured["handle"]._error == "ValueError"


async def test_trace_task_measures_duration_ms() -> None:
    """Duration is measured in ms and proves the timer is actually wired up.

    Uses asyncio.sleep (non-blocking) to yield at least ~10ms; asserts >= 5ms
    so the test is resilient to scheduler jitter while still proving measurement.
    Using time.sleep here would block the event loop (Staff M8).
    """
    from backend.services.observability.task_tracer import trace_task

    trace_obj = MagicMock()
    langfuse = _make_langfuse(trace_obj)
    collector = _make_collector()

    async with trace_task("x", langfuse=langfuse, collector=collector) as handle:
        await asyncio.sleep(0.01)

    assert handle._duration_ms >= 5, (
        f"Expected duration >= 5ms (proves timer is wired up); got {handle._duration_ms}ms"
    )


async def test_trace_task_finalize_swallows_langfuse_errors() -> None:
    """trace.update raising must not propagate out of the context manager."""
    from backend.services.observability.task_tracer import trace_task

    trace_obj = MagicMock()
    trace_obj.update = MagicMock(side_effect=RuntimeError("langfuse down"))
    langfuse = _make_langfuse(trace_obj)
    collector = _make_collector()

    # Must exit cleanly
    async with trace_task("x", langfuse=langfuse, collector=collector) as handle:
        handle.add_metadata(foo="bar")


async def test_trace_task_add_metadata_merges_into_final_update() -> None:
    """add_metadata values appear in the trace.update call on exit."""
    from backend.services.observability.task_tracer import trace_task

    trace_obj = MagicMock()
    langfuse = _make_langfuse(trace_obj)
    collector = _make_collector()

    async with trace_task("x", langfuse=langfuse, collector=collector) as handle:
        handle.add_metadata(articles=10)

    trace_obj.update.assert_called_once()
    metadata = trace_obj.update.call_args.kwargs["metadata"]
    assert metadata["articles"] == 10
    assert metadata["task"] == "x"
    assert metadata["status"] == "completed"
