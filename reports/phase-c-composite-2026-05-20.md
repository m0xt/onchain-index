# Phase C composite — PI_score calibration/backtest — 2026-05-20

Data snapshot: cached Phase A frame, `5252` daily rows, `2012-01-01→2026-05-19`, `18` fetched columns. BTC returns use BMP `btc_price.pct_change()`. Backtests keep the Phase B convention of 252 bars/year for comparability. All composite inputs are lagged: a score dated T uses source data through T-1.

## 1. Indicator → dimension mapping

Hard-gate result: **passed, but narrowly**. The level-based on-chain holder candidates stayed negative; the one surviving on-chain holder-behavior rule is a transformed HODL-wave signal: **30d change in 1Y+ HODL share, inverted z-score**. This represents below-trend HODL-share change / contracting aged-supply share, and was positive in all four walk-forward cycles.

| Indicator | Phase B / retest alpha | Dimension call | Composite decision | Notes |
| --- | ---: | --- | --- | --- |
| STH MVRV | +10.6%, 4/4 cycles | Valuation | Include | Despite the holder label, the signal is price vs short-term-holder cost basis; treat as valuation to avoid double-counting. |
| RHODL Ratio | +9.1%, 4/4 cycles | Valuation | Include | Age-band realized-value valuation oscillator. |
| Puell Multiple | +1.3%, 3/4 cycles | Valuation | Include | Miner-revenue valuation lens; modest standalone but diversifies the valuation basket. |
| MVRV-Z | +1.5%, 2/4 cycles | Valuation | Include | Chosen over NUPL as the canonical realized-cap deviation metric. |
| NUPL | +4.7%, 2/4 cycles | Valuation | Exclude / alternate | Excluded because Phase B found MVRV-Z/NUPL correlation at 0.88; do not include both. |
| LTH MVRV | -10.5% (`z>0`), -33.0% (`z<0`) | Holder Behavior / on-chain | Exclude | Natural dimension is holder positioning, but both signs are negative full-sample. |
| HODL 1Y+ level | -31.3% (`z>0`), -12.5% (`z<0`) | Holder Behavior / on-chain | Exclude level rule | Level rule remains mismatched to timing use. |
| HODL 1Y+ 30d change | **+15.9%**, 4/4 cycles (`z<0`) | Holder Behavior / on-chain | **Include** | Surviving on-chain holder-behavior constituent; no threshold tuning, just transform from slow level to change. |
| Address Growth | -18.7% (`z>0`), -25.7% (`z<0`) | Holder-ish / adoption | Exclude | Both signs failed; also closer to adoption than holder positioning. |
| Reserve Risk | -5.8% (`z>0`), -36.7% (`z<0`) | Holder/valuation hybrid | Exclude | Literature-low Reserve Risk did not work as a standalone long/cash rule under the Phase B convention. |
| Hash Ribbon | -2.5% | Out | Exclude | Miner-derived; not cleanly Valuation or Holder Behavior in the locked theory. |
| MSTR Holdings Δ | -0.9% | Holder Behavior / corporate DAT | Include as cohort | Weak standalone, but it is the only current DAT cohort feed and is structurally part of the theory. |
| ETF Net Flow | +12.4%, short coverage | Holder Behavior / institutional ETF | Include as cohort | Cleanest post-2024 marginal-holder flow input. |
| Coinbase Premium | -20.5% | Uncertain | Exclude | Not salvaged as exchange-flow proxy; behaves more like short-window sentiment/microstructure. |
| Exchange net flow | — | Holder Behavior / exchange-side flow | Gap | Explicit all-NaN cohort until a real source is added. |

Sign-contested retest detail:

| Rule | Full-sample alpha | Cycle alphas (2014-17 / 2018-21 / 2022-24 / 2025-now) | Decision |
| --- | ---: | --- | --- |
| HODL 1Y+ level `z>0` | -31.3% | -67.2 / +3.1 / -8.6 / +9.4 | Out |
| HODL 1Y+ level `z<0` | -12.5% | +1.5 / -25.5 / -9.6 / +0.0 | Out |
| HODL 1Y+ 30d-change `z<0` | **+15.9%** | **+19.4 / +14.3 / +8.3 / +22.5** | **In** |
| Address Growth `z>0` | -18.7% | -42.6 / +20.9 / -14.2 / +17.9 | Out |
| Address Growth `z<0` | -25.7% | -31.9 / -37.6 / -3.7 / -7.1 | Out |
| Reserve Risk `z>0` | -5.8% | +1.3 / -22.4 / +12.0 / +6.6 | Out |
| Reserve Risk `z<0` | -36.7% | -67.1 / -0.8 / -26.8 / +2.6 | Out |

## 2. Composite definitions

Implementation lives in `src/onchain_index/composite.py`; Phase C backtests call `pi_score()` and `sizing_tier()` directly.

Notation: `z(x)` means a 504d trailing z-score of `x`, shifted one day before scoring.

**Valuation composite**

```text
valuation = mean_available(
  z(sth_mvrv),
  z(rhodl_ratio),
  z(puell_multiple),
  z(mvrv_zscore)
)
```

**Holder Behavior cohorts**

```text
on_chain          = -z(diff_30d(hodl_1yr_pct))
corporate_dat     =  z(diff_30d(mstr_btc))
institutional_etf =  z(rolling_30d_sum(etf_net_flow_m))
exchange_flow     =  NaN until a real source exists

holder_behavior = mean_available(on_chain, corporate_dat, institutional_etf, exchange_flow)
```

**Headline score**

```text
PI_score = valuation + holder_behavior
```

Cohorts are equal-weighted across available coverage. This is epoch-aware by construction: pre-DAT dates can only use on-chain; post-MSTR dates can use on-chain + DAT once enough history exists; ETF contributes only after ETF launch plus enough trailing history for the 504d z-score.

## 3. Tier thresholds + empirical sanity check

Default threshold buckets remain the fixed z-score-style theory defaults:

| PI_score bucket | Tier | Allocation default |
| --- | --- | ---: |
| `< -1.0` | Cash | 0% |
| `[-1.0, 0.0)` | Trim | 50% |
| `[0.0, 1.0)` | Sized | 75% |
| `>= 1.0` | Strong | 100% |

Empirical full-history tier share:

| Tier | Share of non-NaN days |
| --- | ---: |
| Cash | 26.9% |
| Trim | 17.9% |
| Sized | 22.8% |
| Strong | 32.4% |

Cycle-reference PI_score values:

| Reference point | Date used | PI_score | Tier | Valuation | Holder Behavior | Read-through |
| --- | --- | ---: | --- | ---: | ---: | --- |
| 2013 cycle top | 2013-12-04 | +5.46 | Strong | +3.75 | +1.71 | Correctly euphoric/high-risk by score, though tier maps high score to max-long under the current trend-following convention. |
| 2015 bottom | 2015-01-14 | -1.86 | Cash | -0.93 | -0.93 | Correctly deep risk-off/capitulation. |
| 2017 cycle top | 2017-12-17 | +5.46 | Strong | +4.50 | +0.95 | Correctly extreme positive. |
| 2018 bottom | 2018-12-15 | -0.73 | Trim | -1.14 | +0.41 | Near lower boundary but not full Cash; holder behavior softened the valuation low. |
| 2021 cycle top | 2021-11-10 | -0.28 | Trim | +0.66 | -0.94 | Important mismatch/feature: holder distribution offset valuation, so top was not a Strong print. |
| 2022 bottom / FTX | 2022-11-21 | -0.95 | Trim | -0.89 | -0.06 | Borderline Cash but not below -1. |
| Current latest | 2026-05-19 | -0.50 | Trim | -0.93 | +0.43 | Cheap-ish valuation offset by positive holder/DAT contribution. |

Sanity-check verdict: fixed thresholds are usable for v1 and not obviously miscalibrated at bottoms, but cycle tops are mixed. 2013/2017 printed extremely high; 2021 was already Trim because holder behavior had deteriorated. Do **not** auto-shift thresholds here; this is calibration evidence for Martin.

## 4. Walk-forward backtest

Default tier map: Cash=0%, Trim=50%, Sized=75%, Strong=100%.

| Window | BTC B&H ann | PI tier ann | PI alpha | BTC DD | PI DD | Avg allocation | Tier transitions/yr | Avg dwell |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Full sample | +42.6% | +55.7% | **+13.1%** | -84.5% | -64.5% | 58.4% | 17.4 | 15d |
| 2014-2017 | +66.3% | +77.3% | **+11.0%** | -80.8% | -53.3% | 67.2% | 14.8 | 17d |
| 2018-2021 | +23.1% | +37.2% | **+14.1%** | -81.4% | -57.8% | 53.8% | 13.3 | 19d |
| 2022-2024 | +17.5% | +34.5% | **+17.0%** | -66.9% | -27.6% | 57.6% | 20.0 | 13d |
| 2025-now | -9.4% | +3.8% | **+13.2%** | -49.6% | -13.1% | 38.6% | 34.1 | 7d |

Benchmark comparison:

| Window | PI tier ann / alpha | Best single benchmark | Static 50/50 BTC/cash ann / alpha |
| --- | --- | --- | --- |
| Full sample | +55.7% / +13.1% | — | +24.8% / -17.8% |
| 2014-2017 | +77.3% / +11.0% | STH MVRV: +68.7% / +2.4% | +35.1% / -31.2% |
| 2018-2021 | +37.2% / +14.1% | STH MVRV: +51.1% / +28.0% | +16.9% / -6.2% |
| 2022-2024 | +34.5% / +17.0% | STH MVRV: +28.4% / +10.9% | +11.2% / -6.3% |
| 2025-now | +3.8% / +13.2% | ETF Net Flow: +9.7% / +19.1% | -3.1% / +6.2% |

Interpretation: the composite beats BTC B&H in **4/4 cycles** and beats the 50/50 static baseline comfortably. It does not beat the best single indicator in every cycle: STH MVRV wins 2018-2021, and ETF Net Flow wins 2025-now. That is acceptable for a v1 composite if the goal is robustness rather than per-cycle winner selection.

## 5. Sub-cohort epoch evolution

Epoch labels for dashboard use:

| Epoch | Intended holder cohorts | Production coverage in this repo |
| --- | --- | --- |
| 2012-2020 | on-chain | On-chain HODL-change cohort only. |
| 2020-2024 | on-chain + corporate DAT | MSTR starts 2020-08-10, but 504d z-score warmup delays usable DAT scoring. |
| 2024-onward | on-chain + corporate DAT + institutional ETF | ETF starts 2024-01-11, but 504d z-score warmup means ETF cohort first contributes in 2025. |
| Future | + exchange-flow | Not sourced; explicit NaN placeholder. |

For dates where all three current 2024-onward cohorts are live (`2025-06-27→2026-05-19`), average absolute contribution share:

| Cohort | Avg abs contribution share | Latest abs contribution share |
| --- | ---: | ---: |
| On-chain | 36.9% | 24.0% |
| Corporate DAT | 25.8% | 65.4% |
| Institutional ETF | 37.3% | 10.6% |
| Exchange flow | — | — |

Latest score (`2026-05-19`): PI_score `-0.50`, tier `Trim`; valuation `-0.93`, holder behavior `+0.43`. Holder cohort values: on-chain `-1.01`, corporate DAT `+2.76`, institutional ETF `-0.45`, exchange flow `NaN`.

## 6. Open Q1/Q2/Q3 with recommended defaults

1. **Sizing floor:** recommend **0% Cash floor for v1**. The backtest already shows drawdown control with Cash=0%; a 25% structural floor is a portfolio-policy choice, not something Phase C data demands.
2. **Tier naming:** recommend **Strong / Sized / Trim / Cash**. It is descriptive and dashboard-friendly without pretending there is more precision than four buckets.
3. **Threshold calibration:** recommend **fixed `(-1, 0, +1)` thresholds for v1**, with the regime-reference table displayed as calibration evidence. Do not optimize or grid-search thresholds in Phase C.

Open questions worth Martin's attention:
- The 2021 top being `Trim`, not `Strong`, means the holder dimension materially changed the top diagnosis; this is probably useful but should be discussed.
- The current production holder dimension has only one on-chain holder rule after the hard gate. That makes DAT/ETF cohorts disproportionately important post-2024.
- Exchange-side flow is still the cleanest missing cohort; Coinbase Premium should not be used as a substitute.

## 7. Dashboard sketch

Phase C.5 should build the iteration surface, not this report. Suggested layout:

```text
┌─────────────────────────────────────────────────────────────┐
│ PI_score: -0.50        Tier: Trim        Allocation: 50%    │
│ Epoch: 2024-onward     Data gaps: exchange_flow missing     │
├───────────────────────────────┬─────────────────────────────┤
│ Dimension scores              │ Holder sub-cohorts          │
│ Valuation:        -0.93        │ On-chain:          -1.01    │
│ Holder Behavior:  +0.43        │ Corporate DAT:     +2.76    │
│                               │ Institutional ETF: -0.45    │
│                               │ Exchange flow:      N/A     │
├─────────────────────────────────────────────────────────────┤
│ Historical chart: BTC log price + PI_score line             │
│ Tier shading: Cash / Trim / Sized / Strong                  │
│ Markers: known cycle tops/bottoms from Section 3            │
├─────────────────────────────────────────────────────────────┤
│ Walk-forward panel: per-cycle alpha, drawdown, dwell time   │
└─────────────────────────────────────────────────────────────┘
```

The headline score drives the decision; the dimension and cohort panels explain the decision. The dashboard should surface composition drift explicitly rather than hiding it inside the aggregate.
