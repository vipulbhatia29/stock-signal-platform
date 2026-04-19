"""Agent layer observability instrumentation — intent, reasoning, provider health.

Emission helpers for intent classification, ReAct loop reasoning, and
provider health snapshots. All use emit_sync() for thread safety.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timezone

from backend.config import settings

logger = logging.getLogger(__name__)


def emit_intent_log(
    *,
    intent: str,
    confidence: float,
    out_of_scope: bool,
    query_text_hash: str,
    decline_reason: str | None = None,
) -> None:
    """Emit an AGENT_INTENT event after intent classification.

    Args:
        intent: Classified intent string (e.g. "stock", "portfolio").
        confidence: Classification confidence score (0-1).
        out_of_scope: Whether the query was declined.
        query_text_hash: SHA256 hash of the query text.
        decline_reason: Why the query was declined (if out_of_scope).
    """
    try:
        from backend.observability.bootstrap import _maybe_get_obs_client
        from backend.observability.context import (
            current_query_id,
            current_session_id,
            current_span_id,
            current_trace_id,
            current_user_id,
        )
        from backend.observability.schema.agent_events import AgentIntentEvent

        client = _maybe_get_obs_client()
        if client is None:
            return

        event = AgentIntentEvent(
            trace_id=current_trace_id() or uuid.uuid4(),
            span_id=current_span_id() or uuid.uuid4(),
            parent_span_id=None,
            ts=datetime.now(timezone.utc),
            env=getattr(settings, "APP_ENV", "dev"),
            git_sha=getattr(settings, "GIT_SHA", None),
            user_id=current_user_id.get(),
            session_id=current_session_id.get(),
            query_id=current_query_id.get(),
            intent=intent,
            confidence=confidence,
            out_of_scope=out_of_scope,
            decline_reason=decline_reason,
            query_text_hash=query_text_hash,
        )
        client.emit_sync(event)
    except Exception:  # noqa: BLE001 — instrumentation must not break classification
        logger.debug("obs.agent_intent.emit_failed", exc_info=True)


def emit_reasoning_log(
    *,
    loop_step: int,
    reasoning_type: str,
    content_summary: str,
    tool_calls_proposed: dict | None = None,
    termination_reason: str | None = None,
) -> None:
    """Emit an AGENT_REASONING event per ReAct loop iteration.

    Args:
        loop_step: Iteration index (0-based).
        reasoning_type: Type of reasoning (plan, reflect, etc.).
        content_summary: Truncated LLM response content (max 500 chars).
        tool_calls_proposed: Tool names proposed in this iteration.
        termination_reason: Reason for loop exit (only on final step).
    """
    try:
        from backend.observability.bootstrap import _maybe_get_obs_client
        from backend.observability.context import (
            current_query_id,
            current_session_id,
            current_span_id,
            current_trace_id,
            current_user_id,
        )
        from backend.observability.schema.agent_events import (
            AgentReasoningEvent,
            ReasoningType,
            TerminationReason,
        )

        client = _maybe_get_obs_client()
        if client is None:
            return

        event = AgentReasoningEvent(
            trace_id=current_trace_id() or uuid.uuid4(),
            span_id=current_span_id() or uuid.uuid4(),
            parent_span_id=None,
            ts=datetime.now(timezone.utc),
            env=getattr(settings, "APP_ENV", "dev"),
            git_sha=getattr(settings, "GIT_SHA", None),
            user_id=current_user_id.get(),
            session_id=current_session_id.get(),
            query_id=current_query_id.get(),
            loop_step=loop_step,
            reasoning_type=ReasoningType(reasoning_type),
            content_summary=content_summary[:500],
            tool_calls_proposed=tool_calls_proposed,
            termination_reason=(
                TerminationReason(termination_reason) if termination_reason else None
            ),
        )
        client.emit_sync(event)
    except Exception:  # noqa: BLE001 — instrumentation must not break the loop
        logger.debug("obs.agent_reasoning.emit_failed", exc_info=True)


def emit_provider_health_snapshot(
    *,
    provider: str,
    model: str | None = None,
    is_exhausted: bool = False,
    exhausted_until: datetime | None = None,
    consecutive_failures: int = 0,
    last_failure_at: datetime | None = None,
) -> None:
    """Emit a PROVIDER_HEALTH_SNAPSHOT event.

    Args:
        provider: Provider name (e.g. "openai").
        model: Model name if available.
        is_exhausted: Whether the provider is quota-exhausted.
        exhausted_until: When the provider will recover.
        consecutive_failures: Number of consecutive failures.
        last_failure_at: Timestamp of last failure.
    """
    try:
        from backend.observability.bootstrap import _maybe_get_obs_client
        from backend.observability.schema.agent_events import (
            ProviderHealthSnapshotEvent,
        )

        client = _maybe_get_obs_client()
        if client is None:
            return

        event = ProviderHealthSnapshotEvent(
            trace_id=uuid.uuid4(),
            span_id=uuid.uuid4(),
            parent_span_id=None,
            ts=datetime.now(timezone.utc),
            env=getattr(settings, "APP_ENV", "dev"),
            git_sha=getattr(settings, "GIT_SHA", None),
            user_id=None,
            session_id=None,
            query_id=None,
            provider=provider,
            model=model,
            is_exhausted=is_exhausted,
            exhausted_until=exhausted_until,
            consecutive_failures=consecutive_failures,
            last_failure_at=last_failure_at,
        )
        client.emit_sync(event)
    except Exception:  # noqa: BLE001 — instrumentation must not crash
        logger.debug("obs.provider_health.emit_failed", exc_info=True)


def hash_query_text(query: str) -> str:
    """Hash query text for privacy-safe logging.

    Args:
        query: Raw query text.

    Returns:
        SHA256 hex digest of the query.
    """
    return hashlib.sha256(query.encode()).hexdigest()
