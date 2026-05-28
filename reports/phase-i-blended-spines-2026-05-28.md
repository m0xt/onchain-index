# Phase I blended-spine audit — 2026-05-28

Data snapshot: cached Phase A frame, `5259` daily rows, `2012-01-01→2026-05-26`. Yahoo research closes came from the existing Phase H `.cache/research/yahoo_daily_closes.pkl` cache for `BTC-USD`, `^IXIC`, and `^GSPC`; this run did not require a fresh Yahoo fetch. This dispatch changed no production data fetch, composite, threshold, sizing, dashboard, or macro-framework code. Structured output: `.cache/optim/phase_i.json`.

## 1. Methodology

This is a fixed-candidate architecture audit, not threshold optimization. All eight Phase I candidates use the same symmetric valuation override as Phase G/H: if `z(valuation) > +2.0`, go `CASH`; if `z(valuation) < -2.0`, stay long; otherwise the candidate spine or conjunction rule drives the binary `STAY LONG`/`CASH` state. I1a/I1b test multi-timeframe BTC/equity relative-strength blends, averaging 30d, 90d, and 180d z-scores. I2a–I2d test z-scored rolling outperformance frequency. I3 averages holder behavior with the selected BTC/equity metric. I4 requires both holder behavior and the selected BTC/equity metric to be positive.

For I3/I4, the selected BTC/equity construction was **I2a — BTC/NASDAQ outperformance 90d**, chosen by highest full-sample alpha among I1/I2 (`-10.4%`). The headline OOS median was explicitly not used for that selection.

## 2. Per-candidate results

Annualized alpha vs BTC buy-and-hold; max drawdown is strategy max drawdown over the full sample. `Δ vs additive` compares against the current additive reference of `+18.1%` OOS median alpha; the switch hurdle is `+19.1%`.

| Candidate | Full alpha | 2014-2017 | 2018-2021 | 2022-2024 | 2025-now | OOS median | Δ vs additive | Max DD | Time in cash | Switches / cycle | Spine corr |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| I1a — BTC/NASDAQ RS blend | -24.0% | -245.7% | -12.2% | +6.9% | +22.3% | -2.7% | -20.8pp | -54.5% | 70.4% | 56.8 | 0.81 |
| I1b — BTC/SPX RS blend | -25.2% | -248.8% | -11.9% | +4.6% | +20.4% | -3.6% | -21.7pp | -53.9% | 69.6% | 64.8 | 0.81 |
| I2a — BTC/NASDAQ outperformance 90d | -10.4% | -88.1% | +13.7% | +14.4% | +5.6% | +9.6% | -8.5pp | -59.9% | 59.5% | 46.0 | 0.24 |
| I2b — BTC/SPX outperformance 90d | -14.3% | -83.8% | -5.7% | +16.9% | +11.2% | +2.7% | -15.4pp | -59.9% | 55.5% | 46.5 | 0.22 |
| I2c — BTC/NASDAQ outperformance 30d | -15.7% | -96.2% | +19.1% | -0.7% | +1.2% | +0.3% | -17.8pp | -59.9% | 55.8% | 83.2 | 0.14 |
| I2d — BTC/NASDAQ outperformance 180d | -22.0% | -79.8% | -32.7% | +24.1% | +13.1% | -9.8% | -27.9pp | -60.9% | 58.6% | 44.5 | 0.28 |
| I3 — holder + I2a — BTC/NASDAQ outperformance 90d | -15.5% | -42.1% | -10.3% | +23.7% | +7.2% | -1.6% | -19.7pp | -71.6% | 57.4% | 50.5 | 0.68 |
| I4 — holder AND I2a — BTC/NASDAQ outperformance 90d | -8.9% | -79.4% | +9.5% | +12.3% | +12.0% | +10.7% | -7.4pp | -43.8% | 73.4% | 39.5 | 0.61 |

## 3. Read-through

- The best Phase I candidate was **I4 — holder AND I2a — BTC/NASDAQ outperformance 90d**, at `+10.7%` OOS median cycle alpha. It still trailed the additive reference by `-7.4pp`, so it missed the `+19.1%` switch hurdle by a wide margin.
- The multi-timeframe relative-strength blends did not rescue Phase H. I1a/I1b finished at negative OOS median alpha, and their high correlation to the additive baseline (`~0.81`) suggests they still are not adding a clean independent spine.
- Outperformance frequency was a better BTC/equity transformation than magnitude-based relative strength. The selected I2a 90d NASDAQ frequency reached `+9.6%` OOS median, but its full-sample alpha was still negative and it remained `-8.5pp` below additive.
- The composite I3 failed because averaging holder behavior with I2a diluted the useful holder signal and worsened drawdown. The conjunction I4 improved drawdown and switching, but it sat in cash about three-quarters of the time and gave up too much upside.
- No candidate was within `0.5pp` of the additive baseline, so this does not qualify as `promising-but-needs-more` under the task rule.

## 4. Concrete recommendation

Recommendation: **keep-additive** — no Phase I candidate cleared the `+19.1%` switch hurdle, and the best candidate was still `-7.4pp` behind the current `+18.1%` additive OOS reference. Keep `MROI = z(valuation) + z(holder_behavior)` and the existing binary `MROI > 0` decision rule. This closes the current spine-replacement research thread; the next product/docs pass should frame the architecture honestly as empirical-first additive evidence, not an MRMI-shaped spine+modifier system.

## 5. Downstream changes

No downstream production switch is recommended from this audit. Follow-up should be a docs/theory honesty update rather than productionizing Yahoo equity-index fetches, relative-strength composites, valuation overrides, or conjunction rules.
