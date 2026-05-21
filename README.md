# onchain-index

Milk Road on-chain index is the product-facing BTC regime dashboard; `PI_score` remains the technical math handle inside the `onchain-index` repo/package.

The project will eventually test whether an MRMI-shaped structure from `macro-framework` fits BTC on-chain data: standalone indicator audit → composite design → optional optimization. It does **not** inherit the old four-layer reader-aid model or any backtest logic.

## Run

```bash
uv sync --extra dev
uv run pytest
uv run python -m onchain_index.data
```

Fresh data is cached in `.cache/raw_data.pkl` for 12 hours. `BMP_API_KEY` lives outside this repo at `~/ops/secrets/onchain-index/.env`; copy `.env.example` only as documentation, not as a real secret file.
