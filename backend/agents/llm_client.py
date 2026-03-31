"""LLM Client — provider-agnostic abstraction with fallback chain and retry logic."""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)


class AllProvidersFailedError(Exception):
    """All LLM providers in the fallback chain have failed."""


class MaxRetriesExceeded(Exception):
    """A single provider exceeded its retry limit."""


class AllModelsExhaustedError(Exception):
    """All models within a provider's cascade have been exhausted."""


class RateLimitError(Exception):
    """Provider returned a rate limit error."""

    def __init__(
        self,
        message: str,
        retry_after: float | None = None,
        is_quota_exhausted: bool = False,
    ):
        super().__init__(message)
        self.retry_after = retry_after
        self.is_quota_exhausted = is_quota_exhausted


@dataclass
class RetryPolicy:
    """Retry configuration for LLM provider calls."""

    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 10.0
    backoff_factor: float = 2.0


@dataclass
class ProviderHealth:
    """Health tracking for an LLM provider."""

    provider: str
    is_exhausted: bool = False
    exhausted_until: datetime | None = None
    consecutive_failures: int = 0
    last_failure: datetime | None = None

    def mark_exhausted(self, retry_after: float | None = None) -> None:
        """Mark this provider as exhausted (quota exceeded)."""
        self.is_exhausted = True
        if retry_after:
            self.exhausted_until = datetime.now(timezone.utc) + timedelta(seconds=retry_after)
        logger.warning(
            "provider_exhausted",
            extra={"provider": self.provider, "retry_after": retry_after},
        )

    def is_available(self) -> bool:
        """Check if this provider is available for requests."""
        if not self.is_exhausted:
            return True
        if self.exhausted_until and datetime.now(timezone.utc) >= self.exhausted_until:
            self.is_exhausted = False
            return True
        return False


@dataclass
class LLMResponse:
    """Normalized response from any LLM provider."""

    content: str
    tool_calls: list[dict[str, Any]]
    model: str
    prompt_tokens: int
    completion_tokens: int

    @property
    def has_tool_calls(self) -> bool:
        """Check if the response contains tool calls."""
        return bool(self.tool_calls)

    def usage_dict(self) -> dict[str, Any]:
        """Return usage as a dict for StreamEvent."""
        return {
            "model": self.model,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
        }


class LLMProvider(ABC):
    """Abstract base for LLM providers.

    Subclasses implement chat() for LLM API calls. Observability is provided
    by base class methods — subclasses call self._record_success() after a
    successful API response and self._record_cascade() on failure/skip.

    Attributes:
        collector: ObservabilityCollector instance, injected by main.py lifespan.
        pricing: model_name → (cost_per_1k_input, cost_per_1k_output) dict.
    """

    health: ProviderHealth
    collector: Any = None  # ObservabilityCollector | None — avoid circular import
    pricing: dict[str, tuple[float, float]] | None = None

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider identifier (e.g., 'groq', 'anthropic')."""
        ...

    @abstractmethod
    def get_chat_model(self) -> Any:
        """Return the LangChain chat model instance for LangGraph."""
        ...

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        stream: bool = False,
    ) -> LLMResponse:
        """Send a chat completion request."""
        ...

    def _compute_cost(self, model: str, prompt_tokens: int, completion_tokens: int) -> float | None:
        """Compute cost in USD from token counts and pricing config."""
        if not self.pricing or model not in self.pricing:
            return None
        cost_input, cost_output = self.pricing[model]
        return (prompt_tokens / 1000) * cost_input + (completion_tokens / 1000) * cost_output

    async def _record_success(
        self,
        model: str,
        latency_ms: int,
        prompt_tokens: int,
        completion_tokens: int,
        tier: str = "",
    ) -> None:
        """Record a successful LLM call with cost. Called by subclass after API response."""
        if not self.collector:
            return
        cost = self._compute_cost(model, prompt_tokens, completion_tokens)

        # Read query_id from ContextVar — it IS the Langfuse trace ID
        from backend.request_context import current_query_id

        qid = current_query_id.get(None)

        await self.collector.record_request(
            model=model,
            provider=self.name,
            tier=tier,
            latency_ms=latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost,
            langfuse_trace_id=qid,
        )

    async def _record_cascade(self, from_model: str, reason: str, tier: str = "") -> None:
        """Record a cascade/failure event. Called by subclass on error or budget skip."""
        if not self.collector:
            return
        await self.collector.record_cascade(
            from_model=from_model,
            reason=reason,
            provider=self.name,
            tier=tier,
        )


class LLMClient:
    """Provider-agnostic LLM client with fallback chain and retry logic."""

    def __init__(
        self,
        providers: list[LLMProvider],
        retry_policy: RetryPolicy | None = None,
        tier_config: dict[str, list[LLMProvider]] | None = None,
        collector: Any = None,  # ObservabilityCollector | None
        langfuse_service: Any | None = None,
    ) -> None:
        self._providers = providers
        self._retry_policy = retry_policy or RetryPolicy()
        self._tier_config = tier_config
        self._collector = collector
        self._langfuse = langfuse_service

    def get_active_chat_model(self) -> Any:
        """Return the LangChain chat model from the first healthy provider."""
        for provider in self._providers:
            if provider.health.is_available():
                return provider.get_chat_model()
        return None

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        stream: bool = False,
        tier: str | None = None,
    ) -> LLMResponse:
        """Call the LLM with fallback chain. Tries each provider in order.

        Args:
            messages: Chat messages.
            tools: Tool schemas for function calling.
            stream: Whether to stream the response.
            tier: Optional tier name (e.g., "planner", "synthesizer").
                If provided and tier_config exists, uses that tier's providers.
        """
        providers = self._providers
        if tier and self._tier_config and tier in self._tier_config:
            providers = self._tier_config[tier]

        errors: list[tuple[str, Exception]] = []

        for provider in providers:
            if not provider.health.is_available():
                logger.info(
                    "provider_skipped",
                    extra={"provider": provider.name, "reason": "exhausted"},
                )
                continue

            try:
                response = await self._call_with_retry(provider, messages, tools, stream)
                provider.health.consecutive_failures = 0

                # Langfuse: record generation (fire-and-forget)
                if self._langfuse and self._langfuse.enabled:
                    try:
                        from backend.request_context import current_query_id

                        qid = current_query_id.get(None)
                        if qid:
                            trace = self._langfuse.get_trace_ref(qid)
                            cost = provider._compute_cost(
                                response.model,
                                response.prompt_tokens or 0,
                                response.completion_tokens or 0,
                            )
                            self._langfuse.record_generation(
                                trace=trace,
                                name=f"llm.{provider.name}.{response.model}",
                                model=response.model,
                                input_messages=messages[-1:],
                                output=response.content or "",
                                prompt_tokens=response.prompt_tokens or 0,
                                completion_tokens=response.completion_tokens or 0,
                                cost_usd=cost,
                                metadata={
                                    "type": "llm",
                                    "tier": tier or "",
                                    "provider": provider.name,
                                },
                            )
                    except Exception:
                        logger.debug("langfuse_generation_failed")

                return response
            except Exception as e:
                provider.health.consecutive_failures += 1
                provider.health.last_failure = datetime.now(timezone.utc)
                errors.append((provider.name, e))
                if self._collector:
                    await self._collector.record_cascade(
                        from_model=provider.name,
                        reason=type(e).__name__,
                        provider=provider.name,
                        tier=tier or "",
                    )
                logger.warning(
                    "provider_failed",
                    extra={
                        "provider": provider.name,
                        "error": str(e),
                        "consecutive_failures": provider.health.consecutive_failures,
                    },
                )
                continue

        raise AllProvidersFailedError(
            f"All {len(providers)} providers failed: "
            + ", ".join(f"{name}: {err}" for name, err in errors)
        )

    async def _call_with_retry(
        self,
        provider: LLMProvider,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        stream: bool,
    ) -> LLMResponse:
        """Call a single provider with retry logic per spec §4.4."""
        policy = self._retry_policy

        for attempt in range(policy.max_retries):
            try:
                return await asyncio.wait_for(
                    provider.chat(messages, tools, stream),
                    timeout=30.0,
                )
            except RateLimitError as e:
                if e.is_quota_exhausted:
                    provider.health.mark_exhausted(e.retry_after)
                    raise
                if e.retry_after and e.retry_after <= 5:
                    await asyncio.sleep(e.retry_after)
                    continue
                raise
            except asyncio.TimeoutError:
                raise
            except (ConnectionError, OSError):
                delay = min(
                    policy.base_delay * (policy.backoff_factor**attempt),
                    policy.max_delay,
                )
                logger.warning(
                    "llm_retry",
                    extra={
                        "provider": provider.name,
                        "attempt": attempt,
                        "delay": delay,
                    },
                )
                if attempt < policy.max_retries - 1:
                    await asyncio.sleep(delay)
            except Exception:
                if attempt < policy.max_retries - 1:
                    continue
                raise

        raise MaxRetriesExceeded(f"Provider {provider.name} exceeded {policy.max_retries} retries")
