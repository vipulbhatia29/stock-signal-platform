"""Base classes for the Tool Registry system.

All internal tools inherit from BaseTool. External MCP tools are wrapped as ProxiedTool.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, ClassVar, Literal

from pydantic import BaseModel

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CachePolicy:
    """Redis caching configuration for a tool."""

    ttl: timedelta
    key_fields: list[str]
    backend: Literal["redis"] = "redis"


def _json_serializer(obj: Any) -> Any:
    """Custom JSON serializer for types not handled by default encoder.

    Handles datetime, date, Decimal, and set objects.

    Args:
        obj: The object to serialize.

    Returns:
        A JSON-serializable representation.

    Raises:
        TypeError: If the object type is not supported.
    """
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, set):
        return sorted(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


@dataclass
class ToolResult:
    """Result of a tool execution."""

    status: Literal["ok", "degraded", "timeout", "error"]
    data: Any = None
    error: str | None = None

    def to_json(self) -> str:
        """Serialize this ToolResult to a JSON string.

        Handles non-serializable types: datetime/date to ISO string,
        Decimal to float, set to sorted list.

        Returns:
            A JSON string representation of this ToolResult.
        """
        payload = {
            "status": self.status,
            "data": self.data,
            "error": self.error,
        }
        return json.dumps(payload, default=_json_serializer)

    @classmethod
    def from_json(cls, text: str) -> ToolResult:
        """Deserialize a ToolResult from a JSON string.

        Args:
            text: JSON string previously produced by ``to_json()``.

        Returns:
            A new ToolResult instance.
        """
        payload = json.loads(text)
        return cls(
            status=payload["status"],
            data=payload.get("data"),
            error=payload.get("error"),
        )


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
