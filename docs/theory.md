# Milk Road on-chain index — theory of the framework

**Status:** draft v0.7 — production `MROI` switched on 2026-05-28 to the validated Phase P / P4 architecture: holder-behavior spine only, asymmetric LONG/CASH thresholds, and a state machine that holds the prior posture in the noise band.

> This document encodes *why* the framework is shaped the way it is. Macro-framework encodes its own causal model for broad risk assets; Milk Road on-chain index keeps a BTC-specific causal model: holder behavior drives the production posture, while valuation remains a diagnostic lens for cycle awareness.

---

## 1. What drives BTC on multi-month timescales?

Five causal factors, ranked roughly by signal strength on multi-month horizons:

1. **Valuation mean reversion around realized cost basis.** BTC has no cash flows, no earnings, no DCF anchor. The closest fundamental anchor is realized cap — the aggregate cost basis of all coins. Deep deviations still matter for cycle awareness: expensive markets are fragile, cheap markets can be asymmetric opportunities. But Phase G/H/I/J/N showed valuation does **not** add allocation signal once tested alongside holder behavior; in several structures it actively hurt walk-forward performance. In production it is therefore a diagnostic, not a decision input. See [[reports/phase-g-asymmetric-override-2026-05-28.md]], [[reports/phase-h-spine-candidates-2026-05-28.md]], [[reports/phase-i-blended-spines-2026-05-28.md]], [[reports/phase-j-duration-magnitude-2026-05-28.md]], and [[reports/phase-n-euphoria-overlay-2026-05-28.md]].

2. **Holder behavior — what *all classes of meaningful holders* are doing.** This is broader than the legacy on-chain definition. A holder is anyone with conviction to take or release supply: sovereign individuals (STH/LTH on-chain), institutional funds (spot BTC ETFs, post-2024), and corporate treasuries (DATs — currently MSTR/Strategy, with Metaplanet, Marathon, Riot, etc. desirable as future coverage). LTHs distributing or STHs capitulating, ETF custody net-out, and DATs slowing accumulation all answer the same causal question: *are meaningful holders adding or shedding conviction right now?* This is the production spine.

3. **Network adoption / structural growth.** Address counts, hashrate, transaction count. Slow-moving — sets the *floor* under price, not the *direction* of price on multi-month timescales. Better as a "is this asset still alive?" signal than as a regime call.

4. **Derivative leverage / sentiment.** Funding rates, open interest. *Short-horizon* (days–weeks) contrarian signal. Extreme positive funding marks short-term tops because crowded longs become liquidation fuel. Less reliable multi-month.

5. **Macro environment.** Real yields, dollar strength, equity-correlation regime, global liquidity. Increasingly important since 2022 — BTC is more part of the risk-asset complex than it used to be. **Already covered by macro-framework.** This framework treats macro as an external override, not a re-derived input.

> **What changed from v0.6:** valuation moved from top-level decision input to diagnostic. Holder behavior is now the only production dimension.

## 2. Which dimension does this framework deliberately capture?

**One production dimension: Holder Behavior.**

Rationale:
- **Holder behavior is the action signal.** Phase K showed the pure holder spine (`z(holder_behavior) > 0`) could beat the prior production baseline OOS. Phase L found BTC/equity combinations failed to improve it. Phase P then found P4 — an asymmetric holder-only state machine — as the only candidate to clear both validation tracks. See [[reports/phase-k-pure-rerun-2026-05-28.md]], [[reports/phase-l-holder-btceq-combinations-2026-05-28.md]], and [[reports/phase-p-tier-confirmation-2026-05-28.md]].
- **Valuation is tested-and-rejected for allocation.** It remains useful for explaining where BTC sits in the cycle, but not for deciding the LONG/CASH posture. The dashboard therefore keeps `valuation_composite()` as a clearly labeled diagnostic chart.
- **The output stays chartable.** `MROI` remains a single z-score, but it now means exactly `holder_behavior_composite`, not a blend.

### Holder behavior composition (sub-cohorts)

The holder dimension is composed of three sub-cohorts. Each is a sub-composite within the dimension:

| Cohort | What it measures | Source class | Coverage start |
|---|---|---|---|
| **On-chain holders** | HODL 1Y+ 30d-change inverted z-score | BMP / Glassnode-class | 2012-onward |
| **Institutional funds** | Spot BTC ETF net flows | Farside / 13F filings | 2024-01 |
| **Corporate treasuries (DATs)** | Strategy/MSTR currently; future expansion to Metaplanet, Marathon, Riot, etc. is desirable for diversification | strategytracker.com / direct corporate disclosures | 2020-08 |

### Composition rule — equal-weight by epoch

Inside holder behavior, sub-cohorts are equal-weighted **among those with available coverage at the moment of evaluation**. Coverage windows differ, so we label the framework's composition by epoch:

| Epoch | Inputs to holder-behavior dimension | Notes |
|---|---|---|
| **2012–2020** | On-chain holders only | Only on-chain wallet-age data exists. |
| **2020–2024** | On-chain + corporate DAT | MSTR began accumulating 2020-08. |
| **2024–present** | On-chain + corporate DAT + institutional ETF | Spot ETFs launched 2024-01-11. |

The dashboard surfaces *which epoch* is active and which sub-cohorts are contributing. Composition drift is information, not a bug.

Exchange flow was tested in Task-20 / Phase E via Coin Metrics Community daily BTC exchange inflow/outflow and rejected because the canonical 30d net-flow z-score rule failed walk-forward in 2 of 4 cycles. It is removed from the framework rather than carried as a NaN placeholder; re-adding it would require a deliberate future theory decision. See [[reports/phase-e-exchange-flow-2026-05-21.md]].

**Out of scope (and why):**
- **Adoption (driver #3):** too slow for multi-month timing.
- **Derivative leverage (driver #4):** too short-horizon for this framework's intended use-case.
- **Macro (driver #5):** covered by macro-framework. The two frameworks are complements, not duplicates.

## 3. How is the production signal interpreted?

**Asymmetric thresholds on the holder spine.**

```
MROI = holder_behavior_composite

if MROI > 0.0:    posture = LONG
if MROI < -0.3:   posture = CASH
otherwise:        posture = previous posture
```

The state machine matters. The amber band (`-0.3 <= MROI <= 0.0`) is not a third allocation tier; it is a noise band where the model refuses to flip. Initial state at the first valid date is `LONG` if MROI is non-negative, otherwise `CASH`.

Why asymmetric:
- **Fast entries.** Positive holder behavior is actionable immediately above zero.
- **Sticky exits.** Many false flip clusters happen just below zero; requiring `< -0.3` filters that noise.
- **No CAUTION vocabulary.** Phase P found the tested LONG/CAUTION/CASH variants failed the dual-track/switch hurdle; P4 won as binary asymmetric.
- **No lag from confirmation rules.** Phase O's confirmation rules reduced churn but introduced lag and failed dual-track validation. P4 achieves similar noise filtering directly through the exit threshold. See [[reports/phase-o-confirmation-rules-2026-05-28.md]] and [[reports/phase-p-tier-confirmation-2026-05-28.md]].

## 4. Decision rule

**P4 asymmetric binary posture.** Decided 2026-05-28.

```
MROI  >  0.0  →  LONG  (100%)
MROI  < -0.3  →  CASH  (0%)
-0.3 <= MROI <= 0.0  →  HOLD PRIOR STATE
```

Evidence:
- **Standard walk-forward OOS median alpha:** `+24.2%` for P4 versus the prior production baseline's `+18.1%` (`+6.1pp`).
- **Strict cycle-4 OOS alpha:** `+28.9%`, validating in the modern/post-ETF held-out cycle.
- **Cadence:** `13.8` switches/cycle versus the prior production baseline's `33.2`, roughly an investor-grade `3–4` switches/year instead of clustered churn.

The output remains binary allocation: `LONG` = 100%, `CASH` = 0%. The dashboard separately shows the raw signal zone (green LONG signal, amber HOLD band, red CASH signal) so the user can see when posture and raw signal differ.

## 5. What's deliberately left out and why

- **Valuation as continuous input.** Tested across Phase G/H/I/J/N and rejected for allocation. It correlates with cycle position but hurt the production decision when blended or used as an overlay. See [[reports/phase-g-asymmetric-override-2026-05-28.md]], [[reports/phase-h-spine-candidates-2026-05-28.md]], [[reports/phase-i-blended-spines-2026-05-28.md]], [[reports/phase-j-duration-magnitude-2026-05-28.md]], and [[reports/phase-n-euphoria-overlay-2026-05-28.md]].
- **BTC/equity outperformance signals.** Tested as standalone spines and combinations in Phase H/I/L. They did not add enough alpha to beat the holder-only spine. See [[reports/phase-h-spine-candidates-2026-05-28.md]], [[reports/phase-i-blended-spines-2026-05-28.md]], and [[reports/phase-l-holder-btceq-combinations-2026-05-28.md]].
- **Symmetric thresholds.** Tested in Phase M/O. Symmetric zero-crossing rules left too much churn because cluster noise concentrated near zero, especially as false-CASH triggers. P4's asymmetric exit threshold is the validated answer. See [[reports/phase-m-stickiness-2026-05-28.md]] and [[reports/phase-o-confirmation-rules-2026-05-28.md]].
- **Confirmation rules.** Tested in Phase O. They reduced cadence but did not maintain enough dual-track alpha; P4 replaced them with threshold asymmetry rather than lag.
- **Daily / weekly timing.** This is a multi-month framework. Anyone wanting to time entries/exits within a posture uses something else.
- **Macro inputs.** Already in macro-framework. Treat as external override: if macro-framework says RISK-OFF, that can override this framework's call externally, but not inside MROI.
- **Adoption metrics.** Too slow for timing. Belongs to a "is BTC still a real asset?" framework.
- **Derivative leverage / funding rates.** Short-horizon. Useful for tactical context, not regime classification.
- **Single-cycle backtests.** BTC cycles are ~4 years. Walk-forward by cycle and strict holdout checks remain mandatory.

## 6. Open questions for Martin

None blocking for v1. The production framework is now: holder-only `MROI`, P4 asymmetric state machine, binary `LONG` / `CASH`, valuation diagnostic surface, and strict separation from macro-framework.

Open monitoring question:

- **Generalization to non-stationary regime.** Strict cycle-4 OOS validated P4 specifically in the modern/post-ETF era. Keep monitoring as holder cohort composition continues to evolve.

### Resolved 2026-05-20

- ~~Two dimensions vs three~~ → capital flows folded into expanded holder behavior.
- ~~Macro override or strict separation~~ → **strict separation**. Onchain-index produces the BTC-inside view; macro-framework produces the outside view.

### Resolved 2026-05-21

- ~~Sizing floor~~ → **0% / 100% binary**. `CASH` is 0%; `LONG` is 100%.
- ~~MROI technical handle~~ → keep `MROI` as the code/product math handle.

### Resolved 2026-05-28

- ~~Valuation + holder MROI~~ → **holder-only MROI**.
- ~~Binary zero threshold~~ → **P4 asymmetric state machine**: LONG above `0.0`, CASH below `-0.3`, hold prior posture in between.
- ~~CAUTION/tier vocabulary~~ → rejected by Phase P; no tested tiered variant qualified.

---

## Next step

With v0.7 in place, the production framework is concrete:

1. Compute **MROI** = `holder_behavior_composite` using the locked production cohort logic.
2. Map MROI through the P4 state machine: `MROI > 0.0` → `LONG` / 100%; `MROI < -0.3` → `CASH` / 0%; otherwise keep the prior posture.
3. Keep the dashboard focused on four surfaces:
   - Headline: current posture + current MROI + raw signal zone
   - MROI chart: holder spine with green/amber/red P4 zones
   - Valuation diagnostic: current z-score and constituent drivers, explicitly not used in decision
   - Holder Behavior lens: current z-score, epoch, cohort drivers, and concentration disclosures
4. Future work should monitor cohort drift and data coverage, not silently change the production decision rule.
