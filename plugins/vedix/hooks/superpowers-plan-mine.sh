#!/usr/bin/env bash
set -e
PLAN_PATH="${CLAUDE_HOOK_TOOL_INPUT_FILE:-}"
[[ -n "$PLAN_PATH" ]] || exit 0
[[ "$PLAN_PATH" =~ docs/(plans|specs)/.*\.md$ ]] || exit 0
python "${CLAUDE_PLUGIN_ROOT}/mcp/scripts/plan_archive.py" mine \
  --path "$PLAN_PATH" \
  --palace "${HOME}/.ai-scientist/plugin-palace" \
  --wing "design" \
  --room "$(echo "$PLAN_PATH" | grep -oE 'specs|plans')" \
  --tags "auto,plan,$(date +%Y-%m-%d)" 2>&1 | head -3
