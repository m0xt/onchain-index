# Secrets contract

## Required secret

- `BMP_API_KEY` — Bitcoin Magazine Pro API key used by `src/onchain_pulse_index/data.py`.

## Location

The real file lives outside this project repo:

```text
~/ops/secrets/onchain-pulse-index/.env
```

Expected contents:

```bash
BMP_API_KEY=...
```

The project also accepts `BMP_API_KEY` from the process environment, but the ops-secret file is the canonical machine-local location. The committed `.env.example` documents the variable only and must never contain a real value.

## Validation

`validate_secrets()` loads the explicit ops-secret path with `python-dotenv` and raises `RuntimeError` before network work if `BMP_API_KEY` is missing.

## Rotation

1. Replace the value in `~/ops/secrets/onchain-pulse-index/.env`.
2. Run `uv run python -m onchain_pulse_index.data --no-cache` from this repo.
3. Confirm the fetch summary prints a current date range and `.cache/raw_data.pkl` updates.
4. Do not modify or delete the old prototype's `.env` until Martin explicitly retires it.
