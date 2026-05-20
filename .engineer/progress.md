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
