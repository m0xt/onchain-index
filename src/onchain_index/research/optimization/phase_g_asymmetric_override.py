"""Phase G research: compare additive MROI vs valuation override variants.

This is a parsimony audit, not threshold optimization. The candidate thresholds are
fixed by the Phase G dispatch and are evaluated head-to-head with the production
valuation/holder dimensions and the shared tiered backtest harness.
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

from onchain_index.backtest import backtest_tiered_signal
from onchain_index.composite import holder_behavior_composite, valuation_composite
from onchain_index.data import DEFAULT_CACHE_DIR
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
BASELINE_OOS_ALPHA = 17.7
BINARY_TIER_TO_PCT = {"CASH": 0.0, "STAY LONG": 100.0}
SYMMETRIC_THRESHOLDS: tuple[float, ...] = (1.0, 1.28, 1.5, 2.0)
ASYMMETRIC_TOP_THRESHOLDS: tuple[float, ...] = (1.0, 1.28, 1.5)
ASYMMETRIC_BOTTOM_THRESHOLDS: tuple[float, ...] = (1.0, 1.5, 2.0)


@dataclass(frozen=True)
class OverrideCandidate:
    """Fixed Phase G candidate definition."""

    candidate_id: str
    label: str
    family: str
    rule: str
    t_top: float | None
    t_bottom: float | None
    notes: str


def _empty_tiers(index: pd.Index) -> pd.Series:
    """Return an object Series for binary CASH/STAY LONG tiers."""
    return pd.Series(pd.NA, index=index, dtype="object")


def additive_tiers(valuation: pd.Series, holder: pd.Series) -> pd.Series:
    """Return the current additive baseline tiers."""
    score = valuation + holder
    tiers = _empty_tiers(score.index)
    tiers = tiers.mask(score <= 0.0, "CASH")
    tiers = tiers.mask(score > 0.0, "STAY LONG")
    return tiers


def override_tiers(
    valuation: pd.Series,
    holder: pd.Series,
    *,
    t_top: float,
    t_bottom: float,
) -> pd.Series:
    """Return valuation-override tiers with holder behavior driving the middle."""
    tiers = _empty_tiers(valuation.index)
    tiers = tiers.mask(holder <= 0.0, "CASH")
    tiers = tiers.mask(holder > 0.0, "STAY LONG")
    tiers = tiers.mask(valuation > t_top, "CASH")
    tiers = tiers.mask(valuation < -t_bottom, "STAY LONG")
    return tiers.where(valuation.notna() & holder.notna())


def phase_g_candidates() -> list[OverrideCandidate]:
    """Return the fixed Phase G candidate set."""
    candidates = [
        OverrideCandidate(
            candidate_id="a_additive_baseline",
            label="A — additive baseline",
            family="A",
            rule="STAY LONG if z(val) + z(holder) > 0 else CASH",
            t_top=None,
            t_bottom=None,
            notes="Current production binary interpretation of additive MROI.",
        )
    ]
    for threshold in SYMMETRIC_THRESHOLDS:
        candidates.append(
            OverrideCandidate(
                candidate_id=f"b_override_symmetric_{threshold:g}".replace(".", "p"),
                label=f"B — override symmetric T={threshold:g}",
                family="B",
                rule=(
                    f"if z(val) > +{threshold:g}: CASH; elif z(val) < -{threshold:g}: "
                    "STAY LONG; else holder-only"
                ),
                t_top=threshold,
                t_bottom=threshold,
                notes="Symmetric valuation override around the holder-behavior middle rule.",
            )
        )
    for t_top in ASYMMETRIC_TOP_THRESHOLDS:
        for t_bottom in ASYMMETRIC_BOTTOM_THRESHOLDS:
            candidates.append(
                OverrideCandidate(
                    candidate_id=f"c_override_top_{t_top:g}_bottom_{t_bottom:g}".replace(
                        ".", "p"
                    ),
                    label=f"C — override top={t_top:g}, bottom={t_bottom:g}",
                    family="C",
                    rule=(
                        f"if z(val) > +{t_top:g}: CASH; elif z(val) < -{t_bottom:g}: "
                        "STAY LONG; else holder-only"
                    ),
                    t_top=t_top,
                    t_bottom=t_bottom,
                    notes="Asymmetric valuation override with separate top/bottom thresholds.",
                )
            )
    return candidates


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
    """Return Phase G non-return diagnostics for a tier series."""
    return {
        "time_in_cash_pct": round(cast(float, _cash_share(tiers)), 6)
        if _cash_share(tiers) is not None
        else None,
        "regime_switches": _switch_count(tiers),
    }


def _candidate_tiers(
    candidate: OverrideCandidate, valuation: pd.Series, holder: pd.Series
) -> pd.Series:
    """Build tiers for one candidate."""
    if candidate.family == "A":
        return additive_tiers(valuation, holder)
    if candidate.t_top is None or candidate.t_bottom is None:
        raise ValueError(f"override candidate {candidate.candidate_id} is missing thresholds")
    return override_tiers(valuation, holder, t_top=candidate.t_top, t_bottom=candidate.t_bottom)


def evaluate_candidate(
    candidate: OverrideCandidate,
    valuation: pd.Series,
    holder: pd.Series,
    ret: pd.Series,
) -> dict[str, Any]:
    """Evaluate one fixed Phase G candidate full-sample and by BTC cycle."""
    tiers = _candidate_tiers(candidate, valuation, holder)
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

    return {
        "candidate": {
            "id": candidate.candidate_id,
            "label": candidate.label,
            "family": candidate.family,
            "rule": candidate.rule,
            "t_top": candidate.t_top,
            "t_bottom": candidate.t_bottom,
            "tier_to_pct": BINARY_TIER_TO_PCT,
            "notes": candidate.notes,
        },
        "full_sample": full_sample,
        "cycle_metrics": cycle_metrics,
        "oos_median_alpha": round(float(np.median(cycle_alphas)), 6) if cycle_alphas else None,
        "oos_alpha_spread": [
            round(float(np.min(cycle_alphas)), 6),
            round(float(np.max(cycle_alphas)), 6),
        ]
        if cycle_alphas
        else [],
        "avg_regime_switches_per_cycle": round(float(np.mean(cycle_switches)), 6)
        if cycle_switches
        else None,
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
    """Apply the Phase G promotion rule to candidate results."""
    baseline = next(row for row in results if row["candidate"]["id"] == "a_additive_baseline")
    baseline_alpha = cast(float, baseline["oos_median_alpha"])

    for row in results:
        alpha = row.get("oos_median_alpha")
        row["delta_vs_additive_pp"] = (
            round(float(alpha) - baseline_alpha, 6) if isinstance(alpha, int | float) else None
        )
        row["delta_vs_phase_f_pp"] = (
            round(float(alpha) - BASELINE_OOS_ALPHA, 6)
            if isinstance(alpha, int | float)
            else None
        )

    best = _best_candidate(results)
    best_alpha = cast(float, best["oos_median_alpha"])
    best_delta = round(best_alpha - baseline_alpha, 6)
    best_family = str(best["candidate"]["family"])

    if best_family in {"B", "C"} and best_delta >= PROMOTION_BAR_PP:
        action = "switch-to-override"
        text = (
            f"Switch to asymmetric override: {best['candidate']['label']} beat additive by "
            f"{best_delta:.1f}pp OOS, clearing the +1pp bar."
        )
    elif best_family == "A" or best_delta < PROMOTION_BAR_PP:
        action = "keep-additive"
        text = (
            "Keep current additive: no override candidate beat the additive baseline by the "
            "+1pp OOS promotion bar."
        )
    else:
        action = "re-spec"
        text = "Re-spec required: Phase G results were ambiguous under the promotion rule."

    return {
        "baseline_id": "a_additive_baseline",
        "baseline_oos_median_alpha": round(baseline_alpha, 6),
        "phase_f_reference_oos_median_alpha": BASELINE_OOS_ALPHA,
        "promotion_bar_pp": PROMOTION_BAR_PP,
        "best_candidate_id": best["candidate"]["id"],
        "best_candidate_label": best["candidate"]["label"],
        "best_oos_median_alpha": round(best_alpha, 6),
        "best_delta_vs_additive_pp": best_delta,
        "action": action,
        "text": text,
    }


def run_optimization(data: pd.DataFrame, *, output_path: Path | None = None) -> dict[str, Any]:
    """Run the fixed Phase G comparison and optionally write JSON."""
    ret = cast(pd.Series, data["btc_price"]).pct_change()
    valuation = valuation_composite(data)
    holder = holder_behavior_composite(data)
    results = [
        evaluate_candidate(candidate, valuation, holder, ret)
        for candidate in phase_g_candidates()
    ]

    payload = envelope(
        "phase_g_asymmetric_override",
        {
            "promotion_bar_pp": PROMOTION_BAR_PP,
            "phase_f_reference_oos_median_alpha": BASELINE_OOS_ALPHA,
            "methodology": {
                "walk_forward": (
                    "Each fixed additive/override rule is evaluated on each BTC cycle window "
                    "from BTC_CYCLES; no threshold is selected in-sample."
                ),
                "metric": "Out-of-sample median alpha across the four held-out cycle results.",
                "promotion_rule": (
                    "An override must beat the additive baseline by at least 1pp OOS to justify "
                    "switching production logic."
                ),
            },
            "data_snapshot": {
                "rows": int(len(data)),
                "start": str(data.index.min()),
                "end": str(data.index.max()),
                "valuation_non_nan": int(valuation.notna().sum()),
                "holder_non_nan": int(holder.notna().sum()),
                "joint_non_nan": int((valuation.notna() & holder.notna()).sum()),
            },
            "candidate_grid": {
                "symmetric_thresholds": list(SYMMETRIC_THRESHOLDS),
                "asymmetric_top_thresholds": list(ASYMMETRIC_TOP_THRESHOLDS),
                "asymmetric_bottom_thresholds": list(ASYMMETRIC_BOTTOM_THRESHOLDS),
            },
            "results": results,
            "recommendation": _recommendation(results),
        },
    )
    if output_path is not None:
        write_json(output_path, payload)
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare additive MROI vs valuation override variants."
    )
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--output", type=Path, default=default_output_path("phase_g.json"))
    args = parser.parse_args(argv)

    data = load_data(cache_dir=cast(Path, args.cache_dir), use_cache=not bool(args.no_cache))
    payload = run_optimization(data, output_path=cast(Path, args.output))
    print(json.dumps(json_ready(payload["recommendation"]), indent=2, sort_keys=True))
    print(f"wrote {cast(Path, args.output)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
