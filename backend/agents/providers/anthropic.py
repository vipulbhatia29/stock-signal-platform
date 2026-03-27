"""Anthropic LLM provider — uses LangChain ChatAnthropic."""

from __future__ import annotations

import logging
import time
from typing import Any

from backend.agents.llm_client import LLMProvider, LLMResponse, ProviderHealth

logger = logging.getLogger(__name__)


class AnthropicProvider(LLMProvider):
    """Anthropic provider wrapping LangChain's ChatAnthropic."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        self._api_key = api_key
        self._model = model
        self.health = ProviderHealth(provider="anthropic")
        self._chat_model = None

    @property
    def name(self) -> str:
        """Provider name."""
        return "anthropic"

    def get_chat_model(self) -> Any:
        """Return LangChain ChatAnthropic instance for LangGraph."""
        if self._chat_model is None:
            from langchain_anthropic import ChatAnthropic

            self._chat_model = ChatAnthropic(
                api_key=self._api_key,
                model=self._model,
            )
        return self._chat_model

    async def chat(self, messages, tools, stream=False) -> LLMResponse:
        """Send chat completion via Anthropic SDK."""
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=self._api_key)

        # Extract system message if present
        system_msg = ""
        api_messages = []
        for msg in messages:
            if msg.get("role") == "system":
                system_msg = msg["content"]
            else:
                api_messages.append(msg)

        # Convert tools to Anthropic format
        anthropic_tools = []
        for t in tools or []:
            func = t.get("function", {})
            anthropic_tools.append(
                {
                    "name": func.get("name", ""),
                    "description": func.get("description", ""),
                    "input_schema": func.get("parameters", {}),
                }
            )

        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": 4096,
            "messages": api_messages,
        }
        if system_msg:
            kwargs["system"] = system_msg
        if anthropic_tools:
            kwargs["tools"] = anthropic_tools

        start = time.monotonic()
        response = await client.messages.create(**kwargs)
        latency_ms = int((time.monotonic() - start) * 1000)

        # Normalize Anthropic response to LLMResponse
        content = ""
        tool_calls = []
        for block in response.content:
            if block.type == "text":
                content += block.text
            elif block.type == "tool_use":
                tool_calls.append(
                    {
                        "id": block.id,
                        "name": block.name,
                        "arguments": block.input,
                    }
                )

        result = LLMResponse(
            content=content,
            tool_calls=tool_calls,
            model=self._model,
            prompt_tokens=response.usage.input_tokens,
            completion_tokens=response.usage.output_tokens,
        )

        await self._record_success(
            model=self._model,
            latency_ms=latency_ms,
            prompt_tokens=response.usage.input_tokens,
            completion_tokens=response.usage.output_tokens,
        )

        return result
