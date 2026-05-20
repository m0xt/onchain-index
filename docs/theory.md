# onchain-index — theory of the framework

**Status:** draft v0.2 — incorporates Martin's correction (2026-05-20): ETF and DAT flows are holder behavior, not a separate "capital flows" category. The two-dimension structure (Valuation × Holder Behavior) is preserved; holder behavior now spans on-chain positioning + institutional fund flows + corporate treasuries + exchange flow, equal-weighted within available coverage and labeled by epoch.

> This document encodes *why* the framework is shaped the way it is. The MRMI structure works for macro-framework because it encodes a specific causal model (growth + financial conditions drive regime; real-econ tail risk modifies it). For onchain-index to be more than "MRMI shape with BTC inputs," it needs its own causal model. That's what this doc is for.

---

## 1. What drives BTC on multi-month timescales?

Five causal factors, ranked roughly by signal strength on multi-month horizons:

1. **Valuation mean reversion around realized cost basis.** BTC has no cash flows, no earnings, no DCF anchor. The only fundamental anchor is realized cap — the aggregate cost basis of all coins. Deep deviations (high MVRV-Z) tend to mean-revert downward; extreme negative deviations (capitulation lows) tend to mean-revert upward. Empirically the single strongest multi-month driver across 2014–2025.

2. **Holder behavior — what *all classes of meaningful holders* are doing.** This is broader than the legacy on-chain definition. A holder is anyone with conviction to take or release supply: sovereign individuals (STH/LTH on-chain), institutional funds (spot BTC ETFs, post-2024), corporate treasuries (DATs — MSTR/Strategy, Metaplanet, Marathon, Riot, etc.), and the exchange-side cohort (movement to/from sell venues). LTHs distributing or STHs capitulating, ETF custody net-out, DATs slowing accumulation, exchange inflows spiking — all answer the same causal question: *are meaningful holders adding or shedding conviction right now?* The measurement systems differ (wallet age vs Farside fund flows vs corporate balance-sheet disclosures vs exchange-flow analytics), but the underlying behavior is one thing.

3. **Network adoption / structural growth.** Address counts, hashrate, transaction count. Slow-moving — sets the *floor* under price, not the *direction* of price on multi-month timescales. Better as a "is this asset still alive?" signal than as a regime call.

4. **Derivative leverage / sentiment.** Funding rates, open interest. *Short-horizon* (days–weeks) contrarian signal. Extreme positive funding marks short-term tops because crowded longs become liquidation fuel. Less reliable multi-month.

5. **Macro environment.** Real yields, dollar strength, equity-correlation regime, global liquidity. Increasingly important since 2022 — BTC is more part of the risk-asset complex than it used to be. **Already covered by macro-framework.** This framework treats macro as an external override, not a re-derived input.

> **What changed from v0.1:** the prior draft separated "holder behavior" (on-chain) from "external capital flows" (ETF/DAT/exchange). That was a measurement-system distinction masquerading as a causal one. Causally, they all answer the same question. The framework collapses cleaner without the split.

## 2. Which dimensions does this framework deliberately capture?

**Two core dimensions: Valuation × Holder Behavior.**

Rationale:
- **Valuation** (driver #1) is the strongest single signal in the multi-month range. Mean reversion around realized cost basis is the closest thing BTC has to a fundamental anchor.
- **Holder behavior — expanded definition** (driver #2) is the *confirmation/contradiction* dimension. Valuation alone is noisy; valuation cross-checked against what holders across cohorts are actually doing is sharper.

These two are complementary because they're measuring different things on different time horizons (valuation: where price is now relative to cost basis; holder behavior: which way meaningful holders are positioning). When they agree, the signal is strong. When they disagree, the signal is uncertain — and "uncertain" is a real, action-relevant state we want to be able to report.

### Holder behavior composition (sub-cohorts)

The holder dimension is itself composed of four sub-cohorts. Each is a sub-composite within the dimension:

| Cohort | What it measures | Source class | Coverage start |
|---|---|---|---|
| **On-chain holders** | STH MVRV, LTH MVRV, HODL waves, dormancy, RHODL — wallet-age-derived positioning | BMP / Glassnode-class | 2012-onward (~13y) |
| **Institutional funds** | Spot BTC ETF net flows | Farside / 13F filings | 2024-01 (~2.5y) |
| **Corporate treasuries (DATs)** | Strategy/MSTR, Metaplanet, Marathon, Riot, etc. — Δ in disclosed holdings | strategytracker.com / direct corporate disclosures | 2020-08 (~5y for MSTR, less for others) |
| **Exchange-side flow** | Net coin flow to/from sell venues — coins moving onto exchanges = distribution signal | BMP / Glassnode / CryptoQuant (currently NOT pulled — see Phase B data-gap finding) | (depends on source) |

### Composition rule — equal-weight by epoch

Inside the holder-behavior dimension, sub-cohorts are equal-weighted **among those with available coverage at the moment of evaluation**. Coverage windows differ dramatically, so we label the framework's composition by epoch:

| Epoch | Inputs to holder-behavior dimension | Notes |
|---|---|---|
| **2012–2020** | On-chain holders only | Only on-chain wallet-age data exists; DATs and ETFs don't yet meaningfully exist. |
| **2020–2024** | On-chain + corporate DAT | MSTR began accumulating 2020-08. DAT cohort is small but real. |
| **2024–present** | On-chain + corporate DAT + institutional ETF | Spot ETFs launched 2024-01-11; ETF flow is now the largest marginal-supply lens. |
| **Future** | + exchange-side flow once we add a source | Phase B flagged this as missing. Adding it is a data-layer task, not a theory change. |

The dashboard surfaces *which epoch* is currently active and which sub-cohorts are contributing, so the user can see the *composition* of the holder-behavior score and not just its number. Composition-drift is information, not a bug.

**Out of scope (and why):**
- **Adoption (driver #3):** too slow for multi-month timing. Belongs to a "is BTC still a real asset?" framework, which is different.
- **Derivative leverage (driver #4):** too short-horizon for this framework's intended use-case (multi-month positioning, not weekly tactical).
- **Macro (driver #5):** covered by macro-framework. **The two frameworks are complements, not duplicates.** Macro-framework reads the outside (risk-asset regime); onchain-index reads the inside (BTC-specific regime). A future "joint" rule could combine the two; this framework just produces the inside view.

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
- **Composite of composites beyond what's spec'd here.** Holder behavior is *intentionally* a composite-of-sub-cohorts because that's how the dimension is defined (cohorts of holders). No further nesting. If a third top-level dimension ever genuinely belongs, we revisit this doc; we don't quietly bolt one on.

## 6. Open questions for Martin (please push back)

1. **2×2 vs additive composite?** I lean strongly 2×2 but the call depends on downstream use-case. If you want a single number you can chart and present, additive wins. If you want a regime label + sizing + visible decomposition, 2×2 wins. *(Unchanged from v0.1 — still open.)*

2. **Graded sizing levels (100/75/50/0)** — is the cash floor really 0% in the DISTRIBUTION quadrant, or do you want a small structural long (e.g. 25%) always? Function of how the framework is used, not what it can measure. *(Unchanged from v0.1 — still open.)*

3. **Macro override** — should this framework *take* macro-framework as an input (e.g. "in our quadrant logic, when macro is RISK-OFF, downshift one tier"), or stay strictly on-chain and let the user combine? Strict separation is cleaner; joint logic is more decision-ready. *(Unchanged from v0.1 — still open.)*

4. **Naming the quadrants** — ACCUMULATION / EARLY-BULL / MATURE-BULL / DISTRIBUTION is conventional but not the only choice. Some prefer COILED / EXPANSION / EUPHORIA / UNWIND or similar. Naming sets the dashboard's tone. *(Unchanged from v0.1 — still open.)*

5. **Diagnostic surface for holder-behavior sub-cohorts.** The 2×2 only sees the *aggregate* holder-behavior score, but the user might want to see whether the call is being driven by on-chain LTHs, by ETF flows, or by DATs. Should the dashboard surface the four sub-cohort scores explicitly alongside the quadrant call? My lean: yes, prominently — when on-chain and ETFs disagree, that's the single most decision-relevant signal the framework produces. *(New in v0.2.)*

### Resolved in v0.2

- ~~Two dimensions vs three~~ — Resolved 2026-05-20: stays two. Capital flows folded into expanded holder behavior. The "third dimension" question went away because the partition was wrong, not because we deliberately discarded a real driver.

---

## Next step

If Martin accepts the broad shape (two dimensions, 2×2 matrix, graded sizing, epoch-labeled holder-behavior composition), Phase C becomes:

1. Build the **Valuation composite** from Phase B's robust valuation winners. Candidates: STH MVRV, RHODL Ratio (both 4/4 cycles positive), Puell Multiple (3/4 cycles, miner-revenue lens), and one of MVRV-Z / NUPL (not both — 0.88 correlated).
2. Build the **Holder Behavior composite** with the four sub-cohorts, equal-weighted within available coverage and epoch-labeled:
   - On-chain holders (always available)
   - Corporate DAT (2020+)
   - Institutional ETF (2024+)
   - Exchange-side flow (pending data-layer addition — Phase B flagged)
3. Define the quadrant thresholds (likely 504d-rolling percentile on both dimension scores).
4. Backtest each quadrant's historical occupancy + the implied graded-sizing rule, walk-forward by cycle.
5. Build the dashboard with the 2×2 matrix surfaced + four sub-cohort scores visible (so the user sees *why* we're in a given quadrant).

But only after the theory is locked.
