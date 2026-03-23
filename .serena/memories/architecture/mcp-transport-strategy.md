# MCP Transport Strategy (decided Session 49)

## Decision
Agent consumes tools via MCP protocol. Transport evolves: stdio (Phase 5.6) → Streamable HTTP (Phase 6).

## Current State (through Phase 5)
- Agent calls tools via direct in-process Python calls (`tool.execute(params)`)
- `/mcp` Streamable HTTP endpoint exists but only for external clients (Claude Code, Cursor)
- "MCPAdapter" classes (Edgar, AlphaVantage, FRED, Finnhub) are plain API wrappers, NOT real MCP clients

## Phase 5.6 — stdio MCP (local, no cloud needed)
- MCP Tool Server runs as subprocess, spawned by FastAPI lifespan
- Agent executor calls tools via MCP client over stdio pipes (~0 latency)
- Celery tasks stay direct (no MCP overhead for batch jobs)
- `/mcp` endpoint remains for external clients
- New tools built MCP-first from this point

## Phase 6 — Streamable HTTP MCP (cloud deployment)
- Tool Server runs as separate container on :8282
- Agent, Celery, and all clients connect via Streamable HTTP
- Single config change (transport URL), no tool/schema changes
- Enables: independent scaling, any new client app (Telegram, mobile, Slack)

## Key Insight
stdio and Streamable HTTP are independent transport decisions. Tool definitions, schemas, client calls, and auth stay identical. Only the transport config changes.

## Files Updated
- `project-plan.md` — Phase 5.6 added, Phase 6 updated
- `docs/TDD.md` — Section 5.1 corrected, Section 12 rewritten
