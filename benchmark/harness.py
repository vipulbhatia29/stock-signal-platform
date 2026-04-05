"""Main benchmark orchestrator — runs tasks across models in parallel worktrees."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path

import yaml

from benchmark.metrics import BenchmarkRun, ModelResult, TaskComplexity, BenchmarkLogger
from benchmark.worktree import (
    create_worktrees,
    collect_git_metrics,
    run_tests_in_worktree,
    run_lint_in_worktree,
    create_pr_from_worktree,
    cleanup_worktrees,
)
from benchmark.judge import OpusJudge
from benchmark.report import (
    generate_per_task_report,
    generate_failure_analysis,
    generate_cto_brief,
    generate_enterprise_assessment,
)


def load_config() -> dict:
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


def load_task(task_path: str) -> dict:
    with open(task_path) as f:
        return yaml.safe_load(f)


def load_env(env_file: str) -> None:
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
    """Run Claude Code in a worktree with a specific model."""
    result = ModelResult(model_id=model_id)

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

    env = os.environ.copy()
    env["ANTHROPIC_BASE_URL"] = model_config["base_url"]

    auth_header = model_config.get("auth_header", "ANTHROPIC_API_KEY")
    env_key = model_config["env_key"]
    env_value = os.environ.get(env_key, "")

    if auth_header == "ANTHROPIC_AUTH_TOKEN":
        env["ANTHROPIC_AUTH_TOKEN"] = env_value
        env.pop("ANTHROPIC_API_KEY", None)
    else:
        env["ANTHROPIC_API_KEY"] = env_value

    cmd = [
        "claude", "-p", prompt,
        "--model", model_config["model_id"],
        "--output-format", "json",
        "--max-turns", "20",
    ]

    start_time = time.time()
    try:
        proc = subprocess.run(
            cmd, cwd=str(worktree_path),
            capture_output=True, text=True,
            timeout=timeout, env=env,
        )
        elapsed_ms = int((time.time() - start_time) * 1000)

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
    print("\n" + "=" * 70)
    print(f"  BENCHMARK RESULTS — {run.task_name} ({run.task_tier})")
    print("=" * 70)
    print(f"{'Model':<30} {'Score':>6} {'Cost':>8} {'$/QP':>8} {'Time':>7} {'Tests':>6}")
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
    config = load_config()
    task = load_task(task_path)
    load_env(config["benchmark"]["env_file"])

    model_ids = config["benchmark"]["implementors"]
    model_configs = {m: config["models"][m] for m in model_ids}
    timeout = config["benchmark"]["timeout_seconds"]
    worktree_dir = config["benchmark"]["worktree_dir"]

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

    print(f"\nTask: {task['name']} ({run.task_tier})")
    print(f"Models: {', '.join(model_ids)}")
    print(f"Estimated cost: ~${len(model_ids) * 0.55 + 0.25:.2f}")

    confirm = input("Proceed? (y/n): ").strip().lower()
    if confirm != "y":
        print("Skipped.")
        return run

    print("\nCreating worktrees...")
    worktrees = create_worktrees(model_ids, worktree_dir=worktree_dir)

    try:
        print(f"Running {len(model_ids)} models in parallel...")
        with ThreadPoolExecutor(max_workers=len(model_ids)) as executor:
            futures = {}
            for model_id in model_ids:
                future = executor.submit(
                    run_model_agent, model_id, model_configs[model_id],
                    task, worktrees[model_id], timeout,
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
            print("\nRunning Opus blind review...")
            judge = OpusJudge()

            implementations = {
                m: {"diff_text": r.diff_text, "test_output": r.test_output, "lint_output": r.lint_output}
                for m, r in run.models.items()
            }
            run.opus_review = judge.score(task.get("description", ""), implementations)

            for model_id, result in run.models.items():
                fix_summary = judge.estimate_fixes(
                    task.get("description", ""), model_id, result.diff_text, result.test_output,
                )
                run.opus_review.fix_summaries[model_id] = fix_summary

            run.opus_review.review_input_tokens = judge.total_input_tokens
            run.opus_review.review_output_tokens = judge.total_output_tokens
            run.opus_review.calculate_cost()

        staff_rate = config.get("staff_engineer", {}).get("hourly_rate_usd", 95.0)
        run.calculate_derived(staff_rate=staff_rate)
        print_summary(run)

        logger = BenchmarkLogger(config["benchmark"]["results_dir"])
        logger.save_run(run)

        results_dir = Path(config["benchmark"]["results_dir"]) / "reports"
        run_dict = json.loads(json.dumps(asdict(run), default=str))
        generate_per_task_report(run_dict, results_dir)
        print(f"\nReport: {results_dir / f'{run.run_id}.md'}")

        if run.opus_review and run.opus_review.winner:
            winner = run.opus_review.winner
            ws = run.opus_review.scores.get(winner)
            ws_val = ws.weighted_score if ws else 0.0

            if ws_val >= 7.5:
                print(f"\n★ Winner: {winner} (score: {ws_val:.1f})")
                merge = input(f"Create PR from {winner}'s worktree? (y/n): ").strip().lower()
                if merge == "y" and winner in worktrees:
                    pr_num = create_pr_from_worktree(
                        worktrees[winner], winner, task["name"], task["id"],
                        ws_val, run.models[winner].actual_cost_usd,
                    )
                    if pr_num:
                        run.winner_merged = winner
                        run.pr_number = pr_num
                        print(f"PR #{pr_num} created!")
            else:
                print(f"\n⚠️ Winner {winner} scored {ws_val:.1f} (below 7.5 merge threshold)")

    finally:
        print("\nCleaning up worktrees...")
        cleanup_worktrees(model_ids, worktree_dir=worktree_dir)

    return run


def run_batch(tasks_dir: str) -> None:
    config = load_config()
    tasks_path = Path(tasks_dir)
    task_files = sorted(tasks_path.glob("*.yaml")) + sorted(tasks_path.glob("*.yml"))

    if not task_files:
        print(f"No task files found in {tasks_dir}")
        return

    print(f"\nBatch: {len(task_files)} tasks")
    print(f"Models: {', '.join(config['benchmark']['implementors'])}")

    for i, task_file in enumerate(task_files, 1):
        print(f"\n{'=' * 70}")
        print(f"  Task {i}/{len(task_files)}: {task_file.name}")
        print(f"{'=' * 70}")
        run_benchmark(str(task_file))

    logger = BenchmarkLogger(config["benchmark"]["results_dir"])
    all_runs = logger.load_all_runs()
    if all_runs:
        results_dir = Path(config["benchmark"]["results_dir"]) / "reports"
        staff_rate = config.get("staff_engineer", {}).get("hourly_rate_usd", 95.0)
        if len(all_runs) >= 4:
            print(f"\n📊 {generate_failure_analysis(all_runs, results_dir)}")
        print(f"★ {generate_cto_brief(all_runs, results_dir, staff_rate=staff_rate)}")
        print(f"🏢 {generate_enterprise_assessment(all_runs, results_dir)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Model Benchmark Harness")
    parser.add_argument("--task", help="Path to task YAML")
    parser.add_argument("--batch", help="Directory of task YAMLs")
    parser.add_argument("--report", action="store_true", help="Generate reports from existing data")
    parser.add_argument("--skip-review", action="store_true", help="Skip Opus review")
    args = parser.parse_args()

    if args.report:
        config = load_config()
        logger = BenchmarkLogger(config["benchmark"]["results_dir"])
        all_runs = logger.load_all_runs()
        results_dir = Path(config["benchmark"]["results_dir"]) / "reports"
        staff_rate = config.get("staff_engineer", {}).get("hourly_rate_usd", 95.0)
        if len(all_runs) >= 4:
            print(f"📊 {generate_failure_analysis(all_runs, results_dir)}")
        print(f"★ {generate_cto_brief(all_runs, results_dir, staff_rate=staff_rate)}")
        print(f"🏢 {generate_enterprise_assessment(all_runs, results_dir)}")
    elif args.batch:
        run_batch(args.batch)
    elif args.task:
        run_benchmark(args.task, skip_review=args.skip_review)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
