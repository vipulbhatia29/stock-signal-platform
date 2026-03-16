---
allowed-tools: mcp__plugin_serena_serena__list_memories, mcp__plugin_serena_serena__read_memory, mcp__plugin_serena_serena__find_file, mcp__plugin_serena_serena__find_symbol, mcp__plugin_serena_serena__search_for_pattern, Bash(git branch:*), Bash(git log:*)
description: Audit all Serena memories for staleness — validates file paths, symbol names, and described behavior
---

## Your task

Perform a staleness audit of all Serena project memories. Work methodically through each memory.

### Step 1 — List all memories

Call `list_memories` to get the full list of project-scoped memory keys.

### Step 2 — Audit each memory

For each memory:
1. Read the memory content.
2. Check each claim type:

   **File path claims** — any path like `backend/tools/market_data.py`:
   Use `find_file` to verify the file exists. If missing: STALE.

   **Symbol name claims** — any function/class like `compute_signals()`:
   Use `find_symbol` to verify the symbol exists. If missing: STALE.

   **Behavioral claims** — e.g., "bcrypt must be pinned to 4.2.x":
   Use `search_for_pattern` to verify the claim (e.g., check pyproject.toml for bcrypt pin).

   **GLOBAL-CANDIDATE flag** — if `GLOBAL-CANDIDATE: true` in frontmatter:
   Flag for promotion to `global/`.

### Step 3 — Report

Output a markdown table:

| Memory Key | Status | Issue (if any) |
|---|---|---|
| project/state | OK | — |
| debugging/backend-gotchas | STALE | example: file renamed |
| domain/agent-tools | GLOBAL-CANDIDATE | frontmatter flag set |

Status values:
- **OK** — all claims verified
- **STALE** — one or more claims no longer accurate (describe issue)
- **GLOBAL-CANDIDATE** — frontmatter `GLOBAL-CANDIDATE: true` flagged for global promotion
- **REMOVE** — memory is entirely superseded or no longer relevant

### Step 4 — Propose fixes

For each STALE or REMOVE item, propose the fix:
- STALE: show updated text for the affected claim(s)
- REMOVE: confirm the memory serves no purpose

Ask for approval before applying any changes.

### Step 5 — Apply approved fixes

On approval, write updated memories using `write_memory`.
If fixes are significant, offer to commit them on a dedicated branch.
