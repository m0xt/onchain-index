# Phase L holder × BTC/equity pure-mode combinations — 2026-05-28

Data snapshot: cached Phase A frame, `5259` daily rows, `2012-01-01→2026-05-26`. Yahoo research closes reused the Phase H `.cache/research/yahoo_daily_closes.pkl` cache for `BTC-USD`, `^IXIC`, and `^GSPC`; no production data fetch, composite, threshold, sizing, dashboard, or macro-framework code was changed. Structured output: `.cache/optim/phase_l.json`.

## 1. Methodology

Phase K made **K1 — holder behavior PURE** the new baseline at `+21.0%` OOS median cycle alpha. Phase L tests the remaining untried holder × BTC/equity combinations in **PURE MODE**: no valuation input and no valuation override anywhere. The switch hurdle is K1 + 1pp, or `+22.0%` OOS median alpha.

The BTC/equity input is K2's BTC/NASDAQ 90d outperformance-frequency z-score unless the candidate explicitly specifies another window/index. L1a/L1b/L1c use holder-heavy weighted averages; L2 uses BTC/equity only as a negative tail-risk cash filter; L3 uses BTC/equity only when holder behavior is near zero; L4a/L4b/L4c are holder AND BTC/equity conjunctions.

The headline statistic mirrors prior phases: median annualized cycle alpha versus BTC buy-and-hold across the four `BTC_CYCLES`. Every row below includes `Δ vs K1`, comparing the candidate OOS median alpha to the fixed `+21.0%` K1 reference.

## 2. Per-candidate results

Annualized alpha vs BTC buy-and-hold; max drawdown is strategy max drawdown over the full sample.

| Candidate | Full alpha | 2014–2017 | 2018–2021 | 2022–2024 | 2025-now | OOS median | Δ vs K1 | Max DD | Time in cash | Switches / cycle | BTC/equity corr |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| L1a — weighted 0.7/0.3 | +10.9% | -9.6% | +10.8% | +30.8% | +1.4% | +6.1% | -14.9pp | -61.2% | +45.6% | 29.0 | 0.2 |
| L1b — weighted 0.8/0.2 | +14.8% | -5.5% | +21.0% | +25.9% | +4.6% | +12.8% | -8.2pp | -64.1% | +45.1% | 26.2 | 0.2 |
| L1c — weighted 0.9/0.1 | +12.6% | -6.5% | +15.4% | +14.4% | +23.2% | +14.9% | -6.1pp | -62.0% | +45.7% | 29.8 | 0.2 |
| L2 — asymmetric safety filter | +20.0% | +16.9% | +15.8% | +21.9% | +25.5% | +19.4% | -1.6pp | -60.3% | +49.9% | 37.8 | 0.2 |
| L3 — hierarchical tiebreaker | +14.2% | -4.1% | +23.6% | +20.5% | +3.0% | +11.7% | -9.3pp | -62.4% | +47.8% | 30.8 | 0.2 |
| L4a — conjunction 30d NASDAQ | -1.6% | -51.9% | +5.5% | +19.4% | +11.1% | +8.3% | -12.7pp | -39.2% | +67.1% | 48.0 | 0.1 |
| L4b — conjunction 180d NASDAQ | -4.1% | -38.7% | -6.2% | +13.2% | +13.4% | +3.5% | -17.5pp | -42.0% | +65.1% | 19.5 | 0.2 |
| L4c — conjunction 90d SPX | -3.7% | -65.1% | +13.7% | +13.3% | +10.8% | +12.0% | -9.0pp | -56.8% | +65.4% | 23.0 | 0.1 |

## 3. K1 comparison

Computed K1 on the same snapshot remains `+21.0%` OOS median alpha (`+20.961%` unrounded), with full-sample alpha `+20.5%`, max drawdown `-60.3%`, and `47.1%` time in cash.

- No Phase L candidate cleared the `+22.0%` switch hurdle.
- No candidate finished within 0.5pp of K1 while also lowering max drawdown. L2's max drawdown was fractionally less severe than K1 (`-60.32%` vs `-60.34%`), but its OOS alpha was `-1.6pp` below K1, outside the diversification-benefit band.
- All eight candidates lost to K1 by at least 1pp. The best Phase L row was L2 at `+19.4%`, still `-1.6pp` versus K1.

## 4. Read-through

- **BTC/equity still dilutes holder behavior.** Even a 90% holder / 10% BTC-equity weighted rule fell to `+14.9%` OOS, `-6.1pp` versus K1.
- **Tail-risk filtering is the least harmful combination**, but it still fails the decision tree. L2 preserved much of K1's profile at `+19.4%`, but gave up `-1.6pp` of OOS alpha and increased switching.
- **Conjunctions improve drawdown by spending more time in cash**, but the opportunity cost is too high. L4a/L4b/L4c had lower drawdowns than K1, but their OOS alpha ranged only `+3.5%` to `+12.0%`.
- **The Phase K implication survives Martin's catch.** The untested combinations do not rescue BTC/equity as a useful production input.

## 5. Concrete recommendation

Recommendation: **decision-tree branch 3 — K1 wins decisively**. All Phase L candidates lose to K1 by at least 1pp, so the next dispatch should productionize the K1 holder-only pure decision rule (`STAY LONG if z(holder_behavior) > 0 else CASH`) and rewrite `docs/theory.md` / dashboard wording around the empirical holder-only result.

Do **not** productionize Yahoo equity-index fetches or BTC/equity spines from Phase L. They were useful as research controls, but the production-relevant result is that holder behavior alone remains stronger than every tested holder × BTC/equity combination.

## 6. Downstream

- Next dispatch: narrow production migration to K1 holder-only pure, including tests, dashboard/docs wording, and decision-rule updates.
- Preserve the Phase K and Phase L tables in `docs/theory.md` as the evidence chain: Phase K found K1; Phase L tested Martin's missing combinations and confirmed K1 remains the migration target.
