---
scope: project
category: project
updated_by: session-34
---

# JIRA Integration — Complete Reference

## JIRA Instance
- Site: https://vipulbhatia29.atlassian.net
- Cloud ID for API calls: `https://vipulbhatia29.atlassian.net`
- Project: StockScreener (key: `KAN`, id: 10000)
- MCP tools prefix: `mcp__plugin_atlassian_atlassian__*`
- Auth: OAuth 2.1 via Atlassian MCP plugin (browser-based, no API token needed for local dev)
- API token exists (expires 2026-03-30) for headless/CI use

## Transition IDs
| ID | Status |
|----|--------|
| `7` | Blocked |
| `8` | Ready for Verification |
| `11` | To Do |
| `21` | In Progress |
| `31` | Done |

## Board: 5 Columns
To Do → In Progress → Blocked → Ready for Verification → Done

## Issue Types
Epic → Story → Subtask (Tasks are same level as Stories, NOT children)

## Automation Rules (2 active)
1. **PR merged → Done** — transitions issue referenced in PR title to Done
2. **All subtasks done → parent Done** — cascades up: subtask → Story → Epic

## GitHub for Jira App
Installed and connected to `stock-signal-platform` repo. Enables:
- Smart commits (KAN-* references in commit messages)
- PR references visible in JIRA dev panel
- Automation triggers for PR events

## JIRA Board — Current Tickets

### Epic: KAN-1 Phase 4B — AI Chatbot Backend
- KAN-16 Story: Refinement (To Do) — subtasks KAN-17 to KAN-21
- KAN-2 Story: Agent Selection (To Do) — subtasks KAN-9, KAN-10
- KAN-3 Story: Tool Orchestration (To Do) — subtasks KAN-7, KAN-8, KAN-11, KAN-14
- KAN-4 Story: Streaming Responses (To Do) — subtasks KAN-12, KAN-13, KAN-15
- KAN-5 Story: Conversation History (To Do) — subtask KAN-6

### Epic: KAN-22 CI/CD Pipeline + Branching Strategy
- KAN-23 Story: Refinement (Done)
- KAN-29 Story: Doc catch-up (To Do)

## Key Convention
Read `conventions/jira-sdlc-workflow` for the mandatory process. Never skip refinement.
