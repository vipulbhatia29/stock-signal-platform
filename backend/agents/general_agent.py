"""GeneralAgent — limited toolkit for general Q&A."""

from backend.agents.base import BaseAgent
from backend.tools.base import ToolFilter


class GeneralAgent(BaseAgent):
    """General-purpose agent with access to data and news tools only."""

    agent_type = "general"
    tool_filter = ToolFilter(categories=["data", "news"])
