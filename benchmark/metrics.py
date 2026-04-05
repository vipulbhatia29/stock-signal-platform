"""Dataclasses for benchmark metrics, cost calculation, and JSONL logging."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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
    diff_text: str = ""
    test_output: str = ""
    lint_output: str = ""

    def calculate_derived(self) -> None:
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
    file: str
    fix_type: str
    severity: str
    description: str
    estimated_fix_lines: int = 0
    estimated_fix_minutes: int = 0


@dataclass
class FixSummary:
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
    cost_per_quality_point: float = 0.0
    test_pass_rate: float = 0.0
    cost_ratio_vs_sonnet: float = 0.0
    speed_ratio_vs_sonnet: float = 0.0
    quality_gap_vs_sonnet: float = 0.0
    value_score: float = 0.0
    net_cost: float = 0.0
    net_cost_vs_sonnet: float = 0.0


@dataclass
class BenchmarkRun:
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

            review_share = (review.review_cost_usd / len(self.models)) if review else 0.0
            staff_cost = 0.0
            if fix_summary:
                staff_cost = (fix_summary.total_fix_minutes / 60) * staff_rate
            d.net_cost = result.actual_cost_usd + review_share + staff_cost

            self.derived[model_id] = d

        sonnet_net = self.derived.get("claude-sonnet-4-6")
        if sonnet_net and sonnet_net.net_cost > 0:
            for d in self.derived.values():
                d.net_cost_vs_sonnet = d.net_cost / sonnet_net.net_cost

        self.total_benchmark_cost_usd = sum(
            r.actual_cost_usd for r in self.models.values()
        ) + (review.review_cost_usd if review else 0.0)


def _serialize(obj: Any) -> Any:
    if hasattr(obj, "__dataclass_fields__"):
        return asdict(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    return str(obj)


class BenchmarkLogger:
    def __init__(self, results_dir: str = "benchmark/results"):
        self.results_dir = Path(results_dir)
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.jsonl_path = self.results_dir / "all_runs.jsonl"

    def save_run(self, run: BenchmarkRun) -> Path:
        data = json.loads(json.dumps(asdict(run), default=_serialize))
        with open(self.jsonl_path, "a") as f:
            f.write(json.dumps(data) + "\n")
        individual = self.results_dir / "reports" / f"{run.run_id}.json"
        individual.parent.mkdir(parents=True, exist_ok=True)
        with open(individual, "w") as f:
            json.dump(data, f, indent=2, default=_serialize)
        return individual

    def load_all_runs(self) -> list[dict]:
        if not self.jsonl_path.exists():
            return []
        runs = []
        with open(self.jsonl_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    runs.append(json.loads(line))
        return runs
