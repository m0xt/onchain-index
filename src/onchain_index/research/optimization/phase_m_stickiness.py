"""Phase M research: investor-grade stickiness variants for K1.

This is a research-only follow-up to Phase K/L. It keeps the holder-only PURE
spine and tests only decision-rule stickiness: hysteresis, 3-tier bands, and
EMA smoothing. Production data fetches, MROI construction, and dashboard code
are untouched.
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
from onchain_index.composite import holder_behavior_composite
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

K1_BASELINE_OOS_ALPHA = 21.0
QUALIFYING_OOS_ALPHA = 20.0
MAX_SWITCHES_PER_CYCLE = 15.0
HYSTERESIS_TIER_TO_PCT = {"CASH": 0.0, "STAY LONG": 100.0}
THREE_TIER_TO_PCT = {"CASH": 0.0, "CAUTION": 75.0, "STAY LONG": 100.0}
STICKINESS_THRESHOLDS: tuple[float, ...] = (0.3, 0.5, 0.7)
EMA_SPAN_DAYS = 30


@dataclass(frozen=True)
class StickinessCandidate:
    """Fixed Phase M candidate definition."""

    candidate_id: str
    label: str
    family: str
    rule_type: str
    threshold: float | None
    source: str
    notes: str
    ema_span_days: int | None = None


def phase_m_candidates() -> list[StickinessCandidate]:
    """Return the fixed Phase M holder-only stickiness candidate set."""
    hysteresis = [
        StickinessCandidate(
            candidate_id=f"m1{suffix}_holder_hysteresis_{str(threshold).replace('.', '_')}",
            label=f"M1{suffix} — hysteresis ±{threshold:.1f}",
            family=f"M1{suffix}",
            rule_type="hysteresis",
            threshold=threshold,
            source="Production holder_behavior_composite",
            notes=(
                f"Enter STAY LONG above +{threshold:.1f}; exit to CASH below "
                f"-{threshold:.1f}; hold current state inside the band."
            ),
        )
        for suffix, threshold in zip(("a", "b", "c"), STICKINESS_THRESHOLDS, strict=True)
    ]
    three_tier = [
        StickinessCandidate(
            candidate_id=f"m2{suffix}_holder_three_tier_{str(threshold).replace('.', '_')}",
            label=f"M2{suffix} — 3-tier ±{threshold:.1f}",
            family=f"M2{suffix}",
            rule_type="three_tier",
            threshold=threshold,
            source="Production holder_behavior_composite",
            notes=(
                f"STAY LONG above +{threshold:.1f}; CASH below -{threshold:.1f}; "
                "CAUTION at 75% allocation inside the band."
            ),
        )
        for suffix, threshold in zip(("a", "b", "c"), STICKINESS_THRESHOLDS, strict=True)
    ]
    return [
        *hysteresis,
        *three_tier,
        StickinessCandidate(
            candidate_id="m3_holder_ema_30d_threshold_0",
            label="M3 — 30d EMA holder threshold",
            family="M3",
            rule_type="ema_threshold",
            threshold=0.0,
            source="Production holder_behavior_composite",
            notes="Apply a 30-day EMA to z(holder_behavior), then STAY LONG if EMA > 0 else CASH.",
            ema_span_days=EMA_SPAN_DAYS,
        ),
    ]


def _empty_tiers(index: pd.Index) -> pd.Series:
    """Return an object Series for holder-only tiers."""
    return pd.Series(pd.NA, index=index, dtype="object")


def pure_holder_tiers(holder: pd.Series) -> pd.Series:
    """Return the K1 holder-only pure-mode tiers."""
    tiers = _empty_tiers(holder.index)
    tiers = tiers.mask(holder <= 0.0, "CASH")
    tiers = tiers.mask(holder > 0.0, "STAY LONG")
    return tiers.where(holder.notna())


def hysteresis_tiers(holder: pd.Series, threshold: float) -> pd.Series:
    """Return stateful K1 hysteresis tiers."""
    tiers = _empty_tiers(holder.index)
    state: str | None = None
    for index, value in holder.items():
        if pd.isna(value):
            continue
        z_value = float(value)
        if state is None:
            state = "STAY LONG" if z_value > 0.0 else "CASH"
        elif state == "CASH" and z_value > threshold:
            state = "STAY LONG"
        elif state == "STAY LONG" and z_value < -threshold:
            state = "CASH"
        tiers.loc[index] = state
    return tiers.where(holder.notna())


def three_tier_tiers(holder: pd.Series, threshold: float) -> pd.Series:
    """Return stateless LONG/CAUTION/CASH tiers for holder z-score bands."""
    tiers = _empty_tiers(holder.index)
    tiers = tiers.mask(holder < -threshold, "CASH")
    tiers = tiers.mask((holder >= -threshold) & (holder <= threshold), "CAUTION")
    tiers = tiers.mask(holder > threshold, "STAY LONG")
    return tiers.where(holder.notna())


def ema_threshold_tiers(holder: pd.Series, span: int) -> pd.Series:
    """Return binary tiers from a smoothed holder z-score."""
    smoothed = holder.ewm(span=span, adjust=False).mean()
    tiers = _empty_tiers(smoothed.index)
    tiers = tiers.mask(smoothed <= 0.0, "CASH")
    tiers = tiers.mask(smoothed > 0.0, "STAY LONG")
    return tiers.where(smoothed.notna())


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
    """Return Phase M non-return diagnostics for a tier series."""
    cash_share = _cash_share(tiers)
    return {
        "time_in_cash_pct": round(cash_share, 6) if cash_share is not None else None,
        "regime_switches": _switch_count(tiers),
    }


def _tier_to_pct(candidate: StickinessCandidate) -> dict[str, float]:
    """Return allocation mapping for one Phase M candidate."""
    if candidate.rule_type == "three_tier":
        return THREE_TIER_TO_PCT
    return HYSTERESIS_TIER_TO_PCT


def _candidate_tiers(candidate: StickinessCandidate, holder: pd.Series) -> pd.Series:
    """Build tiers for one Phase M candidate."""
    if candidate.rule_type == "hysteresis":
        return hysteresis_tiers(holder, cast(float, candidate.threshold))
    if candidate.rule_type == "three_tier":
        return three_tier_tiers(holder, cast(float, candidate.threshold))
    if candidate.rule_type == "ema_threshold":
        return ema_threshold_tiers(holder, cast(int, candidate.ema_span_days))
    raise ValueError(f"unknown rule_type {candidate.rule_type!r}")


def _rule_text(candidate: StickinessCandidate) -> str:
    """Return a compact rule description for one Phase M candidate."""
    if candidate.rule_type == "hysteresis":
        threshold = cast(float, candidate.threshold)
        return f"Enter LONG above +{threshold:.1f}; exit CASH below -{threshold:.1f}; hold between"
    if candidate.rule_type == "three_tier":
        threshold = cast(float, candidate.threshold)
        return f"LONG if z > +{threshold:.1f}; CASH if z < -{threshold:.1f}; CAUTION 75% between"
    span = cast(int, candidate.ema_span_days)
    return f"LONG if {span}d EMA of z(holder) > 0 else CASH"


def _evaluate_tiers(
    tiers: pd.Series, ret: pd.Series, tier_to_pct: dict[str, float]
) -> tuple[dict[str, Any], float | None, list[float], list[int]]:
    """Evaluate a tier series full-sample and by BTC cycle."""
    full_metrics = backtest_tiered_signal(tiers, ret.reindex(tiers.index), tier_to_pct)
    cycle_metrics: dict[str, dict[str, float | int | None]] = {}
    cycle_alphas: list[float] = []
    cycle_switches: list[int] = []
    for cycle_name, (start, end) in BTC_CYCLES.items():
        mask = _cycle_mask(tiers.index, start, end)
        cycle_tiers = tiers.loc[mask]
        metrics = backtest_tiered_signal(
            cycle_tiers, ret.reindex(tiers.index).loc[mask], tier_to_pct
        )
        diagnostics = _diagnostics(cycle_tiers)
        cycle_metrics[cycle_name] = {**rounded_metrics(metrics), **diagnostics}
        alpha = _finite_alpha(metrics)
        switches = diagnostics["regime_switches"]
        if alpha is not None:
            cycle_alphas.append(alpha)
        if isinstance(switches, int):
            cycle_switches.append(switches)

    oos_alpha = round(float(np.median(cycle_alphas)), 6) if cycle_alphas else None
    full_sample = {**rounded_metrics(full_metrics), **_diagnostics(tiers)}
    return (
        {"full_sample": full_sample, "cycle_metrics": cycle_metrics},
        oos_alpha,
        cycle_alphas,
        cycle_switches,
    )


def _alpha_per_switch(oos_alpha: float | None, switches_per_cycle: float | None) -> float | None:
    """Return OOS alpha divided by average switches per cycle."""
    if oos_alpha is None or switches_per_cycle is None or switches_per_cycle == 0:
        return None
    return round(oos_alpha / switches_per_cycle, 6)


def _k1_reference(holder: pd.Series, ret: pd.Series) -> dict[str, Any]:
    """Return computed K1 holder-only reference diagnostics on this data snapshot."""
    tiers = pure_holder_tiers(holder)
    metrics, oos_alpha, cycle_alphas, cycle_switches = _evaluate_tiers(
        tiers, ret, HYSTERESIS_TIER_TO_PCT
    )
    switches_per_cycle = round(float(np.mean(cycle_switches)), 6) if cycle_switches else None
    return {
        "id": "k1_holder_behavior_pure_reference",
        "label": "K1 — holder behavior PURE",
        "rule": "STAY LONG if z(holder) > 0 else CASH",
        "fixed_reference_oos_median_alpha": K1_BASELINE_OOS_ALPHA,
        "computed_oos_median_alpha": oos_alpha,
        "full_sample": metrics["full_sample"],
        "cycle_metrics": metrics["cycle_metrics"],
        "oos_alpha_spread": [
            round(float(np.min(cycle_alphas)), 6),
            round(float(np.max(cycle_alphas)), 6),
        ]
        if cycle_alphas
        else [],
        "avg_regime_switches_per_cycle": switches_per_cycle,
        "alpha_per_switch": _alpha_per_switch(oos_alpha, switches_per_cycle),
    }


def evaluate_candidate(
    candidate: StickinessCandidate,
    holder: pd.Series,
    ret: pd.Series,
) -> dict[str, Any]:
    """Evaluate one fixed Phase M candidate full-sample and by BTC cycle."""
    tiers = _candidate_tiers(candidate, holder)
    tier_to_pct = _tier_to_pct(candidate)
    metrics, oos_alpha, cycle_alphas, cycle_switches = _evaluate_tiers(tiers, ret, tier_to_pct)
    switches_per_cycle = round(float(np.mean(cycle_switches)), 6) if cycle_switches else None

    return {
        "candidate": {
            "id": candidate.candidate_id,
            "label": candidate.label,
            "family": candidate.family,
            "rule_type": candidate.rule_type,
            "threshold": candidate.threshold,
            "ema_span_days": candidate.ema_span_days,
            "source": candidate.source,
            "rule": _rule_text(candidate),
            "pure_mode": True,
            "valuation_override": None,
            "tier_to_pct": tier_to_pct,
            "notes": candidate.notes,
        },
        **metrics,
        "oos_median_alpha": oos_alpha,
        "delta_vs_k1_reference_pp": (
            round(oos_alpha - K1_BASELINE_OOS_ALPHA, 6) if oos_alpha is not None else None
        ),
        "oos_alpha_spread": [
            round(float(np.min(cycle_alphas)), 6),
            round(float(np.max(cycle_alphas)), 6),
        ]
        if cycle_alphas
        else [],
        "avg_regime_switches_per_cycle": switches_per_cycle,
        "alpha_per_switch": _alpha_per_switch(oos_alpha, switches_per_cycle),
    }


def _best_candidate(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Return the result with the highest OOS median alpha."""
    ranked = [row for row in results if isinstance(row.get("oos_median_alpha"), int | float)]
    if not ranked:
        raise ValueError("no finite candidate OOS alpha results")
    ranked.sort(key=lambda row: (-float(row["oos_median_alpha"]), str(row["candidate"]["id"])))
    return ranked[0]


def _qualifies(row: dict[str, Any]) -> bool:
    """Return True if a candidate clears the Phase M investor-grade hurdle."""
    alpha = row.get("oos_median_alpha")
    switches = row.get("avg_regime_switches_per_cycle")
    return (
        isinstance(alpha, int | float)
        and isinstance(switches, int | float)
        and float(alpha) >= QUALIFYING_OOS_ALPHA
        and float(switches) < MAX_SWITCHES_PER_CYCLE
    )


def _select_qualifier(qualifiers: list[dict[str, Any]]) -> dict[str, Any]:
    """Select the preferred qualifying candidate by the Phase M product rule."""
    if not qualifiers:
        raise ValueError("no qualifying candidates")
    three_tier = [row for row in qualifiers if row["candidate"]["rule_type"] == "three_tier"]
    pool = three_tier if three_tier else qualifiers
    pool.sort(
        key=lambda row: (
            float(row["avg_regime_switches_per_cycle"]),
            -float(row["oos_median_alpha"]),
            str(row["candidate"]["id"]),
        )
    )
    return pool[0]


def _pareto_frontier(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return non-dominated alpha/switch trade-off rows."""
    rows = [
        row
        for row in results
        if isinstance(row.get("oos_median_alpha"), int | float)
        and isinstance(row.get("avg_regime_switches_per_cycle"), int | float)
    ]
    frontier = []
    for row in rows:
        alpha = float(row["oos_median_alpha"])
        switches = float(row["avg_regime_switches_per_cycle"])
        dominated = any(
            other is not row
            and float(other["oos_median_alpha"]) >= alpha
            and float(other["avg_regime_switches_per_cycle"]) <= switches
            and (
                float(other["oos_median_alpha"]) > alpha
                or float(other["avg_regime_switches_per_cycle"]) < switches
            )
            for other in rows
        )
        if not dominated:
            frontier.append(
                {
                    "candidate_id": row["candidate"]["id"],
                    "candidate_label": row["candidate"]["label"],
                    "oos_median_alpha": row["oos_median_alpha"],
                    "avg_regime_switches_per_cycle": row["avg_regime_switches_per_cycle"],
                    "alpha_per_switch": row["alpha_per_switch"],
                }
            )
    frontier.sort(key=lambda row: float(row["avg_regime_switches_per_cycle"]))
    return frontier


def _recommendation(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Apply the Phase M decision tree to stickiness results."""
    best = _best_candidate(results)
    qualifiers = [row for row in results if _qualifies(row)]

    if qualifiers:
        selected = _select_qualifier(qualifiers)
        branch = "1_investor_grade_candidate"
        action = f"productionize-{selected['candidate']['family'].lower()}"
        text = (
            f"Prefer {selected['candidate']['label']}: it reached "
            f"{float(selected['oos_median_alpha']):.1f}% OOS median alpha with "
            f"{float(selected['avg_regime_switches_per_cycle']):.1f} switches/cycle, "
            "clearing the >=20.0% alpha and <15 switches/cycle hurdles."
        )
    else:
        selected = None
        branch = "3_no_qualifier_pareto"
        action = "surface-alpha-vs-switches-tradeoff"
        text = (
            "No Phase M candidate cleared both >=20.0% OOS median alpha and "
            "<15 switches/cycle; surface the alpha-vs-switches Pareto frontier."
        )

    return {
        "baseline_id": "k1_holder_behavior_pure_reference",
        "k1_reference_oos_median_alpha": K1_BASELINE_OOS_ALPHA,
        "qualifying_oos_median_alpha": QUALIFYING_OOS_ALPHA,
        "max_switches_per_cycle": MAX_SWITCHES_PER_CYCLE,
        "best_candidate_id": best["candidate"]["id"],
        "best_candidate_label": best["candidate"]["label"],
        "best_oos_median_alpha": round(float(best["oos_median_alpha"]), 6),
        "best_avg_switches_per_cycle": best["avg_regime_switches_per_cycle"],
        "selected_candidate_id": selected["candidate"]["id"] if selected is not None else None,
        "selected_candidate_label": (
            selected["candidate"]["label"] if selected is not None else None
        ),
        "selected_oos_median_alpha": selected["oos_median_alpha"] if selected is not None else None,
        "selected_avg_switches_per_cycle": selected["avg_regime_switches_per_cycle"]
        if selected is not None
        else None,
        "selected_alpha_per_switch": selected["alpha_per_switch"] if selected is not None else None,
        "qualifying_candidate_ids": [row["candidate"]["id"] for row in qualifiers],
        "decision_tree_branch": branch,
        "action": action,
        "text": text,
        "pareto_frontier": _pareto_frontier(results),
    }


def run_optimization(
    data: pd.DataFrame,
    *,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    use_cache: bool = True,
    output_path: Path | None = None,
) -> dict[str, Any]:
    """Run the fixed Phase M stickiness comparison and optionally write JSON."""
    del cache_dir, use_cache
    ret = cast(pd.Series, data["btc_price"]).pct_change()
    holder = holder_behavior_composite(data)
    candidates = phase_m_candidates()
    results = [evaluate_candidate(candidate, holder, ret) for candidate in candidates]
    k1_reference = _k1_reference(holder, ret)

    payload = envelope(
        "phase_m_stickiness",
        {
            "k1_reference_oos_median_alpha": K1_BASELINE_OOS_ALPHA,
            "qualifying_oos_median_alpha": QUALIFYING_OOS_ALPHA,
            "max_switches_per_cycle": MAX_SWITCHES_PER_CYCLE,
            "methodology": {
                "walk_forward": (
                    "Each fixed holder-only pure rule is evaluated full-sample and separately "
                    "on each BTC_CYCLES window; no candidate is selected in-sample."
                ),
                "metric": "Out-of-sample median alpha across the four cycle results.",
                "pure_mode": (
                    "No valuation input and no valuation override in any Phase M candidate."
                ),
                "decision_rule": (
                    "Qualify if OOS median alpha is >=20.0% and average switches/cycle is <15. "
                    "If multiple qualify, prefer 3-tier M2 rows for LONG/CAUTION/CASH UX parity; "
                    "otherwise surface the alpha-vs-switches Pareto frontier."
                ),
                "hysteresis_state": (
                    "Initial valid state follows the sign of z(holder); CASH flips to STAY LONG "
                    "only above +T and STAY LONG flips to CASH only below -T."
                ),
                "ema_smoothing": (
                    f"M3 applies pandas ewm(span={EMA_SPAN_DAYS}, adjust=False).mean()."
                ),
            },
            "data_snapshot": {
                "rows": int(len(data)),
                "start": str(data.index.min()),
                "end": str(data.index.max()),
                "holder_non_nan": int(holder.notna().sum()),
            },
            "candidate_grid": {
                "candidate_count": len(results),
                "thresholds": list(STICKINESS_THRESHOLDS),
                "ema_span_days": EMA_SPAN_DAYS,
                "valuation_override": None,
                "modes": ["hysteresis", "three_tier", "ema_threshold"],
            },
            "k1_reference": k1_reference,
            "results": results,
            "recommendation": _recommendation(results),
        },
    )
    if output_path is not None:
        write_json(output_path, payload)
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare Phase M holder-only stickiness variants."
    )
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--output", type=Path, default=default_output_path("phase_m.json"))
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
