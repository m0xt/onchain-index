"""Shared walk-forward helpers for Phase D optimization research.

This module intentionally consumes the production composite/backtest functions instead
of cloning signal construction. Optimization outputs are candidates for review only;
nothing here is used by the production dashboard or cron path.
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import numpy as np
import pandas as pd

from onchain_index.backtest import BTC_CYCLES, CycleMap, backtest_tiered_signal
from onchain_index.composite import TIER_PCT, sizing_tier
from onchain_index.data import DEFAULT_CACHE_DIR, PROJECT_ROOT, RAW_CACHE_NAME, fetch_all

Candidate = dict[str, Any]
Metrics = dict[str, float]
Evaluator = Callable[[Candidate, pd.Series], Metrics | None]
ComplexityFn = Callable[[Candidate], float]

DEFAULT_THRESHOLDS: tuple[float, float, float] = (-1.0, 0.0, 1.0)
STOPPING_RULE_PP = 2.0


def load_data(*, cache_dir: Path = DEFAULT_CACHE_DIR, use_cache: bool = True) -> pd.DataFrame:
    """Load the cached raw frame, fetching only if the cache is absent/stale."""
    cache_path = Path(cache_dir).expanduser().resolve() / RAW_CACHE_NAME
    if use_cache and cache_path.exists():
        return cast(pd.DataFrame, pd.read_pickle(cache_path))
    return fetch_all(use_cache=use_cache, cache_dir=cache_dir)


def cycle_mask(index: pd.Index, cycles: CycleMap, names: Sequence[str]) -> pd.Series:
    """Return a boolean mask selecting one or more BTC cycle windows."""
    mask = pd.Series(False, index=index)
    for name in names:
        start, end = cycles[name]
        mask = mask | ((index >= pd.Timestamp(start)) & (index <= pd.Timestamp(end)))
    return mask


def alpha_metric(metrics: Metrics | None) -> float:
    """Extract alpha, returning -inf for failed/short backtests."""
    if metrics is None:
        return -math.inf
    value = metrics.get("alpha")
    return float(value) if value is not None and math.isfinite(value) else -math.inf


def rounded_metrics(metrics: Metrics | None) -> dict[str, float | None]:
    """JSON-friendly copy of the common backtest metrics."""
    if metrics is None:
        return {}
    return {key: round(float(value), 6) for key, value in metrics.items()}


def backtest_score(
    score: pd.Series,
    ret: pd.Series,
    mask: pd.Series,
    *,
    thresholds: tuple[float, float, float] = DEFAULT_THRESHOLDS,
) -> Metrics | None:
    """Backtest a PI_score-style series through the production tier mapper."""
    local_score = score.reindex(mask.index).loc[mask]
    local_ret = ret.reindex(mask.index).loc[mask]
    tiers = sizing_tier(local_score, thresholds=thresholds)
    return backtest_tiered_signal(tiers, local_ret, TIER_PCT)


def walk_forward_grid(
    *,
    data: pd.DataFrame,
    candidates: Sequence[Candidate],
    evaluate: Evaluator,
    complexity: ComplexityFn,
    baseline_id: str,
    cycles: CycleMap = BTC_CYCLES,
) -> dict[str, Any]:
    """Select the best in-sample candidate on all-but-one cycles and test held out."""
    if not candidates:
        raise ValueError("candidate grid is empty")

    baseline = next((candidate for candidate in candidates if candidate["id"] == baseline_id), None)
    if baseline is None:
        raise ValueError(f"baseline candidate {baseline_id!r} not found")

    cycle_names = list(cycles)
    folds: list[dict[str, Any]] = []
    optimized_oos_alphas: list[float] = []
    baseline_oos_alphas: list[float] = []

    for test_cycle in cycle_names:
        train_cycles = [name for name in cycle_names if name != test_cycle]
        train_mask = cycle_mask(data.index, cycles, train_cycles)
        test_mask = cycle_mask(data.index, cycles, [test_cycle])

        ranked: list[tuple[float, float, str, Candidate, Metrics | None]] = []
        for candidate in candidates:
            metrics = evaluate(candidate, train_mask)
            ranked.append(
                (
                    -alpha_metric(metrics),
                    complexity(candidate),
                    str(candidate["id"]),
                    candidate,
                    metrics,
                )
            )
        ranked.sort(key=lambda item: (item[0], item[1], item[2]))
        _, _, _, best, train_metrics = ranked[0]

        test_metrics = evaluate(best, test_mask)
        baseline_test_metrics = evaluate(baseline, test_mask)
        test_alpha = alpha_metric(test_metrics)
        baseline_alpha = alpha_metric(baseline_test_metrics)
        if math.isfinite(test_alpha):
            optimized_oos_alphas.append(test_alpha)
        if math.isfinite(baseline_alpha):
            baseline_oos_alphas.append(baseline_alpha)

        folds.append(
            {
                "test_cycle": test_cycle,
                "train_cycles": train_cycles,
                "best_candidate": json_ready(best),
                "train_metrics": rounded_metrics(train_metrics),
                "test_metrics": rounded_metrics(test_metrics),
                "baseline_test_metrics": rounded_metrics(baseline_test_metrics),
                "oos_alpha_improvement_pp": round(test_alpha - baseline_alpha, 6)
                if math.isfinite(test_alpha) and math.isfinite(baseline_alpha)
                else None,
            }
        )

    optimized_median = float(np.median(optimized_oos_alphas)) if optimized_oos_alphas else math.nan
    baseline_median = float(np.median(baseline_oos_alphas)) if baseline_oos_alphas else math.nan
    spread = (
        [float(np.min(optimized_oos_alphas)), float(np.max(optimized_oos_alphas))]
        if optimized_oos_alphas
        else []
    )

    return {
        "folds": folds,
        "median_oos_alpha": round(optimized_median, 6) if math.isfinite(optimized_median) else None,
        "baseline_median_oos_alpha": (
            round(baseline_median, 6) if math.isfinite(baseline_median) else None
        ),
        "median_oos_alpha_improvement_pp": round(optimized_median - baseline_median, 6)
        if math.isfinite(optimized_median) and math.isfinite(baseline_median)
        else None,
        "oos_alpha_spread": [round(value, 6) for value in spread],
    }


def grid_diagnostics(
    *,
    data: pd.DataFrame,
    candidates: Sequence[Candidate],
    evaluate: Evaluator,
    cycles: CycleMap = BTC_CYCLES,
) -> list[dict[str, Any]]:
    """Evaluate every candidate full-sample and cycle-by-cycle for reporting."""
    full_mask = pd.Series(True, index=data.index)
    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        full_metrics = evaluate(candidate, full_mask)
        cycle_rows: dict[str, dict[str, float | None]] = {}
        cycle_alphas: list[float] = []
        for cycle_name in cycles:
            mask = cycle_mask(data.index, cycles, [cycle_name])
            metrics = evaluate(candidate, mask)
            cycle_rows[cycle_name] = rounded_metrics(metrics)
            alpha = alpha_metric(metrics)
            if math.isfinite(alpha):
                cycle_alphas.append(alpha)
        rows.append(
            {
                "candidate": json_ready(candidate),
                "full_sample": rounded_metrics(full_metrics),
                "cycle_metrics": cycle_rows,
                "median_cycle_alpha": round(float(np.median(cycle_alphas)), 6)
                if cycle_alphas
                else None,
                "cycle_alpha_spread": [
                    round(float(np.min(cycle_alphas)), 6),
                    round(float(np.max(cycle_alphas)), 6),
                ]
                if cycle_alphas
                else [],
            }
        )
    return rows


def perturbation_summary(
    *,
    data: pd.DataFrame,
    folds: Sequence[Mapping[str, Any]],
    evaluate: Evaluator,
    perturb: Callable[[Candidate], Sequence[Candidate]],
    cycles: CycleMap = BTC_CYCLES,
) -> dict[str, Any]:
    """Measure held-out alpha sensitivity around each fold's selected candidate."""
    base_alphas: list[float] = []
    perturb_rows: list[dict[str, Any]] = []

    for fold in folds:
        test_cycle = str(fold["test_cycle"])
        test_mask = cycle_mask(data.index, cycles, [test_cycle])
        best = cast(Candidate, fold["best_candidate"])
        base_alpha = alpha_metric(evaluate(best, test_mask))
        if math.isfinite(base_alpha):
            base_alphas.append(base_alpha)
        for perturbed in perturb(best):
            metrics = evaluate(perturbed, test_mask)
            pert_alpha = alpha_metric(metrics)
            perturb_rows.append(
                {
                    "test_cycle": test_cycle,
                    "candidate": json_ready(perturbed),
                    "alpha": round(pert_alpha, 6) if math.isfinite(pert_alpha) else None,
                    "delta_vs_selected_pp": round(pert_alpha - base_alpha, 6)
                    if math.isfinite(pert_alpha) and math.isfinite(base_alpha)
                    else None,
                }
            )

    deltas = [
        abs(float(row["delta_vs_selected_pp"]))
        for row in perturb_rows
        if row["delta_vs_selected_pp"] is not None
    ]
    return {
        "procedure": "Perturb each selected fold candidate and re-test on the same held-out cycle.",
        "selected_median_oos_alpha": round(float(np.median(base_alphas)), 6)
        if base_alphas
        else None,
        "max_abs_oos_alpha_delta_pp": round(max(deltas), 6) if deltas else None,
        "rows": perturb_rows,
    }


def should_continue(summary: Mapping[str, Any]) -> bool:
    """Apply the Phase D 2pp out-of-sample stopping rule."""
    improvement = summary.get("median_oos_alpha_improvement_pp")
    return isinstance(improvement, int | float) and float(improvement) >= STOPPING_RULE_PP


def envelope(step: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Attach shared metadata to an optimizer result."""
    return {
        "step": step,
        "generated_at_utc": datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
        "stopping_rule_pp": STOPPING_RULE_PP,
        **payload,
    }


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    """Write structured optimizer output."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_ready(payload), indent=2, sort_keys=True) + "\n")


def default_output_path(name: str) -> Path:
    """Return the conventional .cache/optim output path."""
    return PROJECT_ROOT / ".cache" / "optim" / name


def json_ready(value: Any) -> Any:
    """Convert pandas/numpy scalars and tuples into JSON-safe values."""
    if isinstance(value, Mapping):
        return {str(key): json_ready(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [json_ready(item) for item in value]
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value
