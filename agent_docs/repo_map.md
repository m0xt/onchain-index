# Repo map

- `README.md` — one-page human front door and run commands.
- `AGENTS.md` — agent navigation hub and binding Phase A constraints.
- `CLAUDE.md` — symlink to `AGENTS.md`.
- `DECISIONS.md` — dated rationale for durable decisions.
- `pyproject.toml` / `uv.lock` — uv-managed package, tests, lint, type-check config.
- `src/onchain_index/` — importable production package.
- `src/onchain_index/data.py` — source fetchers, 12h cache, CLI summary.
- `tests/` — smoke tests only in Phase A.
- `docs/` — human-facing architecture notes.
- `agent_docs/` — terse operational contracts for agents.
- `.cache/` — gitignored local cache; safe to delete and rebuild.
