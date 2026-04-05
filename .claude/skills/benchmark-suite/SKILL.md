---
name: benchmark-suite
description: Run full benchmark suite across multiple JIRA tickets. Generates aggregate CTO assessment report with quality-by-tier analysis.
disable-model-invocation: true
argument-hint: "[KAN-XXX KAN-YYY ...] or [T1 T2 T3 T4]"
effort: high
---

# Benchmark Suite — $ARGUMENTS

## Context
- Current branch: !`git branch --show-current`
- Existing results: !`wc -l metrics/benchmark-results.jsonl 2>/dev/null || echo "0 (no results yet)"`

## Your Task

Run `/benchmark` for each ticket, then generate an aggregate CTO assessment report.

### Step 1: Resolve Ticket List

If `$ARGUMENTS` contains KAN-XXX ticket keys, use those directly.

If `$ARGUMENTS` contains tier labels (T1, T2, T3, T4), query JIRA and select tickets per tier:

| Tier | Capability Score | Ticket Selection |
|------|-----------------|------------------|
| T1 | ≤ 5 | Pick 3 simplest open tickets |
| T2 | 6-10 | Pick 3 scoped bug fixes |
| T3 | 11-15 | Pick 3 multi-file tasks |
| T4 | 16+ | Pick 2 complex stories |

```
project = KAN AND status != Done ORDER BY rank ASC
```

Present the selected tickets with complexity scores for approval before proceeding.

### Step 2: Sequential Execution

Run `/benchmark KAN-XXX` for each ticket sequentially (local model can only handle one task at a time due to GPU memory).

Between each run:
- Confirm the previous run completed successfully
- Present a running tally: "Completed 3/11 benchmarks. Local wins: 1, Sonnet wins: 2, Ties: 0"

### Step 3: Aggregate Analysis

After all benchmarks complete, read `metrics/benchmark-results.jsonl` and generate:

#### 3a: Quality Matrix (Pass Rate by Tier)

```markdown
| Tier | Local Pass Rate | Sonnet Pass Rate | Quality Gap | Avg Local Time | Avg Sonnet Time |
|------|----------------|-----------------|-------------|----------------|-----------------|
| T1   | X%             | Y%              | Z%          | Ns             | Ns              |
| T2   | ...            | ...             | ...         | ...            | ...             |
| T3   | ...            | ...             | ...         | ...            | ...             |
| T4   | ...            | ...             | ...         | ...            | ...             |
```

#### 3b: Cost Comparison

Calculate per-tier and total:
- Local cost: $0 (local inference)
- Sonnet cost: sum of API costs from JSON outputs
- Projected monthly savings at 1/3/5/10 developers

#### 3c: Performance Metrics

- Average TPS (output tokens / generation time)
- Average TPM
- Prompt processing overhead (time before first output token)

#### 3d: Opus Judge Summary

Aggregate the 6 quality dimensions across all tasks:
- Average score per dimension (local vs sonnet)
- Dimensions where local performs worst (biggest gaps)
- Dimensions where local is competitive

#### 3e: Scaling Prediction

If 70B results are available, plot the quality curve. Otherwise note:
"Phase 4 (Cloud-70B via Ollama API) needed for scaling prediction."

### Step 4: Generate CTO Brief

Write the aggregate report to `metrics/benchmark-reports/aggregate-YYYY-MM-DD.md` using the format from spec section 9.

Present the executive summary to the user.

### Step 5: Recommendations

Based on the data, generate:
1. Which task tiers are viable for local LLM
2. Estimated monthly savings per team size
3. Hardware recommendation (stay with current, upgrade, or use cloud API)
4. Next steps (Phase 4 with 70B, Phase 5 with AWS, or conclusion)
