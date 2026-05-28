"""Phase P research: K1 3-tier bands plus confirmation variants.

This is a research-only follow-up to Phase K-O. It keeps the holder-only PURE
spine and tests only the final fixed decision-rule grid requested for Phase P:
3-tier CAUTION bands with confirmation and asymmetric binary thresholds.
Production data fetches, MROI construction, and dashboard code are untouched.
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
K1_BASELINE_MAX_DD = -60.3
K1_BASELINE_SWITCHES_PER_CYCLE = 29.8
O1_BASELINE_OOS_ALPHA = 17.2
O1_BASELINE_SWITCHES_PER_CYCLE = 19.2
QUALIFYING_OOS_ALPHA = 19.0
MAX_SWITCHES_PER_CYCLE = 20.0
BINARY_TIER_TO_PCT = {"CASH": 0.0, "STAY LONG": 100.0}
THREE_TIER_75_TO_PCT = {"CASH": 0.0, "CAUTION": 75.0, "STAY LONG": 100.0}
THREE_TIER_50_TO_PCT = {"CASH": 0.0, "CAUTION": 50.0, "STAY LONG": 100.0}


@dataclass(frozen=True)
class PhasePCandidate:
    """Fixed Phase P candidate definition."""

    candidate_id: str
    label: str
    family: str
    rule_type: str
    source: str
    notes: str
    threshold: float | None = None
    confirmation_days: int | None = None
    caution_allocation_pct: float | None = None
    entry_threshold: float | None = None
    exit_threshold: float | None = None


def phase_p_candidates() -> list[PhasePCandidate]:
    """Return the fixed Phase P holder-only candidate set."""
    return [
        PhasePCandidate(
            candidate_id="p1_three_tier_0_3_confirmation_3d",
            label="P1 — 3-tier ±0.3 + N=3",
            family="P1",
            rule_type="three_tier_confirmation",
            threshold=0.3,
            confirmation_days=3,
            caution_allocation_pct=75.0,
            source="Production holder_behavior_composite",
            notes=(
                "STAY LONG above +0.3, CASH below -0.3, CAUTION at 75%; "
                "require 3-day confirmation on band crossings."
            ),
        ),
        PhasePCandidate(
            candidate_id="p2_three_tier_0_5_confirmation_3d",
            label="P2 — 3-tier ±0.5 + N=3",
            family="P2",
            rule_type="three_tier_confirmation",
            threshold=0.5,
            confirmation_days=3,
            caution_allocation_pct=75.0,
            source="Production holder_behavior_composite",
            notes=(
                "STAY LONG above +0.5, CASH below -0.5, CAUTION at 75%; "
                "require 3-day confirmation on band crossings."
            ),
        ),
        PhasePCandidate(
            candidate_id="p3_three_tier_0_3_confirmation_5d",
            label="P3 — 3-tier ±0.3 + N=5",
            family="P3",
            rule_type="three_tier_confirmation",
            threshold=0.3,
            confirmation_days=5,
            caution_allocation_pct=75.0,
            source="Production holder_behavior_composite",
            notes=(
                "STAY LONG above +0.3, CASH below -0.3, CAUTION at 75%; "
                "require 5-day confirmation on band crossings."
            ),
        ),
        PhasePCandidate(
            candidate_id="p4_asymmetric_long_0_cash_neg_0_3",
            label="P4 — asymmetric sticky LONG",
            family="P4",
            rule_type="asymmetric_binary",
            entry_threshold=0.0,
            exit_threshold=-0.3,
            source="Production holder_behavior_composite",
            notes=(
                "LONG at z(holder)>0; CASH at z(holder)<-0.3; "
                "hold current state between thresholds."
            ),
        ),
        PhasePCandidate(
            candidate_id="p5_asymmetric_long_0_3_cash_0",
            label="P5 — asymmetric conservative entry",
            family="P5",
            rule_type="asymmetric_binary",
            entry_threshold=0.3,
            exit_threshold=0.0,
            source="Production holder_behavior_composite",
            notes=(
                "LONG at z(holder)>+0.3; CASH at z(holder)<0; "
                "hold current state between thresholds."
            ),
        ),
        PhasePCandidate(
            candidate_id="p6_three_tier_0_3_confirmation_3d_caution_50",
            label="P6 — 3-tier ±0.3 + N=3, 50% CAUTION",
            family="P6",
            rule_type="three_tier_confirmation",
            threshold=0.3,
            confirmation_days=3,
            caution_allocation_pct=50.0,
            source="Production holder_behavior_composite",
            notes=(
                "STAY LONG above +0.3, CASH below -0.3, CAUTION at 50%; "
                "require 3-day confirmation on band crossings."
            ),
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


def raw_three_tier_tiers(holder: pd.Series, threshold: float) -> pd.Series:
    """Return the unconfirmed LONG/CAUTION/CASH tier proposal for holder bands."""
    tiers = _empty_tiers(holder.index)
    tiers = tiers.mask(holder < -threshold, "CASH")
    tiers = tiers.mask((holder >= -threshold) & (holder <= threshold), "CAUTION")
    tiers = tiers.mask(holder > threshold, "STAY LONG")
    return tiers.where(holder.notna())


def confirmation_tiers(proposed_tiers: pd.Series, confirmation_days: int) -> pd.Series:
    """Return tiers after confirming each new proposed tier for N valid days."""
    tiers = _empty_tiers(proposed_tiers.index)
    current_regime: str | None = None
    pending_target: str | None = None
    pending_flip_count = 0

    for index, value in proposed_tiers.items():
        if pd.isna(value):
            continue
        proposed = str(value)
        if current_regime is None:
            current_regime = proposed
            pending_target = None
            pending_flip_count = 0
        elif proposed == current_regime:
            pending_target = None
            pending_flip_count = 0
        else:
            if pending_target != proposed:
                pending_target = proposed
                pending_flip_count = 1
            else:
                pending_flip_count += 1
            if pending_flip_count >= confirmation_days:
                current_regime = proposed
                pending_target = None
                pending_flip_count = 0
        tiers.loc[index] = current_regime

    return tiers.where(proposed_tiers.notna())


def confirmation_events(proposed_tiers: pd.Series, confirmation_days: int) -> list[dict[str, Any]]:
    """Return confirmed tier-change events from the N-day confirmation state machine."""
    events: list[dict[str, Any]] = []
    current_regime: str | None = None
    pending_target: str | None = None
    pending_start: pd.Timestamp | None = None
    pending_flip_count = 0

    for index, value in proposed_tiers.items():
        if pd.isna(value):
            continue
        timestamp = cast(pd.Timestamp, index)
        proposed = str(value)
        if current_regime is None:
            current_regime = proposed
            continue
        if proposed == current_regime:
            pending_target = None
            pending_start = None
            pending_flip_count = 0
            continue

        if pending_target != proposed:
            pending_target = proposed
            pending_start = timestamp
            pending_flip_count = 1
        else:
            pending_flip_count += 1

        if pending_flip_count >= confirmation_days:
            previous = current_regime
            current_regime = proposed
            events.append(
                {
                    "confirmed_date": str(timestamp.date()),
                    "pending_start_date": str(pending_start.date())
                    if pending_start is not None
                    else str(timestamp.date()),
                    "from_regime": previous,
                    "to_regime": current_regime,
                    "confirmation_days": confirmation_days,
                }
            )
            pending_target = None
            pending_start = None
            pending_flip_count = 0

    return events


def asymmetric_tiers(holder: pd.Series, entry_threshold: float, exit_threshold: float) -> pd.Series:
    """Return binary stateful tiers using separate LONG-entry and CASH-exit thresholds."""
    tiers = _empty_tiers(holder.index)
    state: str | None = None
    for index, value in holder.items():
        if pd.isna(value):
            continue
        z_value = float(value)
        if state is None:
            state = "STAY LONG" if z_value > entry_threshold else "CASH"
        elif state == "CASH" and z_value > entry_threshold:
            state = "STAY LONG"
        elif state == "STAY LONG" and z_value < exit_threshold:
            state = "CASH"
        tiers.loc[index] = state
    return tiers.where(holder.notna())


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


def _tier_share(tiers: pd.Series, tier: str) -> float | None:
    """Return share of valid days spent in one tier."""
    valid = tiers.dropna().astype("object")
    if valid.empty:
        return None
    return float(valid.eq(tier).mean() * 100)


def _switch_count(tiers: pd.Series) -> int | None:
    """Return raw tier-transition count after dropping unscored days."""
    valid = tiers.dropna().astype("object")
    if valid.empty:
        return None
    transitions = valid.ne(valid.shift()).fillna(False)
    return max(int(transitions.sum() - 1), 0)


def _diagnostics(tiers: pd.Series) -> dict[str, float | int | None]:
    """Return Phase P non-return diagnostics for a tier series."""
    cash_share = _tier_share(tiers, "CASH")
    caution_share = _tier_share(tiers, "CAUTION")
    return {
        "time_in_cash_pct": round(cash_share, 6) if cash_share is not None else None,
        "time_in_caution_pct": round(caution_share, 6) if caution_share is not None else None,
        "regime_switches": _switch_count(tiers),
    }


def _tier_to_pct(candidate: PhasePCandidate) -> dict[str, float]:
    """Return allocation mapping for one Phase P candidate."""
    if candidate.rule_type == "asymmetric_binary":
        return BINARY_TIER_TO_PCT
    if candidate.caution_allocation_pct == 50.0:
        return THREE_TIER_50_TO_PCT
    return THREE_TIER_75_TO_PCT


def _candidate_tiers(candidate: PhasePCandidate, holder: pd.Series) -> pd.Series:
    """Build tiers for one Phase P candidate."""
    if candidate.rule_type == "three_tier_confirmation":
        proposed = raw_three_tier_tiers(holder, cast(float, candidate.threshold))
        return confirmation_tiers(proposed, cast(int, candidate.confirmation_days))
    if candidate.rule_type == "asymmetric_binary":
        return asymmetric_tiers(
            holder,
            cast(float, candidate.entry_threshold),
            cast(float, candidate.exit_threshold),
        )
    raise ValueError(f"unknown rule_type {candidate.rule_type!r}")


def _rule_text(candidate: PhasePCandidate) -> str:
    """Return a compact rule description for one Phase P candidate."""
    if candidate.rule_type == "three_tier_confirmation":
        threshold = cast(float, candidate.threshold)
        days = cast(int, candidate.confirmation_days)
        caution = cast(float, candidate.caution_allocation_pct)
        return (
            f"LONG if z > +{threshold:.1f}; CASH if z < -{threshold:.1f}; "
            f"CAUTION {caution:.0f}% between; confirm each new band for {days} days"
        )
    entry = cast(float, candidate.entry_threshold)
    exit_ = cast(float, candidate.exit_threshold)
    return f"LONG above {entry:+.1f}; CASH below {exit_:+.1f}; hold between thresholds"


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


def _cycle4_name() -> str:
    """Return the strict holdout cycle name."""
    return list(BTC_CYCLES)[-1]


def _is_cycle_names() -> list[str]:
    """Return the strict in-sample cycle names."""
    return list(BTC_CYCLES)[:-1]


def _median_alpha_for_cycles(
    cycle_metrics: dict[str, dict[str, float | int | None]], cycle_names: Sequence[str]
) -> float | None:
    """Return median alpha across selected cycle metrics."""
    alphas: list[float] = []
    for cycle_name in cycle_names:
        alpha = cycle_metrics[cycle_name].get("alpha")
        if isinstance(alpha, int | float):
            alphas.append(float(alpha))
    return round(float(np.median(alphas)), 6) if alphas else None


def _avg_switches_for_cycles(
    cycle_metrics: dict[str, dict[str, float | int | None]], cycle_names: Sequence[str]
) -> float | None:
    """Return average regime switches across selected cycle metrics."""
    switches: list[int] = []
    for cycle_name in cycle_names:
        value = cycle_metrics[cycle_name].get("regime_switches")
        if isinstance(value, int):
            switches.append(value)
    return round(float(np.mean(switches)), 6) if switches else None


def _k1_reference(holder: pd.Series, ret: pd.Series) -> dict[str, Any]:
    """Return computed K1 holder-only reference diagnostics on this data snapshot."""
    tiers = pure_holder_tiers(holder)
    metrics, oos_alpha, cycle_alphas, cycle_switches = _evaluate_tiers(
        tiers, ret, BINARY_TIER_TO_PCT
    )
    switches_per_cycle = round(float(np.mean(cycle_switches)), 6) if cycle_switches else None
    return {
        "id": "k1_holder_behavior_pure_reference",
        "label": "K1 — holder behavior PURE",
        "rule": "STAY LONG if z(holder) > 0 else CASH",
        "fixed_reference_oos_median_alpha": K1_BASELINE_OOS_ALPHA,
        "fixed_reference_max_drawdown": K1_BASELINE_MAX_DD,
        "fixed_reference_switches_per_cycle": K1_BASELINE_SWITCHES_PER_CYCLE,
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
    candidate: PhasePCandidate,
    holder: pd.Series,
    ret: pd.Series,
) -> dict[str, Any]:
    """Evaluate one fixed Phase P candidate full-sample and by BTC cycle."""
    tiers = _candidate_tiers(candidate, holder)
    tier_to_pct = _tier_to_pct(candidate)
    metrics, oos_alpha, cycle_alphas, cycle_switches = _evaluate_tiers(tiers, ret, tier_to_pct)
    switches_per_cycle = round(float(np.mean(cycle_switches)), 6) if cycle_switches else None
    cycle_metrics = cast(dict[str, dict[str, float | int | None]], metrics["cycle_metrics"])
    cycle4_name = _cycle4_name()
    cycle4_metrics = cycle_metrics[cycle4_name]
    cycle4_alpha = cycle4_metrics.get("alpha")
    strict_cycle4_alpha = float(cycle4_alpha) if isinstance(cycle4_alpha, int | float) else None
    full_max_dd = metrics["full_sample"].get("strat_dd")
    max_dd = float(full_max_dd) if isinstance(full_max_dd, int | float) else None
    proposed = None
    if candidate.rule_type == "three_tier_confirmation":
        proposed = raw_three_tier_tiers(holder, cast(float, candidate.threshold))

    return {
        "candidate": {
            "id": candidate.candidate_id,
            "label": candidate.label,
            "family": candidate.family,
            "rule_type": candidate.rule_type,
            "threshold": candidate.threshold,
            "confirmation_days": candidate.confirmation_days,
            "caution_allocation_pct": candidate.caution_allocation_pct,
            "entry_threshold": candidate.entry_threshold,
            "exit_threshold": candidate.exit_threshold,
            "source": candidate.source,
            "rule": _rule_text(candidate),
            "pure_mode": True,
            "valuation_override": None,
            "tier_to_pct": tier_to_pct,
            "notes": candidate.notes,
        },
        **metrics,
        "standard_walk_forward": {
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
        },
        "strict_holdout": {
            "is_cycles": _is_cycle_names(),
            "oos_cycle": cycle4_name,
            "is_median_alpha": _median_alpha_for_cycles(cycle_metrics, _is_cycle_names()),
            "is_avg_regime_switches_per_cycle": _avg_switches_for_cycles(
                cycle_metrics, _is_cycle_names()
            ),
            "cycle4_alpha": round(strict_cycle4_alpha, 6)
            if strict_cycle4_alpha is not None
            else None,
            "cycle4_metrics": cycle4_metrics,
            "cycle4_delta_vs_k1_reference_pp": round(
                strict_cycle4_alpha - K1_BASELINE_OOS_ALPHA, 6
            )
            if strict_cycle4_alpha is not None
            else None,
        },
        "oos_median_alpha": oos_alpha,
        "delta_vs_k1_reference_pp": (
            round(oos_alpha - K1_BASELINE_OOS_ALPHA, 6) if oos_alpha is not None else None
        ),
        "max_drawdown_reduction_vs_k1_pp": round(max_dd - K1_BASELINE_MAX_DD, 6)
        if max_dd is not None
        else None,
        "oos_alpha_spread": [
            round(float(np.min(cycle_alphas)), 6),
            round(float(np.max(cycle_alphas)), 6),
        ]
        if cycle_alphas
        else [],
        "avg_regime_switches_per_cycle": switches_per_cycle,
        "alpha_per_switch": _alpha_per_switch(oos_alpha, switches_per_cycle),
        "cycle4_confirmation_events": [
            event
            for event in (
                confirmation_events(proposed, cast(int, candidate.confirmation_days))
                if proposed is not None
                else []
            )
            if pd.Timestamp(event["confirmed_date"]) >= pd.Timestamp(BTC_CYCLES[cycle4_name][0])
            and pd.Timestamp(event["confirmed_date"]) <= pd.Timestamp(BTC_CYCLES[cycle4_name][1])
        ],
    }


def _is_tier_variant(row: dict[str, Any]) -> bool:
    """Return True for LONG/CAUTION/CASH candidates."""
    return row["candidate"]["rule_type"] == "three_tier_confirmation"


def _best_standard_candidate(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Return the result with the highest standard walk-forward OOS median alpha."""
    ranked = [row for row in results if isinstance(row.get("oos_median_alpha"), int | float)]
    if not ranked:
        raise ValueError("no finite candidate OOS alpha results")
    ranked.sort(
        key=lambda row: (
            -float(row["oos_median_alpha"]),
            float(row["avg_regime_switches_per_cycle"]),
            str(row["candidate"]["id"]),
        )
    )
    return ranked[0]


def _strict_selected_candidate(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Select candidate using only cycles 1-3 median alpha."""
    ranked = [
        row
        for row in results
        if isinstance(
            cast(dict[str, Any], row["strict_holdout"]).get("is_median_alpha"), int | float
        )
    ]
    if not ranked:
        raise ValueError("no finite strict in-sample alpha results")
    ranked.sort(
        key=lambda row: (
            -float(cast(dict[str, Any], row["strict_holdout"])["is_median_alpha"]),
            not _is_tier_variant(row),
            float(row["avg_regime_switches_per_cycle"]),
            str(row["candidate"]["id"]),
        )
    )
    return ranked[0]


def _qualifies(row: dict[str, Any]) -> bool:
    """Return True if a candidate clears the Phase P adoption hurdle."""
    standard = cast(dict[str, Any], row["standard_walk_forward"])
    strict = cast(dict[str, Any], row["strict_holdout"])
    standard_alpha = standard.get("oos_median_alpha")
    cycle4_alpha = strict.get("cycle4_alpha")
    switches = row.get("avg_regime_switches_per_cycle")
    return (
        isinstance(standard_alpha, int | float)
        and isinstance(cycle4_alpha, int | float)
        and isinstance(switches, int | float)
        and float(standard_alpha) >= QUALIFYING_OOS_ALPHA
        and float(cycle4_alpha) >= QUALIFYING_OOS_ALPHA
        and float(switches) < MAX_SWITCHES_PER_CYCLE
    )


def _select_qualifier(qualifiers: list[dict[str, Any]]) -> dict[str, Any]:
    """Select the preferred qualifying candidate by the Phase P product rule."""
    if not qualifiers:
        raise ValueError("no qualifying candidates")
    qualifiers.sort(
        key=lambda row: (
            not _is_tier_variant(row),
            -float(row["standard_walk_forward"]["oos_median_alpha"]),
            -float(row["strict_holdout"]["cycle4_alpha"]),
            float(row["avg_regime_switches_per_cycle"]),
            str(row["candidate"]["id"]),
        )
    )
    return qualifiers[0]


def _track_qualifiers(results: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Return candidate ids that qualify individual validation tracks."""
    standard_ids = []
    strict_ids = []
    switch_ids = []
    for row in results:
        standard = cast(dict[str, Any], row["standard_walk_forward"])
        strict = cast(dict[str, Any], row["strict_holdout"])
        if isinstance(standard.get("oos_median_alpha"), int | float) and float(
            standard["oos_median_alpha"]
        ) >= QUALIFYING_OOS_ALPHA:
            standard_ids.append(str(row["candidate"]["id"]))
        if isinstance(strict.get("cycle4_alpha"), int | float) and float(
            strict["cycle4_alpha"]
        ) >= QUALIFYING_OOS_ALPHA:
            strict_ids.append(str(row["candidate"]["id"]))
        if isinstance(row.get("avg_regime_switches_per_cycle"), int | float) and float(
            row["avg_regime_switches_per_cycle"]
        ) < MAX_SWITCHES_PER_CYCLE:
            switch_ids.append(str(row["candidate"]["id"]))
    return {"standard": standard_ids, "strict_cycle4": strict_ids, "switches": switch_ids}


def _recommendation(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Apply the Phase P decision tree to tier+confirmation results."""
    standard_best = _best_standard_candidate(results)
    strict_selected = _strict_selected_candidate(results)
    qualifiers = [row for row in results if _qualifies(row)]
    track_qualifiers = _track_qualifiers(results)
    tracks_agree = standard_best["candidate"]["id"] == strict_selected["candidate"]["id"]

    if qualifiers:
        selected = _select_qualifier(qualifiers)
        branch = "1_adopt_phase_p_winner"
        action = f"productionize-{selected['candidate']['family'].lower()}"
        text = (
            f"Prefer {selected['candidate']['label']}: it maintained "
            f"{float(selected['standard_walk_forward']['oos_median_alpha']):.1f}% standard-WF "
            f"OOS alpha and {float(selected['strict_holdout']['cycle4_alpha']):.1f}% strict "
            f"cycle-4 alpha with {float(selected['avg_regime_switches_per_cycle']):.1f} "
            "switches/cycle."
        )
    else:
        selected = None
        if track_qualifiers["standard"] or track_qualifiers["strict_cycle4"]:
            branch = "2_tracks_disagree_no_dual_qualifier"
            action = "surface-disagreement-use-strict-holdout"
            text = (
                "No candidate cleared both validation tracks with <20 switches/cycle. "
                "Some rows cleared one alpha track, so trust the strict holdout if the tracks "
                "disagree and treat K1 versus O1 N=3 as the production judgment call."
            )
        else:
            branch = "3_no_phase_p_winner"
            action = "commit-to-k1-or-o1-product-judgment"
            text = (
                "No Phase P candidate cleared the >=19.0% standard-WF alpha, >=19.0% strict "
                "cycle-4 alpha, and <20 switches/cycle hurdle; K1 or O1 N=3 is the call."
            )

    return {
        "baseline_id": "k1_holder_behavior_pure_reference",
        "k1_reference_oos_median_alpha": K1_BASELINE_OOS_ALPHA,
        "k1_reference_max_drawdown": K1_BASELINE_MAX_DD,
        "k1_reference_switches_per_cycle": K1_BASELINE_SWITCHES_PER_CYCLE,
        "o1_reference_oos_median_alpha": O1_BASELINE_OOS_ALPHA,
        "o1_reference_switches_per_cycle": O1_BASELINE_SWITCHES_PER_CYCLE,
        "qualifying_oos_alpha": QUALIFYING_OOS_ALPHA,
        "max_switches_per_cycle": MAX_SWITCHES_PER_CYCLE,
        "standard_best_candidate_id": standard_best["candidate"]["id"],
        "standard_best_candidate_label": standard_best["candidate"]["label"],
        "standard_best_oos_median_alpha": standard_best["standard_walk_forward"][
            "oos_median_alpha"
        ],
        "strict_selected_candidate_id": strict_selected["candidate"]["id"],
        "strict_selected_candidate_label": strict_selected["candidate"]["label"],
        "strict_selected_is_median_alpha": strict_selected["strict_holdout"]["is_median_alpha"],
        "strict_selected_cycle4_alpha": strict_selected["strict_holdout"]["cycle4_alpha"],
        "tracks_agree_on_best_candidate": tracks_agree,
        "selected_candidate_id": selected["candidate"]["id"] if selected is not None else None,
        "selected_candidate_label": selected["candidate"]["label"]
        if selected is not None
        else None,
        "selected_standard_oos_median_alpha": selected["standard_walk_forward"][
            "oos_median_alpha"
        ]
        if selected is not None
        else None,
        "selected_strict_cycle4_alpha": selected["strict_holdout"]["cycle4_alpha"]
        if selected is not None
        else None,
        "selected_avg_switches_per_cycle": selected["avg_regime_switches_per_cycle"]
        if selected is not None
        else None,
        "qualifying_candidate_ids": [row["candidate"]["id"] for row in qualifiers],
        "single_track_qualifying_candidate_ids": track_qualifiers,
        "decision_tree_branch": branch,
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
    """Run the fixed Phase P tier+confirmation comparison and optionally write JSON."""
    del cache_dir, use_cache
    ret = cast(pd.Series, data["btc_price"]).pct_change()
    holder = holder_behavior_composite(data)
    candidates = phase_p_candidates()
    results = [evaluate_candidate(candidate, holder, ret) for candidate in candidates]
    k1_reference = _k1_reference(holder, ret)

    payload = envelope(
        "phase_p_tier_confirmation",
        {
            "k1_reference_oos_median_alpha": K1_BASELINE_OOS_ALPHA,
            "k1_reference_max_drawdown": K1_BASELINE_MAX_DD,
            "k1_reference_switches_per_cycle": K1_BASELINE_SWITCHES_PER_CYCLE,
            "o1_reference_oos_median_alpha": O1_BASELINE_OOS_ALPHA,
            "o1_reference_switches_per_cycle": O1_BASELINE_SWITCHES_PER_CYCLE,
            "qualifying_oos_alpha": QUALIFYING_OOS_ALPHA,
            "max_switches_per_cycle": MAX_SWITCHES_PER_CYCLE,
            "methodology": {
                "standard_walk_forward": (
                    "Each fixed holder-only pure candidate is evaluated full-sample and "
                    "separately on each BTC_CYCLES window; the headline is median alpha "
                    "across all four cycles for comparability with Phase K-O."
                ),
                "strict_is_oos_holdout": (
                    "Select the best candidate using only cycles 1-3 median alpha, then "
                    "evaluate that selected candidate once on cycle 4 (2025-now). If the "
                    "tracks disagree, trust the strict holdout."
                ),
                "metric": (
                    "Annualized alpha vs BTC buy-and-hold, plus switches/cycle, time in "
                    "cash, time in CAUTION where applicable, alpha-per-switch, max drawdown, "
                    "and cycle-4 confirmation dates."
                ),
                "pure_mode": (
                    "No valuation input, BTC/equity input, or valuation override in any "
                    "Phase P candidate. Base spine is z(holder_behavior)."
                ),
                "confirmation_state": (
                    "For P1/P2/P3/P6, first map z(holder) into raw LONG/CAUTION/CASH bands. "
                    "Initial valid state follows the raw band. When the proposed band equals "
                    "the current state, reset the pending count; when a new proposed band "
                    "differs, count consecutive observations of that proposed target and flip "
                    "only when pending_flip_count >= N."
                ),
                "asymmetric_state": (
                    "For P4/P5, CASH flips to STAY LONG only above the entry threshold and "
                    "STAY LONG flips to CASH only below the exit threshold."
                ),
                "decision_rule": (
                    "Adopt if a candidate has >=19.0% standard OOS median alpha, >=19.0% "
                    "strict cycle-4 alpha, and <20 switches/cycle. Prefer tier variants over "
                    "asymmetric variants for LONG/CAUTION/CASH vocabulary parity."
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
                "thresholds": [0.3, 0.5],
                "confirmation_days": [3, 5],
                "caution_allocation_pct": [75.0, 50.0],
                "valuation_override": None,
                "modes": ["three_tier_confirmation", "asymmetric_binary"],
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
        description="Compare Phase P K1 tier+confirmation and asymmetric variants."
    )
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--output", type=Path, default=default_output_path("phase_p.json"))
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
