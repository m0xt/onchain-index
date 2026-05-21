# Phase F tier-structure parsimony audit — 2026-05-21

Data snapshot: cached Phase A frame, `5253` daily rows, `2012-01-01→2026-05-20`. Production `PI_score` values come from `src/onchain_index/composite.py`; this dispatch changed no production composite, threshold, sizing, dashboard, or macro-framework code. Structured output: `.cache/optim/tier_structure.json`.

## 1. Methodology

This is a simplify-test, not threshold optimization. The audit compares only the four fixed tier-count structures Martin/Bob specified: 2-tier, 3-tier, current 4-tier, and 5-tier. Each candidate uses canonical symmetric thresholds around zero, fixed sizing percentages, and the shared `backtest_tiered_signal` harness. The walk-forward statistic mirrors Phase D's parsimony discipline: evaluate each fixed structure on the four BTC cycle windows defined in `BTC_CYCLES`, then summarize out-of-sample performance as the median held-out cycle alpha. The current 4-tier rule is the baseline. If a simpler tier structure comes within `1pp` of the 4-tier baseline OOS, the parsimony rule recommends simplifying; the 5-tier structure must beat 4-tier by at least `1pp` to justify extra granularity.

## 2. Per-candidate results

Annualized alpha vs BTC buy-and-hold:

| Candidate | Rule | Sizing | Full-sample alpha | 2014–2017 | 2018–2021 | 2022–2024 | 2025-now | OOS median alpha | Delta vs 4-tier |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2-tier | `PI > 0` | `0 / 100` | `+12.5%` | `+22.6%` | `+0.6%` | `+20.4%` | `+15.0%` | `+17.7%` | `+4.1pp` |
| 3-tier | `<-0.5 / ±0.5 / >=+0.5` | `0 / 50 / 100` | `+14.7%` | `+21.8%` | `+9.0%` | `+21.4%` | `+9.3%` | `+15.4%` | `+1.8pp` |
| 4-tier baseline | `<-1 / -1..0 / 0..+1 / >=+1` | `0 / 50 / 75 / 100` | `+13.0%` | `+11.0%` | `+14.1%` | `+17.0%` | `+13.0%` | `+13.5%` | `0.0pp` |
| 5-tier | `<-1.5 / -1.5..-0.5 / ±0.5 / +0.5..+1.5 / >=+1.5` | `0 / 25 / 50 / 75 / 100` | `+12.0%` | `+14.9%` | `+12.7%` | `+15.6%` | `+8.1%` | `+13.8%` | `+0.2pp` |

Read-through:

- The 2-tier binary rule has the best OOS median alpha (`+17.7%`) and beats the 4-tier baseline by `+4.1pp` on the requested statistic.
- The 3-tier rule also beats the 4-tier baseline on OOS median alpha (`+15.4%`, `+1.8pp`) and has the best full-sample alpha (`+14.7%`).
- The 4-tier baseline is steadier across cycles than 2-tier, but under the explicit Phase F parsimony metric it is not earning its added granularity.
- The 5-tier rule does **not** justify extra precision: it beats 4-tier by only `+0.2pp` OOS and trails 4-tier by `-1.0pp` full-sample.

## 3. Tier dwell-time distribution

Share of non-NaN `PI_score` days (`4719` scored days):

### 2-tier

| Tier | Allocation | Days | Share |
| --- | ---: | ---: | ---: |
| Cash | `0%` | `2116` | `44.8%` |
| Long | `100%` | `2603` | `55.2%` |

### 3-tier

| Tier | Allocation | Days | Share |
| --- | ---: | ---: | ---: |
| Cash | `0%` | `1705` | `36.1%` |
| Mid | `50%` | `1091` | `23.1%` |
| Long | `100%` | `1923` | `40.8%` |

### 4-tier baseline

| Tier | Allocation | Days | Share |
| --- | ---: | ---: | ---: |
| Cash | `0%` | `1271` | `26.9%` |
| Trim | `50%` | `845` | `17.9%` |
| Sized | `75%` | `1076` | `22.8%` |
| Strong | `100%` | `1527` | `32.4%` |

### 5-tier

| Tier | Allocation | Days | Share |
| --- | ---: | ---: | ---: |
| Cash | `0%` | `805` | `17.1%` |
| Trim | `25%` | `900` | `19.1%` |
| Mid | `50%` | `1091` | `23.1%` |
| Sized | `75%` | `689` | `14.6%` |
| Strong | `100%` | `1234` | `26.1%` |

## 4. Recommendation

The framework's 4-tier granularity is not earning its keep under the requested Phase F test. Both simpler structures came within `1pp` of the 4-tier baseline; in fact both beat it on OOS median alpha, and the coarsest 2-tier rule beat it by `+4.1pp`.

Recommendation: **simplify to 2-tier as the research candidate** — Cash when `PI_score <= 0`, Long when `PI_score > 0`. That is the honest parsimony result from this test.

Caveat before production promotion: the 2-tier rule's cycle profile is less even than the 4-tier baseline, especially `2018–2021` (`+0.6%` vs 4-tier `+14.1%`). If Martin values smoother behavior and partial-sizing semantics more than the requested median-OOS parsimony statistic, 3-tier is the more balanced simplification candidate. But under the rule Bob specified, binary wins and 5-tier does not.
