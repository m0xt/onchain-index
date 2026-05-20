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
