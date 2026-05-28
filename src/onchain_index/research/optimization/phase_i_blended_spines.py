"""Phase I research: test blended BTC/equity spines with valuation override.

This is a research-only audit. It extends Phase H's Yahoo-based relative-strength
work without touching production data fetches, MROI construction, or dashboard code.
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
    multi_timeframe_relative_strength_blend,
    outperformance_frequency_z,
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
PROMISING_WITHIN_BASELINE_PP = 0.5
VALUATION_OVERRIDE_THRESHOLD = 2.0
RELATIVE_STRENGTH_LOOKBACKS: tuple[int, ...] = (30, 90, 180)
BINARY_TIER_TO_PCT = {"CASH": 0.0, "STAY LONG": 100.0}


@dataclass(frozen=True)
class SpineCandidate:
    """Fixed Phase I spine candidate definition."""

    candidate_id: str
    label: str
    family: str
    spine_column: str
    rule_type: str
    source: str
    notes: str
    selected_from: str | None = None


def base_phase_i_candidates() -> list[SpineCandidate]:
    """Return I1/I2 BTC/equity candidates before I3/I4 selection."""
    return [
        SpineCandidate(
            candidate_id="i1a_btc_nasdaq_rs_blend",
            label="I1a — BTC/NASDAQ RS blend",
            family="I1a",
            spine_column="btc_nasdaq_rs_blend_z",
            rule_type="spine",
            source="Yahoo BTC-USD / ^IXIC daily closes",
            notes="Mean of 30d, 90d, and 180d BTC/NASDAQ relative-strength z-scores.",
        ),
        SpineCandidate(
            candidate_id="i1b_btc_spx_rs_blend",
            label="I1b — BTC/SPX RS blend",
            family="I1b",
            spine_column="btc_spx_rs_blend_z",
            rule_type="spine",
            source="Yahoo BTC-USD / ^GSPC daily closes",
            notes="Mean of 30d, 90d, and 180d BTC/SPX relative-strength z-scores.",
        ),
        SpineCandidate(
            candidate_id="i2a_btc_nasdaq_outperf_90d",
            label="I2a — BTC/NASDAQ outperformance 90d",
            family="I2a",
            spine_column="btc_nasdaq_outperf_freq_z_90d",
            rule_type="spine",
            source="Yahoo BTC-USD / ^IXIC daily closes",
            notes="Z-score of rolling 90d share of days BTC outperformed NASDAQ.",
        ),
        SpineCandidate(
            candidate_id="i2b_btc_spx_outperf_90d",
            label="I2b — BTC/SPX outperformance 90d",
            family="I2b",
            spine_column="btc_spx_outperf_freq_z_90d",
            rule_type="spine",
            source="Yahoo BTC-USD / ^GSPC daily closes",
            notes="Z-score of rolling 90d share of days BTC outperformed S&P 500.",
        ),
        SpineCandidate(
            candidate_id="i2c_btc_nasdaq_outperf_30d",
            label="I2c — BTC/NASDAQ outperformance 30d",
            family="I2c",
            spine_column="btc_nasdaq_outperf_freq_z_30d",
            rule_type="spine",
            source="Yahoo BTC-USD / ^IXIC daily closes",
            notes="Z-score of rolling 30d share of days BTC outperformed NASDAQ.",
        ),
        SpineCandidate(
            candidate_id="i2d_btc_nasdaq_outperf_180d",
            label="I2d — BTC/NASDAQ outperformance 180d",
            family="I2d",
            spine_column="btc_nasdaq_outperf_freq_z_180d",
            rule_type="spine",
            source="Yahoo BTC-USD / ^IXIC daily closes",
            notes="Z-score of rolling 180d share of days BTC outperformed NASDAQ.",
        ),
    ]


def _empty_tiers(index: pd.Index) -> pd.Series:
    """Return an object Series for binary CASH/STAY LONG tiers."""
    return pd.Series(pd.NA, index=index, dtype="object")


def override_tiers(valuation: pd.Series, spine: pd.Series) -> pd.Series:
    """Return valuation-override tiers with a candidate spine in the middle."""
    tiers = _empty_tiers(valuation.index)
    tiers = tiers.mask(spine <= 0.0, "CASH")
    tiers = tiers.mask(spine > 0.0, "STAY LONG")
    tiers = tiers.mask(valuation > VALUATION_OVERRIDE_THRESHOLD, "CASH")
    tiers = tiers.mask(valuation < -VALUATION_OVERRIDE_THRESHOLD, "STAY LONG")
    return tiers.where(valuation.notna() & spine.notna())


def conjunction_tiers(valuation: pd.Series, holder: pd.Series, btc_equity: pd.Series) -> pd.Series:
    """Return valuation-override tiers with holder AND BTC/equity agreement in the middle."""
    tiers = _empty_tiers(valuation.index)
    tiers = tiers.mask((holder <= 0.0) | (btc_equity <= 0.0), "CASH")
    tiers = tiers.mask((holder > 0.0) & (btc_equity > 0.0), "STAY LONG")
    tiers = tiers.mask(valuation > VALUATION_OVERRIDE_THRESHOLD, "CASH")
    tiers = tiers.mask(valuation < -VALUATION_OVERRIDE_THRESHOLD, "STAY LONG")
    return tiers.where(valuation.notna() & holder.notna() & btc_equity.notna())


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
    """Build Phase I BTC/equity candidate spine series on the Phase A daily index."""
    closes = yahoo_daily_closes(data.index, cache_dir=cache_dir, use_cache=use_cache)
    spines = {
        "holder_behavior": holder_behavior_composite(data),
        "btc_nasdaq_rs_blend_z": multi_timeframe_relative_strength_blend(
            closes, "btc_usd_close", "nasdaq_close", RELATIVE_STRENGTH_LOOKBACKS
        ),
        "btc_spx_rs_blend_z": multi_timeframe_relative_strength_blend(
            closes, "btc_usd_close", "spx_close", RELATIVE_STRENGTH_LOOKBACKS
        ),
        "btc_nasdaq_outperf_freq_z_90d": outperformance_frequency_z(
            closes, "btc_usd_close", "nasdaq_close", 90
        ),
        "btc_spx_outperf_freq_z_90d": outperformance_frequency_z(
            closes, "btc_usd_close", "spx_close", 90
        ),
        "btc_nasdaq_outperf_freq_z_30d": outperformance_frequency_z(
            closes, "btc_usd_close", "nasdaq_close", 30
        ),
        "btc_nasdaq_outperf_freq_z_180d": outperformance_frequency_z(
            closes, "btc_usd_close", "nasdaq_close", 180
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
    """Return Phase I non-return diagnostics for a tier series."""
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
    valuation: pd.Series,
    holder: pd.Series,
    spines: pd.DataFrame,
) -> pd.Series:
    """Build tiers for one Phase I candidate."""
    spine = cast(pd.Series, spines[candidate.spine_column])
    if candidate.rule_type == "conjunction":
        return conjunction_tiers(valuation, holder, spine)
    return override_tiers(valuation, spine)


def _rule_text(candidate: SpineCandidate) -> str:
    """Return a compact rule description for one candidate."""
    override = "if z(valuation) > +2.0: CASH; elif z(valuation) < -2.0: STAY LONG; else "
    if candidate.rule_type == "conjunction":
        return override + "STAY LONG if z(holder) > 0 AND z(best BTC/equity) > 0 else CASH"
    return override + "STAY LONG if z(spine) > 0 else CASH"


def evaluate_candidate(
    candidate: SpineCandidate,
    valuation: pd.Series,
    holder: pd.Series,
    spines: pd.DataFrame,
    baseline_score: pd.Series,
    ret: pd.Series,
) -> dict[str, Any]:
    """Evaluate one fixed Phase I candidate full-sample and by BTC cycle."""
    spine = cast(pd.Series, spines[candidate.spine_column])
    correlation_spine = (
        cast(pd.Series, spines["holder_btc_equity_conjunction"])
        if candidate.rule_type == "conjunction" and "holder_btc_equity_conjunction" in spines
        else spine
    )
    tiers = _candidate_tiers(candidate, valuation, holder, spines)
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
            "rule_type": candidate.rule_type,
            "source": candidate.source,
            "rule": _rule_text(candidate),
            "valuation_override_threshold": VALUATION_OVERRIDE_THRESHOLD,
            "tier_to_pct": BINARY_TIER_TO_PCT,
            "selected_from": candidate.selected_from,
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
    """Return finite full-sample alpha for I3/I4 BTC/equity metric selection."""
    full_sample = cast(dict[str, Any], result["full_sample"])
    alpha = full_sample.get("alpha")
    if not isinstance(alpha, int | float) or not math.isfinite(alpha):
        return -math.inf
    return float(alpha)


def _select_best_btc_equity_metric(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Select the best I1/I2 BTC/equity metric by full-sample alpha."""
    ranked = [row for row in results if str(row["candidate"]["family"]).startswith(("I1", "I2"))]
    if not ranked:
        raise ValueError("no finite I1/I2 BTC/equity metric results")
    ranked.sort(key=lambda row: (-_full_sample_alpha(row), str(row["candidate"]["id"])))
    return ranked[0]


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
    """Apply the Phase I promotion rule to spine results."""
    best = _best_candidate(results)
    best_alpha = cast(float, best["oos_median_alpha"])
    best_delta = round(best_alpha - ADDITIVE_BASELINE_OOS_ALPHA, 6)

    if best_alpha >= SWITCH_HURDLE_OOS_ALPHA:
        action = f"switch-to-spine-{best['candidate']['family'].lower()}"
        text = (
            f"Switch to {best['candidate']['label']}: it reached {best_alpha:.1f}% OOS "
            "median alpha, clearing the +19.1% switch hurdle."
        )
    elif best_delta >= -PROMISING_WITHIN_BASELINE_PP:
        action = "promising-but-needs-more"
        text = (
            f"Promising but needs more work: {best['candidate']['label']} finished within "
            f"0.5pp of the +18.1% additive reference but did not clear +19.1%."
        )
    else:
        action = "keep-additive"
        text = (
            "Keep current additive: no Phase I candidate beat the +19.1% switch hurdle, "
            "and none was within 0.5pp of the +18.1% additive reference."
        )

    return {
        "baseline_id": "additive_baseline_reference",
        "additive_reference_oos_median_alpha": ADDITIVE_BASELINE_OOS_ALPHA,
        "promotion_bar_pp": PROMOTION_BAR_PP,
        "switch_hurdle_oos_median_alpha": round(SWITCH_HURDLE_OOS_ALPHA, 6),
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
    """Run the fixed Phase I spine comparison and optionally write JSON."""
    ret = cast(pd.Series, data["btc_price"]).pct_change()
    valuation = valuation_composite(data)
    holder = holder_behavior_composite(data)
    baseline_score = valuation + holder
    spines = build_spines(data, cache_dir=cache_dir, use_cache=use_cache)

    candidates = base_phase_i_candidates()
    base_results = [
        evaluate_candidate(candidate, valuation, holder, spines, baseline_score, ret)
        for candidate in candidates
    ]
    selected = _select_best_btc_equity_metric(base_results)
    selected_column = str(selected["candidate"]["spine_column"])
    selected_id = str(selected["candidate"]["id"])
    selected_label = str(selected["candidate"]["label"])

    selected_spine = cast(pd.Series, spines[selected_column])
    spines["holder_btc_equity_composite_z"] = pd.concat(
        [holder, selected_spine], axis=1
    ).mean(axis=1)
    spines["holder_btc_equity_conjunction"] = (
        (holder > 0.0) & (selected_spine > 0.0)
    ).astype(float).where(holder.notna() & selected_spine.notna())

    selected_candidates = [
        SpineCandidate(
            candidate_id="i3_holder_best_btc_equity_composite",
            label=f"I3 — holder + {selected_label}",
            family="I3",
            spine_column="holder_btc_equity_composite_z",
            rule_type="spine",
            source="Production holder behavior plus selected Phase I BTC/equity metric",
            notes="Mean of z(holder_behavior) and z(best BTC/equity metric by full-sample alpha).",
            selected_from=selected_id,
        ),
        SpineCandidate(
            candidate_id="i4_holder_best_btc_equity_conjunction",
            label=f"I4 — holder AND {selected_label}",
            family="I4",
            spine_column=selected_column,
            rule_type="conjunction",
            source="Production holder behavior plus selected Phase I BTC/equity metric",
            notes=(
                "STAY LONG only when holder behavior and selected BTC/equity metric "
                "are positive."
            ),
            selected_from=selected_id,
        ),
    ]
    selected_results = [
        evaluate_candidate(candidate, valuation, holder, spines, baseline_score, ret)
        for candidate in selected_candidates
    ]
    results = base_results + selected_results

    payload = envelope(
        "phase_i_blended_spines",
        {
            "promotion_bar_pp": PROMOTION_BAR_PP,
            "additive_reference_oos_median_alpha": ADDITIVE_BASELINE_OOS_ALPHA,
            "switch_hurdle_oos_median_alpha": SWITCH_HURDLE_OOS_ALPHA,
            "valuation_override_threshold": VALUATION_OVERRIDE_THRESHOLD,
            "methodology": {
                "walk_forward": (
                    "Each fixed spine+valuation-override rule is evaluated on each BTC cycle "
                    "window from BTC_CYCLES. I3/I4 use the I1/I2 BTC/equity metric selected "
                    "by full-sample alpha, not by the OOS median headline metric."
                ),
                "metric": "Out-of-sample median alpha across the four cycle results.",
                "promotion_rule": (
                    "A spine switch must beat the +18.1% additive reference by at least "
                    "1pp OOS, i.e. clear +19.1% OOS median alpha."
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
                "outperformance_frequency_windows": [30, 90, 180],
                "valuation_override_threshold": VALUATION_OVERRIDE_THRESHOLD,
            },
            "i3_i4_selection": {
                "criterion": (
                    "Highest full-sample alpha among I1/I2 candidates; "
                    "OOS median not used."
                ),
                "selected_candidate_id": selected_id,
                "selected_candidate_label": selected_label,
                "selected_spine_column": selected_column,
                "selected_full_sample_alpha": _full_sample_alpha(selected),
                "selected_oos_median_alpha": selected["oos_median_alpha"],
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
        description="Compare Phase I blended BTC/equity spines with valuation override."
    )
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--output", type=Path, default=default_output_path("phase_i.json"))
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
