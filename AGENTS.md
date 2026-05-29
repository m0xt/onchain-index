# onchain-index

## What this does

Milk Road on-chain index is the product-facing BTC regime dashboard; `MROI` remains the technical math handle inside the `onchain-index` repo/package.

Production architecture is P4: `mroi()` returns `holder_behavior_composite(data)`, and `posture_state_machine()` maps that holder spine into binary `LONG` / `CASH` posture with a hold-prior-state noise band.

## Repo map

| Path | Purpose |
|---|---|
| `src/onchain_index/data.py` | Production data fetch layer: BMP, Farside ETF flows, Strategy holdings, Coinbase/Binance premium, cache + CLI summary. |
| `src/onchain_index/composite.py` | Canonical MROI construction, holder cohorts, valuation diagnostics, P4 thresholds, and `posture_state_machine()`. |
| `src/onchain_index/build.py` | Product dashboard renderer for `outputs/dashboard.html`, Pages copy at `docs/dashboard.html`, plus `.cache/status.json`. |
| `src/onchain_index/brief.py` | Single Claude CLI-generated dashboard brief loader/generator, archived under `briefs/YYYY-MM-DD/onchain.md`. |
| `src/onchain_index/build_index_page.py` | Generated Atlas at `docs/index.html`. |
| `src/onchain_index/backtest.py` | Lagged signal and walk-forward backtest helpers used by research/tests/dashboard summaries. |
| `src/onchain_index/cost.py` | Static Claude/API cost estimates for the Atlas. |
| `src/onchain_index/research/optimization/` | Research-only Phase G-P scripts and earlier optimizers; not production signal code. |
| `tests/` | Regression, build, optimization, and smoke tests. |
| `scripts/refresh.sh` | LaunchAgent refresh entry point via `~/ops/lib/cron-wrapper.sh`. |
| `scripts/com.milkroad.onchain-index-refresh-daily.plist` | Weekday 22:30 Prague dashboard/docs refresh job. |
| `scripts/com.milkroad.onchain-index-serve.plist` | LAN dashboard server for `outputs/dashboard.html` on port 8002. |
| `scripts/com.milkroad.onchain-index-docs-serve.plist` | LAN docs/Atlas server for `docs/index.html` on port 8012. |
| `docs/architecture.md` | Human narrative for the current P4 pipeline, decision rule, dashboard structure, and rejected approaches. |
| `docs/theory.md` | Framework rationale and Phase G-P decision trail. |
| `docs/index.html` | Generated Atlas; rebuild with `uv run python -m onchain_index.build_index_page`. |
| `briefs/` | Durable dated archive for the single generated on-chain brief. |
| `docs/dashboard.html` | GitHub Pages copy of the generated full dashboard; rebuilt by `uv run python -m onchain_index.build`. |
| `outputs/dashboard.html` | Generated product dashboard; rebuild with `uv run python -m onchain_index.build`. |
| `agent_docs/repo_map.md` | One-line-per-dir structural map for agents. |
| `agent_docs/cron_failure_recovery.md` | LaunchAgent/dashboard refresh recovery runbook. |
| `agent_docs/secrets.md` | BMP_API_KEY location, validation, and rotation contract. |
| `DECISIONS.md` | Append-only dated rationale for non-obvious project choices. |
| `.cache/` | Gitignored raw fetch cache, status files, and local-only scratch data. |

## How to run

- Install/update deps: `uv sync --extra dev`
- Tests: `uv run pytest`
- Lint: `uv run ruff check .`
- Type check: `uv run pyright`
- Fetch data: `uv run python -m onchain_index.data`
- Force fresh data: `uv run python -m onchain_index.data --no-cache`
- Dry-run entry point: `uv run python -m onchain_index.data --dry-run`
- Build dashboard from cache: `uv run python -m onchain_index.build`
- Force dashboard refresh: `uv run python -m onchain_index.build --no-cache`
- Build Atlas: `uv run python -m onchain_index.build_index_page`
- Cron path: `scripts/refresh.sh` (LaunchAgent `com.milkroad.onchain-index-refresh-daily`, Mon–Fri 22:30 Prague, logs to `.cache/launchd-refresh-daily.log` and `.cache/refresh.log`.)
- LAN dashboard serve: `com.milkroad.onchain-index-serve` exposes `outputs/dashboard.html` at `http://Felixs-Mac-mini.local:8002/dashboard.html`.
- LAN docs serve: `com.milkroad.onchain-index-docs-serve` exposes `docs/index.html` at `http://Felixs-Mac-mini.local:8012/index.html`.

## Conventions

- Python style/tooling is encoded in `pyproject.toml` (`ruff`, lenient `pyright`, `pytest`).
- Production Python lives under `src/onchain_index/`; run entry points with `uv run python -m onchain_index.<module>`.
- Keep production signal changes in `src/onchain_index/composite.py` and lock behavior with tests.
- Research scripts under `src/onchain_index/research/optimization/` are evidence generators only; they do not change production posture unless a later task explicitly migrates them.
- The old prototype at `~/Projects/on-chain-index-archive/` is reference-only. Do not edit it.

## Testing

- Fast gate: `uv run pytest`.
- Lint gate: `uv run ruff check .`.
- Type gate: `uv run pyright`.
- Smoke tests import every package module and dry-run the data entry point with a dummy secret.

## Security

- Required var: `BMP_API_KEY`.
- Secret location: `~/ops/secrets/onchain-index/.env`.
- Never commit a real `.env`; `.env.example` is the only committed template.
- Full contract: `agent_docs/secrets.md`.

## When something breaks

Start with `agent_docs/cron_failure_recovery.md`, then `agent_docs/repo_map.md` and `agent_docs/secrets.md`. If a data source is down, let the HTTP error fail loud; do not mask it with placeholder data.
