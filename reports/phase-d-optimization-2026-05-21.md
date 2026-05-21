# Phase D optimization research — 2026-05-21

Data snapshot: cached Phase A frame, `5253` daily rows, `2012-01-01→2026-05-20`, `18` fetched columns. This is research-only: production `src/onchain_index/composite.py` and the live dashboard remain on the equal-weight Phase C composite.

Structured optimizer output: `.cache/optim/step1.json`.

## 1. Methodology

Phase D uses optimization as a candidate generator, not as an auto-apply path.

- **Walk-forward design:** leave-one-cycle-out by BTC cycle. For each fold, train on the other three cycles, select the best candidate by training alpha vs BTC buy-and-hold, then test once on the held-out cycle.
- **Baseline bar:** compare directly against the Phase C equal-weight production baseline: `Valuation_z + HolderBehavior_z` with thresholds `(-1, 0, +1)` and sizing `0/50/75/100`.
- **Stopping rule:** if median out-of-sample alpha improvement is `< 2pp`, stop and keep equal-weight.
- **Perturbation procedure:** for Step 1, perturb each selected fold ratio by ±10%, re-test on the same held-out cycle, and report the largest absolute alpha movement.
- **Scale discipline:** cohort weights are normalized to sum to `2.0`, so changing the valuation/holder ratio does not accidentally retune the fixed threshold scale.

## 2. Step 1 — Cohort dimension weights

Grid: 12 raw valuation/holder combinations from `{0.5, 0.75, 1.0, 1.25, 1.5, 2.0}` and inverse. Duplicates are retained where the spec's inverse grid lands on the same effective ratio.

### Full grid diagnostics

These are diagnostics only; selection was not done on full-sample alpha.

| Candidate | Effective `w_v/w_h` | Normalized `w_v` | Normalized `w_h` | Full alpha | Median cycle alpha | Cycle alpha spread |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| raw_wv0.50_wh1.00 | 0.50 | 0.67 | 1.33 | +14.0% | +13.9% | +12.8% to +16.6% |
| raw_wv0.75_wh1.00 | 0.75 | 0.86 | 1.14 | +13.0% | +13.2% | +10.4% to +17.6% |
| raw_wv1.00_wh1.00a | 1.00 | 1.00 | 1.00 | +13.0% | +13.5% | +11.0% to +17.0% |
| raw_wv1.25_wh1.00 | 1.25 | 1.11 | 0.89 | +12.7% | +12.8% | +11.1% to +19.1% |
| raw_wv1.50_wh1.00 | 1.50 | 1.20 | 0.80 | +11.5% | +13.3% | +6.8% to +19.9% |
| raw_wv2.00_wh1.00 | 2.00 | 1.33 | 0.67 | +11.9% | +15.1% | +4.8% to +20.5% |
| raw_wv1.00_wh0.50 | 2.00 | 1.33 | 0.67 | +11.9% | +15.1% | +4.8% to +20.5% |
| raw_wv1.00_wh0.75 | 1.33 | 1.14 | 0.86 | +12.5% | +14.3% | +7.9% to +19.5% |
| raw_wv1.00_wh1.00b | 1.00 | 1.00 | 1.00 | +13.0% | +13.5% | +11.0% to +17.0% |
| raw_wv1.00_wh1.25 | 0.80 | 0.89 | 1.11 | +12.6% | +14.1% | +9.5% to +16.0% |
| raw_wv1.00_wh1.50 | 0.67 | 0.80 | 1.20 | +13.1% | +13.0% | +12.5% to +17.7% |
| raw_wv1.00_wh2.00 | 0.50 | 0.67 | 1.33 | +14.0% | +13.9% | +12.8% to +16.6% |

### Walk-forward result

| Held-out cycle | Best ratio from training | Train alpha | Held-out alpha | Equal-weight held-out alpha | Improvement |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2014-2017 | 0.75 | +15.1% | +10.4% | +11.0% | -0.6pp |
| 2018-2021 | 2.00 | +17.9% | +4.8% | +14.1% | -9.3pp |
| 2022-2024 | 0.50 | +13.9% | +16.6% | +17.0% | -0.4pp |
| 2025-now | 0.50 | +14.7% | +13.5% | +13.0% | +0.5pp |

Median out-of-sample alpha:

- Optimized fold-selected ratios: **+11.9%**
- Equal-weight baseline: **+13.5%**
- Median improvement: **-1.6pp**
- Optimized OOS spread: **+4.8% to +16.6%**

### Perturbation

Largest ±10% ratio-perturbation movement: **1.6pp** OOS alpha. The biggest move was in `2025-now`, where shifting the selected `0.50` ratio to `0.55` moved held-out alpha from `+13.5%` to `+15.1%`.

The more important fragility is not the perturbation delta; it is the fold instability. Training picked holder-heavy ratios (`0.50–0.75`) in three folds but a valuation-heavy `2.00` ratio when 2018-2021 was held out, and that valuation-heavy candidate then underperformed equal-weight by **9.3pp** OOS.

**Step 1 verdict:** fail. The optimized selector did not beat equal-weight out-of-sample and missed the 2pp continuation bar by a wide margin. Stop here.

## 3. Step 2 — Tier thresholds

Not reached. Per the standing rule, Step 2 only runs if Step 1 produces a robust ≥2pp median out-of-sample improvement over equal-weight. Step 1 produced **-1.6pp**, so threshold optimization would be scope creep and likely overfit.

## 4. Step 3 — Constituent weights within Valuation

Not reached. Since Step 2 was not reached, the higher-risk valuation-constituent grid was intentionally not run on the live dataset.

The Step 3 runner exists for future gated research, but this dispatch did not use it for report evidence.

## 5. Summary table

| Candidate | In-sample full alpha | Out-of-sample alpha | Perturbation robustness | Recommendation |
| --- | ---: | ---: | --- | --- |
| Equal-weight production baseline | +13.0% | +13.5% median OOS | Baseline; no optimized perturbation needed | **Leave in production** |
| Step 1 cohort-weight optimizer | N/A fold-selected; best full-sample diagnostic was ratio `0.50` at +14.0% | +11.9% median OOS | ±10% perturb max move 1.6pp; fold choice unstable | **Drop / do not promote** |
| Step 2 threshold optimizer | Not run | Not run | Not run | Stop per Step 1 |
| Step 3 valuation-constituent optimizer | Not run | Not run | Not run | Stop per Step 1 |

## 6. Recommendation back to Martin

Equal-weight wins. The cohort-weight grid can make the full-sample diagnostic look slightly better, but the walk-forward selector generalizes worse than the Phase C baseline. The clearest warning sign is the `2018-2021` held-out fold: training picked a valuation-heavy `2.00` ratio, then delivered only `+4.8%` held-out alpha vs equal-weight's `+14.1%`.

My recommendation: **leave the production composite equal-weighted**. There is no promotion candidate from Phase D. The useful finding is negative: the Phase C baseline's parsimony is not leaving obvious, robust alpha on the table at the cohort-weight level.
