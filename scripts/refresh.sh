#!/usr/bin/env bash
# Refresh wrapper — LaunchAgent entry point.
#
# Runs on weekdays — see scripts/com.milkroad.onchain-index-refresh-daily.plist:
#   · Mon–Fri 22:30 Prague — daily on-chain dashboard refresh, mirrored to the
#     macro-framework cron landscape for easy operations.
#
# Delegates boilerplate to ~/ops/lib/cron-wrapper.sh:
#   - git pull, cron status emission, commit/push, operator/engineer handoff.

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."   # repo root

PROJECT_NAME=onchain-index
LAUNCHD_LOG="$PWD/.cache/launchd-refresh-daily.log"
REFRESH_LOG="$PWD/.cache/refresh.log"
STATUS_FILE="$PWD/.cache/cron-status.json"
COMMIT_AUTHOR_NAME="Mac mini refresh"
COMMIT_AUTHOR_EMAIL="refresh@onchain-index.local"
SUCCESS_SUMMARY="refresh ok (dashboard + docs rebuild)"
if [[ -f .venv/bin/activate ]]; then
    source .venv/bin/activate
fi

source "$HOME/ops/lib/cron-wrapper.sh"

cron_wrapper_pull

{
    echo "=== onchain-index refresh: $(date -u +%FT%TZ) ==="
    uv run python -m onchain_index.build --no-cache
    uv run python -m onchain_index.build_index_page
} 2>&1 | tee -a "$REFRESH_LOG"

cron_wrapper_commit_outputs \
    .cache/status.json \
    docs/index.html \
    outputs/dashboard.html \
    -- "refresh $(date -u +%FT%TZ)"
