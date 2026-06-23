#!/usr/bin/env bash
# Weekly on-chain brief refresh — Hermes cron entry point.
#
# Runs every Monday at 06:00 Prague time. Forces a new generated brief, rebuilds
# the product dashboard/Pages copy from fresh data, then commits generated outputs.

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."   # repo root

PROJECT_NAME=onchain-index
LAUNCHD_LOG="$PWD/.cache/launchd-brief-weekly.log"
REFRESH_LOG="$PWD/.cache/brief-weekly.log"
STATUS_FILE="$PWD/.cache/brief-weekly-status.json"
COMMIT_AUTHOR_NAME="Mac mini refresh"
COMMIT_AUTHOR_EMAIL="refresh@onchain-index.local"
SUCCESS_SUMMARY="weekly brief ok (forced brief + dashboard + Pages dashboard)"
if [[ -f .venv/bin/activate ]]; then
    source .venv/bin/activate
fi

source "$HOME/ops/lib/cron-wrapper.sh"

cron_wrapper_pull

{
    echo "=== onchain-index weekly brief: $(date -u +%FT%TZ) ==="
    uv run python -m onchain_index.build --no-cache --force-brief
    uv run python -m onchain_index.build_index_page
} 2>&1 | tee -a "$REFRESH_LOG"

cron_wrapper_commit_outputs \
    briefs \
    docs/dashboard.html \
    docs/index.html \
    outputs/dashboard.html \
    -- "weekly brief refresh $(date -u +%FT%TZ)"
