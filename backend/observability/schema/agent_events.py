"""Pydantic event schemas for Agent layer observability (1b PR5).

Three event types:
- AgentIntentEvent — intent classification result
- AgentReasoningEvent — per-iteration reasoning snapshot
- ProviderHealthSnapshotEvent — periodic LLM provider health state
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from backend.observability.schema.v1 import ObsEventBase


class ReasoningType(str, Enum):
    """Type of reasoning step in the ReAct loop."""

    PLAN = "plan"
    REFLECT = "reflect"
    SYNTHESIZE = "synthesize"
    CLARIFY = "clarify"
    REFUSE = "refuse"


class TerminationReason(str, Enum):
    """Reason for ReAct loop termination."""

    NORMAL = "normal"
    MAX_ITERATIONS = "max_iterations"
    WALL_CLOCK_TIMEOUT = "wall_clock_timeout"
    ZERO_TOOL_CALLS = "zero_tool_calls"
    EXCEPTION = "exception"


class AgentIntentEvent(ObsEventBase):
    """Event emitted after intent classification.

    Attributes:
        event_type: Always AGENT_INTENT.
        intent: Classified intent (e.g. "stock", "portfolio", "general").
        confidence: Classification confidence score (0-1).
        out_of_scope: Whether the query was declined.
        decline_reason: Why the query was declined (if out_of_scope).
        query_text_hash: SHA256 hash of the query text (privacy-safe).
    """

    event_type: Literal["agent_intent"] = "agent_intent"  # type: ignore[assignment]
    intent: str
    confidence: float
    out_of_scope: bool
    decline_reason: str | None = None
    query_text_hash: str


class AgentReasoningEvent(ObsEventBase):
    """Event emitted per ReAct loop iteration.

    Attributes:
        event_type: Always AGENT_REASONING.
        loop_step: Iteration index (0-based).
        reasoning_type: Type of reasoning (plan, reflect, etc.).
        content_summary: Truncated LLM response content (max 500 chars).
        tool_calls_proposed: Tool names proposed in this iteration.
        termination_reason: Reason for loop exit (only on final step).
    """

    event_type: Literal["agent_reasoning"] = "agent_reasoning"  # type: ignore[assignment]
    loop_step: int
    reasoning_type: ReasoningType
    content_summary: str
    tool_calls_proposed: dict | None = None
    termination_reason: TerminationReason | None = None


class ProviderHealthSnapshotEvent(ObsEventBase):
    """Periodic snapshot of LLM provider health.

    Attributes:
        event_type: Always PROVIDER_HEALTH_SNAPSHOT.
        provider: Provider name (e.g. "openai", "anthropic").
        model: Model name if available.
        is_exhausted: Whether the provider is quota-exhausted.
        exhausted_until: When the provider will recover.
        consecutive_failures: Number of consecutive failures.
        last_failure_at: Timestamp of last failure.
    """

    event_type: Literal["provider_health_snapshot"] = "provider_health_snapshot"  # type: ignore[assignment]
    provider: str
    model: str | None = None
    is_exhausted: bool
    exhausted_until: datetime | None = None
    consecutive_failures: int
    last_failure_at: datetime | None = None
    last_success_at: datetime | None = None
    requests_last_5m: int | None = None
    errors_last_5m: int | None = None
    avg_latency_ms_last_5m: int | None = None
