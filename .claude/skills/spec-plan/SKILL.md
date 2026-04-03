---
name: spec-plan
description: Generate spec and plan with one review cycle. Invokes brainstorming (if needed) and writing-plans in sequence, then runs combined review.
disable-model-invocation: true
argument-hint: "[feature-topic]"
---

# Spec + Plan Pipeline — $ARGUMENTS

## Your Task

Orchestrate the full spec→plan pipeline for **$ARGUMENTS** with minimal round-trips.

### Step 1: Check Brainstorming Status

Has brainstorming already been completed for this topic in the current conversation?

**Signs that brainstorming is done:**
- Design was discussed and user approved it
- A spec file already exists for this topic
- User said "I'm aligned" or "looks good" or "approved"

- If YES: skip to Step 2
- If NO: check brainstorm-routing score (design_surface + reversibility + cross_cutting)
  - Score ≤ 6: skip brainstorm, proceed to Step 2
  - Score 7-10: quick brainstorm (3 options + recommendation, no Socratic)
  - Score 11+: invoke `superpowers:brainstorming` skill fully

### Step 2: Write Spec

If brainstorming produced a spec file, it already exists. Otherwise, write the spec now.

Save to: `docs/superpowers/specs/YYYY-MM-DD-$ARGUMENTS-design.md`

The spec should cover:
- Problem statement
- Design decisions with rejected alternatives
- Architecture
- File manifest
- Success criteria
- Risks

### Step 3: Write Plan

Immediately invoke `superpowers:writing-plans` skill to create the implementation plan. Do NOT wait for a separate user review of the spec — the combined review in Step 4 covers both.

The plan MUST use the exact format expected by `superpowers:subagent-driven-development`:
- Header: `> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development...`
- Tasks: `### Task N:` with `**Files:**` section
- Steps: `- [ ]` checkbox syntax with complete code blocks
- Commands: exact `Run:` and `Expected:` for every verification

Save to: `docs/superpowers/plans/YYYY-MM-DD-$ARGUMENTS.md`

### Step 4: Combined Review

Dispatch TWO review subagents in parallel using the Agent tool:

**Subagent 1 — Spec Reviewer:**
```
Review the spec at docs/superpowers/specs/YYYY-MM-DD-$ARGUMENTS-design.md

Check for: completeness, consistency, clarity, scope, YAGNI violations.
Only flag issues that would cause real problems during implementation.
Output: Status (Approved/Issues Found), Issues list, Recommendations.
```

**Subagent 2 — Plan Reviewer:**
```
Review the plan at docs/superpowers/plans/YYYY-MM-DD-$ARGUMENTS.md
against the spec at docs/superpowers/specs/YYYY-MM-DD-$ARGUMENTS-design.md

Check for: spec coverage, placeholders, task decomposition, buildability.
Only flag issues that would block an engineer during implementation.
Output: Status (Approved/Issues Found), Issues list, Recommendations.
```

Present combined findings. Fix any issues inline in the spec/plan files.

### Step 5: Offer Execution Choice

"Spec and plan complete:
- Spec: `docs/superpowers/specs/YYYY-MM-DD-$ARGUMENTS-design.md`
- Plan: `docs/superpowers/plans/YYYY-MM-DD-$ARGUMENTS.md`

Two execution options:
1. **Subagent-Driven** (recommended) — fresh subagent per task, two-stage review
2. **Inline Execution** — batch execution with checkpoints

Which approach?"

If Subagent-Driven: invoke `superpowers:subagent-driven-development`
If Inline: invoke `superpowers:executing-plans`

## Key Constraints
- Spec and plan are TWO SEPARATE FILES — never merge them
- Plan must be consumable by existing superpowers execution skills without modification
- One review cycle covers both docs — this is where the token savings come from
- If brainstorming was already done, do NOT re-invoke it
