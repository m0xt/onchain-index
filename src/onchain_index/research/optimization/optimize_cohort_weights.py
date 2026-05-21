"""Step 1 optimizer: valuation-vs-holder cohort dimension weights."""

from __future__ import annotations

import argparse
import json
import math
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

import pandas as pd

from onchain_index.composite import holder_behavior_composite, valuation_composite
from onchain_index.data import DEFAULT_CACHE_DIR
from onchain_index.research.optimization.common import (
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

BASELINE_ID = "raw_wv1.00_wh1.00a"


def _normalized_weights(raw_valuation: float, raw_holder: float) -> tuple[float, float]:
    total = raw_valuation + raw_holder
    return (2.0 * raw_valuation / total, 2.0 * raw_holder / total)


def cohort_weight_grid() -> list[Candidate]:
    """Return the 12-combination ratio grid from the Phase D spec."""
    values = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0]
    grid: list[Candidate] = []
    for idx, raw_ratio in enumerate(values):
        wv, wh = _normalized_weights(raw_ratio, 1.0)
        suffix = "a" if raw_ratio == 1.0 else ""
        grid.append(
            {
                "id": f"raw_wv{raw_ratio:.2f}_wh1.00{suffix}",
                "raw_weights": {"valuation": raw_ratio, "holder_behavior": 1.0},
                "weights": {"valuation": wv, "holder_behavior": wh},
                "ratio": wv / wh,
                "grid_order": idx,
            }
        )
    for idx, raw_ratio in enumerate(values):
        wv, wh = _normalized_weights(1.0, raw_ratio)
        suffix = "b" if raw_ratio == 1.0 else ""
        grid.append(
            {
                "id": f"raw_wv1.00_wh{raw_ratio:.2f}{suffix}",
                "raw_weights": {"valuation": 1.0, "holder_behavior": raw_ratio},
                "weights": {"valuation": wv, "holder_behavior": wh},
                "ratio": wv / wh,
                "grid_order": len(values) + idx,
            }
        )
    return grid


def build_score(data: pd.DataFrame, candidate: Candidate) -> pd.Series:
    """Build a candidate MROI from production dimension composites."""
    weights = cast(dict[str, float], candidate["weights"])
    score = (
        valuation_composite(data) * weights["valuation"]
        + holder_behavior_composite(data) * weights["holder_behavior"]
    )
    score.name = "mroi"
    return score


def complexity(candidate: Candidate) -> float:
    """Prefer equal-weight candidates on exact ties."""
    ratio = float(candidate["ratio"])
    return abs(math.log(ratio))


def run_optimization(data: pd.DataFrame, *, output_path: Path | None = None) -> dict[str, Any]:
    """Run Step 1 and optionally write `.cache/optim/step1.json`."""
    ret = cast(pd.Series, data["btc_price"]).pct_change()
    grid = cohort_weight_grid()
    score_cache: dict[str, pd.Series] = {}

    def score_for(candidate: Candidate) -> pd.Series:
        candidate_id = str(candidate["id"])
        if candidate_id not in score_cache:
            score_cache[candidate_id] = build_score(data, candidate)
        return score_cache[candidate_id]

    def evaluate(candidate: Candidate, mask: pd.Series) -> Metrics | None:
        return backtest_score(score_for(candidate), ret, mask)

    wf = walk_forward_grid(
        data=data,
        candidates=grid,
        evaluate=evaluate,
        complexity=complexity,
        baseline_id=BASELINE_ID,
    )

    def perturb(candidate: Candidate) -> list[Candidate]:
        ratio = float(candidate["ratio"])
        out: list[Candidate] = []
        for multiplier in (0.9, 1.1):
            perturbed_ratio = ratio * multiplier
            wv, wh = _normalized_weights(perturbed_ratio, 1.0)
            out.append(
                {
                    "id": f"{candidate['id']}_ratio_x{multiplier:.1f}",
                    "weights": {"valuation": wv, "holder_behavior": wh},
                    "ratio": perturbed_ratio,
                    "perturbation": f"ratio × {multiplier:.1f}",
                }
            )
        return out

    payload = envelope(
        "cohort_dimension_weights",
        {
            "methodology": {
                "walk_forward": (
                    "Leave-one-cycle-out: choose best on the other three BTC cycles, "
                    "test on the held-out cycle."
                ),
                "grid": (
                    "12 raw valuation/holder combinations from "
                    "{0.5,0.75,1.0,1.25,1.5,2.0} and inverse; weights "
                    "normalized to sum to 2 so threshold scale is not retuned."
                ),
                "selection_metric": (
                    "training alpha vs BTC buy-and-hold from the production "
                    "tiered backtest"
                ),
            },
            "grid_results": grid_diagnostics(data=data, candidates=grid, evaluate=evaluate),
            "walk_forward": wf,
            "perturbation": perturbation_summary(
                data=data, folds=wf["folds"], evaluate=evaluate, perturb=perturb
            ),
            "continue_to_step2": should_continue(wf),
        },
    )
    if output_path is not None:
        write_json(output_path, payload)
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Optimize Phase D cohort dimension weights.")
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--output", type=Path, default=default_output_path("step1.json"))
    args = parser.parse_args(argv)

    data = load_data(cache_dir=cast(Path, args.cache_dir), use_cache=not bool(args.no_cache))
    payload = run_optimization(data, output_path=cast(Path, args.output))
    summary = payload["walk_forward"]
    print(json.dumps(json_ready(summary), indent=2, sort_keys=True))
    print(f"wrote {cast(Path, args.output)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
