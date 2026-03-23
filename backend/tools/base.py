"""Base classes for the Tool Registry system.

All internal tools inherit from BaseTool. External MCP tools are wrapped as ProxiedTool.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, ClassVar, Literal

from pydantic import BaseModel

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CachePolicy:
    """Redis caching configuration for a tool."""

    ttl: timedelta
    key_fields: list[str]
    backend: Literal["redis"] = "redis"


@dataclass
class ToolResult:
    """Result of a tool execution."""

    status: Literal["ok", "degraded", "timeout", "error"]
    data: Any = None
    error: str | None = None


@dataclass(frozen=True)
class ToolInfo:
    """Serializable tool metadata for LLM context."""

    name: str
    description: str
    category: str
    parameters: dict[str, Any]

    def to_llm_schema(self) -> dict:
        """Return OpenAI-compatible function-calling schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass(frozen=True)
class ToolFilter:
    """Filter for selecting tools by category."""

    categories: list[str]

    def matches(self, info: ToolInfo) -> bool:
        """Check if a tool's category is in this filter's allowed categories."""
        return info.category in self.categories


class BaseTool(ABC):
    """Abstract base for all tools (internal and proxied)."""

    name: str
    description: str
    category: str
    parameters: dict[str, Any]
    args_schema: ClassVar[type[BaseModel] | None] = None
    cache_policy: CachePolicy | None = None
    timeout_seconds: float = 10.0

    @abstractmethod
    async def execute(self, params: dict[str, Any]) -> ToolResult:
        """Execute the tool with the given parameters."""
        ...

    def info(self) -> ToolInfo:
        """Return serializable metadata."""
        return ToolInfo(
            name=self.name,
            description=self.description,
            category=self.category,
            parameters=self.parameters,
        )


class ProxiedTool(BaseTool):
    """A tool discovered from an external MCP server."""

    timeout_seconds: float = 30.0

    def __init__(
        self,
        name: str,
        description: str,
        category: str,
        parameters: dict[str, Any],
        adapter: Any,
        cache_policy: CachePolicy | None = None,
    ) -> None:
        self.name = name
        self.description = description
        self.category = category
        self.parameters = parameters
        self._adapter = adapter
        self.cache_policy = cache_policy

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        """Delegate execution to the MCP adapter."""
        return await self._adapter.execute(self.name, params)
