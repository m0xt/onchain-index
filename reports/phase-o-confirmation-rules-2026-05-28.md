# Phase O K1 confirmation rules — 2026-05-28

Data snapshot: cached Phase A frame, `5259` daily rows, `2012-01-01→2026-05-26`. This audit reused only the production `holder_behavior_composite` spine from K1; no valuation, BTC/equity, production composite, threshold, sizing, dashboard, or macro-framework code was changed. Structured output: `.cache/optim/phase_o.json`.

## 1. Methodology

Phase O tests whether simple confirmation rules can remove K1's zero-crossing cluster noise without losing real regime changes. K1 remains PURE MODE: `STAY LONG if z(holder_behavior) > 0 else CASH`.

- O1/O2/O3/O4/O5 require 3/5/7/10/14 consecutive opposite-sign valid observations before flipping regime.
- The state machine tracks `current_regime` and `pending_flip_count`; same-sign observations reset the pending count, opposite-sign observations increment it, and the regime flips only when `pending_flip_count >= N`.
- Standard walk-forward track: median annualized alpha versus BTC buy-and-hold across all four `BTC_CYCLES`, directly comparable with K1 at `+21.0%`.
- Strict IS-OOS holdout track: select N using only cycles 1–3 (`2014–2017`, `2018–2021`, `2022–2024`) by IS median alpha, then evaluate that selected N once on cycle 4 (`2025-now`).
- Decision hurdle: adopt only if a candidate keeps `>=+20.0%` alpha in both tracks and has `<20` switches/cycle; if multiple qualify, prefer lower N.

## 2. Side-by-side validation results

Annualized alpha vs BTC buy-and-hold. `Strict IS` is cycles 1–3 median alpha; `Strict OOS` is standalone 2025-now alpha. `Result` applies the dual-track + switch hurdle.

| Candidate | Standard WF OOS | Strict IS | Strict OOS cycle 4 | Switches / cycle | Δ vs K1 std | Result |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| O1 — N=3 confirmation | +17.2% | +14.2% | +20.1% | 19.2 | -3.8pp | No — std <20 |
| O2 — N=5 confirmation | +13.9% | +8.8% | +19.1% | 15.8 | -7.1pp | No — std <20, strict OOS <20 |
| O3 — N=7 confirmation | +13.6% | +13.5% | +13.7% | 13.5 | -7.4pp | No — std <20, strict OOS <20 |
| O4 — N=10 confirmation | +4.5% | +7.3% | +1.7% | 12.0 | -16.5pp | No — std <20, strict OOS <20 |
| O5 — N=14 confirmation | +10.0% | +14.6% | +5.4% | 11.5 | -11.0pp | No — std <20, strict OOS <20 |

## 3. Full per-candidate results

Max drawdown is strategy max drawdown over the full sample. Time in cash is the share of valid scored days assigned to `CASH`.

| Candidate | Full alpha | 2014–2017 | 2018–2021 | 2022–2024 | 2025-now | Std OOS | Max DD | Time in cash | Switches / cycle | Alpha / switch |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| O1 — N=3 confirmation | +15.4% | +14.2% | +10.4% | +20.5% | +20.1% | +17.2% | -59.4% | +47.1% | 19.2 | 0.89 |
| O2 — N=5 confirmation | +11.4% | +8.8% | +4.9% | +26.9% | +19.1% | +13.9% | -62.4% | +46.8% | 15.8 | 0.88 |
| O3 — N=7 confirmation | +9.8% | +0.9% | +13.5% | +20.1% | +13.7% | +13.6% | -70.8% | +46.3% | 13.5 | 1.00 |
| O4 — N=10 confirmation | +2.8% | +7.3% | +0.8% | +17.8% | +1.7% | +4.5% | -65.2% | +46.3% | 12.0 | 0.37 |
| O5 — N=14 confirmation | +7.2% | +14.6% | +0.4% | +18.8% | +5.4% | +10.0% | -66.0% | +46.3% | 11.5 | 0.87 |

## 4. K1 comparison

Computed K1 on the same snapshot remains `+21.0%` OOS median alpha (`+20.961%` unrounded), with `29.8` switches/cycle and alpha-per-switch of `0.70`.

- O1 is the only row near the hurdle: it cuts switches from `29.8` to `19.2` and keeps cycle-4 alpha at `+20.1%`, but standard WF alpha falls to `+17.2%`.
- O2 also reaches investor cadence at `15.8` switches/cycle, but misses both alpha tracks (`+13.9%` standard WF and `+19.1%` strict OOS).
- O3/O4/O5 reduce cadence further, but the extra delay increasingly misses the 2025-now turns; strict OOS falls to `+13.7%`, `+1.7%`, and `+5.4%`.
- The strict IS selector picked O5 (`N=14`) from cycles 1–3 at `+14.6%` IS median, while the standard WF best was O1 (`N=3`) at `+17.2%`; the tracks therefore disagree.

## 5. Strict-holdout selection

| IS-selected N | IS median alpha | Cycle-4 alpha | Cycle-4 switches | Cycle-4 time in cash | Read-through |
| --- | ---: | ---: | ---: | ---: | --- |
| O5 — N=14 confirmation | +14.6% | +5.4% | 8 | +62.0% | Collapses below the +20.0% strict-OOS hurdle. |

Because Martin specifically asked for “more history but keep something for OOS,” this strict holdout is the conservative read. It says the best-looking IS confirmation lag does not generalize cleanly into the recent cycle.

## 6. Cycle-4 flip dates

No Phase O candidate qualifies, so there is no winning candidate. For sanity checking, dates below show the two relevant rows: standard-WF best O1 and strict-IS selected O5. `Pending start` is the first opposite-sign day; `Confirmed` is when the N-day rule actually flipped.

### O1 — N=3 confirmation

| Pending start | Confirmed | Flip | z(holder) on confirm |
| --- | --- | --- | ---: |
| 2025-01-17 | 2025-01-19 | STAY LONG → CASH | -0.147 |
| 2025-01-21 | 2025-01-23 | CASH → STAY LONG | +0.029 |
| 2025-02-20 | 2025-02-22 | STAY LONG → CASH | -0.174 |
| 2025-04-21 | 2025-04-23 | CASH → STAY LONG | +0.069 |
| 2025-06-12 | 2025-06-14 | STAY LONG → CASH | -0.080 |
| 2025-07-05 | 2025-07-07 | CASH → STAY LONG | +0.082 |
| 2025-08-11 | 2025-08-13 | STAY LONG → CASH | -0.022 |
| 2025-09-19 | 2025-09-21 | CASH → STAY LONG | +0.055 |
| 2025-09-27 | 2025-09-29 | STAY LONG → CASH | -0.189 |
| 2025-11-24 | 2025-11-26 | CASH → STAY LONG | +0.332 |
| 2025-12-23 | 2025-12-25 | STAY LONG → CASH | -0.640 |
| 2026-04-21 | 2026-04-23 | CASH → STAY LONG | +0.135 |
| 2026-05-21 | 2026-05-23 | STAY LONG → CASH | -0.539 |

### O5 — N=14 confirmation

| Pending start | Confirmed | Flip | z(holder) on confirm |
| --- | --- | --- | ---: |
| 2025-02-20 | 2025-03-05 | STAY LONG → CASH | -0.323 |
| 2025-05-06 | 2025-05-19 | CASH → STAY LONG | +0.517 |
| 2025-06-18 | 2025-07-01 | STAY LONG → CASH | -0.216 |
| 2025-07-05 | 2025-07-19 | CASH → STAY LONG | +0.409 |
| 2025-08-11 | 2025-08-24 | STAY LONG → CASH | -0.421 |
| 2025-11-24 | 2025-12-07 | CASH → STAY LONG | +0.223 |
| 2025-12-23 | 2026-01-05 | STAY LONG → CASH | -0.731 |
| 2026-04-21 | 2026-05-04 | CASH → STAY LONG | +0.477 |

## 7. Concrete recommendation

Recommendation: **decision-tree branch 4 — strict holdout collapse / flag overfitting risk**. Do not productionize a Phase O confirmation rule from this grid.

The confirmation rule does solve the stated cadence problem mechanically: O1 gets below `<20` switches/cycle, and larger N values reduce switching further. But the performance cost is not negligible. No candidate maintains `>=+20.0%` in both validation tracks, and the strict IS-selected N=14 row underperforms badly in 2025-now. Trust the strict holdout over the all-cycle standard-WF table.

## 8. Downstream

- Next dispatch: Martin review of the Phase O trade-off; no production MROI/dashboard changes made.
- If Martin still wants lower cadence, O1 (`N=3`) is the least-bad candidate to discuss because it preserves cycle-4 alpha and cuts switches below 20, but it should be treated as an explicit alpha-for-cadence trade-off, not as a validated improvement over K1.
