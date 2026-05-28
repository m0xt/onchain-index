# Phase M investor-grade K1 stickiness — 2026-05-28

Data snapshot: cached Phase A frame, `5259` daily rows, `2012-01-01→2026-05-26`. This audit reused only the production `holder_behavior_composite` spine from K1; no valuation, BTC/equity, production composite, threshold, sizing, dashboard, or macro-framework code was changed. Structured output: `.cache/optim/phase_m.json`.

## 1. Methodology

Phase K made **K1 — holder behavior PURE** the baseline at `+21.0%` OOS median cycle alpha, but its binary zero-crossing rule flips `29.8` times per cycle. Phase M tests seven stickiness variants that keep the K1 holder-only PURE spine and change only the decision rule.

- M1a/M1b/M1c use stateful hysteresis: enter `STAY LONG` above `+T`, exit to `CASH` below `-T`, and hold the current state inside the band. The initial valid state follows the sign of `z(holder)`.
- M2a/M2b/M2c use a stateless 3-tier rule: `STAY LONG` above `+T`, `CASH` below `-T`, and `CAUTION` at 75% allocation inside the band.
- M3 applies a 30-day EMA to `z(holder)` and then uses the K1 zero threshold.

The headline statistic mirrors prior phases: median annualized cycle alpha versus BTC buy-and-hold across the four `BTC_CYCLES`. The investor-grade hurdle is **OOS median alpha ≥ +20.0%** and **<15 switches/cycle**. If multiple rows qualify, the decision tree prefers M2 3-tier rows for product/UX parity with MRMI's LONG/CAUTION/CASH vocabulary.

## 2. Headline results

Annualized alpha vs BTC buy-and-hold. `Δ vs K1` compares against the fixed `+21.0%` K1 reference. `Alpha / switch` is OOS median alpha divided by average switches/cycle.

| Candidate | OOS median | Switches / cycle | Δ vs K1 | Alpha / switch | Qualifies? |
| --- | ---: | ---: | ---: | ---: | --- |
| M1a — hysteresis ±0.3 | +14.1% | 11.2 | -6.9pp | 1.25 | No — alpha below +20.0% |
| M1b — hysteresis ±0.5 | +6.3% | 9.8 | -14.7pp | 0.65 | No — alpha below +20.0% |
| M1c — hysteresis ±0.7 | +3.5% | 5.8 | -17.5pp | 0.61 | No — alpha below +20.0% |
| M2a — 3-tier ±0.3 | +19.0% | 53.2 | -2.0pp | 0.36 | No — alpha below +20.0% and switches too high |
| M2b — 3-tier ±0.5 | +14.7% | 55.5 | -6.3pp | 0.26 | No — alpha below +20.0% and switches too high |
| M2c — 3-tier ±0.7 | +8.4% | 43.2 | -12.6pp | 0.20 | No — alpha below +20.0% and switches too high |
| M3 — 30d EMA holder threshold | +8.3% | 12.8 | -12.7pp | 0.65 | No — alpha below +20.0% |

## 3. Full per-candidate results

Max drawdown is strategy max drawdown over the full sample. Time in cash is the share of valid scored days assigned to `CASH`; M2 rows also spend time in `CAUTION`, so cash share is not the full defensive-allocation share.

| Candidate | Full alpha | 2014–2017 | 2018–2021 | 2022–2024 | 2025-now | OOS median | Max DD | Time in cash | Switches / cycle |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| M1a — hysteresis ±0.3 | +15.5% | +13.1% | +9.6% | +22.3% | +15.0% | +14.1% | -65.1% | +44.7% | 11.2 |
| M1b — hysteresis ±0.5 | +9.9% | +11.0% | +1.7% | +23.3% | +1.2% | +6.3% | -65.1% | +47.3% | 9.8 |
| M1c — hysteresis ±0.7 | +4.8% | +4.0% | -8.3% | +24.2% | +3.0% | +3.5% | -77.8% | +43.9% | 5.8 |
| M2a — 3-tier ±0.3 | +17.0% | +8.5% | +22.8% | +15.1% | +23.3% | +19.0% | -64.6% | +33.1% | 53.2 |
| M2b — 3-tier ±0.5 | +13.3% | +2.8% | +19.8% | +16.7% | +12.7% | +14.7% | -70.3% | +24.0% | 55.5 |
| M2c — 3-tier ±0.7 | +11.0% | +6.5% | +21.4% | +7.4% | +9.5% | +8.4% | -71.7% | +17.7% | 43.2 |
| M3 — 30d EMA holder threshold | +12.4% | +14.6% | +0.3% | +30.9% | +2.1% | +8.3% | -69.6% | +46.3% | 12.8 |

## 4. K1 comparison

Computed K1 on the same snapshot remains `+21.0%` OOS median alpha (`+20.961%` unrounded), with `29.8` switches/cycle and alpha-per-switch of `0.70`.

- No Phase M candidate cleared both the `+20.0%` OOS alpha floor and `<15` switches/cycle.
- Hysteresis solved cadence but gave up too much alpha. M1a was the least costly hysteresis row at `+14.1%` OOS and `11.2` switches/cycle, still `-6.9pp` below K1.
- The 3-tier band preserved the most alpha only at the tightest threshold. M2a reached `+19.0%`, but it still missed the alpha floor and increased switching to `53.2` transitions/cycle because CAUTION creates an additional transition state around the zero band.
- EMA smoothing hit investor cadence (`12.8` switches/cycle) but not performance (`+8.3%` OOS), with the 2018–2021 and 2025-now cycles carrying most of the cost.

## 5. Pareto frontier

No row qualifies, so the useful output is the alpha-vs-switches frontier:

| Candidate | OOS median | Switches / cycle | Alpha / switch | Read-through |
| --- | ---: | ---: | ---: | --- |
| M1c — hysteresis ±0.7 | +3.5% | 5.8 | 0.61 | Lowest cadence, unacceptable alpha. |
| M1b — hysteresis ±0.5 | +6.3% | 9.8 | 0.65 | Still investor cadence, still far below K1. |
| M1a — hysteresis ±0.3 | +14.1% | 11.2 | 1.25 | Best alpha-per-switch, but misses the alpha floor by `5.9pp`. |
| M2a — 3-tier ±0.3 | +19.0% | 53.2 | 0.36 | Closest to K1 alpha, but materially worse cadence than K1. |

## 6. Concrete recommendation

Recommendation: **decision-tree branch 3 — no qualifier / surface Pareto trade-off**. Do not productionize any Phase M stickiness variant as tested. The variants that solve investor cadence lose too much annualized OOS alpha, while the only row near the alpha floor (M2a) switches even more often than K1.

The next production decision should not be a simple hysteresis, 3-tier band, or 30d EMA smoothing change. If Martin still wants investor-grade cadence, the next research branch should test a different stickiness mechanism with a stronger prior, or accept an explicit alpha-for-cadence trade-off rather than treating it as negligible.

## 7. Downstream

- Next dispatch: Martin review of the Phase M trade-off; no production MROI/dashboard changes made.
- Preserve the Phase K/L/M sequence in `docs/theory.md`: K1 wins on alpha, Phase L confirms no BTC/equity rescue, and Phase M shows simple stickiness mechanisms do not retain K1's alpha at investor cadence.
