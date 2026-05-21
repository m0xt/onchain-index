# Engineer progress — onchain-index

Append a structured entry at the bottom on every dispatch. Format:

```
## <UTC timestamp> — <short title>
- What: <1-2 line summary>
- Files touched: <list>
- Commit: <SHA or "none">
- Status: completed | partial | blocked
- Open thread for next dispatch: <if any, else "none">
```

Keep entries terse — this file is read by every stateless dispatch.

## 2026-05-20T11:48:23Z — Internal rename to onchain-index
- What: Renamed Python package/project metadata/docs from the Phase A inferred name to `onchain-index`; regenerated uv lock/sync under the new package name.
- Files touched: src/onchain_index/, pyproject.toml, uv.lock, tests/test_smoke.py, README.md, AGENTS.md, DECISIONS.md, docs/architecture.md, agent_docs/*.md, .env.example, .engineer/progress.md
- Commit: pending in this commit
- Status: completed
- Open thread for next dispatch: none

## 2026-05-20T11:55:20Z — Phase B standalone indicator audit
- What: Added reusable lagged binary-signal/backtest helpers, measured 13 standalone on-chain signals vs BTC buy-and-hold, and wrote ranked/cycle/correlation Phase B report.
- Files touched: src/onchain_index/backtest.py, tests/test_backtest.py, reports/phase-b-indicator-audit-2026-05-20.md, .engineer/progress.md
- Commit: pending in this commit
- Status: completed
- Open thread for next dispatch: Phase C should choose the composite slate from the report; funding rate/SOPR/exchange net flow remain source-expansion gaps.

## 2026-05-20T13:02:25Z — Phase C PI_score composite
- What: Built production PI_score composite, tiered sizing backtest, cycle walk-forward report, and lock-style composite tests; sign gate passed via HODL 1Y+ 30d-change z<0 as the only on-chain holder survivor.
- Files touched: src/onchain_index/composite.py, src/onchain_index/backtest.py, tests/test_composite.py, tests/test_backtest.py, reports/phase-c-composite-2026-05-20.md, .engineer/progress.md
- Commit: pending in this commit
- Status: completed
- Open thread for next dispatch: Phase C.5 dashboard surface; exchange-flow data remains missing and Coinbase Premium is not a valid substitute.

## 2026-05-21T08:50:26Z — Phase C.5 dashboard iteration surface
- What: Added `onchain_index.build` to refresh/cache data, render the single-page PI_score dashboard/iteration surface, mirror it to `outputs/dashboard.html`, and write `.cache/status.json`; added build smoke/status tests.
- Files touched: src/onchain_index/build.py, tests/test_build.py, docs/index.html, outputs/dashboard.html, .engineer/progress.md
- Commit: pending in this commit
- Status: completed
- Open thread for next dispatch: Review dashboard layout with Martin; launchd/cron wiring intentionally deferred.

## 2026-05-21T09:04:10Z — Phase C.5.1 LAN dashboard serve
- What: Added launchd LAN serve for outputs/dashboard.html on :8002, documented the port allocation/LAN URL, generated the MacBook webloc, loaded/smoke-tested the job, and placed fallback relay copies in ~/Public.
- Files touched: scripts/com.milkroad.onchain-index-serve.plist, AGENTS.md, agent_docs/repo_map.md, DECISIONS.md, .engineer/progress.md, /tmp/onchain-index-dashboard.webloc, ~/Public/onchain-index-dashboard.webloc
- Commit: pending in this commit
- Status: completed
- Open thread for next dispatch: none
