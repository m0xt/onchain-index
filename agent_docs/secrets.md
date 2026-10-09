# Secrets contract

## Required secret

None. The Bitcoin Magazine Pro subscription ended in 2026-09, and `validate_secrets()` no longer requires `BMP_API_KEY`. A daily refresh runs with no key.

## Optional secret

- `BGEOMETRICS_TOKEN` — optional token for `https://api.bitcoin-data.com/v1/hodl-one-year`.

Without it, BGeometrics applies the free plan (10 requests/hour, 15/day, last 4 years). One daily HODL fetch fits that plan. The frozen history in `data/hodl_1yr_pct_bmp_frozen.csv` covers dates through 2026-08-30, so the live request only needs the splice window forward.

## Location

If you set the optional token, the file lives outside this project repo:

```text
~/ops/secrets/onchain-index/.env
```

Expected contents:

```bash
BGEOMETRICS_TOKEN=...
```

The project also accepts `BGEOMETRICS_TOKEN` from the process environment. The committed `.env.example` documents the variable only and must never contain a real value.

`BMP_API_KEY` may still be present in an old ops env file. The refresh ignores it. Do not put a new BMP key in place to “fix” the job.

## Validation

`validate_secrets()` loads the explicit ops-secret path with `python-dotenv` when that file exists and returns the optional token, or `None`. It does not raise when the file or the token is missing.

## Rotation

1. Replace `BGEOMETRICS_TOKEN` in `~/ops/secrets/onchain-index/.env`, or delete the line to use the free plan.
2. Run `uv run python -m onchain_index.data --no-cache` from this repo.
3. Confirm the fetch summary prints a current date range and `.cache/raw_data.pkl` updates.
4. Do not modify or delete the old prototype's `.env` until Martin explicitly retires it.
