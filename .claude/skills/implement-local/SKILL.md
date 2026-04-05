---
name: implement-local
description: Implement a task using a local LLM as full Claude Code agent. Opus reviews output.
disable-model-invocation: true
argument-hint: "[task-description or KAN-XXX]"
effort: medium
---

# Implement via Ollama — $ARGUMENTS

## Prerequisites Check

Run this check before proceeding:
```bash
curl -s http://localhost:11434/api/tags | python3 -c "
import sys, json
models = json.load(sys.stdin)['models']
coder = [m for m in models if 'coder' in m['name']]
if not coder:
    print('ERROR: No coder model. Run: ollama pull qwen2.5-coder:14b')
    sys.exit(1)
print(f'Ollama ready: {coder[0][\"name\"]} ({coder[0][\"size\"]/(1<<30):.1f} GB)')
"
```

If Ollama is not running or no coder model found, inform the user and abort.

## Step 1: Prepare Task Prompt

Construct a focused prompt for the local model:

1. If `$ARGUMENTS` starts with `KAN-`: fetch the JIRA ticket description
2. Otherwise, use `$ARGUMENTS` as the task description
3. Include these context items in the prompt:
   - The specific files to modify (identify from task description)
   - Relevant project conventions from CLAUDE.md (cherry-pick, don't dump the whole file)
   - The test command to verify: `uv run pytest tests/unit/ -q --tb=short`
   - The lint command to verify: `ruff check --fix && ruff format`

Format the prompt as:
```
You are working on the stock-signal-platform project.

TASK: [task description]

FILES TO MODIFY: [list specific files]

CONVENTIONS:
- [relevant conventions only]

AFTER IMPLEMENTING:
1. Run: uv run pytest tests/unit/ -q --tb=short
2. Run: ruff check --fix && ruff format
3. Fix any failures before finishing

Reply with a summary of what you changed.
```

## Step 2: Execute via Ollama

Run the local model as a full Claude Code agent:

```bash
ANTHROPIC_AUTH_TOKEN=ollama ANTHROPIC_BASE_URL=http://localhost:11434 ANTHROPIC_API_KEY="" \
  claude -p "$PROMPT" \
  --model qwen2.5-coder:14b \
  --yes \
  --output-format json \
  2>&1
```

Capture the JSON output. Extract:
- `result` — the model's summary
- `duration_ms` — wall clock time
- `usage.input_tokens` / `usage.output_tokens` — token counts
- `num_turns` — number of tool-use rounds

## Step 3: Opus Review

Review the local model's changes:

1. Run `git diff` to see what changed
2. Run `uv run pytest tests/unit/ -q --tb=short` — verify tests pass
3. Run `ruff check` — verify lint clean
4. Review the diff for:
   - Convention violations (CLAUDE.md rules)
   - Security issues (Rule #10: no str(e))
   - Integration safety (correct imports, no circular deps)
   - Over-engineering (YAGNI)

If issues found:
- Fix them directly (Opus corrects the local model's work)
- Note what was fixed for the metrics log

## Step 4: Log Metrics

Append one JSON line to `metrics/implement-local-log.jsonl`:

```json
{
  "timestamp": "[ISO 8601]",
  "task_id": "[KAN-XXX or description]",
  "task_title": "[short title]",
  "model": "qwen2.5-coder:14b",
  "complexity": {
    "context_span": N, "reasoning_depth": N, "integration_surface": N,
    "pattern_novelty": N, "implicit_knowledge": N, "verifiability": N,
    "failure_cost": N, "capability_score": N, "risk_score": N
  },
  "duration_ms": N,
  "input_tokens": N,
  "output_tokens": N,
  "tps": N,
  "num_turns": N,
  "tests_passed": true/false,
  "lint_clean": true/false,
  "opus_fixes": ["list of issues Opus corrected"],
  "final_verdict": "pass/fail",
  "files_modified": ["list"]
}
```

## Step 5: Present Summary

Present to the user:
- What the local model implemented
- What Opus fixed (if anything)
- Metrics summary (time, tokens, verdict)
- "Changes ready. Review the diff and commit when satisfied."
