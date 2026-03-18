"""Tests for agent types and prompt loading."""

from pathlib import Path

from backend.agents.base import BaseAgent
from backend.agents.general_agent import GeneralAgent
from backend.agents.stock_agent import StockAgent
from backend.tools.base import ToolFilter


def test_stock_agent_tool_filter():
    """StockAgent has access to all tool categories."""
    agent = StockAgent()
    assert isinstance(agent.tool_filter, ToolFilter)
    assert "analysis" in agent.tool_filter.categories
    assert "portfolio" in agent.tool_filter.categories
    assert "sec" in agent.tool_filter.categories
    assert "macro" in agent.tool_filter.categories


def test_general_agent_tool_filter():
    """GeneralAgent only has access to data and news."""
    agent = GeneralAgent()
    assert isinstance(agent.tool_filter, ToolFilter)
    assert "data" in agent.tool_filter.categories
    assert "news" in agent.tool_filter.categories
    assert "portfolio" not in agent.tool_filter.categories


def test_stock_agent_system_prompt():
    """StockAgent loads a non-empty system prompt."""
    agent = StockAgent()
    prompt = agent.system_prompt()
    assert len(prompt) > 100
    assert "stock" in prompt.lower() or "financial" in prompt.lower()


def test_general_agent_system_prompt():
    """GeneralAgent loads a non-empty system prompt."""
    agent = GeneralAgent()
    prompt = agent.system_prompt()
    assert len(prompt) > 100


def test_prompt_files_exist():
    """Prompt markdown files exist on disk."""
    prompts_dir = Path(__file__).resolve().parents[2] / "backend" / "agents" / "prompts"
    assert (prompts_dir / "stock_agent.md").exists()
    assert (prompts_dir / "general_agent.md").exists()


def test_stock_agent_type():
    """StockAgent reports correct agent_type."""
    assert StockAgent().agent_type == "stock"


def test_general_agent_type():
    """GeneralAgent reports correct agent_type."""
    assert GeneralAgent().agent_type == "general"
