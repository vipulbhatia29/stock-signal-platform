"""Task-level tracing helper for non-agent Celery code paths.

Wraps Langfuse trace creation + ObservabilityCollector recording so
nightly jobs (sentiment scoring, Prophet training, news ingestion,
convergence, backtest) get the same visibility agents get today.

Singleton wiring
----------------
The ``langfuse_service`` and ``observability_collector`` module-level
singletons must be populated before ``trace_task`` is called.

* **FastAPI**: The ``lifespan`` context manager in ``backend/main.py``
  calls :func:`set_langfuse_service` and :func:`set_observability_collector`
  on startup and clears them on shutdown. No manual setup needed.

* **Celery workers**: The ``worker_process_init`` signal handler in the
  Celery app (Spec D) must call both setters. This wiring is deferred to
  Spec D. Until then, :func:`trace_task` raises :exc:`RuntimeError` with
  a clear message rather than silently producing no-op traces.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from backend.observability.collector import ObservabilityCollector
from backend.observability.langfuse import LangfuseService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stable sentinel UUIDs for non-agent task traces.
#
# Using the trace_id as both session_id and user_id (the previous approach)
# would pollute Langfuse's user/session analytics — every task run looks like
# a unique user and session, making those dashboards meaningless for real users.
# These all-zeros sentinels flag non-agent traces as "system" rather than
# attributing them to any real user or interactive session.
# ---------------------------------------------------------------------------
SYSTEM_SESSION_ID = uuid.UUID("00000000-0000-0000-0000-000000000000")
SYSTEM_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


class TaskTraceHandle:
    """Handle yielded by :func:`trace_task` — exposes metadata and LLM recording."""

    def __init__(
        self,
        *,
        name: str,
        trace_id: uuid.UUID,
        trace: Any | None,
        langfuse: LangfuseService,
        collector: ObservabilityCollector,
    ) -> None:
        """Initialise the handle.

        Args:
            name: Human-readable task name.
            trace_id: UUID of the Langfuse trace.
            trace: The Langfuse trace object (may be None when disabled).
            langfuse: The app-level LangfuseService.
            collector: The app-level ObservabilityCollector.
        """
        self.name = name
        self.trace_id = trace_id
        self._trace = trace
        self._langfuse = langfuse
        self._collector = collector
        self._metadata: dict[str, Any] = {}
        self._status: str = "completed"
        self._error: str | None = None
        self._duration_ms: int = 0

    def add_metadata(self, **kwargs: Any) -> None:
        """Attach metadata to the trace (flushed on exit).

        Args:
            **kwargs: Key/value pairs to merge into the final trace metadata.
        """
        self._metadata.update(kwargs)

    async def record_llm(
        self,
        *,
        model: str,
        provider: str,
        tier: str,
        latency_ms: int,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: float | None = None,
    ) -> None:
        """Record an LLM call made inside this task.

        Delegates to :meth:`ObservabilityCollector.record_request` with the
        current trace id so the DB row joins cleanly to agent observability.

        Args:
            model: Model identifier (e.g. "gpt-4o-mini").
            provider: Provider name (e.g. "openai").
            tier: Cost tier (e.g. "cheap", "standard").
            latency_ms: Request latency in milliseconds.
            prompt_tokens: Number of prompt tokens consumed.
            completion_tokens: Number of completion tokens generated.
            cost_usd: Estimated cost in USD, or None if unknown.
        """
        await self._collector.record_request(
            model=model,
            provider=provider,
            tier=tier,
            latency_ms=latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost_usd,
            status="completed",
            langfuse_trace_id=self.trace_id,
        )

    async def _finalize(self) -> None:
        """End the trace with final metadata (fire-and-forget)."""
        if self._trace is None:
            return
        try:
            self._trace.update(
                metadata={
                    "task": self.name,
                    "status": self._status,
                    "error": self._error,
                    "duration_ms": self._duration_ms,
                    **self._metadata,
                }
            )
        except Exception:
            logger.warning("trace_task finalize failed for %s", self.name, exc_info=True)


@asynccontextmanager
async def trace_task(
    name: str,
    *,
    langfuse: LangfuseService,
    collector: ObservabilityCollector,
    metadata: dict[str, Any] | None = None,
) -> AsyncIterator[TaskTraceHandle]:
    """Trace a non-agent task block in Langfuse + the DB collector.

    Usage::

        async with trace_task(
            "nightly_sentiment_scoring",
            langfuse=langfuse_service,
            collector=observability_collector,
            metadata={"ticker_count": 500},
        ) as handle:
            await do_work()
            handle.add_metadata(articles_scored=1234)
            await handle.record_llm(
                model="gpt-4o-mini",
                provider="openai",
                tier="cheap",
                latency_ms=450,
                prompt_tokens=300,
                completion_tokens=40,
                cost_usd=0.0012,
            )

    On exit, the trace is ended; on exception, status is set to "error"
    and the exception re-raises.

    Args:
        name: Human-readable task name (e.g. "nightly_sentiment_scoring").
        langfuse: The app-level LangfuseService (no-op safe when disabled).
        collector: The app-level ObservabilityCollector.
        metadata: Optional initial metadata dict.

    Yields:
        TaskTraceHandle — call add_metadata / record_llm inside the block.
    """
    if langfuse is None or collector is None:
        raise RuntimeError(
            "task_tracer not initialised — call set_langfuse_service() and "
            "set_observability_collector() in FastAPI lifespan or Celery "
            "worker_process_init before using trace_task."
        )
    trace_id = uuid.uuid4()
    # Non-agent traces use stable sentinel UUIDs for session_id and user_id
    # so Langfuse's user/session analytics are not polluted with task run IDs.
    # See module-level SYSTEM_SESSION_ID / SYSTEM_USER_ID for rationale.
    trace = langfuse.create_trace(
        trace_id=trace_id,
        session_id=SYSTEM_SESSION_ID,
        user_id=SYSTEM_USER_ID,
        metadata={"task": name, **(metadata or {})},
    )
    handle = TaskTraceHandle(
        name=name,
        trace_id=trace_id,
        trace=trace,
        langfuse=langfuse,
        collector=collector,
    )
    started_at = time.perf_counter()
    try:
        yield handle
    except Exception as exc:
        handle._status = "error"
        handle._error = type(exc).__name__
        logger.warning("trace_task %s failed: %s", name, type(exc).__name__)
        raise
    finally:
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        handle._duration_ms = duration_ms
        await handle._finalize()


# ---------------------------------------------------------------------------
# Module-level singletons — set from FastAPI lifespan (main.py) so callers can
# `from backend.services.observability.task_tracer import langfuse_service`
# and tests can patch `backend.services.observability.task_tracer.langfuse_service`.
# ---------------------------------------------------------------------------

langfuse_service: LangfuseService | None = None
observability_collector: ObservabilityCollector | None = None


def set_langfuse_service(svc: LangfuseService | None) -> None:
    """Publish the app-level LangfuseService from main.py lifespan.

    Args:
        svc: The LangfuseService instance (or None to clear).
    """
    global langfuse_service  # noqa: PLW0603
    langfuse_service = svc


def set_observability_collector(coll: ObservabilityCollector | None) -> None:
    """Publish the app-level ObservabilityCollector from main.py lifespan.

    Args:
        coll: The ObservabilityCollector instance (or None to clear).
    """
    global observability_collector  # noqa: PLW0603
    observability_collector = coll
