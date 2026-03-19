---
scope: project
category: conventions
updated_by: session-34
---

# JIRA SDLC Workflow — Mandatory Process

This document defines the **mandatory workflow** for all feature development in the Stock Signal Platform.
Every Epic, Story, and Subtask follows this process. No exceptions. No shortcuts.

## 1. JIRA Connection Details

- **Site:** https://vipulbhatia29.atlassian.net
- **Cloud ID for API calls:** `https://vipulbhatia29.atlassian.net`
- **Project key:** KAN (StockScreener)
- **MCP tools prefix:** `mcp__plugin_atlassian_atlassian__*`
- **Issue types:** Epic, Story, Task, Subtask, Bug
- **Hierarchy:** Epic → Story → Subtask (Tasks are same level as Stories, NOT children of Stories)

## 2. JIRA Board Columns (Workflow Statuses)

```
To Do → In Progress → Blocked → Ready for Verification → Done
```

### Status Transitions
| From | To | Trigger | Who |
|------|-----|---------|-----|
| To Do | In Progress | Agent picks up work | Agent |
| In Progress | Blocked | Needs human input / external dependency | Agent |
| Blocked | In Progress | Human provides answer / blocker resolved | Human or Agent |
| In Progress | Ready for Verification | Work complete, tests pass, PR open | Agent |
| Ready for Verification | Done | Human approves | Human |
| Ready for Verification | In Progress | Human rejects with feedback | Human |

## 3. The Full Feature Lifecycle

### 3.1 Product Level (PM creates — already exists in PRD/FSD/TDD)

```
PRD  →  FSD  →  TDD
```
- PRD defines the feature and user value
- FSD defines functional requirements (these become Stories)
- TDD defines API contracts and technical architecture (aspirational — refined during spec)
- **These are the INPUTS to JIRA, not created in JIRA**

### 3.2 JIRA Structure for Each Feature

```
EPIC: [Phase X — Feature Name]
│
├── STORY: "Refinement: [Feature Name]"          ← ALWAYS FIRST
│     ├── Subtask: Brainstorm [Feature] architecture
│     ├── Subtask: Write spec [Feature]
│     ├── Subtask: Review spec [Feature]          ← assigned to PM (human gate)
│     ├── Subtask: Write plan [Feature]
│     └── Subtask: Review plan [Feature]          ← assigned to PM (human gate)
│
├── STORY: [User Story 1 from FSD]               ← from FSD requirements
│     ├── Subtask: [technical task from plan]
│     ├── Subtask: [technical task from plan]
│     └── ...
│
├── STORY: [User Story 2 from FSD]
│     └── ...
│
└── STORY: [User Story N from FSD]
      └── ...
```

### 3.3 Workflow Phases (in order — NEVER skip)

#### PHASE A: Epic + Story Creation
**When:** PM decides to build a new feature
**Who:** Agent (with PM input)
**Steps:**
1. Create Epic from PRD feature description
2. Create Stories from FSD functional requirements (with acceptance criteria)
3. Create "Refinement: [Feature]" Story with 5 subtasks (brainstorm, spec, spec review, plan, plan review)
4. **DO NOT create implementation subtasks yet** — they come from the approved plan

#### PHASE B: Refinement (Refinement Story)
**When:** Epic + Stories exist
**Who:** Agent + PM
**Steps:**

**B1. Brainstorm** (subtask: "Brainstorm [Feature] architecture")
- Use `superpowers:brainstorming` skill
- Agent explores the design space with PM
- Questions to answer:
  - What are the key architectural decisions?
  - What frameworks/libraries to use? Why?
  - What are the trade-offs?
  - How does this integrate with existing code?
  - What's the testing strategy for this type of code?
  - What's in scope vs. out of scope?
- Output: Design decisions captured in JIRA subtask comments
- Move subtask → Done when PM confirms decisions

**B2. Write Spec** (subtask: "Write spec [Feature]")
- Agent writes detailed technical spec
- File: `docs/superpowers/specs/YYYY-MM-DD-[feature-name].md`
- Covers: architecture, data flow, error handling, dependencies, security, scope
- References PRD/FSD/TDD but goes deeper on HOW
- Move subtask → Ready for Verification

**B3. Spec Review** (subtask: "Review spec [Feature]" — assigned to PM)
- PM reviews spec document
- ✅ Approve → subtask Done
- ❌ Reject → feedback comment → back to B2

**B4. Write Plan** (subtask: "Write plan [Feature]")
- Use `superpowers:writing-plans` skill
- Agent breaks approved spec into sequenced implementation steps
- File: `docs/superpowers/plans/YYYY-MM-DD-[feature-name].md`
- Each step: what to build, which files to create/edit, dependencies, test strategy
- Steps are ordered by dependency (what must be built first)
- Each step maps to a Story + Subtask in JIRA
- Move subtask → Ready for Verification

**B5. Plan Review** (subtask: "Review plan [Feature]" — assigned to PM)
- PM reviews plan: ordering, scope, completeness
- ✅ Approve → subtask Done → Refinement Story Done
- ❌ Reject → feedback comment → back to B4

#### PHASE C: Backlog Creation (after plan approved)
**When:** Refinement Story is Done
**Who:** Agent
**Steps:**
1. Create implementation Subtasks under each Story based on the approved plan
2. Each Subtask has: summary, description with file paths, definition of done, source reference to plan step
3. Order Subtasks by dependency
4. All Subtasks start in "To Do"

#### PHASE D: Implementation (per Subtask)
**When:** Implementation subtasks exist, Refinement Story is Done
**Who:** Agent (use `superpowers:subagent-driven-development` for parallel independent tasks)
**Steps per Subtask:**
1. Agent picks next unblocked Subtask → moves to "In Progress"
2. Agent adds comment: approach summary
3. Agent creates or uses Story branch: `feat/KAN-[story#]-[short-name]`
4. Agent implements + writes tests
5. Agent runs tests locally: `uv run pytest tests/unit/ -v` + `ruff check --fix && ruff format`
6. If tests green → move Subtask to "Ready for Verification"
7. Agent adds structured comment:
   ```
   ## Implementation Complete
   - Branch: feat/KAN-X-name
   - Files changed: [list]
   - Tests added: [count]
   - Test result: All passing
   ```

#### PHASE E: Story PR + Review
**When:** All Subtasks in a Story are Ready for Verification
**Who:** Agent creates PR, PM reviews
**Steps:**
1. Agent opens PR: `feat/KAN-[story#]-[name]` → `develop`
2. CI runs automatically (`ci-pr.yml`): lint + unit + API + Jest
3. CI green → PM reviews PR
4. ✅ Approve + merge → all Subtasks + Story → Done
5. ❌ Reject → feedback → Subtasks back to In Progress

#### PHASE F: Epic Promotion
**When:** All Stories in Epic are Done (merged to develop)
**Who:** PM
**Steps:**
1. Open PR: `develop` → `main`
2. CI full gate (`ci-merge.yml`): lint + test + integration + build
3. PM merges → `deploy.yml` fires (stub until Phase 6)
4. Epic → Done

## 4. Git Branching Integration

```
main                    ← production-ready, always deployable
  └── develop           ← integration branch, accumulates Stories
        ├── feat/KAN-2-agent-selection        ← Story branch
        ├── feat/KAN-3-tool-orchestration     ← Story branch
        ├── feat/KAN-4-streaming              ← Story branch
        └── feat/KAN-5-conversation-history   ← Story branch
```

### Rules
- **One branch per Story** (not per Subtask, not per Epic)
- All Subtasks of a Story commit to the same Story branch
- **ALWAYS branch from `develop`** — never from `main`. Command:
  ```bash
  git checkout develop && git pull origin develop && git checkout -b feat/KAN-[story#]-[short-name]
  ```
  Branching from `main` causes merge conflicts because `develop` diverges from `main` between Epic promotions.
- Story branch PRs go to `develop`
- `develop` → `main` PR when Epic is complete
- Branch naming: `feat/KAN-[story-number]-[short-kebab-name]`
- Hotfixes: `hotfix/KAN-[bug#]-[short-name]` → PR to `main` + back-merge to `develop`

## 5. JIRA Automation Rules (configured in project)

Two automation rules are active:
1. **PR merged → Done:** When a PR is merged (GitHub trigger), transition the referenced issue to Done.
2. **All subtasks done → parent Done:** When a subtask transitions to Done AND all sibling subtasks are also Done, transition the parent Story/Task to Done. Uses Branch/For:Parent to transition the parent, not the trigger.

These handle human-triggered events. Agent still explicitly transitions tickets during its workflow.

## 6. JIRA Transition IDs (for MCP API calls)

| ID | Status |
|----|--------|
| `7` | Blocked |
| `8` | Ready for Verification |
| `11` | To Do |
| `21` | In Progress |
| `31` | Done |

Use `mcp__plugin_atlassian_atlassian__transitionJiraIssue` with `cloudId: "https://vipulbhatia29.atlassian.net"`.

## 7. CI/CD Integration

### PR Gate (ci-pr.yml) — triggers on PR to develop or main
- backend-lint: `ruff check` + `ruff format --check`
- frontend-lint: `npm run lint` + `npx tsc --noEmit`
- backend-test: `pytest tests/unit/ tests/api/`
- frontend-test: `npx jest`
- **Must pass before merge is allowed**

### Merge Gate (ci-merge.yml) — triggers on push to develop
- All of above + integration tests + `npm run build`
- **Must pass before develop → main promotion**

### JIRA ↔ CI Connection (current: manual, future: automated)
| Event | JIRA Action | Today | Future (Phase 4.5) |
|-------|-------------|-------|---------------------|
| PR opened | Subtasks → Ready for Verification | Agent does manually | GitHub Action updates JIRA |
| CI fails on PR | Subtasks stay In Progress | Agent checks CI | GitHub Action comments on JIRA |
| PR merged to develop | Story → Done | Agent does manually | JIRA Automation rule transitions to Done |
| develop → main merged | Epic → Done | PM does manually | JIRA Automation rule or agent reconciliation |

## 8. Session Start Protocol (for Agent)

At the start of every coding session:
1. Read this memory (`conventions/jira-sdlc-workflow`)
2. Query JIRA board: `project = KAN AND status != Done ORDER BY rank ASC`
3. Identify the **current phase** of each active Epic (Refinement? Implementation?)
4. Pick the next unblocked Subtask
5. Present to PM: "Next up is KAN-XX: [summary]. Proceed?"

## 9. Anti-Patterns (NEVER do these)

1. **NEVER create implementation subtasks before Refinement Story is Done**
   - The plan determines the subtask breakdown, not the TDD pseudocode
2. **NEVER skip brainstorming** — even for "obvious" features
   - Every feature has trade-offs worth exploring
3. **NEVER implement without an approved spec + plan**
   - Code without a plan leads to rework
4. **NEVER commit directly to develop or main**
   - Everything goes through a PR with CI gate
5. **NEVER move a Subtask to Ready for Verification with failing tests**
   - Tests must be green locally before status change
6. **NEVER close a Story without all Subtasks Done**
   - Story completion = all Subtasks Done + PR merged
7. **NEVER start a new Epic's implementation while another Epic has open Stories**
   - Finish what you started (Refinement can overlap)

## 10. Git Hooks and CI Checks

The project may have pre-commit and post-commit hooks configured. Before committing:
- Do NOT skip hooks with `--no-verify`
- If a hook fails, read the error and fix the issue — don't bypass
- Hooks may include: ruff lint/format, type checks, secret scanning
- Check `.pre-commit-config.yaml` or `.husky/` if hooks exist
- CI workflows (ci-pr.yml, ci-merge.yml) run the same checks — hooks are local enforcement of the same rules

## 11. JIRA Comment Templates

### Brainstorm Complete
```
## Brainstorm Summary
- **Key decisions:** [list]
- **Trade-offs considered:** [list]
- **Framework/library choices:** [list]
- **Open questions for spec:** [list]
```

### Implementation Complete (on Subtask)
```
## Implementation Complete
- **Branch:** feat/KAN-X-name
- **Files changed:** [list]
- **Tests added:** [count]
- **Test result:** All passing ([total] tests)
- **Notes:** [any context for reviewer]
```

### PR Ready (on Story)
```
## PR Ready for Review
- **PR:** #[number]
- **Branch:** feat/KAN-X-name → develop
- **CI status:** ✅ All checks passing
- **Subtasks completed:** KAN-A, KAN-B, KAN-C
- **Acceptance criteria:** [checklist from Story description]
```
