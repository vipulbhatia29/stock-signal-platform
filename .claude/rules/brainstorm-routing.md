---
description: Complexity-based brainstorm routing — skip, quick, or full Socratic mode based on design complexity score
---

# Brainstorm Routing by Design Complexity

Before invoking `superpowers:brainstorming`, score the task on three dimensions (each 1-5):

| Dimension | 1 (Low) | 3 (Medium) | 5 (High) |
|-----------|---------|------------|----------|
| **design_surface** | One obvious approach | 2-3 viable options | Many architectural choices |
| **reversibility** | Easy to change later | Moderate effort to redo | Hard to undo (DB schema, API contract) |
| **cross_cutting** | 1 module | 2-3 modules | 4+ modules or new infrastructure |

## Routing Rules

- **Score ≤ 6:** Skip brainstorming entirely. Present: "Design complexity score: X/15 — skipping brainstorm, proceeding to spec/implementation." Go directly to spec writing or implementation.
- **Score 7-10:** Quick mode. Skip Socratic questions. Go straight to: "3 options: [A], [B], [C]. I recommend [X] because [Y]. Risks: [Z]." Then proceed.
- **Score 11+:** Full Socratic brainstorming as defined in `superpowers:brainstorming`.

Present the score and routing suggestion. Override: "This scores X/15 — suggesting [quick/full] brainstorm. Deep dive instead?"

## Already-Done Detection

If the current conversation has already:
1. Explored project context for this topic
2. Proposed 2+ approaches with trade-offs
3. Converged on a design the user approved

Then brainstorming is ALREADY COMPLETE. Do NOT re-invoke the skill. Proceed to spec writing.

## Independence from LLM Triage

These dimensions measure DESIGN complexity, not IMPLEMENTATION complexity. The LLM triage score (context_span + convention_density + ambiguity) is independent. A task can score low on design (skip brainstorm) but high on implementation (use Opus), or vice versa.
