---
name: Benchmarking models
description: Runs a coding task across Sonnet 4.6, MiniMax M2.5, and Qwen3-32B in
  parallel worktrees, collects cost/quality/speed metrics, and produces an Opus blind review
triggers: ["benchmark", "model comparison", "compare models", "run benchmark"]
---

# Benchmark Skill

Run a coding task across multiple LLM models and compare results.

## Usage

```bash
# Single task
uv run python3 -m benchmark.harness --task benchmark/tasks/t1_001_example.yaml

# All tasks
uv run python3 -m benchmark.harness --batch benchmark/tasks/

# Regenerate reports from existing data
uv run python3 -m benchmark.harness --report
```

## Prerequisites

1. API keys in `backend/.env`: `ANTHROPIC_API_KEY`, `MINIMAX_API_KEY`, `GROQ_API_KEY`
2. For Groq: start LiteLLM proxy first: `litellm --config benchmark/litellm-config.yaml --port 4000`
3. Install deps: `pip install httpx pyyaml` (NOT in project venv)

## What happens

1. Creates 3 git worktrees from develop (one per model)
2. Runs Claude Code in each worktree in parallel
3. Collects: tokens, cost, time, test results, lint results, git diff
4. Opus blind review: scores quality + estimates staff engineer fix burden
5. Logs to `benchmark/results/all_runs.jsonl`
6. Generates per-task markdown report
7. Offers to PR the winner to develop
8. Cleans up all worktrees

## Reports

- Per-task: `benchmark/results/reports/{run_id}.md`
- Failure analysis: `benchmark/results/reports/failure-analysis.md`
- CTO brief: `benchmark/results/reports/cto-decision-brief.md`
- Enterprise: `benchmark/results/reports/enterprise-readiness.md`
