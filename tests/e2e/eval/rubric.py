"""Eval rubric — 8 dimensions for LLM-as-Judge quality assessment.

Each dimension is scored 1-5 (except hallucination which is binary).
The rubric is injected into the judge prompt as scoring criteria.
"""

DIMENSIONS = {
    "factual_grounding": {
        "name": "Factual Grounding",
        "description": "Response cites specific data from tool results (prices, scores, ratios)",
        "scale": "1-5",
        "criteria": {
            1: "No data cited, purely generic statements",
            2: "Mentions data exists but no specific values",
            3: "Cites 1-2 specific data points from tools",
            4: "Cites 3+ data points with source attribution",
            5: "Every claim backed by specific tool-sourced data",
        },
        "fail_threshold": 2,
    },
    "hallucination": {
        "name": "Hallucination Check",
        "description": "Response does NOT fabricate data not present in tool results",
        "scale": "binary",
        "criteria": {
            0: "FAIL — contains fabricated prices, scores, or statistics not in tool results",
            1: "PASS — all claims traceable to tool results or marked as estimates",
        },
        "fail_threshold": 0,
    },
    "actionability": {
        "name": "Actionability",
        "description": "Response provides clear, actionable guidance (not just data dump)",
        "scale": "1-5",
        "criteria": {
            1: "Raw data dump with no interpretation",
            2: "Data with minimal interpretation",
            3: "Clear recommendation with basic reasoning",
            4: "Recommendation with scenarios and risk context",
            5: "Personalized recommendation with portfolio-aware sizing",
        },
        "fail_threshold": 2,
    },
    "risk_disclosure": {
        "name": "Risk Disclosure",
        "description": "Response includes appropriate risk warnings and disclaimers",
        "scale": "1-5",
        "criteria": {
            1: "No risk mention at all",
            2: "Generic 'investing has risks' disclaimer",
            3: "Mentions specific risks relevant to the stock/sector",
            4: "Quantifies risk (volatility, max drawdown, bear scenario)",
            5: "Personalized risk assessment based on portfolio exposure",
        },
        "fail_threshold": 1,
    },
    "evidence_quality": {
        "name": "Evidence Quality",
        "description": "Evidence citations are specific, timestamped, and from named tools",
        "scale": "1-5",
        "criteria": {
            1: "No evidence citations",
            2: "Vague references to 'analysis' without tool names",
            3: "Names tools but no specific values or timestamps",
            4: "Names tools with specific values",
            5: "Full evidence chain: tool → value → timestamp → interpretation",
        },
        "fail_threshold": 2,
    },
    "scope_compliance": {
        "name": "Scope Compliance",
        "description": "Response stays within financial analysis scope, declines out-of-scope",
        "scale": "1-5",
        "criteria": {
            1: "Answers unrelated questions or provides personal advice",
            2: "Mostly on-topic but drifts into non-financial territory",
            3: "Stays on topic, properly declines tangential requests",
            4: "Focused analysis with clear scope boundaries",
            5: "Precisely scoped, explicitly notes what's excluded and why",
        },
        "fail_threshold": 2,
    },
    "personalization": {
        "name": "Personalization",
        "description": "Response incorporates user's portfolio context when available",
        "scale": "1-5",
        "criteria": {
            1: "Completely generic, ignores user context",
            2: "Acknowledges user holds stocks but no integration",
            3: "References holdings in recommendation",
            4: "Adjusts recommendation based on position size/sector exposure",
            5: "Full portfolio-aware analysis with concentration and sector checks",
        },
        "fail_threshold": 1,
    },
    "context_relevance": {
        "name": "Context Relevance",
        "description": "Response addresses the specific question asked, not a generic template",
        "scale": "1-5",
        "criteria": {
            1: "Generic template response unrelated to query",
            2: "Partially addresses query, mostly boilerplate",
            3: "Addresses the core question with relevant data",
            4: "Directly answers the question with supporting analysis",
            5: "Precise, targeted answer that anticipates follow-up needs",
        },
        "fail_threshold": 2,
    },
}

# Default thresholds for pass/fail
DEFAULT_MIN_SCORE = 3.0  # Average across scored dimensions
DRIFT_TOLERANCE = 0.5  # Max acceptable score drop from baseline


def build_rubric_prompt() -> str:
    """Build the rubric section for the judge LLM prompt."""
    lines = ["## Evaluation Rubric\n"]
    lines.append("Score each dimension. Return JSON with dimension keys and numeric scores.\n")

    for key, dim in DIMENSIONS.items():
        lines.append(f"### {dim['name']} (`{key}`)")
        lines.append(f"_{dim['description']}_\n")
        if dim["scale"] == "binary":
            lines.append("Score: 0 (FAIL) or 1 (PASS)")
        else:
            lines.append(f"Score: {dim['scale']}")
        for score, desc in dim["criteria"].items():
            lines.append(f"  - **{score}**: {desc}")
        lines.append("")

    return "\n".join(lines)
