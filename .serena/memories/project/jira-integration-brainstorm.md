---
scope: project
category: project
updated_by: session-32
---

# JIRA Integration Brainstorm — In Progress

## Context
Session 32: User wants to move entire feature development lifecycle to JIRA.
Goal: JIRA as single source of truth for planning, stories, implementation tracking, and progress.
NOT a solo workflow — designing for a team of AI agents as developers, user as PM/architect.

## JIRA Instance
- Site: https://vipulbhatia29.atlassian.net
- Email: vipulbhatia29@outlook.com
- API token generated: "StockScreener" (expires 2026-03-30) — NOTE: may not be needed, OAuth 2.1 is the primary auth
- Project: "My Kanban Space" (needs rename to "Stock Signal Platform" or "SSP")

## Board Setup (COMPLETE)
- Template: Software development → Kanban
- Statuses: To Do → In Progress → Blocked → Ready for Verification → Done
- Workflow transitions designed:
  - In Progress → Blocked (via "Human-in-the-loop request")
  - Blocked → In Progress (via "Human-in-the-Loop end")
  - In Progress → Ready for Verification (agent submits work)
  - Ready for Verification → In Progress (via "Re-work" — reviewer rejects)
  - Ready for Verification → Done (via "Complete" — reviewer approves)
- Issue types: Epic, Story, Task, Subtask, Bug

## MCP Connection
- Atlassian plugin already enabled in Claude Code (`atlassian@claude-plugins-official`)
- Plugin configures MCP server at `https://mcp.atlassian.com/v1/mcp` via HTTP transport
- OAuth 2.1 authorization NOT yet completed — user needs to restart session to trigger OAuth flow
- No `.mcp.json` needed in project root (plugin handles it)

## Design Decisions (COMPLETE)
1. **Epic mapping:** Option C — JIRA is forward-looking only, Phase 4B onward. No backfill.
2. **Hierarchy:** Epic → Stories (from PRD/FSD) → Subtasks (technical work from TDD/plan)
3. **Agent workflow:** No assignment (solo PM), structured comments, PR link as comment
4. **Team-managed JIRA limitation:** Tasks can't be children of Stories — use Subtasks instead

## JIRA Board (CREATED)

### Epic
- **KAN-1** Phase 4B — AI Chatbot Backend

### Stories (from PRD/FSD)
- **KAN-2** Agent Selection (FR-8.1) → subtasks: KAN-9, KAN-10
- **KAN-3** Tool Orchestration (FR-8.2) → subtasks: KAN-7, KAN-8, KAN-11, KAN-14
- **KAN-4** Streaming Responses (FR-8.3) → subtasks: KAN-12, KAN-13, KAN-15
- **KAN-5** Conversation History (FR-8.4) → subtasks: KAN-6

### Subtasks (technical, from TDD/plan)
- **KAN-6** ChatSession + ChatMessage DB models + migration (→ KAN-5)
- **KAN-7** BaseAgent ABC with tool binding (→ KAN-3)
- **KAN-8** ToolRegistry with all platform tools (→ KAN-3)
- **KAN-9** GeneralAgent — web search + Q&A (→ KAN-2)
- **KAN-10** StockAgent — full platform toolkit (→ KAN-2)
- **KAN-11** Agentic tool-calling loop, max 15 iterations (→ KAN-3)
- **KAN-12** NDJSON streaming layer for SSE (→ KAN-4)
- **KAN-13** POST /api/v1/chat/stream SSE endpoint (→ KAN-4)
- **KAN-14** LLM client: Groq → Claude → LMStudio fallback (→ KAN-3)
- **KAN-15** Wire ChatPanel frontend to streaming backend (→ KAN-4)

## Atlassian Connection
- Cloud ID: 563a03d7-e754-4ac0-8477-275cd76e886f
- Site: https://vipulbhatia29.atlassian.net
- Project key: KAN (StockScreener)
- Auth: OAuth 2.1 via Atlassian MCP plugin (no API token needed for local dev)
- MCP tools: `mcp__plugin_atlassian_atlassian__*`
- Use `cloudId: "https://vipulbhatia29.atlassian.net"` for all API calls
- **Transition IDs:** `11` = To Do, `21` = In Progress, `31` = Done
- Note: Blocked + Ready for Verification statuses not yet configured on board — only 3 statuses available

## Automation Roadmap
1. **Now:** Manual — agent reads board, implements, updates ticket
2. **Soon:** Session startup skill queries JIRA for next unblocked subtask
3. **Future (Phase 4.5+):** GitHub Actions + JIRA webhooks close the loop automatically

## Remaining Design Questions
- How JIRA workflow integrates with git branching (branch per subtask? per story?)
- Agent autonomy boundaries — what can agents do without human approval?
- JIRA ↔ Claude Code integration pattern details