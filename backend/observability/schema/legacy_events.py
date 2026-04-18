"""PR5 strangler-fig event subclasses for legacy emitters.

Each class inherits from ObsEventBase (envelope) and _LegacyStranglerFigMixin
(dual-write decision snapshot). The mixin captures `wrote_via_legacy` at emit
time — a snapshot of OBS_LEGACY_DIRECT_WRITES — so post-hoc analysis can
distinguish events that went through the legacy path from SDK-only events.

Spec §2.7: flip OBS_LEGACY_DIRECT_WRITES to False after 2 weeks of green
production to cut over fully to SDK emission.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from backend.observability.schema.v1 import EventType, ObsEventBase


class _LegacyStranglerFigMixin(BaseModel):
    """Mixin for PR5 strangler-fig events — captures dual-write decision at emit time."""

    wrote_via_legacy: bool  # snapshot of OBS_LEGACY_DIRECT_WRITES at emit, NOT read later


class LLMCallEvent(ObsEventBase, _LegacyStranglerFigMixin):
    """Observability event for a single LLM call (agent or batch sentiment scoring).

    Args:
        model: Model name (e.g. ``gpt-4o-mini``, ``claude-3-haiku``).
        provider: Provider name (e.g. ``openai``, ``anthropic``, ``groq``).
        tier: Routing tier (e.g. ``fast``, ``balanced``, ``precise``).
        latency_ms: Wall-clock latency in ms. ``None`` for cascade (error-only) events.
        prompt_tokens: Input token count. ``None`` when unavailable.
        completion_tokens: Output token count. ``None`` when unavailable.
        cost_usd: Estimated cost in USD. ``None`` when unavailable.
        loop_step: ReAct loop step index. ``None`` for non-agent calls.
        status: Call outcome. Defaults to ``"completed"``.
        langfuse_trace_id: Langfuse trace ID for cross-system correlation.
        error: Safe error message for cascade/failure events. No ``str(exc)`` — callers
            must sanitise before passing. ``None`` for successful calls.
    """

    event_type: Literal[EventType.LLM_CALL] = EventType.LLM_CALL
    model: str
    provider: str
    tier: str
    latency_ms: int | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cost_usd: float | None = None
    loop_step: int | None = None
    status: str = "completed"
    langfuse_trace_id: UUID | str | None = None
    error: str | None = None  # safe message only — cascade events; NO str(exc)


class ToolExecutionEvent(ObsEventBase, _LegacyStranglerFigMixin):
    """Observability event for a single agent tool execution.

    Args:
        tool_name: Name of the tool (e.g. ``get_ticker_price``).
        latency_ms: Wall-clock latency in ms.
        status: Execution outcome (e.g. ``"success"``, ``"error"``).
        result_size_bytes: Serialised result size. ``None`` on error paths.
        error: Safe error message. No ``str(exc)`` — callers must sanitise.
        cache_hit: Whether the result was served from cache. Defaults to ``False``.
        loop_step: ReAct loop step index. ``None`` for non-loop invocations.
    """

    event_type: Literal[EventType.TOOL_EXECUTION] = EventType.TOOL_EXECUTION
    tool_name: str
    latency_ms: int
    status: str
    result_size_bytes: int | None = None
    error: str | None = None  # safe message only — NO str(exc)
    cache_hit: bool = False
    loop_step: int | None = None


class LoginAttemptEvent(ObsEventBase, _LegacyStranglerFigMixin):
    """Observability event for an authentication attempt.

    Args:
        email: Email address used in the attempt.
        success: Whether authentication succeeded.
        ip_address: Client IP address.
        user_agent: HTTP User-Agent header value.
        failure_reason: Human-readable reason for failure. ``None`` on success.
        method: Auth method used. Plain ``str`` to accommodate ``"password"``,
            ``"google"``, ``"github"``, etc. without forcing exhaustive Literal.
    """

    event_type: Literal[EventType.LOGIN_ATTEMPT] = EventType.LOGIN_ATTEMPT
    email: str
    success: bool
    ip_address: str
    user_agent: str
    failure_reason: str | None = None
    method: str = "password"


class DqFindingEvent(ObsEventBase, _LegacyStranglerFigMixin):
    """Observability event for a data-quality check finding.

    Args:
        check_name: Identifier for the DQ check (e.g. ``"null_price_check"``).
        severity: Finding severity — one of ``info``, ``warning``, ``error``, ``critical``,
            ``high``, ``medium``.
        ticker: Ticker symbol if the finding is ticker-scoped. ``None`` for global checks.
        message: Human-readable finding description.
        metadata: Optional structured metadata dict (e.g. affected row count).
    """

    event_type: Literal[EventType.DQ_FINDING] = EventType.DQ_FINDING
    check_name: str
    severity: Literal["info", "warning", "error", "critical", "high", "medium"]
    ticker: str | None = None
    message: str
    metadata: dict | None = None


class PipelineLifecycleEvent(ObsEventBase, _LegacyStranglerFigMixin):
    """Observability event for a pipeline run state transition.

    Args:
        pipeline_name: Pipeline identifier (e.g. ``"nightly_signal"``).
        transition: State transition — one of ``started``, ``success``, ``failed``,
            ``no_op``, ``partial``. Note: uses ``"success"`` (not ``"succeeded"``)
            to match what ``complete_run`` returns.
        run_id: UUID of the pipeline run (PipelineRunner.id).
        trigger: What triggered the run (e.g. ``"celery_beat"``, ``"api"``, ``"manual"``).
        celery_task_id: Celery task ID for cross-system correlation. ``None`` for
            non-Celery triggers.
        duration_s: Wall-clock duration in seconds. ``None`` for ``started`` events.
        tickers_total: Total tickers processed. ``None`` when not applicable.
        tickers_succeeded: Tickers that succeeded. ``None`` when not applicable.
        tickers_failed: Tickers that failed. ``None`` when not applicable.
    """

    event_type: Literal[EventType.PIPELINE_LIFECYCLE] = EventType.PIPELINE_LIFECYCLE
    pipeline_name: str
    transition: Literal["started", "success", "failed", "no_op", "partial"]
    run_id: UUID
    trigger: str
    celery_task_id: str | None = None
    duration_s: float | None = None
    tickers_total: int | None = None
    tickers_succeeded: int | None = None
    tickers_failed: int | None = None
