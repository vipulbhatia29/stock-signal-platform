"""Base agent ABC."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from backend.tools.base import ToolFilter

PROMPTS_DIR = Path(__file__).parent / "prompts"


class BaseAgent(ABC):
    """Abstract base for all agent types."""

    @property
    @abstractmethod
    def agent_type(self) -> str:
        """Agent type identifier (e.g., 'stock', 'general')."""
        ...

    @property
    @abstractmethod
    def tool_filter(self) -> ToolFilter:
        """Which tool categories this agent can access."""
        ...

    def system_prompt(self) -> str:
        """Load the agent's system prompt from markdown file."""
        prompt_file = PROMPTS_DIR / f"{self.agent_type}_agent.md"
        return prompt_file.read_text(encoding="utf-8")
