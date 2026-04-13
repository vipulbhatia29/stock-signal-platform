---
name: capture
description: Capture notes to Obsidian vault. Use when user says "/capture", "save to obsidian", "capture this", or "note this down".
argument-hint: "[topic or content to capture]"
allowed-tools: "mcp__obsidian__obsidian_append_content mcp__obsidian__obsidian_simple_search mcp__obsidian__obsidian_get_file_contents Write"
---

# Capture to Obsidian — $ARGUMENTS

Save a note to the Obsidian vault at `/Users/sigmoid/Documents/brain/`.

## Step 1: Try MCP, fall back to file write

Try `mcp__obsidian__obsidian_simple_search` first. If the MCP call fails (Obsidian not running), switch to **fallback mode** for the rest of this capture:
- Skip deduplication (can't search without API)
- Use the `Write` tool to write directly to `/Users/sigmoid/Documents/brain/0-inbox/<title>.md`
- Tell the user: "Obsidian wasn't running — wrote directly to disk. Open Obsidian to index it."

If MCP works, proceed normally with deduplication + `mcp__obsidian__obsidian_append_content`.

## Step 2: Deduplicate (MCP mode only)

Search the vault with keywords from $ARGUMENTS.
If a similar note exists, **append** to it instead of creating a new one.

## Step 3: Classify

| Field | How to determine |
|---|---|
| **type** | `research` (findings, explorations), `decision` (choices + rationale), `capture` (quick ideas) |
| **source** | Always `claude-code` in this context |
| **project** | From working directory. Default: `stock-signal-platform`. Use `general` if not project-specific |

## Step 4: Write

Write to `0-inbox/<Title Case Note Name>.md` with this format:

```markdown
---
tags: [<type>, <topic-tags>]
source: claude-code
project: <project>
date: YYYY-MM-DD
status: inbox
---

# <Title>

<Content — summarize the relevant conversation context, not the entire chat>

## Related
- [[Concept A]]
- [[Concept B]]
```

## Step 5: Confirm

Tell the user: the file path and a one-line summary. Nothing more.

## Rules

- One concept per note — multiple things = multiple notes
- Link generously — any concept that could be its own note gets `[[double brackets]]`
- No dates in titles — dates go in frontmatter only
- Keep it concise — capture the insight, not the conversation
