# Workflow Optimization System — Design Spec

## Problem Statement

Over 90 sessions building the stock-signal-platform, we've accumulated manual ceremony that costs tokens and introduces human error: multi-round spec reviews, manual doc updates after each phase, manual JIRA transitions, cross-sprint reviews that add little value, and brainstorming for trivially simple tasks. These processes worked when the project was smaller but now create drag.

## Goal

Reduce per-phase token cost and manual steps by ~40% while maintaining (or improving) quality. Every optimization must be self-enforcing — rules that depend on "remember to do X" decay within 10 sessions.

## Design Decisions

### DD-1: Override plugin skill behavior via `.claude/rules/`, not by modifying plugin files

Plugin skills live in `~/.claude/plugins/cache/` and get overwritten on updates. The official docs confirm: "User's explicit instructions (CLAUDE.md) — highest priority" over skill content. We override specific behaviors by adding `.claude/rules/` files that take precedence when the skill is active.

**Rejected alternative:** Forking the superpowers plugin. Too high maintenance — every plugin update requires manual merge.

### DD-2: New skills go in `.claude/skills/`, not `.claude/commands/`

The docs confirm skills and commands are equivalent, but skills support additional features: `context: fork`, `disable-model-invocation`, `effort:`, scoped hooks, and supporting files. All new workflow tools will be skills.

### DD-3: Enforcement via hooks, not CLAUDE.md rules

For checks that must happen every time (stale state detection, doc-delta reminders), use Claude Code hooks that inject `additionalContext`. CLAUDE.md rules are advisory; hooks are deterministic.

### DD-4: CLAUDE.md stays lean — behavioral overrides go to `.claude/rules/`

CLAUDE.md is at 142 lines (limit: 200). All new behavioral rules go to `.claude/rules/` files, which load identically at session start but keep the main file focused.

---

## Architecture

### Layer 1: Rules (`.claude/rules/`) — Always-loaded behavioral overrides

These files load at session start and override plugin skill behavior when active.

#### R1: `workflow-optimization.md` — General workflow rules

Contents:
- **One spec review round, not three.** 5-persona review, one round. Personas chosen per domain (forecast → quant expert, auth → security expert, frontend → UX expert). Override: "I'll run a 5-persona review. Want to adjust personas or add a round?"
- **No cross-sprint review.** Phase-end review adds "cross-sprint integration" as an explicit review dimension instead. Override: "Ready for phase-end review. Skip or proceed?"
- **JIRA transition reminder in PR creation.** When creating a PR, list the JIRA tickets that should transition. Don't auto-transition — present for approval. Override: "PR merges KAN-384, KAN-385. Transition to Done? (y/n)"

#### R2: `brainstorm-routing.md` — Complexity-based brainstorm routing

Overrides `superpowers:brainstorming` behavior. Before starting brainstorming, score the task on three dimensions:
- `design_surface` (how many architectural options exist, 1-5)
- `reversibility` (how hard to undo if wrong, 1-5)
- `cross_cutting` (how many modules affected, 1-5)

Routing:
- Score ≤6: skip brainstorming entirely (present "skipping brainstorm — low design complexity" and proceed directly to spec writing or implementation)
- Score 7-10: quick mode — skip Socratic questions, go straight to "3 options, I recommend X because Y, risks are Z"
- Score 11+: full Socratic brainstorming as normal

Also: if the conversation has already completed brainstorming organically (explored context, proposed approaches, converged on a design), skip re-invoking the skill and proceed to spec writing.

Override: "This scores 7/15 — suggesting quick brainstorm. Deep dive instead?"

Note: these dimensions are independent of the LLM triage score (context_span + convention_density + ambiguity), which measures implementation complexity, not design complexity.

#### R3: `review-config.md` — Review round control

Overrides `superpowers:requesting-code-review` behavior:
- Default to 1 review round (not 3)
- Personas auto-selected by domain: forecast → quantitative analyst, auth → security engineer, frontend → UX engineer, data → data engineer, API → API design expert
- Override: "Running 1-round, 5-persona review. Add a round?"

#### R4: `doc-delta.md` — Doc-delta tracking rule

After completing each sprint or task batch during implementation:
1. Note what changed: new endpoints, new models, new services, new/changed FRs
2. Store the delta in Serena memory key `session/doc-delta` with format:
   ```
   [sprint N] [type: endpoint|model|service|FR] [description] [file path]
   ```
3. Override: "Sprint done. Doc delta: [summary]. Apply now or accumulate?"

At phase end, the accumulated deltas are applied to TDD/FSD/README/PRD in one batch (10 minutes, not a full session).

#### R5: `phase-end-review.md` — Phase-end review dimensions

When `superpowers:requesting-code-review` is triggered at phase end (explicitly by user saying "phase-end review" or by `/phase-closeout`), include these additional review dimensions alongside standard code quality:
- Cross-sprint integration consistency
- JIRA gap verification (any tickets still open that should be done?)
- Security review of new endpoints
- Performance implications of new queries
- Test coverage of new features

Override: "Phase-end review. Including integration + JIRA gap + security. Adjust dimensions?"

---

### Layer 2: Skills (`.claude/skills/`) — On-demand workflow tools

Skills are markdown files with YAML frontmatter. They load on demand (not every session), support `$ARGUMENTS` substitution, and can run in isolated context with `context: fork`. All three new skills use `disable-model-invocation: true` because they have side effects.

**Key patterns from official docs applied:**
- `disable-model-invocation: true` — prevents Claude from auto-triggering skills with side effects
- `argument-hint` — shown during autocomplete to guide usage
- `effort` — controls reasoning depth (medium for sprint ops, high for phase-end analysis)
- `context: fork` — runs skill in isolated subagent context (for S2 which reads many files)
- `allowed-tools` — restricts tool access where appropriate
- Dynamic context with `` !`command` `` — preprocesses shell commands before Claude sees the content
- Supporting files referenced from SKILL.md — keep main file focused

#### S1: `/sprint-closeout`

**Purpose:** Replace 4 manual end-of-sprint steps with one invocation.

**Full SKILL.md content:**
````yaml
---
name: sprint-closeout
description: End-of-sprint bookkeeping — doc delta, JIRA transitions, state update. Run after completing a sprint's implementation tasks.
disable-model-invocation: true
effort: medium
argument-hint: "[sprint-number]"
allowed-tools:
  - Bash(git log *)
  - Bash(git diff *)
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
2. If it exists, present the accumulated deltas in a table
3. If it doesn't exist, scan recent commits for new files in `backend/routers/`, `backend/models/`, `backend/services/` and note them as deltas
4. Present: "Doc deltas for this sprint: [table]. These will be applied at phase closeout."

### Step 2: JIRA Ticket Scan
1. Extract KAN-XXX references from recent commits and branch name
2. For each ticket, query JIRA for current status using `getJiraIssue`
3. Identify tickets that should transition to Done (currently In Progress or Ready for Verification)
4. Present: "Tickets to transition to Done: [list]. Tickets already Done: [list]. Approve transitions? (y/n)"
5. WAIT for user approval before transitioning anything

### Step 3: Execute Transitions (only after approval)
1. Transition approved tickets to Done (transition ID: 31)
2. Report results: "Transitioned: [list]. Failed: [list]."

### Step 4: Update Project State
1. Read current `project/state` Serena memory
2. Update with: current branch, resume point (next sprint/task), date
3. Write updated state
4. Present: "State updated. Run `/ship` to commit and push."
````

**Does NOT:** Apply doc changes to TDD/FSD — that's accumulated for phase-closeout. Does NOT commit or push — that's `/ship`.

**Relationship to `/ship`:** Sprint-closeout does pre-commit bookkeeping. `/ship` does git+PR ceremony. Flow: `/sprint-closeout` → (approval) → `/ship`.

#### S2: `/phase-closeout`

**Purpose:** Replace 6 manual end-of-phase steps with one invocation.

**Full SKILL.md content:**
````yaml
---
name: phase-closeout
description: End-of-phase ceremony — apply doc deltas, review, update project-plan and PROJECT_INDEX. Two-stage process with human approval gate.
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

## Your Task

This is a TWO-STAGE process. Complete Stage 1 and present findings. Do NOT proceed to Stage 2 until the user explicitly approves.

### Stage 1: Prepare (reversible — show diffs, don't apply)

#### 1.1 Collect Doc Deltas
Read Serena memory `session/doc-delta`. List all accumulated deltas across sprints in a table:

| Sprint | Type | Description | File | Target Doc |
|--------|------|-------------|------|------------|

Map each delta to which doc needs updating:
- New endpoints → `docs/TDD.md` (API section)
- New models → `docs/TDD.md` (data model section)
- New services → `docs/TDD.md` (services section)
- New user-facing features → `docs/FSD.md` (add FR-XX)
- Product scope changes → `docs/PRD.md`
- Feature descriptions → `README.md`

#### 1.2 Generate Doc Diffs
For each target doc:
1. Read the current file
2. Generate the specific edit needed (show as diff with before/after)
3. Do NOT apply the edit yet

#### 1.3 Update project-plan.md
1. Read `project-plan.md`
2. Find deliverables completed in this phase
3. Show diff: add checkmarks, session numbers, and JIRA ticket refs

#### 1.4 Run Phase-End Review
Dispatch a code review subagent (Agent tool) with these dimensions:
- Standard code quality
- Cross-sprint integration consistency
- JIRA gap verification (query board for any open tickets that should be done)
- Security review of new endpoints
- Test coverage of new features

Reference the review prompt template: `review-prompt.md`

#### 1.5 Present Summary
Present all diffs + review findings in one message:
- Doc change diffs (per file)
- project-plan.md diff
- Review findings (Critical/Important/Minor)
- Ask: "Approve these changes? (approve all / approve with changes / reject)"

### Stage 2: Execute (only after user says "approve")

#### 2.1 Apply Doc Changes
Apply all approved diffs to TDD/FSD/README/PRD/project-plan.md

#### 2.2 Regenerate PROJECT_INDEX.md
Read all files in the repo and regenerate `PROJECT_INDEX.md` with current structure.

#### 2.3 Update Memories
- Update Serena `project/state` with phase completion, test count, resume point
- Update any domain memories that changed (e.g., new architecture patterns)
- Delete `session/doc-delta` memory (deltas have been applied)

#### 2.4 Handoff
Present: "Phase closeout complete. Run `/ship` to commit and push."
````

**Supporting file:** `.claude/skills/phase-closeout/review-prompt.md` (T2) — contains the full phase-end review prompt template with persona definitions and review dimensions.

**Uses `context: fork`** because it reads 6+ large files (TDD, FSD, PRD, README, project-plan, PROJECT_INDEX). Runs in isolated subagent context, returns summary to main conversation. This prevents bloating the main context with all those file reads.

#### S3: `/spec-plan`

**Purpose:** Streamline the spec→plan→review pipeline into fewer round-trips.

**Full SKILL.md content:**
````yaml
---
name: spec-plan
description: Generate spec and plan with one review cycle. Invokes brainstorming (if needed) and writing-plans in sequence, then runs combined spec+plan review.
disable-model-invocation: true
argument-hint: "[feature-topic]"
---

# Spec + Plan Pipeline — $ARGUMENTS

## Your Task

Orchestrate the full spec→plan pipeline for **$ARGUMENTS** with minimal round-trips.

### Step 1: Check Brainstorming Status
Has brainstorming already been completed for this topic in the current conversation?
- If YES (design was discussed and approved): skip to Step 2
- If NO: invoke `superpowers:brainstorming` skill (respecting brainstorm-routing rules — check design complexity score first)

### Step 2: Write Spec
If brainstorming produced a spec, it's already written. If not, write it now to:
`docs/superpowers/specs/YYYY-MM-DD-$ARGUMENTS-design.md`

### Step 3: Write Plan
Immediately invoke `superpowers:writing-plans` skill. Do NOT wait for user review of the spec — the combined review in Step 4 covers both.

The plan MUST use the exact format expected by `superpowers:subagent-driven-development`:
- Plan header: `> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development...`
- Task structure: `### Task N:` with `**Files:**` and `- [ ]` checkbox steps
- Complete code blocks, exact file paths, exact commands with expected output

Save to: `docs/superpowers/plans/YYYY-MM-DD-$ARGUMENTS.md`

### Step 4: Combined Review
Dispatch TWO review subagents in parallel:
1. **Spec reviewer** — using the spec-document-reviewer prompt template from superpowers
2. **Plan reviewer** — using the plan-document-reviewer prompt template from superpowers

Present combined findings. Fix any issues inline.

### Step 5: Offer Execution Choice
Present the standard execution choice from writing-plans:

"Plan complete. Two execution options:
1. **Subagent-Driven** (recommended) — fresh subagent per task, two-stage review
2. **Inline Execution** — batch execution with checkpoints

Which approach?"

## Key Constraints
- Spec and plan are TWO SEPARATE FILES — do not merge formats
- Plan must be consumable by `superpowers:executing-plans` and `superpowers:subagent-driven-development` without modification
- One review cycle covers both docs — this is the token savings
- If brainstorming was already done in conversation, do NOT re-invoke it
````

**Key design choice:** The spec and plan are written as **two separate files**, preserving the existing format contracts. The optimization is eliminating the human round-trips between spec-review → plan-write → plan-review. Instead: write both, review both in parallel, fix, execute.

---

### Layer 3: Hooks (`.claude/settings.json`) — Automated enforcement

Hooks are deterministic scripts that run outside Claude's conversation. They fire on lifecycle events and can inject context, block actions, or modify tool inputs. Unlike CLAUDE.md rules, hooks **cannot be forgotten or ignored** — they are the enforcement layer.

#### settings.json hook configuration

Add this to `.claude/settings.json` (merged with existing `permissions` and `env` keys):

```json
{
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

**Key patterns from official docs applied:**
- `$CLAUDE_PROJECT_DIR` ensures scripts work regardless of working directory (e.g., when Claude `cd`s into a subdirectory)
- `timeout` in milliseconds — prevents hooks from blocking the session
- `statusMessage` shown as spinner text during execution (SessionStart only — gives user feedback)
- `matcher` uses regex — `startup|resume` fires on fresh sessions and resumed ones, `Edit|Write` fires on both file operations
- Hook output is capped at 10,000 characters — our scripts return < 200 chars

#### H1: Stale state detector — SessionStart hook

**Trigger:** Every session start (matcher: `startup|resume`). Does NOT fire on `clear` or `compact` — stale state check is only needed at session boundaries.

**Script:** `.claude/hooks/stale-state-check.sh`

**Input (JSON on stdin):**
```json
{
  "session_id": "abc123",
  "cwd": "/path/to/project",
  "hook_event_name": "SessionStart",
  "source": "startup"
}
```

**Full script logic:**
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

**Key design choices:**
- `set -euo pipefail` for safety, but every failure path exits 0 (non-blocking)
- Cross-platform: handles both macOS (`stat -f`) and Linux (`stat -c`) date formats
- Uses `git rev-parse --show-toplevel` to find project root regardless of cwd
- Counts commits behind for actionable specificity ("5 commits behind" vs "state is old")

#### H2: Doc-delta reminder — PostToolUse hook on Edit|Write

**Trigger:** After any Edit or Write tool completes successfully

**Matcher:** `Edit|Write` (regex — matches both tool names)

**Script:** `.claude/hooks/doc-delta-reminder.sh`

**Input (JSON on stdin):**
```json
{
  "session_id": "abc123",
  "cwd": "/path/to/project",
  "hook_event_name": "PostToolUse",
  "tool_name": "Edit",
  "tool_input": {
    "file_path": "/abs/path/to/backend/routers/convergence.py",
    "old_string": "...",
    "new_string": "..."
  },
  "tool_response": "...",
  "tool_use_id": "toolu_xxx"
}
```

**Full script logic:**
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

**Key design choices:**
- Uses `jq` to parse JSON stdin (standard for Claude Code hooks)
- Excludes test files, `__init__.py`, and migrations — reduces false positives
- Includes the specific component type and filename in the reminder for actionability
- Regex excludes nested directories (e.g., `backend/routers/utils/helper.py` won't match)
- Performance: pure bash + grep + jq, completes in <50ms

---

### Layer 4: `/ship` update — Structured JIRA section

Update the existing `.claude/commands/ship.md` to add a `## Ships` section to PR bodies and a JIRA transition prompt.

**Changes to Step 4 (Create PR):**

Before creating the PR:
1. Extract KAN-XXX references from:
   - Branch name (e.g., `feat/KAN-384-convergence-scoring`)
   - All commit messages in the PR: `git log develop..HEAD --oneline`
2. Deduplicate the list
3. Add a `## Ships` section to the PR body template:
   ```markdown
   ## Ships
   - KAN-384
   - KAN-385
   ```
4. After PR creation, present: "PR ships KAN-384, KAN-385. Transition to Done? (y/n)"
5. On approval, transition each ticket to Done (transition ID: 31)

This structured `## Ships` section is the prerequisite for future E1 (JIRA auto-transition GitHub Action) — regex parsing of `## Ships` is reliable, unlike scanning the full PR body.

**Only scan `## Ships` section** for JIRA automation. References elsewhere in the PR body ("see KAN-384 for context", "blocked by KAN-390") are NOT shipped tickets.

---

### Layer 5: Templates (supporting files for skills)

#### T1: Doc-delta scratch format

Used by R4 and S1. Stored in Serena memory `session/doc-delta`.

```markdown
## Doc Delta Log

### Sprint 1
- [endpoint] POST /api/v1/convergence/forecast — backend/routers/convergence.py
- [model] ConvergenceScore — backend/models/convergence.py
- [FR] FR-42: Convergence scoring — needs update in FSD

### Sprint 2
- [endpoint] GET /api/v1/convergence/history — backend/routers/convergence.py
- [service] ConvergenceService.get_history() — backend/services/convergence.py
```

#### T2: Phase-end review prompt template

Used by R5 and S2. Stored as supporting file in `.claude/skills/phase-closeout/review-prompt.md`.

Defines:
- 5 persona slots (auto-selected by domain)
- 6 review dimensions: code quality, cross-sprint integration, JIRA gap, security, performance, test coverage
- Output format: findings by severity (Critical/Important/Minor) with file references

---

## Deferred Items

These are acknowledged but not built in this phase:

| Item | Reason for Deferral |
|------|-------------------|
| D2: JIRA drift detector hook | Requires JIRA API call in a hook — fragile. JIRA drift check is handled inside S1 (/sprint-closeout) instead. |
| E1: JIRA auto-transition GitHub Action | Needs JIRA CI secrets (JIRA_API_TOKEN, JIRA_USER_EMAIL, JIRA_CLOUD_ID) — not configured yet. |
| E2: Stale memory CI check | Trivial but low priority — advisory PR comment if project/state not modified. |

---

## Dependency Graph

```
T1 (doc-delta format)     → used by R4 + S1
T2 (review prompt)        → used by R5 + S2

R1-R5 (rules)             → no deps, ship first
H1 (stale state hook)     → no deps, ship independently
H2 (doc-delta hook)       → no deps, ship independently

S1 (/sprint-closeout)     → uses R4, T1
S2 (/phase-closeout)      → uses R5, T2, context: fork
S3 (/spec-plan)           → uses R2, existing superpowers skills

/ship update              → no deps, update existing file
```

## Build Order

| Phase | Items | Estimated Effort |
|-------|-------|-----------------|
| 1 | R1-R5 (5 rules files) | 15 min |
| 2 | H1 + H2 (2 hooks + settings.json config) | 20 min |
| 3 | /ship update (add ## Ships section) | 5 min |
| 4 | S1 (/sprint-closeout) + T1 (doc-delta format) | 30 min |
| 5 | S2 (/phase-closeout) + T2 (review prompt) | 30 min |
| 6 | S3 (/spec-plan) | 20 min |

## File Manifest

### New files to create:
```
.claude/rules/workflow-optimization.md          # R1
.claude/rules/brainstorm-routing.md             # R2
.claude/rules/review-config.md                  # R3
.claude/rules/doc-delta.md                      # R4
.claude/rules/phase-end-review.md               # R5
.claude/hooks/stale-state-check.sh              # H1
.claude/hooks/doc-delta-reminder.sh             # H2
.claude/skills/sprint-closeout/SKILL.md         # S1
.claude/skills/phase-closeout/SKILL.md          # S2
.claude/skills/phase-closeout/review-prompt.md  # T2
.claude/skills/spec-plan/SKILL.md               # S3
```

### Files to modify:
```
.claude/settings.json                           # Add hooks config
.claude/commands/ship.md                        # Add ## Ships section
```

### Files NOT modified:
```
CLAUDE.md                                       # Stays at 142 lines — no changes
~/.claude/plugins/cache/.../superpowers/...     # Never touch plugin files
```

## Success Criteria

1. All 5 rules files load at session start (verify with `/memory`)
2. H1 fires on session start and warns when state is stale (test with intentionally outdated state file)
3. H2 fires after editing a file in `backend/routers/` but NOT after editing a test file
4. `/sprint-closeout` presents doc deltas + JIRA transitions and waits for approval
5. `/phase-closeout` generates doc diffs in isolated context and presents for review
6. `/spec-plan` produces spec + plan in one session with one review cycle
7. `/ship` includes `## Ships` section with KAN-XXX tickets in PR body
8. No plugin files were modified
9. CLAUDE.md line count unchanged (142 lines)

## Testing Plan

Each component should be tested in isolation after creation, then integrated.

### Phase 1 Tests: Rules (R1-R5)
- Start a new session with `/clear`
- Ask Claude "What skills are available?" — verify all 5 rules load (check with `/memory`)
- Invoke `superpowers:brainstorming` on a trivially simple task — verify R2 routes to "skip" mode
- Invoke `superpowers:requesting-code-review` — verify R3 defaults to 1 round
- Say "phase-end review" — verify R5 dimensions are included

### Phase 2 Tests: Hooks (H1, H2)
- **H1 test:** Manually backdate `.serena/memories/project/state.md` mtime with `touch -t`, then start a new session. Verify warning appears in context.
- **H1 negative test:** Update state file, then start session. Verify no warning.
- **H2 test:** Edit a file in `backend/routers/` — verify reminder appears.
- **H2 negative test:** Edit a file in `tests/` — verify NO reminder.
- **H2 negative test:** Edit `backend/routers/__init__.py` — verify NO reminder (excluded).
- **Performance test:** Time the hook execution: `time echo '{"tool_input":{"file_path":"backend/routers/foo.py"}}' | .claude/hooks/doc-delta-reminder.sh` — must be <100ms.

### Phase 3 Tests: /ship update
- Create a test branch `feat/KAN-999-test`, make a commit mentioning KAN-998
- Run `/ship` — verify PR body contains `## Ships` section with both KAN-999 and KAN-998
- Verify JIRA transition prompt appears

### Phase 4 Tests: /sprint-closeout
- Write a test doc delta to Serena memory `session/doc-delta`
- Run `/sprint-closeout 1`
- Verify: deltas presented, JIRA tickets scanned, state update proposed
- Verify: nothing executes until user approves

### Phase 5 Tests: /phase-closeout
- Accumulate test deltas across multiple sprints in `session/doc-delta`
- Run `/phase-closeout`
- Verify: runs in forked context (check context isolation)
- Verify: diffs generated but NOT applied in Stage 1
- Verify: blocks for user approval between stages

### Phase 6 Tests: /spec-plan
- Run `/spec-plan test-feature`
- Verify: brainstorming routing applies (R2 score check)
- Verify: spec and plan written as separate files
- Verify: combined review dispatches two reviewers in parallel
- Verify: execution choice offered at end

## Cross-Project Portability

This workflow system is designed to be reusable across future projects. Here's what's portable vs project-specific:

### Portable (copy to any project)
- `.claude/rules/workflow-optimization.md` (R1) — universal workflow rules
- `.claude/rules/brainstorm-routing.md` (R2) — complexity routing is domain-independent
- `.claude/rules/review-config.md` (R3) — review round control
- `.claude/skills/spec-plan/SKILL.md` (S3) — spec+plan pipeline
- `.claude/hooks/stale-state-check.sh` (H1) — works with any Serena project
- Hook configuration pattern in `settings.json`

### Project-specific (adapt per project)
- `.claude/rules/doc-delta.md` (R4) — file path patterns are project-specific (`backend/routers/` etc.)
- `.claude/rules/phase-end-review.md` (R5) — review dimensions depend on project type
- `.claude/hooks/doc-delta-reminder.sh` (H2) — path regex matches project structure
- `.claude/skills/sprint-closeout/SKILL.md` (S1) — JIRA project key, transition IDs
- `.claude/skills/phase-closeout/SKILL.md` (S2) — doc file paths (TDD, FSD, etc.)
- `/ship` updates — JIRA ticket pattern (KAN-XXX)

### Future: Global skills
Once validated on this project, portable items can be promoted to `~/.claude/skills/` (user-level) so they're available across all projects without copying.

## Risks

1. **Rule override effectiveness** — `.claude/rules/` files override plugin skill behavior in theory (CLAUDE.md > skills), but untested at this scale. Mitigation: test each rule against its target skill in isolation before building skills.
2. **Hook performance** — H2 fires on every Edit/Write. If the script is slow, it'll delay every edit. Mitigation: script must complete in <100ms (it's just a path regex check). Test with `time` command.
3. **context: fork isolation** — S2 runs in isolated context. It can't access the main conversation history. Mitigation: S2's skill content must include all the instructions it needs, including dynamic context injection via `` !`command` `` syntax.
4. **Doc-delta persistence** — Stored in Serena memory `session/doc-delta`. If Serena server restarts or memory is cleared, deltas are lost. Mitigation: deltas are also visible in commit history; worst case, regenerate from git log.
5. **jq dependency** — H2 uses `jq` to parse JSON stdin. If `jq` is not installed, the hook silently exits 0 (non-blocking). Verify `jq` is available: `which jq`.
6. **Skill description truncation** — Docs say skill descriptions are truncated at 250 characters in the listing. All our descriptions are under 250 chars. If they get longer, Claude may not match them correctly.
