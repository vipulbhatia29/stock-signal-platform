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
- MCP tools prefix: `mcp__plugin_atlassian_atlassian__*` (verify in current session — prefix may differ by MCP server version)
- Auth: OAuth 2.1 via Atlassian MCP plugin (browser-based, no API token needed for local dev)
- API token existed (expired 2026-03-30) — regenerate if headless/CI use needed

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

## Epic Status (Session 113)
Epic list below was frozen at Session 67 and is **44+ sessions out of date**. Canonical source for current Epic/ticket status is now `MEMORY.md` + the JIRA board. Only the JIRA connection details + transition IDs above remain authoritative.