"""Tests for MessageCompressor 3-stage compression."""

from pathlib import Path

import pytest

from backend.agents.message_compressor import MessageCompressor
from backend.observability.token_budget import TokenBudget

_PROMPT_DIR = Path(__file__).resolve().parents[3] / "backend" / "agents" / "prompts"


@pytest.fixture
def compressor():
    """MessageCompressor with default settings."""
    return MessageCompressor(prompt_dir=_PROMPT_DIR)


def _make_scratchpad(
    system_lines: int = 100,
    history_turns: int = 5,
    tool_results: int = 3,
    tool_result_len: int = 5000,
) -> list[dict]:
    """Build a realistic scratchpad for testing.

    Structure: system + history pairs + current query + tool loop messages.
    """
    msgs: list[dict] = []
    # System prompt (large, with examples like the real one)
    msgs.append({"role": "system", "content": "x " * system_lines * 10})
    # History turns (pre-loop conversation)
    for i in range(history_turns):
        msgs.append({"role": "user", "content": f"history question {i}"})
        msgs.append({"role": "assistant", "content": f"history answer {i}"})
    # Current query (boundary)
    msgs.append({"role": "user", "content": "current question"})
    # Tool call + results (loop-generated)
    for i in range(tool_results):
        msgs.append(
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": f"tc_{i}",
                        "type": "function",
                        "function": {"name": f"tool_{i}", "arguments": "{}"},
                    }
                ],
            }
        )
        msgs.append(
            {
                "role": "tool",
                "tool_call_id": f"tc_{i}",
                "content": "d " * (tool_result_len // 2),
            }
        )
    return msgs


class TestStage1SystemPrompt:
    def test_condenses_system_prompt_on_iteration_2(self, compressor):
        """Stage 1: system prompt replaced with condensed version on iteration >= 2."""
        scratchpad = _make_scratchpad()
        original_system_len = len(scratchpad[0]["content"])

        result = compressor.compress(scratchpad, iteration=2)
        compressed_system_len = len(result[0]["content"])

        assert compressed_system_len < original_system_len * 0.6

    def test_keeps_full_system_on_iteration_1(self, compressor):
        """Stage 1: full system prompt kept on iteration 1."""
        scratchpad = _make_scratchpad()
        original_system = scratchpad[0]["content"]

        result = compressor.compress(scratchpad, iteration=1)
        assert result[0]["content"] == original_system

    def test_preserves_user_context_in_condensed(self, compressor):
        """Stage 1: user context from original is preserved in condensed prompt."""
        msgs = [
            {
                "role": "system",
                "content": (
                    "Long system prompt with examples...\n"
                    "## User context\nHoldings: AAPL, MSFT\n"
                    "## Entity context\nRecent: NVDA"
                ),
            },
            {"role": "user", "content": "hi"},
        ]

        result = compressor.compress(msgs, iteration=2)
        assert "Holdings: AAPL, MSFT" in result[0]["content"]
        assert "Recent: NVDA" in result[0]["content"]


class TestStage2HistoryTruncation:
    def test_truncates_history_to_keep_latest(self, compressor):
        """Stage 2: old history turns dropped, current query + loop messages kept."""
        scratchpad = _make_scratchpad(history_turns=8, tool_results=2)
        original_len = len(scratchpad)

        result = compressor.compress(scratchpad, iteration=3)

        assert len(result) < original_len
        assert any(m.get("content") == "current question" for m in result)
        assert any(m.get("role") == "tool" for m in result)

    def test_progressive_reduces_to_1_turn(self, compressor):
        """Stage 2 progressive: target_tokens forces history down to 1 turn."""
        scratchpad = _make_scratchpad(history_turns=5, tool_results=2)

        result = compressor.compress(scratchpad, iteration=3, target_tokens=500)

        user_msgs = [
            m
            for m in result
            if m.get("role") == "user" and m.get("content", "").startswith("history")
        ]
        assert len(user_msgs) <= 1

    def test_preserves_all_loop_messages(self, compressor):
        """Stage 2: all tool calls and results from current request are kept."""
        scratchpad = _make_scratchpad(history_turns=8, tool_results=4)

        result = compressor.compress(scratchpad, iteration=3)

        tool_msgs = [m for m in result if m.get("role") == "tool"]
        assert len(tool_msgs) == 4

    def test_no_history_no_crash(self, compressor):
        """Stage 2: handles scratchpad with no history turns gracefully."""
        msgs = [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "query"},
        ]
        result = compressor.compress(msgs, iteration=1)
        assert len(result) == 2


class TestStage3ToolResultTruncation:
    def test_truncates_long_tool_results(self, compressor):
        """Stage 3: tool result content capped at max_tool_result_chars."""
        scratchpad = _make_scratchpad(tool_result_len=8000)

        result = compressor.compress(scratchpad, iteration=2)

        for msg in result:
            if msg.get("role") == "tool":
                assert len(msg["content"]) <= 4100  # 4000 + truncation notice

    def test_progressive_caps_tool_results_tighter(self, compressor):
        """Stage 3 progressive: target_tokens tightens tool result cap."""
        scratchpad = _make_scratchpad(tool_result_len=5000)

        result = compressor.compress(scratchpad, iteration=3, target_tokens=500)

        for msg in result:
            if msg.get("role") == "tool":
                assert len(msg["content"]) <= 1600  # 1500 + notice

    def test_short_tool_results_unchanged(self, compressor):
        """Stage 3: tool results under the cap are not modified."""
        scratchpad = _make_scratchpad(tool_result_len=100)

        result = compressor.compress(scratchpad, iteration=2)

        for msg in result:
            if msg.get("role") == "tool":
                assert "truncated" not in msg["content"]


class TestEstimateReduction:
    def test_compression_reduces_token_estimate(self, compressor):
        """Compressed messages should have lower token estimate."""
        scratchpad = _make_scratchpad(
            system_lines=100, history_turns=5, tool_results=3, tool_result_len=5000
        )
        original_est = TokenBudget.estimate_tokens(scratchpad)

        compressed = compressor.compress(scratchpad, iteration=3, target_tokens=2000)
        compressed_est = TokenBudget.estimate_tokens(compressed)

        assert compressed_est < original_est * 0.7


class TestEarlyExit:
    def test_skips_compression_when_well_under_budget(self, compressor):
        """Early exit: if estimate < 50% of target, return copy without compressing."""
        msgs = [
            {"role": "system", "content": "short"},
            {"role": "user", "content": "hi"},
        ]
        result = compressor.compress(msgs, iteration=3, target_tokens=100000)

        # Should return same content (no compression applied)
        assert result[0]["content"] == "short"
        assert len(result) == 2


class TestOriginalNotMutated:
    def test_original_messages_unchanged(self, compressor):
        """Compression must not mutate the input list."""
        scratchpad = _make_scratchpad(tool_result_len=8000)
        original_lens = [len(m.get("content", "")) for m in scratchpad]

        compressor.compress(scratchpad, iteration=3, target_tokens=500)

        current_lens = [len(m.get("content", "")) for m in scratchpad]
        assert original_lens == current_lens
