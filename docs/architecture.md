# Architecture

Milk Road on-chain index is a BTC regime dashboard. The production signal is P4: `MROI` is the holder-behavior composite only, and allocation posture is a sticky asymmetric LONG/CASH state machine.

## Current pipeline

1. `validate_secrets()` loads `BMP_API_KEY` from `~/ops/secrets/onchain-index/.env` or the process environment and fails before network work if it is missing.
2. `fetch_bmp()` pulls Bitcoin Magazine Pro daily metrics from 2012-01-01 onward.
3. `fetch_etf_flows()` pulls daily US spot BTC ETF flows from Farside.
4. `fetch_strategy_holdings()` pulls Strategy/MSTR BTC holdings from strategytracker.com.
5. `fetch_coinbase_premium()` compares Coinbase BTC-USD and Binance BTCUSDT daily closes from 2023 onward for Reference Library context.
6. `fetch_all()` merges source frames onto the BMP daily date index and caches the result at `.cache/raw_data.pkl` for 12 hours.
7. `holder_behavior_cohorts()` computes the three production holder cohorts with lagged rolling z-scores.
8. `holder_behavior_composite()` equal-weights the available holder cohorts by date.
9. `mroi()` returns that holder composite as the production MROI.
10. `posture_state_machine()` maps MROI to the sticky P4 posture.
11. `build_dashboard()` writes `outputs/dashboard.html`, copies it to `docs/dashboard.html` for GitHub Pages, and writes `.cache/status.json`.
12. `build_index_page()` writes `docs/index.html`, the separate Atlas for challenging constants, source contracts, backtest assumptions, and docs links.
13. `scripts/refresh.sh` runs both builders on the LaunchAgent cadence and lets `~/ops/lib/cron-wrapper.sh` commit tracked outputs.

HTTP errors intentionally fail loud. Missing source columns should be fixed at the parser/source-contract layer, not hidden behind placeholder values.

## Production signal path

Production math lives in `src/onchain_index/composite.py`.

```python
mroi(data) = holder_behavior_composite(data)
```

`valuation_composite()` still exists for diagnostics and dashboard Reference Library context, but it is not part of `mroi()` and not part of the allocation decision.

All production z-scores use `rolling_zscore()`, which lags inputs so a score dated T only uses source data through T-1.

## Holder behavior parameter provenance

The holder spine has three epoch-aware cohorts. Each cohort contributes when its source has live coverage; the composite is the mean across cohorts available on that date.

| Cohort | Production transform | Coverage gate | Source |
|---|---|---|---|
| On-chain holders | `-rolling_zscore(hodl_1yr_pct.diff(30))` | 2012 onward | Bitcoin Magazine Pro / Glassnode-class HODL share |
| Corporate DAT | `rolling_zscore(mstr_btc.diff(30))` | `MSTR_START = 2020-08-10` | StrategyTracker / Strategy treasury history |
| Institutional ETF | `rolling_zscore(etf_net_flow_m.rolling(30).sum())` | `ETF_START = 2024-01-11` | Farside spot BTC ETF flows |

Production constants:

```python
HODL_DELTA_DAYS = 30
DAT_DELTA_DAYS = 30
ETF_FLOW_SUM_DAYS = 30
```

Epoch labels surfaced by `epoch_for_date()`:

| Epoch | Active production inputs |
|---|---|
| 2012-2020 | On-chain holders |
| 2020-2024 | On-chain holders + corporate DAT |
| 2024-onward | On-chain holders + corporate DAT + institutional ETF |

## Decision rule

P4 is a binary posture with an amber noise band. The amber band is not a separate allocation tier; it means keep the current state.

```python
MROI_LONG_THRESHOLD = 0.0
MROI_CASH_THRESHOLD = -0.3

if first_valid_mroi:
    state = "LONG" if mroi >= 0.0 else "CASH"
elif mroi > 0.0:
    state = "LONG"
elif mroi < -0.3:
    state = "CASH"
else:
    state = previous_state
```

Allocation mapping:

| State | Exposure |
|---|---:|
| `LONG` | 100% |
| `CASH` | 0% |

The strict inequalities are intentional: after initialization, exactly `0.0` and exactly `-0.3` stay inside the hold-prior-state band.

## Dashboard structure

`outputs/dashboard.html` follows the macro-framework visual idiom while keeping the on-chain model simpler:

1. **Hero** — current MROI, current posture, allocation percentage, signal zone, active epoch, and headline holder drivers.
2. **Section 1: MROI history** — holder-spine history with BTC as an optional normalized overlay and green/amber/red P4 zones.
3. **Section 2: holder cohorts** — expandable decision-input rows for on-chain HODL behavior, Strategy treasury delta, and spot ETF flows. Each row shows the current z-score plus raw-input history.
4. **Section 3: Reference Library** — supplementary valuation charts. These indicators explain cycle context but do not affect posture.
5. **Footer** — repo, commit, refresh timestamp, and theory version.

`docs/index.html` is the Atlas, not the dashboard mirror. It links to `docs/dashboard.html`, the GitHub Pages copy of the full generated dashboard from `outputs/dashboard.html`. The Atlas uses the same dark card layout as macro-framework's Atlas and imports live constants from production modules.

## Reference Library diagnostics

Valuation diagnostics are retained for explanation and cycle awareness:

- `sth_mvrv`
- `rhodl_ratio`
- `puell_multiple`
- `mvrv_zscore`

They are equal-weighted by `valuation_composite()` for display/context only. NUPL remains excluded because it overlaps heavily with MVRV-Z.

## Rejected approaches

These are deliberately out of production unless Martin explicitly reopens the research thread:

- Exchange-flow integration: Phase E rejected the canonical 30d net-flow rule.
- Valuation overrides or overlays: Phase G/J/N found they did not improve allocation quality after holder behavior was available.
- BTC/equity relative-strength spines: Phase H/I/L did not beat the holder-only spine.
- Symmetric zero-crossing and extra stickiness rules: Phase M/O showed the churn/lag trade-off was worse than P4.
- LONG/CAUTION/CASH tier vocabulary: Phase P found the qualifying production candidate was binary P4, not a tiered state model.
- Macro inputs: macro-framework owns the external macro view; this repo produces the BTC-inside holder-behavior view.

See the Phase G-P reports in `reports/` and `docs/theory.md` for the evidence trail.

## Operational posture

- Required secret: `BMP_API_KEY`.
- Main data cache: `.cache/raw_data.pkl`.
- Dashboard output: `outputs/dashboard.html`, served on LAN port `8002` by `com.milkroad.onchain-index-serve`.
- GitHub Pages dashboard copy: `docs/dashboard.html`.
- Atlas: `docs/index.html`, served on LAN port `8012` by `com.milkroad.onchain-index-docs-serve`.
- Daily refresh: `scripts/refresh.sh`, weekday 22:30 Prague.

If a source fails, prefer a loud failure and a clear incident over partial or placeholder data.
