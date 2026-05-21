# Milk Road on-chain index — theory of the framework

**Status:** draft v0.4 — Milk Road on-chain index display name adopted; `PI_score` remains the technical math handle. v0.3 framework retained, honesty pass applied: exchange flow removed after the failed Phase E canonical-rule gate, and the Valuation × Holder Behavior framing softened to partially correlated complementary lenses (Phase D Pearson `0.631`). Composite math, thresholds, and production tier logic are unchanged.

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

**Graded sizing tiers derived from threshold buckets on PI_score.** Decided 2026-05-20.

```
PI_score  > +1.0         →  100% long  (Strong)
PI_score   0   to +1.0   →   75% long  (Sized)
PI_score  -1.0 to  0     →   50% long  (Trim)
PI_score  < -1.0         →    0% (cash) or floor — see open Q below
```

Threshold values are placeholders. **Actual thresholds will be set empirically in Phase C** by examining the historical PI_score distribution at known regime-transition points (2018 top, 2018 bottom, 2021 top, 2022 bottom, etc.), not by optimization. Same discipline as macro-framework's threshold provenance.

Why these properties:
- **Four tiers, deliberately coarse.** Not 0/10/20/…/100. Fine sizing implies a precision the framework doesn't have. Four tiers treats sizing as a categorical decision, which it really is.
- **Symmetric around zero.** The composite is built from z-scores; zero is the natural neutral. Tiers above zero are scaled long; tiers at-or-below scale toward cash.
- **Single decisive output.** Tier = function of PI_score. No averaging across "but maybe…" inputs. Reproducible and auditable.

Binary was rejected because BTC's regime structure has stacked timescales (within-cycle volatility + 4-year structural cycle) — a single in/out call hides too much information. Regime-label-only was rejected because it leaves the sizing question for downstream, and we'd just end up specifying sizing tiers anyway. Graded sizing is the honest output for a multi-month BTC framework.

> **What changed from v0.2:** the sizing tiers were previously derived from the 2×2 quadrants. With the structure now additive, the tiers are derived from PI_score thresholds. Same number of tiers, same decision-shape, different upstream math.

## 5. What's deliberately left out and why

- **Daily / weekly timing.** This is a multi-month framework. Anyone wanting to time entries/exits within a quadrant uses something else.
- **Macro inputs.** Already in macro-framework. Treat as external override: if macro-framework says RISK-OFF, that overrides this framework's call. Don't re-derive.
- **Adoption metrics.** Too slow for timing. Belongs to a "is BTC still a real asset?" framework, which is different.
- **Derivative leverage / funding rates.** Short-horizon. Useful for tactical sizing within a regime; not for regime classification itself.
- **Single-cycle backtests.** BTC cycles are ~4 years. Any backtest that doesn't span ≥2-3 cycles is curve-fitting noise. Walk-forward by cycle is mandatory.
- **Composite of composites beyond what's spec'd here.** Holder behavior is *intentionally* a composite-of-sub-cohorts because that's how the dimension is defined (cohorts of holders). No further nesting. If a third top-level dimension ever genuinely belongs, we revisit this doc; we don't quietly bolt one on.

## 6. Open questions for Martin (please push back)

1. **Sizing floor — 0% cash or structural 25%?** In the bottom tier (PI_score < -1.0), the framework's natural output is 0% (full cash). For a discretionary trader that's fine; for someone who wants permanent BTC exposure and just sizes around a baseline, a floor of e.g. 25% is more realistic. The math can produce either. Martin's call.

2. **Naming the sizing tiers.** Three candidates:
   - Descriptive: **Strong / Sized / Trim / Cash**
   - Actionable: **Max / Long / Cautious / Out**
   - Numerical only: **100% / 75% / 50% / 0%** (no labels, scores speak for themselves)
   - Conviction-shaped: **High Conviction Long / Conviction Long / Neutral / Risk-Off**
   
   Naming sets the dashboard's tone and how it gets cited verbally ("we're in a Sized regime" vs "we're at 75% long" vs "we're in Conviction Long").

3. **Threshold calibration method for the four tiers.** Three candidates:
   - **Fixed z-score thresholds** (>+1, 0–1, -1–0, <-1) — assumes composite is roughly normally distributed. Simple, reproducible.
   - **Rolling percentile** (top quartile / upper third / lower third / bottom quartile) — forces equal time in each tier. More even but can churn during steady regimes.
   - **Empirically calibrated to historical regime transitions** — set thresholds by looking at composite values at known cycle tops/bottoms (2014/2018/2022 lows; 2017/2021 highs). Most defensible but requires explicit historical labelling — and the cycle-transition dates themselves involve some discretion.
   
   My lean: **start with fixed z-score thresholds for v1 simplicity, validate against empirical regime transitions in Phase C as a sanity check.** Don't optimize either.

4. **Diagnostic surface for holder-behavior sub-cohorts.** Should the dashboard prominently show all three sub-cohort scores (on-chain / DAT / ETF) alongside the headline PI_score? My lean: yes, prominently — when on-chain and ETF flows disagree, that's the single most decision-relevant signal the framework produces. Equivalent to macro-framework's morning page showing component sub-indicators alongside the MRMI value. *(Carried forward from v0.2; exchange flow removed in v0.4.)*

### Resolved 2026-05-20

- ~~Two dimensions vs three~~ → two. Capital flows folded into expanded holder behavior.
- ~~2×2 matrix vs additive composite~~ → **additive composite**. Diagnostic decomposition recovered via dashboard.
- ~~Macro override or strict separation~~ → **strict separation**. Onchain-index produces the BTC-inside view; macro-framework produces the outside view. They are complementary outputs, not nested inputs. A future "joint" wrapper layer could combine them; not part of this framework.

---

## Next step

With the v0.4 framing in (additive composite, graded sizing tiers, strict separation from macro-framework, three holder cohorts, and partial-correlation disclosure), Phase C is concrete:

1. Build the **Valuation composite** from Phase B's robust winners. Candidates: STH MVRV, RHODL Ratio (both 4/4 cycles positive), Puell Multiple (3/4 cycles, miner-revenue lens), and one of MVRV-Z / NUPL (not both — 0.88 correlated). Equal-weighted z-score of constituents.
2. Build the **Holder Behavior composite** as three epoch-aware sub-cohort scores, equal-weighted within available coverage:
   - On-chain holders (always available — STH MVRV is already in valuation; for holder-behavior, use HODL waves / dormancy / age-band metrics not already in valuation, to avoid double-counting)
   - Corporate DAT (2020+) — MSTR/Strategy Δ holdings; future expansion to Metaplanet, Marathon, etc. would diversify the currently single-buyer DAT signal
   - Institutional ETF (2024+) — Farside spot ETF net flow
3. Compute **PI_score** = z(Valuation) + z(Holder Behavior).
4. Set the four sizing-tier thresholds. Start with fixed z-score thresholds (>+1, 0–1, -1–0, <-1); sanity-check against historical cycle-transition values.
5. Backtest the tier-driven sizing rule walk-forward by cycle (2014-17 / 2018-21 / 2022-24 / 2025-now). Output: per-cycle realized return, drawdown, time-in-each-tier breakdown.
6. Build the dashboard:
   - Headline: current PI_score + current tier + suggested sizing
   - Dimension scores: Valuation z, Holder Behavior z
   - Sub-cohort scores: 3 holder-behavior cohort z's, with epoch tag and constituent concentration disclosure
   - Historical context: PI_score chart over time with tier-region shading + BTC price overlay

Open calibration questions from Section 6 (sizing floor, tier naming, threshold calibration method) get resolved during Phase C empirics. Theory shape is locked.
