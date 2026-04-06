---
name: reviewing-code
description: Score code changes and route to appropriate review depth with auto-selected personas. Use when completing tasks, before committing, or when user asks for code review.
---

# Review Configuration

When `superpowers:requesting-code-review` is invoked, score the changes and recommend the appropriate review depth. Always present the score and recommendation — PM decides whether to skip, adjust, or proceed.

## Step 1: Score the Change

| Dimension | 1 (Low) | 3 (Medium) | 5 (High) |
|-----------|---------|------------|----------|
| **lines_changed** | < 30 lines | 30–150 lines | 150+ lines |
| **risk_surface** | Internal/logging/comments | Existing behavior change | New API contract, auth flow, DB schema, or data model |
| **cross_module** | 1–2 files in same module | 3–5 files across 2 modules | 6+ files or 3+ modules or new infrastructure |

**Total = lines_changed + risk_surface + cross_module** (range 3–15)

## Step 2: Route by Score

| Score | Depth | What Happens |
|-------|-------|-------------|
| **3–6** | **Skip** | No formal review. Lint + tests + Semgrep are sufficient. Present: "Review score X/15 — recommend skip. Lint/tests/Semgrep all green. Commit? (or force review)" |
| **7–10** | **Quick** | 1–2 personas, inline in conversation (no agent dispatch). Opus reads the diff and reviews from those perspectives. Present: "Review score X/15 — quick review with [Persona A, Persona B]. Proceed?" |
| **11–15** | **Full** | Full agent-dispatched review, 1 round, personas auto-selected per Step 3. Present: "Review score X/15 — full 5-persona review. Adjust personas or add a round?" |

## Step 3: Select Personas by Change Type

See [personas.md](personas.md) for the full change-type-to-persona mapping table and persona count rules by depth.

## Step 4: Present the Recommendation

Always show this to the PM before proceeding:

```
Review score: X/15 (lines: X, risk: X, cross-module: X)
Change types: [API, Backend Services, ...]
Recommendation: [Skip / Quick / Full]
Personas: [list, or "none — automated checks sufficient"]
[Proceed? / Commit? / Adjust?]
```

## Round Control

### Initial review
- Default: **1 round** of initial review
- Never run multiple escalating initial rounds — one round catches 95% of issues

### Post-fix verification (MANDATORY)
- After fixing HIGH+ findings: **always** re-review the changed files
- Re-review is focused (only personas that flagged issues, only files that changed)
- This is NOT a "second round" — it is fix verification, a distinct step
- Skip re-review ONLY if all findings were LOW/MEDIUM and fixes were trivial (rename, typo)

### The distinction
- **Initial review** = "What's wrong with this code?" → 1 round
- **Fix verification** = "Did the fix actually address the finding? Did it introduce new issues?" → always after HIGH+ fixes
- Skipping fix verification was the source of a real bug in Session 96 (ticker case mismatch fix was applied but never verified)

### Per-task reviews (subagent-driven development)
- When using subagent-driven-development, each task gets its own spec + quality review loop per the skill's process
- The final holistic review (this config) runs AFTER all tasks complete — it is the capstone, not the only review
- Do not skip per-task reviews and defer everything to the final review

## Override Rules

- PM can always force a higher depth ("force review" on a skip, "full review" on a quick)
- PM can always force a lower depth ("skip review" on a full) — but Opus should flag if risk_surface ≥ 4
- Phase-end review (via `/phase-closeout`) always runs Full regardless of score — it includes additional dimensions from the phase-closeout skill

## Examples

| Scenario | Lines | Risk | Cross | Score | Depth | Personas |
|----------|:-----:|:----:|:-----:|:-----:|-------|----------|
| Fix `str(e)` in one file | 1 | 1 | 1 | **3** | Skip | — |
| Scope analytics to user-only | 1 | 3 | 1 | **5** | Skip | — |
| Split health endpoint + add auth | 3 | 3 | 1 | **7** | Quick | Security Engineer |
| New API router + service + tests | 3 | 5 | 3 | **11** | Full | API Designer, Backend Architect, Security Engineer |
| Auth overhaul (OAuth + email verify) | 5 | 5 | 5 | **15** | Full | Security, Crypto, Full-Stack, PM, QA |
| Spec document review | 1 | 3 | 1 | **5** | Skip as code review, but PM review of spec content separately |
