# Project State

## Current Phase
- Phase 7+ backlog items remain (KAN board has 6 open tickets)
- **Implement-local hybrid workflow: FIRST TRIAL COMPLETE**

## Resume Point
- Pick next JIRA ticket from remaining 6 (KAN-152, 155, 157, 162, 176, 186)
- Score task for local LLM triage (CLAUDE.md step 8 — mandatory)
- If score ≤8, present to user for `/implement-local` delegation

## Implement-Local Workflow Status
- **MCP bridge server:** `tools/lmstudio-bridge/server.py` — now returns `{result, finish_reason, truncated, usage}` (gitignored)
- **Skill:** `~/.claude/commands/implement-local.md` — updated with branch guard, known pitfalls, truncation detection
- **CLAUDE.md:** Step 8 added — mandatory local LLM triage before implementing
- **First trial results:** DeepSeek 16B produced ~70% correct code, 5 convention violations fixed. Logged to `metrics/implement-local-log.jsonl`
- **Prompt improvements applied:** 6 known-pitfall rules (snake_case keys, modern types, complete file output, no commentary, minimal null checks, match neighbor patterns)
- **Model:** DeepSeek Coder V2 Lite Instruct (16B, Q4_K_M) — 128k context window, 8192 max output tokens
- **Hardware:** M4 Pro 48GB — 10GB model leaves 32GB free

## Key Decisions
- Opus = architect/reviewer, local LLM = implementor
- 3-dimension complexity scoring (context_span + convention_density + ambiguity)
- Score ≤8 → local, 9-11 → warn, 12+ → Opus only
- Up to 3 retry loops with specific error feedback
- Observability: JSONL log + markdown dashboard, self-improving prompts

## Last Session (66)
- KAN-156 closed as superseded — short interest added to StockIntelligenceTool (PR #135 merged)
- Files changed: intelligence.py, stock_intelligence.py, intelligence schema, stocks/data.py router, tests
- Implement-local skill hardened: branch guard, known pitfalls, truncation detection
- CLAUDE.md updated with local LLM triage step
- 6 open JIRA tickets remain

## Test Counts
- ~1053 total tests (+3 new short interest tests)
- Alembic head: `1a001d6d3535` (migration 014)

## Branch
- `develop` — PR #135 merged