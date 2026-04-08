"""Spec D.5 — Plan D consumes Spec A's trace_task; verify wiring.

These tests lock in the contract Plan D depends on:
    * `trace_task` is an async context manager
    * Success path finalizes with status="completed"
    * Finalize swallows Langfuse errors (fire-and-forget)
    * `record_llm` awaits `ObservabilityCollector.record_request`

Spec A's `main.py` lifespan already publishes the module-level
singletons (`set_langfuse_service` / `set_observability_collector`),
so Plan D Task 1 only needs these consumer-side tests plus the
Langfuse feature flags added to `backend/config.py`.

The `Settings.LANGFUSE_TRACK_TASKS` kill switch is enforced at the
decorator layer (Task 2 — `@tracked_task`); these tests exercise the
underlying `trace_task` contract and therefore pass fake services
directly rather than relying on the flag.
"""

from unittest.mock import AsyncMock, MagicMock

from backend.services.observability.task_tracer import trace_task


async def test_trace_task_no_op_when_langfuse_disabled() -> None:
    """When LangfuseService returns None, trace_task yields a usable handle.

    The handle still accepts metadata calls without raising. This is the
    path exercised when `LANGFUSE_SECRET_KEY` is unset in dev/CI.
    """
    fake_langfuse = MagicMock()
    fake_langfuse.create_trace.return_value = None  # disabled path
    fake_collector = MagicMock()

    async with trace_task("x", langfuse=fake_langfuse, collector=fake_collector) as handle:
        handle.add_metadata(k=1)  # does not raise

    # trace_task must still call create_trace on the disabled path —
    # the no-op behavior comes from create_trace returning None, not
    # from trace_task short-circuiting the call entirely. If a future
    # refactor adds a pre-check that skips create_trace, this test
    # should fail so the disabled-path contract stays explicit.
    # (If _finalize tried to call .update() on the None trace, we'd
    # already have AttributeError above — the success of the `async
    # with` exit is the implicit assertion that no method access
    # happened on the None trace.)
    fake_langfuse.create_trace.assert_called_once()


async def test_trace_task_creates_trace_when_enabled() -> None:
    """On success, trace_task finalizes with completed status + merged metadata."""
    fake_trace = MagicMock()
    fake_langfuse = MagicMock()
    fake_langfuse.create_trace.return_value = fake_trace
    fake_collector = MagicMock()
    fake_collector.record_request = AsyncMock()

    async with trace_task(
        "prophet_train",
        langfuse=fake_langfuse,
        collector=fake_collector,
        metadata={"ticker": "AAPL"},
    ) as handle:
        handle.add_metadata(mape=0.03)

    fake_langfuse.create_trace.assert_called_once()
    fake_trace.update.assert_called_once()

    # Initial metadata (passed at trace_task entry) must go to
    # create_trace, NOT to the final update() — these are separate
    # metadata bags with different lifecycles. Locking in the split.
    create_metadata = fake_langfuse.create_trace.call_args.kwargs["metadata"]
    assert create_metadata["task"] == "prophet_train"
    assert create_metadata["ticker"] == "AAPL"

    # Runtime metadata (add_metadata inside the block) is merged into
    # the finalize update() call along with status/task/duration.
    update_kwargs = fake_trace.update.call_args.kwargs["metadata"]
    assert update_kwargs["task"] == "prophet_train"
    assert update_kwargs["mape"] == 0.03
    assert update_kwargs["status"] == "completed"
    # Initial metadata (ticker) should NOT appear in the finalize update.
    assert "ticker" not in update_kwargs


async def test_trace_task_finalize_swallows_langfuse_errors() -> None:
    """If `trace.update` raises, trace_task exits cleanly (fire-and-forget).

    Telemetry must never break the wrapped task. Regression guard for
    Spec A's `_finalize` try/except contract.
    """
    fake_trace = MagicMock()
    fake_trace.update.side_effect = RuntimeError("boom")
    fake_langfuse = MagicMock()
    fake_langfuse.create_trace.return_value = fake_trace
    fake_collector = MagicMock()

    async with trace_task("x", langfuse=fake_langfuse, collector=fake_collector) as _handle:
        pass  # finalize runs on exit; the raised error must be swallowed
    # If we reach this line without RuntimeError, the contract holds.


async def test_trace_task_records_llm_via_collector() -> None:
    """`handle.record_llm` forwards to `ObservabilityCollector.record_request`."""
    fake_trace = MagicMock()
    fake_langfuse = MagicMock()
    fake_langfuse.create_trace.return_value = fake_trace
    fake_collector = MagicMock()
    fake_collector.record_request = AsyncMock()

    async with trace_task(
        "sentiment_batch",
        langfuse=fake_langfuse,
        collector=fake_collector,
    ) as handle:
        await handle.record_llm(
            model="gpt-4o-mini",
            provider="openai",
            tier="cheap",
            latency_ms=450,
            prompt_tokens=300,
            completion_tokens=40,
            cost_usd=0.0012,
        )
    fake_collector.record_request.assert_awaited_once()
