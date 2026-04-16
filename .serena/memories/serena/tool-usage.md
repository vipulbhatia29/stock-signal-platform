---
scope: project
category: serena
---

# Serena Tool Usage Rules

## MCP Prefix
Use `mcp__serena__*` (the active MCP server exposes tools under this prefix; older memories referencing `mcp__plugin_serena_serena__*` are out of date).
Must call `activate_project("stock-signal-platform")` at session start before any memory reads/writes.

## Tool Priority
ALL file operations use Serena first:
- `find_file`, `list_dir`, `search_for_pattern`, `read_file` (not Read/Grep/Glob)
- `replace_content`, `replace_symbol_body`, `insert_after_symbol` (not Edit/Write)
- This applies to TypeScript, CSS, JSON — not just Python.
- Built-in Read/Grep/Edit/Glob only when Serena cannot do the job.

## Symbolic Reading (token efficiency)
- `get_symbols_overview(file)` — see all symbols without reading bodies.
- `find_symbol(name_path, include_body=True)` — read a specific function/class.
- NEVER read entire files to find one function — use find_symbol first.

## Editing
- Replace entire symbol: `replace_symbol_body`
- Replace a few lines: `replace_content` (regex or string)
- Add to end of file: `insert_after_symbol` with last top-level symbol
- Add to start of file: `insert_before_symbol` with first top-level symbol
