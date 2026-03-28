# Project State

## Current Phase
- Phase 7+ backlog items remain (KAN board has ~10 open tickets)
- **Implement-local hybrid workflow: BUILT, awaiting live test**

## Resume Point
- Restart Claude Code to connect `lmstudio-bridge` MCP server
- Verify `mcp__lmstudio-bridge__health()` works
- Pick an easy JIRA ticket (score ~4-5), create `test/implement-local-trial-1` branch
- Run `/implement-local KAN-xxx` for first real end-to-end test
- Log first metrics entry to `metrics/implement-local-log.jsonl`

## Implement-Local Workflow Status
- **MCP bridge server:** Built at `tools/lmstudio-bridge/server.py` (gitignored)
- **Skill:** `~/.claude/commands/implement-local.md` (global, outside repo)
- **MCP registration:** `~/.claude.json` user scope, needs restart to connect
- **Spec:** `docs/superpowers/specs/2026-03-28-implement-local-hybrid-workflow-design.md` (gitignored)
- **Plan:** `docs/superpowers/plans/2026-03-28-implement-local-hybrid-workflow-plan.md` (gitignored)
- **Metrics dir:** `metrics/` created, empty
- **Model:** DeepSeek Coder V2 Lite Instruct (16B, Q4_K_M) on LM Studio at 127.0.0.1:1234
- **Hardware:** M4 Pro 48GB — 10GB model leaves 32GB free
- **Smoke test result:** Model follows conventions when explicitly told. Needs rich context prompts.
- Spec verified against implementation: 31/31 checks pass

## Key Decisions
- Opus = architect/reviewer, local LLM = implementor
- 3-dimension complexity scoring (context_span + convention_density + ambiguity)
- Score ≤8 → local, 9-11 → warn, 12+ → Opus only
- Up to 3 retry loops with specific error feedback
- Observability: JSONL log + markdown dashboard, self-improving prompts

## Test Counts
- ~1050 total tests (806 unit + ~180 API + 7 e2e + 24 integration + 107 frontend)
- Alembic head: `1a001d6d3535` (migration 014)

## Branch
- `develop` (no feature branch needed — all implement-local files are gitignored)
- Only `.gitignore` itself was modified (added gitignore entries for local tooling)
