#!/bin/bash
# Doc-delta reminder — PostToolUse hook
# Fires after Edit/Write on backend API surface files
# Returns additionalContext reminder to note doc delta
# Exit 0 always — reminder only, never blocks

set -euo pipefail

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty') || exit 0

# Skip if no file path (shouldn't happen, but defensive)
[ -z "$FILE_PATH" ] && exit 0

# Only fire for backend API surface directories
# Match: backend/routers/*.py, backend/models/*.py, backend/services/*.py
# Exclude: test files, __init__.py, migration files
if echo "$FILE_PATH" | grep -qE 'backend/(routers|models|services)/[^/]+\.py$' && \
   ! echo "$FILE_PATH" | grep -qE '(test_|__init__|/migrations/)'; then

  # Extract the component type from the path
  COMPONENT=$(echo "$FILE_PATH" | grep -oE '(routers|models|services)')
  FILENAME=$(basename "$FILE_PATH" .py)

  echo "{\"additionalContext\": \"API surface edited: ${COMPONENT}/${FILENAME}.py — note doc delta if new endpoints, models, or services were added (type + description + file path).\"}"
fi

exit 0
