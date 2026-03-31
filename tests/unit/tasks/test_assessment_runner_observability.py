"""Tests for assessment runner observability instrumentation.

Verifies that _run_query_live returns a 4-tuple whose 4th element is a
``uuid.UUID``, enabling the caller to join assessment results against
``llm_call_log`` rows via ``query_id``.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestAssessmentRunnerQueryId:
    """Tests that assessment runner propagates query_id for eval score join."""

    @pytest.mark.asyncio
    async def test_run_query_live_returns_query_id(self) -> None:
        """_run_query_live should return a 4-tuple with query_id as the 4th element.

        The contract: ``(response_text: str, tools_called: list[str],
        iterations: int, query_id: UUID)``. Callers store ``query_id`` on
        ``AssessmentResult`` so that observability service can join eval
        scores against ``llm_call_log`` rows.
        """
        from backend.tasks.assessment_runner import _run_query_live

        # --- Minimal golden query stub ---
        golden = MagicMock()
        golden.query_text = "Analyze AAPL"
        golden.mock_failures = {}
        golden.max_iterations = 3

        # --- Minimal user stub ---
        user = MagicMock()
        user.id = uuid.uuid4()

        # --- DB session stub ---
        session = AsyncMock()

        # --- ToolRegistry stub ---
        mock_registry = MagicMock()
        mock_registry.get_tool_schemas.return_value = []

        # --- react_loop stub: yields a text event then a done event ---
        async def _mock_react_loop(*args, **kwargs):
            """Yield minimal stream events so _run_query_live completes."""
            from backend.agents.stream import StreamEvent

            yield StreamEvent(type="token", content="Analysis complete.")

        # --- Patch at the lookup sites (lazy imports inside _run_query_live) ---
        # ToolRegistry and react_loop are imported lazily inside _run_query_live,
        # so we patch at their definition modules (the lookup site rule).
        with (
            patch(
                "backend.tools.registry.ToolRegistry",
                return_value=mock_registry,
            ),
            patch(
                "backend.agents.react_loop.react_loop",
                side_effect=_mock_react_loop,
            ),
        ):
            result = await _run_query_live(golden, user, session)

        # The return value must be a 4-tuple
        assert len(result) == 4, (
            f"Expected 4-tuple (text, tools, iterations, query_id), "
            f"got {len(result)}-tuple: {result!r}"
        )

        response_text, tools_called, iterations, query_id = result

        # 4th element must be a UUID
        assert isinstance(query_id, uuid.UUID), (
            f"4th element should be uuid.UUID for query_id join, got {type(query_id)}"
        )

        # Sanity-check other elements have expected types
        assert isinstance(response_text, str), (
            f"1st element (response_text) should be str, got {type(response_text)}"
        )
        assert isinstance(tools_called, list), (
            f"2nd element (tools_called) should be list, got {type(tools_called)}"
        )
        assert isinstance(iterations, int), (
            f"3rd element (iterations) should be int, got {type(iterations)}"
        )

    @pytest.mark.asyncio
    async def test_run_query_live_query_id_is_unique_per_call(self) -> None:
        """Each _run_query_live call should generate a fresh query_id.

        This ensures assessment runs never accidentally reuse a query_id,
        which would corrupt observability join results.
        """
        from backend.tasks.assessment_runner import _run_query_live

        golden = MagicMock()
        golden.query_text = "Analyze MSFT"
        golden.mock_failures = {}
        golden.max_iterations = 3

        user = MagicMock()
        user.id = uuid.uuid4()

        mock_registry = MagicMock()
        mock_registry.get_tool_schemas.return_value = []

        async def _mock_react_loop(*args, **kwargs):
            """Yield a minimal token event."""
            from backend.agents.stream import StreamEvent

            yield StreamEvent(type="token", content="Done.")

        session = AsyncMock()

        with (
            patch(
                "backend.tools.registry.ToolRegistry",
                return_value=mock_registry,
            ),
            patch(
                "backend.agents.react_loop.react_loop",
                side_effect=_mock_react_loop,
            ),
        ):
            result_a = await _run_query_live(golden, user, session)
            result_b = await _run_query_live(golden, user, session)

        query_id_a = result_a[3]
        query_id_b = result_b[3]

        assert query_id_a != query_id_b, (
            "Each _run_query_live call must generate a unique query_id; "
            f"got duplicate: {query_id_a}"
        )
