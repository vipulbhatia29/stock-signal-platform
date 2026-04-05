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
    return f"${v:.4f}" if v < 1 else f"${v:.2f}"


def _tl(score: float) -> str:
    if score >= 7.5:
        return "✅"
    if score >= 5.0:
        return "⚠️"
    return "❌"


def _avg(lst: list) -> float:
    return sum(lst) / len(lst) if lst else 0.0


def _get_ws(scores: dict, model_id: str) -> float:
    s = scores.get(model_id, {})
    return s.get("weighted_score", 0) if isinstance(s, dict) else 0


def _model_short(m: str) -> str:
    return m.replace("claude-", "").replace("moonshotai/", "")[:18]


def generate_per_task_report(run: dict, output_dir: Path) -> Path:
    """Report 1 — generated after each benchmark task."""
    task_name = run.get("task_name", "Unknown Task")
    task_id = run.get("task_id", "unknown")
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
    sep = " | ".join(["---"] * (len(model_ids) + 1))

    lines = [
        f"# Benchmark Report — {task_name}\n",
        f"**Task:** {task_id} | **Tier:** {tier} | **JIRA:** {jira}",
        f"**Date:** {timestamp} | **Run ID:** {run_id}",
        f"**Winner:** {winner} | **Total cost:** {_fmt(run.get('total_benchmark_cost_usd', 0))}\n",
        "## Complexity Profile\n",
        "| Dimension | Score |\n|---|---|",
    ]
    for dim in ["context_span", "reasoning_depth", "integration_surface",
                 "convention_density", "implicit_knowledge", "verification_difficulty", "failure_cost"]:
        lines.append(f"| {dim.replace('_', ' ').title()} | {complexity.get(dim, '?')}/5 |")
    cx_total = complexity.get("total", sum(complexity.get(d, 0) for d in [
        "context_span", "reasoning_depth", "integration_surface",
        "convention_density", "implicit_knowledge", "verification_difficulty", "failure_cost"]))
    lines.append(f"| **Total** | **{cx_total}/35 → {tier}** |\n")

    # Results summary
    lines.append("## Results Summary\n")
    lines.append(f"| Metric | {' | '.join(hdrs)} |")
    lines.append(f"|{sep}|")

    ws_cells = []
    for m in model_ids:
        ws = _get_ws(scores, m)
        ws_cells.append(f"{_tl(ws)} {ws:.1f}/10")
    lines.append(f"| **Weighted Score** | {' | '.join(ws_cells)} |")

    for label, key, fmt in [
        ("Tests Passed", "tests_passed", "{}"), ("Tests Total", "tests_total", "{}"),
        ("Lint Violations", "lint_violations", "{}"), ("First-Pass", "first_pass_success", "{}"),
        ("Input Tokens", "input_tokens", "{:,}"), ("Output Tokens", "output_tokens", "{:,}"),
        ("**Actual Cost**", "actual_cost_usd", "${:.4f}"),
        ("Wall Clock", "wall_clock_ms", "{:.0f}ms"), ("Tok/s", "tokens_per_second", "{:.0f}"),
        ("Turns", "num_turns", "{}"), ("Files Changed", "files_changed", "{}"),
    ]:
        cells = []
        for m in model_ids:
            v = models_data.get(m, {}).get(key, "—")
            cells.append(fmt.format(v) if isinstance(v, (int, float)) else str(v))
        lines.append(f"| {label} | {' | '.join(cells)} |")

    # So what
    winner_ws = _get_ws(scores, winner)
    winner_cost = models_data.get(winner, {}).get("actual_cost_usd", 0)
    sonnet_cost = models_data.get("claude-sonnet-4-6", {}).get("actual_cost_usd", 0)
    if winner != "claude-sonnet-4-6" and sonnet_cost > 0 and winner_cost > 0:
        lines.append(f"\n**So what:** {_model_short(winner)} won at {_fmt(winner_cost)} — "
                      f"{sonnet_cost / winner_cost:.0f}x cheaper than Sonnet's {_fmt(sonnet_cost)}.\n")
    else:
        lines.append(f"\n**So what:** {_model_short(winner)} produced the best implementation ({winner_ws:.1f}/10).\n")

    # Dimension scores
    lines.append("## Dimension Scores (Opus Blind Review)\n")
    lines.append(f"| Dimension (weight) | {' | '.join(hdrs)} |")
    lines.append(f"|{sep}|")
    for dim, weight in [("correctness", "25%"), ("convention_adherence", "20%"),
                         ("integration_safety", "20%"), ("completeness", "15%"),
                         ("code_quality", "10%"), ("first_pass_success", "10%")]:
        cells = []
        for m in model_ids:
            s = scores.get(m, {})
            sc = s.get("scores", s) if isinstance(s, dict) else {}
            v = sc.get(dim, s.get(dim, "—")) if isinstance(sc, dict) else "—"
            cells.append(f"{v}/10" if isinstance(v, (int, float)) else str(v))
        lines.append(f"| {dim.replace('_', ' ').title()} ({weight}) | {' | '.join(cells)} |")

    # Winner rationale
    lines.append(f"\n## Opus Review\n")
    lines.append(f"> An independent AI reviewer, not knowing which model produced which code, "
                  f'chose {_model_short(winner)} because: "{review.get("winner_rationale", "N/A")}"\n')

    # Cost efficiency
    lines.append("## Cost Efficiency\n")
    lines.append(f"| Metric | {' | '.join(hdrs)} |")
    lines.append(f"|{sep}|")
    for label, key, fmt in [
        ("$/QP", "cost_per_quality_point", "${:.4f}"), ("Cost vs Sonnet", "cost_ratio_vs_sonnet", "{:.2f}x"),
        ("Speed vs Sonnet", "speed_ratio_vs_sonnet", "{:.2f}x"), ("Value (Q/$)", "value_score", "{:.0f}"),
        ("Net Cost", "net_cost", "${:.4f}"),
    ]:
        cells = []
        for m in model_ids:
            d = derived.get(m, {})
            v = d.get(key, 0) if isinstance(d, dict) else 0
            cells.append(fmt.format(v) if isinstance(v, (int, float)) else str(v))
        lines.append(f"| {label} | {' | '.join(cells)} |")

    output_path = output_dir / f"{run_id}.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines))
    return output_path


def generate_failure_analysis(runs: list[dict], output_dir: Path) -> Path:
    """Report 2 — failure patterns after 4+ tasks."""
    model_ids = list(runs[0].get("models", {}).keys())
    n = len(runs)
    model_patterns: dict[str, list[dict]] = defaultdict(list)
    tier_results: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))

    for run in runs:
        review = run.get("opus_review", {})
        sc = review.get("scores", {})
        tier = run.get("task_tier", "?")
        task_id = run.get("task_id", "")
        for m in model_ids:
            ws = _get_ws(sc, m)
            tier_results[tier][m].append(ws)
            s = sc.get(m, {}) if isinstance(sc.get(m), dict) else {}
            for issue in s.get("specific_issues", []):
                model_patterns[m].append({"issue": issue, "task": task_id, "tier": tier, "score": ws})
            for viol in s.get("convention_violations", []):
                model_patterns[m].append({"issue": f"Convention: {viol}", "task": task_id, "tier": tier, "score": ws})
            if s.get("hallucinated_apis", 0) > 0:
                model_patterns[m].append({"issue": f"Hallucinated {s['hallucinated_apis']} APIs", "task": task_id, "tier": tier, "score": ws})

    lines = [f"# Failure Pattern Analysis — After {n} Tasks\n"]
    for m in model_ids:
        lines.append(f"### {_model_short(m)}\n")
        pats = model_patterns.get(m, [])
        if not pats:
            lines.append("No failure patterns detected.\n")
            continue
        lines.append("| Pattern | Task | Tier | Score |\n|---|---|---|---|")
        for p in pats[:20]:
            lines.append(f"| {p['issue'][:80]} | {p['task']} | {p['tier']} | {p['score']:.1f} |")
        lines.append("")

    lines.append("## Capability Ceiling by Tier\n")
    lines.append(f"| Tier | {' | '.join(_model_short(m) for m in model_ids)} |")
    lines.append(f"|---|{'---|' * len(model_ids)}")
    for tier in sorted(tier_results.keys()):
        cells = [f"{_tl(_avg(tier_results[tier][m]))} {_avg(tier_results[tier][m]):.1f}" for m in model_ids]
        lines.append(f"| {tier} | {' | '.join(cells)} |")
    lines.append(f"\nLegend: ✅ ≥7.5 | ⚠️ 5.0–7.4 | ❌ <5.0\n")

    lines.append("## Interim Assessment\n")
    for m in model_ids:
        all_sc = [_get_ws(r.get("opus_review", {}).get("scores", {}), m) for r in runs]
        a = _avg(all_sc)
        status = "✅ On track" if a >= 7.5 else "⚠️ Struggling" if a >= 5.0 else "❌ Failing"
        lines.append(f"- **{_model_short(m)}:** {status} — avg {a:.1f}/10 across {n} tasks")

    output_path = output_dir / "failure-analysis.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines))
    return output_path


def generate_cto_brief(runs: list[dict], output_dir: Path, monthly_task_volume: int = 40, staff_rate: float = 95.0) -> Path:
    """Report 3 — CTO Decision Brief."""
    if not runs:
        p = output_dir / "cto-decision-brief.md"
        p.write_text("# No benchmark data.\n")
        return p

    model_ids = list(runs[0].get("models", {}).keys())
    n = len(runs)
    total_cost = sum(r.get("total_benchmark_cost_usd", 0) for r in runs)

    stats: dict[str, dict] = {m: {
        "scores": [], "costs": [], "times": [], "wins": 0, "tasks": 0,
        "fix_minutes": [], "pr_blocks": 0, "fix_types": defaultdict(int), "dim_scores": defaultdict(list),
    } for m in model_ids}
    tier_scores: dict[str, dict[str, list]] = defaultdict(lambda: {m: [] for m in model_ids})
    cx_scores: dict[str, dict[str, list]] = defaultdict(lambda: {m: [] for m in model_ids})

    for run in runs:
        review = run.get("opus_review", {})
        sc = review.get("scores", {})
        fs = review.get("fix_summaries", {})
        tier = run.get("task_tier", "?")
        winner = review.get("winner", "")
        cx = run.get("complexity", {})
        cx_t = cx.get("total", 0) if isinstance(cx, dict) else 0
        band = "7-12" if cx_t <= 12 else "13-18" if cx_t <= 18 else "19-25" if cx_t <= 25 else "26-35"

        for m in model_ids:
            md = run.get("models", {}).get(m, {})
            s = sc.get(m, {}) if isinstance(sc.get(m), dict) else {}
            f = fs.get(m, {}) if isinstance(fs.get(m), dict) else {}
            ws = s.get("weighted_score", 0)
            stats[m]["scores"].append(ws)
            stats[m]["costs"].append(md.get("actual_cost_usd", 0))
            stats[m]["times"].append(md.get("wall_clock_ms", 0) / 1000 if md.get("wall_clock_ms") else 0)
            stats[m]["tasks"] += 1
            if m == winner:
                stats[m]["wins"] += 1
            stats[m]["fix_minutes"].append(f.get("total_fix_minutes", 0))
            if f.get("would_block_pr"):
                stats[m]["pr_blocks"] += 1
            for ft, cnt in f.get("by_type", {}).items():
                stats[m]["fix_types"][ft] += cnt
            for dim in ["correctness", "convention_adherence", "integration_safety", "completeness", "code_quality", "first_pass_success"]:
                v = s.get("scores", s).get(dim, s.get(dim, 0)) if isinstance(s, dict) else 0
                stats[m]["dim_scores"][dim].append(v if isinstance(v, (int, float)) else 0)
            tier_scores[tier][m].append(ws)
            cx_scores[band][m].append(ws)

    lines = [
        "# Model Benchmark — CTO Decision Brief\n",
        f"**Date:** {runs[-1].get('timestamp', '')[:10]}",
        f"**Scope:** {n} real JIRA tasks | **Models:** {', '.join(_model_short(m) for m in model_ids)}",
        f"**Total cost:** {_fmt(total_cost)} | **Tasks merged:** {n}\n",
        "---\n",
        "## How This Was Conducted\n",
        "Fully automated. Every task was a real JIRA ticket — winners merged to codebase. "
        "Opus 4.6 reviewed blind (no model names visible during scoring).\n",
        "---\n",
    ]

    # Executive summary
    best_v = max(model_ids, key=lambda m: _avg(stats[m]["scores"]) / max(_avg(stats[m]["costs"]), 0.001))
    son_avg = _avg(stats.get("claude-sonnet-4-6", stats[model_ids[0]])["scores"])
    bv_avg = _avg(stats[best_v]["scores"])
    bv_cost = _avg(stats[best_v]["costs"])
    son_cost = _avg(stats.get("claude-sonnet-4-6", stats[model_ids[0]])["costs"])

    lines.append("## Executive Summary\n")
    if best_v != "claude-sonnet-4-6" and son_avg > 0 and son_cost > 0:
        lines.append(f"> {_model_short(best_v)} delivers {bv_avg/son_avg*100:.0f}% of Sonnet's quality "
                      f"at {bv_cost/son_cost*100:.0f}% of the cost.\n")
    else:
        lines.append(f"> Sonnet 4.6 remains the quality leader at {son_avg:.1f}/10 avg.\n")

    # Overall performance
    lines.append("## Overall Performance\n")
    lines.append("| Model | Avg Score | Win% | Avg Cost | $/QP | Time | Value |")
    lines.append("|---|---|---|---|---|---|---|")
    for m in model_ids:
        s = stats[m]
        a_s = _avg(s["scores"]); wr = s["wins"]/max(s["tasks"],1)*100; a_c = _avg(s["costs"])
        cpqp = a_c / a_s if a_s > 0 else 0; a_t = _avg(s["times"]); val = a_s / a_c if a_c > 0 else 0
        lines.append(f"| {_model_short(m)} | {_tl(a_s)} {a_s:.1f} | {wr:.0f}% | {_fmt(a_c)} | {_fmt(cpqp)} | {a_t:.0f}s | {val:.0f} |")

    # By tier
    lines.append("\n## By Tier\n")
    lines.append(f"| Tier | {' | '.join(_model_short(m) for m in model_ids)} | Best Value |")
    lines.append(f"|---|{'---|' * len(model_ids)}---|")
    for tier in sorted(tier_scores.keys()):
        avgs = {m: _avg(tier_scores[tier][m]) for m in model_ids}
        cells = [f"{_tl(avgs[m])} {avgs[m]:.1f}" for m in model_ids]
        bst = max(model_ids, key=lambda m: avgs.get(m, 0) / max(_avg(stats[m]["costs"]), 0.001))
        lines.append(f"| {tier} | {' | '.join(cells)} | {_model_short(bst)} |")

    # Quality floor
    lines.append("\n## Quality Floor\n")
    lines.append("| Model | ≥7.5 (merge) | 5-7.4 (fix) | <5 (reject) |")
    lines.append("|---|---|---|---|")
    for m in model_ids:
        sc = stats[m]["scores"]; t = len(sc)
        mg = sum(1 for s in sc if s >= 7.5); fx = sum(1 for s in sc if 5.0 <= s < 7.5); rj = sum(1 for s in sc if s < 5.0)
        lines.append(f"| {_model_short(m)} | {mg}/{t} ({mg/max(t,1)*100:.0f}%) | {fx}/{t} | {rj}/{t} |")

    # Monthly projection
    lines.append("\n## Monthly Cost Projection\n")
    t12 = int(monthly_task_volume * 0.67); t34 = monthly_task_volume - t12
    curr = monthly_task_volume * son_cost
    alt = best_v if best_v != "claude-sonnet-4-6" else model_ids[1] if len(model_ids) > 1 else model_ids[0]
    alt_c = _avg(stats[alt]["costs"])
    prop = t12 * alt_c + t34 * son_cost
    sav = curr - prop
    lines.append(f"| Scenario | Monthly cost |\n|---|---|")
    lines.append(f"| Current (Sonnet only, {monthly_task_volume} tasks) | {_fmt(curr)}/mo |")
    lines.append(f"| Proposed ({_model_short(alt)} T1-T2, Sonnet T3-T4) | {_fmt(prop)}/mo |")
    lines.append(f"| **Savings** | **{_fmt(sav)}/mo ({sav/max(curr,0.01)*100:.0f}%), {_fmt(sav*12)}/yr** |")

    # True cost with staff cleanup
    lines.append("\n## True Cost (including staff cleanup)\n")
    lines.append("| Model | Impl | Review | Staff | **Net** | vs Sonnet |")
    lines.append("|---|---|---|---|---|---|")
    son_net = 0
    for m in model_ids:
        impl = _avg(stats[m]["costs"]); rev = total_cost / n / len(model_ids) if n else 0
        staff = _avg(stats[m]["fix_minutes"]) / 60 * staff_rate; net = impl + rev + staff
        if m == "claude-sonnet-4-6": son_net = net
        vs = f"{net/son_net*100:.0f}%" if son_net > 0 else "—"
        lines.append(f"| {_model_short(m)} | {_fmt(impl)} | {_fmt(rev)} | {_fmt(staff)} ({_avg(stats[m]['fix_minutes']):.0f}m) | **{_fmt(net)}** | {vs} |")

    # Fix type distribution
    lines.append("\n## Fix Types\n")
    fts = ["bug", "convention", "missing_feature", "security", "over_engineering", "test_gap"]
    lines.append(f"| Type | {' | '.join(_model_short(m) for m in model_ids)} |")
    lines.append(f"|---|{'---|' * len(model_ids)}")
    for ft in fts:
        cells = []
        for m in model_ids:
            cnt = stats[m]["fix_types"].get(ft, 0); tot = sum(stats[m]["fix_types"].values())
            cells.append(f"{cnt} ({cnt/max(tot,1)*100:.0f}%)")
        lines.append(f"| {ft.replace('_',' ').title()} | {' | '.join(cells)} |")

    # Dimension analysis
    lines.append("\n## Dimension Analysis\n")
    lines.append(f"| Dimension | {' | '.join(_model_short(m) for m in model_ids)} | Gap |")
    lines.append(f"|---|{'---|' * len(model_ids)}---|")
    for dim in ["correctness", "convention_adherence", "integration_safety", "completeness", "code_quality", "first_pass_success"]:
        avgs = {m: _avg(stats[m]["dim_scores"][dim]) for m in model_ids}
        gap = max(avgs.values()) - min(avgs.values())
        cells = [f"{avgs[m]:.1f}" for m in model_ids]
        lines.append(f"| {dim.replace('_',' ').title()} | {' | '.join(cells)} | {gap:.1f} |")

    # Complexity ceilings
    lines.append("\n## Complexity Ceilings\n")
    lines.append("| Model | Max for ≥7.5 | Max for ≥5.0 |")
    lines.append("|---|---|---|")
    for m in model_ids:
        c75 = c50 = "—"
        for band in ["7-12", "13-18", "19-25", "26-35"]:
            a = _avg(cx_scores.get(band, {}).get(m, []))
            if a >= 7.5: c75 = band
            if a >= 5.0: c50 = band
        lines.append(f"| {_model_short(m)} | {c75} | {c50} |")

    # Risk + recommendation
    lines.append("\n## Risk Assessment\n")
    lines.append("| Factor | Sonnet | MiniMax | Qwen3 |\n|---|---|---|---|")
    lines.append("| API stability | High | Medium | Medium |")
    lines.append("| Fallback | — | Sonnet | Sonnet/MiniMax |")
    lines.append("| Bedrock? | Yes | Yes (announced) | No |")

    lines.append("\n## Recommendation\n")
    lines.append("### Immediate\n*To be filled after benchmark completes.*\n")
    lines.append("### Short-term (30 days)\n*TBD.*\n")
    lines.append("### Long-term (quarter)\n*TBD.*\n")

    # Glossary
    lines.append("---\n\n## Glossary\n")
    lines.append("| Term | Definition |\n|---|---|")
    for t, d in [
        ("Weighted Score", "1-10 across 6 dimensions, weighted by project importance"),
        ("$/QP", "Cost per quality point. Lower = more efficient"),
        ("Value (Q/$)", "Quality per dollar. Higher = better"),
        ("Net Cost", "Impl + review + staff cleanup = true cost"),
        ("PR Block Rate", "% of tasks needing critical/high fixes before merge"),
        ("T1-T4", "T1: simple. T2: feature. T3: multi-file. T4: refactor"),
        ("Capability Ceiling", "Max complexity for ≥7.5 score"),
    ]:
        lines.append(f"| **{t}** | {d} |")

    p = output_dir / "cto-decision-brief.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(lines))
    return p


def generate_enterprise_assessment(runs: list[dict], output_dir: Path) -> Path:
    """Report 4 — enterprise readiness."""
    model_ids = list(runs[0].get("models", {}).keys()) if runs else []
    n = len(runs)
    has_groq = any(not r.get("models", {}).get("qwen3-32b", {}).get("is_error", True) for r in runs)
    has_mm = any(not r.get("models", {}).get("MiniMax-M2.5", {}).get("is_error", True) for r in runs)

    lines = [
        "# Multi-Model Architecture — Enterprise Readiness\n",
        "## Patterns Validated\n",
        f"- **Direct Anthropic-compat (MiniMax):** {'✅' if has_mm else '❌'} — no proxy needed",
        f"- **Proxy (LiteLLM → Groq):** {'✅' if has_groq else '❌'} — OpenAI models via Claude Code",
        f"- **Bedrock:** Not tested — LiteLLM supports it\n",
        "## Deployment Options\n",
        "| Option | Models | Cost | Quality |",
        "|---|---|---|---|",
        "| A: Anthropic-only | Sonnet + Opus | $$$$ | Highest |",
        f"| B: Hybrid | {'MiniMax' if has_mm else 'TBD'} + Sonnet + Opus | $$ | High |",
        "| C: Bedrock | Customer models + Opus | $ | Depends |",
        f"| D: Open-source | {'Qwen3' if has_groq else 'TBD'} + Opus | $ | Medium |\n",
        f"## Evidence\n- {n} tasks, {_fmt(sum(r.get('total_benchmark_cost_usd',0) for r in runs))} total cost",
        "- All data archived for reproducibility",
    ]

    p = output_dir / "enterprise-readiness.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(lines))
    return p
