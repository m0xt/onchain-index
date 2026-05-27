# onchain-index

## What this does

Milk Road on-chain index is the product-facing BTC regime dashboard; `MROI` remains the technical math handle inside the `onchain-index` repo/package.

## Repo map

| Path | Purpose |
|---|---|
| `src/onchain_index/data.py` | Production data fetch layer: BMP, Farside ETF flows, Strategy holdings, Coinbase/Binance premium, cache + CLI summary. |
| `scripts/refresh.sh` | LaunchAgent refresh entry point via `~/ops/lib/cron-wrapper.sh`. |
| `scripts/com.milkroad.onchain-index-refresh-daily.plist` | Weekday 22:30 Prague dashboard refresh job. |
| `tests/test_smoke.py` | Import and dry-run smoke tests for the package entry point. |
| `docs/architecture.md` | Human narrative for the current data layer and planned four phases. |
| `agent_docs/repo_map.md` | One-line-per-dir structural map for agents. |
| `agent_docs/cron_failure_recovery.md` | LaunchAgent/dashboard refresh recovery runbook. |
| `agent_docs/secrets.md` | BMP_API_KEY location, validation, and rotation contract. |
| `DECISIONS.md` | Append-only dated rationale for non-obvious project choices. |
| `.cache/` | Gitignored raw fetch cache (`raw_data.pkl`) and local-only scratch data. |

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
- Cron path: `scripts/refresh.sh` (LaunchAgent `com.milkroad.onchain-refresh-daily`, Mon–Fri 22:30 Prague, logs to `.cache/launchd-refresh-daily.log` and `.cache/refresh.log`.)
- LAN dashboard serve: `com.milkroad.onchain-index-serve` exposes `outputs/dashboard.html` at `http://Felixs-Mac-mini.local:8002/dashboard.html`.
- LAN docs serve: `com.milkroad.onchain-index-docs-serve` exposes `docs/index.html` at `http://Felixs-Mac-mini.local:8012/index.html`.

## Conventions

- Python style/tooling is encoded in `pyproject.toml` (`ruff`, lenient `pyright`, `pytest`).
- Production Python lives under `src/onchain_index/`; run entry points with `uv run python -m onchain_index.<module>`.
- Phase A may fetch and cache data only. Do not add composite logic, backtests, optimization, or dashboard artifacts until later phases explicitly ask for them.
- The old prototype at `~/Projects/on-chain-index-archive/` is reference-only. Do not edit it.

## Testing

- Fast gate: `uv run pytest`.
- Lint gate: `uv run ruff check .`.
- Smoke tests import every package module and dry-run the data entry point with a dummy secret.

## Security

- Required var: `BMP_API_KEY`.
- Secret location: `~/ops/secrets/onchain-index/.env`.
- Never commit a real `.env`; `.env.example` is the only committed template.
- Full contract: `agent_docs/secrets.md`.

## When something breaks

Start with `agent_docs/cron_failure_recovery.md`, then `agent_docs/repo_map.md` and `agent_docs/secrets.md`. If a data source is down, let the HTTP error fail loud; do not mask it with placeholder data.
