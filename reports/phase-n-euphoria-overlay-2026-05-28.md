# Phase N K1 euphoria-peak overlay — 2026-05-28

Data snapshot: cached Phase A frame, `5259` daily rows, `2012-01-01→2026-05-26`. This audit reused only the production `holder_behavior_composite` spine from K1; no valuation, BTC/equity, production composite, threshold, sizing, dashboard, or macro-framework code was changed. Structured output: `.cache/optim/phase_n.json`.

## 1. Methodology

Phase K made **K1 — holder behavior PURE** the baseline at `+21.0%` OOS median cycle alpha, `29.8` switches/cycle, and `-60.3%` max drawdown. Bob's inline diagnostic suggested `z(holder)` trends up to roughly `+1σ`, but mean-reverts in the `>+2σ` bucket, while extreme lows keep cascading. Phase N tests whether an asymmetric euphoria overlay can improve K1.

All candidates are PURE MODE and start from K1: `STAY LONG if z(holder_behavior) > 0 else CASH`.

- N1a/N1b/N1c/N1d force `CASH` when `z(holder)` is above `+1.5`, `+1.75`, `+2.0`, or `+2.25`.
- N2 uses a softer `CAUTION` state: 75% allocation when `z(holder) > +2.0`.
- N3 uses state tracking: each `z(holder) > +2.0` day resets a 30-valid-observation force-`CASH` window.
- N4 is the sanity check: force `STAY LONG` when `z(holder) < -2.0`.

The headline statistic mirrors prior phases: median annualized cycle alpha versus BTC buy-and-hold across the four `BTC_CYCLES`. The decision tree adopts an overlay only if N1/N2/N3 beats K1 OOS, or if it stays within 1pp of K1 alpha and improves max drawdown.

Note: the brief says “8 candidates,” but the enumerated IDs are 7 overlay variants: N1a-d, N2, N3, and N4. I implemented the enumerated set and kept K1 as a separate reference row.

## 2. Headline results

Annualized alpha vs BTC buy-and-hold. `Δ vs K1` compares against the fixed `+21.0%` K1 reference. `Max-DD Δ` is full-sample drawdown improvement versus K1's `-60.3%`; negative means worse drawdown.

| Candidate | OOS median | Δ vs K1 | Max DD | Max-DD Δ | Switches / cycle | Result |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| N1a — euphoria CASH z>1.5 | +13.3% | -7.7pp | -62.3% | -2.0pp | 40.2 | Loses |
| N1b — euphoria CASH z>1.75 | +14.7% | -6.3pp | -63.5% | -3.2pp | 37.8 | Loses |
| N1c — euphoria CASH z>2.0 | +13.1% | -7.9pp | -63.6% | -3.3pp | 36.2 | Loses |
| N1d — euphoria CASH z>2.25 | +14.2% | -6.8pp | -60.3% | -0.0pp | 33.2 | Loses |
| N2 — euphoria CAUTION z>2.0 | +17.2% | -3.8pp | -61.2% | -0.9pp | 36.5 | Best Phase N row, still loses |
| N3 — sticky euphoria CASH z>2.0 | +13.0% | -8.0pp | -63.8% | -3.5pp | 31.8 | Loses |
| N4 — extreme-low contrarian LONG | +12.8% | -8.2pp | -67.8% | -7.5pp | 32.8 | Loses; confirms low-tail cascade |

## 3. Full per-candidate results

| Candidate | Full alpha | 2014–2017 | 2018–2021 | 2022–2024 | 2025-now | OOS median | Time in cash | Switches / cycle |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| N1a — euphoria CASH z>1.5 | +8.9% | -9.5% | +5.1% | +21.4% | +26.9% | +13.3% | 54.9% | 40.2 |
| N1b — euphoria CASH z>1.75 | +8.3% | -10.3% | +5.9% | +23.5% | +26.9% | +14.7% | 52.8% | 37.8 |
| N1c — euphoria CASH z>2.0 | +9.2% | -9.1% | +9.5% | +16.7% | +26.9% | +13.1% | 50.8% | 36.2 |
| N1d — euphoria CASH z>2.25 | +11.1% | -5.6% | +12.9% | +15.5% | +26.9% | +14.2% | 49.6% | 33.2 |
| N2 — euphoria CAUTION z>2.0 | +17.8% | +12.1% | +13.2% | +21.2% | +26.9% | +17.2% | 47.1% | 36.5 |
| N3 — sticky euphoria CASH z>2.0 | +11.0% | -4.8% | +3.0% | +30.7% | +23.1% | +13.0% | 56.2% | 31.8 |
| N4 — extreme-low contrarian LONG | +13.8% | +10.2% | +8.1% | +15.4% | +26.9% | +12.8% | 43.4% | 32.8 |

## 4. Euphoria trigger dates

Dates below are contiguous raw threshold-window start dates by BTC cycle. N2 and N3 share the same raw `z(holder) > +2.0` trigger windows as N1c; N3's additional 30-day force-CASH cooldown days are not listed as new triggers.

### N1a — z(holder) > +1.5

- 2014–2017: `2016-05-18`, `2016-07-01`, `2016-12-29`, `2017-03-27`, `2017-05-26`, `2017-06-11`, `2017-07-31`, `2017-11-21`, `2017-12-08`
- 2018–2021: `2019-07-27`, `2019-07-30`, `2020-12-19`
- 2022–2024: `2023-03-26`, `2023-06-29`, `2023-12-13`, `2024-01-17`, `2024-01-23`, `2024-03-12`, `2024-10-09`, `2024-10-12`, `2024-11-16`, `2024-11-19`
- 2025-now: none

### N1b — z(holder) > +1.75

- 2014–2017: `2016-05-18`, `2016-06-26`, `2016-12-31`, `2017-05-27`, `2017-05-30`, `2017-06-14`, `2017-08-01`
- 2018–2021: `2019-07-30`, `2020-12-22`, `2020-12-29`
- 2022–2024: `2023-03-31`, `2023-06-29`, `2023-12-14`, `2024-01-25`, `2024-03-12`, `2024-11-19`, `2024-12-25`
- 2025-now: none

### N1c / N2 / N3 — z(holder) > +2.0

- 2014–2017: `2016-05-19`, `2016-05-28`, `2017-08-01`
- 2018–2021: `2019-07-30`, `2019-08-06`, `2021-01-03`
- 2022–2024: `2023-04-07`, `2023-04-12`, `2023-06-29`, `2023-07-28`, `2023-12-27`, `2024-03-15`, `2024-03-20`, `2024-11-19`
- 2025-now: none

Longest `+2.0` windows: `2017-08-01→2017-09-03` (34 days), `2021-01-03→2021-01-17` (15 days), `2024-03-20→2024-04-10` (22 days), and `2024-11-19→2024-12-18` (30 days).

### N1d — z(holder) > +2.25

- 2014–2017: `2016-06-03`, `2016-06-08`, `2017-08-01`
- 2018–2021: `2021-01-05`
- 2022–2024: `2023-06-29`, `2023-12-27`, `2024-03-20`, `2024-11-19`
- 2025-now: none

Sanity check: the euphoria rules did **not** cleanly isolate actual BTC cycle tops. The `+2.0` rule fired in August 2017, months before the December 2017 top, and in early January 2021, well before the late-2021 second top. The looser `+1.5` rule did fire in late November/December 2017, but it still missed late 2021 and over-fired elsewhere.

## 5. Extreme-low sanity check

N4 event starts for `z(holder) < -2.0`:

- 2014–2017: `2014-04-09`, `2014-11-14`
- 2018–2021: `2018-07-26`, `2019-01-05`, `2019-12-02`, `2021-12-18`
- 2022–2024: `2022-01-01`
- 2025-now: none

N4 lost to K1 by `-8.2pp` OOS and worsened max drawdown by `-7.5pp`, so the walk-forward result supports the diagnostic that extreme-low holder readings are not a contrarian-buy signal in this rule family.

## 6. Concrete recommendation

Recommendation: **decision-tree branch 4 — all N1/N2/N3 overlays lose; keep K1 unchanged**. No euphoria overlay beat K1. No euphoria overlay stayed within 1pp of K1 while improving max drawdown. The best row, N2, was still `-3.8pp` below K1 and had slightly worse max drawdown.

Branch 5 is also confirmed for the sanity check: **N4 loses to K1**, reinforcing that extreme lows cascade rather than mean-revert.

Do not productionize a Phase N euphoria overlay as tested. The bucketing diagnostic appears to be an unstable event-timing clue rather than a robust walk-forward trading rule.

## 7. Downstream

- Next dispatch: keep K1 unchanged unless Martin explicitly wants a new overlay family; no production MROI/dashboard changes made.
- Preserve the Phase K/L/M/N sequence in theory/docs framing: K1 wins on alpha, Phase L finds no BTC/equity rescue, Phase M shows simple stickiness gives up too much alpha, and Phase N shows high-euphoria CASH/CAUTION overlays do not reliably catch cycle tops.
