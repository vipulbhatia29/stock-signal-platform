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

## Completed Epics (as of Session 47)
- KAN-1: Phase 4B — AI Chatbot Backend (Done)
- KAN-22: CI/CD Pipeline + Branching Strategy (Done)
- KAN-30: Phase 4C — Frontend Chat UI (Done)
- KAN-61: Phase 4D — Agent Intelligence (Done)
- KAN-88: Phase 4F — UI Migration (Done)
- KAN-106: Phase 5 — Forecasting & Automation (Done)

## Key Convention
Read `conventions/jira-sdlc-workflow` for the mandatory process. Never skip refinement.
Query `project = KAN AND status != Done ORDER BY rank ASC` to find next work.
