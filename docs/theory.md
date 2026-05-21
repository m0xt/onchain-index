# Milk Road on-chain index — theory of the framework

**Status:** draft v0.5 — production decision rule simplified from the former 4-bucket sizing rule to the 2-tier MRMI-shaped `CASH` / `STAY LONG` rule. Martin chose option (a) on 2026-05-21 after Task-26 / Phase F showed the binary rule beat the former baseline by `+4.1pp` (`+4.2pp` rounded in the dispatch note) OOS median alpha while matching MRMI shape. Composite math is unchanged.

> This document encodes *why* the framework is shaped the way it is. The MRMI structure works for macro-framework because it encodes a specific causal model (growth + financial conditions drive regime; real-econ tail risk modifies it). For Milk Road on-chain index to be more than "MRMI shape with BTC inputs," it needs its own causal model. That's what this doc is for.

---

## 1. What drives BTC on multi-month timescales?

Five causal factors, ranked roughly by signal strength on multi-month horizons:

1. **Valuation mean reversion around realized cost basis.** BTC has no cash flows, no earnings, no DCF anchor. The only fundamental anchor is realized cap — the aggregate cost basis of all coins. Deep deviations (high MVRV-Z) tend to mean-revert downward; extreme negative deviations (capitulation lows) tend to mean-revert upward. Empirically the single strongest multi-month driver across 2014–2025.

2. **Holder behavior — what *all classes of meaningful holders* are doing.** This is broader than the legacy on-chain definition. A holder is anyone with conviction to take or release supply: sovereign individuals (STH/LTH on-chain), institutional funds (spot BTC ETFs, post-2024), and corporate treasuries (DATs — currently MSTR/Strategy, with Metaplanet, Marathon, Riot, etc. desirable as future coverage). LTHs distributing or STHs capitulating, ETF custody net-out, and DATs slowing accumulation all answer the same causal question: *are meaningful holders adding or shedding conviction right now?* The measurement systems differ (wallet age vs Farside fund flows vs corporate balance-sheet disclosures), but the underlying behavior is one thing.

3. **Network adoption / structural growth.** Address counts, hashrate, transaction count. Slow-moving — sets the *floor* under price, not the *direction* of price on multi-month timescales. Better as a "is this asset still alive?" signal than as a regime call.

4. **Derivative leverage / sentiment.** Funding rates, open interest. *Short-horizon* (days–weeks) contrarian signal. Extreme positive funding marks short-term tops because crowded longs become liquidation fuel. Less reliable multi-month.

5. **Macro environment.** Real yields, dollar strength, equity-correlation regime, global liquidity. Increasingly important since 2022 — BTC is more part of the risk-asset complex than it used to be. **Already covered by macro-framework.** This framework treats macro as an external override, not a re-derived input.

> **What changed from v0.1:** the prior draft separated "holder behavior" (on-chain) from "external capital flows" (ETF/DAT). That was a measurement-system distinction masquerading as a causal one. Causally, they answer the same question. The framework collapses cleaner without the split.

## 2. Which dimensions does this framework deliberately capture?

**Two core dimensions: Valuation × Holder Behavior.**

Rationale:
- **Valuation** (driver #1) is the strongest single signal in the multi-month range. Mean reversion around realized cost basis is the closest thing BTC has to a fundamental anchor.
- **Holder behavior — expanded definition** (driver #2) is the *confirmation/contradiction* dimension. Valuation alone is noisy; valuation cross-checked against what holders across cohorts are actually doing is sharper.

These two are complementary lenses, not independent axes. They carry overlapping but distinct information: valuation says where price is relative to cost basis, while holder behavior says how meaningful holders are positioning. Phase D measured full-sample Pearson correlation at `0.631`, so the honest claim is partial overlap with diagnostic value, not orthogonality. When they agree, the signal is strong. When they disagree, the signal is uncertain — and "uncertain" is a real, action-relevant state we want to be able to report. See [[reports/phase-d-audit-2026-05-21.md]].

### Holder behavior composition (sub-cohorts)

The holder dimension is itself composed of three sub-cohorts. Each is a sub-composite within the dimension:

| Cohort | What it measures | Source class | Coverage start |
|---|---|---|---|
| **On-chain holders** | STH MVRV, LTH MVRV, HODL waves, dormancy, RHODL — wallet-age-derived positioning | BMP / Glassnode-class | 2012-onward (~13y) |
| **Institutional funds** | Spot BTC ETF net flows | Farside / 13F filings | 2024-01 (~2.5y) |
| **Corporate treasuries (DATs)** | Strategy/MSTR currently; future expansion to Metaplanet, Marathon, Riot, etc. is desirable for diversification because DAT is now a single-buyer signal | strategytracker.com / direct corporate disclosures | 2020-08 (~5y for MSTR, less for others) |

### Composition rule — equal-weight by epoch

Inside the holder-behavior dimension, sub-cohorts are equal-weighted **among those with available coverage at the moment of evaluation**. Coverage windows differ dramatically, so we label the framework's composition by epoch:

| Epoch | Inputs to holder-behavior dimension | Notes |
|---|---|---|
| **2012–2020** | On-chain holders only | Only on-chain wallet-age data exists; DATs and ETFs don't yet meaningfully exist. |
| **2020–2024** | On-chain + corporate DAT | MSTR began accumulating 2020-08. DAT cohort is small but real. |
| **2024–present** | On-chain + corporate DAT + institutional ETF | Spot ETFs launched 2024-01-11; ETF flow is now the largest marginal-supply lens. |

The dashboard surfaces *which epoch* is currently active and which sub-cohorts are contributing, so the user can see the *composition* of the holder-behavior score and not just its number. Composition-drift is information, not a bug.

Exchange flow was tested in Task-20 / Phase E via Coin Metrics Community daily BTC exchange inflow/outflow and rejected because the canonical 30d net-flow z-score rule failed walk-forward in 2 of 4 cycles. It is removed from the framework rather than carried as a NaN placeholder; re-adding it would require a deliberate future theory decision, not a data-layer toggle. See [[reports/phase-e-exchange-flow-2026-05-21.md]].

**Out of scope (and why):**
- **Adoption (driver #3):** too slow for multi-month timing. Belongs to a "is BTC still a real asset?" framework, which is different.
- **Derivative leverage (driver #4):** too short-horizon for this framework's intended use-case (multi-month positioning, not weekly tactical).
- **Macro (driver #5):** covered by macro-framework. **The two frameworks are complements, not duplicates.** Macro-framework reads the outside (risk-asset regime); onchain-index reads the inside (BTC-specific regime). A future "joint" rule could combine the two; this framework just produces the inside view.

## 3. How are the two dimensions combined?

**Additive composite, MRMI-shaped, with diagnostic decomposition surfaced on the dashboard.** Decided 2026-05-20.

```
PI_score = z(valuation_composite) + z(holder_behavior_composite)
```

Where:
- `valuation_composite` = equal-weighted z of Phase B's robust valuation winners (STH MVRV, RHODL Ratio, Puell Multiple, one-of {MVRV-Z, NUPL}).
- `holder_behavior_composite` = equal-weighted z of the available sub-cohort signals at this epoch (on-chain holders always; corporate DAT 2020+; institutional ETF 2024+).

The score is a single number you can chart, compare against BTC price, and reason about over time.

**The diagnostic trade-off is solved by the dashboard, not by the math.** An additive composite alone collapses *why* you're at a given score — "cheap + distribution" averages to neutral. The dashboard fixes this by surfacing decomposition, while being explicit that the dimensions are partially overlapping rather than independent. At Phase D's `0.631` full-sample correlation, divergences between dimensions are still useful signal, but the user should not be told they are statistically clean axes. The dashboard surfaces four levels:

1. **PI_score** — the headline composite, drives the sizing tier
2. **Valuation dimension** — current z-score
3. **Holder Behavior dimension** — current z-score
4. **Three holder-behavior sub-cohort scores** — on-chain / DAT / ETF, so the user can see *which cohort* is moving the holder-behavior score

The aggregate drives the decision. The components explain the decision. Best of both — the additive math gives a chart-able decision signal, the decomposition prevents the framework from being a black box without overselling independence.

> **What changed from v0.2:** I leaned toward a 2×2 categorical matrix. Martin chose additive composite, which I now think is right. The 2×2's "preserves the diagnostic" argument is recovered by the dashboard decomposition without sacrificing the additive's "single chartable number." Additive wins on both fronts once the dashboard does its job.

## 4. Decision rule

**Binary MRMI-shaped rule on PI_score.** Decided 2026-05-21.

```
PI_score  > 0   →  STAY LONG  (100%)
PI_score <= 0   →  CASH        (0%)
```

The threshold is deliberately fixed at zero. This is the same shape as MRMI: invested only when the framework score is positive, otherwise cash. Exact zero maps to `CASH`, matching the strict `score > 0` convention.

Why these properties:
- **MRMI parity.** The product surface now has the same two-state action language as Milk Road Macro Index: `STAY LONG` / `CASH`.
- **Parsimony with evidence.** Task-26 / Phase F compared fixed 2-, 3-, 4-, and 5-tier structures without tuning thresholds. The 2-tier rule produced `+17.7%` OOS median alpha versus `+13.5%` for the former 4-tier baseline (`+4.1pp`; rounded as `+4.2pp` in Bob's dispatch).
- **No false precision.** The composite remains a multi-month BTC-specific regime score. Intermediate sizing buckets implied precision the walk-forward did not earn.
- **Single decisive output.** Tier = function of PI_score. No averaging across “but maybe…” inputs. Reproducible and auditable.

> **What changed from v0.4:** the prior graded 4-bucket production sizing rule was simplified to binary `CASH` / `STAY LONG`. The Valuation, Holder Behavior, and PI_score formulas did not change; only the interpretation layer changed.

## 5. What's deliberately left out and why

- **Daily / weekly timing.** This is a multi-month framework. Anyone wanting to time entries/exits within a quadrant uses something else.
- **Macro inputs.** Already in macro-framework. Treat as external override: if macro-framework says RISK-OFF, that overrides this framework's call. Don't re-derive.
- **Adoption metrics.** Too slow for timing. Belongs to a "is BTC still a real asset?" framework, which is different.
- **Derivative leverage / funding rates.** Short-horizon. Useful for tactical sizing within a regime; not for regime classification itself.
- **Single-cycle backtests.** BTC cycles are ~4 years. Any backtest that doesn't span ≥2-3 cycles is curve-fitting noise. Walk-forward by cycle is mandatory.
- **Composite of composites beyond what's spec'd here.** Holder behavior is *intentionally* a composite-of-sub-cohorts because that's how the dimension is defined (cohorts of holders). No further nesting. If a third top-level dimension ever genuinely belongs, we revisit this doc; we don't quietly bolt one on.

## 6. Open questions for Martin

None blocking for v1. The framework shape is now settled: additive `PI_score`, strict separation from macro-framework, two product states (`CASH` / `STAY LONG`), and prominent diagnostic decomposition.

Future research can still evaluate new source coverage or a separate joint macro + on-chain wrapper, but not by silently changing this framework's production rule.

### Resolved 2026-05-20

- ~~Two dimensions vs three~~ → two. Capital flows folded into expanded holder behavior.
- ~~2×2 matrix vs additive composite~~ → **additive composite**. Diagnostic decomposition recovered via dashboard.
- ~~Macro override or strict separation~~ → **strict separation**. Onchain-index produces the BTC-inside view; macro-framework produces the outside view. They are complementary outputs, not nested inputs. A future "joint" wrapper layer could combine them; not part of this framework.

### Resolved 2026-05-21

- ~~Sizing floor~~ → **0% / 100% binary**. `CASH` is 0%; `STAY LONG` is 100%. No configurable floor.
- ~~Tier naming~~ → **MRMI wording: `CASH` / `STAY LONG`**.
- ~~Threshold calibration~~ → **fixed zero threshold**. `PI_score > 0` is invested; `PI_score <= 0` is cash. No grid search or tuning.

---

## Next step

With v0.5 in place, the production framework is concrete:

1. Compute **PI_score** = z(Valuation) + z(Holder Behavior) using the locked production composite.
2. Map PI_score through the binary rule: `PI_score > 0` → `STAY LONG` / 100%; `PI_score <= 0` → `CASH` / 0%.
3. Keep the dashboard focused on the same three-section product surface:
   - Headline: current PI_score + binary action + allocation
   - Valuation lens: current z-score and constituent drivers
   - Holder Behavior lens: current z-score, epoch, cohort drivers, and concentration disclosures
4. Treat future work as additive research only: new source coverage, DAT diversification, or a separate joint macro + on-chain wrapper. Do not change the production threshold or sizing shape without a new explicit decision.
