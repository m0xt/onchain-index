# onchain-index

Milk Road on-chain index is the product-facing BTC regime dashboard. `MROI` remains the technical math handle inside this repo/package.

The current production architecture is P4: a holder-behavior-only MROI and an asymmetric LONG/CASH state machine.

```text
MROI = z(holder_behavior)

MROI > 0.0   → LONG
MROI < -0.3  → CASH
otherwise    → hold the prior posture
```

Holder behavior is an equal-weight composite of the available live cohorts for each date:

- on-chain HODL behavior: inverted 30d change in 1Y+ HODL share
- corporate DAT accumulation: Strategy/MSTR 30d BTC-holdings change
- institutional ETF flows: 30d rolling sum of spot BTC ETF net flows

Valuation inputs still ship as Reference Library diagnostics for cycle context, but they do not drive the production posture. The Phase G-P research thread in `reports/` and the rationale in `docs/theory.md` / `DECISIONS.md` explain why P4 replaced the earlier candidate structures.

## Run

```bash
uv sync --extra dev
uv run pytest
uv run python -m onchain_index.data
uv run python -m onchain_index.build
uv run python -m onchain_index.build_index_page
```

Fresh data is cached in `.cache/raw_data.pkl` for 12 hours. `BMP_API_KEY` lives outside this repo at `~/ops/secrets/onchain-index/.env`; copy `.env.example` only as documentation, not as a real secret file.
