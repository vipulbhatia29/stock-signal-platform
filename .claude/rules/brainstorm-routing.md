---
description: Score design complexity before brainstorming — skip if ≤6, quick if 7-10, full if 11+
---

# Brainstorm Routing

Score on three dimensions (each 1-5): **design_surface**, **reversibility**, **cross_cutting**.

- **≤ 6:** Skip brainstorming. "Design complexity X/15 — skipping brainstorm."
- **7-10:** Quick mode. Skip Socratic questions. "3 options, I recommend X because Y."
- **11+:** Full Socratic brainstorming via `superpowers:brainstorming`.

**Already done?** If the conversation already explored 2+ approaches with trade-offs and converged on a design, brainstorming is ALREADY COMPLETE. Do not re-invoke.

**Independent of LLM triage.** Design complexity ≠ implementation complexity. A task can skip brainstorm but need Opus, or vice versa.

**Plan-size gate (Hard Rule #12).** After brainstorming converges on a design, BEFORE writing the plan, estimate the plan's line count. If >500 lines → the scope needs splitting into multiple PRs. Split BEFORE entering the planning skill. See `.claude/rules/plan-execution.md`.

**Verify-before-plan gate (Hard Rule #13).** Before writing any plan that touches existing code (refactors, decorator adoption, signature changes), run the grep-based fact sheet described in `.claude/rules/plan-execution.md`. The plan should be "fact sheet + transformation", not narrative from memory.
