# Phase K pure-mode re-run — 2026-05-28

Data snapshot: cached Phase A frame, `5259` daily rows, `2012-01-01→2026-05-26`. Yahoo research closes reused the Phase H `.cache/research/yahoo_daily_closes.pkl` cache for `BTC-USD`, `^IXIC`, and `^GSPC`; no production data fetch, composite, threshold, sizing, dashboard, or macro-framework code was changed. Structured output: `.cache/optim/phase_k.json`.

## 1. Methodology

This audit re-runs the best Phase G/H/I candidates in **PURE MODE** after Martin caught that those phases were override-contaminated. Every Phase K candidate uses only holder behavior and/or BTC-vs-equity outperformance frequency. There is no valuation in any candidate spine and no valuation override in any candidate decision. The candidate rule is `STAY LONG if z(spine) > 0 else CASH`, except K5, which is the pure conjunction `STAY LONG if z(holder) > 0 AND z(best BTC/equity) > 0 else CASH`.

K4/K5 selected the BTC/equity metric by highest full-sample alpha among K2/K3, not by OOS median: **K2 — BTC/NASDAQ outperformance 90d PURE** (`btc_nasdaq_outperf_freq_z_90d`), with full-sample alpha `+2.5%` and OOS median alpha `+9.6%`. K2 and K3's 90d BTC/NASDAQ rows intentionally share the same underlying spine because the brief counted K2 as the original Phase I2a re-test and K3 as the broad outperformance-frequency sensitivity grid.

The headline statistic mirrors prior phases: median annualized cycle alpha versus BTC buy-and-hold across the four `BTC_CYCLES`. The current additive reference remains `+18.1%` OOS median alpha; the switch hurdle is `+19.1%`.

## 2. Per-candidate results

Annualized alpha vs BTC buy-and-hold; max drawdown is strategy max drawdown over the full sample. `Δ vs additive` compares against the current additive reference of `+18.1%` OOS median alpha.

| Candidate | Full alpha | 2014–2017 | 2018–2021 | 2022–2024 | 2025-now | OOS median | Δ vs additive | Max DD | Time in cash | Switches / cycle | Spine corr |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| K1 — holder behavior PURE | +20.5% | +19.4% | +14.3% | +22.5% | +26.9% | +21.0% | +2.9pp | -60.3% | +47.1% | 29.8 | 0.9 |
| K2 — BTC/NASDAQ outperformance 90d PURE | +2.5% | -62.8% | +32.6% | +16.8% | +2.4% | +9.6% | -8.5pp | -62.8% | +51.3% | 25.0 | 0.2 |
| K3 — BTC/NASDAQ outperformance 30d PURE | -6.4% | -64.4% | +21.9% | +0.4% | -1.9% | -0.7% | -18.8pp | -59.9% | +47.5% | 68.2 | 0.1 |
| K3 — BTC/NASDAQ outperformance 90d PURE | +2.5% | -62.8% | +32.6% | +16.8% | +2.4% | +9.6% | -8.5pp | -62.8% | +51.3% | 25.0 | 0.2 |
| K3 — BTC/NASDAQ outperformance 180d PURE | -9.9% | -49.6% | -20.2% | +25.2% | +9.6% | -5.3% | -23.4pp | -64.6% | +50.4% | 22.0 | 0.3 |
| K3 — BTC/SPX outperformance 90d PURE | -6.0% | -74.0% | +10.5% | +19.3% | +7.7% | +9.1% | -9.0pp | -59.9% | +47.8% | 25.5 | 0.2 |
| K4 — holder + K2 — BTC/NASDAQ outperformance 90d PURE | +8.3% | -5.8% | +5.3% | +29.7% | +3.9% | +4.6% | -13.5pp | -74.5% | +48.3% | 26.5 | 0.7 |
| K5 — holder AND K2 — BTC/NASDAQ outperformance 90d PURE | +5.2% | -49.8% | +27.8% | +16.2% | +8.5% | +12.3% | -5.8pp | -51.1% | +65.7% | 23.5 | 0.6 |

## 3. Pure-vs-prior-override comparison

This is the load-bearing Phase K table: it compares each pure-mode re-run against the corresponding Phase G/H/I result that used the valuation override.

| Phase K candidate | Prior override source | PURE OOS | Prior override OOS | Pure − override | PURE Δ vs additive | Read-through |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| K1 — holder behavior PURE | Phase H1 / Phase G symmetric T=2 / `h1_holder_behavior` | +21.0% | +8.0% | +13.0pp | +2.9pp | Removing the valuation override transformed holder-only from a weak `+8.0%` override result into the only switch-clearing result. |
| K2 — BTC/NASDAQ outperformance 90d PURE | Phase I2a / `i2a_btc_nasdaq_outperf_90d` | +9.6% | +9.6% | -0.0pp | -8.5pp | Override was effectively neutral for the 90d BTC/NASDAQ frequency spine; the spine itself still trails additive by `-8.5pp`. |
| K3 — BTC/NASDAQ outperformance 30d PURE | Phase I2c / `i2c_btc_nasdaq_outperf_30d` | -0.7% | +0.3% | -1.0pp | -18.8pp | Pure mode was slightly worse; short-window frequency remains non-competitive. |
| K3 — BTC/NASDAQ outperformance 90d PURE | Phase I2a / `i2a_btc_nasdaq_outperf_90d` | +9.6% | +9.6% | -0.0pp | -8.5pp | Override was effectively neutral for the 90d BTC/NASDAQ frequency spine; the spine itself still trails additive by `-8.5pp`. |
| K3 — BTC/NASDAQ outperformance 180d PURE | Phase I2d / `i2d_btc_nasdaq_outperf_180d` | -5.3% | -9.8% | +4.5pp | -23.4pp | Pure mode improved materially versus override but still landed deeply below additive. |
| K3 — BTC/SPX outperformance 90d PURE | Phase I2b / `i2b_btc_spx_outperf_90d` | +9.1% | +2.7% | +6.4pp | -9.0pp | Pure mode improved BTC/SPX frequency by `+6.4pp`, but not enough to approach the switch hurdle. |
| K4 — holder + K2 — BTC/NASDAQ outperformance 90d PURE | Phase I3 / `i3_holder_best_btc_equity_composite` | +4.6% | -1.6% | +6.2pp | -13.5pp | Removing override helped the blended composite, but averaging holder with BTC/equity diluted the now-obvious holder-only signal. |
| K5 — holder AND K2 — BTC/NASDAQ outperformance 90d PURE | Phase I4 / `i4_holder_best_btc_equity_conjunction` | +12.3% | +10.7% | +1.6pp | -5.8pp | Pure conjunction improved versus override and lowered drawdown, but still trailed additive by `-5.8pp`. |

## 4. Read-through

- **K1 holder-only pure is the decisive result**: `+21.0%` OOS median alpha, `+2.9pp` above the additive reference and `+1.9pp` above the `+19.1%` switch hurdle.
- The contamination effect was concentrated in holder-only: Phase H/G holder-with-override was only `+8.0%`, so the override cost was `-13.0pp` relative to pure holder behavior.
- BTC/equity outperformance frequency did not become the architecture. K2/K3 90d BTC/NASDAQ reached `+9.6%`, K3 90d BTC/SPX reached `+9.1%`, and the other K3 windows were weaker.
- K4/K5 confirm that adding BTC/equity to holder behavior is not helpful under this construction. K4 fell to `+4.6%`; K5 improved drawdown to `-51.1%` and reached `+12.3%`, but still gave up `-8.6pp` versus K1 and `-5.8pp` versus additive.
- The additive reference computed on this snapshot is `+18.1%` OOS median alpha with full-sample max drawdown `-65.9%`; K1 pure has a smaller full-sample max drawdown (`-60.3%`) and higher OOS alpha.

## 5. Concrete recommendation

Recommendation: **decision-tree branch 1 — switch**. Switch to K1 — holder behavior PURE: it reached 21.0% OOS median alpha, clearing the +19.1% switch hurdle. Within this dispatch, production code changes were explicitly out of scope, so the follow-on should be a narrow production switch proposal/implementation for a holder-behavior-only pure rule, plus the docs/theory update explaining why Phase K overturned the prior keep-additive recommendation.

Do **not** productionize Yahoo equity-index fetches or BTC/equity spines from this audit: every BTC/equity-only, blended, and conjunction candidate still lost to the additive reference by more than 1pp. The production-relevant finding is the removal of valuation override from holder behavior, not the equity-relative family.

## 6. Downstream

- Next dispatch: implement/review the production implications of `STAY LONG if z(holder_behavior) > 0 else CASH`, including tests, dashboard/docs wording, and any decision-rule migration needed.
- Preserve the Phase K report table when updating `docs/theory.md`; it is the evidence that the earlier Phase G/H/I override-contaminated reads understated holder-only performance.
