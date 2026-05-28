"""Phase O research: K1 confirmation-rule variants.

This is a research-only follow-up to Phase K/L/M/N. It keeps the holder-only
PURE spine and tests only N-day zero-crossing confirmation rules. Production
data fetches, MROI construction, and dashboard code are untouched.
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
QUALIFYING_OOS_ALPHA = 20.0
MAX_SWITCHES_PER_CYCLE = 20.0
BINARY_TIER_TO_PCT = {"CASH": 0.0, "STAY LONG": 100.0}
CONFIRMATION_DAYS: tuple[int, ...] = (3, 5, 7, 10, 14)


@dataclass(frozen=True)
class ConfirmationCandidate:
    """Fixed Phase O confirmation-rule candidate definition."""

    candidate_id: str
    label: str
    family: str
    confirmation_days: int
    source: str
    notes: str


def phase_o_candidates() -> list[ConfirmationCandidate]:
    """Return the fixed Phase O holder-only confirmation candidate set."""
    return [
        ConfirmationCandidate(
            candidate_id=f"o{index}_k1_confirmation_{days}d",
            label=f"O{index} — N={days} confirmation",
            family=f"O{index}",
            confirmation_days=days,
            source="Production holder_behavior_composite",
            notes=(
                "K1 holder rule, but require "
                f"{days} consecutive opposite-sign valid observations before flipping."
            ),
        )
        for index, days in enumerate(CONFIRMATION_DAYS, start=1)
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


def _signal_from_value(value: float) -> str:
    """Return the raw K1 regime signal for one finite holder z-score."""
    return "STAY LONG" if value > 0.0 else "CASH"


def confirmation_tiers(holder: pd.Series, confirmation_days: int) -> pd.Series:
    """Return K1 tiers with an N-day same-side confirmation rule."""
    tiers = _empty_tiers(holder.index)
    current_regime: str | None = None
    pending_flip_count = 0

    for index, value in holder.items():
        if pd.isna(value):
            continue
        signal = _signal_from_value(float(value))
        if current_regime is None:
            current_regime = signal
            pending_flip_count = 0
        elif signal == current_regime:
            pending_flip_count = 0
        else:
            pending_flip_count += 1
            if pending_flip_count >= confirmation_days:
                current_regime = signal
                pending_flip_count = 0
        tiers.loc[index] = current_regime

    return tiers.where(holder.notna())


def confirmation_flip_events(holder: pd.Series, confirmation_days: int) -> list[dict[str, Any]]:
    """Return confirmed flip events from the N-day confirmation state machine."""
    events: list[dict[str, Any]] = []
    current_regime: str | None = None
    pending_flip_count = 0
    pending_start: pd.Timestamp | None = None
    pending_target: str | None = None

    for index, value in holder.items():
        if pd.isna(value):
            continue
        timestamp = cast(pd.Timestamp, index)
        z_value = float(value)
        signal = _signal_from_value(z_value)
        if current_regime is None:
            current_regime = signal
            continue
        if signal == current_regime:
            pending_flip_count = 0
            pending_start = None
            pending_target = None
            continue

        if pending_target != signal:
            pending_target = signal
            pending_start = timestamp
            pending_flip_count = 1
        else:
            pending_flip_count += 1

        if pending_flip_count >= confirmation_days:
            previous = current_regime
            current_regime = signal
            events.append(
                {
                    "confirmed_date": str(timestamp.date()),
                    "pending_start_date": str(pending_start.date())
                    if pending_start is not None
                    else str(timestamp.date()),
                    "from_regime": previous,
                    "to_regime": current_regime,
                    "confirmation_days": confirmation_days,
                    "holder_z_on_confirm": round(z_value, 6),
                }
            )
            pending_flip_count = 0
            pending_start = None
            pending_target = None

    return events


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
    """Return Phase O non-return diagnostics for a tier series."""
    cash_share = _cash_share(tiers)
    return {
        "time_in_cash_pct": round(cash_share, 6) if cash_share is not None else None,
        "regime_switches": _switch_count(tiers),
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


def _rule_text(candidate: ConfirmationCandidate) -> str:
    """Return a compact rule description for one Phase O candidate."""
    days = candidate.confirmation_days
    return f"Flip only after {days} consecutive opposite-sign z(holder) observations"


def evaluate_candidate(
    candidate: ConfirmationCandidate,
    holder: pd.Series,
    ret: pd.Series,
) -> dict[str, Any]:
    """Evaluate one fixed Phase O candidate full-sample and by BTC cycle."""
    tiers = confirmation_tiers(holder, candidate.confirmation_days)
    metrics, oos_alpha, cycle_alphas, cycle_switches = _evaluate_tiers(
        tiers, ret, BINARY_TIER_TO_PCT
    )
    switches_per_cycle = round(float(np.mean(cycle_switches)), 6) if cycle_switches else None
    cycle_metrics = cast(dict[str, dict[str, float | int | None]], metrics["cycle_metrics"])
    cycle4_name = _cycle4_name()
    cycle4_metrics = cycle_metrics[cycle4_name]
    cycle4_alpha = cycle4_metrics.get("alpha")
    strict_cycle4_alpha = float(cycle4_alpha) if isinstance(cycle4_alpha, int | float) else None
    full_max_dd = metrics["full_sample"].get("strat_dd")
    max_dd = float(full_max_dd) if isinstance(full_max_dd, int | float) else None

    return {
        "candidate": {
            "id": candidate.candidate_id,
            "label": candidate.label,
            "family": candidate.family,
            "confirmation_days": candidate.confirmation_days,
            "source": candidate.source,
            "rule": _rule_text(candidate),
            "pure_mode": True,
            "valuation_override": None,
            "tier_to_pct": BINARY_TIER_TO_PCT,
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
        "cycle4_flip_events": [
            event
            for event in confirmation_flip_events(holder, candidate.confirmation_days)
            if pd.Timestamp(event["confirmed_date"]) >= pd.Timestamp(BTC_CYCLES[cycle4_name][0])
            and pd.Timestamp(event["confirmed_date"]) <= pd.Timestamp(BTC_CYCLES[cycle4_name][1])
        ],
    }


def _best_standard_candidate(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Return the result with the highest standard walk-forward OOS median alpha."""
    ranked = [row for row in results if isinstance(row.get("oos_median_alpha"), int | float)]
    if not ranked:
        raise ValueError("no finite candidate OOS alpha results")
    ranked.sort(
        key=lambda row: (
            -float(row["oos_median_alpha"]),
            int(row["candidate"]["confirmation_days"]),
            str(row["candidate"]["id"]),
        )
    )
    return ranked[0]


def _strict_selected_candidate(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Select N using only cycles 1-3 median alpha, preferring lower N on ties."""
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
            int(row["candidate"]["confirmation_days"]),
            str(row["candidate"]["id"]),
        )
    )
    return ranked[0]


def _qualifies(row: dict[str, Any]) -> bool:
    """Return True if a candidate clears the Phase O adoption hurdle."""
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
    """Select the preferred qualifying candidate by the Phase O product rule."""
    if not qualifiers:
        raise ValueError("no qualifying candidates")
    qualifiers.sort(
        key=lambda row: (
            int(row["candidate"]["confirmation_days"]),
            -float(row["standard_walk_forward"]["oos_median_alpha"]),
            str(row["candidate"]["id"]),
        )
    )
    return qualifiers[0]


def _strict_cycle4_alpha(row: dict[str, Any]) -> float | None:
    """Return strict holdout cycle-4 alpha for one result row."""
    value = cast(dict[str, Any], row["strict_holdout"]).get("cycle4_alpha")
    return float(value) if isinstance(value, int | float) else None


def _recommendation(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Apply the Phase O decision tree to confirmation-rule results."""
    standard_best = _best_standard_candidate(results)
    strict_selected = _strict_selected_candidate(results)
    qualifiers = [row for row in results if _qualifies(row)]
    tracks_agree = (
        standard_best["candidate"]["id"] == strict_selected["candidate"]["id"]
    )

    if qualifiers:
        selected = _select_qualifier(qualifiers)
        branch = "1_adopt_confirmation_rule"
        action = f"productionize-{selected['candidate']['family'].lower()}-confirmation"
        text = (
            f"Prefer {selected['candidate']['label']}: it maintained "
            f"{float(selected['standard_walk_forward']['oos_median_alpha']):.1f}% standard-WF "
            f"OOS alpha and {float(selected['strict_holdout']['cycle4_alpha']):.1f}% strict "
            f"cycle-4 alpha with {float(selected['avg_regime_switches_per_cycle']):.1f} "
            "switches/cycle."
        )
    else:
        selected = None
        strict_alpha = _strict_cycle4_alpha(strict_selected)
        if strict_alpha is not None and strict_alpha < QUALIFYING_OOS_ALPHA:
            branch = "4_strict_holdout_collapse"
            action = "flag-overfitting-risk"
            text = (
                f"No candidate cleared both tracks. The strict IS-selected row, "
                f"{strict_selected['candidate']['label']}, reached only {strict_alpha:.1f}% "
                "on the held-out 2025-now cycle, so do not switch on standard walk-forward "
                "results alone."
            )
        else:
            branch = "3_no_dual_track_qualifier"
            action = "surface-alpha-vs-switches-tradeoff"
            text = (
                "No Phase O candidate cleared >=20.0% alpha in both validation tracks with "
                "<20 switches/cycle; surface the Pareto trade-off and keep K1 pending review."
            )

    return {
        "baseline_id": "k1_holder_behavior_pure_reference",
        "k1_reference_oos_median_alpha": K1_BASELINE_OOS_ALPHA,
        "k1_reference_max_drawdown": K1_BASELINE_MAX_DD,
        "k1_reference_switches_per_cycle": K1_BASELINE_SWITCHES_PER_CYCLE,
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
        "tracks_agree_on_best_n": tracks_agree,
        "selected_candidate_id": selected["candidate"]["id"] if selected is not None else None,
        "selected_candidate_label": selected["candidate"]["label"]
        if selected is not None
        else None,
        "selected_confirmation_days": selected["candidate"]["confirmation_days"]
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
    """Run the fixed Phase O confirmation-rule comparison and optionally write JSON."""
    del cache_dir, use_cache
    ret = cast(pd.Series, data["btc_price"]).pct_change()
    holder = holder_behavior_composite(data)
    candidates = phase_o_candidates()
    results = [evaluate_candidate(candidate, holder, ret) for candidate in candidates]
    k1_reference = _k1_reference(holder, ret)

    payload = envelope(
        "phase_o_confirmation_rules",
        {
            "k1_reference_oos_median_alpha": K1_BASELINE_OOS_ALPHA,
            "k1_reference_max_drawdown": K1_BASELINE_MAX_DD,
            "k1_reference_switches_per_cycle": K1_BASELINE_SWITCHES_PER_CYCLE,
            "qualifying_oos_alpha": QUALIFYING_OOS_ALPHA,
            "max_switches_per_cycle": MAX_SWITCHES_PER_CYCLE,
            "methodology": {
                "standard_walk_forward": (
                    "Each fixed holder-only pure confirmation rule is evaluated full-sample "
                    "and separately on each BTC_CYCLES window; the headline is median alpha "
                    "across all four cycles for comparability with Phase K-N."
                ),
                "strict_is_oos_holdout": (
                    "Select N using only cycles 1-3 median alpha, then evaluate that N once "
                    "on cycle 4 (2025-now). If the tracks disagree, trust the strict holdout."
                ),
                "metric": (
                    "Annualized alpha vs BTC buy-and-hold, plus switches/cycle, time in cash, "
                    "alpha-per-switch, max drawdown, and cycle-4 flip dates."
                ),
                "pure_mode": (
                    "No valuation input, BTC/equity input, or valuation override in any "
                    "Phase O candidate. Base raw signal is K1: STAY LONG if z(holder) > 0 "
                    "else CASH."
                ),
                "confirmation_state": (
                    "Initial valid state follows the sign of z(holder). Opposite-sign days "
                    "increment pending_flip_count; same-sign days reset it. The regime flips "
                    "only when pending_flip_count >= N."
                ),
                "decision_rule": (
                    "Adopt if a candidate has >=20.0% standard OOS median alpha, >=20.0% "
                    "strict cycle-4 alpha, and <20 switches/cycle. Prefer lower N if multiple "
                    "qualify."
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
                "confirmation_days": list(CONFIRMATION_DAYS),
                "valuation_override": None,
                "modes": ["n_day_confirmation"],
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
        description="Compare Phase O K1 confirmation-rule variants."
    )
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--output", type=Path, default=default_output_path("phase_o.json"))
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
