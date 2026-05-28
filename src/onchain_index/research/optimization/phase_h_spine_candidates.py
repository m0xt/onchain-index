"""Phase H research: test MROI spine candidates with valuation tails override.

This is a research-only audit. It leaves production data fetches, MROI construction,
and dashboard rendering untouched while comparing fixed spine candidates under the
valuation override rule requested for Phase H.
"""

from __future__ import annotations

import argparse
import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import numpy as np
import pandas as pd

from onchain_index.backtest import DEFAULT_ZSCORE_WINDOW, backtest_tiered_signal, rolling_zscore
from onchain_index.composite import holder_behavior_composite, valuation_composite
from onchain_index.data import DEFAULT_CACHE_DIR
from onchain_index.research.equity_data import yahoo_daily_closes
from onchain_index.research.optimization.common import (
    BTC_CYCLES,
    Metrics,
    default_output_path,
    envelope,
    json_ready,
    load_data,
    rounded_metrics,
    write_json,
)

PROMOTION_BAR_PP = 1.0
ADDITIVE_BASELINE_OOS_ALPHA = 18.1
VALUATION_OVERRIDE_THRESHOLD = 2.0
RELATIVE_STRENGTH_LOOKBACKS: tuple[int, ...] = (30, 90, 180)
BINARY_TIER_TO_PCT = {"CASH": 0.0, "STAY LONG": 100.0}


@dataclass(frozen=True)
class SpineCandidate:
    """Fixed Phase H spine candidate definition."""

    candidate_id: str
    label: str
    family: str
    spine_column: str
    lookback_days: int | None
    source: str
    notes: str


def phase_h_candidates() -> list[SpineCandidate]:
    """Return the fixed Phase H spine set."""
    candidates = [
        SpineCandidate(
            candidate_id="h1_holder_behavior",
            label="H1 — holder behavior",
            family="H1",
            spine_column="holder_behavior",
            lookback_days=None,
            source="production holder_behavior_composite",
            notes="Clean holder-only spine reference using the existing holder dimension.",
        )
    ]
    for lookback in RELATIVE_STRENGTH_LOOKBACKS:
        candidates.append(
            SpineCandidate(
                candidate_id=f"h2_btc_nasdaq_rs_{lookback}d",
                label=f"H2 — BTC/NASDAQ RS {lookback}d",
                family="H2",
                spine_column=f"btc_nasdaq_rs_z_{lookback}d",
                lookback_days=lookback,
                source="Yahoo BTC-USD / ^IXIC daily closes",
                notes="BTC relative strength versus NASDAQ over the fixed lookback window.",
            )
        )
    for lookback in RELATIVE_STRENGTH_LOOKBACKS:
        candidates.append(
            SpineCandidate(
                candidate_id=f"h3_btc_spx_rs_{lookback}d",
                label=f"H3 — BTC/SPX RS {lookback}d",
                family="H3",
                spine_column=f"btc_spx_rs_z_{lookback}d",
                lookback_days=lookback,
                source="Yahoo BTC-USD / ^GSPC daily closes",
                notes="BTC relative strength versus S&P 500 over the fixed lookback window.",
            )
        )
    return candidates


def _empty_tiers(index: pd.Index) -> pd.Series:
    """Return an object Series for binary CASH/STAY LONG tiers."""
    return pd.Series(pd.NA, index=index, dtype="object")


def override_tiers(valuation: pd.Series, spine: pd.Series) -> pd.Series:
    """Return Phase H valuation-override tiers with a candidate spine in the middle."""
    tiers = _empty_tiers(valuation.index)
    tiers = tiers.mask(spine <= 0.0, "CASH")
    tiers = tiers.mask(spine > 0.0, "STAY LONG")
    tiers = tiers.mask(valuation > VALUATION_OVERRIDE_THRESHOLD, "CASH")
    tiers = tiers.mask(valuation < -VALUATION_OVERRIDE_THRESHOLD, "STAY LONG")
    return tiers.where(valuation.notna() & spine.notna())


def additive_tiers(valuation: pd.Series, holder: pd.Series) -> pd.Series:
    """Return the current additive baseline tiers for reference diagnostics."""
    score = valuation + holder
    tiers = _empty_tiers(score.index)
    tiers = tiers.mask(score <= 0.0, "CASH")
    tiers = tiers.mask(score > 0.0, "STAY LONG")
    return tiers.where(score.notna())


def _relative_strength_z(
    closes: pd.DataFrame, numerator: str, denominator: str, lookback: int
) -> pd.Series:
    """Return trailing z-score of BTC relative strength over a fixed lookback."""
    ratio = cast(pd.Series, closes[numerator].astype(float) / closes[denominator].astype(float))
    strength = cast(pd.Series, ratio.pct_change(lookback))
    result = rolling_zscore(strength, window=DEFAULT_ZSCORE_WINDOW)
    result.name = f"{numerator}_over_{denominator}_rs_z_{lookback}d"
    return result


def build_spines(
    data: pd.DataFrame,
    *,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    use_cache: bool = True,
) -> pd.DataFrame:
    """Build all Phase H candidate spine series on the Phase A daily index."""
    closes = yahoo_daily_closes(data.index, cache_dir=cache_dir, use_cache=use_cache)
    spines = {"holder_behavior": holder_behavior_composite(data)}
    for lookback in RELATIVE_STRENGTH_LOOKBACKS:
        spines[f"btc_nasdaq_rs_z_{lookback}d"] = _relative_strength_z(
            closes, "btc_usd_close", "nasdaq_close", lookback
        )
        spines[f"btc_spx_rs_z_{lookback}d"] = _relative_strength_z(
            closes, "btc_usd_close", "spx_close", lookback
        )
    return pd.DataFrame(spines, index=data.index)


def _cycle_mask(index: pd.Index, start: str, end: str) -> pd.Series:
    """Return a boolean Series selecting one BTC cycle window."""
    return pd.Series((index >= pd.Timestamp(start)) & (index <= pd.Timestamp(end)), index=index)


def _finite_alpha(metrics: Metrics | None) -> float | None:
    """Extract a finite alpha for median calculations."""
    if metrics is None:
        return None
    alpha = metrics.get("alpha")
    if alpha is None or not math.isfinite(alpha):
        return None
    return float(alpha)


def _cash_share(tiers: pd.Series) -> float | None:
    """Return share of valid days spent in CASH."""
    valid = tiers.dropna().astype("object")
    if valid.empty:
        return None
    return float(valid.eq("CASH").mean() * 100)


def _switch_count(tiers: pd.Series) -> int | None:
    """Return raw tier-transition count after dropping unscored days."""
    valid = tiers.dropna().astype("object")
    if valid.empty:
        return None
    transitions = valid.ne(valid.shift()).fillna(False)
    return max(int(transitions.sum() - 1), 0)


def _diagnostics(tiers: pd.Series) -> dict[str, float | int | None]:
    """Return Phase H non-return diagnostics for a tier series."""
    cash_share = _cash_share(tiers)
    return {
        "time_in_cash_pct": round(cash_share, 6) if cash_share is not None else None,
        "regime_switches": _switch_count(tiers),
    }


def _correlation(left: pd.Series, right: pd.Series) -> float | None:
    """Return finite correlation for two aligned series."""
    corr = left.corr(right)
    if corr is None or not math.isfinite(corr):
        return None
    return round(float(corr), 6)


def evaluate_candidate(
    candidate: SpineCandidate,
    valuation: pd.Series,
    spines: pd.DataFrame,
    baseline_score: pd.Series,
    ret: pd.Series,
) -> dict[str, Any]:
    """Evaluate one fixed Phase H candidate full-sample and by BTC cycle."""
    spine = cast(pd.Series, spines[candidate.spine_column])
    tiers = override_tiers(valuation, spine)
    full_metrics = backtest_tiered_signal(tiers, ret.reindex(tiers.index), BINARY_TIER_TO_PCT)

    cycle_metrics: dict[str, dict[str, float | int | None]] = {}
    cycle_alphas: list[float] = []
    cycle_switches: list[int] = []
    for cycle_name, (start, end) in BTC_CYCLES.items():
        mask = _cycle_mask(tiers.index, start, end)
        cycle_tiers = tiers.loc[mask]
        metrics = backtest_tiered_signal(
            cycle_tiers, ret.reindex(tiers.index).loc[mask], BINARY_TIER_TO_PCT
        )
        diagnostics = _diagnostics(cycle_tiers)
        cycle_metrics[cycle_name] = {**rounded_metrics(metrics), **diagnostics}
        alpha = _finite_alpha(metrics)
        switches = diagnostics["regime_switches"]
        if alpha is not None:
            cycle_alphas.append(alpha)
        if isinstance(switches, int):
            cycle_switches.append(switches)

    full_diagnostics = _diagnostics(tiers)
    full_sample = {**rounded_metrics(full_metrics), **full_diagnostics}
    oos_alpha = round(float(np.median(cycle_alphas)), 6) if cycle_alphas else None

    return {
        "candidate": {
            "id": candidate.candidate_id,
            "label": candidate.label,
            "family": candidate.family,
            "spine_column": candidate.spine_column,
            "lookback_days": candidate.lookback_days,
            "source": candidate.source,
            "rule": (
                "if z(valuation) > +2.0: CASH; elif z(valuation) < -2.0: STAY LONG; "
                "else STAY LONG if z(spine) > 0 else CASH"
            ),
            "valuation_override_threshold": VALUATION_OVERRIDE_THRESHOLD,
            "tier_to_pct": BINARY_TIER_TO_PCT,
            "notes": candidate.notes,
        },
        "full_sample": full_sample,
        "cycle_metrics": cycle_metrics,
        "oos_median_alpha": oos_alpha,
        "delta_vs_additive_reference_pp": (
            round(oos_alpha - ADDITIVE_BASELINE_OOS_ALPHA, 6) if oos_alpha is not None else None
        ),
        "oos_alpha_spread": [
            round(float(np.min(cycle_alphas)), 6),
            round(float(np.max(cycle_alphas)), 6),
        ]
        if cycle_alphas
        else [],
        "avg_regime_switches_per_cycle": round(float(np.mean(cycle_switches)), 6)
        if cycle_switches
        else None,
        "spine_vs_additive_baseline_correlation": _correlation(spine, baseline_score),
    }


def _baseline_reference(
    valuation: pd.Series,
    holder: pd.Series,
    ret: pd.Series,
) -> dict[str, Any]:
    """Return current additive baseline diagnostics on this data snapshot."""
    tiers = additive_tiers(valuation, holder)
    full_metrics = backtest_tiered_signal(tiers, ret.reindex(tiers.index), BINARY_TIER_TO_PCT)
    cycle_metrics: dict[str, dict[str, float | int | None]] = {}
    cycle_alphas: list[float] = []
    for cycle_name, (start, end) in BTC_CYCLES.items():
        mask = _cycle_mask(tiers.index, start, end)
        cycle_tiers = tiers.loc[mask]
        metrics = backtest_tiered_signal(
            cycle_tiers, ret.reindex(tiers.index).loc[mask], BINARY_TIER_TO_PCT
        )
        cycle_metrics[cycle_name] = {**rounded_metrics(metrics), **_diagnostics(cycle_tiers)}
        alpha = _finite_alpha(metrics)
        if alpha is not None:
            cycle_alphas.append(alpha)
    full_diagnostics = _diagnostics(tiers)
    return {
        "id": "additive_baseline_reference",
        "label": "Current additive baseline",
        "rule": "STAY LONG if z(val) + z(holder) > 0 else CASH",
        "fixed_reference_oos_median_alpha": ADDITIVE_BASELINE_OOS_ALPHA,
        "computed_oos_median_alpha": round(float(np.median(cycle_alphas)), 6)
        if cycle_alphas
        else None,
        "full_sample": {**rounded_metrics(full_metrics), **full_diagnostics},
        "cycle_metrics": cycle_metrics,
    }


def _best_candidate(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Return the result with the highest OOS median alpha."""
    ranked = [row for row in results if isinstance(row.get("oos_median_alpha"), int | float)]
    if not ranked:
        raise ValueError("no finite candidate OOS alpha results")
    ranked.sort(
        key=lambda row: (
            -float(row["oos_median_alpha"]),
            str(row["candidate"]["family"]),
            str(row["candidate"]["id"]),
        )
    )
    return ranked[0]


def _recommendation(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Apply the Phase H promotion rule to spine results."""
    best = _best_candidate(results)
    best_alpha = cast(float, best["oos_median_alpha"])
    best_delta = round(best_alpha - ADDITIVE_BASELINE_OOS_ALPHA, 6)

    if best_delta >= PROMOTION_BAR_PP:
        action = f"switch-to-spine-{best['candidate']['family'].lower()}"
        text = (
            f"Switch to {best['candidate']['label']}: it beat the additive reference by "
            f"{best_delta:.1f}pp OOS, clearing the +1pp bar."
        )
    elif best_delta >= 0.0:
        action = "promising-but-needs-more"
        text = (
            f"Promising but needs more work: {best['candidate']['label']} beat the additive "
            "reference directionally but did not clear the +1pp switch hurdle."
        )
    else:
        action = "keep-additive"
        text = (
            "Keep current additive: no fixed spine+valuation-override candidate beat the "
            "+18.1% additive OOS reference, let alone the +1pp switch hurdle."
        )

    return {
        "baseline_id": "additive_baseline_reference",
        "additive_reference_oos_median_alpha": ADDITIVE_BASELINE_OOS_ALPHA,
        "promotion_bar_pp": PROMOTION_BAR_PP,
        "switch_hurdle_oos_median_alpha": round(
            ADDITIVE_BASELINE_OOS_ALPHA + PROMOTION_BAR_PP, 6
        ),
        "best_candidate_id": best["candidate"]["id"],
        "best_candidate_label": best["candidate"]["label"],
        "best_oos_median_alpha": round(best_alpha, 6),
        "best_delta_vs_additive_reference_pp": best_delta,
        "action": action,
        "text": text,
    }


def run_optimization(
    data: pd.DataFrame,
    *,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    use_cache: bool = True,
    output_path: Path | None = None,
) -> dict[str, Any]:
    """Run the fixed Phase H spine comparison and optionally write JSON."""
    ret = cast(pd.Series, data["btc_price"]).pct_change()
    valuation = valuation_composite(data)
    holder = holder_behavior_composite(data)
    baseline_score = valuation + holder
    spines = build_spines(data, cache_dir=cache_dir, use_cache=use_cache)
    results = [
        evaluate_candidate(candidate, valuation, spines, baseline_score, ret)
        for candidate in phase_h_candidates()
    ]

    payload = envelope(
        "phase_h_spine_candidates",
        {
            "promotion_bar_pp": PROMOTION_BAR_PP,
            "additive_reference_oos_median_alpha": ADDITIVE_BASELINE_OOS_ALPHA,
            "valuation_override_threshold": VALUATION_OVERRIDE_THRESHOLD,
            "methodology": {
                "walk_forward": (
                    "Each fixed spine+valuation-override rule is evaluated on each BTC cycle "
                    "window from BTC_CYCLES; no candidate is selected in-sample."
                ),
                "metric": "Out-of-sample median alpha across the four cycle results.",
                "promotion_rule": (
                    "A spine switch must beat the +18.1% additive reference by at least "
                    "1pp OOS to justify production follow-up."
                ),
            },
            "data_snapshot": {
                "rows": int(len(data)),
                "start": str(data.index.min()),
                "end": str(data.index.max()),
                "valuation_non_nan": int(valuation.notna().sum()),
                "holder_non_nan": int(holder.notna().sum()),
                "joint_baseline_non_nan": int((valuation.notna() & holder.notna()).sum()),
                "spine_non_nan": {
                    column: int(cast(pd.Series, spines[column]).notna().sum())
                    for column in spines.columns
                },
            },
            "candidate_grid": {
                "relative_strength_lookbacks": list(RELATIVE_STRENGTH_LOOKBACKS),
                "valuation_override_threshold": VALUATION_OVERRIDE_THRESHOLD,
            },
            "baseline_reference": _baseline_reference(valuation, holder, ret),
            "results": results,
            "recommendation": _recommendation(results),
        },
    )
    if output_path is not None:
        write_json(output_path, payload)
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare Phase H spine candidates with valuation override."
    )
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--output", type=Path, default=default_output_path("phase_h.json"))
    args = parser.parse_args(argv)

    data = load_data(cache_dir=cast(Path, args.cache_dir), use_cache=not bool(args.no_cache))
    payload = run_optimization(
        data,
        cache_dir=cast(Path, args.cache_dir),
        use_cache=not bool(args.no_cache),
        output_path=cast(Path, args.output),
    )
    print(json.dumps(json_ready(payload["recommendation"]), indent=2, sort_keys=True))
    print(f"wrote {cast(Path, args.output)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
