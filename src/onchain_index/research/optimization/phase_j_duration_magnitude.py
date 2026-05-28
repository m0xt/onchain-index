"""Phase J research: test duration x magnitude BTC/NASDAQ spines.

This is a research-only final architecture audit. It compares three BTC/NASDAQ
spine constructions in pure mode and with the Phase G/H/I symmetric valuation
override, without touching production data fetches, MROI construction, or dashboard
code.
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
from onchain_index.research.equity_data import (
    cumulative_log_relative_return_z,
    relative_trend_slope_z,
    streak_magnitude_z,
    yahoo_daily_closes,
)
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
SWITCH_HURDLE_OOS_ALPHA = ADDITIVE_BASELINE_OOS_ALPHA + PROMOTION_BAR_PP
NEAR_ADDITIVE_PP = 2.0
EXHAUSTED_LOSS_PP = 5.0
VALUATION_OVERRIDE_THRESHOLD = 2.0
TREND_WINDOW_DAYS = 252
CUMULATIVE_RETURN_LOOKBACK_DAYS = 252
STREAK_WINDOW_DAYS = 180
BINARY_TIER_TO_PCT = {"CASH": 0.0, "STAY LONG": 100.0}


@dataclass(frozen=True)
class SpineCandidate:
    """Fixed Phase J spine candidate definition."""

    candidate_id: str
    label: str
    family: str
    spine_column: str
    mode: str
    source: str
    notes: str


def phase_j_candidates() -> list[SpineCandidate]:
    """Return the fixed Phase J candidate set."""
    base_candidates = [
        (
            "j1_trend_slope",
            "J1 — trend slope",
            "J1",
            "btc_nasdaq_trend_slope_z_252d",
            "Linear-regression slope of log(BTC/NASDAQ) over rolling 252d windows.",
        ),
        (
            "j2_cumulative_log_relative_return",
            "J2 — cumulative log relative return",
            "J2",
            "btc_nasdaq_cum_log_relret_z_252d",
            "Trailing 252d cumulative log BTC/NASDAQ relative return.",
        ),
        (
            "j3_streak_magnitude",
            "J3 — streak × magnitude",
            "J3",
            "btc_nasdaq_streak_magnitude_z_180d",
            "Longest BTC-outperformance streak sum over rolling 180d windows.",
        ),
    ]
    candidates: list[SpineCandidate] = []
    for base_id, label, family, spine_column, notes in base_candidates:
        candidates.extend(
            [
                SpineCandidate(
                    candidate_id=f"{base_id}_pure",
                    label=f"{label} PURE",
                    family=family,
                    spine_column=spine_column,
                    mode="pure",
                    source="Yahoo BTC-USD / ^IXIC daily closes",
                    notes=notes,
                ),
                SpineCandidate(
                    candidate_id=f"{base_id}_override",
                    label=f"{label} WITH OVERRIDE",
                    family=family,
                    spine_column=spine_column,
                    mode="override",
                    source="Yahoo BTC-USD / ^IXIC daily closes",
                    notes=notes,
                ),
            ]
        )
    return candidates


def _empty_tiers(index: pd.Index) -> pd.Series:
    """Return an object Series for binary CASH/STAY LONG tiers."""
    return pd.Series(pd.NA, index=index, dtype="object")


def pure_tiers(spine: pd.Series) -> pd.Series:
    """Return pure spine tiers with no valuation involvement."""
    tiers = _empty_tiers(spine.index)
    tiers = tiers.mask(spine <= 0.0, "CASH")
    tiers = tiers.mask(spine > 0.0, "STAY LONG")
    return tiers.where(spine.notna())


def override_tiers(valuation: pd.Series, spine: pd.Series) -> pd.Series:
    """Return valuation-override tiers with a candidate spine in the middle."""
    tiers = pure_tiers(spine)
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


def build_spines(
    data: pd.DataFrame,
    *,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    use_cache: bool = True,
) -> pd.DataFrame:
    """Build Phase J BTC/NASDAQ candidate spine series on the Phase A daily index."""
    closes = yahoo_daily_closes(
        data.index, cache_dir=cache_dir, use_cache=use_cache, cache_only=use_cache
    )
    spines = {
        "btc_nasdaq_trend_slope_z_252d": relative_trend_slope_z(
            closes, "btc_usd_close", "nasdaq_close", TREND_WINDOW_DAYS
        ),
        "btc_nasdaq_cum_log_relret_z_252d": cumulative_log_relative_return_z(
            closes, "btc_usd_close", "nasdaq_close", CUMULATIVE_RETURN_LOOKBACK_DAYS
        ),
        "btc_nasdaq_streak_magnitude_z_180d": streak_magnitude_z(
            closes, "btc_usd_close", "nasdaq_close", STREAK_WINDOW_DAYS
        ),
    }
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
    """Return Phase J non-return diagnostics for a tier series."""
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


def _candidate_tiers(
    candidate: SpineCandidate, valuation: pd.Series, spine: pd.Series
) -> pd.Series:
    """Build tiers for one Phase J candidate."""
    if candidate.mode == "pure":
        return pure_tiers(spine)
    return override_tiers(valuation, spine)


def _rule_text(candidate: SpineCandidate) -> str:
    """Return a compact rule description for one candidate."""
    spine_rule = "STAY LONG if z(spine) > 0 else CASH"
    if candidate.mode == "pure":
        return spine_rule
    return "if z(valuation) > +2.0: CASH; elif z(valuation) < -2.0: STAY LONG; else " + spine_rule


def evaluate_candidate(
    candidate: SpineCandidate,
    valuation: pd.Series,
    spines: pd.DataFrame,
    baseline_score: pd.Series,
    ret: pd.Series,
) -> dict[str, Any]:
    """Evaluate one fixed Phase J candidate full-sample and by BTC cycle."""
    spine = cast(pd.Series, spines[candidate.spine_column])
    tiers = _candidate_tiers(candidate, valuation, spine)
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

    oos_alpha = round(float(np.median(cycle_alphas)), 6) if cycle_alphas else None

    return {
        "candidate": {
            "id": candidate.candidate_id,
            "label": candidate.label,
            "family": candidate.family,
            "spine_column": candidate.spine_column,
            "mode": candidate.mode,
            "source": candidate.source,
            "rule": _rule_text(candidate),
            "valuation_override_threshold": VALUATION_OVERRIDE_THRESHOLD
            if candidate.mode == "override"
            else None,
            "tier_to_pct": BINARY_TIER_TO_PCT,
            "notes": candidate.notes,
        },
        "full_sample": {**rounded_metrics(full_metrics), **_diagnostics(tiers)},
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
    return {
        "id": "additive_baseline_reference",
        "label": "Current additive baseline",
        "rule": "STAY LONG if z(val) + z(holder) > 0 else CASH",
        "fixed_reference_oos_median_alpha": ADDITIVE_BASELINE_OOS_ALPHA,
        "computed_oos_median_alpha": round(float(np.median(cycle_alphas)), 6)
        if cycle_alphas
        else None,
        "full_sample": {**rounded_metrics(full_metrics), **_diagnostics(tiers)},
        "cycle_metrics": cycle_metrics,
    }


def _result_by_id(results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Return candidate result mapping by id."""
    return {str(row["candidate"]["id"]): row for row in results}


def _pure_override_comparison(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return explicit pure-vs-override comparison rows per Phase J spine."""
    by_id = _result_by_id(results)
    rows: list[dict[str, Any]] = []
    for family, stem in [
        ("J1", "j1_trend_slope"),
        ("J2", "j2_cumulative_log_relative_return"),
        ("J3", "j3_streak_magnitude"),
    ]:
        pure = by_id[f"{stem}_pure"]
        override = by_id[f"{stem}_override"]
        pure_alpha = cast(float | None, pure["oos_median_alpha"])
        override_alpha = cast(float | None, override["oos_median_alpha"])
        rows.append(
            {
                "family": family,
                "pure_candidate_id": pure["candidate"]["id"],
                "override_candidate_id": override["candidate"]["id"],
                "pure_oos_median_alpha": pure_alpha,
                "override_oos_median_alpha": override_alpha,
                "override_minus_pure_pp": round(override_alpha - pure_alpha, 6)
                if pure_alpha is not None and override_alpha is not None
                else None,
                "pure_delta_vs_additive_pp": pure["delta_vs_additive_reference_pp"],
                "override_delta_vs_additive_pp": override["delta_vs_additive_reference_pp"],
            }
        )
    return rows


def _best_candidate(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Return the result with the highest OOS median alpha."""
    ranked = [row for row in results if isinstance(row.get("oos_median_alpha"), int | float)]
    if not ranked:
        raise ValueError("no finite candidate OOS alpha results")
    ranked.sort(
        key=lambda row: (
            -float(row["oos_median_alpha"]),
            str(row["candidate"]["family"]),
            str(row["candidate"]["mode"]),
        )
    )
    return ranked[0]


def _recommendation(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Apply the Phase J decision tree to duration x magnitude spine results."""
    best = _best_candidate(results)
    best_alpha = cast(float, best["oos_median_alpha"])
    best_delta = round(best_alpha - ADDITIVE_BASELINE_OOS_ALPHA, 6)
    comparisons = _pure_override_comparison(results)

    if best_alpha >= SWITCH_HURDLE_OOS_ALPHA:
        branch = "switch"
        action = f"switch-to-{best['candidate']['family'].lower()}-{best['candidate']['mode']}"
        text = (
            f"Switch to {best['candidate']['label']}: it reached {best_alpha:.1f}% OOS "
            "median alpha, clearing the +19.1% switch hurdle."
        )
    elif any(
        row["override_minus_pure_pp"] is not None
        and abs(float(row["override_minus_pure_pp"])) <= NEAR_ADDITIVE_PP
        and row["override_delta_vs_additive_pp"] is not None
        and abs(float(row["override_delta_vs_additive_pp"])) <= NEAR_ADDITIVE_PP
        for row in comparisons
    ):
        branch = "multi_dim_composite_worth_productionizing"
        action = "consider-productionizing-multi-dim-composite"
        text = (
            "Pure mode is within 2pp of override mode and override is within 2pp of "
            "the additive reference for at least one spine, so the BTC/equity spine "
            "is doing real work worth production review."
        )
    elif any(
        row["pure_delta_vs_additive_pp"] is not None
        and float(row["pure_delta_vs_additive_pp"]) <= -EXHAUSTED_LOSS_PP
        and row["override_delta_vs_additive_pp"] is not None
        and float(row["override_delta_vs_additive_pp"]) > -EXHAUSTED_LOSS_PP
        for row in comparisons
    ):
        branch = "valuation_carries_alpha"
        action = "commit-docs-update-additive-empirical-first"
        text = (
            "Pure spine mode loses badly while valuation override catches up, so valuation "
            "has been carrying the alpha; commit to the empirical-first additive framing."
        )
    elif all(
        isinstance(row.get("delta_vs_additive_reference_pp"), int | float)
        and float(row["delta_vs_additive_reference_pp"]) <= -EXHAUSTED_LOSS_PP
        for row in results
    ):
        branch = "architecture_search_exhausted"
        action = "commit-docs-update-additive-empirical-first"
        text = (
            "All Phase J variants lose to additive by at least 5pp, so the architecture "
            "search is empirically exhausted; commit to the empirical-first additive framing."
        )
    else:
        branch = "keep_additive"
        action = "keep-additive"
        text = (
            "No Phase J candidate cleared the switch hurdle or met the multi-dimensional "
            "productionizing branch; keep the current additive architecture."
        )

    return {
        "baseline_id": "additive_baseline_reference",
        "additive_reference_oos_median_alpha": ADDITIVE_BASELINE_OOS_ALPHA,
        "promotion_bar_pp": PROMOTION_BAR_PP,
        "switch_hurdle_oos_median_alpha": round(SWITCH_HURDLE_OOS_ALPHA, 6),
        "near_additive_pp": NEAR_ADDITIVE_PP,
        "exhausted_loss_pp": EXHAUSTED_LOSS_PP,
        "best_candidate_id": best["candidate"]["id"],
        "best_candidate_label": best["candidate"]["label"],
        "best_oos_median_alpha": round(best_alpha, 6),
        "best_delta_vs_additive_reference_pp": best_delta,
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
    """Run the fixed Phase J duration x magnitude spine comparison."""
    ret = cast(pd.Series, data["btc_price"]).pct_change()
    valuation = valuation_composite(data)
    holder = holder_behavior_composite(data)
    baseline_score = valuation + holder
    spines = build_spines(data, cache_dir=cache_dir, use_cache=use_cache)

    candidates = phase_j_candidates()
    results = [
        evaluate_candidate(candidate, valuation, spines, baseline_score, ret)
        for candidate in candidates
    ]
    comparisons = _pure_override_comparison(results)

    payload = envelope(
        "phase_j_duration_magnitude",
        {
            "promotion_bar_pp": PROMOTION_BAR_PP,
            "additive_reference_oos_median_alpha": ADDITIVE_BASELINE_OOS_ALPHA,
            "switch_hurdle_oos_median_alpha": SWITCH_HURDLE_OOS_ALPHA,
            "valuation_override_threshold": VALUATION_OVERRIDE_THRESHOLD,
            "methodology": {
                "walk_forward": (
                    "Each fixed spine rule is evaluated full-sample and separately on each "
                    "BTC_CYCLES window; no candidate is selected in-sample."
                ),
                "metric": "Out-of-sample median alpha across the four cycle results.",
                "pure_mode": "STAY LONG if z(spine) > 0 else CASH; no valuation input.",
                "override_mode": (
                    "Same spine rule, except z(valuation) > +2.0 forces CASH and "
                    "z(valuation) < -2.0 forces STAY LONG."
                ),
                "promotion_rule": (
                    "A switch must beat the +18.1% additive reference by at least 1pp "
                    "OOS, i.e. clear +19.1% OOS median alpha."
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
                "trend_window_days": TREND_WINDOW_DAYS,
                "cumulative_return_lookback_days": CUMULATIVE_RETURN_LOOKBACK_DAYS,
                "streak_window_days": STREAK_WINDOW_DAYS,
                "modes": ["pure", "override"],
                "valuation_override_threshold": VALUATION_OVERRIDE_THRESHOLD,
            },
            "baseline_reference": _baseline_reference(valuation, holder, ret),
            "pure_vs_override": comparisons,
            "results": results,
            "recommendation": _recommendation(results),
        },
    )
    if output_path is not None:
        write_json(output_path, payload)
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare Phase J duration x magnitude BTC/NASDAQ spines."
    )
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--output", type=Path, default=default_output_path("phase_j.json"))
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
