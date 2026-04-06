"""Base agent ABC."""

from __future__ import annotations

from abc import ABC
from pathlib import Path
from typing import ClassVar

from backend.tools.base import ToolFilter

PROMPTS_DIR = Path(__file__).parent / "prompts"


class BaseAgent(ABC):
    """Abstract base for all agent types.

    Subclasses must set both class variables. They're declared without
    defaults so pyright flags missing overrides; at runtime, accessing an
    unset attribute on a subclass raises AttributeError immediately.
    """

    agent_type: ClassVar[str]
    tool_filter: ClassVar[ToolFilter]

    def system_prompt(self) -> str:
        """Load the agent's system prompt from markdown file."""
        prompt_file = PROMPTS_DIR / f"{self.agent_type}_agent.md"
        return prompt_file.read_text(encoding="utf-8")
