# Phase D structural audit — cross-dimension correlation + null benchmark — 2026-05-21

Data snapshot: cached Phase A frame, `5253` daily rows, `2012-01-01→2026-05-20`, `18` fetched columns. BTC returns use BMP `btc_price.pct_change()`. Composite inputs are the production functions in `src/onchain_index/composite.py`; no production code, dashboard code, constituents, weights, thresholds, or optimization logic were changed.

## 1. Why this audit exists

Bob raised two structural concerns after Martin asked for honest feedback:

1. **Cross-dimension correlation was untested.** The framework says Valuation and Holder Behavior are complementary dimensions, but Phase C never measured whether the dimension-level scores are actually different signals.
2. **The full composite might not earn its complexity.** Phase C showed the full composite beats BTC buy-and-hold, but it did not directly compare the tiered composite against the simplest viable tiered nulls: STH MVRV alone, Valuation-only, and Holder Behavior-only.

This audit does not re-litigate the other known limits: the 2021-top diagnostic is still partly post-hoc, DAT concentration is handled in a separate dashboard-rebuild dispatch, and the HODL holder rule remains a small-n empirical survivor until better holder-behavior data exists.

## 2. Audit A — Cross-dimension correlation

### Methodology

Measured the production dimension-level series directly:

- `valuation_composite(data)` — equal-weighted mean of lagged 504d z-scores for STH MVRV, RHODL Ratio, Puell Multiple, and MVRV-Z.
- `holder_behavior_composite(data)` — equal-weighted mean of available holder-behavior cohorts: on-chain HODL 1Y+ 30d-change, corporate DAT, ETF flow, and the all-NaN exchange-flow placeholder.

Cross-checks:

- Pearson correlation across the full shared non-NaN coverage period.
- Rolling 504d Pearson correlation to see whether the relationship shifts across epochs.
- Pearson correlation between binary `score > 0` versions of the two dimensions, because the tiering rule is threshold-based and behaviorally cares about above/below-zero crossings.

### Results

Full shared dimension-level coverage: `2013-06-18→2026-05-20`, `n=4719`.

| Check | Correlation | Read |
| --- | ---: | --- |
| Full-sample dimension Pearson | `0.631` | 0.4–0.7 bucket: meaningful overlap, not fully independent. |
| Full-sample binary `>0` Pearson | `0.483` | Same bucket, weaker than raw z-score correlation but still materially overlapping. |

Rolling 504d dimension correlation:

| Window | Dates covered | Mean | Median | Min | Max | Latest |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Full rolling sample | 2014-11-03→2026-05-20 | `0.568` | `0.568` | `0.085` | `0.839` | `0.505` |
| 2012–2020 epoch | 2014-11-03→2020-08-09 | `0.608` | `0.583` | `0.340` | `0.839` | `0.556` |
| 2020–2024 epoch | 2020-08-10→2024-01-10 | `0.531` | `0.546` | `0.085` | `0.799` | `0.277` |
| 2024-onward epoch | 2024-01-11→2026-05-20 | `0.524` | `0.451` | `0.249` | `0.792` | `0.505` |

Rolling-regime share:

| Rolling correlation bucket | Share of rolling observations |
| --- | ---: |
| `< 0.4` | `15.7%` |
| `0.4–0.7` | `54.5%` |
| `> 0.7` | `29.9%` |

Binary `score > 0` correlations by epoch:

| Epoch | Correlation | n |
| --- | ---: | ---: |
| 2012–2020 | `0.538` | 2610 |
| 2020–2024 | `0.401` | 1249 |
| 2024-onward | `0.449` | 860 |

### Interpretation

The dimensions are **not independent**. Full-sample Pearson is `0.631`, and rolling correlation spends almost 30% of observed days above `0.7`. That means the dashboard should not market the two-dimension decomposition as two cleanly independent axes.

But the dimensions are also **not one signal in disguise**. The full-sample and binary correlations land in the 0.4–0.7 bucket, rolling correlation has meaningful low-correlation periods, and the latest rolling correlation is `0.505`. The honest framing is: **Valuation and Holder Behavior are partially overlapping cross-checks with some diagnostic value, not orthogonal dimensions.**

## 3. Audit B — Null benchmark

### Methodology

Used the existing `backtest_tiered_signal` / `walk_forward_tiered_by_cycle` harness from `src/onchain_index/backtest.py` with the same fixed tier thresholds and sizing map as Phase C:

```text
score < -1.0       → Cash   →   0%
-1.0 ≤ score < 0   → Trim   →  50%
 0 ≤ score < 1     → Sized  →  75%
score ≥ 1.0        → Strong → 100%
```

Compared four contenders:

1. **Full production composite** — `PI_score = Valuation + Holder Behavior`.
2. **STH MVRV alone** — lagged 504d z-score of `sth_mvrv`, tiered with the same `(-1, 0, +1)` thresholds.
3. **Valuation only** — production `valuation_composite(data)`, tiered directly.
4. **Holder Behavior only** — production `holder_behavior_composite(data)`, tiered directly.

The table reports annualized alpha versus BTC buy-and-hold. “Median cycle alpha” is the out-of-sample-style summary used in Phase D: median of the four cycle-window alphas.

### Results

| Contender | Full-sample alpha | Median cycle alpha | 2014–2017 | 2018–2021 | 2022–2024 | 2025-now |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Full composite | `+13.0%` | `+13.5%` | `+11.0%` | `+14.1%` | `+17.0%` | `+13.0%` |
| STH MVRV alone | `-1.8%` | `+3.0%` | `-13.7%` | `+7.7%` | `+0.7%` | `+5.3%` |
| Valuation only | `+3.8%` | `+5.0%` | `-0.6%` | `+2.2%` | `+12.0%` | `+7.8%` |
| Holder Behavior only | `+8.2%` | `+8.0%` | `+3.7%` | `+16.2%` | `+5.5%` | `+10.5%` |

Alpha gaps, using median cycle alpha:

| Gap | Difference |
| --- | ---: |
| Full composite minus STH MVRV alone | `+10.5pp` |
| Full composite minus Valuation-only | `+8.5pp` |
| Full composite minus Holder Behavior-only | `+5.5pp` |

Full-sample alpha gaps:

| Gap | Difference |
| --- | ---: |
| Full composite minus STH MVRV alone | `+14.9pp` |
| Full composite minus Valuation-only | `+9.3pp` |

### Interpretation

The null-benchmark concern does **not** undermine the full composite under the requested tiered-rule comparison. The full composite clears the parsimony bar by a wide margin:

- Versus STH MVRV alone: `+10.5pp` median cycle alpha, not a sub-1pp rounding-error gain.
- Versus Valuation-only: `+8.5pp` median cycle alpha, so the Holder Behavior dimension is earning its keep under this rule shape.
- Versus Holder Behavior-only: `+5.5pp` median cycle alpha, so Valuation is still adding useful information.

The one uncomfortable nuance is that Holder Behavior-only is the strongest single-dimension null here (`+8.0%` median cycle alpha) and even beats the full composite in `2018–2021` (`+16.2%` vs `+14.1%`). That does not argue for simplification, because it loses in the other three cycles and trails the full composite on median, but it does say the holder leg is not just a decorative confirmation layer.

## 4. What this changes

1. **Two-dimension independence claim should be weakened.** The framework should not say Valuation and Holder Behavior are meaningfully independent. The measured reality is moderate overlap: useful decomposition, not orthogonal axes.
2. **Full-composite complexity is justified by current evidence.** The production composite beats STH MVRV alone, Valuation-only, and Holder Behavior-only by more than the 1pp parsimony threshold on median cycle alpha.
3. **The dashboard decomposition still has value, but the claim is diagnostic rather than causal purity.** It can show whether valuation and holders agree or disagree; it should not imply the two numbers are statistically independent.
4. **Holder Behavior deserves respect, but also scrutiny.** It is empirically strong in this audit, yet still structurally fragile because the on-chain holder survivor was discovered through small-n sign testing and the post-2024 cohort mix is concentrated.

Bottom line: **Do not simplify to STH MVRV alone or Valuation-only based on this audit. Keep the full composite for now, but stop overselling the two dimensions as independent.**

## 5. Recommended follow-ups

1. **Update dashboard/report wording:** replace “complementary/independent dimensions” language with “partially overlapping cross-checks.”
2. **Add a standing correlation panel to future dashboard iterations:** show latest rolling 504d Valuation-vs-Holder correlation and binary agreement rate so the decomposition claim stays falsifiable.
3. **Keep the full composite as production baseline:** the null benchmark does not justify simplification.
4. **Prioritize holder-data hardening:** exchange net flow remains the cleanest missing cohort, and better holder data would reduce dependence on the HODL 1Y+ change survivor plus DAT/ETF composition drift.
5. **Re-run this audit after the DAT concentration rebuild:** concentration changes should not alter historical composite math unless production math changes, but it may change the dashboard’s explanatory emphasis.