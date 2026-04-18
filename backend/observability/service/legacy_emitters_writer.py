"""Writers for legacy-emitter events routed through the SDK.

Each persist_* function maps an SDK event back to the original table,
producing the SAME row the legacy direct-write path would have created.

Dedup invariant: if event.wrote_via_legacy is True, the row already exists
(legacy path wrote it at emit time). We skip to avoid duplicates. When False,
we insert — this is the SDK-only path after the strangler-fig flag is flipped.
"""

from __future__ import annotations

import logging

from backend.database import async_session_factory
from backend.observability.schema.legacy_events import (
    DqFindingEvent,
    LLMCallEvent,
    LoginAttemptEvent,
    PipelineLifecycleEvent,
    ToolExecutionEvent,
)

logger = logging.getLogger(__name__)


async def persist_llm_calls(events: list[LLMCallEvent]) -> None:
    """Persist LLM call events to llm_call_log table.

    Skips events where wrote_via_legacy=True (legacy path already wrote the row).
    Only inserts events on the SDK-only path (wrote_via_legacy=False).

    Args:
        events: List of LLMCallEvent instances to persist.
    """
    to_write = [e for e in events if not e.wrote_via_legacy]
    if not to_write:
        return

    from backend.models.logs import LLMCallLog

    try:
        async with async_session_factory() as session:
            for event in to_write:
                session.add(
                    LLMCallLog(
                        session_id=event.session_id,
                        query_id=event.query_id,
                        provider=event.provider,
                        model=event.model,
                        tier=event.tier,
                        latency_ms=event.latency_ms,
                        prompt_tokens=event.prompt_tokens,
                        completion_tokens=event.completion_tokens,
                        cost_usd=event.cost_usd,
                        loop_step=event.loop_step,
                        status=event.status,
                        langfuse_trace_id=event.langfuse_trace_id,
                        error=event.error,
                        agent_type=event.agent_type,
                        agent_instance_id=event.agent_instance_id,
                    )
                )
            await session.commit()
    except Exception:  # noqa: BLE001
        logger.warning("obs.writer.llm_call.failed", exc_info=True)


async def persist_tool_executions(events: list[ToolExecutionEvent]) -> None:
    """Persist tool execution events to tool_execution_log table.

    Skips events where wrote_via_legacy=True (legacy path already wrote the row).
    Only inserts events on the SDK-only path (wrote_via_legacy=False).

    Args:
        events: List of ToolExecutionEvent instances to persist.
    """
    to_write = [e for e in events if not e.wrote_via_legacy]
    if not to_write:
        return

    from backend.models.logs import ToolExecutionLog
    from backend.utils.sanitize import sanitize_summary

    try:
        async with async_session_factory() as session:
            for event in to_write:
                session.add(
                    ToolExecutionLog(
                        session_id=event.session_id,
                        query_id=event.query_id,
                        tool_name=event.tool_name,
                        latency_ms=event.latency_ms,
                        status=event.status,
                        result_size_bytes=event.result_size_bytes,
                        params=event.params,
                        error=event.error,
                        cache_hit=event.cache_hit,
                        loop_step=event.loop_step,
                        agent_type=event.agent_type,
                        agent_instance_id=event.agent_instance_id,
                        input_summary=sanitize_summary(event.params or {}),
                        output_summary=sanitize_summary(event.result or ""),
                    )
                )
            await session.commit()
    except Exception:  # noqa: BLE001
        logger.warning("obs.writer.tool_execution.failed", exc_info=True)


async def persist_login_attempts(events: list[LoginAttemptEvent]) -> None:
    """Persist login attempt events to login_attempts table.

    Skips events where wrote_via_legacy=True (legacy path already wrote the row).
    Only inserts events on the SDK-only path (wrote_via_legacy=False).

    Args:
        events: List of LoginAttemptEvent instances to persist.
    """
    to_write = [e for e in events if not e.wrote_via_legacy]
    if not to_write:
        return

    from backend.models.login_attempt import LoginAttempt

    try:
        async with async_session_factory() as session:
            for event in to_write:
                session.add(
                    LoginAttempt(
                        timestamp=event.ts,
                        user_id=event.user_id,
                        email=event.email,
                        ip_address=event.ip_address,
                        user_agent=event.user_agent,
                        success=event.success,
                        failure_reason=event.failure_reason,
                        method=event.method,
                    )
                )
            await session.commit()
    except Exception:  # noqa: BLE001
        logger.warning("obs.writer.login_attempt.failed", exc_info=True)


async def persist_dq_findings(events: list[DqFindingEvent]) -> None:
    """Persist DQ finding events to dq_check_history table.

    Skips events where wrote_via_legacy=True (legacy path already wrote the row).
    Only inserts events on the SDK-only path (wrote_via_legacy=False).

    Args:
        events: List of DqFindingEvent instances to persist.
    """
    to_write = [e for e in events if not e.wrote_via_legacy]
    if not to_write:
        return

    from backend.models.dq_check_history import DqCheckHistory

    try:
        async with async_session_factory() as session:
            for event in to_write:
                session.add(
                    DqCheckHistory(
                        check_name=event.check_name,
                        severity=event.severity,
                        ticker=event.ticker,
                        message=event.message,
                        metadata_=event.metadata,
                    )
                )
            await session.commit()
    except Exception:  # noqa: BLE001
        logger.warning("obs.writer.dq_finding.failed", exc_info=True)


async def persist_pipeline_lifecycle(events: list[PipelineLifecycleEvent]) -> None:
    """Pipeline lifecycle events are INFORMATIONAL ONLY — they do NOT write to pipeline_runs.

    The pipeline_runs table is already maintained by PipelineRunner.start_run/complete_run
    and the tracked_task exception handler. Lifecycle events exist for downstream consumers
    (dashboards, audit trails) and will be written to an observability.pipeline_events table
    in sub-epic 1b. For now, we log them at DEBUG level as a forward-compatibility stub.

    Args:
        events: List of PipelineLifecycleEvent instances (logged only, no DB write).
    """
    for event in events:
        logger.debug(
            "obs.pipeline_lifecycle",
            extra={
                "pipeline_name": event.pipeline_name,
                "transition": event.transition,
                "run_id": str(event.run_id),
                "duration_s": event.duration_s,
            },
        )
