---
allowed-tools: Bash(git add:*), Bash(git status:*), Bash(git push:*), Bash(git commit:*), Bash(gh pr create:*), Bash(gh pr view:*), Bash(git log:*), Bash(git diff:*), Bash(git branch:*), Bash(ruff:*), Bash(uv run pytest:*), Read, Grep, Glob, Agent, mcp__plugin_serena_serena__list_memories, mcp__plugin_serena_serena__read_memory, mcp__plugin_serena_serena__write_memory, mcp__plugin_serena_serena__delete_memory, mcp__plugin_atlassian_atlassian__getJiraIssue, mcp__plugin_atlassian_atlassian__transitionJiraIssue
description: Review, promote session memories, commit, push, and open a PR
---

## Context

- Current git status: !`git status`
- Current git diff (stat): !`git diff --stat develop..HEAD 2>/dev/null || git diff --stat HEAD`
- Current branch: !`git branch --show-current`
- Files changed: !`git diff --name-only develop..HEAD 2>/dev/null || git diff --name-only HEAD`

## Your task

Execute steps in order. Steps with WAIT gates require human approval before proceeding.

### Step 0 — Code review gate

Score the changes using the `reviewing-code` skill (`.claude/skills/reviewing-code/SKILL.md`):

1. **Score the diff** (develop..HEAD or staged changes):
   - `lines_changed`: <30 → 1, 30-150 → 3, 150+ → 5
   - `risk_surface`: internal/logging → 1, behavior change → 3, new API/auth/schema → 5
   - `cross_module`: 1-2 files same module → 1, 3-5 files 2 modules → 3, 6+ files 3+ modules → 5

2. **Route by score:**
   - **Score 3-6 (Skip):** Present "Review score X/15 — skipping formal review. Lint/tests/Semgrep green." Proceed to Step 0.5.
   - **Score 7-10 (Quick):** Read the diff. Review inline from 1-2 auto-selected personas (see `reviewing-code/personas.md`). Present findings. WAIT for approval if any HIGH+ findings.
   - **Score 11-15 (Full):** Dispatch review agent(s) with auto-selected personas (3-5 per `personas.md`). Present findings. WAIT for approval. Fix HIGH+ findings before proceeding.

3. **Present review summary:**
   ```
   Review score: X/15 (lines: X, risk: X, cross-module: X)
   Depth: [Skip / Quick / Full]
   Personas: [list or "none"]
   Findings: [count by severity or "none"]
   ```

4. If HIGH+ findings exist: fix them, re-run affected tests, then proceed.

### Step 0.5 — Session memory scan and promotion

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
