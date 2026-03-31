"""Tests for chat router decline logging to observability."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


class TestDeclineLogging:
    """Tests that decline paths write to llm_call_log."""

    @pytest.mark.asyncio
    async def test_log_decline_writes_declined_status(self) -> None:
        """_log_decline should call write_event with status='declined'."""
        with patch(
            "backend.agents.observability_writer.write_event",
            new_callable=AsyncMock,
        ) as mock_write:
            from backend.routers.chat import _log_decline

            await _log_decline("injection_detected")

            mock_write.assert_awaited_once()
            call_args = mock_write.call_args
            assert call_args[0][0] == "llm_call"
            assert call_args[0][1]["status"] == "declined"
            assert call_args[0][1]["error"] == "injection_detected"

    @pytest.mark.asyncio
    async def test_log_decline_sets_provider_to_none(self) -> None:
        """Declined queries should have provider='none' since no LLM was called."""
        with patch(
            "backend.agents.observability_writer.write_event",
            new_callable=AsyncMock,
        ) as mock_write:
            from backend.routers.chat import _log_decline

            await _log_decline("out_of_scope")

            data = mock_write.call_args[0][1]
            assert data["provider"] == "none"
            assert data["model"] == "none"

    @pytest.mark.asyncio
    async def test_log_decline_sets_zero_tokens(self) -> None:
        """Declined queries should report zero token usage."""
        with patch(
            "backend.agents.observability_writer.write_event",
            new_callable=AsyncMock,
        ) as mock_write:
            from backend.routers.chat import _log_decline

            await _log_decline("session_abuse_limit")

            data = mock_write.call_args[0][1]
            assert data["prompt_tokens"] == 0
            assert data["completion_tokens"] == 0
            assert data["latency_ms"] == 0

    @pytest.mark.asyncio
    async def test_log_decline_each_reason(self) -> None:
        """Each decline reason should be passed through as the error field."""
        reasons = [
            "input_length_exceeded",
            "injection_detected",
            "session_abuse_limit",
            "out_of_scope",
        ]
        for reason in reasons:
            with patch(
                "backend.agents.observability_writer.write_event",
                new_callable=AsyncMock,
            ) as mock_write:
                from backend.routers.chat import _log_decline

                await _log_decline(reason)

                data = mock_write.call_args[0][1]
                assert data["error"] == reason, f"Expected error={reason}"
