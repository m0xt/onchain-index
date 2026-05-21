"""Phase F research: compare canonical PI_score tier-count structures.

This is a parsimony audit, not threshold optimization. The candidate thresholds and
sizing maps are fixed by the Phase F dispatch and are evaluated head-to-head with
the production PI_score series and the shared tiered backtest harness.
"""

from __future__ import annotations

import argparse
import json
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import numpy as np
import pandas as pd

from onchain_index.backtest import BTC_CYCLES, backtest_tiered_signal
from onchain_index.composite import pi_score
from onchain_index.data import DEFAULT_CACHE_DIR
from onchain_index.research.optimization.common import (
    Metrics,
    default_output_path,
    envelope,
    json_ready,
    load_data,
    rounded_metrics,
    write_json,
)

TierFunction = Callable[[pd.Series], pd.Series]
TIER_PARSIMONY_RULE_PP = 1.0
FIVE_TIER_PROMOTION_PP = 1.0


@dataclass(frozen=True)
class TierStructure:
    """Fixed tier-count candidate for the Phase F parsimony audit."""

    candidate_id: str
    label: str
    thresholds: str
    tier_order: tuple[str, ...]
    tier_to_pct: dict[str, float]
    tier_function: TierFunction
    complexity: int
    notes: str


def _empty_tiers(score: pd.Series) -> pd.Series:
    """Return an object Series with the same index, preserving score NaNs."""
    return pd.Series(pd.NA, index=score.index, dtype="object")


def tier_2(score: pd.Series) -> pd.Series:
    """Map PI_score to the 2-tier CASH/STAY LONG structure: PI > 0 is long."""
    values = _empty_tiers(score)
    values = values.mask(score <= 0.0, "CASH")
    values = values.mask(score > 0.0, "STAY LONG")
    return values


def tier_3(score: pd.Series) -> pd.Series:
    """Map PI_score to the canonical 3-bucket structure."""
    values = _empty_tiers(score)
    values = values.mask(score < -0.5, "BUCKET_0")
    values = values.mask((score >= -0.5) & (score < 0.5), "BUCKET_50")
    values = values.mask(score >= 0.5, "BUCKET_100")
    return values


def tier_4(score: pd.Series) -> pd.Series:
    """Map PI_score to the historical 4-bucket structure."""
    values = _empty_tiers(score)
    values = values.mask(score < -1.0, "BUCKET_0")
    values = values.mask((score >= -1.0) & (score < 0.0), "BUCKET_50")
    values = values.mask((score >= 0.0) & (score < 1.0), "BUCKET_75")
    values = values.mask(score >= 1.0, "BUCKET_100")
    return values


def tier_5(score: pd.Series) -> pd.Series:
    """Map PI_score to the canonical 5-bucket structure."""
    values = _empty_tiers(score)
    values = values.mask(score < -1.5, "BUCKET_0")
    values = values.mask((score >= -1.5) & (score < -0.5), "BUCKET_25")
    values = values.mask((score >= -0.5) & (score < 0.5), "BUCKET_50")
    values = values.mask((score >= 0.5) & (score < 1.5), "BUCKET_75")
    values = values.mask(score >= 1.5, "BUCKET_100")
    return values


def tier_structures() -> list[TierStructure]:
    """Return the four fixed tier-count candidates from the Phase F spec."""
    return [
        TierStructure(
            candidate_id="2_tier",
            label="2-tier",
            thresholds="PI > 0",
            tier_order=("CASH", "STAY LONG"),
            tier_to_pct={"CASH": 0.0, "STAY LONG": 100.0},
            tier_function=tier_2,
            complexity=2,
            notes="MRMI-style binary; coarsest candidate.",
        ),
        TierStructure(
            candidate_id="3_tier",
            label="3-tier",
            thresholds="PI < -0.5; -0.5 <= PI < +0.5; PI >= +0.5",
            tier_order=("BUCKET_0", "BUCKET_50", "BUCKET_100"),
            tier_to_pct={"BUCKET_0": 0.0, "BUCKET_50": 50.0, "BUCKET_100": 100.0},
            tier_function=tier_3,
            complexity=3,
            notes="Symmetric middle ground.",
        ),
        TierStructure(
            candidate_id="4_tier",
            label="4-tier (former baseline)",
            thresholds="PI < -1; -1 <= PI < 0; 0 <= PI < +1; PI >= +1",
            tier_order=("BUCKET_0", "BUCKET_50", "BUCKET_75", "BUCKET_100"),
            tier_to_pct={
                "BUCKET_0": 0.0,
                "BUCKET_50": 50.0,
                "BUCKET_75": 75.0,
                "BUCKET_100": 100.0,
            },
            tier_function=tier_4,
            complexity=4,
            notes="Former production rule retained for Phase F reproducibility."
        ),
        TierStructure(
            candidate_id="5_tier",
            label="5-tier",
            thresholds=(
                "PI < -1.5; -1.5 <= PI < -0.5; -0.5 <= PI < +0.5; "
                "+0.5 <= PI < +1.5; PI >= +1.5"
            ),
            tier_order=("BUCKET_0", "BUCKET_25", "BUCKET_50", "BUCKET_75", "BUCKET_100"),
            tier_to_pct={
                "BUCKET_0": 0.0,
                "BUCKET_25": 25.0,
                "BUCKET_50": 50.0,
                "BUCKET_75": 75.0,
                "BUCKET_100": 100.0,
            },
            tier_function=tier_5,
            complexity=5,
            notes="Finer sanity check: more tiers should earn their precision.",
        ),
    ]


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


def _dwell_distribution(tiers: pd.Series, tier_order: Sequence[str]) -> list[dict[str, Any]]:
    """Return non-NaN tier dwell-time distribution in candidate tier order."""
    valid = tiers.dropna().astype("object")
    total = int(len(valid))
    counts = {str(tier): int(count) for tier, count in valid.value_counts(dropna=True).items()}
    rows: list[dict[str, Any]] = []
    for tier in tier_order:
        count = counts.get(tier, 0)
        rows.append(
            {
                "tier": tier,
                "days": count,
                "share_pct": round((count / total) * 100, 6) if total else None,
                "allocation_pct": None,
            }
        )
    return rows


def evaluate_structure(
    structure: TierStructure, score: pd.Series, ret: pd.Series
) -> dict[str, Any]:
    """Evaluate one fixed tier structure full-sample and by BTC cycle."""
    tiers = structure.tier_function(score)
    full_metrics = backtest_tiered_signal(tiers, ret.reindex(tiers.index), structure.tier_to_pct)

    cycle_metrics: dict[str, dict[str, float | None]] = {}
    cycle_alphas: list[float] = []
    for cycle_name, (start, end) in BTC_CYCLES.items():
        mask = _cycle_mask(tiers.index, start, end)
        metrics = backtest_tiered_signal(
            tiers.loc[mask], ret.reindex(tiers.index).loc[mask], structure.tier_to_pct
        )
        cycle_metrics[cycle_name] = rounded_metrics(metrics)
        alpha = _finite_alpha(metrics)
        if alpha is not None:
            cycle_alphas.append(alpha)

    dwell = _dwell_distribution(tiers, structure.tier_order)
    for row in dwell:
        row["allocation_pct"] = structure.tier_to_pct[str(row["tier"])]

    return {
        "candidate": {
            "id": structure.candidate_id,
            "label": structure.label,
            "thresholds": structure.thresholds,
            "tier_order": list(structure.tier_order),
            "tier_to_pct": structure.tier_to_pct,
            "complexity": structure.complexity,
            "notes": structure.notes,
        },
        "full_sample": rounded_metrics(full_metrics),
        "cycle_metrics": cycle_metrics,
        "oos_median_alpha": round(float(np.median(cycle_alphas)), 6) if cycle_alphas else None,
        "oos_alpha_spread": [
            round(float(np.min(cycle_alphas)), 6),
            round(float(np.max(cycle_alphas)), 6),
        ]
        if cycle_alphas
        else [],
        "dwell_time_distribution": dwell,
    }


def _recommendation(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Apply the Phase F parsimony rule to candidate results."""
    by_id = {str(row["candidate"]["id"]): row for row in results}
    baseline = by_id["4_tier"]
    baseline_alpha = cast(float, baseline["oos_median_alpha"])

    for row in results:
        alpha = row.get("oos_median_alpha")
        row["delta_vs_4tier_pp"] = (
            round(float(alpha) - baseline_alpha, 6) if isinstance(alpha, int | float) else None
        )

    simpler_matches = [
        row
        for row in results
        if int(row["candidate"]["complexity"]) < 4
        and isinstance(row.get("delta_vs_4tier_pp"), int | float)
        and float(row["delta_vs_4tier_pp"]) >= -TIER_PARSIMONY_RULE_PP
    ]
    simpler_matches.sort(key=lambda row: int(row["candidate"]["complexity"]))
    five_tier_delta = cast(float, by_id["5_tier"]["delta_vs_4tier_pp"])

    if simpler_matches:
        pick = simpler_matches[0]
        action = f"simplify_to_{pick['candidate']['id']}"
        text = (
            f"Recommend simplifying to {pick['candidate']['label']}: it is simpler and came "
            f"within 1pp of the 4-tier baseline."
        )
    elif five_tier_delta >= FIVE_TIER_PROMOTION_PP:
        action = "surface_5_tier_as_real_finding"
        text = (
            "5-tier beat the 4-tier baseline by at least 1pp OOS; surface this as a real "
            "precision finding for Martin rather than auto-promoting it."
        )
    else:
        action = "keep_4_tier"
        text = (
            "Keep the 4-tier baseline: no simpler structure came within 1pp OOS, and 5-tier "
            "did not beat 4-tier by at least 1pp."
        )

    return {
        "baseline_oos_median_alpha": round(baseline_alpha, 6),
        "simpler_within_1pp": [row["candidate"]["id"] for row in simpler_matches],
        "five_tier_delta_vs_4tier_pp": round(five_tier_delta, 6),
        "action": action,
        "text": text,
    }


def run_optimization(data: pd.DataFrame, *, output_path: Path | None = None) -> dict[str, Any]:
    """Run the fixed tier-structure comparison and optionally write JSON."""
    ret = cast(pd.Series, data["btc_price"]).pct_change()
    score = pi_score(data)
    results = [evaluate_structure(structure, score, ret) for structure in tier_structures()]

    payload = envelope(
        "tier_structure_parsimony",
        {
            "stopping_rule_pp": TIER_PARSIMONY_RULE_PP,
            "five_tier_promotion_rule_pp": FIVE_TIER_PROMOTION_PP,
            "methodology": {
                "walk_forward": (
                    "Leave-one-cycle-out by BTC cycle, with no threshold tuning: each fixed "
                    "tier-count rule is evaluated on each held-out cycle."
                ),
                "metric": "Out-of-sample median alpha across the four held-out cycle results.",
                "parsimony_rule": (
                    "If a simpler tier structure comes within 1pp of the 4-tier baseline, "
                    "recommend simplifying. 5-tier must beat 4-tier by at least 1pp to justify "
                    "the extra granularity."
                ),
            },
            "data_snapshot": {
                "rows": int(len(data)),
                "start": str(data.index.min()),
                "end": str(data.index.max()),
                "score_non_nan": int(score.notna().sum()),
            },
            "results": results,
            "recommendation": _recommendation(results),
        },
    )
    if output_path is not None:
        write_json(output_path, payload)
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare fixed PI_score tier structures.")
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--output", type=Path, default=default_output_path("tier_structure.json"))
    args = parser.parse_args(argv)

    data = load_data(cache_dir=cast(Path, args.cache_dir), use_cache=not bool(args.no_cache))
    payload = run_optimization(data, output_path=cast(Path, args.output))
    print(json.dumps(json_ready(payload["recommendation"]), indent=2, sort_keys=True))
    print(f"wrote {cast(Path, args.output)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
