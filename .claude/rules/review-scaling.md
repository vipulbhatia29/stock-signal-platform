# Review Scaling

Scale review depth to diff size AND authorship trust. Over-reviewing small diffs wastes Opus tokens. Under-reviewing large diffs or subagent output misses bugs.

## Routing Table

| Diff size | Persona count | Who | When to upgrade |
|---|---|---|---|
| **< 100 lines** | 0 (self-review only) | — | Upgrade to 1-2 if touching auth, DB migrations, or security-sensitive paths |
| **100-300 lines** | 2-3 personas | Backend Architect + Test Engineer (mandatory when tests in diff) + 1 domain expert if cross-module | — |
| **300-500 lines** | 3-4 personas | Add Reliability if touching error handling/retry/fire-and-forget paths; add DB/SQL if migrations in diff | — |
| **500+ lines** | Don't review — split the PR first | — | Hard Rule #12: plans > 500 lines = scope too big |

## Authorship trust adjustment

Diff size is necessary but not sufficient. Upgrade review depth when:

| Factor | Adjustment |
|---|---|
| **Subagent-authored code** | +1 persona minimum, regardless of diff size. Subagents cannot self-assess risk. A 50-line subagent diff touching 10 files needs at least a read-back, not blind merge. |
| **Multi-file refactor** (≥5 files) | +1 persona if any file has import/signature changes. Mechanical != safe when hoisting closures or rewiring call sites. |
| **Code you haven't read** | NEVER merge without at least reading the diff. "Tests pass" is not a substitute for understanding what shipped. |

The cost of a post-merge review catching nothing is low. The cost of skipping review and shipping a subtle bug (wrong closure capture, dead import, broken call site) is a revert + incident.

## Persona selection priority

1. **Test Engineer** — MANDATORY when tests are in the diff (per `feedback_review_verification_mandatory.md`)
2. **Backend Architect** — for any refactor touching function signatures, decorator patterns, or module boundaries
3. **Reliability** — for error handling, retry semantics, fire-and-forget paths, kill switches
4. **DB/SQL Expert** — for migrations, query changes, session scoping, row volume changes
5. **Performance** — only when the diff touches hot paths (per-ticker loops, request handlers, query paths)

## Plan reviews (different from code reviews)

Plans are reviewed by **2 personas max**: Backend Architect + the single most relevant domain expert. The plan itself should be ≤ 500 lines (Hard Rule #12). If 5 personas are needed to find the bugs in your plan, the plan is too big — split first.

## Re-review rules

After fixing CRITICAL or HIGH findings:
- **Test Engineer** re-review is ALWAYS mandatory if tests changed
- Re-review the persona(s) whose specific finding was fixed
- Other personas do NOT need re-review unless the fix touched their lane

## Session 103 evidence

PR #210 (130 lines): 5 personas, 1 round — found 1 convergent issue (bounds validation). Good ROI.
Monolithic plan (2400 lines): 5 personas, 2 rounds (10 dispatches) — found ~15 issues, most caused by plan being too big. Bad ROI. The fix was splitting into 4 smaller PRs, not more review rounds.
