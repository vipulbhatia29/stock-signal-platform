# Plan Execution Discipline

## Plan Size Limit

**Plans MUST be ≤ 500 lines.** If a plan exceeds 500 lines, the scope is too big for one PR.

Split BEFORE planning:
- Each PR should touch ≤ 10 files and ≤ 500 lines of diff
- Each PR should be implementable + reviewable in 1-2 hours
- Each PR must be independently mergeable (green CI at HEAD)

A 2400-line plan that gets split after 2 rounds of review wasted 10 Opus review dispatches. Split early, split cheap.

## Verify Before Planning

Every claim in a plan must be backed by a `grep` or `read` executed in the SAME message — not from context memory.

Before writing ANY plan involving refactors/decorators/wrappers:

1. **Grep for the real signature** — read the decorator/function you're wrapping. Verify its return type, parameter names, and whether it expects sync or async functions.
2. **Grep for all callers** — `grep -rn "await _helper_name\|_helper_name(" tests/ backend/` to find every call site that will break when you change a signature.
3. **Grep for return-dict consumers** — if you're changing what a function returns, find every place that reads from that return dict (`grep -rn "result\[.status.\]\|ctx\[.pipeline_name.\]"`)
4. **Grep for existing test assertions** — find tests that assert on values you're about to change.
5. **Build a fact sheet FIRST** — dump all grep results into a structured table. The plan is the fact sheet + the transformation, not a narrative written from memory.

### Why this matters

Session 103 incident: a 2400-line plan was written from memory. Two rounds of 5-persona review caught:
- 47 test call sites that would break (not grepped)
- alerts.py consuming a return-dict status field (not grepped)
- 4 wrong module names in seed task table (not verified)
- bypass_tracked shim passing run_id to functions that don't accept it yet (logic not traced)

Every one of these was catchable with a single `grep` before writing the plan.

## Subagent Dispatch Rules

### Model selection (refines Hard Rule #11)

- **Sonnet** — ADDITIVE work: new files, new tests, mechanical decorator additions where the pattern is proven, no signature changes to existing functions.
- **Opus** — REFACTORS: changing function signatures, decorator patterns, removing/replacing existing code, any change where existing tests might break.
- **Never trust a subagent's claim of "pre-existing failures"** — always re-run tests at the pre-dispatch commit yourself.

### Mandatory subagent prompt inclusions

For any refactor subagent:

1. **Ticket description constraints verbatim** — extract pattern/constraint sentences from JIRA ticket description into Hard Constraints section.
2. **Pre-dispatch test baseline** — "baseline at commit X is N passed, 0 failed in tests/unit/tasks/. If your work ends with fewer passed or any new failures, report BLOCKED."
3. **Caller grep output** — paste the grep of every test/production caller for any function whose signature you're changing.
4. **"Run the tests and report EXACT counts"** — not "tests pass", but "N passed, M failed, K skipped" with the actual pytest output tail.

## Plan Review Rules

Plans get reviewed by 2 personas max (Backend Architect + most relevant domain expert). Code diffs get the full persona treatment per `.claude/rules/review-scaling.md`. Reviewing plans with 5 personas produces diminishing returns — the plan itself is the problem when it's too big.
