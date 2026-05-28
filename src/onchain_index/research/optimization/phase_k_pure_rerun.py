"""Phase K research: re-run Phase G/H/I candidates in pure mode.

This is a research-only contamination audit. It re-tests the strongest Phase G/H/I
spines without valuation in the spine and without any valuation override, leaving
production data fetches, MROI construction, and dashboard code untouched.
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
from onchain_index.research.equity_data import outperformance_frequency_z, yahoo_daily_closes
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
PHASE_L_LOWER_BOUND_OOS_ALPHA = ADDITIVE_BASELINE_OOS_ALPHA - PROMOTION_BAR_PP
OUTPERFORMANCE_WINDOWS: tuple[int, ...] = (30, 90, 180)
BINARY_TIER_TO_PCT = {"CASH": 0.0, "STAY LONG": 100.0}

OVERRIDE_REFERENCE_OOS_ALPHA: dict[str, float] = {
    "h1_holder_behavior": 7.955071,
    "i2a_btc_nasdaq_outperf_90d": 9.645877,
    "i2b_btc_spx_outperf_90d": 2.725071,
    "i2c_btc_nasdaq_outperf_30d": 0.260298,
    "i2d_btc_nasdaq_outperf_180d": -9.836259,
    "i3_holder_best_btc_equity_composite": -1.561848,
    "i4_holder_best_btc_equity_conjunction": 10.721463,
}


@dataclass(frozen=True)
class SpineCandidate:
    """Fixed Phase K pure-mode candidate definition."""

    candidate_id: str
    label: str
    family: str
    spine_column: str
    rule_type: str
    source: str
    notes: str
    origin_phase: str
    origin_override_candidate_id: str
    selected_from: str | None = None


def base_phase_k_candidates() -> list[SpineCandidate]:
    """Return K1/K2/K3 candidates before K4/K5 selection."""
    return [
        SpineCandidate(
            candidate_id="k1_holder_behavior_pure",
            label="K1 — holder behavior PURE",
            family="K1",
            spine_column="holder_behavior",
            rule_type="spine",
            source="production holder_behavior_composite",
            notes="Clean holder-only pure-mode reference; no valuation override.",
            origin_phase="Phase H1 / Phase G symmetric T=2",
            origin_override_candidate_id="h1_holder_behavior",
        ),
        SpineCandidate(
            candidate_id="k2_btc_nasdaq_outperf_90d_pure",
            label="K2 — BTC/NASDAQ outperformance 90d PURE",
            family="K2",
            spine_column="btc_nasdaq_outperf_freq_z_90d",
            rule_type="spine",
            source="Yahoo BTC-USD / ^IXIC daily closes",
            notes="Pure re-run of Phase I2a's 90d BTC/NASDAQ outperformance frequency.",
            origin_phase="Phase I2a",
            origin_override_candidate_id="i2a_btc_nasdaq_outperf_90d",
        ),
        SpineCandidate(
            candidate_id="k3_btc_nasdaq_outperf_30d_pure",
            label="K3 — BTC/NASDAQ outperformance 30d PURE",
            family="K3",
            spine_column="btc_nasdaq_outperf_freq_z_30d",
            rule_type="spine",
            source="Yahoo BTC-USD / ^IXIC daily closes",
            notes="Pure 30d BTC/NASDAQ outperformance-frequency sensitivity.",
            origin_phase="Phase I2c",
            origin_override_candidate_id="i2c_btc_nasdaq_outperf_30d",
        ),
        SpineCandidate(
            candidate_id="k3_btc_nasdaq_outperf_90d_pure",
            label="K3 — BTC/NASDAQ outperformance 90d PURE",
            family="K3",
            spine_column="btc_nasdaq_outperf_freq_z_90d",
            rule_type="spine",
            source="Yahoo BTC-USD / ^IXIC daily closes",
            notes="Pure 90d BTC/NASDAQ outperformance-frequency sensitivity; same spine as K2.",
            origin_phase="Phase I2a",
            origin_override_candidate_id="i2a_btc_nasdaq_outperf_90d",
        ),
        SpineCandidate(
            candidate_id="k3_btc_nasdaq_outperf_180d_pure",
            label="K3 — BTC/NASDAQ outperformance 180d PURE",
            family="K3",
            spine_column="btc_nasdaq_outperf_freq_z_180d",
            rule_type="spine",
            source="Yahoo BTC-USD / ^IXIC daily closes",
            notes="Pure 180d BTC/NASDAQ outperformance-frequency sensitivity.",
            origin_phase="Phase I2d",
            origin_override_candidate_id="i2d_btc_nasdaq_outperf_180d",
        ),
        SpineCandidate(
            candidate_id="k3_btc_spx_outperf_90d_pure",
            label="K3 — BTC/SPX outperformance 90d PURE",
            family="K3",
            spine_column="btc_spx_outperf_freq_z_90d",
            rule_type="spine",
            source="Yahoo BTC-USD / ^GSPC daily closes",
            notes="Pure 90d BTC/S&P 500 outperformance-frequency sensitivity.",
            origin_phase="Phase I2b",
            origin_override_candidate_id="i2b_btc_spx_outperf_90d",
        ),
    ]


def _empty_tiers(index: pd.Index) -> pd.Series:
    """Return an object Series for binary CASH/STAY LONG tiers."""
    return pd.Series(pd.NA, index=index, dtype="object")


def pure_tiers(spine: pd.Series) -> pd.Series:
    """Return pure spine tiers with no valuation involvement."""
    tiers = _empty_tiers(spine.index)
    tiers = tiers.mask(spine <= 0.0, "CASH")
    tiers = tiers.mask(spine > 0.0, "STAY LONG")
    return tiers.where(spine.notna())


def conjunction_tiers(holder: pd.Series, btc_equity: pd.Series) -> pd.Series:
    """Return pure holder AND BTC/equity conjunction tiers."""
    tiers = _empty_tiers(holder.index)
    tiers = tiers.mask((holder <= 0.0) | (btc_equity <= 0.0), "CASH")
    tiers = tiers.mask((holder > 0.0) & (btc_equity > 0.0), "STAY LONG")
    return tiers.where(holder.notna() & btc_equity.notna())


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
    """Build Phase K holder and BTC/equity outperformance-frequency spines."""
    closes = yahoo_daily_closes(
        data.index, cache_dir=cache_dir, use_cache=use_cache, cache_only=use_cache
    )
    spines = {
        "holder_behavior": holder_behavior_composite(data),
        "btc_nasdaq_outperf_freq_z_30d": outperformance_frequency_z(
            closes, "btc_usd_close", "nasdaq_close", 30
        ),
        "btc_nasdaq_outperf_freq_z_90d": outperformance_frequency_z(
            closes, "btc_usd_close", "nasdaq_close", 90
        ),
        "btc_nasdaq_outperf_freq_z_180d": outperformance_frequency_z(
            closes, "btc_usd_close", "nasdaq_close", 180
        ),
        "btc_spx_outperf_freq_z_90d": outperformance_frequency_z(
            closes, "btc_usd_close", "spx_close", 90
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
    """Return Phase K non-return diagnostics for a tier series."""
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
    candidate: SpineCandidate,
    holder: pd.Series,
    spines: pd.DataFrame,
) -> pd.Series:
    """Build pure tiers for one Phase K candidate."""
    spine = cast(pd.Series, spines[candidate.spine_column])
    if candidate.rule_type == "conjunction":
        return conjunction_tiers(holder, spine)
    return pure_tiers(spine)


def _rule_text(candidate: SpineCandidate) -> str:
    """Return a compact rule description for one pure-mode candidate."""
    if candidate.rule_type == "conjunction":
        return "STAY LONG if z(holder) > 0 AND z(best BTC/equity) > 0 else CASH"
    return "STAY LONG if z(spine) > 0 else CASH"


def evaluate_candidate(
    candidate: SpineCandidate,
    holder: pd.Series,
    spines: pd.DataFrame,
    baseline_score: pd.Series,
    ret: pd.Series,
) -> dict[str, Any]:
    """Evaluate one fixed Phase K pure-mode candidate full-sample and by BTC cycle."""
    spine = cast(pd.Series, spines[candidate.spine_column])
    correlation_spine = (
        cast(pd.Series, spines["holder_btc_equity_conjunction"])
        if candidate.rule_type == "conjunction" and "holder_btc_equity_conjunction" in spines
        else spine
    )
    tiers = _candidate_tiers(candidate, holder, spines)
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
    override_alpha = OVERRIDE_REFERENCE_OOS_ALPHA[candidate.origin_override_candidate_id]

    return {
        "candidate": {
            "id": candidate.candidate_id,
            "label": candidate.label,
            "family": candidate.family,
            "spine_column": candidate.spine_column,
            "rule_type": candidate.rule_type,
            "source": candidate.source,
            "rule": _rule_text(candidate),
            "pure_mode": True,
            "valuation_override": None,
            "tier_to_pct": BINARY_TIER_TO_PCT,
            "selected_from": candidate.selected_from,
            "origin_phase": candidate.origin_phase,
            "origin_override_candidate_id": candidate.origin_override_candidate_id,
            "notes": candidate.notes,
        },
        "full_sample": {**rounded_metrics(full_metrics), **_diagnostics(tiers)},
        "cycle_metrics": cycle_metrics,
        "oos_median_alpha": oos_alpha,
        "delta_vs_additive_reference_pp": (
            round(oos_alpha - ADDITIVE_BASELINE_OOS_ALPHA, 6) if oos_alpha is not None else None
        ),
        "override_reference_oos_median_alpha": override_alpha,
        "pure_minus_override_reference_pp": (
            round(oos_alpha - override_alpha, 6) if oos_alpha is not None else None
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
        "spine_vs_additive_baseline_correlation": _correlation(correlation_spine, baseline_score),
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


def _full_sample_alpha(result: dict[str, Any]) -> float:
    """Return finite full-sample alpha for K4/K5 BTC/equity metric selection."""
    full_sample = cast(dict[str, Any], result["full_sample"])
    alpha = full_sample.get("alpha")
    if not isinstance(alpha, int | float) or not math.isfinite(alpha):
        return -math.inf
    return float(alpha)


def _select_best_btc_equity_metric(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Select the best K2/K3 BTC/equity metric by full-sample alpha."""
    ranked = [
        row
        for row in results
        if str(row["candidate"]["family"]) in {"K2", "K3"}
        and str(row["candidate"]["spine_column"]).startswith("btc_")
    ]
    if not ranked:
        raise ValueError("no finite K2/K3 BTC/equity metric results")
    ranked.sort(key=lambda row: (-_full_sample_alpha(row), str(row["candidate"]["id"])))
    return ranked[0]


def _best_candidate(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Return the result with the highest OOS median alpha."""
    ranked = [row for row in results if isinstance(row.get("oos_median_alpha"), int | float)]
    if not ranked:
        raise ValueError("no finite candidate OOS alpha results")
    ranked.sort(key=lambda row: (-float(row["oos_median_alpha"]), str(row["candidate"]["id"])))
    return ranked[0]


def _pure_override_comparison(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return explicit Phase K pure-vs-prior-override comparison rows."""
    rows: list[dict[str, Any]] = []
    for row in results:
        pure_alpha = cast(float | None, row["oos_median_alpha"])
        override_alpha = cast(float, row["override_reference_oos_median_alpha"])
        rows.append(
            {
                "candidate_id": row["candidate"]["id"],
                "candidate_label": row["candidate"]["label"],
                "origin_phase": row["candidate"]["origin_phase"],
                "origin_override_candidate_id": row["candidate"]["origin_override_candidate_id"],
                "pure_oos_median_alpha": pure_alpha,
                "override_oos_median_alpha": override_alpha,
                "pure_minus_override_pp": round(pure_alpha - override_alpha, 6)
                if pure_alpha is not None
                else None,
                "pure_delta_vs_additive_pp": row["delta_vs_additive_reference_pp"],
            }
        )
    return rows


def _recommendation(results: list[dict[str, Any]], baseline: dict[str, Any]) -> dict[str, Any]:
    """Apply the Phase K decision tree to pure-mode rerun results."""
    best = _best_candidate(results)
    best_alpha = cast(float, best["oos_median_alpha"])
    best_delta = round(best_alpha - ADDITIVE_BASELINE_OOS_ALPHA, 6)
    baseline_full = cast(dict[str, Any], baseline["full_sample"])
    baseline_max_dd = float(cast(float, baseline_full["strat_dd"]))

    phase_l_candidates = [
        row
        for row in results
        if isinstance(row.get("oos_median_alpha"), int | float)
        and PHASE_L_LOWER_BOUND_OOS_ALPHA
        <= float(row["oos_median_alpha"])
        < SWITCH_HURDLE_OOS_ALPHA
        and isinstance(cast(dict[str, Any], row["full_sample"]).get("strat_dd"), int | float)
        and float(cast(dict[str, Any], row["full_sample"])["strat_dd"]) > baseline_max_dd
    ]

    if best_alpha >= SWITCH_HURDLE_OOS_ALPHA:
        branch = "1_switch"
        action = f"switch-to-{best['candidate']['family'].lower()}-pure"
        text = (
            f"Switch to {best['candidate']['label']}: it reached {best_alpha:.1f}% OOS "
            "median alpha, clearing the +19.1% switch hurdle."
        )
    elif phase_l_candidates:
        phase_l_candidates.sort(
            key=lambda row: (-float(row["oos_median_alpha"]), str(row["candidate"]["id"]))
        )
        candidate = phase_l_candidates[0]
        branch = "2_phase_l_stress_test"
        action = "propose-phase-l-stress-test"
        text = (
            f"Propose Phase L stress tests for {candidate['candidate']['label']}: it finished "
            "within 1pp of additive and had lower full-sample max drawdown."
        )
    elif all(
        isinstance(row.get("oos_median_alpha"), int | float)
        and float(row["oos_median_alpha"]) <= PHASE_L_LOWER_BOUND_OOS_ALPHA
        for row in results
    ):
        branch = "3_docs_update"
        action = "commit-docs-update-additive-empirical-first"
        text = (
            "All Phase K pure-mode candidates lose to additive by at least 1pp, so the "
            "architecture search is exhausted; commit to the empirical-first additive docs update."
        )
    else:
        branch = "keep_additive"
        action = "keep-additive"
        text = (
            "No Phase K candidate cleared the switch hurdle or the Phase L drawdown branch; "
            "keep the current additive architecture."
        )

    return {
        "baseline_id": "additive_baseline_reference",
        "additive_reference_oos_median_alpha": ADDITIVE_BASELINE_OOS_ALPHA,
        "promotion_bar_pp": PROMOTION_BAR_PP,
        "switch_hurdle_oos_median_alpha": round(SWITCH_HURDLE_OOS_ALPHA, 6),
        "phase_l_lower_bound_oos_median_alpha": round(PHASE_L_LOWER_BOUND_OOS_ALPHA, 6),
        "additive_full_sample_max_drawdown": round(baseline_max_dd, 6),
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
    """Run the fixed Phase K pure-mode rerun and optionally write JSON."""
    ret = cast(pd.Series, data["btc_price"]).pct_change()
    valuation = valuation_composite(data)
    holder = holder_behavior_composite(data)
    baseline_score = valuation + holder
    spines = build_spines(data, cache_dir=cache_dir, use_cache=use_cache)

    base_candidates = base_phase_k_candidates()
    base_results = [
        evaluate_candidate(candidate, holder, spines, baseline_score, ret)
        for candidate in base_candidates
    ]
    selected = _select_best_btc_equity_metric(base_results)
    selected_column = str(selected["candidate"]["spine_column"])
    selected_id = str(selected["candidate"]["id"])
    selected_label = str(selected["candidate"]["label"])
    selected_metric_label = selected_label.replace(" PURE", "")

    selected_spine = cast(pd.Series, spines[selected_column])
    spines["holder_btc_equity_composite_z"] = pd.concat(
        [holder, selected_spine], axis=1
    ).mean(axis=1)
    spines["holder_btc_equity_conjunction"] = (
        (holder > 0.0) & (selected_spine > 0.0)
    ).astype(float).where(holder.notna() & selected_spine.notna())

    selected_candidates = [
        SpineCandidate(
            candidate_id="k4_holder_best_btc_equity_composite_pure",
            label=f"K4 — holder + {selected_metric_label} PURE",
            family="K4",
            spine_column="holder_btc_equity_composite_z",
            rule_type="spine",
            source="Production holder behavior plus selected pure K2/K3 BTC/equity metric",
            notes="Mean of z(holder_behavior) and z(best BTC/equity metric by full-sample alpha).",
            origin_phase="Phase I3",
            origin_override_candidate_id="i3_holder_best_btc_equity_composite",
            selected_from=selected_id,
        ),
        SpineCandidate(
            candidate_id="k5_holder_best_btc_equity_conjunction_pure",
            label=f"K5 — holder AND {selected_metric_label} PURE",
            family="K5",
            spine_column=selected_column,
            rule_type="conjunction",
            source="Production holder behavior plus selected pure K2/K3 BTC/equity metric",
            notes=(
                "STAY LONG only when holder behavior and selected BTC/equity metric "
                "are positive."
            ),
            origin_phase="Phase I4",
            origin_override_candidate_id="i4_holder_best_btc_equity_conjunction",
            selected_from=selected_id,
        ),
    ]
    selected_results = [
        evaluate_candidate(candidate, holder, spines, baseline_score, ret)
        for candidate in selected_candidates
    ]
    results = base_results + selected_results
    baseline = _baseline_reference(valuation, holder, ret)

    payload = envelope(
        "phase_k_pure_rerun",
        {
            "promotion_bar_pp": PROMOTION_BAR_PP,
            "additive_reference_oos_median_alpha": ADDITIVE_BASELINE_OOS_ALPHA,
            "switch_hurdle_oos_median_alpha": SWITCH_HURDLE_OOS_ALPHA,
            "phase_l_lower_bound_oos_median_alpha": PHASE_L_LOWER_BOUND_OOS_ALPHA,
            "methodology": {
                "walk_forward": (
                    "Each fixed pure-mode rule is evaluated full-sample and separately on each "
                    "BTC_CYCLES window. K4/K5 use the K2/K3 BTC/equity metric selected by "
                    "full-sample alpha, not by OOS median."
                ),
                "metric": "Out-of-sample median alpha across the four cycle results.",
                "pure_mode": "STAY LONG if z(spine) > 0 else CASH; no valuation input.",
                "conjunction_mode": (
                    "STAY LONG if z(holder) > 0 AND z(best BTC/equity) > 0 else CASH; "
                    "no valuation input."
                ),
                "decision_rule": (
                    "Clear +19.1% OOS to switch; finish from +17.1% to below +19.1% "
                    "with lower full-sample max drawdown to propose Phase L; otherwise if "
                    "all lose by at least 1pp, commit to docs update."
                ),
            },
            "data_snapshot": {
                "rows": int(len(data)),
                "start": str(data.index.min()),
                "end": str(data.index.max()),
                "valuation_non_nan_for_reference_only": int(valuation.notna().sum()),
                "holder_non_nan": int(holder.notna().sum()),
                "joint_baseline_non_nan": int((valuation.notna() & holder.notna()).sum()),
                "spine_non_nan": {
                    column: int(cast(pd.Series, spines[column]).notna().sum())
                    for column in spines.columns
                },
            },
            "candidate_grid": {
                "outperformance_frequency_windows": list(OUTPERFORMANCE_WINDOWS),
                "modes": ["pure"],
                "valuation_override": None,
                "candidate_count": len(results),
            },
            "k4_k5_selection": {
                "criterion": (
                    "Highest full-sample alpha among pure K2/K3 BTC/equity candidates; "
                    "OOS median not used."
                ),
                "selected_candidate_id": selected_id,
                "selected_candidate_label": selected_label,
                "selected_spine_column": selected_column,
                "selected_full_sample_alpha": _full_sample_alpha(selected),
                "selected_oos_median_alpha": selected["oos_median_alpha"],
            },
            "baseline_reference": baseline,
            "pure_vs_prior_override": _pure_override_comparison(results),
            "results": results,
            "recommendation": _recommendation(results, baseline),
        },
    )
    if output_path is not None:
        write_json(output_path, payload)
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Re-run Phase G/H/I spine candidates in pure mode."
    )
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--output", type=Path, default=default_output_path("phase_k.json"))
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
