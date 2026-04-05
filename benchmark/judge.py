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
    """Direct API call to Opus. Returns (response_text, input_tokens, output_tokens)."""
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
    rubric_path = Path(__file__).parent / "scoring_rubric.yaml"
    return rubric_path.read_text()


def _anonymize(model_ids: list[str]) -> tuple[dict[str, str], dict[str, str]]:
    labels = list(string.ascii_uppercase[: len(model_ids)])
    random.shuffle(labels)
    model_to_label = dict(zip(model_ids, labels))
    label_to_model = {v: k for k, v in model_to_label.items()}
    return model_to_label, label_to_model


def _parse_json(text: str) -> dict:
    """Parse JSON from response, handling non-JSON wrapping."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
        raise


class OpusJudge:
    """Two-pass Opus review: blind scoring then fix estimation."""

    def __init__(self) -> None:
        self.total_input_tokens = 0
        self.total_output_tokens = 0

    def score(
        self,
        task_description: str,
        implementations: dict[str, dict],
    ) -> OpusReview:
        """Pass 1: Blind comparative scoring of all implementations."""
        model_ids = list(implementations.keys())
        model_to_label, label_to_model = _anonymize(model_ids)
        rubric = _load_rubric()

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
            "ranking": sorted(model_to_label.values()),
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

        response_text, in_tok, out_tok = _call_opus(system, user, max_tokens=4096)
        self.total_input_tokens += in_tok
        self.total_output_tokens += out_tok

        data = _parse_json(response_text)

        review = OpusReview()
        review.review_input_tokens = in_tok
        review.review_output_tokens = out_tok

        for label, scores_data in data.get("implementations", {}).items():
            model_id = label_to_model.get(label, label)
            sc = scores_data.get("scores", scores_data)
            opus_scores = OpusScores(
                correctness=sc.get("correctness", 0),
                convention_adherence=sc.get("convention_adherence", 0),
                integration_safety=sc.get("integration_safety", 0),
                completeness=sc.get("completeness", 0),
                code_quality=sc.get("code_quality", 0),
                first_pass_success=sc.get("first_pass_success", 0),
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

        response_text, in_tok, out_tok = _call_opus(system, user, max_tokens=2048)
        self.total_input_tokens += in_tok
        self.total_output_tokens += out_tok

        data = _parse_json(response_text)

        summary = FixSummary(model_id=model_id, opus_fix_tokens=in_tok + out_tok)
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
