"""LLM Client — provider-agnostic abstraction with fallback chain and retry logic."""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class AllProvidersFailedError(Exception):
    """All LLM providers in the fallback chain have failed."""


class MaxRetriesExceeded(Exception):
    """A single provider exceeded its retry limit."""


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
            self.exhausted_until = datetime.now(timezone.utc).replace(second=0, microsecond=0)
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
    """Abstract base for LLM providers."""

    health: ProviderHealth

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


class LLMClient:
    """Provider-agnostic LLM client with fallback chain and retry logic."""

    def __init__(
        self,
        providers: list[LLMProvider],
        retry_policy: RetryPolicy | None = None,
        tier_config: dict[str, list[LLMProvider]] | None = None,
    ) -> None:
        self._providers = providers
        self._retry_policy = retry_policy or RetryPolicy()
        self._tier_config = tier_config

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
                return response
            except Exception as e:
                provider.health.consecutive_failures += 1
                provider.health.last_failure = datetime.now(timezone.utc)
                errors.append((provider.name, e))
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
