# Phase P tier + confirmation final audit — 2026-05-28

Data snapshot: cached Phase A frame, `5259` daily rows, `2012-01-01→2026-05-26`. This audit reused only the production `holder_behavior_composite` spine from K1; no valuation, BTC/equity, production composite, threshold, sizing, dashboard, or macro-framework code was changed. Structured output: `.cache/optim/phase_p.json`.

## 1. Methodology

Phase P is the final iteration-phase check: combine Phase M's LONG/CAUTION/CASH band idea with Phase O's confirmation rule, plus Martin's requested asymmetric-threshold variants. All candidates are PURE MODE on the K1 spine: `z(holder_behavior)`.

- P1/P2/P3/P6 first map `z(holder)` into raw `STAY LONG` / `CAUTION` / `CASH` bands, then require N consecutive observations of a new proposed band before flipping.
- P1: ±0.3 band, N=3, CAUTION = 75% allocation.
- P2: ±0.5 band, N=3, CAUTION = 75% allocation.
- P3: ±0.3 band, N=5, CAUTION = 75% allocation.
- P6: ±0.3 band, N=3, CAUTION = 50% allocation.
- P4/P5 are binary asymmetric state machines with no CAUTION band: P4 enters LONG above `0` and exits CASH below `-0.3`; P5 enters LONG above `+0.3` and exits CASH below `0`.
- Standard walk-forward track: median annualized alpha versus BTC buy-and-hold across all four `BTC_CYCLES`, directly comparable with K1 at `+21.0%`.
- Strict IS-OOS holdout track: select the best candidate using only cycles 1–3 (`2014–2017`, `2018–2021`, `2022–2024`) by IS median alpha, then evaluate that selected candidate once on cycle 4 (`2025-now`).
- Decision hurdle: adopt only if a candidate keeps `>=+19.0%` alpha in both tracks and has `<20` switches/cycle. Prefer tier variants over asymmetric variants only if both qualify.

## 2. Side-by-side validation results

Annualized alpha vs BTC buy-and-hold. `Strict IS` is cycles 1–3 median alpha; `Strict OOS` is standalone 2025-now alpha. `Result` applies the dual-track + switch hurdle.

| Candidate | Standard WF OOS | Strict IS | Strict OOS cycle 4 | Switches / cycle | Δ vs K1 std | Result |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| P1 — 3-tier ±0.3 + N=3 | +13.4% | +15.6% | +11.2% | 34.5 | -7.6pp | No — std <19, strict OOS <19, switches ≥20 |
| P2 — 3-tier ±0.5 + N=3 | +5.1% | +7.2% | +0.8% | 30.8 | -15.9pp | No — std <19, strict OOS <19, switches ≥20 |
| P3 — 3-tier ±0.3 + N=5 | +15.6% | +10.2% | +21.2% | 28.5 | -5.4pp | No — std <19, switches ≥20 |
| P4 — asymmetric sticky LONG | +24.2% | +22.3% | +28.9% | 13.8 | +3.2pp | **Yes — sole qualifier** |
| P5 — asymmetric conservative entry | +14.0% | +9.6% | +18.5% | 15.2 | -7.0pp | No — std <19, strict OOS <19 |
| P6 — 3-tier ±0.3 + N=3, 50% CAUTION | +11.0% | +10.9% | +11.1% | 34.5 | -10.0pp | No — std <19, strict OOS <19, switches ≥20 |

## 3. Full per-candidate results

Max drawdown is strategy max drawdown over the full sample. Time in CAUTION is `0.0%` for binary asymmetric rows by construction.

| Candidate | Full alpha | 2014–2017 | 2018–2021 | 2022–2024 | 2025-now | Std OOS | Max DD | Time cash | Time CAUTION | Switches / cycle | Alpha / switch |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| P1 — 3-tier ±0.3 + N=3 | +14.1% | +15.6% | +23.6% | +5.3% | +11.2% | +13.4% | -60.1% | +33.3% | +26.2% | 34.5 | 0.39 |
| P2 — 3-tier ±0.5 + N=3 | +9.2% | +3.0% | +21.7% | +7.2% | +0.8% | +5.1% | -68.3% | +23.7% | +43.3% | 30.8 | 0.17 |
| P3 — 3-tier ±0.3 + N=5 | +14.0% | +10.2% | +21.1% | +7.0% | +21.2% | +15.6% | -65.0% | +33.0% | +26.5% | 28.5 | 0.55 |
| P4 — asymmetric sticky LONG | +20.7% | +22.3% | +8.3% | +26.1% | +28.9% | +24.2% | -65.1% | +41.1% | +0.0% | 13.8 | 1.76 |
| P5 — asymmetric conservative entry | +8.7% | +9.6% | +7.5% | +20.1% | +18.5% | +14.0% | -60.6% | +53.8% | +0.0% | 15.2 | 0.92 |
| P6 — 3-tier ±0.3 + N=3, 50% CAUTION | +10.2% | +10.9% | +17.1% | +9.1% | +11.1% | +11.0% | -55.3% | +33.3% | +26.2% | 34.5 | 0.32 |

## 4. K1 / O1 comparison

Computed K1 on the same snapshot remains `+21.0%` OOS median alpha (`+20.961%` unrounded), with `29.8` switches/cycle and alpha-per-switch of `0.70`. Phase O's best cadence row, O1 N=3, had `+17.2%` standard-WF alpha and `19.2` switches/cycle.

- P4 beats K1 on standard WF alpha (`+24.2%` vs `+21.0%`) and cuts switches materially (`13.8` vs `29.8`), but it is not a LONG/CAUTION/CASH rule and has a worse full-sample max drawdown (`-65.1%` vs K1 reference `-60.3%`).
- P3 is the only 3-tier row with a strong recent-cycle result (`+21.2%` strict OOS), but it misses standard WF alpha (`+15.6%`) and still switches too often (`28.5`/cycle).
- P1/P2/P6 do not solve the original problem: the CAUTION band still adds transitions, and confirmation does not bring switches below the `<20` hurdle.
- P5 solves cadence (`15.2` switches/cycle) but is too conservative; it misses both alpha tracks.

## 5. Strict-holdout selection

The strict IS selector and the standard WF track both picked P4.

| IS-selected candidate | IS median alpha | Cycle-4 alpha | Cycle-4 switches | Cycle-4 time in cash | Read-through |
| --- | ---: | ---: | ---: | ---: | --- |
| P4 — asymmetric sticky LONG | +22.3% | +28.9% | 11 | +53.7% | Validates in the held-out recent cycle and clears the switch hurdle. |

Because the strict holdout agrees with the all-cycle standard WF best, Phase P does not have the Phase O-style track-disagreement problem. The caveat is product vocabulary: the winner is asymmetric binary, not a tiered CAUTION rule.

## 6. Decision-tree outcome

Recommendation: **decision-tree branch 1 — adopt Phase P winner P4 if Martin accepts asymmetric binary wording**.

P4 is the sole candidate that maintains `>=+19.0%` in both tracks and `<20` switches/cycle:

- Standard WF OOS: `+24.2%`.
- Strict cycle-4 OOS: `+28.9%`.
- Switches/cycle: `13.8`.
- Alpha-per-switch: `1.76`, materially better than K1's `0.70`.

The tiered LONG/CAUTION/CASH variants do **not** qualify, so the preference for tier variants never activates. If Martin requires MRMI vocabulary parity, Phase P has no tiered winner and the product call remains K1 alpha purity versus O1 N=3 cadence. If asymmetric binary is acceptable, P4 is the validated Phase P winner.

## 7. Downstream

- Next dispatch: production migration decision. If adopting Phase P, implement P4 as `STAY LONG if z(holder) > 0; CASH if z(holder) < -0.3; otherwise keep prior state` with no valuation and no CAUTION tier.
- No further architecture exploration is recommended on this signal universe; Phase P was the final iteration audit.
