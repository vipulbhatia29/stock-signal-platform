# Model Benchmark Framework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a benchmark harness that runs 3 LLM models (Sonnet 4.6, MiniMax M2.5, Qwen3-32B) on the same coding task in parallel worktrees, collects cost/quality/speed metrics, and produces Opus-judged reports with CTO-ready recommendations.

**Architecture:** Python scripts (stdlib + httpx) orchestrate Claude Code processes via subprocess, one per model per worktree. Opus reviews implementations via direct API call. All data logged as JSONL. Reports generated as markdown.

**Tech Stack:** Python 3.11+ (stdlib: subprocess, dataclasses, json, concurrent.futures, pathlib, argparse, textwrap, datetime), httpx (for Opus API calls), PyYAML (for config/task loading). NO project venv — standalone scripts.

---

## File Structure

```
benchmark/
├── config.yaml              # Model IDs, pricing, staff rate, budget cap
├── scoring_rubric.yaml       # 6 quality dimensions + weights
├── litellm-config.yaml       # LiteLLM proxy config for Groq
├── judge-prompt.md           # Opus review prompt template (Pass 1 + Pass 2)
├── metrics.py                # Dataclasses: ModelResult, OpusReview, BenchmarkRun + JSONL logger + cost calculator
├── worktree.py               # create_worktrees(), cleanup_worktrees(), create_pr()
├── judge.py                  # OpusJudge.score() + OpusJudge.estimate_fixes() — direct httpx to Anthropic API
├── harness.py                # Main CLI orchestrator — ties everything together
├── report.py                 # Generate all 4 report types: per-task, failure analysis, CTO brief, enterprise readiness
├── tasks/                    # Task YAML definitions (created in Task 9)
├── results/                  # gitignored — all_runs.jsonl + reports/
├── .gitignore                # results/
└── README.md                 # Setup + usage guide
```

Each file has one responsibility. Dependencies flow downward: `harness.py` → `worktree.py`, `metrics.py`, `judge.py`, `report.py`. No circular imports.

---

### Task 1: Project scaffold + config files

**Files:**
- Create: `benchmark/config.yaml`
- Create: `benchmark/scoring_rubric.yaml`
- Create: `benchmark/litellm-config.yaml`
- Create: `benchmark/.gitignore`
- Modify: `.gitignore` (add `.benchmark/`)

- [ ] **Step 1: Create benchmark directory**

```bash
mkdir -p benchmark/tasks benchmark/results/reports
```

- [ ] **Step 2: Create `benchmark/config.yaml`**

```yaml
models:
  claude-sonnet-4-6:
    provider: anthropic
    base_url: "https://api.anthropic.com"
    env_key: ANTHROPIC_API_KEY
    model_id: "claude-sonnet-4-6"
    role: implementor
    pricing:
      input_per_m: 3.00
      output_per_m: 15.00
    max_output_tokens: 128000
    context_window: 200000

  MiniMax-M2.5:
    provider: minimax
    base_url: "https://api.minimax.io/anthropic"
    env_key: MINIMAX_API_KEY
    model_id: "MiniMax-M2.5"
    role: implementor
    pricing:
      input_per_m: 0.30
      output_per_m: 1.20
    max_output_tokens: 64000
    context_window: 200000

  qwen3-32b:
    provider: groq
    base_url: "http://localhost:4000"
    env_key: LITELLM_MASTER_KEY
    auth_header: ANTHROPIC_AUTH_TOKEN  # LiteLLM uses this instead of ANTHROPIC_API_KEY
    model_id: "qwen3-32b"
    role: implementor
    pricing:
      input_per_m: 0.29
      output_per_m: 0.59
    max_output_tokens: 40960
    context_window: 131000

  claude-opus-4-6:
    provider: anthropic
    base_url: "https://api.anthropic.com"
    env_key: ANTHROPIC_API_KEY
    model_id: "claude-opus-4-6"
    role: judge
    pricing:
      input_per_m: 5.00
      output_per_m: 25.00

benchmark:
  implementors:
    - claude-sonnet-4-6
    - MiniMax-M2.5
    - qwen3-32b
  reviewer: claude-opus-4-6
  timeout_seconds: 600  # 10 min per model per task
  worktree_dir: .benchmark
  results_dir: benchmark/results
  env_file: backend/.env
  budget_cap_usd: 15.00

staff_engineer:
  hourly_rate_usd: 95.00
  review_overhead_pct: 0.20
```

- [ ] **Step 3: Create `benchmark/scoring_rubric.yaml`**

```yaml
dimensions:
  correctness:
    weight: 0.25
    description: "Does the code correctly implement the requirements? Edge cases?"
    scoring_guide:
      10: "All requirements met, edge cases handled"
      7: "Core logic correct, minor gaps"
      5: "Mostly correct, some bugs"
      3: "Significant errors"
      1: "Fundamentally wrong"

  convention_adherence:
    weight: 0.20
    description: "Follows project patterns: async, naming, file structure, test style?"
    scoring_guide:
      10: "Follows all project patterns perfectly"
      7: "Minor deviations from conventions"
      5: "Some pattern violations"
      3: "Ignores most conventions"
      1: "Completely foreign style"

  integration_safety:
    weight: 0.20
    description: "Breaks nothing existing? Proper imports? FK constraints respected?"
    scoring_guide:
      10: "Breaks nothing, proper imports, FK constraints intact"
      7: "Safe with minor issues"
      5: "One breaking change found"
      3: "Multiple integration risks"
      1: "Would break production"

  completeness:
    weight: 0.15
    description: "All requirements addressed? Error handling? Types?"
    scoring_guide:
      10: "All requirements + error handling + types"
      7: "Core requirements met"
      5: "Most requirements, some gaps"
      3: "Significant missing functionality"
      1: "Only partially addresses the task"

  code_quality:
    weight: 0.10
    description: "Clean, readable, right level of abstraction?"
    scoring_guide:
      10: "Clean, readable, right abstraction level"
      7: "Good with minor issues"
      5: "Functional but messy"
      3: "Hard to read"
      1: "No clear structure"

  first_pass_success:
    weight: 0.10
    description: "Did the code work on first attempt without fixes?"
    scoring_guide:
      10: "Tests + lint pass on first run"
      7: "Minor fix needed (typo, import)"
      5: "One significant fix iteration"
      3: "Multiple fix iterations needed"
      1: "Never achieved working state"

quality_floors:
  merge_ready: 7.5
  fix_and_merge: 5.0
  reject: 5.0  # below this = reject

complexity_dimensions:
  - context_span
  - reasoning_depth
  - integration_surface
  - convention_density
  - implicit_knowledge
  - verification_difficulty
  - failure_cost

fix_types:
  - bug
  - convention
  - missing_feature
  - security
  - over_engineering
  - test_gap

fix_severities:
  - critical  # blocks PR
  - high      # blocks PR
  - medium    # fix preferred
  - low       # nice to have
```

- [ ] **Step 4: Create `benchmark/litellm-config.yaml`**

```yaml
model_list:
  - model_name: qwen3-32b
    litellm_params:
      model: groq/qwen/qwen3-32b
      api_key: os.environ/GROQ_API_KEY
      max_tokens: 40960

general_settings:
  master_key: sk-benchmark-local-key

litellm_settings:
  drop_params: true  # drops unsupported params (output_config) instead of erroring
```

- [ ] **Step 5: Create `benchmark/.gitignore`**

```
results/
__pycache__/
*.pyc
```

- [ ] **Step 6: Add `.benchmark/` to root `.gitignore`**

Append to `/Users/sigmoid/Documents/projects/stockanalysis/stock-signal-platform/.gitignore`:
```
# Benchmark worktrees (ephemeral)
.benchmark/
```

- [ ] **Step 7: Commit**

```bash
git add benchmark/config.yaml benchmark/scoring_rubric.yaml benchmark/litellm-config.yaml benchmark/.gitignore .gitignore
git commit -m "feat(benchmark): scaffold project structure and config files"
```

---

### Task 2: Metrics dataclasses + cost calculator + JSONL logger

**Files:**
- Create: `benchmark/metrics.py`

- [ ] **Step 1: Create `benchmark/metrics.py`**

```python
"""Dataclasses for benchmark metrics, cost calculation, and JSONL logging."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Pricing per million tokens — source of truth
PRICING: dict[str, dict[str, float]] = {
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00},
    "MiniMax-M2.5": {"input": 0.30, "output": 1.20},
    "qwen3-32b": {"input": 0.29, "output": 0.59},
    "claude-opus-4-6": {"input": 5.00, "output": 25.00},
}


def real_cost(model_id: str, input_tokens: int, output_tokens: int) -> float:
    """Calculate actual cost using provider pricing, not Claude Code's reported cost."""
    p = PRICING.get(model_id, {"input": 0.0, "output": 0.0})
    return (input_tokens * p["input"] + output_tokens * p["output"]) / 1_000_000


@dataclass
class ModelResult:
    """Metrics collected for one model's implementation of one task."""

    model_id: str
    input_tokens: int = 0
    output_tokens: int = 0
    actual_cost_usd: float = 0.0
    claude_reported_cost_usd: float = 0.0
    wall_clock_ms: int = 0
    api_time_ms: int = 0
    tokens_per_second: float = 0.0
    num_turns: int = 0
    tests_total: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    lint_violations: int = 0
    files_changed: int = 0
    lines_added: int = 0
    lines_removed: int = 0
    is_error: bool = False
    first_pass_success: bool = False
    diff_text: str = ""  # git diff output for judge
    test_output: str = ""  # pytest output for judge
    lint_output: str = ""  # ruff output for judge

    def calculate_derived(self) -> None:
        """Populate derived fields from raw data."""
        self.actual_cost_usd = real_cost(self.model_id, self.input_tokens, self.output_tokens)
        if self.api_time_ms > 0:
            self.tokens_per_second = self.output_tokens / (self.api_time_ms / 1000)
        self.first_pass_success = (
            self.tests_total > 0
            and self.tests_passed == self.tests_total
            and self.lint_violations == 0
            and not self.is_error
        )


@dataclass
class FixAction:
    """A single fix Opus identified for an implementation."""

    file: str
    fix_type: str  # bug, convention, missing_feature, security, over_engineering, test_gap
    severity: str  # critical, high, medium, low
    description: str
    estimated_fix_lines: int = 0
    estimated_fix_minutes: int = 0


@dataclass
class FixSummary:
    """Aggregate fix estimation for one model's implementation."""

    model_id: str
    fix_actions: list[FixAction] = field(default_factory=list)
    total_actions: int = 0
    by_severity: dict[str, int] = field(default_factory=dict)
    by_type: dict[str, int] = field(default_factory=dict)
    total_fix_lines: int = 0
    total_fix_minutes: int = 0
    opus_fix_tokens: int = 0
    opus_fix_cost_usd: float = 0.0
    would_block_pr: bool = False
    staff_engineer_equivalent_hours: float = 0.0

    def calculate(self, hourly_rate: float = 95.0, overhead_pct: float = 0.20) -> None:
        """Compute aggregates from fix_actions list."""
        self.total_actions = len(self.fix_actions)
        self.by_severity = {}
        self.by_type = {}
        self.total_fix_lines = 0
        self.total_fix_minutes = 0
        for action in self.fix_actions:
            self.by_severity[action.severity] = self.by_severity.get(action.severity, 0) + 1
            self.by_type[action.fix_type] = self.by_type.get(action.fix_type, 0) + 1
            self.total_fix_lines += action.estimated_fix_lines
            self.total_fix_minutes += action.estimated_fix_minutes
        self.would_block_pr = self.by_severity.get("critical", 0) + self.by_severity.get("high", 0) > 0
        self.staff_engineer_equivalent_hours = (self.total_fix_minutes / 60) * (1 + overhead_pct)
        self.opus_fix_cost_usd = real_cost("claude-opus-4-6", self.opus_fix_tokens, 0)


@dataclass
class OpusScores:
    """Quality scores from Opus blind review for one implementation."""

    correctness: int = 0
    convention_adherence: int = 0
    integration_safety: int = 0
    completeness: int = 0
    code_quality: int = 0
    first_pass_success: int = 0
    weighted_score: float = 0.0
    specific_issues: list[str] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)
    would_need_rewrite: bool = False
    # Complexity-aware metrics
    required_codebase_reads: int = 0
    convention_violations: list[str] = field(default_factory=list)
    hallucinated_apis: int = 0
    over_engineering_score: int = 1
    under_engineering_score: int = 1
    self_correction_attempts: int = 0
    self_correction_success_rate: float = 0.0
    dead_end_tools: int = 0
    codebase_awareness: int = 1
    post_complexity_score: int = 0
    post_complexity_reason: str = ""

    def calculate_weighted(self) -> None:
        """Calculate weighted score from dimension scores."""
        weights = {
            "correctness": 0.25,
            "convention_adherence": 0.20,
            "integration_safety": 0.20,
            "completeness": 0.15,
            "code_quality": 0.10,
            "first_pass_success": 0.10,
        }
        self.weighted_score = round(sum(
            getattr(self, dim) * w for dim, w in weights.items()
        ), 2)


@dataclass
class OpusReview:
    """Complete Opus review for one task (all implementations)."""

    review_input_tokens: int = 0
    review_output_tokens: int = 0
    review_cost_usd: float = 0.0
    scores: dict[str, OpusScores] = field(default_factory=dict)
    fix_summaries: dict[str, FixSummary] = field(default_factory=dict)
    ranking: list[str] = field(default_factory=list)
    winner: str = ""
    winner_rationale: str = ""
    comparative_notes: str = ""

    def calculate_cost(self) -> None:
        self.review_cost_usd = real_cost(
            "claude-opus-4-6", self.review_input_tokens, self.review_output_tokens
        )


@dataclass
class TaskComplexity:
    """Pre-scored complexity for a task."""

    context_span: int = 1
    reasoning_depth: int = 1
    integration_surface: int = 1
    convention_density: int = 1
    implicit_knowledge: int = 1
    verification_difficulty: int = 1
    failure_cost: int = 1

    @property
    def total(self) -> int:
        return sum([
            self.context_span, self.reasoning_depth, self.integration_surface,
            self.convention_density, self.implicit_knowledge,
            self.verification_difficulty, self.failure_cost,
        ])

    @property
    def tier(self) -> str:
        t = self.total
        if t <= 12:
            return "T1"
        if t <= 18:
            return "T2"
        if t <= 25:
            return "T3"
        return "T4"


@dataclass
class DerivedMetrics:
    """Derived comparison metrics for one model."""

    cost_per_quality_point: float = 0.0
    test_pass_rate: float = 0.0
    cost_ratio_vs_sonnet: float = 0.0
    speed_ratio_vs_sonnet: float = 0.0
    quality_gap_vs_sonnet: float = 0.0
    value_score: float = 0.0
    net_cost: float = 0.0  # impl + review + staff cleanup
    net_cost_vs_sonnet: float = 0.0


@dataclass
class BenchmarkRun:
    """Top-level result for one task across all models."""

    run_id: str = ""
    task_id: str = ""
    task_name: str = ""
    task_tier: str = ""
    jira_ticket: str = ""
    timestamp: str = ""
    complexity: TaskComplexity | None = None
    models: dict[str, ModelResult] = field(default_factory=dict)
    opus_review: OpusReview | None = None
    derived: dict[str, DerivedMetrics] = field(default_factory=dict)
    winner_merged: str = ""
    pr_number: int = 0
    total_benchmark_cost_usd: float = 0.0

    def generate_run_id(self) -> None:
        now = datetime.now(timezone.utc)
        self.timestamp = now.isoformat()
        self.run_id = f"bench_{now.strftime('%Y%m%d_%H%M%S')}"

    def calculate_derived(self, staff_rate: float = 95.0) -> None:
        """Calculate all derived metrics after models + review are populated."""
        sonnet = self.models.get("claude-sonnet-4-6")
        review = self.opus_review

        for model_id, result in self.models.items():
            d = DerivedMetrics()
            scores = review.scores.get(model_id) if review else None
            fix_summary = review.fix_summaries.get(model_id) if review else None

            ws = scores.weighted_score if scores else 0.0
            if ws > 0:
                d.cost_per_quality_point = result.actual_cost_usd / ws
            if result.tests_total > 0:
                d.test_pass_rate = result.tests_passed / result.tests_total
            if sonnet and sonnet.actual_cost_usd > 0:
                d.cost_ratio_vs_sonnet = result.actual_cost_usd / sonnet.actual_cost_usd
            if sonnet and sonnet.wall_clock_ms > 0 and result.wall_clock_ms > 0:
                d.speed_ratio_vs_sonnet = sonnet.wall_clock_ms / result.wall_clock_ms
            sonnet_scores = review.scores.get("claude-sonnet-4-6") if review else None
            if sonnet_scores and scores:
                d.quality_gap_vs_sonnet = sonnet_scores.weighted_score - ws
            if result.actual_cost_usd > 0:
                d.value_score = ws / result.actual_cost_usd

            # Net cost includes review share + staff cleanup
            review_share = (review.review_cost_usd / len(self.models)) if review else 0.0
            staff_cost = 0.0
            if fix_summary:
                staff_cost = (fix_summary.total_fix_minutes / 60) * staff_rate
            d.net_cost = result.actual_cost_usd + review_share + staff_cost

            self.derived[model_id] = d

        # Net cost vs sonnet
        sonnet_net = self.derived.get("claude-sonnet-4-6")
        if sonnet_net and sonnet_net.net_cost > 0:
            for model_id, d in self.derived.items():
                d.net_cost_vs_sonnet = d.net_cost / sonnet_net.net_cost

        # Total benchmark cost
        self.total_benchmark_cost_usd = sum(
            r.actual_cost_usd for r in self.models.values()
        ) + (review.review_cost_usd if review else 0.0)


def _serialize(obj: Any) -> Any:
    """Custom serializer for dataclass nesting."""
    if hasattr(obj, "__dataclass_fields__"):
        return asdict(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    return str(obj)


class BenchmarkLogger:
    """Append-only JSONL logger for benchmark results."""

    def __init__(self, results_dir: str = "benchmark/results"):
        self.results_dir = Path(results_dir)
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.jsonl_path = self.results_dir / "all_runs.jsonl"

    def save_run(self, run: BenchmarkRun) -> Path:
        """Append run to JSONL and save individual JSON."""
        data = json.loads(json.dumps(asdict(run), default=_serialize))

        # Append to running log
        with open(self.jsonl_path, "a") as f:
            f.write(json.dumps(data) + "\n")

        # Save individual file
        individual = self.results_dir / "reports" / f"{run.run_id}.json"
        individual.parent.mkdir(parents=True, exist_ok=True)
        with open(individual, "w") as f:
            json.dump(data, f, indent=2, default=_serialize)

        return individual

    def load_all_runs(self) -> list[dict]:
        """Load all runs from JSONL for aggregate reporting."""
        if not self.jsonl_path.exists():
            return []
        runs = []
        with open(self.jsonl_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    runs.append(json.loads(line))
        return runs
```

- [ ] **Step 2: Verify the module loads without errors**

```bash
cd /Users/sigmoid/Documents/projects/stockanalysis/stock-signal-platform
python3 -c "import benchmark.metrics as m; r = m.ModelResult(model_id='test'); print(f'ModelResult OK: {r.model_id}')"
```

Expected: `ModelResult OK: test`

- [ ] **Step 3: Test cost calculation**

```bash
python3 -c "
from benchmark.metrics import real_cost
# Sonnet: 88K input + 5K output
s = real_cost('claude-sonnet-4-6', 88000, 5000)
# MiniMax: same tokens
m = real_cost('MiniMax-M2.5', 88000, 5000)
print(f'Sonnet cost: \${s:.4f}')
print(f'MiniMax cost: \${m:.4f}')
print(f'Ratio: {s/m:.1f}x')
"
```

Expected: Sonnet ~$0.339, MiniMax ~$0.032, Ratio ~10.4x

- [ ] **Step 4: Commit**

```bash
git add benchmark/metrics.py
git commit -m "feat(benchmark): metrics dataclasses, cost calculator, JSONL logger"
```

---

### Task 3: Worktree management helpers

**Files:**
- Create: `benchmark/worktree.py`

- [ ] **Step 1: Create `benchmark/worktree.py`**

```python
"""Git worktree management for parallel model benchmarking."""

from __future__ import annotations

import subprocess
import shutil
from pathlib import Path


def run_git(args: list[str], cwd: str | None = None) -> subprocess.CompletedProcess:
    """Run a git command and return the result."""
    return subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=60,
    )


def get_project_root() -> Path:
    """Get the git repo root directory."""
    result = run_git(["rev-parse", "--show-toplevel"])
    if result.returncode != 0:
        raise RuntimeError(f"Not in a git repo: {result.stderr}")
    return Path(result.stdout.strip())


def create_worktrees(
    model_ids: list[str],
    base_branch: str = "develop",
    worktree_dir: str = ".benchmark",
) -> dict[str, Path]:
    """Create one worktree per model, all branching from base_branch.

    Returns dict of model_id → worktree path.
    """
    root = get_project_root()
    wt_base = root / worktree_dir
    wt_base.mkdir(parents=True, exist_ok=True)

    # Ensure base branch is up to date
    run_git(["checkout", base_branch], cwd=str(root))
    run_git(["pull", "origin", base_branch], cwd=str(root))

    worktrees: dict[str, Path] = {}
    for model_id in model_ids:
        safe_name = model_id.lower().replace(".", "-").replace(" ", "-")
        wt_name = f"wt-{safe_name}"
        wt_path = wt_base / wt_name
        branch_name = f"benchmark/{safe_name}"

        # Clean up if exists from a previous failed run
        if wt_path.exists():
            run_git(["worktree", "remove", str(wt_path), "--force"], cwd=str(root))

        # Delete branch if it exists
        run_git(["branch", "-D", branch_name], cwd=str(root))

        # Create worktree with new branch
        result = run_git(
            ["worktree", "add", "-b", branch_name, str(wt_path), base_branch],
            cwd=str(root),
        )
        if result.returncode != 0:
            raise RuntimeError(f"Failed to create worktree for {model_id}: {result.stderr}")

        worktrees[model_id] = wt_path

    return worktrees


def collect_git_metrics(worktree_path: Path) -> dict:
    """Collect git diff metrics from a worktree."""
    cwd = str(worktree_path)

    # Files changed
    stat = run_git(["diff", "--stat", "HEAD"], cwd=cwd)
    files_changed = 0
    for line in stat.stdout.strip().split("\n"):
        if " | " in line:
            files_changed += 1

    # Lines added/removed
    numstat = run_git(["diff", "--numstat", "HEAD"], cwd=cwd)
    lines_added = 0
    lines_removed = 0
    for line in numstat.stdout.strip().split("\n"):
        parts = line.split("\t")
        if len(parts) >= 2:
            try:
                lines_added += int(parts[0]) if parts[0] != "-" else 0
                lines_removed += int(parts[1]) if parts[1] != "-" else 0
            except ValueError:
                pass

    # Full diff for judge
    diff = run_git(["diff", "HEAD"], cwd=cwd)

    return {
        "files_changed": files_changed,
        "lines_added": lines_added,
        "lines_removed": lines_removed,
        "diff_text": diff.stdout[:50000],  # cap at 50K chars for judge prompt
    }


def run_tests_in_worktree(worktree_path: Path) -> dict:
    """Run pytest in a worktree and parse results."""
    result = subprocess.run(
        ["uv", "run", "pytest", "tests/unit/", "-q", "--tb=short", "--no-header"],
        cwd=str(worktree_path),
        capture_output=True,
        text=True,
        timeout=120,
    )

    output = result.stdout + result.stderr
    tests_total = 0
    tests_passed = 0
    tests_failed = 0

    # Parse pytest summary line like "5 passed, 2 failed"
    for line in output.split("\n"):
        line = line.strip()
        if "passed" in line or "failed" in line or "error" in line:
            import re
            passed = re.search(r"(\d+) passed", line)
            failed = re.search(r"(\d+) failed", line)
            errors = re.search(r"(\d+) error", line)
            if passed:
                tests_passed = int(passed.group(1))
            if failed:
                tests_failed = int(failed.group(1))
            if errors:
                tests_failed += int(errors.group(1))
            tests_total = tests_passed + tests_failed

    return {
        "tests_total": tests_total,
        "tests_passed": tests_passed,
        "tests_failed": tests_failed,
        "test_output": output[:10000],  # cap for judge prompt
    }


def run_lint_in_worktree(worktree_path: Path) -> dict:
    """Run ruff check in a worktree and count violations."""
    result = subprocess.run(
        ["uv", "run", "ruff", "check", "--statistics", "backend/"],
        cwd=str(worktree_path),
        capture_output=True,
        text=True,
        timeout=60,
    )

    output = result.stdout + result.stderr
    violations = 0
    for line in output.split("\n"):
        line = line.strip()
        if line and line[0].isdigit():
            try:
                violations += int(line.split()[0])
            except (ValueError, IndexError):
                pass

    return {
        "lint_violations": violations,
        "lint_output": output[:5000],
    }


def create_pr_from_worktree(
    worktree_path: Path,
    model_id: str,
    task_name: str,
    task_id: str,
    score: float,
    cost: float,
) -> int | None:
    """Create a PR from winner's worktree branch to develop."""
    cwd = str(worktree_path)

    # Stage and commit all changes
    run_git(["add", "-A"], cwd=cwd)
    commit_result = run_git(
        ["commit", "-m", f"feat: {task_name} (benchmark winner: {model_id}, score: {score:.1f})"],
        cwd=cwd,
    )
    if commit_result.returncode != 0:
        return None

    # Push the branch
    branch = run_git(["branch", "--show-current"], cwd=cwd).stdout.strip()
    push_result = run_git(["push", "origin", branch], cwd=cwd)
    if push_result.returncode != 0:
        return None

    # Create PR via gh
    pr_result = subprocess.run(
        [
            "gh", "pr", "create",
            "--base", "develop",
            "--head", branch,
            "--title", f"[Benchmark] {task_name}",
            "--body", (
                f"## Benchmark Result\n\n"
                f"- **Winner:** {model_id}\n"
                f"- **Score:** {score:.1f}/10\n"
                f"- **Cost:** ${cost:.4f}\n"
                f"- **Task:** {task_id}\n\n"
                f"Generated by model benchmark framework.\n\n"
                f"🤖 Generated with [Claude Code](https://claude.com/claude-code)"
            ),
        ],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=30,
    )

    if pr_result.returncode == 0:
        # Parse PR number from URL
        url = pr_result.stdout.strip()
        try:
            return int(url.rstrip("/").split("/")[-1])
        except (ValueError, IndexError):
            return None
    return None


def cleanup_worktrees(
    model_ids: list[str],
    worktree_dir: str = ".benchmark",
) -> None:
    """Remove all benchmark worktrees and their branches."""
    root = get_project_root()
    wt_base = root / worktree_dir

    for model_id in model_ids:
        safe_name = model_id.lower().replace(".", "-").replace(" ", "-")
        wt_path = wt_base / f"wt-{safe_name}"
        branch_name = f"benchmark/{safe_name}"

        if wt_path.exists():
            run_git(["worktree", "remove", str(wt_path), "--force"], cwd=str(root))

        run_git(["branch", "-D", branch_name], cwd=str(root))

    # Remove empty worktree dir
    if wt_base.exists() and not any(wt_base.iterdir()):
        wt_base.rmdir()
```

- [ ] **Step 2: Verify imports work**

```bash
python3 -c "from benchmark.worktree import get_project_root; print(f'Root: {get_project_root()}')"
```

Expected: prints the project root path.

- [ ] **Step 3: Commit**

```bash
git add benchmark/worktree.py
git commit -m "feat(benchmark): worktree create/cleanup/PR helpers"
```

---

### Task 4: Opus judge — blind scoring + fix estimation

**Files:**
- Create: `benchmark/judge.py`
- Create: `benchmark/judge-prompt.md`

- [ ] **Step 1: Create `benchmark/judge-prompt.md`**

```markdown
You are an expert code reviewer evaluating {impl_count} implementations of the same coding task.
Score each INDEPENDENTLY on the rubric below. Do not let one implementation bias your scoring of another.

## Task
{task_description}

## Project Conventions (relevant excerpt)
- Python: async by default, type hints required, no str(e) in user-facing output
- Tests: pytest (not unittest), factory-boy for fixtures, bare functions not classes
- DB: SQLAlchemy async, Alembic migrations must not drop TimescaleDB indexes
- Naming: snake_case for Python, kebab-case for URLs, PascalCase for models/schemas
- Error handling: log real error, return safe generic message

## Scoring Rubric
{rubric_yaml}

{implementations_block}

Respond in JSON ONLY. No markdown fences. No preamble. No explanation outside JSON.

{scoring_json_schema}
```

- [ ] **Step 2: Create `benchmark/judge.py`**

```python
"""Opus blind review: scoring + fix estimation via direct Anthropic API."""

from __future__ import annotations

import json
import os
import random
import string
from pathlib import Path

import httpx

from benchmark.metrics import (
    OpusScores,
    OpusReview,
    FixAction,
    FixSummary,
    real_cost,
)


ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
JUDGE_MODEL = "claude-opus-4-6"


def _call_opus(system: str, user: str, max_tokens: int = 4096) -> tuple[str, int, int]:
    """Make a direct API call to Opus. Returns (response_text, input_tokens, output_tokens)."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set — needed for Opus judge")

    with httpx.Client(timeout=300) as client:
        resp = client.post(
            ANTHROPIC_API_URL,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": JUDGE_MODEL,
                "max_tokens": max_tokens,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
        )
        resp.raise_for_status()
        data = resp.json()

    text = ""
    for block in data.get("content", []):
        if block.get("type") == "text":
            text += block["text"]

    usage = data.get("usage", {})
    return text, usage.get("input_tokens", 0), usage.get("output_tokens", 0)


def _load_rubric() -> str:
    """Load scoring rubric YAML as string."""
    rubric_path = Path(__file__).parent / "scoring_rubric.yaml"
    return rubric_path.read_text()


def _anonymize(model_ids: list[str]) -> tuple[dict[str, str], dict[str, str]]:
    """Create random anonymization mapping. Returns (model→label, label→model)."""
    labels = list(string.ascii_uppercase[: len(model_ids)])
    random.shuffle(labels)
    model_to_label = dict(zip(model_ids, labels))
    label_to_model = {v: k for k, v in model_to_label.items()}
    return model_to_label, label_to_model


class OpusJudge:
    """Two-pass Opus review: blind scoring then fix estimation."""

    def __init__(self) -> None:
        self.total_input_tokens = 0
        self.total_output_tokens = 0

    def score(
        self,
        task_description: str,
        implementations: dict[str, dict],  # model_id → {diff_text, test_output, lint_output}
    ) -> OpusReview:
        """Pass 1: Blind comparative scoring of all implementations."""
        model_ids = list(implementations.keys())
        model_to_label, label_to_model = _anonymize(model_ids)
        rubric = _load_rubric()

        # Build implementations block
        impl_blocks = []
        for model_id in model_ids:
            label = model_to_label[model_id]
            impl = implementations[model_id]
            impl_blocks.append(
                f"## Implementation {label}\n"
                f"### Code Changes\n```diff\n{impl.get('diff_text', 'NO DIFF')}\n```\n"
                f"### Test Output\n```\n{impl.get('test_output', 'NO TESTS RUN')}\n```\n"
                f"### Lint Output\n```\n{impl.get('lint_output', 'NO LINT RUN')}\n```"
            )

        scoring_schema = json.dumps({
            "implementations": {
                label: {
                    "scores": {
                        "correctness": "N", "convention_adherence": "N",
                        "integration_safety": "N", "completeness": "N",
                        "code_quality": "N", "first_pass_success": "N",
                    },
                    "weighted_score": "N.N",
                    "specific_issues": ["..."],
                    "strengths": ["..."],
                    "would_need_rewrite": "bool",
                    "required_codebase_reads": "N",
                    "convention_violations": ["..."],
                    "hallucinated_apis": "N",
                    "over_engineering_score": "1-5",
                    "under_engineering_score": "1-5",
                    "self_correction_attempts": "N",
                    "self_correction_success_rate": "0.0-1.0",
                    "dead_end_tools": "N",
                    "codebase_awareness": "1-5",
                    "post_complexity_score": "7-35",
                    "post_complexity_reason": "...",
                }
                for label in sorted(model_to_label.values())
            },
            "ranking": ["A", "B", "C"],
            "winner": "A",
            "winner_rationale": "...",
            "comparative_notes": "...",
        }, indent=2)

        system = (
            "You are an expert code reviewer. Score implementations independently. "
            "Respond in valid JSON only. No markdown. No preamble."
        )
        user = (
            f"## Task\n{task_description}\n\n"
            f"## Project Conventions\n"
            "- Python: async by default, type hints, no str(e) in user-facing output\n"
            "- Tests: pytest bare functions, factory-boy fixtures\n"
            "- DB: SQLAlchemy async, Alembic (no TimescaleDB index drops)\n"
            "- Naming: snake_case Python, kebab-case URLs, PascalCase models\n\n"
            f"## Scoring Rubric\n```yaml\n{rubric}\n```\n\n"
            + "\n\n".join(impl_blocks) +
            f"\n\nRespond in this exact JSON format:\n{scoring_schema}"
        )

        response_text, input_tokens, output_tokens = _call_opus(system, user, max_tokens=4096)
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens

        # Parse JSON response
        try:
            data = json.loads(response_text)
        except json.JSONDecodeError:
            # Try to extract JSON from response
            start = response_text.find("{")
            end = response_text.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(response_text[start:end])
            else:
                raise

        # De-anonymize and build OpusReview
        review = OpusReview()
        review.review_input_tokens = input_tokens
        review.review_output_tokens = output_tokens

        for label, scores_data in data.get("implementations", {}).items():
            model_id = label_to_model.get(label, label)
            opus_scores = OpusScores(
                correctness=scores_data.get("scores", {}).get("correctness", 0),
                convention_adherence=scores_data.get("scores", {}).get("convention_adherence", 0),
                integration_safety=scores_data.get("scores", {}).get("integration_safety", 0),
                completeness=scores_data.get("scores", {}).get("completeness", 0),
                code_quality=scores_data.get("scores", {}).get("code_quality", 0),
                first_pass_success=scores_data.get("scores", {}).get("first_pass_success", 0),
                specific_issues=scores_data.get("specific_issues", []),
                strengths=scores_data.get("strengths", []),
                would_need_rewrite=scores_data.get("would_need_rewrite", False),
                required_codebase_reads=scores_data.get("required_codebase_reads", 0),
                convention_violations=scores_data.get("convention_violations", []),
                hallucinated_apis=scores_data.get("hallucinated_apis", 0),
                over_engineering_score=scores_data.get("over_engineering_score", 1),
                under_engineering_score=scores_data.get("under_engineering_score", 1),
                self_correction_attempts=scores_data.get("self_correction_attempts", 0),
                self_correction_success_rate=scores_data.get("self_correction_success_rate", 0.0),
                dead_end_tools=scores_data.get("dead_end_tools", 0),
                codebase_awareness=scores_data.get("codebase_awareness", 1),
                post_complexity_score=scores_data.get("post_complexity_score", 0),
                post_complexity_reason=scores_data.get("post_complexity_reason", ""),
            )
            opus_scores.calculate_weighted()
            review.scores[model_id] = opus_scores

        # De-anonymize ranking and winner
        ranking_labels = data.get("ranking", [])
        review.ranking = [label_to_model.get(l, l) for l in ranking_labels]
        winner_label = data.get("winner", "")
        review.winner = label_to_model.get(winner_label, winner_label)
        review.winner_rationale = data.get("winner_rationale", "")
        review.comparative_notes = data.get("comparative_notes", "")
        review.calculate_cost()

        return review

    def estimate_fixes(
        self,
        task_description: str,
        model_id: str,
        diff_text: str,
        test_output: str,
    ) -> FixSummary:
        """Pass 2: Estimate fixes needed for one implementation."""
        system = (
            "You are a staff engineer estimating the work to make this code merge-ready. "
            "Respond in valid JSON only."
        )
        fix_schema = json.dumps({
            "fix_actions": [
                {
                    "file": "path/to/file.py",
                    "type": "bug|convention|missing_feature|security|over_engineering|test_gap",
                    "severity": "critical|high|medium|low",
                    "description": "What needs fixing and why",
                    "estimated_fix_lines": 0,
                    "estimated_fix_minutes": 0,
                }
            ],
        }, indent=2)

        user = (
            f"## Task\n{task_description}\n\n"
            f"## Code Changes\n```diff\n{diff_text[:30000]}\n```\n\n"
            f"## Test Output\n```\n{test_output[:5000]}\n```\n\n"
            f"List ALL fixes needed to make this merge-ready. "
            f"If the code is perfect, return empty fix_actions array.\n\n"
            f"JSON format:\n{fix_schema}"
        )

        response_text, input_tokens, output_tokens = _call_opus(system, user, max_tokens=2048)
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens

        try:
            data = json.loads(response_text)
        except json.JSONDecodeError:
            start = response_text.find("{")
            end = response_text.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(response_text[start:end])
            else:
                data = {"fix_actions": []}

        summary = FixSummary(model_id=model_id, opus_fix_tokens=input_tokens + output_tokens)
        for action_data in data.get("fix_actions", []):
            summary.fix_actions.append(FixAction(
                file=action_data.get("file", ""),
                fix_type=action_data.get("type", "bug"),
                severity=action_data.get("severity", "medium"),
                description=action_data.get("description", ""),
                estimated_fix_lines=action_data.get("estimated_fix_lines", 0),
                estimated_fix_minutes=action_data.get("estimated_fix_minutes", 0),
            ))
        summary.calculate()

        return summary
```

- [ ] **Step 3: Verify imports**

```bash
python3 -c "from benchmark.judge import OpusJudge; j = OpusJudge(); print('OpusJudge OK')"
```

Expected: `OpusJudge OK` (requires httpx installed: `pip install httpx`)

- [ ] **Step 4: Commit**

```bash
git add benchmark/judge.py benchmark/judge-prompt.md
git commit -m "feat(benchmark): Opus blind judge with scoring + fix estimation"
```

---

### Task 5: Report generator

**Files:**
- Create: `benchmark/report.py`

- [ ] **Step 1: Create `benchmark/report.py`**

This file generates all 4 report types from the spec. It's the largest single file because the reports require comprehensive data aggregation and the spec's explainability principles (context for every number, "so what" after every table, traffic lights, glossary).

```python
"""Generate all 4 report types from benchmark JSONL data.

Report 1: Per-Task Report (after each task)
Report 2: Failure Pattern Analysis (after 4+ tasks)
Report 3: CTO Decision Brief (after all tasks)
Report 4: Enterprise Readiness Assessment (optional)
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path


def _fmt(v: float) -> str:
    """Format cost with appropriate precision."""
    return f"${v:.4f}" if v < 1 else f"${v:.2f}"


def _tl(score: float) -> str:
    """Traffic light indicator for quality scores."""
    if score >= 7.5:
        return "✅"
    if score >= 5.0:
        return "⚠️"
    return "❌"


def _avg(lst: list) -> float:
    return sum(lst) / len(lst) if lst else 0.0


def _get_ws(scores: dict, model_id: str) -> float:
    """Extract weighted score safely."""
    s = scores.get(model_id, {})
    return s.get("weighted_score", 0) if isinstance(s, dict) else 0


def _model_short(m: str) -> str:
    """Shorten model ID for table headers."""
    return m.replace("claude-", "").replace("moonshotai/", "")[:18]


# ---------------------------------------------------------------------------
# Report 1: Per-Task Report
# ---------------------------------------------------------------------------

def generate_per_task_report(run: dict, output_dir: Path) -> Path:
    """Report 1 — generated after each benchmark task."""
    task_id = run.get("task_id", "unknown")
    task_name = run.get("task_name", "Unknown Task")
    tier = run.get("task_tier", "?")
    jira = run.get("jira_ticket", "N/A")
    timestamp = run.get("timestamp", "")
    run_id = run.get("run_id", "")
    complexity = run.get("complexity", {})
    models_data = run.get("models", {})
    review = run.get("opus_review", {})
    derived = run.get("derived", {})
    scores = review.get("scores", {})
    fix_summaries = review.get("fix_summaries", {})
    winner = review.get("winner", "N/A")
    model_ids = list(models_data.keys())
    hdrs = [_model_short(m) for m in model_ids]

    def _val(m: str, key: str, fmt: str = "{}") -> str:
        v = models_data.get(m, {}).get(key, "—")
        if isinstance(v, float):
            return fmt.format(v)
        return str(v)

    def _score(m: str, dim: str) -> str:
        s = scores.get(m, {})
        sc = s.get("scores", s) if isinstance(s, dict) else {}
        v = sc.get(dim, s.get(dim, "—")) if isinstance(sc, dict) else "—"
        return f"{v}/10" if isinstance(v, (int, float)) else str(v)

    # Build report
    lines = [
        f"# Benchmark Report — {task_name}\n",
        f"**Task:** {task_id} | **Tier:** {tier} | **JIRA:** {jira}",
        f"**Date:** {timestamp} | **Run ID:** {run_id}",
        f"**Winner:** {winner} | **Total cost:** {_fmt(run.get('total_benchmark_cost_usd', 0))}\n",
    ]

    # Complexity profile
    lines.append("## Complexity Profile (pre-scored)\n")
    lines.append("| Dimension | Score |\n|---|---|")
    for dim in ["context_span", "reasoning_depth", "integration_surface",
                 "convention_density", "implicit_knowledge", "verification_difficulty", "failure_cost"]:
        lines.append(f"| {dim.replace('_', ' ').title()} | {complexity.get(dim, '?')}/5 |")
    total = complexity.get("total", sum(complexity.get(d, 0) for d in [
        "context_span", "reasoning_depth", "integration_surface",
        "convention_density", "implicit_knowledge", "verification_difficulty", "failure_cost"]))
    lines.append(f"| **Total** | **{total}/35 → {tier}** |\n")

    # Results summary
    sep = " | ".join(["---"] * (len(model_ids) + 1))
    lines.append("## Results Summary\n")
    lines.append(f"| Metric | {' | '.join(hdrs)} |")
    lines.append(f"|{sep}|")

    # Weighted score row with traffic lights
    ws_cells = []
    for m in model_ids:
        ws = _get_ws(scores, m)
        ws_cells.append(f"{_tl(ws)} {ws:.1f}/10")
    lines.append(f"| **Weighted Score** | {' | '.join(ws_cells)} |")

    for label, key, fmt in [
        ("Tests Passed", "tests_passed", "{}"), ("Tests Total", "tests_total", "{}"),
        ("Lint Violations", "lint_violations", "{}"),
        ("First-Pass Success", "first_pass_success", "{}"),
        ("Input Tokens", "input_tokens", "{:,}"), ("Output Tokens", "output_tokens", "{:,}"),
        ("**Actual Cost**", "actual_cost_usd", "${:.4f}"),
        ("Wall Clock", "wall_clock_ms", "{:.0f}ms"),
        ("Tokens/sec", "tokens_per_second", "{:.0f}"),
        ("Turns", "num_turns", "{}"),
        ("Files Changed", "files_changed", "{}"),
        ("Lines Added", "lines_added", "{}"),
    ]:
        cells = [_val(m, key, fmt) for m in model_ids]
        lines.append(f"| {label} | {' | '.join(cells)} |")

    # So what line
    winner_ws = _get_ws(scores, winner)
    winner_cost = models_data.get(winner, {}).get("actual_cost_usd", 0)
    sonnet_cost = models_data.get("claude-sonnet-4-6", {}).get("actual_cost_usd", 0)
    if winner != "claude-sonnet-4-6" and sonnet_cost > 0 and winner_cost > 0:
        ratio = sonnet_cost / winner_cost
        lines.append(f"\n**So what:** {winner} won this task with a score of {winner_ws:.1f}/10 "
                      f"at {_fmt(winner_cost)} — {ratio:.0f}x cheaper than Sonnet's {_fmt(sonnet_cost)}.\n")
    else:
        lines.append(f"\n**So what:** {winner} produced the highest quality implementation ({winner_ws:.1f}/10).\n")

    # Dimension scores
    lines.append("## Dimension Scores (Opus Blind Review)\n")
    lines.append(f"| Dimension (weight) | {' | '.join(hdrs)} |")
    lines.append(f"|{sep}|")
    for dim, weight in [("correctness", "25%"), ("convention_adherence", "20%"),
                         ("integration_safety", "20%"), ("completeness", "15%"),
                         ("code_quality", "10%"), ("first_pass_success", "10%")]:
        cells = [_score(m, dim) for m in model_ids]
        lines.append(f"| {dim.replace('_', ' ').title()} ({weight}) | {' | '.join(cells)} |")

    # Opus review findings
    lines.append(f"\n## Opus Review — Key Findings\n")
    lines.append(f"### Winner: {winner} (Score: {winner_ws:.1f})")
    lines.append(f'> "An independent AI reviewer, not knowing which model produced which code, '
                  f'chose {_model_short(winner)} because: {review.get("winner_rationale", "N/A")}"\n')

    # Complexity assessment
    lines.append("### Complexity Assessment (Opus post-hoc)\n")
    lines.append(f"| Metric | {' | '.join(hdrs)} |")
    lines.append(f"|{sep}|")
    for metric in ["codebase_awareness", "over_engineering_score", "under_engineering_score",
                    "hallucinated_apis", "self_correction_attempts", "dead_end_tools", "post_complexity_score"]:
        cells = []
        for m in model_ids:
            s = scores.get(m, {})
            v = s.get(metric, "—") if isinstance(s, dict) else "—"
            cells.append(str(v))
        label = metric.replace("_", " ").title()
        lines.append(f"| {label} | {' | '.join(cells)} |")

    # Fix estimation (staff engineer burden)
    if fix_summaries:
        lines.append("\n### Staff Engineer Fix Estimation\n")
        lines.append(f"| Metric | {' | '.join(hdrs)} |")
        lines.append(f"|{sep}|")
        for label, key in [("Fix Actions", "total_actions"), ("Fix Minutes", "total_fix_minutes"),
                            ("Would Block PR", "would_block_pr"), ("Staff Hours", "staff_engineer_equivalent_hours")]:
            cells = []
            for m in model_ids:
                fs = fix_summaries.get(m, {})
                v = fs.get(key, "—") if isinstance(fs, dict) else "—"
                if isinstance(v, float):
                    cells.append(f"{v:.2f}")
                else:
                    cells.append(str(v))
            lines.append(f"| {label} | {' | '.join(cells)} |")

    # Cost efficiency
    lines.append("\n## Cost Efficiency\n")
    lines.append(f"| Metric | {' | '.join(hdrs)} |")
    lines.append(f"|{sep}|")
    for label, key, fmt in [
        ("Cost/Quality Point ($/QP)", "cost_per_quality_point", "${:.4f}"),
        ("Cost vs Sonnet", "cost_ratio_vs_sonnet", "{:.2f}x"),
        ("Speed vs Sonnet", "speed_ratio_vs_sonnet", "{:.2f}x"),
        ("Value Score (Q/$)", "value_score", "{:.0f}"),
        ("Net Cost (impl+review+staff)", "net_cost", "${:.4f}"),
    ]:
        cells = []
        for m in model_ids:
            d = derived.get(m, {})
            v = d.get(key, 0) if isinstance(d, dict) else 0
            cells.append(fmt.format(v) if isinstance(v, (int, float)) else str(v))
        lines.append(f"| {label} | {' | '.join(cells)} |")

    lines.append(f"\n## Decision")
    lines.append(f"- **Merged:** {run.get('winner_merged', 'TBD')} → PR #{run.get('pr_number', 'TBD')}")
    lines.append(f"- **Task cost:** {_fmt(run.get('total_benchmark_cost_usd', 0))}")

    output_path = output_dir / f"{run_id}.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines))
    return output_path


# ---------------------------------------------------------------------------
# Report 2: Failure Pattern Analysis
# ---------------------------------------------------------------------------

def generate_failure_analysis(runs: list[dict], output_dir: Path) -> Path:
    """Report 2 — generated after 4+ tasks. Catalogs how each model fails."""
    model_ids = list(runs[0].get("models", {}).keys())
    n = len(runs)

    # Collect failure patterns per model
    model_patterns: dict[str, list[dict]] = defaultdict(list)
    tier_results: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))

    for run in runs:
        review = run.get("opus_review", {})
        scores = review.get("scores", {})
        fix_summaries = review.get("fix_summaries", {})
        tier = run.get("task_tier", "?")
        task_id = run.get("task_id", "")

        for m in model_ids:
            ws = _get_ws(scores, m)
            tier_results[tier][m].append(ws)

            s = scores.get(m, {}) if isinstance(scores.get(m), dict) else {}
            fixes = fix_summaries.get(m, {}) if isinstance(fix_summaries.get(m), dict) else {}

            # Collect specific issues as patterns
            for issue in s.get("specific_issues", []):
                model_patterns[m].append({"issue": issue, "task": task_id, "tier": tier, "score": ws})
            for violation in s.get("convention_violations", []):
                model_patterns[m].append({"issue": f"Convention: {violation}", "task": task_id, "tier": tier, "score": ws})
            if s.get("hallucinated_apis", 0) > 0:
                model_patterns[m].append({"issue": f"Hallucinated {s['hallucinated_apis']} APIs", "task": task_id, "tier": tier, "score": ws})

    lines = [
        f"# Failure Pattern Analysis — After {n} Tasks\n",
        "## Model Failure Modes\n",
    ]

    for m in model_ids:
        lines.append(f"### {_model_short(m)}\n")
        patterns = model_patterns.get(m, [])
        if not patterns:
            lines.append("No failure patterns detected.\n")
            continue
        lines.append("| Pattern | Task | Tier | Score |")
        lines.append("|---|---|---|---|")
        for p in patterns[:20]:  # cap at 20
            lines.append(f"| {p['issue'][:80]} | {p['task']} | {p['tier']} | {p['score']:.1f} |")
        lines.append("")

    # Capability ceiling by tier
    lines.append("## Capability Ceiling by Tier\n")
    lines.append(f"| Tier | {' | '.join(_model_short(m) for m in model_ids)} | Notes |")
    lines.append(f"|---|{'---|' * len(model_ids)}---|")

    for tier in sorted(tier_results.keys()):
        cells = []
        notes = []
        for m in model_ids:
            a = _avg(tier_results[tier][m])
            cells.append(f"{_tl(a)} {a:.1f}")
            if a < 5.0:
                notes.append(f"{_model_short(m)} fails")
        notes_str = "; ".join(notes) if notes else "All viable"
        lines.append(f"| {tier} | {' | '.join(cells)} | {notes_str} |")

    lines.append(f"\nLegend: ✅ ≥7.5 avg (merge-ready) | ⚠️ 5.0–7.4 (needs fixes) | ❌ <5.0 (reject)\n")

    # Interim assessment
    lines.append("## Interim Assessment\n")
    for m in model_ids:
        all_scores = [_get_ws(r.get("opus_review", {}).get("scores", {}), m) for r in runs]
        a = _avg(all_scores)
        if a >= 7.5:
            status = "✅ On track"
        elif a >= 5.0:
            status = "⚠️ Struggling"
        else:
            status = "❌ Failing"
        lines.append(f"- **{_model_short(m)}:** {status} — avg score {a:.1f}/10 across {n} tasks")

    output_path = output_dir / "failure-analysis.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines))
    return output_path


# ---------------------------------------------------------------------------
# Report 3: CTO Decision Brief
# ---------------------------------------------------------------------------

def generate_cto_brief(runs: list[dict], output_dir: Path, monthly_task_volume: int = 40, staff_rate: float = 95.0) -> Path:
    """Report 3 — the main deliverable. Generated after all tasks."""
    if not runs:
        p = output_dir / "cto-decision-brief.md"
        p.write_text("# No benchmark data available.\n")
        return p

    model_ids = list(runs[0].get("models", {}).keys())
    n_tasks = len(runs)
    total_cost = sum(r.get("total_benchmark_cost_usd", 0) for r in runs)

    # Aggregate stats
    stats: dict[str, dict] = {m: {
        "scores": [], "costs": [], "times": [], "wins": 0, "tasks": 0,
        "fix_minutes": [], "pr_blocks": 0,
        "fix_types": defaultdict(int), "dim_scores": defaultdict(list),
        "hallucinated": [], "dead_ends": [], "self_corrections": [],
    } for m in model_ids}

    tier_scores: dict[str, dict[str, list]] = defaultdict(lambda: {m: [] for m in model_ids})
    tier_costs: dict[str, dict[str, list]] = defaultdict(lambda: {m: [] for m in model_ids})
    complexity_scores: dict[str, dict[str, list]] = defaultdict(lambda: {m: [] for m in model_ids})

    for run in runs:
        review = run.get("opus_review", {})
        sc = review.get("scores", {})
        fix_sums = review.get("fix_summaries", {})
        tier = run.get("task_tier", "?")
        winner = review.get("winner", "")
        cx = run.get("complexity", {})
        cx_total = cx.get("total", 0) if isinstance(cx, dict) else 0
        cx_band = "7-12" if cx_total <= 12 else "13-18" if cx_total <= 18 else "19-25" if cx_total <= 25 else "26-35"

        for m in model_ids:
            md = run.get("models", {}).get(m, {})
            s = sc.get(m, {}) if isinstance(sc.get(m), dict) else {}
            fs = fix_sums.get(m, {}) if isinstance(fix_sums.get(m), dict) else {}
            ws = s.get("weighted_score", 0)
            cost = md.get("actual_cost_usd", 0)
            time_ms = md.get("wall_clock_ms", 0)

            stats[m]["scores"].append(ws)
            stats[m]["costs"].append(cost)
            stats[m]["times"].append(time_ms / 1000 if time_ms else 0)
            stats[m]["tasks"] += 1
            if m == winner:
                stats[m]["wins"] += 1
            stats[m]["fix_minutes"].append(fs.get("total_fix_minutes", 0))
            if fs.get("would_block_pr"):
                stats[m]["pr_blocks"] += 1
            for ft, cnt in fs.get("by_type", {}).items():
                stats[m]["fix_types"][ft] += cnt
            stats[m]["hallucinated"].append(s.get("hallucinated_apis", 0))
            stats[m]["dead_ends"].append(s.get("dead_end_tools", 0))
            stats[m]["self_corrections"].append(s.get("self_correction_success_rate", 0))

            for dim in ["correctness", "convention_adherence", "integration_safety",
                         "completeness", "code_quality", "first_pass_success"]:
                v = s.get("scores", s).get(dim, s.get(dim, 0)) if isinstance(s, dict) else 0
                stats[m]["dim_scores"][dim].append(v if isinstance(v, (int, float)) else 0)

            tier_scores[tier][m].append(ws)
            tier_costs[tier][m].append(cost)
            complexity_scores[cx_band][m].append(ws)

    lines = [
        "# Model Benchmark — CTO Decision Brief\n",
        f"**Date:** {runs[-1].get('timestamp', '')[:10]}",
        f"**Benchmark scope:** {n_tasks} real JIRA tasks across {len(set(r.get('task_tier','?') for r in runs))} complexity tiers",
        f"**Models tested:** {', '.join(_model_short(m) for m in model_ids)}",
        f"**Total benchmark cost:** {_fmt(total_cost)} | **Tasks merged to develop:** {n_tasks}\n",
        "---\n",
        "## How This Benchmark Was Conducted\n",
        "This benchmark was fully automated using Claude Code agents. Every task was a real JIRA "
        "ticket from our backlog — the winning implementation was merged into the codebase. "
        "The reviewer (Opus 4.6) scored all implementations blind, without knowing which model "
        "produced which code. Model identities were revealed only after scores were locked.\n",
        "---\n",
    ]

    # Executive summary — find best value model
    sonnet_avg = _avg(stats.get("claude-sonnet-4-6", {}).get("scores", []))
    best_value = max(model_ids, key=lambda m: _avg(stats[m]["scores"]) / max(_avg(stats[m]["costs"]), 0.001))
    bv_avg = _avg(stats[best_value]["scores"])
    bv_cost = _avg(stats[best_value]["costs"])
    son_cost = _avg(stats.get("claude-sonnet-4-6", {}).get("costs", [1]))
    pct_quality = (bv_avg / sonnet_avg * 100) if sonnet_avg > 0 else 0
    pct_cost = (bv_cost / son_cost * 100) if son_cost > 0 else 0

    lines.append("## Executive Summary\n")
    lines.append(f"> {_model_short(best_value)} delivers {pct_quality:.0f}% of Sonnet's quality "
                  f"at {pct_cost:.0f}% of the cost. " if best_value != "claude-sonnet-4-6" else
                  f"> Sonnet 4.6 remains the quality leader. ")
    lines.append("")

    # Overall performance table
    lines.append("## Head-to-Head Results\n")
    lines.append("### Overall Performance\n")
    lines.append("| Model | Avg Score | Win Rate | Avg Cost | $/QP | Avg Time | Value (Q/$) |")
    lines.append("|---|---|---|---|---|---|---|")
    for m in model_ids:
        s = stats[m]
        a_score = _avg(s["scores"])
        win_rate = (s["wins"] / s["tasks"] * 100) if s["tasks"] else 0
        a_cost = _avg(s["costs"])
        cpqp = a_cost / a_score if a_score > 0 else 0
        a_time = _avg(s["times"])
        value = a_score / a_cost if a_cost > 0 else 0
        lines.append(f"| {_model_short(m)} | {_tl(a_score)} {a_score:.1f}/10 | {win_rate:.0f}% | "
                      f"{_fmt(a_cost)} | {_fmt(cpqp)} | {a_time:.0f}s | {value:.0f} |")

    lines.append(f"\n**So what:** The best value model is {_model_short(best_value)} at "
                  f"{_fmt(_avg(stats[best_value]['costs']))}/task.\n")

    # Performance by tier
    lines.append("### Performance by Tier\n")
    lines.append(f"| Tier | Tasks | {' | '.join(_model_short(m) for m in model_ids)} | Best Value |")
    lines.append(f"|---|---|{'---|' * len(model_ids)}---|")
    for tier in sorted(tier_scores.keys()):
        n = len(tier_scores[tier].get(model_ids[0], []))
        cells = []
        avgs = {}
        for m in model_ids:
            a = _avg(tier_scores[tier][m])
            avgs[m] = a
            cells.append(f"{_tl(a)} {a:.1f}")
        best_t = max(model_ids, key=lambda m: avgs.get(m, 0) / max(_avg(stats[m]["costs"]), 0.001))
        lines.append(f"| {tier} | {n} | {' | '.join(cells)} | {_model_short(best_t)} |")

    # Quality floor analysis
    lines.append("\n### Quality Floor Analysis\n")
    lines.append(f"| Model | ≥7.5 (merge-ready) | 5.0–7.4 (fix needed) | <5.0 (reject) |")
    lines.append("|---|---|---|---|")
    for m in model_ids:
        sc = stats[m]["scores"]
        merge = sum(1 for s in sc if s >= 7.5)
        fix = sum(1 for s in sc if 5.0 <= s < 7.5)
        reject = sum(1 for s in sc if s < 5.0)
        t = len(sc)
        lines.append(f"| {_model_short(m)} | {merge}/{t} ({merge/t*100:.0f}%) | {fix}/{t} | {reject}/{t} |")

    lines.append(f"\n**So what:** Models with high merge-ready rates can be used with minimal human review.\n")

    # Monthly cost projection
    lines.append("---\n\n## Cost Projection — Monthly Impact\n")
    t12_pct = 0.67  # assumed T1-T2 percentage
    t34_pct = 0.33

    lines.append("### Current state (Sonnet-only)\n")
    son_avg_cost = _avg(stats.get("claude-sonnet-4-6", {}).get("costs", [0.55]))
    total_monthly_current = monthly_task_volume * son_avg_cost
    lines.append(f"| Item | Monthly volume | Unit cost | Monthly cost |")
    lines.append("|---|---|---|---|")
    lines.append(f"| All tasks via Sonnet | ~{monthly_task_volume} | ~{_fmt(son_avg_cost)}/task | {_fmt(total_monthly_current)} |")
    lines.append(f"| **Total** | | | **{_fmt(total_monthly_current)}/mo** |\n")

    # Proposed state
    bv_id = best_value if best_value != "claude-sonnet-4-6" else model_ids[1] if len(model_ids) > 1 else model_ids[0]
    bv_cost_avg = _avg(stats[bv_id]["costs"])
    t12_vol = int(monthly_task_volume * t12_pct)
    t34_vol = monthly_task_volume - t12_vol
    proposed_monthly = t12_vol * bv_cost_avg + t34_vol * son_avg_cost

    lines.append(f"### Proposed state ({_model_short(bv_id)} for T1-T2, Sonnet for T3-T4)\n")
    lines.append(f"| Item | Monthly volume | Unit cost | Monthly cost |")
    lines.append("|---|---|---|---|")
    lines.append(f"| T1-T2 via {_model_short(bv_id)} | ~{t12_vol} | ~{_fmt(bv_cost_avg)}/task | {_fmt(t12_vol * bv_cost_avg)} |")
    lines.append(f"| T3-T4 via Sonnet | ~{t34_vol} | ~{_fmt(son_avg_cost)}/task | {_fmt(t34_vol * son_avg_cost)} |")
    lines.append(f"| **Total** | | | **{_fmt(proposed_monthly)}/mo** |\n")

    savings = total_monthly_current - proposed_monthly
    lines.append("### Savings\n")
    lines.append("| Metric | Value |")
    lines.append("|---|---|")
    lines.append(f"| Monthly savings | **{_fmt(savings)}/mo ({savings/total_monthly_current*100:.0f}% reduction)** |")
    lines.append(f"| Annual savings | **{_fmt(savings * 12)}/yr** |")

    # True cost including staff cleanup
    lines.append("\n### True Cost (including staff engineer cleanup)\n")
    lines.append(f"| Model | Impl cost | Opus review | Staff cleanup | **Net cost/task** | vs Sonnet |")
    lines.append("|---|---|---|---|---|---|")
    sonnet_net = 0
    for m in model_ids:
        impl = _avg(stats[m]["costs"])
        review_share = total_cost / n_tasks / len(model_ids) if n_tasks > 0 else 0
        fix_hrs = _avg(stats[m]["fix_minutes"]) / 60
        staff_cost = fix_hrs * staff_rate
        net = impl + review_share + staff_cost
        if m == "claude-sonnet-4-6":
            sonnet_net = net
        vs = f"{net/sonnet_net*100:.0f}%" if sonnet_net > 0 else "—"
        lines.append(f"| {_model_short(m)} | {_fmt(impl)} | {_fmt(review_share)} | "
                      f"{_fmt(staff_cost)} ({_avg(stats[m]['fix_minutes']):.0f} min) | **{_fmt(net)}** | {vs} |")

    # Staff engineer burden
    lines.append("\n### Staff Engineer Burden by Model\n")
    lines.append(f"| Metric | {' | '.join(_model_short(m) for m in model_ids)} |")
    lines.append(f"|---|{'---|' * len(model_ids)}")
    lines.append(f"| Avg fix minutes/task | {' | '.join(f'{_avg(stats[m][\"fix_minutes\"]):.0f} min' for m in model_ids)} |")
    lines.append(f"| PR block rate | {' | '.join(f'{stats[m][\"pr_blocks\"]/max(stats[m][\"tasks\"],1)*100:.0f}%' for m in model_ids)} |")
    lines.append(f"| Avg hallucinated APIs | {' | '.join(f'{_avg(stats[m][\"hallucinated\"]):.1f}' for m in model_ids)} |")
    lines.append(f"| Avg dead-end tool calls | {' | '.join(f'{_avg(stats[m][\"dead_ends\"]):.1f}' for m in model_ids)} |")

    # Fix type distribution
    lines.append("\n### Fix Type Distribution\n")
    fix_types = ["bug", "convention", "missing_feature", "security", "over_engineering", "test_gap"]
    lines.append(f"| Fix type | {' | '.join(_model_short(m) for m in model_ids)} |")
    lines.append(f"|---|{'---|' * len(model_ids)}")
    for ft in fix_types:
        cells = []
        for m in model_ids:
            cnt = stats[m]["fix_types"].get(ft, 0)
            total_fixes = sum(stats[m]["fix_types"].values())
            pct = (cnt / total_fixes * 100) if total_fixes > 0 else 0
            cells.append(f"{cnt} ({pct:.0f}%)")
        lines.append(f"| {ft.replace('_', ' ').title()} | {' | '.join(cells)} |")

    lines.append(f"\n**Key insight:** Compare bug counts (high cognitive load to fix) vs convention "
                  f"violations (mechanical, low effort). A model with more total fixes but fewer bugs "
                  f"may be cheaper to clean up.\n")

    # Dimension analysis
    lines.append("---\n\n## Dimension Analysis — Where Models Diverge\n")
    lines.append(f"| Dimension | {' | '.join(_model_short(m) for m in model_ids)} | Biggest Gap |")
    lines.append(f"|---|{'---|' * len(model_ids)}---|")
    max_gap_dim = ""
    max_gap = 0
    for dim in ["correctness", "convention_adherence", "integration_safety",
                 "completeness", "code_quality", "first_pass_success"]:
        avgs = {m: _avg(stats[m]["dim_scores"][dim]) for m in model_ids}
        cells = [f"{avgs[m]:.1f}" for m in model_ids]
        gap = max(avgs.values()) - min(avgs.values())
        if gap > max_gap:
            max_gap = gap
            max_gap_dim = dim
        lines.append(f"| {dim.replace('_', ' ').title()} | {' | '.join(cells)} | {gap:.1f} |")

    lines.append(f"\n**Biggest quality gap:** {max_gap_dim.replace('_', ' ')} ({max_gap:.1f} points)")

    # Complexity vs quality correlation
    lines.append("\n---\n\n## Complexity vs Quality Correlation\n")
    lines.append("### Score by Complexity Band\n")
    lines.append(f"| Complexity | Tasks | {' | '.join(_model_short(m) for m in model_ids)} | Best Value |")
    lines.append(f"|---|---|{'---|' * len(model_ids)}---|")
    for band in ["7-12", "13-18", "19-25", "26-35"]:
        if band not in complexity_scores:
            continue
        n_b = len(complexity_scores[band].get(model_ids[0], []))
        cells = []
        avgs = {}
        for m in model_ids:
            a = _avg(complexity_scores[band][m])
            avgs[m] = a
            cells.append(f"{_tl(a)} {a:.1f}")
        best_b = max(model_ids, key=lambda m: avgs.get(m, 0) / max(_avg(stats[m]["costs"]), 0.001))
        lines.append(f"| {band} | {n_b} | {' | '.join(cells)} | {_model_short(best_b)} |")

    # Model-specific complexity ceilings
    lines.append("\n### Model Complexity Ceilings\n")
    lines.append("| Model | Max complexity for ≥7.5 | Max complexity for ≥5.0 |")
    lines.append("|---|---|---|")
    for m in model_ids:
        # Find highest complexity band where avg ≥ threshold
        ceil_75 = "—"
        ceil_50 = "—"
        for band in ["7-12", "13-18", "19-25", "26-35"]:
            a = _avg(complexity_scores.get(band, {}).get(m, []))
            if a >= 7.5:
                ceil_75 = band
            if a >= 5.0:
                ceil_50 = band
        lines.append(f"| {_model_short(m)} | {ceil_75} | {ceil_50} |")

    # Risk assessment
    lines.append("\n---\n\n## Risk Assessment\n")
    lines.append("### Provider Dependency\n")
    lines.append("| Factor | Sonnet | MiniMax | Qwen3 (Groq) |")
    lines.append("|---|---|---|---|")
    lines.append("| API stability | High (Anthropic) | Medium (newer) | Medium (Groq) |")
    lines.append("| Pricing stability | Stable | Unknown long-term | Competitive pressure |")
    lines.append("| Anthropic-compat endpoint | Native | Third-party (could break) | Via LiteLLM (proxy) |")
    lines.append("| Fallback if fails | — | Sonnet (baseline) | Sonnet or MiniMax |")
    lines.append("| Enterprise Bedrock available? | Yes | Yes (announced) | No |")

    # Recommendation
    lines.append("\n---\n\n## Recommendation\n")
    lines.append("### Immediate (this sprint)")
    lines.append(f"*Based on data — to be filled after benchmark completes.*\n")
    lines.append("### Short-term (next 30 days)")
    lines.append(f"*To be determined based on results.*\n")
    lines.append("### Long-term (next quarter)")
    lines.append(f"*To be determined based on results.*\n")

    # Glossary
    lines.append("---\n\n## Glossary\n")
    lines.append("| Term | Definition |")
    lines.append("|---|---|")
    for term, defn in [
        ("Weighted Score", "Quality rating 1-10 across 6 dimensions, weighted by project importance"),
        ("Cost per Quality Point ($/QP)", "Cost divided by quality score. Lower = more efficient"),
        ("Value Score (Q/$)", "Quality points per dollar. Higher = better value"),
        ("First-Pass Success", "Code passes all tests and lint on first attempt, no fixes needed"),
        ("Review Burden", "Staff engineer time to clean up model output before merge"),
        ("PR Block Rate", "% of tasks with critical/high issues that would prevent merging"),
        ("Net Cost", "Model API cost + Opus review cost + staff engineer cleanup cost"),
        ("T1-T4", "Complexity tiers. T1 (7-12): simple edits. T2 (13-18): single features. T3 (19-25): multi-file. T4 (26-35): refactors"),
        ("Capability Ceiling", "Maximum complexity score at which a model still produces merge-ready code (≥7.5)"),
        ("MoE (Mixture of Experts)", "Architecture where only a fraction of parameters activate per token, making large models cheap"),
        ("Anthropic-compatible API", "Endpoint that speaks the same protocol as Claude, allowing drop-in model substitution"),
    ]:
        lines.append(f"| **{term}** | {defn} |")

    output_path = output_dir / "cto-decision-brief.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines))
    return output_path


# ---------------------------------------------------------------------------
# Report 4: Enterprise Readiness Assessment
# ---------------------------------------------------------------------------

def generate_enterprise_assessment(runs: list[dict], output_dir: Path) -> Path:
    """Report 4 — optional, for customer-facing enterprise pitch."""
    model_ids = list(runs[0].get("models", {}).keys()) if runs else []
    n = len(runs)

    # Check which patterns were validated
    has_groq = any(
        not r.get("models", {}).get("qwen3-32b", {}).get("is_error", True)
        for r in runs
    )
    has_minimax = any(
        not r.get("models", {}).get("MiniMax-M2.5", {}).get("is_error", True)
        for r in runs
    )

    lines = [
        "# Multi-Model Architecture — Enterprise Readiness\n",
        "## Architecture Patterns Validated\n",
        f"- **Direct Anthropic-compat API (MiniMax):** {'✅ Validated' if has_minimax else '❌ Failed'} — "
        f"drop-in replacement, no proxy needed",
        f"- **Proxy pattern (LiteLLM → Groq):** {'✅ Validated' if has_groq else '❌ Failed'} — "
        f"routes OpenAI-format models through Claude Code",
        f"- **Bedrock routing:** Not tested — enterprise AWS integration (LiteLLM supports it)\n",
        "## Customer Deployment Options\n",
        "| Option | Models | Infra | Cost | Quality |",
        "|---|---|---|---|---|",
        "| A: Anthropic-only | Sonnet + Opus | Direct API | $$$$ | Highest |",
        f"| B: Hybrid (recommended) | {'MiniMax' if has_minimax else 'TBD'} (routine) + Sonnet (complex) + Opus (review) | Direct API × 2 | $$ | High |",
        "| C: Bedrock | Customer's Bedrock models + Opus review | LiteLLM proxy | $ (customer-funded) | Depends |",
        f"| D: Full open-source | {'Qwen3 (Groq)' if has_groq else 'TBD'} + Opus review | LiteLLM proxy | $ | Medium |\n",
        "## Benchmark Evidence\n",
        f"- {n} tasks tested across {len(set(r.get('task_tier','?') for r in runs))} complexity tiers",
        f"- Total benchmark cost: {_fmt(sum(r.get('total_benchmark_cost_usd', 0) for r in runs))}",
        f"- All task definitions, scoring rubric, and raw data archived for reproducibility",
        f"- See CTO Decision Brief for detailed quality/cost analysis\n",
        "## Vendor Diversification\n",
        f"- Providers tested: {len(set(m.split('-')[0] for m in model_ids))}",
        "- API formats validated: Anthropic native, Anthropic-compat (MiniMax), OpenAI via proxy (Groq)",
        "- Fallback chain: Groq fails → MiniMax; MiniMax fails → Sonnet",
    ]

    output_path = output_dir / "enterprise-readiness.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines))
    return output_path
```

- [ ] **Step 2: Verify imports**

```bash
python3 -c "from benchmark.report import generate_per_task_report; print('report.py OK')"
```

- [ ] **Step 3: Commit**

```bash
git add benchmark/report.py
git commit -m "feat(benchmark): per-task and CTO brief report generators"
```

---

### Task 6: Main orchestrator harness

**Files:**
- Create: `benchmark/harness.py`
- Create: `benchmark/__init__.py`

- [ ] **Step 1: Create `benchmark/__init__.py`**

```python
"""Model benchmark framework."""
```

- [ ] **Step 2: Create `benchmark/harness.py`**

```python
"""Main benchmark orchestrator — runs tasks across models in parallel worktrees."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import yaml

from benchmark.metrics import BenchmarkRun, ModelResult, TaskComplexity, BenchmarkLogger, real_cost
from benchmark.worktree import (
    create_worktrees,
    collect_git_metrics,
    run_tests_in_worktree,
    run_lint_in_worktree,
    create_pr_from_worktree,
    cleanup_worktrees,
    get_project_root,
)
from benchmark.judge import OpusJudge
from benchmark.report import (
    generate_per_task_report,
    generate_failure_analysis,
    generate_cto_brief,
    generate_enterprise_assessment,
)


def load_config() -> dict:
    """Load benchmark config."""
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


def load_task(task_path: str) -> dict:
    """Load a task YAML file."""
    with open(task_path) as f:
        return yaml.safe_load(f)


def load_env(env_file: str) -> None:
    """Source environment variables from .env file."""
    env_path = Path(env_file)
    if not env_path.exists():
        print(f"WARNING: {env_file} not found")
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                os.environ.setdefault(key, value)


def run_model_agent(
    model_id: str,
    model_config: dict,
    task: dict,
    worktree_path: Path,
    timeout: int = 600,
) -> ModelResult:
    """Run Claude Code in a worktree with a specific model. Returns ModelResult."""
    result = ModelResult(model_id=model_id)

    # Build the task prompt
    prompt = (
        f"## Task: {task['name']}\n\n"
        f"{task['description']}\n\n"
        f"## Requirements\n"
        + "\n".join(f"- {r}" for r in task.get("requirements", []))
        + "\n\n## Acceptance Criteria\n"
        + "\n".join(f"- {c}" for c in task.get("acceptance_criteria", []))
    )
    if task.get("context"):
        prompt += f"\n\n## Context\n{task['context']}"

    # Build environment for this model
    env = os.environ.copy()
    env["ANTHROPIC_BASE_URL"] = model_config["base_url"]

    # Handle auth key — MiniMax uses ANTHROPIC_API_KEY, LiteLLM uses ANTHROPIC_AUTH_TOKEN
    auth_header = model_config.get("auth_header", "ANTHROPIC_API_KEY")
    env_key = model_config["env_key"]
    env_value = os.environ.get(env_key, "")

    if auth_header == "ANTHROPIC_AUTH_TOKEN":
        env["ANTHROPIC_AUTH_TOKEN"] = env_value
        env.pop("ANTHROPIC_API_KEY", None)
    else:
        env["ANTHROPIC_API_KEY"] = env_value

    # Output file for JSON results
    output_file = worktree_path / ".benchmark-output.json"

    # Build claude command
    cmd = [
        "claude",
        "-p", prompt,
        "--model", model_config["model_id"],
        "--output-format", "json",
        "--max-turns", "20",
    ]

    start_time = time.time()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(worktree_path),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        elapsed_ms = int((time.time() - start_time) * 1000)

        # Parse JSON output
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError:
            result.is_error = True
            result.wall_clock_ms = elapsed_ms
            return result

        usage = data.get("usage", {})
        result.input_tokens = usage.get("input_tokens", 0)
        result.output_tokens = usage.get("output_tokens", 0)
        result.claude_reported_cost_usd = data.get("total_cost_usd", 0.0)
        result.wall_clock_ms = data.get("duration_ms", elapsed_ms)
        result.api_time_ms = data.get("duration_api_ms", 0)
        result.num_turns = data.get("num_turns", 0)
        result.is_error = data.get("is_error", False)

    except subprocess.TimeoutExpired:
        result.is_error = True
        result.wall_clock_ms = timeout * 1000
        return result

    # Collect post-run metrics
    git_metrics = collect_git_metrics(worktree_path)
    result.files_changed = git_metrics["files_changed"]
    result.lines_added = git_metrics["lines_added"]
    result.lines_removed = git_metrics["lines_removed"]
    result.diff_text = git_metrics["diff_text"]

    test_metrics = run_tests_in_worktree(worktree_path)
    result.tests_total = test_metrics["tests_total"]
    result.tests_passed = test_metrics["tests_passed"]
    result.tests_failed = test_metrics["tests_failed"]
    result.test_output = test_metrics["test_output"]

    lint_metrics = run_lint_in_worktree(worktree_path)
    result.lint_violations = lint_metrics["lint_violations"]
    result.lint_output = lint_metrics["lint_output"]

    result.calculate_derived()
    return result


def print_summary(run: BenchmarkRun) -> None:
    """Print a comparison table to console."""
    print("\n" + "=" * 70)
    print(f"  BENCHMARK RESULTS — {run.task_name} ({run.task_tier})")
    print("=" * 70)

    header = f"{'Model':<30} {'Score':>6} {'Cost':>8} {'$/QP':>8} {'Time':>7} {'Tests':>6}"
    print(header)
    print("-" * 70)

    for model_id, result in run.models.items():
        scores = run.opus_review.scores.get(model_id) if run.opus_review else None
        ws = scores.weighted_score if scores else 0.0
        d = run.derived.get(model_id)
        cpqp = d.cost_per_quality_point if d else 0.0
        tests = f"{result.tests_passed}/{result.tests_total}"
        time_s = f"{result.wall_clock_ms / 1000:.0f}s"
        marker = " ★" if run.opus_review and run.opus_review.winner == model_id else ""

        print(f"{model_id:<30} {ws:>5.1f}{marker} ${result.actual_cost_usd:>7.4f} ${cpqp:>7.4f} {time_s:>7} {tests:>6}")

    print("-" * 70)
    print(f"Total cost: ${run.total_benchmark_cost_usd:.4f}")
    if run.opus_review:
        print(f"Winner: {run.opus_review.winner}")
        print(f"Rationale: {run.opus_review.winner_rationale[:100]}")
    print("=" * 70)


def run_benchmark(task_path: str, skip_review: bool = False) -> BenchmarkRun:
    """Run a full benchmark for one task."""
    config = load_config()
    task = load_task(task_path)
    load_env(config["benchmark"]["env_file"])

    model_ids = config["benchmark"]["implementors"]
    model_configs = {m: config["models"][m] for m in model_ids}
    timeout = config["benchmark"]["timeout_seconds"]
    worktree_dir = config["benchmark"]["worktree_dir"]

    # Initialize run
    run = BenchmarkRun(
        task_id=task["id"],
        task_name=task["name"],
        task_tier=task.get("tier", "?"),
        jira_ticket=task.get("jira_ticket", "N/A"),
    )
    run.generate_run_id()

    if "complexity" in task:
        c = task["complexity"]
        run.complexity = TaskComplexity(**{k: v for k, v in c.items() if k != "total"})
        run.task_tier = run.complexity.tier

    # Cost estimate
    estimated = len(model_ids) * 0.55 + 0.25  # rough: biggest model + review
    print(f"\nTask: {task['name']} ({run.task_tier})")
    print(f"Models: {', '.join(model_ids)}")
    print(f"Estimated cost: ~${estimated:.2f}")

    confirm = input("Proceed? (y/n): ").strip().lower()
    if confirm != "y":
        print("Skipped.")
        return run

    # Create worktrees
    print("\nCreating worktrees...")
    worktrees = create_worktrees(model_ids, worktree_dir=worktree_dir)

    try:
        # Run models in parallel
        print(f"Running {len(model_ids)} models in parallel...")
        with ThreadPoolExecutor(max_workers=len(model_ids)) as executor:
            futures = {}
            for model_id in model_ids:
                future = executor.submit(
                    run_model_agent,
                    model_id,
                    model_configs[model_id],
                    task,
                    worktrees[model_id],
                    timeout,
                )
                futures[future] = model_id

            for future in as_completed(futures):
                model_id = futures[future]
                try:
                    result = future.result()
                    run.models[model_id] = result
                    status = "✅" if not result.is_error else "❌"
                    print(f"  {status} {model_id}: {result.tests_passed}/{result.tests_total} tests, ${result.actual_cost_usd:.4f}")
                except Exception as e:
                    print(f"  ❌ {model_id}: {e}")
                    run.models[model_id] = ModelResult(model_id=model_id, is_error=True)

        if not skip_review:
            # Opus blind review
            print("\nRunning Opus blind review...")
            judge = OpusJudge()

            # Pass 1: Scoring
            implementations = {
                m: {
                    "diff_text": r.diff_text,
                    "test_output": r.test_output,
                    "lint_output": r.lint_output,
                }
                for m, r in run.models.items()
            }
            run.opus_review = judge.score(task.get("description", ""), implementations)

            # Pass 2: Fix estimation for each model
            for model_id, result in run.models.items():
                fix_summary = judge.estimate_fixes(
                    task.get("description", ""),
                    model_id,
                    result.diff_text,
                    result.test_output,
                )
                run.opus_review.fix_summaries[model_id] = fix_summary

            # Update review token totals
            run.opus_review.review_input_tokens = judge.total_input_tokens
            run.opus_review.review_output_tokens = judge.total_output_tokens
            run.opus_review.calculate_cost()

        # Calculate derived metrics
        staff_rate = config.get("staff_engineer", {}).get("hourly_rate_usd", 95.0)
        run.calculate_derived(staff_rate=staff_rate)

        # Print summary
        print_summary(run)

        # Log results
        logger = BenchmarkLogger(config["benchmark"]["results_dir"])
        logger.save_run(run)

        # Generate per-task report
        results_dir = Path(config["benchmark"]["results_dir"]) / "reports"
        from dataclasses import asdict
        run_dict = json.loads(json.dumps(asdict(run), default=str))
        generate_per_task_report(run_dict, results_dir)
        print(f"\nReport saved to: {results_dir / f'{run.run_id}.md'}")

        # Offer to PR winner
        if run.opus_review and run.opus_review.winner:
            winner = run.opus_review.winner
            winner_scores = run.opus_review.scores.get(winner)
            ws = winner_scores.weighted_score if winner_scores else 0.0

            if ws >= 7.5:
                print(f"\n★ Winner: {winner} (score: {ws:.1f})")
                merge = input(f"Create PR from {winner}'s worktree? (y/n): ").strip().lower()
                if merge == "y" and winner in worktrees:
                    pr_num = create_pr_from_worktree(
                        worktrees[winner], winner, task["name"], task["id"],
                        ws, run.models[winner].actual_cost_usd,
                    )
                    if pr_num:
                        run.winner_merged = winner
                        run.pr_number = pr_num
                        print(f"PR #{pr_num} created!")
                    else:
                        print("PR creation failed.")
            else:
                print(f"\n⚠️ Winner {winner} scored {ws:.1f} (below 7.5 merge threshold)")

    finally:
        # Always clean up worktrees
        print("\nCleaning up worktrees...")
        cleanup_worktrees(model_ids, worktree_dir=worktree_dir)

    return run


def run_batch(tasks_dir: str) -> None:
    """Run benchmark on all task YAMLs in a directory."""
    config = load_config()
    tasks_path = Path(tasks_dir)
    task_files = sorted(tasks_path.glob("*.yaml")) + sorted(tasks_path.glob("*.yml"))

    if not task_files:
        print(f"No task files found in {tasks_dir}")
        return

    print(f"\nBatch benchmark: {len(task_files)} tasks")
    print(f"Models: {', '.join(config['benchmark']['implementors'])}")
    print(f"Estimated total cost: ~${len(task_files) * 0.75:.2f}")

    for i, task_file in enumerate(task_files, 1):
        print(f"\n{'=' * 70}")
        print(f"  Task {i}/{len(task_files)}: {task_file.name}")
        print(f"{'=' * 70}")
        run_benchmark(str(task_file))

    # Generate all reports
    logger = BenchmarkLogger(config["benchmark"]["results_dir"])
    all_runs = logger.load_all_runs()
    if all_runs:
        results_dir = Path(config["benchmark"]["results_dir"]) / "reports"
        staff_rate = config.get("staff_engineer", {}).get("hourly_rate_usd", 95.0)
        if len(all_runs) >= 4:
            fa_path = generate_failure_analysis(all_runs, results_dir)
            print(f"\n📊 Failure Analysis saved to: {fa_path}")
        brief_path = generate_cto_brief(all_runs, results_dir, staff_rate=staff_rate)
        print(f"★ CTO Decision Brief saved to: {brief_path}")
        ent_path = generate_enterprise_assessment(all_runs, results_dir)
        print(f"🏢 Enterprise Assessment saved to: {ent_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Model Benchmark Harness")
    parser.add_argument("--task", help="Path to task YAML file")
    parser.add_argument("--batch", help="Path to directory of task YAMLs")
    parser.add_argument("--report", action="store_true", help="Generate aggregate report from existing data")
    parser.add_argument("--skip-review", action="store_true", help="Skip Opus review (for testing)")
    args = parser.parse_args()

    if args.report:
        config = load_config()
        logger = BenchmarkLogger(config["benchmark"]["results_dir"])
        all_runs = logger.load_all_runs()
        results_dir = Path(config["benchmark"]["results_dir"]) / "reports"
        staff_rate = config.get("staff_engineer", {}).get("hourly_rate_usd", 95.0)
        if len(all_runs) >= 4:
            fa_path = generate_failure_analysis(all_runs, results_dir)
            print(f"Failure analysis: {fa_path}")
        brief_path = generate_cto_brief(all_runs, results_dir, staff_rate=staff_rate)
        print(f"CTO brief: {brief_path}")
        ent_path = generate_enterprise_assessment(all_runs, results_dir)
        print(f"Enterprise assessment: {ent_path}")
    elif args.batch:
        run_batch(args.batch)
    elif args.task:
        run_benchmark(args.task, skip_review=args.skip_review)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Verify the harness loads**

```bash
python3 -c "from benchmark.harness import load_config; c = load_config(); print(f'Config OK: {len(c[\"models\"])} models')"
```

Expected: `Config OK: 4 models`

- [ ] **Step 4: Commit**

```bash
git add benchmark/__init__.py benchmark/harness.py
git commit -m "feat(benchmark): main orchestrator harness with parallel execution + CLI"
```

---

### Task 7: Benchmark skill

**Files:**
- Create: `.claude/skills/benchmark/SKILL.md`

- [ ] **Step 1: Create `.claude/skills/benchmark/SKILL.md`**

```markdown
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
python3 benchmark/harness.py --task benchmark/tasks/t1_001_xxx.yaml

# All tasks
python3 benchmark/harness.py --batch benchmark/tasks/

# Regenerate reports from existing data
python3 benchmark/harness.py --report
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
- CTO brief: `benchmark/results/reports/cto-decision-brief.md`
```

- [ ] **Step 2: Commit**

```bash
git add .claude/skills/benchmark/SKILL.md
git commit -m "feat(benchmark): /benchmark skill for Claude Code"
```

---

### Task 8: README + dependency install

**Files:**
- Create: `benchmark/README.md`

- [ ] **Step 1: Create `benchmark/README.md`**

```markdown
# Model Benchmark Framework

Compare LLM models on real coding tasks within Claude Code's agentic workflow.

## Quick Start

```bash
# 1. Install dependencies (outside project venv)
pip install httpx pyyaml

# 2. Ensure API keys are in backend/.env:
#    ANTHROPIC_API_KEY=sk-ant-...
#    MINIMAX_API_KEY=...
#    GROQ_API_KEY=...

# 3. For Groq (optional): start LiteLLM proxy
pip install 'litellm[proxy]'
litellm --config benchmark/litellm-config.yaml --port 4000

# 4. Run a single task
python3 benchmark/harness.py --task benchmark/tasks/t1_001_example.yaml

# 5. Run all tasks
python3 benchmark/harness.py --batch benchmark/tasks/

# 6. Generate aggregate report
python3 benchmark/harness.py --report
```

## Models

| Model | Provider | API Format | Proxy? |
|---|---|---|---|
| Sonnet 4.6 | Anthropic | Native | No |
| MiniMax M2.5 | MiniMax | Anthropic-compatible | No |
| Qwen3-32B | Groq | OpenAI (via LiteLLM) | Yes |
| Opus 4.6 | Anthropic | Native (judge only) | No |

## Output

- `benchmark/results/all_runs.jsonl` — raw data
- `benchmark/results/reports/*.md` — per-task reports
- `benchmark/results/reports/cto-decision-brief.md` — aggregate analysis

## Spec

Full specification: `docs/superpowers/specs/2026-04-05-model-benchmark-framework.md`
```

- [ ] **Step 2: Install dependencies**

```bash
pip install httpx pyyaml
```

- [ ] **Step 3: Commit**

```bash
git add benchmark/README.md
git commit -m "docs(benchmark): README with setup guide"
```

---

### Task 9: Create first 3 task YAMLs (T1, T2, T3)

**Files:**
- Create: `benchmark/tasks/t1_001_example.yaml`
- Create: `benchmark/tasks/t2_001_example.yaml`
- Create: `benchmark/tasks/t3_001_example.yaml`

This task creates 3 example task YAMLs — one per tier. The actual JIRA-linked tasks will be created from the backlog during the benchmark session, but these serve as templates and smoke-test tasks.

- [ ] **Step 1: Create `benchmark/tasks/t1_001_example.yaml`**

```yaml
id: "t1_001"
jira_ticket: "N/A"
tier: "T1"
name: "Add is_premium field to UserResponse schema"
description: |
  Add a computed boolean field `is_premium` to the UserResponse Pydantic schema.
  The field should be True if the user's role is 'admin' or 'premium', False otherwise.
  Add a unit test for the new field.
requirements:
  - Add `is_premium: bool` field to UserResponse in backend/schemas/user.py
  - Compute from user.role using a @computed_field or model_validator
  - Unit test verifying is_premium=True for admin role, False for 'user' role
acceptance_criteria:
  - uv run pytest tests/unit/ -q passes with no new failures
  - uv run ruff check backend/schemas/user.py passes
context: |
  Look at existing UserResponse schema in backend/schemas/user.py for patterns.
  UserRole enum is in backend/models/user.py (values: user, admin, premium).
complexity:
  context_span: 1
  reasoning_depth: 1
  integration_surface: 1
  convention_density: 2
  implicit_knowledge: 1
  verification_difficulty: 1
  failure_cost: 1
```

- [ ] **Step 2: Create `benchmark/tasks/t2_001_example.yaml`**

```yaml
id: "t2_001"
jira_ticket: "N/A"
tier: "T2"
name: "Add health check timestamp to /health endpoint"
description: |
  Extend the existing /health endpoint to include a `checked_at` ISO timestamp
  and a `database_connected` boolean that does a simple SELECT 1 against the DB.
  Update the HealthResponse schema and add tests.
requirements:
  - Add `checked_at: datetime` field to HealthResponse schema
  - Add `database_connected: bool` field to HealthResponse
  - Implement async DB connectivity check (SELECT 1) in the health router
  - Handle DB connection failure gracefully (database_connected=False, don't crash)
  - Unit test for schema fields
  - Unit test for DB check (mock the session)
acceptance_criteria:
  - uv run pytest tests/unit/ -q passes with no new failures
  - uv run ruff check backend/ passes
context: |
  Health router is at backend/routers/health.py.
  HealthResponse schema is at backend/schemas/health.py.
  Use get_async_session dependency for DB access (see other routers for pattern).
  IMPORTANT: The health endpoint must not require authentication.
complexity:
  context_span: 2
  reasoning_depth: 2
  integration_surface: 2
  convention_density: 3
  implicit_knowledge: 2
  verification_difficulty: 2
  failure_cost: 2
```

- [ ] **Step 3: Create `benchmark/tasks/t3_001_example.yaml`**

```yaml
id: "t3_001"
jira_ticket: "N/A"
tier: "T3"
name: "Add API usage tracking service"
description: |
  Create a new service that tracks API usage per user: endpoint called,
  timestamp, response time. Store in a new api_usage_log table.
  Expose via a new GET /api/v1/admin/usage endpoint (admin-only).
requirements:
  - New SQLAlchemy model: ApiUsageLog (user_id FK, endpoint, method, response_time_ms, created_at)
  - New Pydantic schemas: ApiUsageLogResponse, ApiUsageListResponse
  - New service function: log_api_usage(user_id, endpoint, method, response_time_ms)
  - New service function: get_usage_stats(user_id=None, limit=100) -> list
  - New admin router endpoint: GET /admin/usage (requires admin role)
  - Alembic migration for api_usage_log table
  - Unit tests for service functions
  - Unit test for admin endpoint (auth + happy path + forbidden for non-admin)
acceptance_criteria:
  - uv run pytest tests/unit/ -q passes with no new failures
  - uv run ruff check backend/ passes
  - Migration applies cleanly (alembic upgrade head)
context: |
  Follow existing patterns in backend/models/, backend/schemas/, backend/services/,
  and backend/routers/admin.py. Use async session. Admin routes use
  require_admin dependency. See backend/routers/admin.py for examples.
  Migration must NOT drop TimescaleDB indexes (known Alembic autogenerate bug).
complexity:
  context_span: 4
  reasoning_depth: 2
  integration_surface: 3
  convention_density: 4
  implicit_knowledge: 3
  verification_difficulty: 3
  failure_cost: 3
```

- [ ] **Step 4: Create `benchmark/tasks/t4_001_example.yaml`**

```yaml
id: "t4_001"
jira_ticket: "N/A"
tier: "T4"
name: "Extract shared pagination logic from list endpoints"
description: |
  Multiple list endpoints (stocks, signals, portfolio holdings, news) each implement
  their own pagination with offset/limit. Extract a shared paginate() utility that
  all list endpoints use. Update all callers.
requirements:
  - Create backend/utils/pagination.py with a paginate() async helper
  - The helper accepts: query (SQLAlchemy select), session, offset, limit, max_limit=100
  - Returns a PaginatedResponse schema with items, total, offset, limit, has_more
  - Create PaginatedResponse generic schema in backend/schemas/common.py
  - Refactor at least 3 existing list endpoints to use the shared helper
  - Preserve existing API contract (same response shape, same query params)
  - Unit tests for paginate() helper (empty, partial, full page, over-limit)
  - Verify existing endpoint tests still pass after refactor
acceptance_criteria:
  - uv run pytest tests/unit/ -q passes with no regressions
  - uv run ruff check backend/ passes
  - At least 3 list endpoints refactored to use shared pagination
  - No changes to API response contract (existing clients unaffected)
context: |
  Look at backend/routers/stocks.py, backend/routers/signals.py, and
  backend/routers/portfolio.py for existing pagination patterns.
  Each currently does its own offset/limit handling with slight variations.
  The refactored version must preserve the same query parameter names.
  Use async session pattern from existing routers.
complexity:
  context_span: 5
  reasoning_depth: 3
  integration_surface: 4
  convention_density: 4
  implicit_knowledge: 4
  verification_difficulty: 4
  failure_cost: 4
```

- [ ] **Step 5: Commit**

```bash
git add benchmark/tasks/
git commit -m "feat(benchmark): example task YAMLs for T1, T2, T3, T4 tiers"
```

---

### Task 10: Smoke test — validate full pipeline with `--skip-review`

**Files:** None (validation only)

- [ ] **Step 1: Verify config loads**

```bash
python3 benchmark/harness.py --help
```

Expected: prints argparse help with `--task`, `--batch`, `--report`, `--skip-review` flags.

- [ ] **Step 2: Verify worktree creation and cleanup (dry run)**

```bash
python3 -c "
from benchmark.worktree import create_worktrees, cleanup_worktrees
wts = create_worktrees(['test-model-a', 'test-model-b'], worktree_dir='.benchmark')
print(f'Created: {list(wts.keys())}')
for name, path in wts.items():
    print(f'  {name}: {path} exists={path.exists()}')
cleanup_worktrees(['test-model-a', 'test-model-b'], worktree_dir='.benchmark')
print('Cleanup OK')
"
```

Expected: creates 2 worktrees, prints paths, cleans up without errors.

- [ ] **Step 3: Run single-model smoke test (Sonnet only, skip review)**

Edit `benchmark/config.yaml` temporarily to test with just Sonnet:
```bash
python3 benchmark/harness.py --task benchmark/tasks/t1_001_example.yaml --skip-review
```

When prompted "Proceed? (y/n)", type `y`. This runs only Sonnet on a T1 task without Opus review — cheapest possible test (~$0.55).

Expected: completes without errors, prints summary table, saves to `benchmark/results/all_runs.jsonl`.

- [ ] **Step 4: Verify JSONL output**

```bash
python3 -c "
import json
with open('benchmark/results/all_runs.jsonl') as f:
    run = json.loads(f.readline())
    print(f'Run ID: {run[\"run_id\"]}')
    for m, r in run.get('models', {}).items():
        print(f'  {m}: tokens={r[\"input_tokens\"]}+{r[\"output_tokens\"]}, cost=\${r[\"actual_cost_usd\"]:.4f}, error={r[\"is_error\"]}')
"
```

Expected: shows run with token counts, cost, and `is_error=False`.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(benchmark): validated full pipeline with smoke test"
```

---

### Task 11: Groq + LiteLLM smoke test

**Files:** None (validation only)

- [ ] **Step 1: Install LiteLLM**

```bash
pip install 'litellm[proxy]'
```

- [ ] **Step 2: Start LiteLLM proxy**

In a separate terminal:
```bash
cd /Users/sigmoid/Documents/projects/stockanalysis/stock-signal-platform
source backend/.env
litellm --config benchmark/litellm-config.yaml --port 4000
```

Wait for "LiteLLM Proxy running on http://0.0.0.0:4000"

- [ ] **Step 3: Test Groq connectivity through LiteLLM**

```bash
source backend/.env
ANTHROPIC_BASE_URL=http://localhost:4000 \
ANTHROPIC_AUTH_TOKEN=sk-benchmark-local-key \
claude -p "What is 2+2? Reply with just the number." \
  --model qwen3-32b --output-format json --max-turns 1 2>/dev/null \
| python3 -c "
import sys,json
d=json.loads(sys.stdin.read())
print(json.dumps({
    'result': d.get('result'),
    'is_error': d.get('is_error'),
    'input_tokens': d.get('usage',{}).get('input_tokens',0),
    'output_tokens': d.get('usage',{}).get('output_tokens',0),
}, indent=2))
"
```

Expected: `result` contains "4", `is_error` is false, tokens > 0.

- [ ] **Step 4: If smoke test fails**

If `output_config` error occurs, verify `drop_params: true` is in `benchmark/litellm-config.yaml`.
If still fails, the spec says: proceed with Sonnet vs MiniMax only. Log the failure.

- [ ] **Step 5: Stop LiteLLM proxy**

Ctrl+C in the LiteLLM terminal.

---

### Task 12: Final commit + push

**Files:**
- Modify: `.gitignore` (verify `.benchmark/` is listed)

- [ ] **Step 1: Verify all files exist**

```bash
ls -la benchmark/
ls -la benchmark/tasks/
ls -la .claude/skills/benchmark/
```

Expected: all files from the file structure section present.

- [ ] **Step 2: Run ruff on benchmark code (best practice even though it's standalone)**

```bash
python3 -m ruff check benchmark/ --fix
python3 -m ruff format benchmark/
```

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "feat(benchmark): complete model benchmark framework

- Config: 3 implementor models + Opus judge, pricing, staff rate
- Metrics: dataclasses, cost calculator (corrects Claude Code's wrong cost), JSONL logger
- Worktree: create/cleanup/PR helpers for parallel model execution
- Judge: Opus blind scoring (6 dimensions) + fix estimation (staff burden)
- Reports: per-task, failure analysis, CTO decision brief with glossary
- Harness: CLI orchestrator with parallel execution, cost guard, winner PR
- Skill: /benchmark for Claude Code integration
- Tasks: 3 example YAMLs (T1, T2, T3) as templates
- README: setup and usage guide"
```

- [ ] **Step 4: Push branch and create PR**

```bash
git push origin HEAD
gh pr create --base develop --title "feat: Model benchmark framework" --body "$(cat <<'EOF'
## Summary
- Benchmark harness comparing Sonnet 4.6 vs MiniMax M2.5 vs Qwen3-32B (Groq)
- Parallel worktree execution, Opus blind review, staff engineer burden estimation
- Per-task and CTO-ready aggregate reports with explainability
- All 3 models run on all 12 tasks from JIRA backlog

## Spec
docs/superpowers/specs/2026-04-05-model-benchmark-framework.md

## Test plan
- [x] Config loads correctly
- [x] Worktree create/cleanup works
- [x] Sonnet smoke test passes (--skip-review)
- [x] JSONL output has correct structure
- [ ] LiteLLM + Groq smoke test
- [ ] Full benchmark run (12 tasks × 3 models)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
