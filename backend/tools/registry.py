"""Tool Registry — central hub for all tool discovery and execution."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from backend.tools.base import BaseTool, ToolFilter, ToolInfo, ToolResult

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Registry for all internal and proxied tools."""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """Register a tool. Raises ValueError if name is already taken."""
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' already registered")
        self._tools[tool.name] = tool
        logger.info("tool_registered", extra={"tool": tool.name, "category": tool.category})

    def register_mcp(self, adapter: Any) -> None:
        """Register all tools from an MCP adapter."""
        for tool in adapter.get_tools():
            self.register(tool)

    def get(self, name: str) -> BaseTool:
        """Get a tool by name. Raises KeyError if not found."""
        return self._tools[name]

    def discover(self) -> list[ToolInfo]:
        """Return metadata for all registered tools."""
        return [tool.info() for tool in self._tools.values()]

    def by_category(self, *categories: str) -> list[BaseTool]:
        """Return tools matching any of the given categories."""
        return [t for t in self._tools.values() if t.category in categories]

    def schemas(self, tool_filter: ToolFilter) -> list[dict]:
        """Return LLM-compatible function schemas for tools matching the filter."""
        return [
            tool.info().to_llm_schema()
            for tool in self._tools.values()
            if tool_filter.matches(tool.info())
        ]

    async def execute(self, name: str, params: dict[str, Any]) -> ToolResult:
        """Execute a tool by name with the given params."""
        tool = self.get(name)
        return await asyncio.wait_for(
            tool.execute(params),
            timeout=tool.timeout_seconds,
        )

    def get_langchain_tools(self, tool_filter: ToolFilter) -> list:
        """Return LangChain-compatible tool objects for LangGraph ToolNode."""
        from langchain_core.tools import StructuredTool

        lc_tools = []
        for tool in self._tools.values():
            if tool_filter.matches(tool.info()):
                lc_tool = StructuredTool.from_function(
                    coroutine=tool.execute,
                    name=tool.name,
                    description=tool.description,
                )
                lc_tools.append(lc_tool)
        return lc_tools

    def health(self) -> dict[str, bool]:
        """Return health status for all registered tools."""
        return {name: True for name in self._tools}
