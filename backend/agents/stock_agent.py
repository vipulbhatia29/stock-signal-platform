"""StockAgent — full-toolkit financial analysis agent."""

from backend.agents.base import BaseAgent
from backend.tools.base import ToolFilter


class StockAgent(BaseAgent):
    """Financial analysis agent with access to all tool categories."""

    agent_type = "stock"
    tool_filter = ToolFilter(
        categories=["analysis", "data", "portfolio", "macro", "news", "sec"]
    )
