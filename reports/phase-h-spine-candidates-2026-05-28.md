# Phase H spine-candidate audit — 2026-05-28

Data snapshot: cached Phase A frame, `5259` daily rows, `2012-01-01→2026-05-26`. Yahoo research closes were fetched for `BTC-USD`, `^IXIC`, and `^GSPC`, aligned to the Phase A daily index, and cached under `.cache/research/`. This dispatch changed no production data fetch, composite, threshold, sizing, dashboard, or macro-framework code. Structured output: `.cache/optim/phase_h.json`.

## 1. Methodology

This is a fixed-candidate architecture audit, not threshold optimization. The audit tests Martin's MRMI-shaped spine+modifier pattern with valuation as a symmetric extreme override at `T=2.0σ`: if valuation is above `+2.0`, the rule goes `CASH`; if valuation is below `-2.0`, the rule stays long; otherwise the candidate spine drives `STAY LONG` when its z-score is positive and `CASH` when non-positive. H1 uses the existing holder-behavior dimension as the spine. H2/H3 use Yahoo `BTC-USD` versus `^IXIC`/`^GSPC` relative-strength z-scores over fixed `30d`, `90d`, and `180d` lookbacks. The headline statistic mirrors Phase F/G: median annualized cycle alpha versus BTC buy-and-hold across the four `BTC_CYCLES`, with no in-sample candidate selection.

## 2. Per-candidate results

Annualized alpha vs BTC buy-and-hold; max drawdown is strategy max drawdown over the full sample. `Δ vs additive` compares against the current additive reference of `+18.1%` OOS median alpha.

| Candidate | Full alpha | 2014–2017 | 2018–2021 | 2022–2024 | 2025-now | OOS median | Δ vs additive | Max DD | Time in cash | Switches / cycle | Spine corr |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| H1 — holder behavior | -5.3% | -24.5% | -2.4% | +18.4% | +31.1% | +8.0% | -10.1pp | -59.4% | 56.0% | 51.2 | 0.9 |
| H2 — BTC/NASDAQ RS 30d | -20.3% | -242.6% | +5.8% | -0.3% | +10.0% | +2.8% | -15.3pp | -50.7% | 66.3% | 83.2 | 0.6 |
| H2 — BTC/NASDAQ RS 90d | -29.3% | -286.3% | -15.3% | -0.6% | +10.8% | -7.9% | -26.0pp | -62.7% | 70.8% | 56.5 | 0.8 |
| H2 — BTC/NASDAQ RS 180d | -28.6% | -293.8% | -30.6% | +4.0% | +20.7% | -13.3% | -31.4pp | -53.7% | 68.9% | 42.8 | 0.8 |
| H3 — BTC/SPX RS 30d | -19.1% | -241.1% | +7.3% | +4.2% | +4.5% | +4.4% | -13.7pp | -49.8% | 65.8% | 76.8 | 0.6 |
| H3 — BTC/SPX RS 90d | -31.6% | -287.9% | -21.2% | -0.5% | +13.7% | -10.9% | -29.0pp | -66.1% | 69.5% | 61.5 | 0.8 |
| H3 — BTC/SPX RS 180d | -27.9% | -276.2% | -31.5% | +8.2% | +9.4% | -11.7% | -29.8pp | -54.6% | 67.3% | 44.8 | 0.8 |

## 3. Read-through

- The best Phase H spine was **H1 — holder behavior**, at `+8.0%` OOS median cycle alpha, but it still trailed the additive reference by `-10.1pp` and exactly echoes Phase G's best symmetric `T=2` override result.
- No BTC/equity relative-strength spine beat holder behavior. The best equity-relative spine was **H3 — BTC/SPX RS 30d** at `+4.4%` OOS median alpha; the best BTC/NASDAQ variant was the 30d lookback at `+2.8%`.
- H2/H3 improved some recent-cycle and full-sample drawdown numbers by sitting in cash roughly two-thirds of the time, but the alpha cost was too high. The 30d relative-strength variants also switched more often than H1.
- Yahoo BTC history plus the 504d z-score warmup leaves the first cycle with shorter H2/H3 coverage (`518–668` observations depending on lookback), so the `2014–2017` annualized losses are especially harsh. That caveat does not change the conclusion: the completed 2018–2024 cycles and the partial 2025-now cycle still do not clear the additive reference.
- Spine correlations versus the additive baseline are moderate-to-high (`0.6–0.9`). The equity-relative spines are not independent enough, under this construction, to overcome the lost continuous additive valuation information.

## 4. Concrete recommendation

Recommendation: **keep-additive** — no fixed spine+valuation-override candidate beat the current additive baseline of `+18.1%` OOS median alpha, and none came close to the `+19.1%` switch hurdle. Keep `MROI = z(valuation) + z(holder_behavior)` and the existing binary `MROI > 0` decision rule. If the product narrative wants MRMI-style language, frame the current on-chain math honestly as empirical-first additive evidence rather than claiming a spine+modifier architecture.

## 5. Downstream changes if a switch were recommended

No downstream production switch is recommended from this audit.

If Martin nevertheless wanted to pursue a spine architecture after reviewing the report, the follow-on work would be: productionize equity-index fetches in `data.py`, add tested relative-strength construction in `composite.py`, revise `docs/theory.md` around the selected spine and valuation override, surface the active spine/override state in the dashboard, and update decision-rule tests. Based on Phase H, those changes should not be made without a new hypothesis or materially different spine spec.
