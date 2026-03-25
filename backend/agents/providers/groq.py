"""Groq LLM provider — multi-model cascade with budget-aware routing."""

from __future__ import annotations

import logging
import time
from typing import Any

from backend.agents.llm_client import (
    AllModelsExhaustedError,
    LLMProvider,
    LLMResponse,
    ProviderHealth,
)
from backend.agents.observability import ObservabilityCollector
from backend.agents.token_budget import TokenBudget

logger = logging.getLogger(__name__)

# Groq error imports — optional, fail gracefully if not installed
try:
    from groq import APIConnectionError as GroqConnectionError
    from groq import APIError as GroqAPIError
    from groq import APIStatusError as GroqStatusError

    _GROQ_ERRORS = (GroqAPIError, GroqStatusError, GroqConnectionError)
except ImportError:
    _GROQ_ERRORS = ()


def _classify_error(exc: Exception) -> str:
    """Classify a Groq error for cascade decision-making.

    Returns:
        One of: rate_limit, context_length, auth, transient, permanent
    """
    msg = str(exc).lower()
    if "rate" in msg or "429" in msg or "too many" in msg:
        return "rate_limit"
    if "context" in msg or "token" in msg or "too long" in msg:
        return "context_length"
    if "auth" in msg or "401" in msg or "api key" in msg:
        return "auth"
    if "timeout" in msg or "connection" in msg or "503" in msg or "502" in msg:
        return "transient"
    return "permanent"


class GroqProvider(LLMProvider):
    """Groq provider with internal multi-model cascade."""

    def __init__(
        self,
        api_key: str,
        models: list[str] | None = None,
        token_budget: TokenBudget | None = None,
        collector: ObservabilityCollector | None = None,
    ) -> None:
        self._api_key = api_key
        self._models = models or ["llama-3.3-70b-versatile"]
        self._token_budget = token_budget
        self._collector = collector
        self.health = ProviderHealth(provider="groq")
        self._chat_models: dict[str, Any] = {}

    @property
    def name(self) -> str:
        """Provider name."""
        return "groq"

    def get_chat_model(self) -> Any:
        """Return LangChain ChatGroq instance for the first model."""
        model_name = self._models[0]
        if model_name not in self._chat_models:
            from langchain_groq import ChatGroq

            self._chat_models[model_name] = ChatGroq(
                api_key=self._api_key,
                model=model_name,
            )
        return self._chat_models[model_name]

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        stream: bool = False,
    ) -> LLMResponse:
        """Cascade through models until one succeeds.

        For each model in priority order:
        1. Check token budget — skip if over threshold
        2. Attempt the API call
        3. On success: record usage and return
        4. On failure: classify error, log, try next model

        Raises:
            AllModelsExhaustedError: All models failed or were over-budget.
        """
        estimated_tokens = TokenBudget.estimate_tokens(messages)
        errors: list[tuple[str, str]] = []

        for model_name in self._models:
            # Budget check
            if self._token_budget:
                if not await self._token_budget.can_afford(model_name, estimated_tokens):
                    logger.info("Skipping %s — over budget", model_name)
                    errors.append((model_name, "over_budget"))
                    if self._collector:
                        await self._collector.record_cascade(
                            from_model=model_name,
                            reason="over_budget",
                            provider=self.name,
                            tier="",
                        )
                    continue

            start = time.monotonic()
            try:
                result = await self._call_model(model_name, messages, tools, stream)
                # Record usage on success
                if self._token_budget:
                    actual = result.prompt_tokens + result.completion_tokens
                    await self._token_budget.record(model_name, actual)
                if self._collector:
                    latency_ms = int((time.monotonic() - start) * 1000)
                    await self._collector.record_request(
                        model=model_name,
                        provider=self.name,
                        tier="",
                        latency_ms=latency_ms,
                        prompt_tokens=result.prompt_tokens,
                        completion_tokens=result.completion_tokens,
                    )
                return result
            except Exception as exc:
                error_type = _classify_error(exc)
                logger.warning(
                    "Groq model %s failed (%s): %s — cascading",
                    model_name,
                    error_type,
                    str(exc)[:200],
                )
                errors.append((model_name, error_type))
                if self._collector:
                    await self._collector.record_cascade(
                        from_model=model_name,
                        reason=error_type,
                        provider=self.name,
                        tier="",
                    )

                # Auth errors affect all models — don't cascade
                if error_type == "auth":
                    break

        raise AllModelsExhaustedError(
            f"All {len(self._models)} Groq models exhausted: "
            + ", ".join(f"{m}({e})" for m, e in errors)
        )

    async def _call_model(
        self,
        model_name: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        stream: bool,
    ) -> LLMResponse:
        """Call a single Groq model."""
        from groq import AsyncGroq

        client = AsyncGroq(api_key=self._api_key)
        response = await client.chat.completions.create(
            model=model_name,
            messages=messages,
            tools=tools if tools else None,
            stream=False,
        )
        choice = response.choices[0]
        tool_calls = []
        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                tool_calls.append(
                    {
                        "id": tc.id,
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    }
                )

        return LLMResponse(
            content=choice.message.content or "",
            tool_calls=tool_calls,
            model=model_name,
            prompt_tokens=response.usage.prompt_tokens if response.usage else 0,
            completion_tokens=response.usage.completion_tokens if response.usage else 0,
        )
