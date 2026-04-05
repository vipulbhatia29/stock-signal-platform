---
name: closing-out-phase
description: Performs end-of-phase ceremony — applies accumulated doc deltas, runs phase-end review, updates project-plan and PROJECT_INDEX. Use when user says "phase closeout", "end of phase", "wrap up the phase", "finalize phase", or invokes /phase-closeout.
disable-model-invocation: true
context: fork
effort: high
allowed-tools:
  - Read
  - Edit
  - Write
  - Glob
  - Grep
  - Bash(git log *)
  - Bash(git diff *)
  - Bash(wc *)
  - mcp__plugin_serena_serena__read_memory
  - mcp__plugin_serena_serena__write_memory
  - mcp__plugin_serena_serena__list_memories
  - mcp__plugin_serena_serena__delete_memory
  - mcp__plugin_atlassian_atlassian__searchJiraIssuesUsingJql
  - Agent
---

# Phase Closeout

## Context
- Current branch: !`git branch --show-current`
- CLAUDE.md line count: !`wc -l CLAUDE.md`

## Important
This is a TWO-STAGE process. Complete Stage 1 and present all findings. Do NOT proceed to Stage 2 until the user explicitly says "approve".

---

### Stage 1: Prepare (show diffs, do NOT apply)

#### 1.1 Collect Doc Deltas
1. Read Serena memory `session/doc-delta`
2. List all accumulated deltas across sprints in a table:

| Sprint | Type | Description | File | Target Doc |
|--------|------|-------------|------|------------|

3. Map each delta to its target document:
   - New endpoints → `docs/TDD.md` (API Contracts section)
   - New models → `docs/TDD.md` (Data Models section)
   - New services → `docs/TDD.md` (Services section)
   - New user-facing features → `docs/FSD.md` (add FR-XX entry)
   - Product scope changes → `docs/PRD.md`
   - Feature descriptions → `README.md` (Features section)

#### 1.2 Generate Doc Diffs
For EACH target doc file:
1. Read the current file content
2. Identify where the new content should be inserted
3. Generate the exact edit (show old_string → new_string diff)
4. Do NOT apply the edit — just show what would change

Present each diff clearly:

```
docs/TDD.md — API Contracts section
+ POST /api/v1/convergence/forecast
+   Request: { ticker, horizon_days }
+   Response: { forecast_id, predictions[] }
```

#### 1.3 Generate project-plan.md Diff
1. Read `project-plan.md`
2. Find deliverables completed in this phase
3. Show the diff: add checkmarks, session numbers, and JIRA ticket refs

#### 1.4 Run Phase-End Review
1. Read the review prompt template: `review-prompt.md` (in this skill's directory)
2. Dispatch a code review subagent (Agent tool) with those dimensions
3. Collect findings

#### 1.5 Present Summary
Present everything in ONE message:

**Doc Changes:**
- [diff for each file]

**project-plan.md Changes:**
- [diff]

**Phase-End Review Findings:**
- Critical: [list]
- Important: [list]
- Minor: [list]

**Decision:** "Approve all changes? (approve / approve with changes / reject)"

---

### Stage 2: Execute (only after user says "approve")

#### 2.1 Apply Doc Changes
Apply all approved diffs using the Edit tool:
- `docs/TDD.md`
- `docs/FSD.md`
- `docs/PRD.md` (if applicable)
- `README.md` (if applicable)
- `project-plan.md`

#### 2.2 Regenerate PROJECT_INDEX.md
1. Read the current `PROJECT_INDEX.md`
2. Scan all directories for new/changed files
3. Regenerate with current structure
4. Write the updated file

#### 2.3 Update Memories
1. Update Serena `project/state` with:
   - Phase completion status
   - Current test count (run `uv run pytest tests/unit/ -q --tb=no 2>&1 | tail -1`)
   - Resume point for next phase
   - Date
2. Delete Serena `session/doc-delta` memory (deltas have been applied)
3. Update any domain memories that changed

#### 2.4 Handoff
Present: "Phase closeout complete. Changes applied to [N] files. Run `/ship` to commit and push."
