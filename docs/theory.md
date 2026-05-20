# onchain-index — theory of the framework

**Status:** draft v0.1 — Bob first-pass for Martin to argue with. Not yet locked. Once we agree on this, the indicator slate and composite math become implementation details downstream of it.

> This document encodes *why* the framework is shaped the way it is. The MRMI structure works for macro-framework because it encodes a specific causal model (growth + financial conditions drive regime; real-econ tail risk modifies it). For onchain-index to be more than "MRMI shape with BTC inputs," it needs its own causal model. That's what this doc is for.

---

## 1. What drives BTC on multi-month timescales?

Six causal factors, roughly ranked by signal strength on multi-month horizons:

1. **Valuation mean reversion around realized cost basis.** BTC has no cash flows, no earnings, no DCF anchor. The only fundamental anchor is realized cap — the aggregate cost basis of all coins. Deep deviations (high MVRV-Z) tend to mean-revert downward; extreme negative deviations (capitulation lows) tend to mean-revert upward. Empirically the single strongest multi-month driver across 2014–2025.

2. **Holder behavior / supply distribution.** Long-term holders (LTHs, structurally smart money) and short-term holders (STHs, reactive money) trade differently. LTH distribution → tops form; STH capitulation → bottoms form. Encoded by STH MVRV, LTH MVRV, dormancy, age-band metrics. Leading-indicator-shaped (smart money moves before price).

3. **External capital flows.** Spot ETF flows, exchange net flow, institutional accumulation (MSTR-type). Coincident-to-leading. Empirically: sustained inflows → up; sustained outflows → down. But often partly *circular* — flows respond to price too, not just predict it.

4. **Network adoption / structural growth.** Address counts, hashrate, transaction count. Slow-moving — sets the *floor* under price, not the *direction* of price on multi-month timescales. Better as a "is this asset still alive?" signal than as a regime call.

5. **Derivative leverage / sentiment.** Funding rates, open interest. *Short-horizon* (days–weeks) contrarian signal. Extreme positive funding marks short-term tops because crowded longs become liquidation fuel. Less reliable multi-month.

6. **Macro environment.** Real yields, dollar strength, equity-correlation regime, global liquidity. Increasingly important since 2022 — BTC is more part of the risk-asset complex than it used to be. **Already covered by macro-framework.** This framework treats macro as an external override, not a re-derived input.

## 2. Which dimensions does this framework deliberately capture?

**Two core dimensions: Valuation × Holder Behavior.**

Rationale:
- **Valuation** (driver #1) is the strongest single signal in the multi-month range. Mean reversion around realized cost basis is the closest thing BTC has to a fundamental anchor.
- **Holder behavior** (driver #2) is the *confirmation/contradiction* dimension. Valuation alone is noisy; valuation cross-checked against what LTHs are actually doing is much sharper.

These two are complementary because they're measuring different things on different time horizons (valuation: backward-looking; holder behavior: leading-shaped). When they agree, the signal is strong. When they disagree, the signal is uncertain — and "uncertain" is a real, action-relevant state we want to be able to report.

**Out of scope (and why):**
- **Capital flows (driver #3):** coincident, partly circular, only 2024-onward for ETF flows. Use as a *sanity check* on regime calls, not as a core input.
- **Adoption (driver #4):** too slow for multi-month timing.
- **Derivative leverage (driver #5):** too short-horizon for this framework's intended use-case (multi-month positioning, not weekly tactical).
- **Macro (driver #6):** covered by macro-framework. **The two frameworks are complements, not duplicates.** Macro-framework reads the outside (risk-asset regime); onchain-index reads the inside (BTC-specific regime). A future "joint" rule could combine the two; this framework just produces the inside view.

## 3. How are the two dimensions combined?

Two candidate structures. I have a lean; both should be considered.

### Option A — Additive composite (MRMI-shaped)

```
score = z(valuation_composite) + z(holder_behavior_composite)
signal = score > 0  (binary)
```

- **Pro:** simple, MRMI-shaped, easy to backtest, single number to chart against BTC price.
- **Con:** hides which dimension is driving. "Cheap + distribution" averages to neutral and loses the diagnostic of *why* it's neutral.

### Option B — 2×2 regime matrix (hierarchical / categorical)

| | LTHs accumulating | LTHs distributing |
|---|---|---|
| **Valuation cheap** | **ACCUMULATION** (max long) | **EARLY-BULL** (sized long, watch closely) |
| **Valuation expensive** | **MATURE-BULL** (riding, trail) | **DISTRIBUTION** (cash / hedge) |

Each quadrant maps to a position size and a recommended posture. The framework's output is a regime label *plus* a suggested position size, not a single composite score.

- **Pro:** preserves the diagnostic, mirrors how a discretionary trader actually thinks about BTC, makes the framework's output decision-usable as-is rather than requiring downstream interpretation. Maps cleanly to BTC's empirical four-phase cycle structure (you can label every BTC market period since 2014 by quadrant and it reads sensibly).
- **Con:** doesn't produce a single backtestable composite score the way MRMI does — you backtest by quadrant transitions. More moving parts in the dashboard.

### My lean: **Option B — 2×2 regime matrix.**

The reason MRMI is additive is that macro-framework's consumers need a single number you can chart against SPX and make a binary call from. Onchain-index doesn't have that constraint — the use-case is "tell me what BTC regime we're in *and* how much conviction we have." A 2×2 expresses that natively; an additive composite collapses it.

The dashboard becomes a four-quadrant grid with the current state highlighted, plus the two dimension scores shown explicitly so you can see *why* you're in the quadrant you're in.

If Martin pushes back and wants MRMI-style for consistency, we can also produce the additive composite as a secondary output (it falls out of the same two dimension scores).

## 4. Decision rule

Three candidates:

- **Binary (in/cash):** MRMI-style. Decisive, simple, but coarse for BTC's stacked-regime structure.
- **Graded sizing (e.g. 0% / 25% / 50% / 75% / 100%):** captures conviction levels. Natural fit for the 2×2 (each quadrant has a sizing).
- **Regime label only (no position implied):** decision-support, not decision-rule. Output is the label; user decides the position.

**My lean: graded sizing, derived from the 2×2.**

```
ACCUMULATION       → 100% long
EARLY-BULL         → 75% long
MATURE-BULL        → 50% long
DISTRIBUTION       → 0% (cash) / optional hedge
```

Binary forces a false choice when conditions are mixed. Regime-label-only is honest but leaves the harder question (sizing) for later. Graded sizing makes the framework directly actionable while still encoding uncertainty.

The 4 sizing levels are deliberately coarse — not 0/10/20/…/100. Fine sizing implies precision the framework doesn't have. Four levels matches the four quadrants and treats sizing as a categorical decision, which it really is.

## 5. What's deliberately left out and why

- **Daily / weekly timing.** This is a multi-month framework. Anyone wanting to time entries/exits within a quadrant uses something else.
- **Macro inputs.** Already in macro-framework. Treat as external override: if macro-framework says RISK-OFF, that overrides this framework's call. Don't re-derive.
- **Adoption metrics.** Too slow for timing. Belongs to a "is BTC still a real asset?" framework, which is different.
- **Derivative leverage / funding rates.** Short-horizon. Useful for tactical sizing within a regime; not for regime classification itself.
- **Single-cycle backtests.** BTC cycles are ~4 years. Any backtest that doesn't span ≥2-3 cycles is curve-fitting noise. Walk-forward by cycle is mandatory.
- **ETF flows as input.** Used as a sanity check ("does our quadrant call agree with where capital is moving?"), not as a regime input — they're too coincident with price and too short-coverage to anchor a multi-cycle framework.
- **Composite of composites.** No nesting beyond the two-dimension structure. If a third dimension genuinely belongs here later, we revisit this doc; we don't quietly bolt one on.

## 6. Open questions for Martin (please push back)

1. **Two dimensions vs three?** I'm arguing valuation × holder-behavior is enough. Reasonable challenge: adding a third dimension (capital flows? network health?) might add information. My case for stopping at two: parsimony, both dimensions have 13+ years of clean data, third dimensions all have either coverage gaps or coincidence problems.

2. **2×2 vs additive composite?** I lean strongly 2×2 but I might be wrong about Martin's downstream use-case. If you want a single number you can chart and present, additive wins. If you want a regime label + sizing, 2×2 wins.

3. **Graded sizing levels (100/75/50/0)** — is the cash floor really 0% in the DISTRIBUTION quadrant, or do you want a small structural long (e.g. 25%) always? That's a function of how this framework is used, not what it can measure.

4. **Macro override** — should this framework *take* macro-framework as an input (e.g. "in our quadrant logic, when macro is RISK-OFF, downshift one tier"), or stay strictly on-chain and let the user combine? Strict separation is cleaner; joint logic is more decision-ready.

5. **Naming the quadrants** — ACCUMULATION / EARLY-BULL / MATURE-BULL / DISTRIBUTION is conventional but not the only choice. Some prefer COILED / EXPANSION / EUPHORIA / UNWIND or similar. Naming sets the dashboard's tone.

---

## Next step

If Martin accepts the broad shape (two dimensions, 2×2 matrix, graded sizing), Phase C becomes:

1. Build the *valuation composite* from Phase B's robust valuation winners (STH MVRV, RHODL Ratio, MVRV-Z probably one-of, not both).
2. Build the *holder-behavior composite* from Phase B's holder-behavior signals (this is where Phase B was thinner — we may need to revisit which indicators belong here vs the valuation side).
3. Define the quadrant thresholds (likely 504d-rolling percentile, both dimensions).
4. Backtest each quadrant's historical occupancy + the implied sizing rule, walk-forward by cycle.

But only after the theory is locked.
