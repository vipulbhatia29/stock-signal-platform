#!/usr/bin/env bash
# Agent gate — runs e2e tests only when agent/tool code changes are staged.
# Used as a pre-commit hook stage. Skips gracefully if no LLM key available.

set -euo pipefail

# Check if any agent or tool files are staged
CHANGED_FILES=$(git diff --cached --name-only --diff-filter=ACM)
AGENT_CHANGES=$(echo "$CHANGED_FILES" | grep -E '^backend/(agents|tools)/' || true)

if [ -z "$AGENT_CHANGES" ]; then
    echo "⏭  No agent/tool changes — skipping agent gate"
    exit 0
fi

echo "🔍 Agent/tool changes detected:"
echo "$AGENT_CHANGES" | sed 's/^/   /'

# Check for LLM API key
if [ -z "${GROQ_API_KEY:-}" ] && [ -z "${ANTHROPIC_API_KEY:-}" ]; then
    echo "⚠️  No LLM API key available — skipping live agent tests"
    echo "   Set GROQ_API_KEY or ANTHROPIC_API_KEY to enable"
    exit 0
fi

echo "🧪 Running agent regression tests..."
uv run pytest tests/unit/agents/ tests/unit/adversarial/ -v --tb=short -q

echo "✅ Agent gate passed"
