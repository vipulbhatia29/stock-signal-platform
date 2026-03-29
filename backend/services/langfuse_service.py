"""Langfuse tracing wrapper — fire-and-forget, feature-flagged.

All methods are safe to call when Langfuse is disabled (no-op).
Errors in Langfuse calls are logged but never propagated.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

logger = logging.getLogger(__name__)


class LangfuseService:
    """Thin wrapper around the Langfuse SDK.

    Feature-flagged: if secret_key is empty, all methods are no-ops.
    All SDK calls are wrapped in try-except to ensure fire-and-forget.
    """

    def __init__(self, secret_key: str, public_key: str, base_url: str) -> None:
        self._client = None
        self.enabled = False
        if secret_key:
            try:
                from langfuse import Langfuse

                self._client = Langfuse(
                    secret_key=secret_key,
                    public_key=public_key,
                    host=base_url,
                )
                self.enabled = True
                logger.info("Langfuse client initialized at %s", base_url)
            except Exception:
                logger.warning("Langfuse initialization failed — tracing disabled", exc_info=True)

    def create_trace(
        self,
        trace_id: uuid.UUID,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        metadata: dict[str, Any] | None = None,
    ) -> Any | None:
        """Create a Langfuse trace for a user query. Returns trace object or None."""
        if not self._client:
            return None
        try:
            return self._client.trace(
                id=str(trace_id),
                session_id=str(session_id),
                user_id=str(user_id),
                metadata=metadata or {},
            )
        except Exception:
            logger.warning("Langfuse trace creation failed", exc_info=True)
            return None

    def get_trace_ref(self, trace_id: uuid.UUID) -> Any | None:
        """Get a reference to an existing trace by ID. Used by LLMClient."""
        if not self._client:
            return None
        try:
            return self._client.trace(id=str(trace_id))
        except Exception:
            logger.warning("Langfuse trace ref lookup failed", exc_info=True)
            return None

    def record_generation(
        self,
        trace: Any | None,
        name: str,
        model: str,
        input_messages: list[dict],
        output: str,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Any | None:
        """Record an LLM generation span on an existing trace."""
        if not trace:
            return None
        try:
            return trace.generation(
                name=name,
                model=model,
                input=input_messages,
                output=output,
                usage={
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                },
                metadata=metadata or {},
                **({"cost": cost_usd} if cost_usd is not None else {}),
            )
        except Exception:
            logger.warning("Langfuse generation recording failed", exc_info=True)
            return None

    def create_span(
        self,
        trace: Any | None,
        name: str,
        metadata: dict[str, Any] | None = None,
    ) -> Any | None:
        """Create a span (tool execution, ReAct iteration) on an existing trace."""
        if not trace:
            return None
        try:
            return trace.span(name=name, metadata=metadata or {})
        except Exception:
            logger.warning("Langfuse span creation failed", exc_info=True)
            return None

    def end_span(self, span: Any | None) -> None:
        """End a span (sets end_time)."""
        if not span:
            return
        try:
            span.end()
        except Exception:
            logger.warning("Langfuse span end failed", exc_info=True)

    def flush(self) -> None:
        """Flush pending events to Langfuse server."""
        if not self._client:
            return
        try:
            self._client.flush()
        except Exception:
            logger.warning("Langfuse flush failed", exc_info=True)

    def shutdown(self) -> None:
        """Flush and close the Langfuse client."""
        if not self._client:
            return
        try:
            self._client.flush()
            self._client.shutdown()
        except Exception:
            logger.warning("Langfuse shutdown failed", exc_info=True)
