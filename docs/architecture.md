# Architecture

Phase A contains only the data-fetch foundation for a future BTC on-chain pulse index. The package fetches raw inputs from four sources and merges them onto the Bitcoin Magazine Pro daily date index.

## Current data flow

1. `validate_secrets()` loads `BMP_API_KEY` from `~/ops/secrets/onchain-index/.env` or the process environment and fails before network work if it is missing.
2. `fetch_bmp()` pulls on-chain metrics from Bitcoin Magazine Pro from 2012-01-01 onward.
3. `fetch_etf_flows()` pulls daily US spot BTC ETF flows from Farside.
4. `fetch_strategy_holdings()` pulls Strategy/MSTR BTC holdings from strategytracker.com.
5. `fetch_coinbase_premium()` compares Coinbase BTC-USD and Binance BTCUSDT daily closes from 2023 onward.
6. `fetch_all()` merges the source frames into one daily `pandas.DataFrame` and caches it at `.cache/raw_data.pkl` for 12 hours.

HTTP errors intentionally fail loud. Missing data-source columns should be fixed at the parser/source-contract layer, not hidden behind placeholder values.

## Planned phases

- **Phase A — Bootstrap:** clean repo, secrets contract, salvaged data layer, smoke tests.
- **Phase B — Indicator audit:** standalone alpha/colinearity audit of candidate indicators; still no composite.
- **Phase C — Composite design:** MRMI-shaped momentum composite + stress modifier + threshold, tested by BTC cycle and compared against graded sizing.
- **Phase D — Optimization:** conditional; only if Phase C baseline is honest and gains survive perturbation.

The April 2026 prototype's four-layer reader-aid dashboard and backtests are deliberately left out.
