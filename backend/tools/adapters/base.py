"""MCPAdapter ABC — base class for external data-source connections."""

from __future__ import annotations

from abc import ABC, abstractmethod

from backend.tools.base import ProxiedTool, ToolResult


class MCPAdapter(ABC):
    """Abstract adapter for consuming an external data source's tools.

    Each adapter wraps a specific API or library and exposes its capabilities
    as ProxiedTool instances that the ToolRegistry can discover and execute.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Adapter identifier (e.g., 'edgar_tools')."""
        ...

    @abstractmethod
    def get_tools(self) -> list[ProxiedTool]:
        """Return ProxiedTool instances for all tools this adapter exposes."""
        ...

    @abstractmethod
    async def execute(self, tool_name: str, params: dict) -> ToolResult:
        """Execute a specific tool via the external API or library."""
        ...

    async def health_check(self) -> bool:
        """Check if the external data source is reachable. Default: True."""
        return True
