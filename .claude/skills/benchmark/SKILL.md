---
name: benchmarking-models
description: Runs side-by-side benchmark comparing local LLM vs Sonnet on a JIRA task. Opus judges quality and generates a comparison report. Use when user says "benchmark", "compare models", "test local vs cloud", or "run benchmark on KAN-XXX".
disable-model-invocation: true
argument-hint: "KAN-XXX"
effort: high
---

# Benchmark — $ARGUMENTS

## Context
- Current branch: !`git branch --show-current`
- Ollama status: !`curl -s http://localhost:11434/api/tags 2>/dev/null`

## Prerequisites

1. Ollama must be running with qwen2.5-coder:14b loaded
2. `$ARGUMENTS` must be a JIRA ticket key (KAN-XXX)
3. Working tree must be clean (`git status` shows no uncommitted changes)

If any prerequisite fails, inform the user and abort.

## Step 1: Fetch Task & Score Complexity

1. Fetch JIRA ticket `$ARGUMENTS` — get summary, description, acceptance criteria
2. Score the 7 complexity dimensions (each 1-5):
   - **context_span**: How many files must be read/edited?
   - **reasoning_depth**: How many logical steps from problem to solution?
   - **integration_surface**: How many existing interfaces must the change conform to?
   - **pattern_novelty**: Is there an existing example to copy in the codebase?
   - **implicit_knowledge**: Domain knowledge NOT in the codebase?
   - **verifiability**: Can the model self-check via tests?
   - **failure_cost**: What happens if the model gets it wrong?
3. Calculate: capability_score (first 4, max 20), risk_score (last 3, max 15)
4. Determine tier: T1 (cap ≤5), T2 (cap 6-10), T3 (cap 11-15), T4 (cap 16+)
5. Present scores and tier to user. Proceed on confirmation.

## Step 2: Prepare Task Prompt

Construct a prompt that BOTH models will receive identically:

```
You are working on the stock-signal-platform project (FastAPI + Next.js).

JIRA TICKET: $ARGUMENTS
TITLE: [ticket title]
DESCRIPTION: [ticket description]
ACCEPTANCE CRITERIA: [from ticket]

PROJECT CONVENTIONS (must follow):
- Python: async by default, no str(e) in user-facing output, uv only
- Testing: test every public function, pytest
- Lint: ruff check + ruff format, zero errors
- Git: don't commit .env or secrets

AFTER IMPLEMENTING:
1. Run: uv run pytest tests/unit/ -q --tb=short
2. Run: ruff check --fix && ruff format
3. Verify all tests pass and lint is clean
4. Summarize what you changed
```

**CRITICAL:** Both models must receive the EXACT same prompt. No model-specific hints.

## Step 3: Create Worktrees

```bash
# Create two isolated worktrees from current develop HEAD
git worktree add ../bench-local-$ARGUMENTS develop
git worktree add ../bench-sonnet-$ARGUMENTS develop
```

## Step 4: Execute Both Models (Parallel)

Launch both in parallel. Neither should block the other.

**Worktree A — Local (Ollama):**
```bash
cd ../bench-local-$ARGUMENTS && \
ANTHROPIC_AUTH_TOKEN=ollama ANTHROPIC_BASE_URL=http://localhost:11434 ANTHROPIC_API_KEY="" \
  claude -p "$PROMPT" \
  --model qwen2.5-coder:14b \
  --yes \
  --output-format json \
  > /tmp/bench-local-$ARGUMENTS.json 2>&1
```

**Worktree B — Sonnet (API):**
```bash
cd ../bench-sonnet-$ARGUMENTS && \
  claude -p "$PROMPT" \
  --model sonnet \
  --yes \
  --output-format json \
  > /tmp/bench-sonnet-$ARGUMENTS.json 2>&1
```

Wait for both to complete.

## Step 5: Collect Tier 1 Metrics (Automated)

Run in EACH worktree:

```bash
# Tests
cd ../bench-{local|sonnet}-$ARGUMENTS
uv run pytest tests/unit/ -q --tb=short 2>&1 | tail -5

# Lint
ruff check --output-format json 2>&1

# Type check (delta from baseline)
# pyright --outputjson 2>&1 | python3 -c "..." (count new errors)

# Security scan
semgrep --config .semgrep/ --json 2>&1

# Diff stats
git diff --stat
git diff  # full diff for judge
```

Collect all results into structured JSON.

## Step 6: Opus-as-Judge (Tier 2)

Read the judge prompt template from `tools/benchmark/judge-prompt.md`.

Fill in the template with:
- Task description and acceptance criteria
- Both diffs (from git diff in each worktree)
- Both test results
- Both lint results
- Execution metrics from the JSON outputs

Send to Opus for evaluation. Parse the structured JSON response.

## Step 7: Generate Report

Use `tools/benchmark/report.py` to generate:
1. Per-task markdown report → `metrics/benchmark-reports/$ARGUMENTS-YYYY-MM-DD.md`
2. Append structured results → `metrics/benchmark-results.jsonl`

Present the report summary to the user.

## Step 8: Cleanup

```bash
# Remove worktrees
git worktree remove ../bench-local-$ARGUMENTS --force
git worktree remove ../bench-sonnet-$ARGUMENTS --force
rm -f /tmp/bench-local-$ARGUMENTS.json /tmp/bench-sonnet-$ARGUMENTS.json
```

If the user wants to keep a worktree (e.g., to merge the winning implementation):
"Keep a worktree? (local/sonnet/neither)"
