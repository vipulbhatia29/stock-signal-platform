"""Batch writers for Agent layer observability events (1b PR5).

Three persist functions for intent logs, reasoning logs, and provider
health snapshots. All writers set ``_in_obs_write`` ContextVar guard.
"""

from __future__ import annotations

import logging

from backend.database import async_session_factory
from backend.observability.instrumentation.db import _in_obs_write
from backend.observability.models.agent_intent_log import AgentIntentLog
from backend.observability.models.agent_reasoning_log import AgentReasoningLog
from backend.observability.models.provider_health_snapshot import ProviderHealthSnapshot
from backend.observability.schema.agent_events import (
    AgentIntentEvent,
    AgentReasoningEvent,
    ProviderHealthSnapshotEvent,
)

logger = logging.getLogger(__name__)


async def persist_agent_intents(events: list[AgentIntentEvent]) -> None:
    """Persist intent classification events to observability.agent_intent_log.

    Args:
        events: List of AgentIntentEvent instances. No-op for empty list.
    """
    if not events:
        return

    async with async_session_factory() as session:
        for event in events:
            session.add(
                AgentIntentLog(
                    ts=event.ts,
                    trace_id=str(event.trace_id),
                    span_id=str(event.span_id),
                    user_id=str(event.user_id) if event.user_id else None,
                    session_id=str(event.session_id) if event.session_id else None,
                    query_id=str(event.query_id) if event.query_id else None,
                    intent=event.intent,
                    confidence=event.confidence,
                    out_of_scope=event.out_of_scope,
                    decline_reason=event.decline_reason,
                    query_text_hash=event.query_text_hash,
                    env=event.env,
                    git_sha=event.git_sha,
                )
            )
        token = _in_obs_write.set(True)
        try:
            await session.commit()
        finally:
            _in_obs_write.reset(token)
    logger.debug("Persisted %d agent_intent_log rows", len(events))


async def persist_agent_reasoning(events: list[AgentReasoningEvent]) -> None:
    """Persist reasoning events to observability.agent_reasoning_log.

    Args:
        events: List of AgentReasoningEvent instances. No-op for empty list.
    """
    if not events:
        return

    async with async_session_factory() as session:
        for event in events:
            session.add(
                AgentReasoningLog(
                    ts=event.ts,
                    trace_id=str(event.trace_id),
                    span_id=str(event.span_id),
                    user_id=str(event.user_id) if event.user_id else None,
                    session_id=str(event.session_id) if event.session_id else None,
                    query_id=str(event.query_id) if event.query_id else None,
                    loop_step=event.loop_step,
                    reasoning_type=event.reasoning_type.value,
                    content_summary=event.content_summary,
                    tool_calls_proposed=event.tool_calls_proposed,
                    termination_reason=(
                        event.termination_reason.value if event.termination_reason else None
                    ),
                    env=event.env,
                    git_sha=event.git_sha,
                )
            )
        token = _in_obs_write.set(True)
        try:
            await session.commit()
        finally:
            _in_obs_write.reset(token)
    logger.debug("Persisted %d agent_reasoning_log rows", len(events))


async def persist_provider_health_snapshots(
    events: list[ProviderHealthSnapshotEvent],
) -> None:
    """Persist provider health snapshots to observability.provider_health_snapshot.

    Args:
        events: List of ProviderHealthSnapshotEvent instances. No-op for empty list.
    """
    if not events:
        return

    async with async_session_factory() as session:
        for event in events:
            session.add(
                ProviderHealthSnapshot(
                    ts=event.ts,
                    trace_id=str(event.trace_id),
                    span_id=str(event.span_id),
                    provider=event.provider,
                    model=event.model,
                    is_exhausted=event.is_exhausted,
                    exhausted_until=event.exhausted_until,
                    consecutive_failures=event.consecutive_failures,
                    last_failure_at=event.last_failure_at,
                    last_success_at=event.last_success_at,
                    requests_last_5m=event.requests_last_5m,
                    errors_last_5m=event.errors_last_5m,
                    avg_latency_ms_last_5m=event.avg_latency_ms_last_5m,
                    env=event.env,
                    git_sha=event.git_sha,
                )
            )
        token = _in_obs_write.set(True)
        try:
            await session.commit()
        finally:
            _in_obs_write.reset(token)
    logger.debug("Persisted %d provider_health_snapshot rows", len(events))
