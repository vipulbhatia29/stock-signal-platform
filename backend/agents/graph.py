"""LangGraph StateGraph for agent orchestration.

Two nodes: call_model → execute_tools → loop back.
Compiles with MemorySaver checkpointer for session persistence.
Phase 6: swap MemorySaver for PostgresSaver or RedisSaver.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import AnyMessage, add_messages
from langgraph.prebuilt import ToolNode

from backend.agents.base import BaseAgent
from backend.tools.base import ToolResult
from backend.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 15


class AgentState(TypedDict):
    """State managed by the LangGraph agent graph."""

    messages: Annotated[list[AnyMessage], add_messages]
    agent_type: str
    iteration: int
    tool_results: list[dict]
    usage: dict


async def execute_tool_safely(
    registry: ToolRegistry,
    tool_name: str,
    params: dict[str, Any],
) -> ToolResult:
    """Execute a tool with timeout and error isolation."""
    try:
        tool = registry.get(tool_name)
        return await asyncio.wait_for(
            tool.execute(params),
            timeout=tool.timeout_seconds,
        )
    except KeyError:
        return ToolResult(status="error", error=f"Tool '{tool_name}' not found")
    except asyncio.TimeoutError:
        logger.warning("tool_timeout", extra={"tool": tool_name})
        return ToolResult(status="timeout", error="Tool took too long")
    except Exception as e:
        logger.error("tool_failed", extra={"tool": tool_name, "error": str(e)})
        return ToolResult(status="error", error=str(e))


def build_agent_graph(
    agent: BaseAgent,
    registry: ToolRegistry,
    llm: Any,
    max_iterations: int = MAX_ITERATIONS,
) -> Any:
    """Build and compile the LangGraph StateGraph for an agent.

    Args:
        agent: The agent (StockAgent or GeneralAgent) — determines tool filter.
        registry: The ToolRegistry with all registered tools.
        llm: A LangChain-compatible chat model with .bind_tools() support.
        max_iterations: Max tool-calling iterations before forcing synthesis.

    Returns:
        Compiled LangGraph graph with MemorySaver checkpointer.
    """
    lc_tools = registry.get_langchain_tools(agent.tool_filter)
    model_with_tools = llm.bind_tools(lc_tools) if lc_tools else llm

    async def call_model(state: AgentState) -> dict:
        """Invoke the LLM with current messages and tool schemas."""
        response = await model_with_tools.ainvoke(state["messages"])
        return {
            "messages": [response],
            "iteration": state["iteration"] + 1,
        }

    def should_continue(state: AgentState) -> str:
        """Route: execute tools or end."""
        last_message = state["messages"][-1]
        if state["iteration"] >= max_iterations:
            return "end"
        if isinstance(last_message, AIMessage) and last_message.tool_calls:
            return "execute_tools"
        return "end"

    # Build graph
    tool_node = ToolNode(lc_tools) if lc_tools else None
    graph = StateGraph(AgentState)
    graph.add_node("call_model", call_model)

    if tool_node:
        graph.add_node("execute_tools", tool_node)
        graph.add_edge(START, "call_model")
        graph.add_conditional_edges(
            "call_model",
            should_continue,
            {"execute_tools": "execute_tools", "end": END},
        )
        graph.add_edge("execute_tools", "call_model")
    else:
        graph.add_edge(START, "call_model")
        graph.add_edge("call_model", END)

    # Compile with checkpointer
    checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer)
