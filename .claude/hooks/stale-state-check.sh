#!/bin/bash
# Stale state detector — SessionStart hook
# Returns additionalContext warning if project/state memory is older than latest commit
# Exit 0 always — this is advisory, never blocks

set -euo pipefail

# Navigate to project root (hook may run from any cwd)
cd "$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0

# Get last commit date
LAST_COMMIT_DATE=$(git log -1 --format=%ai 2>/dev/null | cut -d' ' -f1) || exit 0

# Find Serena state file
STATE_FILE=".serena/memories/project/state.md"

if [ ! -f "$STATE_FILE" ]; then
  echo "{\"additionalContext\": \"No project/state memory found. Create one with current branch, test count, and resume point before starting work.\"}"
  exit 0
fi

# Get state file modification date (macOS stat format)
if [[ "$(uname)" == "Darwin" ]]; then
  STATE_DATE=$(stat -f "%Sm" -t "%Y-%m-%d" "$STATE_FILE" 2>/dev/null) || exit 0
else
  STATE_DATE=$(stat -c "%y" "$STATE_FILE" 2>/dev/null | cut -d' ' -f1) || exit 0
fi

# Compare dates
if [[ "$STATE_DATE" < "$LAST_COMMIT_DATE" ]]; then
  COMMITS_BEHIND=$(git log --oneline --since="$STATE_DATE" 2>/dev/null | wc -l | tr -d ' ')
  echo "{\"additionalContext\": \"project/state memory is ~${COMMITS_BEHIND} commits behind (state: ${STATE_DATE}, latest commit: ${LAST_COMMIT_DATE}). Read and update project/state before proceeding.\"}"
fi

exit 0
