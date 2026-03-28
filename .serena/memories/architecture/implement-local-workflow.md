# Implement-Local Hybrid Workflow

## Architecture
Opus (Claude Code) orchestrates; local LLM (LM Studio) implements code.
MCP bridge server (`tools/lmstudio-bridge/server.py`) is a thin HTTP pipe.

## Components
- `tools/lmstudio-bridge/server.py` — FastMCP server, 3 tools: generate, list_models, health
- `~/.claude/commands/implement-local.md` — skill with 5 phases: ASSESS → CONSTRUCT → IMPLEMENT → REVIEW → LOG
- `metrics/implement-local-log.jsonl` — per-task observability
- `metrics/implement-local-summary.md` — aggregated dashboard (regenerated every 5 tasks)

## Complexity Scoring
- context_span (1-5) + convention_density (1-5) + ambiguity (1-5) = total
- ≤8 → local LLM, 9-11 → warn (allow --force), 12+ → Opus only
- Thresholds are adaptive based on observability data

## Key Design Choices
- MCP server catches `httpx.HTTPError` (covers ConnectError via inheritance)
- 300s timeout on generate (16B model on M4 Pro needs 60-120s for 8K tokens)
- Skill cherry-picks conventions per task (not full CLAUDE.md dump)
- Feedback loop: up to 3 retries with specific error messages
- All files gitignored — zero repo footprint

## MCP Registration
- User scope in `~/.claude.json` (not settings.local.json — that doesn't support mcpServers)
- Command: `uv run --directory .../tools/lmstudio-bridge python server.py`
- Requires Claude Code restart after registration

## Spec & Plan
- Spec: `docs/superpowers/specs/2026-03-28-implement-local-hybrid-workflow-design.md`
- Plan: `docs/superpowers/plans/2026-03-28-implement-local-hybrid-workflow-plan.md`
