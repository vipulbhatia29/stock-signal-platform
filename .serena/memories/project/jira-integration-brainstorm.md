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

## Completed Epics (as of Session 67)
- KAN-1: Phase 4B — AI Chatbot Backend (Done)
- KAN-22: CI/CD Pipeline + Branching Strategy (Done)
- KAN-30: Phase 4C — Frontend Chat UI (Done)
- KAN-61: Phase 4D — Agent Intelligence (Done)
- KAN-88: Phase 4F — UI Migration (Done)
- KAN-106: Phase 5 — Forecasting + Automation (Done)
- KAN-119: Phase 5.6 — MCP Tool Server (Done)
- KAN-139: Phase 6 — LLM Factory (Done)
- KAN-147: Phase 7 — Backend Hardening (Done)
- KAN-163: Phase 7.5 — Tech Debt (Done)
- KAN-176: Phase 7.6 — Scale Readiness (Done)
- KAN-189: Phase 8 — ReAct + Observability (Done)
- KAN-211: Test Suite Hardening (In Progress)