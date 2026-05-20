# onchain-pulse-index

## What this does

`onchain-pulse-index` fetches raw BTC on-chain and off-chain market-structure inputs for a future MRMI-shaped on-chain pulse index. Phase A is data-only: no composite, no backtest, no optimization.

## Repo map

| Path | Purpose |
|---|---|
| `src/onchain_pulse_index/data.py` | Production data fetch layer: BMP, Farside ETF flows, Strategy holdings, Coinbase/Binance premium, cache + CLI summary. |
| `tests/test_smoke.py` | Import and dry-run smoke tests for the package entry point. |
| `docs/architecture.md` | Human narrative for the current data layer and planned four phases. |
| `agent_docs/repo_map.md` | One-line-per-dir structural map for agents. |
| `agent_docs/secrets.md` | BMP_API_KEY location, validation, and rotation contract. |
| `DECISIONS.md` | Append-only dated rationale for non-obvious project choices. |
| `.cache/` | Gitignored raw fetch cache (`raw_data.pkl`) and local-only scratch data. |

## How to run

- Install/update deps: `uv sync --extra dev`
- Tests: `uv run pytest`
- Lint: `uv run ruff check .`
- Type check: `uv run pyright`
- Fetch data: `uv run python -m onchain_pulse_index.data`
- Force fresh data: `uv run python -m onchain_pulse_index.data --no-cache`
- Dry-run entry point: `uv run python -m onchain_pulse_index.data --dry-run`

## Conventions

- Python style/tooling is encoded in `pyproject.toml` (`ruff`, lenient `pyright`, `pytest`).
- Production Python lives under `src/onchain_pulse_index/`; run entry points with `uv run python -m onchain_pulse_index.<module>`.
- Phase A may fetch and cache data only. Do not add composite logic, backtests, optimization, or dashboard artifacts until later phases explicitly ask for them.
- The old prototype at `~/Projects/on-chain-index/` is reference-only. Do not edit it.

## Testing

- Fast gate: `uv run pytest`.
- Lint gate: `uv run ruff check .`.
- Smoke tests import every package module and dry-run the data entry point with a dummy secret.

## Security

- Required var: `BMP_API_KEY`.
- Secret location: `~/ops/secrets/onchain-pulse-index/.env`.
- Never commit a real `.env`; `.env.example` is the only committed template.
- Full contract: `agent_docs/secrets.md`.

## When something breaks

Start with `agent_docs/repo_map.md` and `agent_docs/secrets.md`. If a data source is down, let the HTTP error fail loud; do not mask it with placeholder data.
