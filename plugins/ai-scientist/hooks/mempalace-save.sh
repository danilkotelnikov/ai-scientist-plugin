#!/usr/bin/env bash
# Stop / PreCompact hook: save the current session's important context
# into the active job's MemPalace before context gets dropped or compacted.
#
# Args:
#   $1 — trigger name: "precompact" or "stop"
#
# Behavior:
#   - If no active ai-scientist job, exit 0.
#   - If a job is in progress, mine the current session into the per-job
#     palace via `mempalace save` (scoped to the job_id).

set -euo pipefail

TRIGGER="${1:-stop}"
JOB_DIR="${AI_SCIENTIST_OUTPUT_DIR:-}"

if [[ -z "$JOB_DIR" || ! -f "$JOB_DIR/config.json" ]]; then
  exit 0
fi

# Per-project palace lives INSIDE the job's output directory at .palace/.
# Self-contained, no cross-project leakage.
JOB_ID=$(python -c "import json,sys; print(json.load(open('$JOB_DIR/config.json'))['job_id'])" 2>/dev/null || echo "unknown")
JOB_PALACE="$JOB_DIR/.palace"

mkdir -p "$JOB_PALACE"

# Init the per-job palace if not yet done.
if [[ ! -f "$JOB_PALACE/palace.db" ]]; then
  mempalace init "$JOB_PALACE" --quiet 2>/dev/null || true
fi

# Save: mine current conversation/state into the palace.
# Tag with the trigger so we can distinguish stop-saves from precompact-saves.
mempalace save \
  --root "$JOB_PALACE" \
  --tag "$TRIGGER" \
  --tag "ai-scientist" \
  --tag "job:$JOB_ID" \
  2>/dev/null || true
