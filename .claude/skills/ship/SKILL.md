---
name: ship
description: End-of-session ship workflow — capture to Obsidian, promote Serena memories, commit, push, and open PR. Use when user says "/ship" or "let's ship".
disable-model-invocation: true
argument-hint: "[optional: PR title]"
allowed-tools: "mcp__obsidian__obsidian_simple_search mcp__obsidian__obsidian_append_content mcp__obsidian__obsidian_get_file_contents Bash Edit Write"
---

# Ship — $ARGUMENTS

End-of-session workflow: capture knowledge, then ship code.

## Step 1: Obsidian Capture

Before touching git, ask the user:

> **Anything worth capturing to Obsidian?** Key decisions, research findings, domain insights, or hard-won lessons from this session?
>
> I can capture specific topics, or skip if nothing notable.

- If the user names topics: invoke `/capture` for each one
- If the user says "skip" or "no": proceed to step 2
- If the user says "you decide": scan the conversation for decisions, research findings, or gotchas that aren't already in the vault. Search Obsidian first to avoid duplicates. Write 1-3 notes max — quality over quantity.

## Step 2: Promote Serena Memories

- Update `project/state` memory (ALWAYS)
- Promote any `session/` memories to `project/` if they proved useful
- Delete stale `session/` memories

## Step 3: Commit & Push

- `git add` relevant files (never `.env` or credentials)
- Commit with conventional commit message
- Push to remote with `-u` flag

## Step 4: Open PR

- Target: `develop` (ALWAYS — never main)
- Title: `[KAN-X] Summary` or `$ARGUMENTS` if provided
- Body: summary bullets + test plan
- Link JIRA ticket if applicable

## Step 5: JIRA Reconciliation

- Transition completed tickets to Done (transition ID `31`)
- Verify board reflects reality
