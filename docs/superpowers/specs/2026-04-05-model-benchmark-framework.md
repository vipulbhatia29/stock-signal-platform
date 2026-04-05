# Model Benchmark Framework — Spec

**Date:** 2026-04-05
**Status:** Draft
**Goal:** One-shot benchmark comparing Sonnet 4.6 vs MiniMax M2.5 vs Qwen3-32B (Groq) on real JIRA tasks. Every task advances the application build. Winner's code gets merged.

---

## Problem Statement

Opus is reserved for planning/review. We need the cheapest model that can implement routine coding tasks at Sonnet-level quality within Claude Code's agentic workflow. The benchmark must:

1. Compare 3 models on real codebase tasks (not throwaway)
2. Collect granular cost/quality/speed metrics per task
3. Determine the capability ceiling of each model by tier
4. Produce a CTO-ready decision: "Use Model X for Y% of tasks, save Z%"
5. Merge the best implementation into develop — no wasted work

---

## Model Setup

### Sonnet 4.6 (baseline — direct Anthropic API)
```bash
ANTHROPIC_BASE_URL=https://api.anthropic.com   # default, no change
ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY            # existing key
claude --model claude-sonnet-4-6
```
- **Pricing:** $3.00/M input, $15.00/M output
- **Max output:** 128K tokens
- **Context:** 200K

### MiniMax M2.5 (direct Anthropic-compatible API — VALIDATED)
```bash
ANTHROPIC_BASE_URL=https://api.minimax.io/anthropic
ANTHROPIC_API_KEY=$MINIMAX_API_KEY
claude --model MiniMax-M2.5
```
- **Pricing:** $0.30/M input, $1.20/M output
- **Max output:** 64K tokens
- **Context:** 200K
- **Smoke test passed:** 2026-04-05. Tool use, Anthropic format, stop_reason all correct.

### Qwen3-32B (Groq via LiteLLM proxy)
```bash
# Terminal 1: Start LiteLLM
litellm --config benchmark/litellm-config.yaml --port 4000

# Terminal 2: Run Claude Code
ANTHROPIC_BASE_URL=http://localhost:4000
ANTHROPIC_AUTH_TOKEN=$LITELLM_MASTER_KEY
claude --model qwen3-32b
```
- **Pricing:** $0.29/M input, $0.59/M output (Groq)
- **Max output:** 41K tokens
- **Context:** 131K
- **Requires:** LiteLLM proxy (Anthropic ↔ OpenAI translation)
- **Known risks:** `output_config` param issue (#22963), multi-turn tool use edge cases (#19061)
- **Smoke test:** NOT YET VALIDATED — must pass before first benchmark run

#### LiteLLM config (`benchmark/litellm-config.yaml`)
```yaml
model_list:
  - model_name: qwen3-32b
    litellm_params:
      model: groq/qwen/qwen3-32b
      api_key: os.environ/GROQ_API_KEY
      max_tokens: 40960

general_settings:
  master_key: sk-benchmark-local-key
```

#### Groq setup steps
1. Confirm `GROQ_API_KEY` is in `backend/.env` (already done)
2. Install LiteLLM: `pip install 'litellm[proxy]'` (NOT in project venv — global or separate venv)
3. Start proxy: `litellm --config benchmark/litellm-config.yaml --port 4000`
4. Smoke test — run from a separate terminal:
```bash
source backend/.env
ANTHROPIC_BASE_URL=http://localhost:4000 \
ANTHROPIC_AUTH_TOKEN=sk-benchmark-local-key \
claude -p "What is 2+2? Reply with just the number." \
  --model qwen3-32b --output-format json --max-turns 1 2>/dev/null \
| python3 -c "import sys,json; d=json.loads(sys.stdin.read()); print(json.dumps({
    'result': d.get('result'),
    'is_error': d.get('is_error'),
    'tokens': d.get('usage',{}).get('input_tokens',0) + d.get('usage',{}).get('output_tokens',0),
    'cost_reported': d.get('total_cost_usd')
}, indent=2))"
```
5. **Expected output:** `result` contains "4", `is_error` is false, tokens > 0
6. **If `output_config` error (#22963):** Try adding to litellm config:
```yaml
litellm_settings:
  drop_params: true   # drops unsupported params instead of erroring
```
7. **If still fails:** Drop Qwen3-32B from benchmark, proceed with Sonnet vs MiniMax only. Log the failure as a data point ("proxy pattern not yet production-ready for Groq").

#### Groq free tier limits to monitor
- 30 requests/min, 14,400 requests/day
- ~500K tokens/day (model-dependent)
- If rate-limited mid-task: Claude Code will get an error, `is_error` will be true
- Mitigation: add 30-second delay between Qwen3 tasks if needed

### Opus 4.6 (judge — NOT benchmarked)
```bash
# Used only for blind review. Direct Anthropic API.
ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY
# Called from harness.py, not Claude Code
```
- **Pricing:** $5.00/M input, $25.00/M output

---

## Critical Metric Collection Guarantee

**VERIFIED:** Claude Code `--output-format json` returns these fields for ALL providers:

| Field | Source | Verified |
|---|---|---|
| `usage.input_tokens` | Model response header | Yes (Sonnet + MiniMax) |
| `usage.output_tokens` | Model response header | Yes (Sonnet + MiniMax) |
| `duration_ms` | Claude Code wall clock | Yes |
| `duration_api_ms` | API call time only | Yes |
| `num_turns` | Conversation turns | Yes |
| `result` | Final text output | Yes |
| `is_error` | Success/failure | Yes |
| `total_cost_usd` | **WRONG for non-Anthropic** | Uses Sonnet pricing |

**IMPORTANT:** `total_cost_usd` applies Sonnet's pricing to all models regardless of provider. We MUST calculate real cost:

```python
PRICING = {
    "claude-sonnet-4-6":  {"input": 3.00,  "output": 15.00},
    "MiniMax-M2.5":       {"input": 0.30,  "output": 1.20},
    "qwen3-32b":          {"input": 0.29,  "output": 0.59},
    "claude-opus-4-6":    {"input": 5.00,  "output": 25.00},
}

def real_cost(model_id, input_tokens, output_tokens):
    p = PRICING[model_id]
    return (input_tokens * p["input"] + output_tokens * p["output"]) / 1_000_000
```

**Additional metrics collected post-run (not from Claude Code):**
- `pytest` exit code + pass/fail count → run in worktree after agent completes
- `ruff check --statistics` → lint violation count
- `git diff --stat` → files changed, lines added/removed
- `wc -l` on changed files → lines of code

---

## Task Design — Real JIRA Work

### Selection criteria
- Tasks from Phase E (UI Overhaul) or Phase F (Subscriptions) backlog
- Each task must be self-contained (completable without other tasks)
- Each task must be testable (has a clear pass/fail via pytest or manual check)
- Mix of tiers to find the capability ceiling

### Task tiers (3 tasks each = 12 total)

| Tier | Complexity | Example | What it tests |
|---|---|---|---|
| **T1: Surgical** | 1-2 files, <50 LOC | Add field to Pydantic model + test | Targeted edit, convention adherence |
| **T2: Single-feature** | 2-4 files, 50-150 LOC | New service function + endpoint + tests | Pattern following, integration |
| **T3: Multi-file** | 4-6 files, 150-300 LOC | New page + API hook + backend route | Cross-layer coordination |
| **T4: Refactor** | 5+ files, modify existing | Extract shared logic, update callers | Codebase understanding, safety |

### Task YAML format

```yaml
id: "bench_001"
jira_ticket: "KAN-XXX"
tier: "T1"
name: "Add subscription tier field to User model"
description: |
  Add a `subscription_tier` enum field (free/pro/enterprise) to the User model.
  Include Alembic migration, update UserResponse schema, add unit test.
requirements:
  - Add SubscriptionTier enum (free, pro, enterprise) to backend/models/
  - Add nullable subscription_tier column to users table
  - Alembic migration with safe default (free)
  - Update UserResponse Pydantic schema
  - Unit test for enum values and default
acceptance_criteria:
  - pytest tests/unit/test_user_model.py passes
  - ruff check passes with zero violations
  - alembic upgrade head succeeds
files_likely_touched:
  - backend/models/user.py
  - backend/schemas/user.py
  - backend/migrations/versions/
  - tests/unit/
context: |
  Follow existing enum patterns (see UserRole in backend/models/user.py).
  Migration must NOT drop TimescaleDB indexes (known Alembic gotcha).
```

### Task Complexity Scoring (pre-benchmark, per task)

Every task YAML includes a complexity score computed BEFORE the benchmark runs. This lets us correlate model performance against objective complexity — not just tier labels.

#### 7 complexity dimensions (each scored 1-5)

| Dimension | 1 (trivial) | 3 (moderate) | 5 (hard) |
|---|---|---|---|
| **Context span** | Single file, self-contained | 2-3 files, one module | 5+ files across modules |
| **Reasoning depth** | Copy a pattern | Adapt a pattern to new context | Design a new approach |
| **Integration surface** | No existing code touched | Modify 1-2 existing functions | Modify interfaces used by multiple callers |
| **Convention density** | Generic Python (any style OK) | Must follow 2-3 project patterns | Must follow async + DB + test + naming conventions |
| **Implicit knowledge** | Requirements fully explicit | Needs to read 1-2 existing files to understand pattern | Needs to understand cross-cutting concerns (auth, caching, etc.) |
| **Verification difficulty** | Pass/fail via single pytest | Multiple test files + lint | Requires integration test or manual verification |
| **Failure cost** | Wrong output is harmless | Bug affects one feature | Bug could break auth, data integrity, or migrations |

**Composite complexity score:** Sum of all 7 dimensions (range: 7-35)

| Score range | Tier mapping | Description |
|---|---|---|
| 7-12 | T1 (Surgical) | Any competent model should handle this |
| 13-18 | T2 (Single-feature) | Needs pattern awareness and convention following |
| 19-25 | T3 (Multi-file) | Needs codebase understanding and coordination |
| 26-35 | T4 (Refactor) | Needs deep reasoning and integration safety |

#### Example scoring

```yaml
# Task: Add subscription_tier enum to User model
complexity:
  context_span: 2          # 3 files (model, schema, migration)
  reasoning_depth: 1       # Copy existing UserRole enum pattern
  integration_surface: 2   # Modify User model, add migration
  convention_density: 3    # Must follow enum pattern + Alembic gotchas
  implicit_knowledge: 2    # Needs to know TimescaleDB index gotcha
  verification_difficulty: 2  # pytest + alembic upgrade
  failure_cost: 3          # Bad migration could break DB
  total: 15                # → T2
```

#### Opus post-hoc complexity assessment

After reviewing all implementations, Opus ALSO scores the task's actual complexity. This catches cases where a task was harder/easier than anticipated:

```json
{
  "pre_score": 15,
  "post_score": 18,
  "adjustment_reason": "Task required understanding the CachedUser pattern which wasn't in the requirements — implicit knowledge was underscored"
}
```

The delta between pre-score and post-score tells us how well we calibrate task definitions.

#### Complexity metrics Opus reports per implementation

Beyond the 6 quality dimensions, Opus reports these complexity-aware observations:

| Metric | Type | What it captures |
|---|---|---|
| `required_codebase_reads` | count | How many existing files the model needed to read to succeed |
| `convention_violations` | list | Specific project patterns the model got wrong |
| `hallucinated_apis` | count | Non-existent functions/imports the model invented |
| `over_engineering_score` | 1-5 | Did the model add unnecessary abstraction? (1=lean, 5=massively over-built) |
| `under_engineering_score` | 1-5 | Did the model skip error handling, types, edge cases? (1=thorough, 5=bare minimum) |
| `self_correction_attempts` | count | How many times the model fixed its own errors |
| `self_correction_success_rate` | pct | Of those attempts, how many actually fixed the issue? |
| `dead_end_tools` | count | Tool calls that produced no useful result (wasted turns) |
| `codebase_awareness` | 1-5 | Did the model understand existing patterns or code from scratch? |

These feed into the Failure Pattern Analysis (Report 2) and the CTO Decision Brief (Report 3).

#### Updated Opus judge prompt addition

The judge prompt includes this section for each implementation:

```
## Complexity Assessment for {implementation}
In addition to quality scores, assess:
- required_codebase_reads: How many existing files did this implementation need to reference?
- convention_violations: List specific project conventions violated (async, naming, file structure, test patterns)
- hallucinated_apis: Count of non-existent functions, imports, or modules referenced
- over_engineering_score: 1-5 (1=appropriate complexity, 5=massively over-built for the task)
- under_engineering_score: 1-5 (1=thorough, 5=skipped critical error handling/types/edge cases)
- self_correction_attempts: How many error-fix cycles visible in the conversation?
- self_correction_success_rate: What percentage of fix attempts actually resolved the issue?
- dead_end_tools: Tool calls that produced no useful progress
- codebase_awareness: 1-5 (1=codes from scratch ignoring existing patterns, 5=deeply aware of codebase)
- post_complexity_score: Your assessment of actual task complexity (7-35 scale, same dimensions as pre-score)
- post_complexity_reason: Why you scored it differently from the pre-score (if applicable)
```

### No progressive elimination

All 3 models run on all 12 tasks. With only 12 data points, eliminating a model early would weaken the statistical validity of the results. The extra cost of running all 3 (~$2-3 more than a 2-model run) is worth having a complete dataset where every model has 12 data points across all 4 tiers.

---

## Quantitative Metrics (Automatic — Zero Human Input)

Collected per model per task:

| Metric | Source | Formula |
|---|---|---|
| `input_tokens` | Claude Code JSON `.usage.input_tokens` | raw |
| `output_tokens` | Claude Code JSON `.usage.output_tokens` | raw |
| `actual_cost_usd` | Calculated | `tokens × provider_pricing` |
| `claude_reported_cost` | Claude Code JSON `.total_cost_usd` | raw (for audit) |
| `wall_clock_ms` | Claude Code JSON `.duration_ms` | raw |
| `api_time_ms` | Claude Code JSON `.duration_api_ms` | raw |
| `tokens_per_second` | Calculated | `output_tokens / (api_time_ms / 1000)` |
| `num_turns` | Claude Code JSON `.num_turns` | raw |
| `tests_total` | `pytest --tb=no -q` output | parse count |
| `tests_passed` | `pytest` exit code + output | parse count |
| `tests_failed` | `pytest` output | parse count |
| `lint_violations` | `ruff check --statistics` | parse count |
| `files_changed` | `git diff --stat` | parse count |
| `lines_added` | `git diff --numstat` | sum |
| `lines_removed` | `git diff --numstat` | sum |
| `is_error` | Claude Code JSON `.is_error` | raw boolean |

### Derived metrics (calculated in report)

| Metric | Formula | What it tells you |
|---|---|---|
| `cost_per_quality_point` | `actual_cost / weighted_score` | Efficiency |
| `test_pass_rate` | `tests_passed / tests_total` | Correctness |
| `first_pass_success` | `tests_passed == tests_total && lint == 0` | No-fix-needed |
| `cost_ratio_vs_sonnet` | `model_cost / sonnet_cost` | Savings multiplier |
| `speed_ratio_vs_sonnet` | `sonnet_time / model_time` | Speed multiplier |
| `quality_gap_vs_sonnet` | `sonnet_score - model_score` | Quality delta |
| `value_score` | `weighted_score / actual_cost` | Quality per dollar |

---

## Qualitative Metrics (Opus Blind Review)

### Protocol
1. Opus receives **anonymized** implementations (Implementation A, B, C)
2. No model names revealed until after scoring
3. Each implementation includes: code diff, test output, lint output
4. Opus scores independently, then ranks comparatively
5. Structured JSON response — no prose parsing

### Scoring rubric (6 dimensions)

| Dimension | Weight | 10 | 7 | 5 | 3 | 1 |
|---|---|---|---|---|---|---|
| **Correctness** | 25% | All requirements met, edge cases handled | Core logic correct, minor gaps | Mostly correct, some bugs | Significant errors | Fundamentally wrong |
| **Convention adherence** | 20% | Follows all project patterns (async, naming, file structure) | Minor deviations | Some pattern violations | Ignores conventions | Foreign style |
| **Integration safety** | 20% | Breaks nothing, proper imports, FK constraints | Safe with minor issues | One breaking change found | Multiple integration risks | Would break production |
| **Completeness** | 15% | All requirements + error handling + types | Core requirements met | Most requirements, gaps | Significant missing | Partial |
| **Code quality** | 10% | Clean, readable, right abstraction level | Good with minor issues | Functional but messy | Hard to read | No structure |
| **First-pass success** | 10% | Tests + lint pass on first run | Minor fix needed (typo, import) | One significant fix | Multiple fixes | Never achieved working state |

### Opus judge prompt (template)

```
You are an expert code reviewer evaluating three implementations of the same task.
Score each INDEPENDENTLY on the rubric below. Do not let one implementation bias
your scoring of another.

## Task
{task_description}

## Project conventions (relevant excerpt)
{claude_md_excerpt}

## Scoring rubric
{rubric_yaml}

## Implementation A
### Code changes
{diff_a}
### Test output
{test_output_a}
### Lint output
{lint_output_a}

## Implementation B
{...same structure...}

## Implementation C
{...same structure...}

Respond in JSON ONLY. No markdown. No preamble. Format:
{
  "implementations": {
    "A": {
      "scores": {"correctness": N, "convention_adherence": N, ...},
      "weighted_score": N.N,
      "specific_issues": ["..."],
      "strengths": ["..."],
      "would_need_rewrite": bool
    },
    "B": {...},
    "C": {...}
  },
  "ranking": ["A", "B", "C"],
  "winner": "A",
  "winner_rationale": "...",
  "comparative_notes": "..."
}
```

### Opus review cost estimate
- Input: ~5K (rubric + task) + ~3K per impl × 3 = ~14K tokens
- Output: ~1K tokens (JSON response)
- Cost per review: 14K × $5/M + 1K × $25/M = $0.07 + $0.025 = **~$0.10**
- 12 tasks: **~$1.20** total for judging

### Opus as Staff Engineer Proxy — Review Burden Metric

Opus doesn't just judge — it also **fixes**. After blind scoring, Opus does a second pass:
for each implementation, it produces the specific fixes needed to make the code merge-ready.
The volume and severity of those fixes quantify the "staff engineer cleanup cost."

#### Two-pass review protocol

**Pass 1 — Blind scoring** (described above)
Scores quality, identifies issues, ranks implementations.

**Pass 2 — Fix estimation** (per implementation)
Opus receives each implementation individually and produces:

```json
{
  "model": "(revealed after scoring)",
  "fix_actions": [
    {
      "file": "backend/models/user.py",
      "type": "bug",
      "severity": "high",
      "description": "Missing nullable=True on subscription_tier column",
      "estimated_fix_lines": 1,
      "estimated_fix_minutes": 2
    },
    {
      "file": "tests/unit/test_user.py",
      "type": "convention",
      "severity": "low",
      "description": "Test uses unittest.TestCase instead of bare pytest functions",
      "estimated_fix_lines": 15,
      "estimated_fix_minutes": 5
    }
  ],
  "fix_summary": {
    "total_actions": 2,
    "by_severity": {"critical": 0, "high": 1, "medium": 0, "low": 1},
    "by_type": {"bug": 1, "convention": 1, "missing_feature": 0, "security": 0, "over_engineering": 0},
    "total_fix_lines": 16,
    "total_fix_minutes": 7,
    "opus_fix_tokens": 850,
    "opus_fix_cost_usd": 0.025,
    "would_block_pr": true,
    "staff_engineer_equivalent_hours": 0.12
  }
}
```

#### Fix action types
| Type | Description | Staff engineer impact |
|---|---|---|
| `bug` | Logic error, wrong behavior | Must find and fix — high cognitive load |
| `convention` | Wrong pattern, naming, style | Tedious but mechanical — low cognitive load |
| `missing_feature` | Requirement not implemented | Must understand and implement — high load |
| `security` | Auth bypass, injection, data leak | Must catch AND fix correctly — highest load |
| `over_engineering` | Unnecessary abstraction, dead code | Must simplify — medium cognitive load |
| `test_gap` | Missing test case or assertion | Must write additional tests — medium load |

#### Fix severity levels
| Severity | Definition | PR impact |
|---|---|---|
| `critical` | Would break production, data loss, security hole | **Blocks PR** — must fix |
| `high` | Bug that affects functionality | **Blocks PR** — must fix |
| `medium` | Convention violation, missing edge case | Fix preferred, could ship with TODO |
| `low` | Style nit, minor improvement | Nice to have |

#### Derived review burden metrics

| Metric | Formula | What it tells the CTO |
|---|---|---|
| `total_fix_minutes` | Sum of all fix action estimates | Staff engineer time per task |
| `fix_minutes_per_month` | `fix_minutes × monthly_task_volume` | Monthly cleanup overhead |
| `staff_cost_per_task` | `fix_minutes / 60 × hourly_rate` | Dollar cost of human review |
| `pr_block_rate` | `tasks_with_blocking_fixes / total_tasks` | How often would this model's PR get rejected? |
| `opus_fix_tokens` | Tokens Opus used to describe fixes | Complexity proxy — more tokens = messier code |
| `opus_fix_cost_usd` | Real cost of the fix description | What it costs Opus to clean up after this model |
| `net_cost` | `impl_cost + opus_review_cost + staff_cleanup_cost` | TRUE total cost of using this model |
| `net_cost_vs_sonnet` | `model_net_cost / sonnet_net_cost` | Real savings after accounting for cleanup |

#### Staff engineer hourly rate (configurable)

```yaml
# In benchmark/config.yaml
staff_engineer:
  hourly_rate_usd: 95.00    # Median US senior SWE fully loaded
  review_overhead_pct: 0.20  # 20% overhead for context switching, PR review
```

This lets the CTO brief compute: "Using MiniMax saves $X on model costs but adds $Y in staff cleanup, for a net savings of $Z."

#### Opus fix pass cost estimate
- Input: ~3K (implementation) + ~2K (task context) = ~5K tokens per implementation
- Output: ~800 tokens (fix JSON)
- Cost per implementation: 5K × $5/M + 800 × $25/M = $0.025 + $0.020 = **~$0.045**
- Per task (3 implementations): **~$0.135**
- 12 tasks: **~$1.62** total for fix estimation
- Combined (scoring + fixes): **~$2.82** total Opus cost

---

## Worktree Management — Winner Takes All

### The problem
3 models implement the same task in 3 worktrees. Only one gets merged. Development must continue linearly on develop.

### The solution: Sequential task execution

```
For each task:
  1. git checkout develop && git pull
  2. Create 3 worktrees:
     - .benchmark/wt-sonnet    (from develop)
     - .benchmark/wt-minimax   (from develop)
     - .benchmark/wt-qwen      (from develop)
  3. Run 3 Claude Code agents IN PARALLEL (one per worktree)
  4. Collect metrics from all 3
  5. Run tests + lint in all 3 worktrees
  6. Opus blind review
  7. Winner determination:
     a. Any model with is_error=true or test_pass_rate=0 → disqualified
     b. Among remaining: highest weighted_score wins
     c. Ties broken by: cost_per_quality_point (lower wins)
  8. Winner's worktree → PR to develop (auto-created)
  9. User approves + merges PR
  10. Delete ALL 3 worktrees
  11. Next task starts from updated develop

Key: develop is always linear. Only one PR per task. No branching conflicts.
```

### What if no model produces passing code?
- Log the failure
- Skip the task (don't merge garbage)
- Move to next task
- The failure itself is benchmark data ("none could handle T4 refactors")

### What if the task modifies files that the next task also needs?
- Tasks run sequentially, winner merges first
- Next task starts from updated develop
- This tests real-world sequential development — not artificial isolation

---

## Budget Estimate

### Per-task cost (estimated)

Claude Code sends ~88K system prompt tokens per invocation (verified).

| Component | Sonnet | MiniMax | Qwen3 (Groq) | Opus (judge) |
|---|---|---|---|---|
| System prompt (88K input) | $0.264 | $0.026 | $0.026 | — |
| Task context (~20K input) | $0.060 | $0.006 | $0.006 | — |
| Code generation (~5K output) | $0.075 | $0.006 | $0.003 | — |
| Multi-turn overhead (3 turns avg, ~50K additional input) | $0.150 | $0.015 | $0.015 | — |
| Review (14K in, 1K out) | — | — | — | $0.095 |
| **Per-task per-model** | **~$0.55** | **~$0.05** | **~$0.05** | **~$0.10** |

### Total budget

| Scenario | Tasks | Models | Impl cost | Review cost | Total |
|---|---|---|---|---|---|
| Full run (12 tasks × 3 models) | 12 | 3 | $7.80 | $2.82 | **~$10.62** |

*Review cost includes both scoring ($1.20) and fix estimation ($1.62) passes. All 3 models run on all 12 tasks — no early elimination.*

**Budget allocation:**
- Anthropic (Sonnet + Opus): ~$8-9 from existing API credits
- MiniMax: ~$0.60-0.80 from $25 deposit (plenty of headroom)
- Groq: ~$0.60-0.80 from free tier (should be sufficient)

### Cost guard
Before each task, the harness prints:
```
Estimated cost for this task:
  Sonnet: ~$0.55  |  MiniMax: ~$0.05  |  Qwen3: ~$0.05  |  Opus review: ~$0.10
  Total: ~$0.75
  Running balance: $X.XX spent of $15 budget

Proceed? (y/n)
```

---

## Project Organization

```
stock-signal-platform/
├── benchmark/                              # ALL benchmark infra
│   ├── README.md                           # How to run, prerequisites
│   ├── config.yaml                         # Model configs + pricing
│   ├── scoring_rubric.yaml                 # 6 dimensions + weights + guides
│   ├── litellm-config.yaml                 # LiteLLM proxy config for Groq
│   ├── harness.py                          # Main orchestrator
│   ├── judge.py                            # Opus blind review (direct API call)
│   ├── metrics.py                          # Dataclasses + cost calculator + JSONL logger
│   ├── worktree.py                         # Worktree create/cleanup/PR helpers
│   ├── tasks/                              # Task YAMLs
│   │   ├── t1_001_subscription_tier.yaml
│   │   ├── t1_002_xxx.yaml
│   │   ├── t2_001_xxx.yaml
│   │   └── ...
│   ├── results/                            # gitignored — raw data
│   │   ├── all_runs.jsonl                  # Append-only master log
│   │   └── reports/                        # Per-task + aggregate reports
│   ├── .gitignore                          # results/ ignored
│   └── judge-prompt.md                     # Opus review prompt template
│
├── .benchmark/                             # gitignored — worktree workspace
│   ├── wt-sonnet/
│   ├── wt-minimax/
│   └── wt-qwen/
│
├── .claude/
│   └── skills/
│       └── benchmark/                      # Benchmark skill
│           └── SKILL.md
│
└── .gitignore                              # add .benchmark/
```

**Isolation guarantees:**
- `benchmark/` has NO imports from `backend/` or `frontend/`
- All Python is stdlib only (`json`, `subprocess`, `dataclasses`, `pathlib`, `concurrent.futures`)
- No `uv add` — benchmark scripts don't enter the project's venv
- `.benchmark/` worktrees are gitignored — ephemeral workspace
- `results/` is gitignored — raw metrics stay local
- Winner's PR goes through normal CI (lint, test, semgrep)

---

## Skill Design

### `.claude/skills/benchmark/SKILL.md`

```yaml
---
name: Benchmarking models
description: Runs a coding task across multiple LLM models in parallel worktrees,
  collects metrics, and produces a blind Opus review
triggers: ["benchmark", "model comparison", "compare models"]
---
```

**Skill workflow:**
1. Accept task YAML path as argument
2. Validate task YAML has all required fields
3. Print cost estimate, ask for confirmation
4. Create 3 worktrees from develop
5. Launch 3 Claude Code processes in parallel (`subprocess.Popen`)
6. Wait for all to complete (timeout: 10 min per task)
7. Run `pytest` and `ruff check` in each worktree
8. Collect metrics from JSON output + test/lint results
9. Call Opus for blind comparative review
10. Calculate derived metrics (real cost, value score, etc.)
11. Log to JSONL + print comparison table
12. Ask: "Winner is [Model X] (score: N.N, cost: $X.XX). PR to develop? (y/n)"
13. If yes → create PR from winner's worktree branch
14. Clean up all worktrees

---

## Run Protocol — The Actual Session

### Prerequisites (one-time)
- [ ] MiniMax API key in `backend/.env` (done — $25 loaded)
- [ ] Groq API key in `backend/.env` (done — free tier)
- [ ] `pip install 'litellm[proxy]'` (for Groq path)
- [ ] LiteLLM config validated (Groq connectivity test)
- [ ] 12 task YAMLs written from JIRA backlog
- [ ] `.benchmark/` added to `.gitignore`

### Execution order
1. **Tasks 1-12** — all 3 models on every task, sequential execution
2. **After each task** — Per-Task Report generated, winner PR'd to develop
3. **After task 4** — Failure Pattern Analysis generated (interim checkpoint)
4. **After task 12** — CTO Decision Brief + Enterprise Readiness Assessment

### After all 12 tasks
- 12 PRs merged to develop (from best implementations)
- 12 data points in `all_runs.jsonl`
- Aggregate report with decision: "MiniMax handles T1-T2 at X% of Sonnet cost with Y quality gap"
- JIRA tickets closed for completed tasks

---

## Output Format

### Per-task JSONL entry

```json
{
  "run_id": "bench_20260405_143022",
  "task_id": "t1_001",
  "task_name": "Add subscription tier field",
  "task_tier": "T1",
  "jira_ticket": "KAN-XXX",
  "timestamp": "2026-04-05T14:30:22Z",
  "models": {
    "claude-sonnet-4-6": {
      "input_tokens": 158000,
      "output_tokens": 5200,
      "actual_cost_usd": 0.552,
      "claude_reported_cost_usd": 0.552,
      "wall_clock_ms": 45000,
      "api_time_ms": 38000,
      "tokens_per_second": 136.8,
      "num_turns": 3,
      "tests_total": 5,
      "tests_passed": 5,
      "lint_violations": 0,
      "files_changed": 4,
      "lines_added": 85,
      "lines_removed": 2,
      "is_error": false,
      "first_pass_success": true
    },
    "MiniMax-M2.5": {
      "input_tokens": 155000,
      "output_tokens": 4800,
      "actual_cost_usd": 0.052,
      "claude_reported_cost_usd": 0.537,
      "...": "..."
    },
    "qwen3-32b": {
      "...": "..."
    }
  },
  "opus_review": {
    "review_input_tokens": 14200,
    "review_output_tokens": 980,
    "review_cost_usd": 0.096,
    "scores": {
      "claude-sonnet-4-6": {"correctness": 9, "convention_adherence": 9, "...": "...", "weighted_score": 8.8},
      "MiniMax-M2.5": {"correctness": 8, "...": "...", "weighted_score": 8.1},
      "qwen3-32b": {"correctness": 7, "...": "...", "weighted_score": 7.0}
    },
    "ranking": ["claude-sonnet-4-6", "MiniMax-M2.5", "qwen3-32b"],
    "winner": "claude-sonnet-4-6",
    "winner_rationale": "..."
  },
  "derived": {
    "claude-sonnet-4-6": {"cost_per_qp": 0.063, "value_score": 15.9},
    "MiniMax-M2.5": {"cost_per_qp": 0.006, "value_score": 155.8},
    "qwen3-32b": {"cost_per_qp": 0.007, "value_score": 140.0}
  },
  "winner_merged": "MiniMax-M2.5",
  "pr_number": 195,
  "total_benchmark_cost_usd": 0.748
}
```

### Aggregate report (after 12 tasks)

```
═══════════════════════════════════════════════════════════════
  MODEL BENCHMARK — AGGREGATE RESULTS (12 tasks)
═══════════════════════════════════════════════════════════════

Model              Avg Score  Win%  Avg Cost  $/QP    Avg Time
───────────────────────────────────────────────────────────────
Sonnet 4.6           8.5/10   58%   $0.550   $0.065    42s
MiniMax M2.5         8.1/10   33%   $0.052   $0.006    38s
Qwen3-32B            6.8/10    8%   $0.050   $0.007    12s

By Tier:
        Sonnet    MiniMax   Qwen3
T1:      9.2       8.9      7.5     ← MiniMax viable
T2:      8.8       8.3      7.0     ← MiniMax viable
T3:      8.2       7.5      6.2     ← Quality gap emerging
T4:      7.8       6.8      5.5     ← Sonnet-only territory

RECOMMENDATION:
  Use MiniMax M2.5 for T1-T2 tasks (67% of backlog)
  Use Sonnet 4.6 for T3-T4 tasks (33% of backlog)
  Projected savings: 52% on implementation costs

Total benchmark cost: $9.12
Tasks completed: 12 (all merged to develop)
═══════════════════════════════════════════════════════════════
```

---

## What We Build (implementation tasks)

| # | Component | LOC est. | Deps |
|---|---|---|---|
| 1 | `benchmark/config.yaml` | 30 | None |
| 2 | `benchmark/scoring_rubric.yaml` | 40 | None |
| 3 | `benchmark/litellm-config.yaml` | 15 | None |
| 4 | `benchmark/metrics.py` (dataclasses + cost calc + logger) | 150 | stdlib only |
| 5 | `benchmark/worktree.py` (create/cleanup/PR helpers) | 100 | subprocess, git |
| 6 | `benchmark/judge.py` (Opus blind review via httpx) | 120 | httpx |
| 7 | `benchmark/judge-prompt.md` | 40 | None |
| 8 | `benchmark/harness.py` (orchestrator + CLI) | 200 | subprocess, concurrent.futures |
| 9 | `.claude/skills/benchmark/SKILL.md` | 60 | None |
| 10 | 12 task YAMLs | 12 × 30 = 360 | JIRA backlog |
| 11 | `.gitignore` updates | 5 | None |
| 12 | `benchmark/README.md` | 50 | None |

**Total: ~1,170 LOC.** All stdlib except httpx for Opus API calls.

---

## Risk Register

| Risk | Impact | Mitigation |
|---|---|---|
| MiniMax Anthropic endpoint drops tool use mid-task | Task fails, money wasted | Smoke test passed; timeout + retry; count as data point |
| LiteLLM `output_config` error (#22963) with Qwen3 | Groq path blocked | Drop Groq, run 2-model comparison |
| Groq free tier rate-limited mid-benchmark | Qwen3 tasks timeout | Add retry with backoff; or upgrade to Developer ($0) |
| `total_cost_usd` wrong for non-Anthropic | Misleading cost data | Already mitigated — we calculate real cost from tokens |
| Worktree cleanup fails, stale branches | Disk space, confusion | harness.py has finally block for cleanup |
| Task too complex for all models | No winner to merge | Log failure, skip task, still useful data |
| MiniMax 64K output limit hit | Truncated response | T3-T4 tasks most at risk; monitor output token count |
| System prompt is 88K tokens (verified) | High base cost per run | Fixed cost; included in budget estimate |
| Opus judge bias toward verbose code | Inflated scores for over-engineered output | Rubric penalizes over-engineering; blind protocol hides model identity |
| MiniMax `thinking` blocks inflate output tokens | Misleading token count / cost | Separate thinking tokens from code tokens in metrics |
| Network latency difference (Anthropic US vs MiniMax Asia?) | Unfair speed comparison | Report `api_time_ms` AND `tokens_per_second`; latency is per-provider, throughput is per-model |

---

## CTO Review — Gaps and Additions

### Gap 1: Monthly projection missing
The per-task cost is meaningless without: "At our current velocity of X tasks/month, Model Y saves $Z/month." Added to Report Template 3.

### Gap 2: Quality floor not defined
When is a model "good enough"? Added decision criteria:
- **Merge-ready (≥7.5 weighted):** Winner can be merged as-is
- **Fix-and-merge (5.0–7.4):** Needs human review/fixes, still faster than writing from scratch
- **Reject (<5.0):** Model cannot handle this tier

### Gap 3: Failure mode analysis
Not just "which model wins" but "how does each model fail?" Pattern analysis needed:
- Does it hallucinate imports?
- Does it ignore project conventions?
- Does it produce code that compiles but is logically wrong?
- Does it over-engineer?
Added to Report Template 2.

### Gap 4: Ramp-down cost of Opus review
If MiniMax proves reliable on T1-T2, the real savings come from **dropping Opus review** for those tiers. The report must model this scenario explicitly. Added to Report Template 3.

### Gap 5: Vendor lock-in risk
MiniMax could change pricing, deprecate the Anthropic endpoint, or degrade quality. The report must note provider dependency risk and whether the proxy pattern (LiteLLM) provides a fallback. Added to Report Template 4.

---

## Report Templates

### Explainability Principles

Every report must be understandable by a human who will present it to stakeholders without the agent present. Rules:

1. **No unexplained abbreviations.** First use always includes full form: "Cost per Quality Point ($/QP)"
2. **Every number has context.** Not "$0.05" but "$0.05 (10x cheaper than Sonnet's $0.55)"
3. **Every recommendation has a "because."** Not "Use MiniMax for T1" but "Use MiniMax for T1 because it scored 8.9/10 vs Sonnet's 9.2 while costing 90% less — the 0.3-point quality gap is a convention violation (missing type annotation) that takes 2 minutes to fix"
4. **Jargon glossary at the bottom** of Reports 2, 3, and 4 — defines every technical term used
5. **Traffic light indicators** (✅ ⚠️ ❌) alongside numbers so the presenter can skim
6. **"So what?" line after every data table** — one sentence stating the implication
7. **Winner rationale is always Opus's own words** — not our paraphrase. Opus wrote it blind, which gives it credibility: "An independent AI reviewer, not knowing which model produced which code, chose X because..."

### Report 1: Per-Task Report (generated after each task)

```markdown
# Benchmark Report — {task_name}

**Task:** {task_id} | **Tier:** {tier} | **JIRA:** {jira_ticket}
**Date:** {timestamp} | **Run ID:** {run_id}

## Task Description
{description}

## Complexity Profile (pre-scored)
| Dimension | Score |
|---|---|
| Context Span | {n}/5 |
| Reasoning Depth | {n}/5 |
| Integration Surface | {n}/5 |
| Convention Density | {n}/5 |
| Implicit Knowledge | {n}/5 |
| Verification Difficulty | {n}/5 |
| Failure Cost | {n}/5 |
| **Total** | **{n}/35 → {tier}** |

## Results Summary

| Metric | Sonnet 4.6 | MiniMax M2.5 | Qwen3-32B |
|---|---|---|---|
| **Weighted Score** | {score}/10 | {score}/10 | {score}/10 |
| **Winner** | | ★ | |
| Tests Passed | {n}/{total} | {n}/{total} | {n}/{total} |
| Lint Violations | {n} | {n} | {n} |
| First-Pass Success | ✓/✗ | ✓/✗ | ✓/✗ |
| Input Tokens | {n} | {n} | {n} |
| Output Tokens | {n} | {n} | {n} |
| **Actual Cost** | ${x.xxx} | ${x.xxx} | ${x.xxx} |
| Wall Clock | {n}s | {n}s | {n}s |
| Tokens/sec | {n} | {n} | {n} |
| Turns | {n} | {n} | {n} |
| Files Changed | {n} | {n} | {n} |
| Lines Added | {n} | {n} | {n} |

## Dimension Scores (Opus Blind Review)

| Dimension (weight) | Sonnet | MiniMax | Qwen3 |
|---|---|---|---|
| Correctness (25%) | {n}/10 | {n}/10 | {n}/10 |
| Convention Adherence (20%) | {n}/10 | {n}/10 | {n}/10 |
| Integration Safety (20%) | {n}/10 | {n}/10 | {n}/10 |
| Completeness (15%) | {n}/10 | {n}/10 | {n}/10 |
| Code Quality (10%) | {n}/10 | {n}/10 | {n}/10 |
| First-Pass Success (10%) | {n}/10 | {n}/10 | {n}/10 |

## Opus Review — Key Findings

### Winner: {model} (Score: {score})
{winner_rationale}

### Complexity Assessment (Opus post-hoc)
| Metric | Sonnet | MiniMax | Qwen3 |
|---|---|---|---|
| Codebase Awareness | {n}/5 | {n}/5 | {n}/5 |
| Over-engineering | {n}/5 | {n}/5 | {n}/5 |
| Under-engineering | {n}/5 | {n}/5 | {n}/5 |
| Convention Violations | {list} | {list} | {list} |
| Hallucinated APIs | {n} | {n} | {n} |
| Self-correction Attempts | {n} | {n} | {n} |
| Self-correction Success | {pct}% | {pct}% | {pct}% |
| Dead-end Tool Calls | {n} | {n} | {n} |
| Post Complexity Score | {n}/35 | {n}/35 | {n}/35 |

**Pre-score:** {n}/35 | **Opus post-score avg:** {n}/35 | **Calibration delta:** {±n}

### Per-Model Notes
**Sonnet:** {strengths} | Issues: {issues}
**MiniMax:** {strengths} | Issues: {issues}
**Qwen3:** {strengths} | Issues: {issues}

## Cost Efficiency

| Metric | Sonnet | MiniMax | Qwen3 |
|---|---|---|---|
| Cost/Quality Point | ${x.xxxx} | ${x.xxxx} | ${x.xxxx} |
| Cost vs Sonnet | 1.00x | {x.xx}x | {x.xx}x |
| Speed vs Sonnet | 1.00x | {x.xx}x | {x.xx}x |
| Value Score (quality/$) | {n} | {n} | {n} |

## Decision
- **Merged:** {winner_model} → PR #{pr_number}
- **Task cost:** ${total} (impl: ${impl} + review: ${review})
```

### Report 2: Failure Pattern Analysis (generated after 4+ tasks)

```markdown
# Failure Pattern Analysis — After {n} Tasks

## Model Failure Modes

### Sonnet 4.6
| Pattern | Occurrences | Severity | Example |
|---|---|---|---|
| {e.g., Over-engineers simple tasks} | {n}/{total} | Low | Task T1_002 |
| {e.g., Ignores context from CLAUDE.md} | {n}/{total} | Medium | Task T2_001 |

### MiniMax M2.5
| Pattern | Occurrences | Severity | Example |
|---|---|---|---|
| {e.g., Hallucinates non-existent imports} | {n}/{total} | High | Task T2_003 |
| {e.g., Doesn't follow async convention} | {n}/{total} | Medium | Task T3_001 |
| {e.g., Truncates output at 64K limit} | {n}/{total} | High | Task T4_001 |

### Qwen3-32B
| Pattern | Occurrences | Severity | Example |
|---|---|---|---|
| {e.g., Tool use fails after 5+ turns} | {n}/{total} | Critical | Task T3_002 |
| {e.g., Wrong test framework (unittest vs pytest)} | {n}/{total} | Medium | Task T1_003 |

## Capability Ceiling by Tier

| Tier | Sonnet | MiniMax | Qwen3 | Notes |
|---|---|---|---|---|
| T1 (Surgical) | ✅ Reliable | ✅ Reliable | ⚠️ Inconsistent | {notes} |
| T2 (Feature) | ✅ Reliable | ⚠️ Sometimes | ❌ Unreliable | {notes} |
| T3 (Multi-file) | ✅ Reliable | ⚠️ Sometimes | ❌ Failed | {notes} |
| T4 (Refactor) | ⚠️ Sometimes | ❌ Failed | ❌ Failed | {notes} |

Legend: ✅ ≥7.5 avg score | ⚠️ 5.0–7.4 avg | ❌ <5.0 avg or >50% failure

## Interim Assessment (checkpoint at task 4)
- **Qwen3-32B viability:** {On track / Struggling / Failing} — {rationale}
- **MiniMax viability:** {On track / Competitive / Exceeding expectations} — {rationale}
- **Any model completely non-functional?** {If yes, note it but keep running for data completeness}
```

### Report 3: CTO Decision Brief (generated after all tasks complete)

```markdown
# Model Benchmark — CTO Decision Brief

**Date:** {date}
**Benchmark scope:** {n} real JIRA tasks across 4 complexity tiers
**Models tested:** Sonnet 4.6, MiniMax M2.5, Qwen3-32B (Groq)
**Total benchmark cost:** ${total} | **Tasks merged to develop:** {n}

---

## Executive Summary

{1-2 sentence recommendation, e.g.: "MiniMax M2.5 handles T1-T2 tasks at
94% of Sonnet quality for 10% of the cost. Recommend adopting for routine
implementation tasks, keeping Sonnet for T3+ complexity."}

---

## Head-to-Head Results

### Overall Performance
| Model | Avg Score | Win Rate | Avg Cost | Cost/QP | Avg Time | Value (Q/$) |
|---|---|---|---|---|---|---|
| Sonnet 4.6 | {n}/10 | {n}% | ${n} | ${n} | {n}s | {n} |
| MiniMax M2.5 | {n}/10 | {n}% | ${n} | ${n} | {n}s | {n} |
| Qwen3-32B | {n}/10 | {n}% | ${n} | ${n} | {n}s | {n} |

### Performance by Tier
| Tier | Tasks | Sonnet Score | MiniMax Score | Qwen3 Score | Best Value |
|---|---|---|---|---|---|
| T1 Surgical | {n} | {score} | {score} | {score} | {model} |
| T2 Feature | {n} | {score} | {score} | {score} | {model} |
| T3 Multi-file | {n} | {score} | {score} | {score} | {model} |
| T4 Refactor | {n} | {score} | {score} | {score} | {model} |

### Quality Floor Analysis
| Model | Tasks ≥7.5 (merge-ready) | Tasks 5-7.4 (fix needed) | Tasks <5 (reject) |
|---|---|---|---|
| Sonnet 4.6 | {n}/{total} ({pct}%) | {n}/{total} | {n}/{total} |
| MiniMax M2.5 | {n}/{total} ({pct}%) | {n}/{total} | {n}/{total} |
| Qwen3-32B | {n}/{total} ({pct}%) | {n}/{total} | {n}/{total} |

---

## Cost Projection — Monthly Impact

### Current state (Sonnet-only)
| Item | Monthly volume | Unit cost | Monthly cost |
|---|---|---|---|
| T1-T2 tasks (routine) | ~{n} tasks | ~${x}/task | ${total} |
| T3-T4 tasks (complex) | ~{n} tasks | ~${x}/task | ${total} |
| Opus review (all tasks) | ~{n} reviews | ~${x}/review | ${total} |
| **Total** | | | **${total}/mo** |

### Proposed state (MiniMax for T1-T2, Sonnet for T3-T4)
| Item | Monthly volume | Unit cost | Monthly cost |
|---|---|---|---|
| T1-T2 via MiniMax M2.5 | ~{n} tasks | ~${x}/task | ${total} |
| T3-T4 via Sonnet 4.6 | ~{n} tasks | ~${x}/task | ${total} |
| Opus review (all tasks) | ~{n} reviews | ~${x}/review | ${total} |
| **Total** | | | **${total}/mo** |

### Savings
| Metric | Value |
|---|---|
| Monthly savings | **${x}/mo ({pct}% reduction)** |
| Annual savings | **${x}/yr** |
| Quality impact | {x.x}% average score reduction on T1-T2 |
| Speed impact | {x.x}x faster on average |

### True cost (including staff engineer cleanup)
| Model | Impl cost | Opus review | Staff cleanup | **Net cost/task** | vs Sonnet |
|---|---|---|---|---|---|
| Sonnet 4.6 | ${impl} | ${review} | ${cleanup} ({n} min) | **${net}** | baseline |
| MiniMax M2.5 | ${impl} | ${review} | ${cleanup} ({n} min) | **${net}** | {pct}% |
| Qwen3-32B | ${impl} | ${review} | ${cleanup} ({n} min) | **${net}** | {pct}% |

### Staff engineer burden by model
| Metric | Sonnet | MiniMax | Qwen3 |
|---|---|---|---|
| Avg fix actions per task | {n} | {n} | {n} |
| Avg fix minutes per task | {n} min | {n} min | {n} min |
| PR block rate | {n}% | {n}% | {n}% |
| Critical/High fixes | {n} | {n} | {n} |
| Convention violations | {n} | {n} | {n} |
| Monthly staff cleanup hours (at {n} tasks/mo) | {n} hrs | {n} hrs | {n} hrs |
| Monthly staff cleanup cost (@${rate}/hr) | ${n} | ${n} | ${n} |

### Fix type distribution
| Fix type | Sonnet | MiniMax | Qwen3 |
|---|---|---|---|
| Bug | {n} ({pct}%) | {n} ({pct}%) | {n} ({pct}%) |
| Convention | {n} ({pct}%) | {n} ({pct}%) | {n} ({pct}%) |
| Missing feature | {n} ({pct}%) | {n} ({pct}%) | {n} ({pct}%) |
| Security | {n} ({pct}%) | {n} ({pct}%) | {n} ({pct}%) |
| Over-engineering | {n} ({pct}%) | {n} ({pct}%) | {n} ({pct}%) |
| Test gap | {n} ({pct}%) | {n} ({pct}%) | {n} ({pct}%) |

**Key insight:** {e.g., "MiniMax produces more convention violations but fewer bugs than Qwen3. Convention fixes are mechanical (5 min each), but bugs require investigation (15 min each). MiniMax cleanup is cheaper despite more total fix actions."}

### Scenario: Drop Opus review for T1-T2 (if MiniMax proves reliable)
| Metric | Value |
|---|---|
| Additional monthly savings | **${x}/mo** |
| Risk | {describe: e.g., "2/12 MiniMax outputs needed fixes that review would have caught"} |
| Recommendation | {e.g., "Drop review for T1 only after 20+ consecutive clean merges"} |

---

## Dimension Analysis — Where Models Diverge

| Dimension | Sonnet avg | MiniMax avg | Gap | Concern? |
|---|---|---|---|---|
| Correctness | {n} | {n} | {delta} | {Yes/No — why} |
| Convention Adherence | {n} | {n} | {delta} | {Yes/No} |
| Integration Safety | {n} | {n} | {delta} | {Yes/No} |
| Completeness | {n} | {n} | {delta} | {Yes/No} |
| Code Quality | {n} | {n} | {delta} | {Yes/No} |
| First-Pass Success | {n} | {n} | {delta} | {Yes/No} |

**Biggest quality gap:** {dimension} — {explanation}
**Surprising strength:** {model did better than expected on X}

## Complexity vs Quality Correlation

### Score by complexity band
| Complexity | Tasks | Sonnet avg | MiniMax avg | Qwen3 avg | Best value model |
|---|---|---|---|---|---|
| 7-12 (T1) | {n} | {score} | {score} | {score} | {model} (${cost_per_qp}) |
| 13-18 (T2) | {n} | {score} | {score} | {score} | {model} (${cost_per_qp}) |
| 19-25 (T3) | {n} | {score} | {score} | {score} | {model} (${cost_per_qp}) |
| 26-35 (T4) | {n} | {score} | {score} | {score} | {model} (${cost_per_qp}) |

### Quality drop-off threshold
**MiniMax stays within 1 point of Sonnet up to complexity {n}/35.**
Above that threshold, quality degrades by {x} points per complexity unit.

→ **Decision boundary:** Use MiniMax for tasks scoring ≤{n}/35, Sonnet for >{n}/35.

### Model-specific complexity ceilings
| Model | Max complexity for ≥7.5 score | Max complexity for ≥5.0 score | Failure threshold |
|---|---|---|---|
| Sonnet 4.6 | {n}/35 | {n}/35 | {n}/35 |
| MiniMax M2.5 | {n}/35 | {n}/35 | {n}/35 |
| Qwen3-32B | {n}/35 | {n}/35 | {n}/35 |

### Agentic behavior by complexity
| Metric (avg) | Simple (7-12) | Moderate (13-18) | Hard (19-25) | Very Hard (26-35) |
|---|---|---|---|---|
| Turns (Sonnet) | {n} | {n} | {n} | {n} |
| Turns (MiniMax) | {n} | {n} | {n} | {n} |
| Self-correction rate (Sonnet) | {pct}% | {pct}% | {pct}% | {pct}% |
| Self-correction rate (MiniMax) | {pct}% | {pct}% | {pct}% | {pct}% |
| Dead-end tools (Sonnet) | {n} | {n} | {n} | {n} |
| Dead-end tools (MiniMax) | {n} | {n} | {n} | {n} |
| Hallucinated APIs (Sonnet) | {n} | {n} | {n} | {n} |
| Hallucinated APIs (MiniMax) | {n} | {n} | {n} | {n} |

---

## Risk Assessment

### Provider Dependency
| Factor | Sonnet | MiniMax | Qwen3 (Groq) |
|---|---|---|---|
| API stability | High (Anthropic) | Medium (newer provider) | Medium (Groq) |
| Pricing stability | Stable | Unknown long-term | Competitive pressure |
| Anthropic-compat endpoint | Native | Third-party (could break) | Via LiteLLM (proxy) |
| Fallback if provider fails | — | Sonnet (baseline) | Sonnet or MiniMax |
| Enterprise Bedrock available? | Yes | Yes (announced) | No |

### Operational Risks
- **MiniMax Anthropic endpoint deprecation:** Fallback to MiniMax OpenAI endpoint + LiteLLM
- **Quality regression on model updates:** Re-run 3 sentinel tasks (one per tier) monthly
- **Output token limit (64K MiniMax, 41K Qwen3):** Monitor for truncation; escalate T3+ to Sonnet

---

## Recommendation

### Immediate (this sprint)
{e.g., "Adopt MiniMax M2.5 for T1-T2 tasks via direct Anthropic API. Keep Sonnet for T3+."}

### Short-term (next 30 days)
{e.g., "Run 20 T1-T2 tasks on MiniMax without Opus review. Track defect rate. If <5% need fixes, formalize review-skip policy."}

### Long-term (next quarter)
{e.g., "Evaluate MiniMax M2.7 as potential T3 candidate. Build Bedrock routing for enterprise customers."}

---

## How This Benchmark Was Conducted

This benchmark was fully automated using Claude Code agents. Here's what happened and why you can trust the results:

1. **Real work, not synthetic tests.** Every task was a real JIRA ticket from our backlog. The winning implementation was merged into our codebase. This is not a lab exercise — it produced working software.

2. **Blind evaluation.** The reviewer (Opus 4.6) scored all implementations without knowing which model produced which code. Model identities were revealed only after scores were locked. This eliminates brand bias.

3. **Same task, same tools, same codebase.** All three models received identical instructions, had access to the same tools (file read/write, search, test execution), and worked on the same codebase. The only variable was the model.

4. **Automated metric collection.** Token counts, costs, and timing come from API responses — not estimates. Staff cleanup time is estimated by the reviewer based on specific issues found.

5. **Reproducible.** Task definitions, scoring rubric, and all raw data are archived. Any task can be re-run to verify results.

## Glossary

| Term | Definition |
|---|---|
| **Weighted Score** | Quality rating 1-10 across 6 dimensions (correctness, convention adherence, integration safety, completeness, code quality, first-pass success), weighted by importance to our project |
| **Cost per Quality Point ($/QP)** | How much each point of quality costs. Lower = more efficient. A model scoring 8/10 for $0.05 has $/QP of $0.006 |
| **Value Score (Quality/$)** | Inverse of $/QP. Higher = better value. Quality points per dollar spent |
| **First-Pass Success** | Did the model's code pass all tests and linting on the first attempt, with no fixes needed? |
| **Review Burden** | The time and effort a staff engineer would need to clean up the model's output before it can be merged |
| **PR Block Rate** | Percentage of tasks where the model's output had critical/high issues that would prevent merging without fixes |
| **Net Cost** | True cost = model API cost + Opus review cost + staff engineer cleanup cost. The actual price of getting working code |
| **Complexity Score** | 7-35 rating across 7 dimensions measuring how hard a task is. Higher = more files, more reasoning, more risk |
| **T1-T4 Tiers** | Task complexity bands. T1 (7-12): simple edits. T2 (13-18): single features. T3 (19-25): multi-file. T4 (26-35): refactors |
| **Capability Ceiling** | The maximum complexity score at which a model still produces merge-ready code (score ≥7.5) |
| **No Progressive Elimination** | All 3 models run all 12 tasks for complete data. No early dropping. |
| **MoE (Mixture of Experts)** | Architecture where only a fraction of the model's parameters activate per token, making large models computationally cheap |
| **Anthropic-compatible API** | An endpoint that speaks the same protocol as Claude, allowing drop-in model substitution |

## Appendix: Raw Data
- Full results: `benchmark/results/all_runs.jsonl`
- Per-task reports: `benchmark/results/reports/`
- Scoring rubric: `benchmark/scoring_rubric.yaml`
- Task definitions: `benchmark/tasks/`
```

### Report 4: Enterprise Readiness Assessment (optional, for customer-facing pitch)

```markdown
# Multi-Model Architecture — Enterprise Readiness

## Architecture Pattern Validated
- **Proxy pattern (LiteLLM):** {Validated/Failed} — routes any model through Claude Code
- **Direct Anthropic-compat API:** {Validated/Failed} — MiniMax drop-in replacement
- **Bedrock routing:** {Not tested / Validated} — enterprise AWS integration

## Customer Deployment Options

| Option | Models | Infra | Cost profile | Quality |
|---|---|---|---|---|
| A: Anthropic-only | Sonnet + Opus | Direct API | $$$$ | Highest |
| B: Hybrid (recommended) | MiniMax (routine) + Sonnet (complex) + Opus (review) | Direct API × 2 | $$ | High |
| C: Bedrock | Customer's Bedrock models + Opus review | LiteLLM proxy | $ (customer-funded) | Depends on model |
| D: Full open-source | Qwen3 (Groq/self-hosted) + Opus review | LiteLLM proxy | $ | Medium |

## Benchmark Evidence
- {n} tasks tested across {n} tiers
- Quality data: {summary}
- Cost data: {summary}
- Failure modes documented: {reference to Report 2}

## Vendor Diversification Score
- Models tested: {n} providers
- API formats validated: Anthropic native, Anthropic-compat, OpenAI via proxy
- Fallback paths: {describe}
```
