"""Phase N research: K1 with euphoria-peak overlays.

This is a research-only follow-up to Phase K/L/M. It keeps the holder-only PURE
spine and tests asymmetric extreme-high and extreme-low overlays. Production data
fetches, MROI construction, and dashboard code are untouched.
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
WITHIN_K1_ALPHA_PP = 1.0
STICKY_EUPHORIA_DAYS = 30
BINARY_TIER_TO_PCT = {"CASH": 0.0, "STAY LONG": 100.0}
CAUTION_TIER_TO_PCT = {"CASH": 0.0, "CAUTION": 75.0, "STAY LONG": 100.0}
EUPHORIA_THRESHOLDS: tuple[float, ...] = (1.5, 1.75, 2.0, 2.25)


@dataclass(frozen=True)
class EuphoriaCandidate:
    """Fixed Phase N euphoria-overlay candidate definition."""

    candidate_id: str
    label: str
    family: str
    rule_type: str
    high_threshold: float | None
    low_threshold: float | None
    source: str
    notes: str
    sticky_days: int | None = None


def phase_n_candidates() -> list[EuphoriaCandidate]:
    """Return the fixed Phase N holder-only euphoria-overlay candidate set."""
    n1 = [
        EuphoriaCandidate(
            candidate_id=f"n1{suffix}_k1_euphoria_cash_{str(threshold).replace('.', '_')}",
            label=f"N1{suffix} — euphoria CASH z>{threshold:g}",
            family=f"N1{suffix}",
            rule_type="euphoria_cash",
            high_threshold=threshold,
            low_threshold=None,
            source="Production holder_behavior_composite",
            notes=(
                "K1 holder rule, but force CASH when z(holder_behavior) is above "
                f"+{threshold:g}."
            ),
        )
        for suffix, threshold in zip(("a", "b", "c", "d"), EUPHORIA_THRESHOLDS, strict=True)
    ]
    return [
        *n1,
        EuphoriaCandidate(
            candidate_id="n2_k1_euphoria_caution_2_0",
            label="N2 — euphoria CAUTION z>2.0",
            family="N2",
            rule_type="euphoria_caution",
            high_threshold=2.0,
            low_threshold=None,
            source="Production holder_behavior_composite",
            notes="K1 holder rule, but reduce to 75% CAUTION when z(holder_behavior) > +2.0.",
        ),
        EuphoriaCandidate(
            candidate_id="n3_k1_sticky_euphoria_cash_2_0_30d",
            label="N3 — sticky euphoria CASH z>2.0",
            family="N3",
            rule_type="sticky_euphoria_cash",
            high_threshold=2.0,
            low_threshold=None,
            source="Production holder_behavior_composite",
            notes=(
                "K1 holder rule, but once z(holder_behavior) > +2.0, force CASH "
                f"for at least {STICKY_EUPHORIA_DAYS} valid observations."
            ),
            sticky_days=STICKY_EUPHORIA_DAYS,
        ),
        EuphoriaCandidate(
            candidate_id="n4_k1_extreme_low_contrarian_long",
            label="N4 — extreme-low contrarian LONG",
            family="N4",
            rule_type="contrarian_low_long",
            high_threshold=None,
            low_threshold=-2.0,
            source="Production holder_behavior_composite",
            notes="K1 holder rule, but force STAY LONG when z(holder_behavior) < -2.0.",
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


def euphoria_cash_tiers(holder: pd.Series, threshold: float) -> pd.Series:
    """Return K1 tiers with an extreme-high force-CASH override."""
    tiers = pure_holder_tiers(holder)
    tiers = tiers.mask(holder > threshold, "CASH")
    return tiers.where(holder.notna())


def euphoria_caution_tiers(holder: pd.Series, threshold: float) -> pd.Series:
    """Return K1 tiers with an extreme-high 75% CAUTION override."""
    tiers = pure_holder_tiers(holder)
    tiers = tiers.mask(holder > threshold, "CAUTION")
    return tiers.where(holder.notna())


def sticky_euphoria_cash_tiers(holder: pd.Series, threshold: float, sticky_days: int) -> pd.Series:
    """Return K1 tiers with a rolling minimum CASH window after euphoria."""
    tiers = _empty_tiers(holder.index)
    remaining_cash_days = 0
    for index, value in holder.items():
        if pd.isna(value):
            continue
        z_value = float(value)
        if z_value > threshold:
            remaining_cash_days = sticky_days
        if remaining_cash_days > 0:
            tiers.loc[index] = "CASH"
            remaining_cash_days -= 1
        else:
            tiers.loc[index] = "STAY LONG" if z_value > 0.0 else "CASH"
    return tiers.where(holder.notna())


def contrarian_low_long_tiers(holder: pd.Series, threshold: float) -> pd.Series:
    """Return K1 tiers with an extreme-low force-LONG sanity-check override."""
    tiers = pure_holder_tiers(holder)
    tiers = tiers.mask(holder < threshold, "STAY LONG")
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
    """Return Phase N non-return diagnostics for a tier series."""
    cash_share = _cash_share(tiers)
    return {
        "time_in_cash_pct": round(cash_share, 6) if cash_share is not None else None,
        "regime_switches": _switch_count(tiers),
    }


def _tier_to_pct(candidate: EuphoriaCandidate) -> dict[str, float]:
    """Return allocation mapping for one Phase N candidate."""
    if candidate.rule_type == "euphoria_caution":
        return CAUTION_TIER_TO_PCT
    return BINARY_TIER_TO_PCT


def _candidate_tiers(candidate: EuphoriaCandidate, holder: pd.Series) -> pd.Series:
    """Build tiers for one Phase N candidate."""
    if candidate.rule_type == "euphoria_cash":
        return euphoria_cash_tiers(holder, cast(float, candidate.high_threshold))
    if candidate.rule_type == "euphoria_caution":
        return euphoria_caution_tiers(holder, cast(float, candidate.high_threshold))
    if candidate.rule_type == "sticky_euphoria_cash":
        return sticky_euphoria_cash_tiers(
            holder,
            cast(float, candidate.high_threshold),
            cast(int, candidate.sticky_days),
        )
    if candidate.rule_type == "contrarian_low_long":
        return contrarian_low_long_tiers(holder, cast(float, candidate.low_threshold))
    raise ValueError(f"unknown rule_type {candidate.rule_type!r}")


def _rule_text(candidate: EuphoriaCandidate) -> str:
    """Return a compact rule description for one Phase N candidate."""
    if candidate.rule_type == "euphoria_cash":
        threshold = cast(float, candidate.high_threshold)
        return f"K1, but CASH when z(holder) > +{threshold:g}"
    if candidate.rule_type == "euphoria_caution":
        threshold = cast(float, candidate.high_threshold)
        return f"K1, but CAUTION 75% when z(holder) > +{threshold:g}"
    if candidate.rule_type == "sticky_euphoria_cash":
        threshold = cast(float, candidate.high_threshold)
        days = cast(int, candidate.sticky_days)
        return f"K1, but CASH for {days} days after z(holder) > +{threshold:g}"
    threshold = cast(float, candidate.low_threshold)
    return f"K1, but LONG when z(holder) < {threshold:g}"


def _event_windows(condition: pd.Series) -> list[dict[str, Any]]:
    """Return contiguous event windows for a boolean trigger condition."""
    events: list[dict[str, Any]] = []
    active = False
    start: pd.Timestamp | None = None
    last: pd.Timestamp | None = None
    days = 0
    for index, value in condition.fillna(False).items():
        triggered = bool(value)
        timestamp = cast(pd.Timestamp, index)
        if triggered and not active:
            active = True
            start = timestamp
            days = 1
        elif triggered:
            days += 1
        elif active:
            events.append(
                {
                    "start": str(start.date()) if start is not None else None,
                    "end": str(last.date()) if last is not None else None,
                    "days": days,
                }
            )
            active = False
            start = None
            days = 0
        last = timestamp
    if active:
        events.append(
            {
                "start": str(start.date()) if start is not None else None,
                "end": str(last.date()) if last is not None else None,
                "days": days,
            }
        )
    return events


def _trigger_condition(candidate: EuphoriaCandidate, holder: pd.Series) -> pd.Series:
    """Return the raw event trigger condition for one candidate."""
    if candidate.high_threshold is not None:
        return holder > candidate.high_threshold
    if candidate.low_threshold is not None:
        return holder < candidate.low_threshold
    return pd.Series(False, index=holder.index)


def _trigger_summary(candidate: EuphoriaCandidate, holder: pd.Series) -> dict[str, Any]:
    """Return event counts and event windows by BTC cycle for one candidate."""
    condition = _trigger_condition(candidate, holder)
    by_cycle: dict[str, dict[str, Any]] = {}
    for cycle_name, (start, end) in BTC_CYCLES.items():
        mask = _cycle_mask(holder.index, start, end)
        events = _event_windows(condition.loc[mask])
        by_cycle[cycle_name] = {
            "event_count": len(events),
            "event_start_dates": [event["start"] for event in events],
            "events": events,
        }
    all_events = _event_windows(condition)
    trigger_type = (
        "extreme_high_euphoria" if candidate.high_threshold is not None else "extreme_low"
    )
    return {
        "trigger_type": trigger_type,
        "threshold": candidate.high_threshold
        if candidate.high_threshold is not None
        else candidate.low_threshold,
        "total_event_count": len(all_events),
        "total_trigger_days": int(condition.fillna(False).sum()),
        "events_by_cycle": by_cycle,
    }


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


def _max_drawdown_reduction(max_drawdown: float | None) -> float | None:
    """Return max-drawdown improvement versus the fixed K1 baseline."""
    if max_drawdown is None or not math.isfinite(max_drawdown):
        return None
    return round(float(max_drawdown) - K1_BASELINE_MAX_DD, 6)


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
    candidate: EuphoriaCandidate,
    holder: pd.Series,
    ret: pd.Series,
) -> dict[str, Any]:
    """Evaluate one fixed Phase N candidate full-sample and by BTC cycle."""
    tiers = _candidate_tiers(candidate, holder)
    tier_to_pct = _tier_to_pct(candidate)
    metrics, oos_alpha, cycle_alphas, cycle_switches = _evaluate_tiers(tiers, ret, tier_to_pct)
    switches_per_cycle = round(float(np.mean(cycle_switches)), 6) if cycle_switches else None
    full_max_dd = metrics["full_sample"].get("strat_dd")
    max_dd = float(full_max_dd) if isinstance(full_max_dd, int | float) else None

    return {
        "candidate": {
            "id": candidate.candidate_id,
            "label": candidate.label,
            "family": candidate.family,
            "rule_type": candidate.rule_type,
            "high_threshold": candidate.high_threshold,
            "low_threshold": candidate.low_threshold,
            "sticky_days": candidate.sticky_days,
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
        "max_drawdown_reduction_vs_k1_pp": _max_drawdown_reduction(max_dd),
        "oos_alpha_spread": [
            round(float(np.min(cycle_alphas)), 6),
            round(float(np.max(cycle_alphas)), 6),
        ]
        if cycle_alphas
        else [],
        "avg_regime_switches_per_cycle": switches_per_cycle,
        "alpha_per_switch": _alpha_per_switch(oos_alpha, switches_per_cycle),
        "trigger_summary": _trigger_summary(candidate, holder),
    }


def _best_candidate(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Return the result with the highest OOS median alpha."""
    ranked = [row for row in results if isinstance(row.get("oos_median_alpha"), int | float)]
    if not ranked:
        raise ValueError("no finite candidate OOS alpha results")
    ranked.sort(key=lambda row: (-float(row["oos_median_alpha"]), str(row["candidate"]["id"])))
    return ranked[0]


def _material_dd_improvement(row: dict[str, Any]) -> bool:
    """Return True when max drawdown improves versus K1."""
    reduction = row.get("max_drawdown_reduction_vs_k1_pp")
    return isinstance(reduction, int | float) and float(reduction) > 0.0


def _recommendation(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Apply the Phase N decision tree to euphoria-overlay results."""
    best = _best_candidate(results)
    euphoria_families = {"N1a", "N1b", "N1c", "N1d", "N2", "N3"}
    euphoria_rows = [row for row in results if row["candidate"]["family"] in euphoria_families]
    n4_rows = [row for row in results if row["candidate"]["family"] == "N4"]
    n4 = n4_rows[0] if n4_rows else None

    euphoria_winners = [
        row
        for row in euphoria_rows
        if isinstance(row.get("oos_median_alpha"), int | float)
        and float(row["oos_median_alpha"]) > K1_BASELINE_OOS_ALPHA
    ]
    tail_risk_rows = [
        row
        for row in euphoria_rows
        if isinstance(row.get("oos_median_alpha"), int | float)
        and float(row["oos_median_alpha"]) >= K1_BASELINE_OOS_ALPHA - WITHIN_K1_ALPHA_PP
        and _material_dd_improvement(row)
    ]

    selected: dict[str, Any] | None
    if euphoria_winners:
        euphoria_winners.sort(
            key=lambda row: (-float(row["oos_median_alpha"]), str(row["candidate"]["id"]))
        )
        selected = euphoria_winners[0]
        branch = "1_euphoria_overlay_beats_k1"
        action = f"switch-to-{selected['candidate']['family'].lower()}"
        text = (
            f"Prefer {selected['candidate']['label']}: it beat K1's +21.0% OOS median alpha "
            f"with {float(selected['oos_median_alpha']):.1f}%."
        )
    elif tail_risk_rows:
        tail_risk_rows.sort(
            key=lambda row: (
                -float(row["max_drawdown_reduction_vs_k1_pp"]),
                -float(row["oos_median_alpha"]),
                str(row["candidate"]["id"]),
            )
        )
        selected = tail_risk_rows[0]
        branch = "2_within_1pp_and_lower_max_dd"
        action = f"adopt-{selected['candidate']['family'].lower()}-tail-risk-overlay"
        text = (
            f"Prefer {selected['candidate']['label']}: it stayed within 1pp of K1 alpha and "
            f"improved full-sample max drawdown by "
            f"{float(selected['max_drawdown_reduction_vs_k1_pp']):.1f}pp."
        )
    elif (
        n4 is not None
        and isinstance(n4.get("oos_median_alpha"), int | float)
        and float(n4["oos_median_alpha"]) > K1_BASELINE_OOS_ALPHA
    ):
        selected = n4
        branch = "3_contrarian_low_improves_oos"
        action = "revisit-tail-framing"
        text = (
            "N4 extreme-low contrarian LONG improved OOS alpha versus K1, so the diagnostic "
            "claim that extreme lows cascade would need revisiting."
        )
    else:
        selected = None
        branch = "4_overlay_loses_keep_k1"
        action = "keep-k1-unchanged"
        text = (
            "All N1/N2/N3 euphoria overlays lost to K1 and no overlay delivered a within-1pp "
            "alpha result with lower max drawdown; keep K1 unchanged."
        )
        if n4 is not None:
            n4_alpha = n4.get("oos_median_alpha")
            if isinstance(n4_alpha, int | float) and float(n4_alpha) < K1_BASELINE_OOS_ALPHA:
                text += (
                    " N4 also lost to K1, confirming that extreme lows cascade rather "
                    "than mean-revert."
                )

    return {
        "baseline_id": "k1_holder_behavior_pure_reference",
        "k1_reference_oos_median_alpha": K1_BASELINE_OOS_ALPHA,
        "k1_reference_max_drawdown": K1_BASELINE_MAX_DD,
        "k1_reference_switches_per_cycle": K1_BASELINE_SWITCHES_PER_CYCLE,
        "within_k1_alpha_pp": WITHIN_K1_ALPHA_PP,
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
        "euphoria_candidate_ids": [row["candidate"]["id"] for row in euphoria_rows],
        "euphoria_winner_ids": [row["candidate"]["id"] for row in euphoria_winners],
        "tail_risk_candidate_ids": [row["candidate"]["id"] for row in tail_risk_rows],
        "n4_candidate_id": n4["candidate"]["id"] if n4 is not None else None,
        "n4_oos_median_alpha": n4["oos_median_alpha"] if n4 is not None else None,
        "n4_delta_vs_k1_reference_pp": n4["delta_vs_k1_reference_pp"] if n4 is not None else None,
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
    """Run the fixed Phase N euphoria-overlay comparison and optionally write JSON."""
    del cache_dir, use_cache
    ret = cast(pd.Series, data["btc_price"]).pct_change()
    holder = holder_behavior_composite(data)
    candidates = phase_n_candidates()
    results = [evaluate_candidate(candidate, holder, ret) for candidate in candidates]
    k1_reference = _k1_reference(holder, ret)

    payload = envelope(
        "phase_n_euphoria_overlay",
        {
            "k1_reference_oos_median_alpha": K1_BASELINE_OOS_ALPHA,
            "k1_reference_max_drawdown": K1_BASELINE_MAX_DD,
            "k1_reference_switches_per_cycle": K1_BASELINE_SWITCHES_PER_CYCLE,
            "within_k1_alpha_pp": WITHIN_K1_ALPHA_PP,
            "methodology": {
                "walk_forward": (
                    "Each fixed holder-only pure rule is evaluated full-sample and separately "
                    "on each BTC_CYCLES window; no candidate is selected in-sample."
                ),
                "metric": "Out-of-sample median alpha across the four cycle results.",
                "pure_mode": (
                    "No valuation input, BTC/equity input, or valuation override in any "
                    "Phase N candidate."
                ),
                "base_rule": "K1: STAY LONG if z(holder_behavior) > 0 else CASH.",
                "decision_rule": (
                    "Adopt N1/N2/N3 if it beats K1 OOS, or if it stays within 1pp of K1 "
                    "and improves max drawdown. If N4 improves, revisit low-tail framing. "
                    "Otherwise keep K1 unchanged."
                ),
                "sticky_euphoria_state": (
                    f"N3 resets a {STICKY_EUPHORIA_DAYS}-valid-observation CASH window each "
                    "day z(holder_behavior) remains above +2.0."
                ),
                "trigger_events": (
                    "Trigger dates are contiguous raw threshold-crossing windows grouped by "
                    "BTC_CYCLES; N3 reports raw z>+2.0 euphoria windows, not every "
                    "forced-cash cooldown day."
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
                "brief_claimed_candidate_count": 8,
                "enumerated_candidate_count": len(results),
                "euphoria_thresholds": list(EUPHORIA_THRESHOLDS),
                "caution_threshold": 2.0,
                "sticky_euphoria_days": STICKY_EUPHORIA_DAYS,
                "contrarian_low_threshold": -2.0,
                "valuation_override": None,
                "modes": [
                    "euphoria_cash",
                    "euphoria_caution",
                    "sticky_euphoria_cash",
                    "contrarian_low_long",
                ],
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
        description="Compare Phase N K1 euphoria-peak overlay variants."
    )
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--output", type=Path, default=default_output_path("phase_n.json"))
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
