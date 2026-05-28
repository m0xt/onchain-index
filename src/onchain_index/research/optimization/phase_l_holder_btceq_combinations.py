"""Phase L research: holder behavior with BTC/equity pure-mode combinations.

This is a research-only follow-up to Phase K. It tests untried pure-mode
combinations of the K1 holder-only rule with BTC/equity outperformance-frequency
signals, without touching production data fetches, MROI construction, or dashboard
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
from onchain_index.composite import holder_behavior_composite
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
K1_BASELINE_OOS_ALPHA = 21.0
SWITCH_HURDLE_OOS_ALPHA = K1_BASELINE_OOS_ALPHA + PROMOTION_BAR_PP
DIVERSIFICATION_WITHIN_K1_PP = 0.5
DECISIVE_LOSS_VS_K1_PP = -1.0
TAIL_RISK_THRESHOLD = -1.5
AMBIGUOUS_HOLDER_ABS_THRESHOLD = 0.5
OUTPERFORMANCE_WINDOWS: tuple[int, ...] = (30, 90, 180)
BINARY_TIER_TO_PCT = {"CASH": 0.0, "STAY LONG": 100.0}


@dataclass(frozen=True)
class HolderBtcEqCandidate:
    """Fixed Phase L candidate definition."""

    candidate_id: str
    label: str
    family: str
    rule_type: str
    btc_equity_column: str
    source: str
    notes: str
    holder_weight: float | None = None


def phase_l_candidates() -> list[HolderBtcEqCandidate]:
    """Return the fixed Phase L holder × BTC/equity pure-mode candidate set."""
    weighted = [
        HolderBtcEqCandidate(
            candidate_id=f"l1{suffix}_holder_{int(weight * 10)}0_btc_nasdaq_90d_weighted",
            label=f"L1{suffix} — weighted {weight:.1f}/{1.0 - weight:.1f}",
            family=f"L1{suffix}",
            rule_type="weighted_average",
            btc_equity_column="btc_nasdaq_outperf_freq_z_90d",
            source="Production holder behavior plus Yahoo BTC-USD / ^IXIC daily closes",
            notes=(
                f"STAY LONG if {weight:.1f}·z(holder) + {1.0 - weight:.1f}·"
                "z(BTC/NASDAQ 90d outperformance frequency) > 0 else CASH."
            ),
            holder_weight=weight,
        )
        for suffix, weight in (("a", 0.7), ("b", 0.8), ("c", 0.9))
    ]
    return [
        *weighted,
        HolderBtcEqCandidate(
            candidate_id="l2_holder_with_btc_nasdaq_90d_tail_filter",
            label="L2 — asymmetric safety filter",
            family="L2",
            rule_type="tail_filter",
            btc_equity_column="btc_nasdaq_outperf_freq_z_90d",
            source="Production holder behavior plus Yahoo BTC-USD / ^IXIC daily closes",
            notes=(
                "K1 holder rule, but force CASH when BTC/NASDAQ 90d outperformance "
                "frequency z-score is below -1.5."
            ),
        ),
        HolderBtcEqCandidate(
            candidate_id="l3_holder_btc_nasdaq_90d_tiebreaker",
            label="L3 — hierarchical tiebreaker",
            family="L3",
            rule_type="tiebreaker",
            btc_equity_column="btc_nasdaq_outperf_freq_z_90d",
            source="Production holder behavior plus Yahoo BTC-USD / ^IXIC daily closes",
            notes=(
                "Use K1 when |z(holder)| >= 0.5; inside the holder ambiguous zone, "
                "use the sign of BTC/NASDAQ 90d outperformance frequency."
            ),
        ),
        HolderBtcEqCandidate(
            candidate_id="l4a_holder_and_btc_nasdaq_30d",
            label="L4a — conjunction 30d NASDAQ",
            family="L4a",
            rule_type="conjunction",
            btc_equity_column="btc_nasdaq_outperf_freq_z_30d",
            source="Production holder behavior plus Yahoo BTC-USD / ^IXIC daily closes",
            notes="STAY LONG only when holder and BTC/NASDAQ 30d outperformance are positive.",
        ),
        HolderBtcEqCandidate(
            candidate_id="l4b_holder_and_btc_nasdaq_180d",
            label="L4b — conjunction 180d NASDAQ",
            family="L4b",
            rule_type="conjunction",
            btc_equity_column="btc_nasdaq_outperf_freq_z_180d",
            source="Production holder behavior plus Yahoo BTC-USD / ^IXIC daily closes",
            notes="STAY LONG only when holder and BTC/NASDAQ 180d outperformance are positive.",
        ),
        HolderBtcEqCandidate(
            candidate_id="l4c_holder_and_btc_spx_90d",
            label="L4c — conjunction 90d SPX",
            family="L4c",
            rule_type="conjunction",
            btc_equity_column="btc_spx_outperf_freq_z_90d",
            source="Production holder behavior plus Yahoo BTC-USD / ^GSPC daily closes",
            notes="STAY LONG only when holder and BTC/S&P 500 90d outperformance are positive.",
        ),
    ]


def _empty_tiers(index: pd.Index) -> pd.Series:
    """Return an object Series for binary CASH/STAY LONG tiers."""
    return pd.Series(pd.NA, index=index, dtype="object")


def pure_holder_tiers(holder: pd.Series) -> pd.Series:
    """Return the K1 holder-only pure-mode tiers."""
    tiers = _empty_tiers(holder.index)
    tiers = tiers.mask(holder <= 0.0, "CASH")
    tiers = tiers.mask(holder > 0.0, "STAY LONG")
    return tiers.where(holder.notna())


def weighted_tiers(holder: pd.Series, btc_equity: pd.Series, holder_weight: float) -> pd.Series:
    """Return weighted holder × BTC/equity pure-mode tiers."""
    score = holder_weight * holder + (1.0 - holder_weight) * btc_equity
    tiers = _empty_tiers(score.index)
    tiers = tiers.mask(score <= 0.0, "CASH")
    tiers = tiers.mask(score > 0.0, "STAY LONG")
    return tiers.where(score.notna())


def tail_filter_tiers(holder: pd.Series, btc_equity: pd.Series) -> pd.Series:
    """Return K1 tiers with BTC/equity as tail-risk-only cash filter."""
    tiers = pure_holder_tiers(holder)
    tiers = tiers.mask(btc_equity < TAIL_RISK_THRESHOLD, "CASH")
    return tiers.where(holder.notna())


def tiebreaker_tiers(holder: pd.Series, btc_equity: pd.Series) -> pd.Series:
    """Return K1 tiers, using BTC/equity sign only when holder is ambiguous."""
    tiers = pure_holder_tiers(holder)
    ambiguous = holder.abs() < AMBIGUOUS_HOLDER_ABS_THRESHOLD
    tiers = tiers.mask(ambiguous & (btc_equity <= 0.0), "CASH")
    tiers = tiers.mask(ambiguous & (btc_equity > 0.0), "STAY LONG")
    unresolved = ambiguous & btc_equity.isna()
    return tiers.where(holder.notna() & ~unresolved)


def conjunction_tiers(holder: pd.Series, btc_equity: pd.Series) -> pd.Series:
    """Return pure holder AND BTC/equity conjunction tiers."""
    tiers = _empty_tiers(holder.index)
    tiers = tiers.mask((holder <= 0.0) | (btc_equity <= 0.0), "CASH")
    tiers = tiers.mask((holder > 0.0) & (btc_equity > 0.0), "STAY LONG")
    return tiers.where(holder.notna() & btc_equity.notna())


def build_spines(
    data: pd.DataFrame,
    *,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    use_cache: bool = True,
) -> pd.DataFrame:
    """Build Phase L holder and BTC/equity outperformance-frequency spines."""
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
    """Return Phase L non-return diagnostics for a tier series."""
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
    candidate: HolderBtcEqCandidate,
    holder: pd.Series,
    spines: pd.DataFrame,
) -> pd.Series:
    """Build tiers for one Phase L candidate."""
    btc_equity = cast(pd.Series, spines[candidate.btc_equity_column])
    if candidate.rule_type == "weighted_average":
        if candidate.holder_weight is None:
            raise ValueError(f"missing holder weight for {candidate.candidate_id}")
        return weighted_tiers(holder, btc_equity, candidate.holder_weight)
    if candidate.rule_type == "tail_filter":
        return tail_filter_tiers(holder, btc_equity)
    if candidate.rule_type == "tiebreaker":
        return tiebreaker_tiers(holder, btc_equity)
    if candidate.rule_type == "conjunction":
        return conjunction_tiers(holder, btc_equity)
    raise ValueError(f"unknown rule_type {candidate.rule_type!r}")


def _rule_text(candidate: HolderBtcEqCandidate) -> str:
    """Return a compact rule description for one Phase L candidate."""
    if candidate.rule_type == "weighted_average":
        weight = cast(float, candidate.holder_weight)
        return f"STAY LONG if {weight:.1f}·z(holder) + {1.0 - weight:.1f}·z(btc_eq) > 0 else CASH"
    if candidate.rule_type == "tail_filter":
        return "STAY LONG if z(holder) > 0 unless z(btc_eq) < -1.5, else CASH"
    if candidate.rule_type == "tiebreaker":
        return "Use z(holder) sign when |z(holder)| >= 0.5; otherwise use z(btc_eq) sign"
    return "STAY LONG if z(holder) > 0 AND z(btc_eq) > 0 else CASH"


def _evaluate_tiers(
    tiers: pd.Series, ret: pd.Series
) -> tuple[dict[str, Any], float | None, list[float], list[int]]:
    """Evaluate a tier series full-sample and by BTC cycle."""
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
    full_sample = {**rounded_metrics(full_metrics), **_diagnostics(tiers)}
    return (
        {"full_sample": full_sample, "cycle_metrics": cycle_metrics},
        oos_alpha,
        cycle_alphas,
        cycle_switches,
    )


def _k1_reference(holder: pd.Series, ret: pd.Series) -> dict[str, Any]:
    """Return computed K1 holder-only reference diagnostics on this data snapshot."""
    tiers = pure_holder_tiers(holder)
    metrics, oos_alpha, cycle_alphas, cycle_switches = _evaluate_tiers(tiers, ret)
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
        "avg_regime_switches_per_cycle": round(float(np.mean(cycle_switches)), 6)
        if cycle_switches
        else None,
    }


def evaluate_candidate(
    candidate: HolderBtcEqCandidate,
    holder: pd.Series,
    spines: pd.DataFrame,
    ret: pd.Series,
) -> dict[str, Any]:
    """Evaluate one fixed Phase L candidate full-sample and by BTC cycle."""
    btc_equity = cast(pd.Series, spines[candidate.btc_equity_column])
    tiers = _candidate_tiers(candidate, holder, spines)
    metrics, oos_alpha, cycle_alphas, cycle_switches = _evaluate_tiers(tiers, ret)

    return {
        "candidate": {
            "id": candidate.candidate_id,
            "label": candidate.label,
            "family": candidate.family,
            "rule_type": candidate.rule_type,
            "btc_equity_column": candidate.btc_equity_column,
            "holder_weight": candidate.holder_weight,
            "source": candidate.source,
            "rule": _rule_text(candidate),
            "pure_mode": True,
            "valuation_override": None,
            "tier_to_pct": BINARY_TIER_TO_PCT,
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
        "avg_regime_switches_per_cycle": round(float(np.mean(cycle_switches)), 6)
        if cycle_switches
        else None,
        "btc_equity_vs_holder_correlation": _correlation(btc_equity, holder),
    }


def _best_candidate(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Return the result with the highest OOS median alpha."""
    ranked = [row for row in results if isinstance(row.get("oos_median_alpha"), int | float)]
    if not ranked:
        raise ValueError("no finite candidate OOS alpha results")
    ranked.sort(key=lambda row: (-float(row["oos_median_alpha"]), str(row["candidate"]["id"])))
    return ranked[0]


def _max_drawdown(row: dict[str, Any]) -> float | None:
    """Return finite full-sample strategy max drawdown for a result row."""
    full_sample = cast(dict[str, Any], row["full_sample"])
    drawdown = full_sample.get("strat_dd")
    if not isinstance(drawdown, int | float) or not math.isfinite(drawdown):
        return None
    return float(drawdown)


def _recommendation(results: list[dict[str, Any]], k1_reference: dict[str, Any]) -> dict[str, Any]:
    """Apply the Phase L decision tree to holder × BTC/equity results."""
    best = _best_candidate(results)
    best_alpha = cast(float, best["oos_median_alpha"])
    best_delta = round(best_alpha - K1_BASELINE_OOS_ALPHA, 6)
    k1_full = cast(dict[str, Any], k1_reference["full_sample"])
    k1_max_dd = float(cast(float, k1_full["strat_dd"]))

    diversification_candidates = []
    for row in results:
        alpha = row.get("oos_median_alpha")
        drawdown = _max_drawdown(row)
        if not isinstance(alpha, int | float) or drawdown is None:
            continue
        delta = float(alpha) - K1_BASELINE_OOS_ALPHA
        if delta >= -DIVERSIFICATION_WITHIN_K1_PP and drawdown > k1_max_dd:
            diversification_candidates.append(row)

    decisive_losses = all(
        isinstance(row.get("oos_median_alpha"), int | float)
        and float(row["oos_median_alpha"]) - K1_BASELINE_OOS_ALPHA <= DECISIVE_LOSS_VS_K1_PP
        for row in results
    )

    if best_alpha >= SWITCH_HURDLE_OOS_ALPHA:
        branch = "1_switch"
        action = f"switch-to-{best['candidate']['family'].lower()}"
        text = (
            f"Switch to {best['candidate']['label']}: it reached {best_alpha:.1f}% OOS "
            "median alpha, clearing the +22.0% K1+1pp switch hurdle."
        )
    elif diversification_candidates:
        diversification_candidates.sort(
            key=lambda row: (-float(row["oos_median_alpha"]), str(row["candidate"]["id"]))
        )
        candidate = diversification_candidates[0]
        branch = "2_diversification_benefit_candidate"
        action = "stress-test-diversification-benefit-candidate"
        text = (
            f"Stress-test {candidate['candidate']['label']}: it finished within 0.5pp of K1 "
            "and had lower full-sample max drawdown."
        )
    elif decisive_losses:
        branch = "3_k1_wins_decisively"
        action = "dispatch-production-migration-to-k1"
        text = (
            "All Phase L holder × BTC/equity candidates lost to K1 by at least 1pp, so "
            "K1 holder-only pure wins decisively; dispatch production migration."
        )
    else:
        branch = "keep_k1_no_switch"
        action = "keep-k1-holder-only-pure"
        text = (
            "No Phase L candidate cleared +22.0% or earned the drawdown diversification branch; "
            "keep K1 holder-only pure as the production-migration target."
        )

    return {
        "baseline_id": "k1_holder_behavior_pure_reference",
        "k1_reference_oos_median_alpha": K1_BASELINE_OOS_ALPHA,
        "promotion_bar_pp": PROMOTION_BAR_PP,
        "switch_hurdle_oos_median_alpha": round(SWITCH_HURDLE_OOS_ALPHA, 6),
        "diversification_within_k1_pp": DIVERSIFICATION_WITHIN_K1_PP,
        "decisive_loss_vs_k1_pp": DECISIVE_LOSS_VS_K1_PP,
        "k1_full_sample_max_drawdown": round(k1_max_dd, 6),
        "best_candidate_id": best["candidate"]["id"],
        "best_candidate_label": best["candidate"]["label"],
        "best_oos_median_alpha": round(best_alpha, 6),
        "best_delta_vs_k1_reference_pp": best_delta,
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
    """Run the fixed Phase L holder × BTC/equity comparison and optionally write JSON."""
    ret = cast(pd.Series, data["btc_price"]).pct_change()
    spines = build_spines(data, cache_dir=cache_dir, use_cache=use_cache)
    holder = cast(pd.Series, spines["holder_behavior"])
    candidates = phase_l_candidates()
    results = [evaluate_candidate(candidate, holder, spines, ret) for candidate in candidates]
    k1_reference = _k1_reference(holder, ret)

    payload = envelope(
        "phase_l_holder_btceq_combinations",
        {
            "promotion_bar_pp": PROMOTION_BAR_PP,
            "k1_reference_oos_median_alpha": K1_BASELINE_OOS_ALPHA,
            "switch_hurdle_oos_median_alpha": SWITCH_HURDLE_OOS_ALPHA,
            "methodology": {
                "walk_forward": (
                    "Each fixed pure-mode rule is evaluated full-sample and separately on each "
                    "BTC_CYCLES window; no candidate is selected in-sample."
                ),
                "metric": "Out-of-sample median alpha across the four cycle results.",
                "pure_mode": (
                    "No valuation input and no valuation override in any Phase L candidate."
                ),
                "decision_rule": (
                    "Clear +22.0% OOS to switch; finish within 0.5pp of K1 with lower "
                    "full-sample max drawdown to mark a diversification-benefit candidate; "
                    "lose by 1pp+ to K1 across all rows and K1 wins decisively."
                ),
                "missing_btc_equity_handling": (
                    "Weighted and conjunction rows require both holder and BTC/equity metrics. "
                    "The L2 tail filter follows K1 when BTC/equity is unavailable because the "
                    "filter can only force CASH on observed tail-risk days. The L3 tiebreaker "
                    "requires BTC/equity only inside the holder ambiguous zone."
                ),
            },
            "data_snapshot": {
                "rows": int(len(data)),
                "start": str(data.index.min()),
                "end": str(data.index.max()),
                "holder_non_nan": int(holder.notna().sum()),
                "spine_non_nan": {
                    column: int(cast(pd.Series, spines[column]).notna().sum())
                    for column in spines.columns
                },
            },
            "candidate_grid": {
                "candidate_count": len(results),
                "outperformance_frequency_windows": list(OUTPERFORMANCE_WINDOWS),
                "k2_metric": "btc_nasdaq_outperf_freq_z_90d",
                "valuation_override": None,
                "modes": ["weighted_average", "tail_filter", "tiebreaker", "conjunction"],
            },
            "k1_reference": k1_reference,
            "results": results,
            "recommendation": _recommendation(results, k1_reference),
        },
    )
    if output_path is not None:
        write_json(output_path, payload)
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare Phase L holder × BTC/equity pure-mode combinations."
    )
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--output", type=Path, default=default_output_path("phase_l.json"))
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
