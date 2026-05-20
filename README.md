# onchain-pulse-index

`onchain-pulse-index` is the clean reboot of the April 2026 BTC on-chain prototype. Phase A intentionally does only one thing: fetch the raw inputs reliably into a `src/`-layout Python package so later phases can audit indicators before any composite signal is designed.

The project will eventually test whether an MRMI-shaped structure from `macro-framework` fits BTC on-chain data: standalone indicator audit → composite design → optional optimization. It does **not** inherit the old four-layer reader-aid model or any backtest logic.

## Run

```bash
uv sync --extra dev
uv run pytest
uv run python -m onchain_pulse_index.data
```

Fresh data is cached in `.cache/raw_data.pkl` for 12 hours. `BMP_API_KEY` lives outside this repo at `~/ops/secrets/onchain-pulse-index/.env`; copy `.env.example` only as documentation, not as a real secret file.
