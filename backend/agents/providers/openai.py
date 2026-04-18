"""OpenAI LLM provider — uses LangChain ChatOpenAI. Also serves as LM Studio local provider."""

from __future__ import annotations

import logging
import time
from typing import Any

from backend.agents.llm_client import LLMProvider, LLMResponse, ProviderHealth

logger = logging.getLogger(__name__)


class OpenAIProvider(LLMProvider):
    """OpenAI provider wrapping LangChain's ChatOpenAI."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o",
        base_url: str | None = None,
    ):
        self._api_key = api_key
        self._model = model
        self._base_url = base_url  # Override for LM Studio (e.g., http://localhost:1234/v1)
        self.health = ProviderHealth(provider="openai")
        self._chat_model = None

    @property
    def name(self) -> str:
        """Provider name."""
        return "openai"

    def get_chat_model(self) -> Any:
        """Return LangChain ChatOpenAI instance for LangGraph."""
        if self._chat_model is None:
            from langchain_openai import ChatOpenAI

            kwargs: dict[str, Any] = {
                "api_key": self._api_key,
                "model": self._model,
            }
            if self._base_url:
                kwargs["base_url"] = self._base_url
            self._chat_model = ChatOpenAI(**kwargs)
        return self._chat_model

    async def chat(self, messages, tools, stream=False) -> LLMResponse:
        """Send chat completion via OpenAI SDK."""
        from openai import AsyncOpenAI

        from backend.observability.instrumentation.providers import ExternalProvider
        from backend.services.http_client import get_observed_http_client

        kwargs: dict[str, Any] = {"api_key": self._api_key}
        if self._base_url:
            kwargs["base_url"] = self._base_url

        client = AsyncOpenAI(
            **kwargs,
            http_client=get_observed_http_client(ExternalProvider.OPENAI),
        )
        start = time.monotonic()
        response = await client.chat.completions.create(
            model=self._model,
            messages=messages,
            tools=tools if tools else None,
            stream=False,
        )
        latency_ms = int((time.monotonic() - start) * 1000)
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

        result = LLMResponse(
            content=choice.message.content or "",
            tool_calls=tool_calls,
            model=self._model,
            prompt_tokens=response.usage.prompt_tokens if response.usage else 0,
            completion_tokens=response.usage.completion_tokens if response.usage else 0,
        )

        await self._record_success(
            model=self._model,
            latency_ms=latency_ms,
            prompt_tokens=response.usage.prompt_tokens if response.usage else 0,
            completion_tokens=response.usage.completion_tokens if response.usage else 0,
        )

        return result
