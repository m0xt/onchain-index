# Phase J duration × magnitude spine audit — 2026-05-28

Data snapshot: cached Phase A frame, `5259` daily rows, `2012-01-01→2026-05-26`. Yahoo research closes used the Phase H `.cache/research/yahoo_daily_closes.pkl` cache for `BTC-USD` and `^IXIC`; no production data fetch, composite, threshold, sizing, dashboard, or macro-framework code was changed. Structured output: `.cache/optim/phase_j.json`.

## 1. Methodology

This is the final fixed-candidate architecture audit, not threshold optimization. Each candidate is a BTC/NASDAQ duration × magnitude spine built from Yahoo daily closes and z-scored over the full available sample, per the task brief. The audit tests three constructions in two modes:

- **PURE**: `STAY LONG if z(spine) > 0 else CASH`, with no valuation input.
- **WITH OVERRIDE**: the same spine rule, except the Phase G/H/I symmetric valuation override applies: if `z(valuation) > +2.0`, go `CASH`; if `z(valuation) < -2.0`, stay long.

J1 is the linear-regression slope of `log(BTC/^IXIC)` over rolling 252d windows. J2 is the 252d cumulative log relative return. J3 is the longest BTC-outperformance streak magnitude over rolling 180d windows, measured as max consecutive BTC-outperform-NASDAQ days × mean daily outperformance in that streak. The headline statistic mirrors prior phases: median annualized cycle alpha versus BTC buy-and-hold across the four `BTC_CYCLES`, with no in-sample candidate selection. The additive reference remains `+18.1%` OOS median alpha, and the switch hurdle remains `+19.1%`.

## 2. Per-candidate results

Annualized alpha vs BTC buy-and-hold; max drawdown is strategy max drawdown over the full sample. `Δ vs additive` compares against the current additive reference of `+18.1%` OOS median alpha.

| Candidate | Full alpha | 2014–2017 | 2018–2021 | 2022–2024 | 2025-now | OOS median | Δ vs additive | Max DD | Time in cash | Switches / cycle | Spine corr |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| J1 — trend slope PURE | -13.9% | -22.5% | -23.1% | -10.7% | +14.3% | -16.6% | -34.7pp | -72.2% | 52.2% | 3.5 | 0.50 |
| J1 — trend slope WITH OVERRIDE | -31.2% | -113.1% | -35.3% | -12.5% | +18.0% | -23.9% | -42.0pp | -70.3% | 61.1% | 24.5 | 0.50 |
| J2 — cumulative log relative return PURE | +11.3% | +1.8% | -3.9% | +15.2% | +46.3% | +8.5% | -9.6pp | -66.3% | 52.9% | 28.0 | 0.60 |
| J2 — cumulative log relative return WITH OVERRIDE | -10.5% | -94.9% | -18.4% | +8.1% | +51.1% | -5.2% | -23.3pp | -61.4% | 62.1% | 48.0 | 0.60 |
| J3 — streak × magnitude PURE | -11.8% | -96.2% | +4.5% | +0.4% | +10.6% | +2.4% | -15.7pp | -68.5% | 57.6% | 5.8 | 0.11 |
| J3 — streak × magnitude WITH OVERRIDE | -26.8% | -145.7% | -10.7% | +3.6% | +14.2% | -3.6% | -21.7pp | -63.8% | 64.9% | 23.8 | 0.11 |

## 3. Pure-vs-override comparison and read-through

| Spine | PURE OOS | WITH OVERRIDE OOS | Override − pure | Read-through |
| --- | ---: | ---: | ---: | --- |
| J1 — trend slope | -16.6% | -23.9% | -7.3pp | Override worsened an already weak spine; the trend slope missed the 2014–2024 cycle set and only helped in the partial 2025-now window. |
| J2 — cumulative log relative return | +8.5% | -5.2% | -13.6pp | J2 was the best Phase J result in pure mode, but it still trailed additive by `-9.6pp`; adding valuation override made it materially worse. |
| J3 — streak × magnitude | +2.4% | -3.6% | -6.0pp | The direct duration × magnitude expression had low correlation to additive (`0.11`) but did not translate into enough OOS alpha; valuation override again hurt. |

The load-bearing result is that **pure mode did not become competitive** and **valuation override did not rescue any spine**. This differs from the “valuation carries alpha” branch: here the override variants did not catch up to additive; they widened the gap for all three spines. The best candidate, **J2 PURE**, reached only `+8.5%` OOS median alpha, still `-9.6pp` behind additive and `-10.6pp` below the `+19.1%` switch hurdle.

## 4. Concrete recommendation

Recommendation: **architecture-search exhausted; commit to the empirical-first additive docs update**. This hits decision-tree branch 4: all six variants lose to the additive reference by at least `5pp` in both modes. No Phase J candidate clears `+19.1%`, no pure/override pair is within the 2pp “multi-dim composite worth productionizing” branch, and no override mode catches up enough to imply the valuation override should become the architecture.

Keep `MROI = z(valuation) + z(holder_behavior)` and the existing binary `MROI > 0` decision rule. The downstream docs/theory pass should say plainly that MROI is an empirical-first additive composite selected because repeated spine/modifier architecture searches failed OOS, not because BTC/equity spines or valuation overrides proved structurally superior.

## 5. Downstream

No production MROI/dashboard switch is recommended. Do not productionize Yahoo equity-index fetches, BTC/NASDAQ duration × magnitude spines, or the symmetric valuation override from this audit. The next dispatch should be a narrow `docs/theory.md` honesty update that closes the Phase G/H/I/J architecture-search thread and frames the additive composite as the evidence-backed design.
