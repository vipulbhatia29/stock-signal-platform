---
name: closing-out-sprint
description: Performs end-of-sprint bookkeeping — records doc deltas, transitions JIRA tickets, updates Serena state. Use when user says "sprint done", "close sprint", "end of sprint", "sprint closeout", or invokes /sprint-closeout.
disable-model-invocation: true
effort: medium
argument-hint: "[sprint-number]"
allowed-tools:
  - Bash(git log *)
  - Bash(git diff *)
  - Bash(git branch *)
  - mcp__serena__read_memory
  - mcp__serena__write_memory
  - mcp__serena__list_memories
  - mcp__plugin_atlassian_atlassian__searchJiraIssuesUsingJql
  - mcp__plugin_atlassian_atlassian__transitionJiraIssue
  - mcp__plugin_atlassian_atlassian__getJiraIssue
---

# Sprint Closeout — Sprint $ARGUMENTS

## Context
- Current branch: !`git branch --show-current`
- Recent commits: !`git log --oneline -10`

## Your Task

Execute these steps IN ORDER. Present a summary after each step and wait for approval before executing transitions.

Copy this checklist and track progress:

```
Sprint Closeout Progress:
- [ ] Step 1: Doc delta review
- [ ] Step 2: JIRA ticket scan — WAIT for approval
- [ ] Step 3: Execute transitions
- [ ] Step 4: Verify transitions succeeded
- [ ] Step 5: Update project state
```

### Step 1: Doc Delta Review
1. Read Serena memory `session/doc-delta`
2. If it exists, present the accumulated deltas in a table:

| Type | Description | File |
|------|-------------|------|

3. If it doesn't exist, scan recent commits for new files in `backend/routers/`, `backend/models/`, `backend/services/` using `git diff --name-only --diff-filter=A develop..HEAD` and note them as deltas
4. Present: "Doc deltas for this sprint: [table]. These will be applied at phase closeout."

### Step 2: JIRA Ticket Scan
1. Extract KAN-XXX references from:
   - Branch name: `git branch --show-current`
   - Recent commits: `git log --oneline -20`
2. For each unique ticket, query JIRA for current status using `getJiraIssue`
3. Classify tickets:
   - **Ready to transition:** Currently "In Progress" or "Ready for Verification"
   - **Already Done:** Currently "Done"
   - **Blocked/Other:** Any other status — flag for manual review
4. Present in a table:

| Ticket | Current Status | Action |
|--------|---------------|--------|
| KAN-384 | In Progress | → Done |
| KAN-385 | Done | No action |

5. Ask: "Approve transitions? (y/n)"
6. **WAIT for user approval. Do NOT transition anything without explicit "yes".**

### Step 3: Execute Transitions (only after approval)
1. For each approved ticket, call `transitionJiraIssue` with transition ID `31` (Done)
2. Report: "Transitioned: [list]. Failed: [list]."

### Step 4: Verify Transitions
1. For each transitioned ticket, query JIRA again using `getJiraIssue`
2. Confirm status is now "Done"
3. If any failed: report which ones and retry once
4. Present: "Verified: [list of confirmed Done]. Issues: [list of failures]."

### Step 5: Update Project State
1. Read current Serena memory `project/state`
2. Update with:
   - Current branch
   - Current date (today)
   - Resume point: "Next: Sprint [N+1]" or "Next: phase closeout" if this was the last sprint
   - Any other relevant state changes
3. Write updated memory
4. Present: "State updated. Run `/ship` to commit and push."
