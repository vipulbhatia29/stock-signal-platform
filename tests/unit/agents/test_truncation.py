"""Tests for tool result truncation in synthesizer."""

from backend.agents.synthesizer import _truncate_tool_results


class TestTruncateToolResults:
    def test_short_results_unchanged(self):
        """Results under max_chars are not modified."""
        results = [{"tool": "analyze", "data": {"score": 8.5}}]
        truncated = _truncate_tool_results(results, max_chars=3000)
        assert truncated == results

    def test_long_results_truncated(self):
        """Results exceeding max_chars are truncated with marker."""
        big_data = {"content": "x" * 5000}
        results = [{"tool": "analyze", "data": big_data}]
        truncated = _truncate_tool_results(results, max_chars=100)
        assert len(truncated) == 1
        assert "truncated" in truncated[0]["data"]
        assert len(truncated[0]["data"]) < 200  # 100 + marker text

    def test_none_data_unchanged(self):
        """Results with None data pass through."""
        results = [{"tool": "analyze", "data": None}]
        truncated = _truncate_tool_results(results, max_chars=100)
        assert truncated[0]["data"] is None

    def test_multiple_results_each_truncated(self):
        """Each result is independently truncated."""
        results = [
            {"tool": "a", "data": {"x": "y" * 5000}},
            {"tool": "b", "data": {"small": True}},
            {"tool": "c", "data": {"z": "w" * 5000}},
        ]
        truncated = _truncate_tool_results(results, max_chars=200)
        # Tool "a" and "c" should be truncated, "b" unchanged
        assert "truncated" in truncated[0]["data"]
        assert truncated[1]["data"] == {"small": True}
        assert "truncated" in truncated[2]["data"]

    def test_original_not_mutated(self):
        """Truncation returns new dicts, not mutated originals."""
        big_data = {"content": "x" * 5000}
        results = [{"tool": "analyze", "data": big_data}]
        _truncate_tool_results(results, max_chars=100)
        # Original should still have the dict
        assert isinstance(results[0]["data"], dict)

    def test_string_data_truncated(self):
        """String data values are also truncated."""
        results = [{"tool": "web_search", "data": "x" * 5000}]
        truncated = _truncate_tool_results(results, max_chars=100)
        assert "truncated" in truncated[0]["data"]
