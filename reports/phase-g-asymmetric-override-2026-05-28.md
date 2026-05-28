# Phase G asymmetric-override audit — 2026-05-28

Data snapshot: cached Phase A frame, `5259` daily rows, `2012-01-01→2026-05-26`. This dispatch changed no production composite, threshold, sizing, dashboard, or macro-framework code. Structured output: `.cache/optim/phase_g.json`.

## 1. Methodology

This is a parsimony audit, not threshold optimization. The audit compares the current additive binary rule against Martin's valuation-as-override proposal using the production valuation and holder-behavior dimensions, the shared `BTC_CYCLES` windows, and the existing `backtest_tiered_signal` harness. Candidate A is the current additive rule (`z(val)+z(holder)>0`). Candidate B sweeps symmetric valuation override thresholds over `{1.0, 1.28, 1.5, 2.0}`. Candidate C sweeps the requested small asymmetric grid (`T_top ∈ {1.0, 1.28, 1.5}`, `T_bottom ∈ {1.0, 1.5, 2.0}`). The headline statistic mirrors Phase F: median cycle alpha versus BTC buy-and-hold across the four cycle windows, with no in-sample threshold selection.

## 2. Per-candidate results

Annualized alpha vs BTC buy-and-hold; max drawdown is strategy max drawdown over the full sample.

| Candidate | Rule | Full alpha | 2014–2017 | 2018–2021 | 2022–2024 | 2025-now | OOS median | Δ vs additive | Max DD | Time in cash | Switches / cycle |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A — additive baseline | STAY LONG if z(val) + z(holder) > 0 else CASH | +12.7% | +22.6% | +0.6% | +20.4% | +15.8% | +18.1% | +0.0pp | -65.9% | 44.9% | 33.2 |
| B — override symmetric T=1 | if z(val) > +1: CASH; elif z(val) < -1: STAY LONG; else holder-only | -21.6% | -27.6% | -11.7% | -12.1% | +19.0% | -11.9% | -30.0pp | -65.3% | 58.2% | 69.8 |
| B — override symmetric T=1.28 | if z(val) > +1.28: CASH; elif z(val) < -1.28: STAY LONG; else holder-only | -20.2% | -31.4% | -15.4% | +1.7% | +12.2% | -6.9% | -25.0pp | -55.9% | 60.8% | 61.5 |
| B — override symmetric T=1.5 | if z(val) > +1.5: CASH; elif z(val) < -1.5: STAY LONG; else holder-only | -16.7% | -23.2% | -10.5% | -1.8% | +24.4% | -6.1% | -24.2pp | -57.4% | 59.7% | 51.0 |
| B — override symmetric T=2 | if z(val) > +2: CASH; elif z(val) < -2: STAY LONG; else holder-only | -5.3% | -24.5% | -2.4% | +18.4% | +31.1% | +8.0% | -10.1pp | -59.4% | 56.0% | 51.2 |
| C — override top=1, bottom=1 | if z(val) > +1: CASH; elif z(val) < -1: STAY LONG; else holder-only | -21.6% | -27.6% | -11.7% | -12.1% | +19.0% | -11.9% | -30.0pp | -65.3% | 58.2% | 69.8 |
| C — override top=1, bottom=1.5 | if z(val) > +1: CASH; elif z(val) < -1.5: STAY LONG; else holder-only | -18.0% | -34.8% | -6.1% | +0.2% | +24.4% | -3.0% | -21.1pp | -51.7% | 67.4% | 60.8 |
| C — override top=1, bottom=2 | if z(val) > +1: CASH; elif z(val) < -2: STAY LONG; else holder-only | -17.3% | -34.8% | -6.1% | -0.1% | +31.1% | -3.1% | -21.2pp | -51.7% | 68.6% | 57.8 |
| C — override top=1.28, bottom=1 | if z(val) > +1.28: CASH; elif z(val) < -1: STAY LONG; else holder-only | -23.7% | -24.0% | -22.2% | -13.9% | +19.0% | -18.1% | -36.2pp | -76.0% | 53.6% | 66.0 |
| C — override top=1.28, bottom=1.5 | if z(val) > +1.28: CASH; elif z(val) < -1.5: STAY LONG; else holder-only | -20.2% | -31.4% | -17.1% | -1.9% | +24.4% | -9.5% | -27.6pp | -55.9% | 62.7% | 57.0 |
| C — override top=1.28, bottom=2 | if z(val) > +1.28: CASH; elif z(val) < -2: STAY LONG; else holder-only | -19.5% | -31.4% | -17.1% | -2.1% | +31.1% | -9.6% | -27.7pp | -55.9% | 64.0% | 54.0 |
| C — override top=1.5, bottom=1 | if z(val) > +1.5: CASH; elif z(val) < -1: STAY LONG; else holder-only | -20.3% | -15.4% | -15.9% | -13.8% | +19.0% | -14.6% | -32.7pp | -71.8% | 50.5% | 60.0 |
| C — override top=1.5, bottom=1.5 | if z(val) > +1.5: CASH; elif z(val) < -1.5: STAY LONG; else holder-only | -16.7% | -23.2% | -10.5% | -1.8% | +24.4% | -6.1% | -24.2pp | -57.4% | 59.7% | 51.0 |
| C — override top=1.5, bottom=2 | if z(val) > +1.5: CASH; elif z(val) < -2: STAY LONG; else holder-only | -16.0% | -23.2% | -10.5% | -2.0% | +31.1% | -6.2% | -24.3pp | -57.4% | 60.9% | 48.0 |

## 3. Read-through

- The current additive baseline won on the Phase G headline metric: `+18.1%` OOS median cycle alpha on the current data snapshot, versus Phase F's `+17.7%` reference.
- The best override candidate was `B — override symmetric T=2`, at `+8.0%` OOS median alpha, trailing additive by `-10.1pp`; no override came close to the `+1pp` promotion bar.
- Override variants were especially punitive in the older completed cycles: most produced negative alpha in `2014–2017` and `2018–2021`, even when the `2025-now` partial cycle looked strong.
- Some override grids lowered full-sample drawdown by spending much more time in cash, but that protection came with sharply negative full-sample alpha and substantially higher regime-switch counts.
- The conceptual objection is real — valuation is plausibly a tails signal — but this specific override spec discards too much useful continuous information from the additive composite.

## 4. Concrete recommendation

Recommendation: **keep-additive** — Phase G failed to beat the current additive baseline, and failed the stricter `+17.7% + 1pp` Phase F reference hurdle. Keep `MROI = z(valuation) + z(holder_behavior)` and the existing binary `MROI > 0` decision rule unless Martin wants to re-spec a different override architecture.

## 5. Downstream changes if a switch were recommended

No downstream production changes are recommended from this audit.

If Martin nevertheless chose to switch after reviewing the report, the follow-on work would be: update `composite.py` decision-rule logic to separate valuation/holder dimensions at decision time, adjust decision-rule tests, revise `docs/theory.md` section 3 to describe valuation as a tails override rather than an additive input, and update the dashboard surface to explain the active override state separately from holder-behavior direction.
