"""Agent V2 Graph — Plan→Execute→Synthesize three-phase StateGraph.

Feature-flagged behind AGENT_V2=true. Coexists with the V1 ReAct graph
in graph.py. The chat router selects which graph to use at runtime.
"""

from __future__ import annotations

import logging
from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph

logger = logging.getLogger(__name__)

MAX_REPLAN = 1


class AgentStateV2(TypedDict):
    """State managed by the V2 agent graph."""

    messages: list
    phase: Literal["plan", "execute", "synthesize", "format_simple", "done"]
    plan: dict[str, Any]
    tool_results: list[dict[str, Any]]
    synthesis: dict[str, Any]
    iteration: int
    replan_count: int
    start_time: float
    user_context: dict[str, Any]
    query_id: str
    skip_synthesis: bool
    response_text: str
    decline_message: str


def build_agent_graph_v2(
    plan_fn: Any,
    execute_fn: Any,
    synthesize_fn: Any,
    format_simple_fn: Any,
    tool_executor: Any,
    tools_description: str,
) -> Any:
    """Build and compile the V2 three-phase LangGraph StateGraph.

    Args:
        plan_fn: async (query, tools_desc, user_context, llm_chat) -> plan dict
        execute_fn: async (steps, tool_executor, on_step) -> execution result dict
        synthesize_fn: async (tool_results, user_context, llm_chat) -> synthesis dict
        format_simple_fn: (tool_name, data) -> formatted string
        tool_executor: async (tool_name, params) -> ToolResult
        tools_description: Formatted tool descriptions for the planner.

    Returns:
        Compiled LangGraph graph.
    """

    async def plan_node(state: AgentStateV2) -> dict:
        """Plan phase: classify intent and generate tool plan."""
        messages = state["messages"]
        query = ""
        for msg in reversed(messages):
            if isinstance(msg, dict) and msg.get("role") == "user":
                query = msg.get("content", "")
                break
            elif hasattr(msg, "content") and hasattr(msg, "type"):
                if msg.type == "human":
                    query = msg.content
                    break

        plan = state.get("plan") or {}
        # Use the injected plan_fn which already has llm_chat bound
        plan = await plan_fn(
            query=query,
            tools_description=tools_description,
            user_context=state.get("user_context", {}),
        )

        return {
            "plan": plan,
            "phase": "plan",
            "skip_synthesis": plan.get("skip_synthesis", False),
            "decline_message": plan.get("decline_message", ""),
        }

    async def execute_node(state: AgentStateV2) -> dict:
        """Execute phase: run tool plan mechanically."""
        plan = state.get("plan", {})
        steps = plan.get("steps", [])

        result = await execute_fn(steps, tool_executor)

        new_state: dict[str, Any] = {
            "tool_results": result["results"],
            "phase": "execute",
            "iteration": state.get("iteration", 0) + 1,
        }

        # If replan needed and we haven't exceeded limit
        if result.get("needs_replan") and state.get("replan_count", 0) < MAX_REPLAN:
            new_state["replan_count"] = state.get("replan_count", 0) + 1

        return new_state

    async def synthesize_node(state: AgentStateV2) -> dict:
        """Synthesize phase: produce final analysis from tool results."""
        synthesis = await synthesize_fn(
            tool_results=state.get("tool_results", []),
            user_context=state.get("user_context", {}),
        )

        response_text = synthesis.get("summary", "Analysis complete.")

        return {
            "synthesis": synthesis,
            "response_text": response_text,
            "phase": "synthesize",
        }

    async def format_simple_node(state: AgentStateV2) -> dict:
        """Format simple result without LLM synthesis."""
        results = state.get("tool_results", [])
        if results and results[0].get("status") == "ok":
            tool_name = results[0].get("tool", "")
            data = results[0].get("data", {})
            text = format_simple_fn(tool_name, data)
        else:
            text = "I couldn't retrieve that information. Please try again."

        return {
            "response_text": text,
            "phase": "format_simple",
        }

    # ── Routing functions ────────────────────────────────────────────

    def route_after_plan(state: AgentStateV2) -> str:
        """Route after planning: execute, decline, or done."""
        plan = state.get("plan", {})
        intent = plan.get("intent", "")

        if intent == "out_of_scope":
            return "done"

        steps = plan.get("steps", [])
        if not steps:
            return "done"

        return "execute"

    def route_after_execute(state: AgentStateV2) -> str:
        """Route after execution: synthesize, replan, or format simple."""
        tool_results = state.get("tool_results", [])

        # Check if replan needed (empty search) and replan budget remaining
        has_replan_results = any(
            r.get("status") == "ok" and isinstance(r.get("data"), list) and len(r["data"]) == 0
            for r in tool_results
            if r.get("tool") == "search_stocks"
        )
        if has_replan_results and state.get("replan_count", 0) <= MAX_REPLAN:
            return "plan"

        # Skip synthesis for simple queries
        if state.get("skip_synthesis"):
            return "format_simple"

        return "synthesize"

    # ── Build graph ──────────────────────────────────────────────────

    graph = StateGraph(AgentStateV2)

    graph.add_node("plan", plan_node)
    graph.add_node("execute", execute_node)
    graph.add_node("synthesize", synthesize_node)
    graph.add_node("format_simple", format_simple_node)

    graph.add_edge(START, "plan")
    graph.add_conditional_edges(
        "plan",
        route_after_plan,
        {"execute": "execute", "done": END},
    )
    graph.add_conditional_edges(
        "execute",
        route_after_execute,
        {"synthesize": "synthesize", "plan": "plan", "format_simple": "format_simple"},
    )
    graph.add_edge("synthesize", END)
    graph.add_edge("format_simple", END)

    return graph.compile()
