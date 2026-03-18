"""Groq LLM provider — uses LangChain ChatGroq."""

from __future__ import annotations

import logging
from typing import Any

from backend.agents.llm_client import LLMProvider, LLMResponse, ProviderHealth

logger = logging.getLogger(__name__)


class GroqProvider(LLMProvider):
    """Groq provider wrapping LangChain's ChatGroq."""

    def __init__(self, api_key: str, model: str = "llama-3.3-70b-versatile"):
        self._api_key = api_key
        self._model = model
        self.health = ProviderHealth(provider="groq")
        self._chat_model = None

    @property
    def name(self) -> str:
        """Provider name."""
        return "groq"

    def get_chat_model(self) -> Any:
        """Return LangChain ChatGroq instance for LangGraph."""
        if self._chat_model is None:
            from langchain_groq import ChatGroq

            self._chat_model = ChatGroq(
                api_key=self._api_key,
                model=self._model,
            )
        return self._chat_model

    async def chat(self, messages, tools, stream=False) -> LLMResponse:
        """Send chat completion via Groq SDK."""
        from groq import AsyncGroq

        client = AsyncGroq(api_key=self._api_key)
        response = await client.chat.completions.create(
            model=self._model,
            messages=messages,
            tools=tools if tools else None,
            stream=False,
        )
        choice = response.choices[0]
        tool_calls = []
        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                tool_calls.append({
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                })

        return LLMResponse(
            content=choice.message.content or "",
            tool_calls=tool_calls,
            model=self._model,
            prompt_tokens=response.usage.prompt_tokens if response.usage else 0,
            completion_tokens=response.usage.completion_tokens if response.usage else 0,
        )
