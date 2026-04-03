# Workflow Optimization System — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a self-enforcing workflow optimization system using Claude Code rules, skills, and hooks to reduce per-phase ceremony by ~40%.

**Architecture:** 5 rules files override plugin skill behavior at session start. 2 shell-script hooks enforce stale-state detection and doc-delta reminders. 3 new skills automate sprint closeout, phase closeout, and spec+plan pipeline. The existing /ship command is updated with structured JIRA sections.

**Tech Stack:** Claude Code skills (SKILL.md + YAML frontmatter), Claude Code hooks (bash scripts + JSON stdin/stdout), jq for JSON parsing, settings.json for hook config.

**Spec:** `docs/superpowers/specs/2026-04-03-workflow-optimization-design.md`

---

### Task 1: Create Rule R1 — Workflow Optimization

**Files:**
- Create: `.claude/rules/workflow-optimization.md`

- [ ] **Step 1: Create the rules file**

```markdown
---
description: General workflow optimization rules — spec review rounds, cross-sprint review, JIRA transitions
---

# Workflow Optimization Rules

## Spec Review: One Round, Not Three

When running spec or code review (including via `superpowers:requesting-code-review`):
- Run exactly ONE review round with 5 personas
- Personas are auto-selected by domain:
  - Forecast/signals → quantitative analyst
  - Auth/security → security engineer
  - Frontend/UI → UX engineer
  - Data/models → data engineer
  - API/endpoints → API design expert
- Before starting: "I'll run a 5-persona review. Want to adjust personas or add a round?"

Do NOT run multiple escalating rounds. One round catches 95% of issues.

## No Cross-Sprint Review

Do NOT run a separate review between sprints during implementation.
Instead, at phase end, the phase-end review includes "cross-sprint integration" as an explicit dimension.

After the last sprint in a phase: "Ready for phase-end review. Skip or proceed?"

## JIRA Transition Reminder at PR Creation

When creating a PR (including via `/ship`):
1. Scan the branch name and commit messages for KAN-XXX patterns
2. Present the list of tickets that should transition: "PR ships KAN-384, KAN-385. Transition to Done? (y/n)"
3. Do NOT auto-transition — always wait for explicit approval
```

- [ ] **Step 2: Verify the file loads**

Run: `ls -la .claude/rules/workflow-optimization.md`
Expected: File exists with the content above

- [ ] **Step 3: Commit**

```bash
git add .claude/rules/workflow-optimization.md
git commit -m "feat: add workflow optimization rules (R1)

One-round spec review, no cross-sprint review, JIRA transition
reminder at PR creation."
```

---

### Task 2: Create Rule R2 — Brainstorm Routing

**Files:**
- Create: `.claude/rules/brainstorm-routing.md`

- [ ] **Step 1: Create the rules file**

```markdown
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
```

- [ ] **Step 2: Verify**

Run: `ls -la .claude/rules/brainstorm-routing.md`
Expected: File exists

- [ ] **Step 3: Commit**

```bash
git add .claude/rules/brainstorm-routing.md
git commit -m "feat: add brainstorm routing rule (R2)

Score-based routing: ≤6 skip, 7-10 quick mode, 11+ full Socratic.
Independent of LLM triage score."
```

---

### Task 3: Create Rule R3 — Review Config

**Files:**
- Create: `.claude/rules/review-config.md`

- [ ] **Step 1: Create the rules file**

```markdown
---
description: Review round control — default 1 round, domain-auto-selected personas
---

# Review Configuration

When `superpowers:requesting-code-review` is invoked:

## Round Control
- Default to **1 review round** (not 3)
- Only add a second round if the first round found Critical-severity issues
- Before starting: "Running 1-round, 5-persona review. Add a round?"

## Persona Auto-Selection

Select 5 personas based on the domain of the code being reviewed:

| Code Domain | Persona Pool |
|-------------|-------------|
| Forecast/signals/convergence | Quantitative Analyst, Data Scientist, Performance Engineer, API Designer, Security Engineer |
| Auth/security/JWT | Security Engineer, Cryptography Expert, API Designer, Frontend Engineer, DevOps Engineer |
| Frontend/UI/components | UX Engineer, Accessibility Expert, Performance Engineer, Frontend Architect, Security Engineer |
| Data/models/migrations | Data Engineer, DBA, API Designer, Security Engineer, Performance Engineer |
| API/endpoints/routers | API Designer, Security Engineer, Performance Engineer, Data Engineer, Frontend Consumer |
| Infrastructure/CI/Docker | DevOps Engineer, Security Engineer, Performance Engineer, Reliability Engineer, Platform Engineer |

If the code spans multiple domains, pick the top 5 most relevant personas across domains (no duplicates).
```

- [ ] **Step 2: Verify**

Run: `ls -la .claude/rules/review-config.md`
Expected: File exists

- [ ] **Step 3: Commit**

```bash
git add .claude/rules/review-config.md
git commit -m "feat: add review config rule (R3)

Default 1 round, domain-auto-selected personas."
```

---

### Task 4: Create Rule R4 — Doc-Delta Tracking

**Files:**
- Create: `.claude/rules/doc-delta.md`

- [ ] **Step 1: Create the rules file**

```markdown
---
description: Doc-delta tracking — note documentation changes needed after each sprint for batch application at phase end
paths:
  - "backend/routers/**"
  - "backend/models/**"
  - "backend/services/**"
---

# Doc-Delta Tracking

After completing each sprint or task batch during implementation, note what changed that affects documentation.

## What to Track

| Change Type | Example | Target Doc |
|------------|---------|------------|
| New endpoint | `POST /api/v1/convergence/forecast` | docs/TDD.md |
| New model | `ConvergenceScore` | docs/TDD.md |
| New service | `ConvergenceService` | docs/TDD.md |
| New user-facing feature | Convergence scoring dashboard | docs/FSD.md (add FR-XX) |
| Product scope change | Added forecast intelligence | docs/PRD.md |
| Feature description | New dashboard section | README.md |

## Storage Format

Store deltas in Serena memory key `session/doc-delta` using this format:

```
## Doc Delta Log

### Sprint N
- [endpoint] POST /api/v1/convergence/forecast — backend/routers/convergence.py
- [model] ConvergenceScore — backend/models/convergence.py
- [FR] FR-42: Convergence scoring — needs update in FSD
```

## Workflow

After each sprint completion:
1. Review what was built (scan commits, new files)
2. Note deltas in the format above
3. Append to existing `session/doc-delta` memory (don't overwrite previous sprints)
4. Present: "Sprint done. Doc delta: [summary]. Apply now or accumulate?"

Deltas are accumulated across sprints and applied in batch at phase end via `/phase-closeout`.

Do NOT update TDD/FSD/README/PRD mid-phase — accumulate and batch.
```

- [ ] **Step 2: Verify**

Run: `ls -la .claude/rules/doc-delta.md`
Expected: File exists

- [ ] **Step 3: Commit**

```bash
git add .claude/rules/doc-delta.md
git commit -m "feat: add doc-delta tracking rule (R4)

Accumulate doc changes per sprint, batch apply at phase end.
Stored in Serena session/doc-delta memory."
```

---

### Task 5: Create Rule R5 — Phase-End Review Dimensions

**Files:**
- Create: `.claude/rules/phase-end-review.md`

- [ ] **Step 1: Create the rules file**

```markdown
---
description: Phase-end review dimensions — additional review criteria when running end-of-phase review
---

# Phase-End Review Dimensions

When `superpowers:requesting-code-review` is triggered at phase end (user says "phase-end review" or `/phase-closeout` is invoked), include these ADDITIONAL dimensions alongside standard code quality review:

## Additional Dimensions

1. **Cross-sprint integration consistency**
   - Do components built in different sprints work together correctly?
   - Are there interface mismatches between sprints?
   - Any duplicate or conflicting implementations?

2. **JIRA gap verification**
   - Query the JIRA board for open tickets in the current Epic
   - Are there tickets still open that should be Done?
   - Are there completed features missing tickets?

3. **Security review of new endpoints**
   - Do all new endpoints have proper auth guards?
   - Any IDOR vulnerabilities on detail endpoints?
   - Input validation on all user-facing parameters?

4. **Performance implications**
   - New database queries: are they indexed?
   - Any N+1 query patterns?
   - Cache invalidation for new data paths?

5. **Test coverage of new features**
   - Every new endpoint has auth + happy + error tests?
   - Every new service has unit tests?
   - Any untested edge cases visible from the code?

## Trigger Detection

This rule activates when ANY of these conditions are true:
- User explicitly says "phase-end review" or "end of phase review"
- `/phase-closeout` skill is invoked
- User says "we're done with this phase"

Present: "Phase-end review. Including integration + JIRA gap + security + performance + coverage. Adjust dimensions?"
```

- [ ] **Step 2: Verify**

Run: `ls -la .claude/rules/phase-end-review.md`
Expected: File exists

- [ ] **Step 3: Commit**

```bash
git add .claude/rules/phase-end-review.md
git commit -m "feat: add phase-end review dimensions rule (R5)

5 additional review dimensions: integration, JIRA gap, security,
performance, test coverage."
```

---

### Task 6: Create Hook H1 — Stale State Detector

**Files:**
- Create: `.claude/hooks/stale-state-check.sh`

- [ ] **Step 1: Create hooks directory and script**

```bash
#!/bin/bash
# Stale state detector — SessionStart hook
# Returns additionalContext warning if project/state memory is older than latest commit
# Exit 0 always — this is advisory, never blocks

set -euo pipefail

# Navigate to project root (hook may run from any cwd)
cd "$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0

# Get last commit date
LAST_COMMIT_DATE=$(git log -1 --format=%ai 2>/dev/null | cut -d' ' -f1) || exit 0

# Find Serena state file
STATE_FILE=".serena/memories/project/state.md"

if [ ! -f "$STATE_FILE" ]; then
  echo "{\"additionalContext\": \"No project/state memory found. Create one with current branch, test count, and resume point before starting work.\"}"
  exit 0
fi

# Get state file modification date (macOS stat format)
if [[ "$(uname)" == "Darwin" ]]; then
  STATE_DATE=$(stat -f "%Sm" -t "%Y-%m-%d" "$STATE_FILE" 2>/dev/null) || exit 0
else
  STATE_DATE=$(stat -c "%y" "$STATE_FILE" 2>/dev/null | cut -d' ' -f1) || exit 0
fi

# Compare dates
if [[ "$STATE_DATE" < "$LAST_COMMIT_DATE" ]]; then
  COMMITS_BEHIND=$(git log --oneline --since="$STATE_DATE" 2>/dev/null | wc -l | tr -d ' ')
  echo "{\"additionalContext\": \"project/state memory is ~${COMMITS_BEHIND} commits behind (state: ${STATE_DATE}, latest commit: ${LAST_COMMIT_DATE}). Read and update project/state before proceeding.\"}"
fi

exit 0
```

- [ ] **Step 2: Make executable**

Run: `chmod +x .claude/hooks/stale-state-check.sh`
Expected: No output, exit 0

- [ ] **Step 3: Test the hook manually**

Run: `echo '{"source":"startup"}' | .claude/hooks/stale-state-check.sh`
Expected: Either empty output (state is fresh) or JSON with `additionalContext` warning

- [ ] **Step 4: Test with intentionally stale state**

Run: `touch -t 202501010000 .serena/memories/project/state.md 2>/dev/null && echo '{"source":"startup"}' | .claude/hooks/stale-state-check.sh`
Expected: JSON output like `{"additionalContext": "project/state memory is ~X commits behind..."}`

Restore the file mtime after test:
Run: `touch .serena/memories/project/state.md 2>/dev/null`

- [ ] **Step 5: Commit**

```bash
git add .claude/hooks/stale-state-check.sh
git commit -m "feat: add stale state detector hook (H1)

SessionStart hook that warns when project/state memory is older
than the latest git commit. Cross-platform (macOS + Linux)."
```

---

### Task 7: Create Hook H2 — Doc-Delta Reminder

**Files:**
- Create: `.claude/hooks/doc-delta-reminder.sh`

- [ ] **Step 1: Verify jq is available**

Run: `which jq`
Expected: A path like `/usr/bin/jq` or `/opt/homebrew/bin/jq`

If jq is not installed: `brew install jq`

- [ ] **Step 2: Create the script**

```bash
#!/bin/bash
# Doc-delta reminder — PostToolUse hook
# Fires after Edit/Write on backend API surface files
# Returns additionalContext reminder to note doc delta
# Exit 0 always — reminder only, never blocks

set -euo pipefail

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty') || exit 0

# Skip if no file path (shouldn't happen, but defensive)
[ -z "$FILE_PATH" ] && exit 0

# Only fire for backend API surface directories
# Match: backend/routers/*.py, backend/models/*.py, backend/services/*.py
# Exclude: test files, __init__.py, migration files
if echo "$FILE_PATH" | grep -qE 'backend/(routers|models|services)/[^/]+\.py$' && \
   ! echo "$FILE_PATH" | grep -qE '(test_|__init__|/migrations/)'; then

  # Extract the component type from the path
  COMPONENT=$(echo "$FILE_PATH" | grep -oE '(routers|models|services)')
  FILENAME=$(basename "$FILE_PATH" .py)

  echo "{\"additionalContext\": \"API surface edited: ${COMPONENT}/${FILENAME}.py — note doc delta if new endpoints, models, or services were added (type + description + file path).\"}"
fi

exit 0
```

- [ ] **Step 3: Make executable**

Run: `chmod +x .claude/hooks/doc-delta-reminder.sh`
Expected: No output, exit 0

- [ ] **Step 4: Test positive case (router file)**

Run: `echo '{"tool_input":{"file_path":"/Users/sigmoid/Documents/projects/stockanalysis/stock-signal-platform/backend/routers/convergence.py"}}' | .claude/hooks/doc-delta-reminder.sh`
Expected: `{"additionalContext": "API surface edited: routers/convergence.py — note doc delta if new endpoints, models, or services were added (type + description + file path)."}`

- [ ] **Step 5: Test negative case (test file)**

Run: `echo '{"tool_input":{"file_path":"/Users/sigmoid/Documents/projects/stockanalysis/stock-signal-platform/tests/unit/test_convergence.py"}}' | .claude/hooks/doc-delta-reminder.sh`
Expected: No output (empty)

- [ ] **Step 6: Test negative case (__init__.py)**

Run: `echo '{"tool_input":{"file_path":"/Users/sigmoid/Documents/projects/stockanalysis/stock-signal-platform/backend/routers/__init__.py"}}' | .claude/hooks/doc-delta-reminder.sh`
Expected: No output (empty)

- [ ] **Step 7: Performance test**

Run: `time echo '{"tool_input":{"file_path":"backend/routers/foo.py"}}' | .claude/hooks/doc-delta-reminder.sh`
Expected: Completes in <100ms (real time)

- [ ] **Step 8: Commit**

```bash
git add .claude/hooks/doc-delta-reminder.sh
git commit -m "feat: add doc-delta reminder hook (H2)

PostToolUse hook on Edit|Write — reminds to note doc delta when
backend API surface files are edited. Excludes tests, __init__,
migrations."
```

---

### Task 8: Configure Hooks in settings.json

**Files:**
- Modify: `.claude/settings.json`

- [ ] **Step 1: Update settings.json to add hooks config**

The current file has `permissions` and `env` keys. Add `hooks` as a new top-level key:

```json
{
  "permissions": {
    "allow": [
      "Edit",
      "Bash(uv *)",
      "Bash(pytest *)",
      "Bash(docker compose *)",
      "Bash(git add *)",
      "Bash(git commit *)",
      "Bash(git checkout *)",
      "Bash(git branch *)",
      "Bash(git push *)",
      "Bash(git diff *)",
      "Bash(git log *)",
      "Bash(git status *)",
      "Bash(alembic *)",
      "Bash(cd *)",
      "Bash(cat *)",
      "Bash(ls *)",
      "Bash(mkdir *)",
      "Bash(cp *)",
      "Bash(mv *)",
      "Bash(head *)",
      "Bash(tail *)",
      "Bash(grep *)",
      "Bash(find *)",
      "Bash(wc *)",
      "Bash(npm *)",
      "Bash(npx *)",
      "Bash(node *)",
      "Bash(ruff *)",
      "Bash(mkdocs *)",
      "Bash(gh *)"
    ],
    "deny": [
      "Bash(rm -rf /)",
      "Bash(sudo *)",
      "Bash(pip install *)",
      "Bash(pip *)"
    ]
  },
  "env": {
    "UV_PYTHON": "3.12"
  },
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup|resume",
        "hooks": [
          {
            "type": "command",
            "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/stale-state-check.sh",
            "timeout": 5000,
            "statusMessage": "Checking project state freshness..."
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/doc-delta-reminder.sh",
            "timeout": 2000
          }
        ]
      }
    ]
  }
}
```

- [ ] **Step 2: Validate JSON**

Run: `python3 -c "import json; json.load(open('.claude/settings.json')); print('Valid JSON')" `
Expected: `Valid JSON`

- [ ] **Step 3: Commit**

```bash
git add .claude/settings.json
git commit -m "feat: configure SessionStart and PostToolUse hooks

H1: stale-state-check on startup|resume (5s timeout)
H2: doc-delta-reminder on Edit|Write (2s timeout)"
```

---

### Task 9: Update /ship with JIRA Ships Section

**Files:**
- Modify: `.claude/commands/ship.md`

- [ ] **Step 1: Update the ship command**

Add a new Step 3.5 between "Push" and "Create PR", and update Step 4. The full updated file:

```markdown
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
- Body format:

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
```

- [ ] **Step 2: Verify**

Run: `wc -l .claude/commands/ship.md`
Expected: ~65 lines (increased from ~53)

- [ ] **Step 3: Commit**

```bash
git add .claude/commands/ship.md
git commit -m "feat: update /ship with JIRA Ships section and transition prompt

Adds Step 3.5 (ticket scan) and Step 4.5 (transition prompt).
PR body now includes ## Ships section for reliable JIRA parsing.
Added git log and atlassian tools to allowed-tools."
```

---

### Task 10: Create Skill S1 — /sprint-closeout

**Files:**
- Create: `.claude/skills/sprint-closeout/SKILL.md`

- [ ] **Step 1: Create directory**

Run: `mkdir -p .claude/skills/sprint-closeout`
Expected: Directory created

- [ ] **Step 2: Create SKILL.md**

```markdown
---
name: sprint-closeout
description: End-of-sprint bookkeeping — doc delta, JIRA transitions, state update. Run after completing a sprint's implementation tasks.
disable-model-invocation: true
effort: medium
argument-hint: "[sprint-number]"
allowed-tools:
  - Bash(git log *)
  - Bash(git diff *)
  - Bash(git branch *)
  - mcp__plugin_serena_serena__read_memory
  - mcp__plugin_serena_serena__write_memory
  - mcp__plugin_serena_serena__list_memories
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
   - **Ready to transition:** Currently "In Progress" (status ID 21) or "Ready for Verification" (status ID 8)
   - **Already Done:** Currently "Done" (status ID 31)
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

### Step 4: Update Project State
1. Read current Serena memory `project/state`
2. Update with:
   - Current branch
   - Current date (today)
   - Resume point: "Next: Sprint [N+1]" or "Next: phase closeout" if this was the last sprint
   - Any other relevant state changes
3. Write updated memory
4. Present: "State updated. Run `/ship` to commit and push."
```

- [ ] **Step 3: Verify**

Run: `ls -la .claude/skills/sprint-closeout/SKILL.md`
Expected: File exists

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/sprint-closeout/SKILL.md
git commit -m "feat: add /sprint-closeout skill (S1)

4-step sprint closeout: doc delta review, JIRA scan, transitions
(with approval gate), state update. Replaces 4 manual steps."
```

---

### Task 11: Create Skill S2 — /phase-closeout

**Files:**
- Create: `.claude/skills/phase-closeout/SKILL.md`
- Create: `.claude/skills/phase-closeout/review-prompt.md`

- [ ] **Step 1: Create directory**

Run: `mkdir -p .claude/skills/phase-closeout`
Expected: Directory created

- [ ] **Step 2: Create SKILL.md**

```markdown
---
name: phase-closeout
description: End-of-phase ceremony — apply doc deltas, review, update project-plan and PROJECT_INDEX. Two-stage with human approval gate.
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
📄 docs/TDD.md — API Contracts section
+ POST /api/v1/convergence/forecast
+   Request: { ticker, horizon_days }
+   Response: { forecast_id, predictions[] }
```

#### 1.3 Generate project-plan.md Diff
1. Read `project-plan.md`
2. Find deliverables completed in this phase
3. Show the diff: add ✅ checkmarks, session numbers, and JIRA ticket refs (e.g., `✅ Session 92 (KAN-384)`)

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
```

- [ ] **Step 3: Create review-prompt.md**

```markdown
# Phase-End Review Prompt

You are reviewing the complete output of a multi-sprint implementation phase. Your review covers both standard code quality AND phase-specific integration concerns.

## Review Dimensions

### 1. Code Quality (standard)
- Clean code, proper error handling, no dead code
- Consistent naming, proper typing
- No security vulnerabilities (OWASP top 10)

### 2. Cross-Sprint Integration
- Do components built in different sprints integrate correctly?
- Any interface mismatches (type conflicts, missing fields, wrong signatures)?
- Duplicate implementations of the same concept?
- Circular dependencies introduced across sprints?

### 3. JIRA Gap Verification
- Are there open tickets in the Epic that should be Done?
- Are there implemented features without corresponding tickets?
- Any tickets marked Done that aren't actually shipped?

### 4. Security Review
- All new endpoints have auth guards (`get_current_user` dependency)?
- IDOR checks on detail endpoints (user_id scoping)?
- Input validation on all user-facing parameters?
- No `str(e)` in user-facing error messages?

### 5. Performance
- New queries: are relevant columns indexed?
- Any N+1 patterns (loop of individual queries)?
- Cache invalidation for new data paths?
- Pagination on list endpoints?

### 6. Test Coverage
- Every new endpoint: auth test + happy path + error case?
- Every new service: unit tests covering main logic?
- Edge cases: empty inputs, None values, boundary conditions?
- Regression tests for any bugs fixed?

## Output Format

```
## Phase-End Review

**Reviewed:** [list of files/areas covered]

### Critical (must fix before merge)
- [file:line] [issue] — [why it matters]

### Important (fix before next phase)
- [file:line] [issue] — [why it matters]

### Minor (note for future)
- [file:line] [issue] — [why it matters]

### Positive Observations
- [what was done well]
```

Focus on REAL issues that would cause bugs, security holes, or integration failures. Do not flag style preferences, minor naming quibbles, or "nice to have" improvements.
```

- [ ] **Step 4: Verify both files**

Run: `ls -la .claude/skills/phase-closeout/`
Expected: Both `SKILL.md` and `review-prompt.md` exist

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/phase-closeout/SKILL.md .claude/skills/phase-closeout/review-prompt.md
git commit -m "feat: add /phase-closeout skill (S2) with review prompt

Two-stage phase closeout: generate diffs + review (Stage 1), apply
changes after approval (Stage 2). Runs in forked context.
Includes 6-dimension phase-end review prompt template."
```

---

### Task 12: Create Skill S3 — /spec-plan

**Files:**
- Create: `.claude/skills/spec-plan/SKILL.md`

- [ ] **Step 1: Create directory**

Run: `mkdir -p .claude/skills/spec-plan`
Expected: Directory created

- [ ] **Step 2: Create SKILL.md**

```markdown
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
```

- [ ] **Step 3: Verify**

Run: `ls -la .claude/skills/spec-plan/SKILL.md`
Expected: File exists

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/spec-plan/SKILL.md
git commit -m "feat: add /spec-plan skill (S3)

Orchestrates spec→plan pipeline with one combined review cycle.
Respects brainstorm routing, preserves existing format contracts.
Two separate files, parallel review, standard execution handoff."
```

---

### Task 13: Final Verification

**Files:** None (verification only)

- [ ] **Step 1: Verify all files exist**

Run: `find .claude/rules .claude/hooks .claude/skills -type f | sort`

Expected:
```
.claude/hooks/doc-delta-reminder.sh
.claude/hooks/stale-state-check.sh
.claude/rules/brainstorm-routing.md
.claude/rules/doc-delta.md
.claude/rules/phase-end-review.md
.claude/rules/review-config.md
.claude/rules/workflow-optimization.md
.claude/skills/phase-closeout/SKILL.md
.claude/skills/phase-closeout/review-prompt.md
.claude/skills/spec-plan/SKILL.md
.claude/skills/sprint-closeout/SKILL.md
```

- [ ] **Step 2: Verify hooks are executable**

Run: `ls -la .claude/hooks/*.sh`
Expected: Both scripts have `x` permission

- [ ] **Step 3: Verify settings.json is valid**

Run: `python3 -c "import json; d=json.load(open('.claude/settings.json')); print('hooks' in d and 'SessionStart' in d['hooks'] and 'PostToolUse' in d['hooks'])"`
Expected: `True`

- [ ] **Step 4: Verify CLAUDE.md unchanged**

Run: `wc -l CLAUDE.md`
Expected: `142` (unchanged from before)

- [ ] **Step 5: Verify no plugin files were modified**

Run: `git diff --name-only HEAD~13 | grep -c 'plugins/cache' || echo "0"`
Expected: `0`

- [ ] **Step 6: Count total commits**

Run: `git log --oneline HEAD~13..HEAD | wc -l`
Expected: `12` (one per task 1-12)

- [ ] **Step 7: Update memory file**

Delete the old detailed workflow optimization memory file and replace with a reference to the spec:

Update `project_workflow_optimization_plan.md` to note: "IMPLEMENTED — see docs/superpowers/specs/2026-04-03-workflow-optimization-design.md and docs/superpowers/plans/2026-04-03-workflow-optimization.md"
