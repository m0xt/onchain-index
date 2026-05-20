# Phase B indicator alpha audit — 2026-05-20

Data snapshot: `5252` daily rows, `2012-01-01→2026-05-19`, `18` fetched columns. BTC returns use BMP `btc_price.pct_change()`.

## 1. Data availability audit

| Column | Source | First available date | Last date | Coverage gaps | Kind |
| --- | --- | --- | --- | --- | --- |
| mvrv_zscore | BMP | 2012-01-01 | 2026-05-19 | none | z-score/valuation oscillator |
| market_cap | BMP | 2012-01-01 | 2026-05-19 | none | level ($ market capitalization) |
| realized_cap | BMP | 2012-01-01 | 2026-05-19 | none | level ($ realized capitalization) |
| btc_price | BMP | 2012-01-01 | 2026-05-19 | none | price level |
| nupl | BMP | 2012-01-01 | 2026-05-19 | none | ratio/profitability oscillator |
| lth_mvrv | BMP | 2012-01-01 | 2026-05-19 | none | ratio |
| sth_mvrv | BMP | 2012-01-01 | 2026-05-19 | none | ratio |
| puell_multiple | BMP | 2012-01-01 | 2026-05-19 | none | ratio/miner revenue multiple |
| hash_30dma | BMP | 2017-01-01 | 2026-05-19 | none | level/smoothed hashrate |
| hash_60dma | BMP | 2017-01-01 | 2026-05-19 | none | level/smoothed hashrate |
| adr_dma30 | BMP | 2012-01-01 | 2026-05-19 | none | level/smoothed active addresses |
| adr_dma365 | BMP | 2012-01-01 | 2026-05-19 | none | level/smoothed active addresses |
| hodl_1yr_pct | BMP | 2012-01-01 | 2026-05-19 | none | ratio/supply share |
| reserve_risk | BMP | 2012-01-01 | 2026-05-19 | none | ratio/valuation-risk oscillator |
| rhodl_ratio | BMP | 2012-01-01 | 2026-05-19 | none | ratio/age-band valuation oscillator |
| etf_net_flow_m | Farside | 2024-01-11 source launch; merged as 0 before launch | 2026-05-19 | none | flow ($M/day) |
| mstr_btc | strategytracker | 2020-08-10 | 2026-05-19 | none | level (BTC held) |
| cb_premium_pct | Coinbase+Binance | 2023-08-25 | 2026-05-19 | none | ratio/spread (%) |

Notes: Farside ETF flow starts with the spot ETF era; the merged Phase A frame fills pre-launch ETF flow as `0`, but Phase B signals mask the pre-launch period out of the ETF standalone backtest. Coinbase premium coverage is limited by the current Binance daily-close fetch window.

### Target slate cross-reference

| Target | Side | Status | Phase B note |
| --- | --- | --- | --- |
| MVRV-Z | Momentum | ✅ available | BMP `mvrv_zscore` |
| NUPL | Momentum | ✅ available | BMP `nupl` |
| SOPR | Momentum | ⚠️ pullable but missing | Not in current fetch; likely BMP metric/API addition if available under the existing BMP key. |
| Hash Ribbon | Momentum | ✅ available | BMP `hash_30dma`, `hash_60dma` since 2017. |
| Address growth | Momentum | ✅ available | BMP `adr_dma30`, `adr_dma365`. |
| Funding rate | Stress | ⚠️ pullable but missing | Not in current fetch; likely Binance futures funding endpoint / derivatives API. |
| Exchange net flow | Stress | ❌ not pullable from current implemented sources | Would need Glassnode/CryptoQuant/BMP exchange-flow coverage if available; not present now. |
| ETF flow | Stress | ✅ available | Farside total spot BTC ETF net flow since 2024-01-11. |
| Coinbase premium | Stress | ✅ available | Coinbase/Binance daily close spread since 2023-08-25. |

## 2. Methodology

Each available indicator is tested as a standalone binary long/cash BTC signal against buy-and-hold over the same date range. Rules are canonical/literature-shaped where obvious; contested or generic indicators use the uniform 504-bar trailing z-score `> 0`, mirroring macro-framework’s long percentile/z-score lookback discipline without optimizing thresholds or windows. All signal constructors are lagged one day: a signal dated T uses source data through T-1 and is then applied to T returns. Annualized metrics keep macro-framework’s 252-bars/year convention for comparability, even though BTC trades seven days/week. No composite construction, grid search, or source expansion is included.

### Canonical standalone rules

| Indicator | Source columns | Binary rule |
| --- | --- | --- |
| MVRV-Z | `mvrv_zscore` | 504d trailing z-score > 0 |
| NUPL | `nupl` | 504d trailing z-score > 0 |
| LTH MVRV | `lth_mvrv` | 504d trailing z-score > 0 |
| STH MVRV | `sth_mvrv` | 504d trailing z-score > 0 |
| Puell Multiple | `puell_multiple` | 504d trailing z-score > 0 |
| Hash Ribbon | `hash_30dma`, `hash_60dma` | lagged 30d hashrate MA > 60d MA |
| Address Growth | `adr_dma30`, `adr_dma365` | 504d trailing z-score of (30d active-address MA / 365d MA − 1) > 0 |
| HODL 1Y+ | `hodl_1yr_pct` | 504d trailing z-score > 0 |
| Reserve Risk | `reserve_risk` | 504d trailing z-score > 0; not inverted |
| RHODL Ratio | `rhodl_ratio` | 504d trailing z-score > 0 |
| ETF Net Flow | `etf_net_flow_m` | 30d trailing net-flow sum > 0 |
| MSTR Holdings Δ | `mstr_btc` | 30d trailing holdings change > 0 |
| Coinbase Premium | `cb_premium_pct` | 30d trailing premium mean > 0 |

## 3. Per-indicator full-sample table — ranked by alpha

| Indicator | Alpha | B&H ann | Strat ann | B&H DD | Strat DD | Green% | Flips/yr | Avg hold | Sample (252-bar years) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ETF Net Flow | +12.4% | +15.9% | +28.3% | -49.6% | -27.4% | 73.1% | 7.6 | 33d | 2024-02-10→2026-05-19 (3.3y) |
| STH MVRV | +10.6% | +41.0% | +51.6% | -84.5% | -48.2% | 46.4% | 7.9 | 32d | 2013-05-19→2026-05-19 (18.8y) |
| RHODL Ratio | +9.1% | +41.0% | +50.1% | -84.5% | -73.6% | 51.7% | 1.4 | 176d | 2013-05-19→2026-05-19 (18.8y) |
| NUPL | +4.7% | +41.0% | +45.7% | -84.5% | -68.5% | 58.1% | 3.9 | 65d | 2013-05-19→2026-05-19 (18.8y) |
| MVRV-Z | +1.5% | +41.0% | +42.6% | -84.5% | -59.9% | 52.6% | 3.7 | 69d | 2013-05-19→2026-05-19 (18.8y) |
| Puell Multiple | +1.3% | +41.0% | +42.4% | -84.5% | -57.1% | 45.0% | 17.2 | 15d | 2013-05-19→2026-05-19 (18.8y) |
| MSTR Holdings Δ | -0.9% | +27.7% | +26.8% | -76.7% | -51.7% | 71.2% | 5.6 | 45d | 2020-09-10→2026-05-19 (8.2y) |
| Hash Ribbon | -2.5% | +37.7% | +35.1% | -83.8% | -76.9% | 80.8% | 4.5 | 56d | 2017-01-02→2026-05-19 (13.6y) |
| Reserve Risk | -5.8% | +41.0% | +35.2% | -84.5% | -74.8% | 45.2% | 3.6 | 71d | 2013-05-19→2026-05-19 (18.8y) |
| LTH MVRV | -10.5% | +41.0% | +30.5% | -84.5% | -76.9% | 52.3% | 3.8 | 67d | 2013-05-19→2026-05-19 (18.8y) |
| Address Growth | -18.7% | +41.0% | +22.3% | -84.5% | -67.3% | 41.1% | 2.4 | 106d | 2013-05-19→2026-05-19 (18.8y) |
| Coinbase Premium | -20.5% | +31.8% | +11.3% | -49.6% | -32.3% | 53.3% | 4.7 | 54d | 2023-09-24→2026-05-19 (3.8y) |
| HODL 1Y+ | -31.3% | +41.0% | +9.8% | -84.5% | -73.0% | 50.0% | 0.4 | 678d | 2013-05-19→2026-05-19 (18.8y) |

## 4. Per-cycle walk-forward table

| Indicator | 2014-2017 α | 2018-2021 α | 2022-2024 α | 2025-now α | Positive cycles | Avg α |
| --- | --- | --- | --- | --- | --- | --- |
| STH MVRV | +2.4% (5.8y) | +28.0% (5.8y) | +10.9% (4.3y) | +2.1% (2.0y) | 4/4 | +10.9% |
| RHODL Ratio | +7.0% (5.8y) | +1.6% (5.8y) | +14.1% (4.3y) | +18.5% (2.0y) | 4/4 | +10.3% |
| NUPL | +25.2% (5.8y) | -6.7% (5.8y) | +17.7% (4.3y) | -0.3% (2.0y) | 2/4 | +9.0% |
| MVRV-Z | +27.7% (5.8y) | -3.5% (5.8y) | +9.3% (4.3y) | -0.6% (2.0y) | 2/4 | +8.2% |
| ETF Net Flow | — | — | -6.0% (1.3y) | +19.0% (2.0y) | 1/2 | +6.5% |
| Puell Multiple | +6.9% (5.8y) | -9.5% (5.8y) | +6.2% (4.3y) | +17.6% (2.0y) | 3/4 | +5.3% |
| Reserve Risk | +1.3% (5.8y) | -22.4% (5.8y) | +12.0% (4.3y) | +6.6% (2.0y) | 3/4 | -0.6% |
| LTH MVRV | +9.0% (5.8y) | -17.9% (5.8y) | +3.8% (4.3y) | +2.3% (2.0y) | 3/4 | -0.7% |
| Hash Ribbon | +0.0% (1.4y) | +3.3% (5.8y) | -9.5% (4.3y) | -1.7% (2.0y) | 1/4 | -2.0% |
| Address Growth | -42.6% (5.8y) | +20.9% (5.8y) | -14.2% (4.3y) | +17.9% (2.0y) | 2/4 | -4.5% |
| MSTR Holdings Δ | — | -60.7% (1.9y) | +15.7% (4.3y) | +0.0% (2.0y) | 1/3 | -15.0% |
| HODL 1Y+ | -67.2% (5.8y) | +3.1% (5.8y) | -8.6% (4.3y) | +9.4% (2.0y) | 2/4 | -15.8% |
| Coinbase Premium | — | — | -69.0% (1.8y) | +6.8% (2.0y) | 1/2 | -31.1% |

Short coverage is flagged in-cell. Missing cells have fewer than 100 aligned observations.

## 5. Pairwise binary-signal correlation matrix

Correlations are computed between binary in/out series over joint non-null coverage (`min_periods=100`).

|  | MVRV-Z | NUPL | LTH MVRV | STH MVRV | Puell Multiple | Hash Ribbon | Address Growth | HODL 1Y+ | Reserve Risk | RHODL Ratio | ETF Net Flow | MSTR Holdings Δ | Coinbase Premium |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| MVRV-Z | 1.00 | 0.88 | 0.76 | 0.56 | 0.57 | 0.24 | 0.28 | -0.15 | 0.56 | 0.60 | 0.47 | 0.10 | 0.36 |
| NUPL | 0.88 | 1.00 | 0.74 | 0.50 | 0.59 | 0.21 | 0.22 | -0.18 | 0.58 | 0.66 | 0.48 | 0.05 | 0.36 |
| LTH MVRV | 0.76 | 0.74 | 1.00 | 0.37 | 0.44 | 0.19 | 0.24 | -0.20 | 0.57 | 0.69 | 0.23 | 0.15 | 0.04 |
| STH MVRV | 0.56 | 0.50 | 0.37 | 1.00 | 0.58 | 0.20 | 0.35 | 0.11 | 0.27 | 0.26 | 0.42 | -0.01 | 0.44 |
| Puell Multiple | 0.57 | 0.59 | 0.44 | 0.58 | 1.00 | 0.29 | 0.29 | -0.02 | 0.39 | 0.29 | 0.36 | 0.06 | 0.52 |
| Hash Ribbon | 0.24 | 0.21 | 0.19 | 0.20 | 0.29 | 1.00 | 0.20 | 0.01 | 0.11 | 0.09 | 0.20 | 0.02 | 0.39 |
| Address Growth | 0.28 | 0.22 | 0.24 | 0.35 | 0.29 | 0.20 | 1.00 | 0.15 | 0.02 | 0.01 | 0.18 | -0.00 | 0.25 |
| HODL 1Y+ | -0.15 | -0.18 | -0.20 | 0.11 | -0.02 | 0.01 | 0.15 | 1.00 | -0.60 | -0.39 | 0.11 | -0.35 | 0.22 |
| Reserve Risk | 0.56 | 0.58 | 0.57 | 0.27 | 0.39 | 0.11 | 0.02 | -0.60 | 1.00 | 0.66 | 0.42 | 0.20 | 0.38 |
| RHODL Ratio | 0.60 | 0.66 | 0.69 | 0.26 | 0.29 | 0.09 | 0.01 | -0.39 | 0.66 | 1.00 | 0.26 | 0.04 | 0.12 |
| ETF Net Flow | 0.47 | 0.48 | 0.23 | 0.42 | 0.36 | 0.20 | 0.18 | 0.11 | 0.42 | 0.26 | 1.00 | -0.08 | 0.28 |
| MSTR Holdings Δ | 0.10 | 0.05 | 0.15 | -0.01 | 0.06 | 0.02 | -0.00 | -0.35 | 0.20 | 0.04 | -0.08 | 1.00 | 0.14 |
| Coinbase Premium | 0.36 | 0.36 | 0.04 | 0.44 | 0.52 | 0.39 | 0.25 | 0.22 | 0.38 | 0.12 | 0.28 | 0.14 | 1.00 |

### Interchangeable groups (corr > 0.80)

- MVRV-Z / NUPL: 0.88

## 6. Suggested Phase C slate

| Indicator/group | Side | Decision | Rationale |
| --- | --- | --- | --- |
| STH MVRV | Momentum | Include | Best cycle-robust result: +10.6% full-sample alpha and 4/4 positive cycles. |
| RHODL Ratio | Momentum | Include | +9.1% full-sample alpha, 4/4 positive cycles, low flip rate; distinct enough from STH MVRV. |
| Puell Multiple | Momentum | Include | Modest full-sample alpha but 3/4 positive cycles and a miner-revenue lens not captured by pure valuation. |
| MVRV-Z | Momentum | Include/benchmark | Target-slate core metric and positive full-sample alpha, but cycle-fragile and colinear with NUPL; use one of MVRV-Z/NUPL, not both. |
| ETF Net Flow | Stress/flow | Include, with caution | Best full-sample alpha but only ETF-era coverage; still the cleanest available flow/stress input. |
| Coinbase Premium | Stress | Include only as short-coverage stress proxy | Full-sample result is negative, but source is in the target slate and 2025-now is positive; use cautiously until funding/exchange-flow data exists. |
| Hash Ribbon | Momentum | Secondary/watch | Low colinearity and canonical rule, but standalone alpha is negative overall and post-2017 only. |
| NUPL | Momentum | Exclude/secondary | Positive alpha, but it is the largest colinearity pair with MVRV-Z (0.88); keep as alternate valuation representative. |
| Address Growth | Momentum | Exclude for now | Non-colinear, but standalone alpha is materially negative and cycle-fragile under the uniform z-score rule. |
| HODL 1Y+ | Momentum | Exclude | Strongly negative full-sample alpha under the canonical/uniform rule despite low flip rate. |
| LTH MVRV | Momentum | Exclude/secondary | Negative full-sample alpha and overlaps the valuation cluster. |
| Reserve Risk | Momentum | Exclude pending sign review | Negative standalone result; literature sign may be contested/inverted, but Phase B did not tune it. |
| MSTR Holdings Δ | Flow | Exclude for composite core | Sparse step-function signal with short coverage and slightly negative standalone alpha. |

Recommended Phase C starting slate: **STH MVRV, RHODL Ratio, Puell Multiple, MVRV-Z (or NUPL as alternate), ETF Net Flow, Coinbase Premium**; keep **Hash Ribbon** as a low-colinearity watch-list candidate if Phase C wants a seventh input. Do not include both MVRV-Z and NUPL in the first composite unless the goal is deliberate valuation smoothing.

## 7. Source-expansion candidates

- **Funding rate:** missing from the current merged frame. Add Binance futures funding history, Coinglass, or another derivatives source in a later source-expansion phase.
- **SOPR:** target momentum input is not currently fetched. If BMP exposes SOPR under the existing key, it is the lowest-friction addition; otherwise use Glassnode/CryptoQuant-style spent-output data.
- **Exchange net flow:** absent from current sources. Likely requires Glassnode/CryptoQuant/BMP exchange-flow coverage; do not infer it from current exchange price feeds.
- **Longer Coinbase premium history:** current Binance spot close pull only gives ~1000 days, truncating the spread. A paginated Binance history fetch would extend coverage without changing the source family.

## 8. Five-line summary inputs

- Indicators measured: **13** standalone binary signals.
- Top 3 by full-sample alpha: **ETF Net Flow (+12.4%), STH MVRV (+10.6%), RHODL Ratio (+9.1%)**.
- Top 3 most cycle-robust: **STH MVRV (4/4 positive cycles, avg +10.9%), RHODL Ratio (4/4 positive cycles, avg +10.3%), Puell Multiple (3/4 positive cycles, avg +5.3%)**.
- Biggest colinearity finding: **MVRV-Z / NUPL at 0.88 corr**.
- Biggest data gap: **funding rate** is missing from the current merged frame; SOPR and exchange net flow are also absent.
