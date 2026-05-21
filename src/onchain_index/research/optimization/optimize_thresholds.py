"""Step 2 optimizer: MROI sizing-tier thresholds."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

import pandas as pd

from onchain_index.composite import holder_behavior_composite, valuation_composite
from onchain_index.data import DEFAULT_CACHE_DIR
from onchain_index.research.optimization.common import (
    DEFAULT_THRESHOLDS,
    Candidate,
    Metrics,
    backtest_score,
    default_output_path,
    envelope,
    grid_diagnostics,
    json_ready,
    load_data,
    perturbation_summary,
    should_continue,
    walk_forward_grid,
    write_json,
)

BASELINE_ID = "thr_-1.00_0.00_1.00"


def threshold_grid() -> list[Candidate]:
    """Return the coarse monotonic threshold grid from the Phase D spec."""
    lows = [-1.5, -1.0, -0.5]
    mids = [-0.25, 0.0, 0.25]
    highs = [0.5, 1.0, 1.5]
    grid: list[Candidate] = []
    for low in lows:
        for mid in mids:
            for high in highs:
                if low < mid < high:
                    grid.append(
                        {
                            "id": f"thr_{low:.2f}_{mid:.2f}_{high:.2f}",
                            "thresholds": (low, mid, high),
                        }
                    )
    return grid


def build_score(
    data: pd.DataFrame, *, valuation_weight: float = 1.0, holder_weight: float = 1.0
) -> pd.Series:
    """Build a MROI candidate from production dimension composites."""
    score = (
        valuation_composite(data) * valuation_weight
        + holder_behavior_composite(data) * holder_weight
    )
    score.name = "mroi"
    return score


def complexity(candidate: Candidate) -> float:
    thresholds = cast(Sequence[float], candidate["thresholds"])
    return sum(
        abs(float(value) - baseline)
        for value, baseline in zip(thresholds, DEFAULT_THRESHOLDS, strict=True)
    )


def run_optimization(
    data: pd.DataFrame,
    *,
    valuation_weight: float = 1.0,
    holder_weight: float = 1.0,
    output_path: Path | None = None,
) -> dict[str, Any]:
    """Run Step 2 and optionally write `.cache/optim/step2.json`."""
    ret = cast(pd.Series, data["btc_price"]).pct_change()
    score = build_score(data, valuation_weight=valuation_weight, holder_weight=holder_weight)
    grid = threshold_grid()

    def evaluate(candidate: Candidate, mask: pd.Series) -> Metrics | None:
        thresholds = cast(tuple[float, float, float], tuple(candidate["thresholds"]))
        return backtest_score(score, ret, mask, thresholds=thresholds)

    wf = walk_forward_grid(
        data=data,
        candidates=grid,
        evaluate=evaluate,
        complexity=complexity,
        baseline_id=BASELINE_ID,
    )

    def perturb(candidate: Candidate) -> list[Candidate]:
        thresholds = tuple(float(value) for value in cast(Sequence[float], candidate["thresholds"]))
        out: list[Candidate] = []
        for idx, value in enumerate(thresholds):
            for multiplier in (0.9, 1.1):
                perturbed = list(thresholds)
                perturbed[idx] = value * multiplier
                if perturbed[0] < perturbed[1] < perturbed[2]:
                    out.append(
                        {
                            "id": f"{candidate['id']}_b{idx}_x{multiplier:.1f}",
                            "thresholds": tuple(perturbed),
                            "perturbation": f"boundary {idx} × {multiplier:.1f}",
                        }
                    )
        return out

    payload = envelope(
        "tier_thresholds",
        {
            "methodology": {
                "walk_forward": "Leave-one-cycle-out after Step 1 acceptance.",
                "grid": (
                    "Coarse monotonic thresholds from lower {-1.5,-1,-0.5}, "
                    "middle {-0.25,0,0.25}, upper {0.5,1,1.5}."
                ),
                "cohort_weights": {
                    "valuation": valuation_weight,
                    "holder_behavior": holder_weight,
                },
            },
            "grid_results": grid_diagnostics(data=data, candidates=grid, evaluate=evaluate),
            "walk_forward": wf,
            "perturbation": perturbation_summary(
                data=data, folds=wf["folds"], evaluate=evaluate, perturb=perturb
            ),
            "continue_to_step3": should_continue(wf),
        },
    )
    if output_path is not None:
        write_json(output_path, payload)
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Optimize Phase D tier thresholds.")
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--valuation-weight", type=float, default=1.0)
    parser.add_argument("--holder-weight", type=float, default=1.0)
    parser.add_argument("--output", type=Path, default=default_output_path("step2.json"))
    args = parser.parse_args(argv)

    data = load_data(cache_dir=cast(Path, args.cache_dir), use_cache=not bool(args.no_cache))
    payload = run_optimization(
        data,
        valuation_weight=float(args.valuation_weight),
        holder_weight=float(args.holder_weight),
        output_path=cast(Path, args.output),
    )
    print(json.dumps(json_ready(payload["walk_forward"]), indent=2, sort_keys=True))
    print(f"wrote {cast(Path, args.output)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
