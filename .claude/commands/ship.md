---
allowed-tools: Bash(git add:*), Bash(git status:*), Bash(git push:*), Bash(git commit:*), Bash(gh pr create:*), Bash(gh pr view:*), Bash(git log:*), Bash(git branch:*), mcp__plugin_serena_serena__list_memories, mcp__plugin_serena_serena__read_memory, mcp__plugin_serena_serena__write_memory, mcp__plugin_serena_serena__delete_memory, mcp__plugin_atlassian_atlassian__getJiraIssue, mcp__plugin_atlassian_atlassian__transitionJiraIssue
description: Promote session memories, commit, push, and open a PR
---

## Context

- Current git status: !`git status`
- Current git diff: !`git diff HEAD`
- Current branch: !`git branch --show-current`

## Your task

Execute ALL steps in a single message with multiple tool calls:

### Step 0 — Session memory scan and promotion

1. List all memories with key prefix `session/` using `list_memories`.
2. If any session memories exist:
   a. Read `serena/memory-map` to understand the taxonomy.
   b. For each session memory, classify it: which project/ or global/ key does it map to?
   c. Present a one-line summary table: `[session/key] -> [target/key] (PROMOTE | DISCARD)`.
   d. Wait for human approval before writing.
   e. On approval: write each PROMOTE item to its target key using `write_memory`.
   f. For GLOBAL-CANDIDATE items (frontmatter flag): write to `global/<category>/<name>` key.
   g. Delete promoted session memories using `delete_memory` (NOT shell rm).
3. If no session memories exist, skip to Step 1.

### Step 1 — Stage and commit

Run `git add` on relevant files (code + any promoted Serena memory files in `.serena/memories/`).
Do NOT use `git add -A` — stage specific files only.

### Step 2 — Commit

Create a single commit with an appropriate conventional commit message covering all staged changes.
Memory promotions and code changes go in the same commit.

### Step 3 — Push

Push the branch to origin with `-u` flag if first push.

### Step 3.5 — Scan for JIRA tickets

1. Extract KAN-XXX patterns from:
   - Branch name: `git branch --show-current`
   - All commit messages: `git log develop..HEAD --oneline`
2. Deduplicate the ticket list
3. If tickets found, store them for the PR body `## Ships` section

### Step 4 — Create PR

Create a PR using `gh pr create` with:
- Title: short (under 70 chars), conventional commit style
- Body format (use HEREDOC):

```
## Summary
<1-3 bullet points>

## Ships
- KAN-XXX
- KAN-YYY

## Test plan
- [ ] <verification steps>
```

- Base branch: `develop` (not `main`)
- If no KAN-XXX tickets found, omit the `## Ships` section entirely

### Step 4.5 — JIRA transition prompt

If tickets were found in Step 3.5:
1. Present: "PR ships [ticket list]. Transition to Done? (y/n)"
2. WAIT for user approval
3. On approval: transition each ticket to Done (transition ID: 31) using `transitionJiraIssue`
4. Report results: "Transitioned: [list]. Failed: [list]."

### Step 5 — Confirm

Report the PR URL. The session is complete.
