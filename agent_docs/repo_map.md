# Repo map

- `README.md` — one-page human front door, P4 summary, and run commands.
- `AGENTS.md` — agent navigation hub and binding repo conventions.
- `CLAUDE.md` — symlink to `AGENTS.md`.
- `DECISIONS.md` — dated rationale for durable decisions.
- `pyproject.toml` / `uv.lock` — uv-managed package, tests, lint, type-check config.
- `src/onchain_index/` — importable production package.
- `src/onchain_index/data.py` — source fetchers, 12h cache, CLI summary.
- `src/onchain_index/composite.py` — Bitcoin Demand Index (`MROI` technical series), valuation diagnostics, P4 thresholds, sizing tiers, and `posture_state_machine()`.
- `src/onchain_index/build.py` — product dashboard renderer for `outputs/dashboard.html`, Pages copy at `docs/dashboard.html`, plus `.cache/status.json`.
- `src/onchain_index/brief.py` — single Claude CLI-generated dashboard brief loader/generator, archived under `briefs/YYYY-MM-DD/onchain.md`.
- `src/onchain_index/build_index_page.py` — generated Atlas at `docs/index.html`.
- `src/onchain_index/backtest.py` — signal construction/backtest helpers used by research and dashboard summaries.
- `src/onchain_index/cost.py` — static Claude/API cost estimates for the Atlas.
- `src/onchain_index/research/optimization/` — research-only Phase G-P scripts and earlier optimizers.
- `tests/` — build, composite, backtest, optimization, and smoke regression tests.
- `docs/architecture.md` — current P4 pipeline, decision rule, dashboard structure, and rejected approaches.
- `docs/theory.md` — framework rationale and Phase G-P evidence trail.
- `docs/index.html` — generated Atlas; rebuild with `uv run python -m onchain_index.build_index_page`.
- `briefs/` — durable dated archive for the single generated on-chain brief.
- `docs/dashboard.html` — GitHub Pages copy of the generated full dashboard; rebuilt by `uv run python -m onchain_index.build`.
- `outputs/dashboard.html` — generated product dashboard; rebuild with `uv run python -m onchain_index.build`.
- `agent_docs/` — terse operational contracts for agents.
- `scripts/` — launchd service plists and operational wrappers.
- `.cache/` — gitignored local cache/status/scratch data; safe to delete and rebuild.

## Port allocation

- `8002` → onchain-index dashboard serve (`com.milkroad.onchain-index-serve`, `outputs/dashboard.html`).
- `8012` → onchain-index docs/Atlas serve (`com.milkroad.onchain-index-docs-serve`, `docs/index.html`).
