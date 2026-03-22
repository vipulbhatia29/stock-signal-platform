"""Tests for V2 stream events."""

import json
from unittest.mock import AsyncMock

import pytest

from backend.agents.stream import StreamEvent, stream_graph_v2_events


class TestStreamEventTypes:
    """Tests for new StreamEvent types."""

    def test_plan_event_serializes(self) -> None:
        """Plan event should serialize with steps data."""
        event = StreamEvent(
            type="plan",
            content="Analyzing PLTR",
            data={"steps": ["get_fundamentals", "get_analyst_targets"]},
        )
        parsed = json.loads(event.to_ndjson())
        assert parsed["type"] == "plan"
        assert "get_fundamentals" in parsed["data"]["steps"]

    def test_decline_event_serializes(self) -> None:
        """Decline event should include message."""
        event = StreamEvent(type="decline", content="I focus on financial analysis.")
        parsed = json.loads(event.to_ndjson())
        assert parsed["type"] == "decline"
        assert "financial" in parsed["content"]

    def test_evidence_event_serializes(self) -> None:
        """Evidence event should include evidence list."""
        evidence = [{"claim": "Score 8.2", "source_tool": "analyze_stock"}]
        event = StreamEvent(type="evidence", data=evidence)
        parsed = json.loads(event.to_ndjson())
        assert parsed["type"] == "evidence"
        assert len(parsed["data"]) == 1

    def test_tool_error_event_serializes(self) -> None:
        """Tool error event should include tool name and error."""
        event = StreamEvent(type="tool_error", tool="get_fundamentals", error="Timeout")
        parsed = json.loads(event.to_ndjson())
        assert parsed["type"] == "tool_error"
        assert parsed["tool"] == "get_fundamentals"


class TestStreamGraphV2Events:
    """Tests for stream_graph_v2_events."""

    @pytest.mark.asyncio
    async def test_full_flow_emits_plan_and_token(self) -> None:
        """Full analysis should emit thinking, plan, tool_result, token, done."""
        mock_graph = AsyncMock()
        mock_graph.ainvoke.return_value = {
            "plan": {
                "intent": "stock_analysis",
                "reasoning": "Analyzing PLTR",
                "steps": [{"tool": "get_fundamentals"}],
            },
            "tool_results": [
                {"tool": "get_fundamentals", "status": "ok", "data": {"ticker": "PLTR"}},
            ],
            "synthesis": {"evidence": [], "summary": "PLTR looks good."},
            "response_text": "PLTR looks good.",
        }

        events = []
        async for event in stream_graph_v2_events(mock_graph, {}):
            events.append(event)

        types = [e.type for e in events]
        assert "thinking" in types
        assert "plan" in types
        assert "tool_result" in types
        assert "token" in types
        assert "done" in types

    @pytest.mark.asyncio
    async def test_out_of_scope_emits_decline(self) -> None:
        """Out-of-scope should emit thinking, decline, done."""
        mock_graph = AsyncMock()
        mock_graph.ainvoke.return_value = {
            "plan": {"intent": "out_of_scope", "steps": []},
            "decline_message": "I focus on financial analysis.",
            "tool_results": [],
            "synthesis": {},
            "response_text": "",
        }

        events = []
        async for event in stream_graph_v2_events(mock_graph, {}):
            events.append(event)

        types = [e.type for e in events]
        assert "decline" in types
        assert "done" in types
        # No plan or tool_result events
        assert "plan" not in types
        assert "tool_result" not in types

    @pytest.mark.asyncio
    async def test_tool_error_emitted(self) -> None:
        """Failed tools should emit tool_error events."""
        mock_graph = AsyncMock()
        mock_graph.ainvoke.return_value = {
            "plan": {
                "intent": "stock_analysis",
                "steps": [{"tool": "get_fundamentals"}],
            },
            "tool_results": [
                {
                    "tool": "get_fundamentals",
                    "status": "unavailable",
                    "data": None,
                    "reason": "API timeout",
                },
            ],
            "synthesis": {"evidence": [], "summary": "Partial data."},
            "response_text": "Partial data.",
        }

        events = []
        async for event in stream_graph_v2_events(mock_graph, {}):
            events.append(event)

        error_events = [e for e in events if e.type == "tool_error"]
        assert len(error_events) == 1
        assert error_events[0].tool == "get_fundamentals"

    @pytest.mark.asyncio
    async def test_evidence_emitted(self) -> None:
        """Synthesis with evidence should emit evidence event."""
        mock_graph = AsyncMock()
        mock_graph.ainvoke.return_value = {
            "plan": {"intent": "stock_analysis", "steps": [{"tool": "t"}]},
            "tool_results": [{"tool": "t", "status": "ok", "data": {}}],
            "synthesis": {
                "evidence": [
                    {"claim": "Score 8", "source_tool": "analyze_stock"},
                ],
                "summary": "Strong.",
            },
            "response_text": "Strong.",
        }

        events = []
        async for event in stream_graph_v2_events(mock_graph, {}):
            events.append(event)

        evidence_events = [e for e in events if e.type == "evidence"]
        assert len(evidence_events) == 1

    @pytest.mark.asyncio
    async def test_graph_error_emits_error_event(self) -> None:
        """Graph exception should emit error event."""
        mock_graph = AsyncMock()
        mock_graph.ainvoke.side_effect = RuntimeError("Graph crashed")

        events = []
        async for event in stream_graph_v2_events(mock_graph, {}):
            events.append(event)

        types = [e.type for e in events]
        assert "error" in types
        assert "done" in types
