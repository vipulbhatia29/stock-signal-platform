"""3-stage message compression for LLM budget management.

Stage 1: System prompt condensing (drop examples on iteration >= 2)
Stage 2: History truncation (keep latest N turns, preserve loop messages)
Stage 3: Tool result truncation (cap content length)

Progressive compression tightens each stage when target_tokens is specified.
"""

from __future__ import annotations

import copy
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_HISTORY_KEEP = 3
_DEFAULT_TOOL_RESULT_CAP = 4000

# Progressive pass configs: (history_keep, tool_cap)
_PROGRESSIVE_PASSES = [
    (3, 4000),  # Pass 1: normal
    (1, 2500),  # Pass 2: tighter
    (0, 1500),  # Pass 3: aggressive
]


class MessageCompressor:
    """3-stage message compressor for LLM scratchpads.

    Operates on OpenAI-format message lists. Does NOT modify the
    original list — returns a compressed copy.
    """

    def __init__(self, prompt_dir: Path | None = None) -> None:
        self._prompt_dir = prompt_dir or Path(__file__).parent / "prompts"
        self._condensed_system: str | None = None

    def _get_condensed_system(self) -> str:
        """Lazy-load the condensed system prompt template."""
        if self._condensed_system is None:
            path = self._prompt_dir / "react_system_condensed.md"
            self._condensed_system = path.read_text(encoding="utf-8")
        return self._condensed_system

    def compress(
        self,
        messages: list[dict],
        iteration: int = 1,
        target_tokens: int | None = None,
    ) -> list[dict]:
        """Compress messages through 3 stages.

        Args:
            messages: OpenAI-format message list (not modified).
            iteration: Current ReAct iteration (1-indexed).
            target_tokens: If set, apply progressive compression
                until estimate is below target.

        Returns:
            Compressed copy of messages.
        """
        if target_tokens is not None:
            from backend.observability.token_budget import TokenBudget

            # Early exit: skip compression if well under budget
            est = TokenBudget.estimate_tokens(messages)
            if est < target_tokens * 0.5:
                return [copy.copy(m) for m in messages]

            # Progressive: try tighter passes until under target
            for history_keep, tool_cap in _PROGRESSIVE_PASSES:
                result = self._apply_stages(
                    [copy.copy(m) for m in messages],
                    iteration,
                    history_keep,
                    tool_cap,
                )
                compressed_est = TokenBudget.estimate_tokens(result)
                if compressed_est <= target_tokens:
                    break
        else:
            result = self._apply_stages(
                [copy.copy(m) for m in messages],
                iteration,
                _DEFAULT_HISTORY_KEEP,
                _DEFAULT_TOOL_RESULT_CAP,
            )

        return result

    def _apply_stages(
        self,
        messages: list[dict],
        iteration: int,
        history_keep: int,
        tool_result_cap: int,
    ) -> list[dict]:
        """Apply all 3 compression stages."""
        # Stage 1: System prompt condensing
        if iteration >= 2 and messages and messages[0].get("role") == "system":
            condensed = self._get_condensed_system()
            original = messages[0]["content"]
            # Preserve user_context and entity_context from original
            user_ctx = _extract_section(original, "## User context")
            entity_ctx = _extract_section(original, "## Entity context")
            if user_ctx:
                condensed = condensed.replace("{{user_context}}", user_ctx)
            if entity_ctx:
                condensed = condensed.replace("{{entity_context}}", entity_ctx)
            messages[0] = {**messages[0], "content": condensed}

        # Stage 2: History truncation
        messages = self._truncate_history(messages, history_keep)

        # Stage 3: Tool result truncation
        for i, msg in enumerate(messages):
            if msg.get("role") == "tool":
                content = msg.get("content", "")
                if len(content) > tool_result_cap:
                    trimmed = content[:tool_result_cap]
                    removed = len(content) - tool_result_cap
                    messages[i] = {
                        **msg,
                        "content": f"{trimmed}\n... [{removed} chars truncated]",
                    }

        return messages

    def _truncate_history(
        self,
        messages: list[dict],
        keep_turns: int,
    ) -> list[dict]:
        """Remove old user/assistant history turns, keep loop messages.

        Loop messages are identified by finding the last user message
        that is followed by tool messages (indicating the current request).
        History = user/assistant pairs before the current query.
        """
        # Find boundary: last user message followed by tool activity
        boundary = self._find_loop_boundary(messages)
        if boundary <= 0:
            return list(messages)

        # Split: system | history | current+loop
        system: list[dict] = []
        idx = 0
        while idx < boundary and messages[idx].get("role") == "system":
            system.append(messages[idx])
            idx += 1

        history = messages[idx:boundary]
        current_and_loop = messages[boundary:]

        # Keep only last N turn pairs from history
        turns: list[list[dict]] = []
        current_turn: list[dict] = []
        for msg in history:
            current_turn.append(msg)
            if msg.get("role") == "assistant":
                turns.append(current_turn)
                current_turn = []
        if current_turn:
            turns.append(current_turn)

        kept_turns = turns[-keep_turns:] if keep_turns > 0 else []
        kept_history: list[dict] = []
        for turn in kept_turns:
            kept_history.extend(turn)

        if len(history) != len(kept_history):
            logger.debug(
                "History truncated: %d → %d messages (%d turns kept)",
                len(history),
                len(kept_history),
                len(kept_turns),
            )

        return system + kept_history + current_and_loop

    @staticmethod
    def _find_loop_boundary(messages: list[dict]) -> int:
        """Find index of the HumanMessage starting the current request.

        The boundary is the last user message that is followed by
        tool messages (indicating the agentic loop has started).
        """
        human_idxs: list[int] = []
        tool_idxs: list[int] = []
        for i, msg in enumerate(messages):
            if msg.get("role") == "user" and "tool_call_id" not in msg:
                human_idxs.append(i)
            elif msg.get("role") == "tool":
                tool_idxs.append(i)

        if not human_idxs:
            return 0

        last_human = human_idxs[-1]

        # If tools exist after last human, that's the boundary
        if any(t > last_human for t in tool_idxs):
            return last_human

        # Check second-to-last human message
        if len(human_idxs) >= 2:
            prev_human = human_idxs[-2]
            if any(t > prev_human for t in tool_idxs):
                return prev_human

        return last_human


def _extract_section(text: str, heading: str) -> str | None:
    """Extract content after a heading until the next heading or EOF."""
    idx = text.find(heading)
    if idx == -1:
        return None
    start = idx + len(heading)
    next_heading = text.find("\n## ", start)
    if next_heading == -1:
        return text[start:].strip()
    return text[start:next_heading].strip()
