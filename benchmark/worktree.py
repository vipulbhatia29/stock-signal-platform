"""Git worktree management for parallel model benchmarking."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


def run_git(args: list[str], cwd: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=60,
    )


def get_project_root() -> Path:
    result = run_git(["rev-parse", "--show-toplevel"])
    if result.returncode != 0:
        raise RuntimeError(f"Not in a git repo: {result.stderr}")
    return Path(result.stdout.strip())


def create_worktrees(
    model_ids: list[str],
    base_branch: str = "develop",
    worktree_dir: str = ".benchmark",
) -> dict[str, Path]:
    root = get_project_root()
    wt_base = root / worktree_dir
    wt_base.mkdir(parents=True, exist_ok=True)

    run_git(["checkout", base_branch], cwd=str(root))
    run_git(["pull", "origin", base_branch], cwd=str(root))

    worktrees: dict[str, Path] = {}
    for model_id in model_ids:
        safe_name = model_id.lower().replace(".", "-").replace(" ", "-")
        wt_name = f"wt-{safe_name}"
        wt_path = wt_base / wt_name
        branch_name = f"benchmark/{safe_name}"

        if wt_path.exists():
            run_git(["worktree", "remove", str(wt_path), "--force"], cwd=str(root))
        run_git(["branch", "-D", branch_name], cwd=str(root))

        result = run_git(
            ["worktree", "add", "-b", branch_name, str(wt_path), base_branch],
            cwd=str(root),
        )
        if result.returncode != 0:
            raise RuntimeError(f"Failed to create worktree for {model_id}: {result.stderr}")

        worktrees[model_id] = wt_path

    return worktrees


def collect_git_metrics(worktree_path: Path) -> dict:
    cwd = str(worktree_path)

    stat = run_git(["diff", "--stat", "HEAD"], cwd=cwd)
    files_changed = sum(1 for line in stat.stdout.strip().split("\n") if " | " in line)

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

    diff = run_git(["diff", "HEAD"], cwd=cwd)

    return {
        "files_changed": files_changed,
        "lines_added": lines_added,
        "lines_removed": lines_removed,
        "diff_text": diff.stdout[:50000],
    }


def run_tests_in_worktree(worktree_path: Path) -> dict:
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

    for line in output.split("\n"):
        line = line.strip()
        if "passed" in line or "failed" in line or "error" in line:
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
        "test_output": output[:10000],
    }


def run_lint_in_worktree(worktree_path: Path) -> dict:
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
    cwd = str(worktree_path)

    run_git(["add", "-A"], cwd=cwd)
    commit_result = run_git(
        ["commit", "-m", f"feat: {task_name} (benchmark winner: {model_id}, score: {score:.1f})"],
        cwd=cwd,
    )
    if commit_result.returncode != 0:
        return None

    branch = run_git(["branch", "--show-current"], cwd=cwd).stdout.strip()
    push_result = run_git(["push", "origin", branch], cwd=cwd)
    if push_result.returncode != 0:
        return None

    pr_body = (
        f"## Benchmark Result\n\n"
        f"- **Winner:** {model_id}\n"
        f"- **Score:** {score:.1f}/10\n"
        f"- **Cost:** ${cost:.4f}\n"
        f"- **Task:** {task_id}\n\n"
        f"Generated by model benchmark framework.\n\n"
        f"🤖 Generated with [Claude Code](https://claude.com/claude-code)"
    )

    pr_result = subprocess.run(
        ["gh", "pr", "create", "--base", "develop", "--head", branch,
         "--title", f"[Benchmark] {task_name}", "--body", pr_body],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=30,
    )

    if pr_result.returncode == 0:
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
    root = get_project_root()
    wt_base = root / worktree_dir

    for model_id in model_ids:
        safe_name = model_id.lower().replace(".", "-").replace(" ", "-")
        wt_path = wt_base / f"wt-{safe_name}"
        branch_name = f"benchmark/{safe_name}"

        if wt_path.exists():
            run_git(["worktree", "remove", str(wt_path), "--force"], cwd=str(root))
        run_git(["branch", "-D", branch_name], cwd=str(root))

    if wt_base.exists() and not any(wt_base.iterdir()):
        wt_base.rmdir()
