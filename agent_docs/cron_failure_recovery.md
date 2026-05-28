# Cron failure recovery

`scripts/refresh.sh` is the production entry point. It refreshes source data, rebuilds `docs/index.html`, mirrors it to `outputs/dashboard.html`, writes `.cache/status.json`, then commits tracked dashboard outputs through `~/ops/lib/cron-wrapper.sh`.

Start every incident here:

```bash
cd ~/projects/onchain-index
tail -200 .cache/launchd-refresh-daily.log 2>/dev/null || true
tail -200 .cache/refresh.log 2>/dev/null || true
cat .cache/status.json 2>/dev/null || true
cat .cache/cron-status.json 2>/dev/null || true
uv run pytest
uv run ruff check .
```

## Data refresh failure

Symptoms:
- `python -m onchain_index.build --no-cache` fails before `outputs/dashboard.html` is updated.
- Stack traces from Bitcoin Magazine Pro, Farside ETF flow reads, Strategy holdings, Yahoo/Coin Metrics, DNS, TLS, rate limits, or empty data frames.
- `.cache/status.json` reports `last_mroi: null` and a non-null `last_error`.

Recovery:
1. Check whether `.cache/raw_data.pkl` exists and whether the failure only happens with `--no-cache`.
2. Retry once after a short interval; source failures are often transient.
3. If cached data is acceptable for the dispatch, run `uv run python -m onchain_index.build` without `--no-cache` and clearly record that the build used cache.
4. Do not commit a dashboard generated from suspicious partial data. Inspect `outputs/dashboard.html` timestamp and `.cache/status.json` first.
5. If a source changed its schema or endpoint, patch `onchain_index.data.fetch_all()` or the relevant parser, then add/update a smoke test.

## Dashboard/status mismatch

Symptoms:
- `docs/index.html` was updated but `outputs/dashboard.html` differs.
- `.cache/status.json` has a stale `last_run_utc`, null `last_mroi`, or non-null `last_error` after a seemingly successful run.
- The LAN page on `http://Felixs-Mac-mini.local:8002/dashboard.html` shows an older build than the repo files.

Recovery:
1. Rebuild locally:
   ```bash
   uv run python -m onchain_index.build --no-cache
   ```
2. Confirm the mirror contract:
   ```bash
   cmp docs/index.html outputs/dashboard.html
   cat .cache/status.json
   ```
3. If the files match but LAN is stale, verify the serve LaunchAgent:
   ```bash
   launchctl list | grep onchain-index-serve || true
   tail -100 .cache/launchd-serve.log 2>/dev/null || true
   curl -fsS http://127.0.0.1:8002/dashboard.html >/tmp/onchain-dashboard.html
   ```
4. Reload the serve plist only if the HTTP server is not running or points at the wrong directory.

## launchd plist not loaded

Symptoms:
- No new `.cache/launchd-refresh-daily.log` output.
- Job does not appear in `launchctl list`.
- Manual `bash scripts/refresh.sh` works.

Diagnose:

```bash
launchctl list | grep -E 'milkroad.*onchain|onchain-refresh' || true
ls -l ~/Library/LaunchAgents/com.milkroad.onchain-index-refresh-daily.plist
plutil -lint ~/Library/LaunchAgents/com.milkroad.onchain-index-refresh-daily.plist
```

Recovery:
1. Confirm the plist path points at the current repo.
2. Manually run `bash scripts/refresh.sh` once to verify the environment.
3. After plist or entrypoint changes, reload the job when safe:
   ```bash
   launchctl unload ~/Library/LaunchAgents/com.milkroad.onchain-index-refresh-daily.plist 2>/dev/null || true
   launchctl load ~/Library/LaunchAgents/com.milkroad.onchain-index-refresh-daily.plist
   ```
4. If the plist is loaded but not firing, check macOS sleep/power settings and launchd logs outside the repo.

## Escalation rules

Escalate instead of guessing if:
- MROI math, holder cohort membership, P4 thresholds, or sizing tiers appear wrong but the dispatch did not ask for parameter changes.
- A data source output changed in a way that affects historical comparability.
- A dashboard build succeeds but values look implausible and no test explains the shift.
- Exchange-flow integration comes up again without a new Martin-approved thesis/rule change.
