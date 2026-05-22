#!/usr/bin/env bash
# scripts/update.sh -- one-command updater for vedix (v3.0+).
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/danilkotelnikov/vedix/master/scripts/update.sh | bash
#
# Re-runs bootstrap.sh (the bootstrap is itself idempotent and handles
# clone-or-pull, dep refresh, config re-merge, and self-test).

set -e
echo
printf "\033[35mVedix -- update via bootstrap\033[0m\n"
curl -fsSL "https://raw.githubusercontent.com/danilkotelnikov/vedix/master/scripts/bootstrap.sh" | bash
