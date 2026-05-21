#!/usr/bin/env bash
# PostToolUse hook: detect if Claude's output looks like an API error or
# ToS refusal, and emit a fallback hint that the orchestrator can act on.
#
# This hook runs after every Task tool call. It reads the tool output
# from $CLAUDE_HOOK_TOOL_OUTPUT (Claude Code injects this), pipes it
# through the bridge's failure-class detector, and if a failure is
# detected, writes a stamped flag file that the orchestrator polls.
#
# CC-exclusive: no-op on other hosts.

set -euo pipefail

# Only run on Claude Code.
[[ -n "${CLAUDE_PLUGIN_ROOT:-}" ]] || exit 0

# Only run when we're inside an active ai-scientist job.
JOB_DIR="${AI_SCIENTIST_OUTPUT_DIR:-}"
[[ -n "$JOB_DIR" ]] || exit 0

# Pull tool output. Claude Code provides it via $CLAUDE_HOOK_TOOL_OUTPUT
# OR (for Task) via stdin. We accept both.
OUTPUT="${CLAUDE_HOOK_TOOL_OUTPUT:-$(cat 2>/dev/null || true)}"
[[ -n "$OUTPUT" ]] || exit 0

CLI="${CLAUDE_PLUGIN_ROOT}/mcp/scripts/codex_bridge_cli.py"
[[ -f "$CLI" ]] || exit 0

# Run the failure-class detector. Exit 0 = ok, exit 1 = failure detected.
FAILURE_CLASS=$(printf '%s' "$OUTPUT" | python "$CLI" failure-class 2>/dev/null || echo "ok")

if [[ "$FAILURE_CLASS" != "ok" ]]; then
  # Stamp a flag file the orchestrator can pick up on its next turn.
  FLAG_DIR="$JOB_DIR/.codex_fallback_flags"
  mkdir -p "$FLAG_DIR"
  TS=$(date -u +%Y%m%dT%H%M%SZ)
  FLAG_FILE="$FLAG_DIR/${TS}_${FAILURE_CLASS}.flag"
  {
    printf 'failure_class: %s\n' "$FAILURE_CLASS"
    printf 'timestamp: %s\n' "$TS"
    printf 'tool_name: %s\n' "${CLAUDE_HOOK_TOOL_NAME:-unknown}"
    printf 'output_excerpt: |\n'
    printf '%s\n' "$OUTPUT" | head -c 2000 | sed 's/^/  /'
  } > "$FLAG_FILE"

  # Emit a hint on stderr so it shows up in Claude's hook log.
  printf '[codex-fallback] detected %s — flag at %s\n' "$FAILURE_CLASS" "$FLAG_FILE" >&2
fi

# Always exit 0 so we don't break the host.
exit 0
