"""Step 3 optimizer: valuation constituent weights."""

from __future__ import annotations

import argparse
import itertools
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

import pandas as pd

from onchain_index.composite import (
    VALUATION_CONSTITUENTS,
    holder_behavior_composite,
    valuation_constituents,
)
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
    walk_forward_grid,
    write_json,
)

BASELINE_ID = "val_1.0_1.0_1.0_1.0"


def valuation_weight_grid() -> list[Candidate]:
    """Return constituent weights in {0.5,1,1.5,2} constrained to sum to 4."""
    values = [0.5, 1.0, 1.5, 2.0]
    grid: list[Candidate] = []
    for weights in itertools.product(values, repeat=len(VALUATION_CONSTITUENTS)):
        if abs(sum(weights) - 4.0) > 1e-9:
            continue
        label = "_".join(f"{value:.1f}" for value in weights)
        grid.append(
            {
                "id": f"val_{label}",
                "weights": dict(zip(VALUATION_CONSTITUENTS, weights, strict=True)),
            }
        )
    return grid


def build_score(
    data: pd.DataFrame,
    candidate: Candidate,
    *,
    holder_weight: float = 1.0,
    thresholds: tuple[float, float, float] = DEFAULT_THRESHOLDS,
) -> pd.Series:
    """Build PI_score from production valuation constituents and holder composite."""
    del thresholds  # score construction is independent of tier thresholds.
    parts = valuation_constituents(data)
    weights = cast(dict[str, float], candidate["weights"])
    weighted = pd.DataFrame(
        {name: parts[name] * float(weights[name]) for name in VALUATION_CONSTITUENTS},
        index=data.index,
    )
    valuation = weighted.sum(axis=1, skipna=True) / sum(float(value) for value in weights.values())
    valuation = valuation.where(weighted.notna().any(axis=1))
    score = valuation + holder_behavior_composite(data) * holder_weight
    score.name = "pi_score"
    return score


def complexity(candidate: Candidate) -> float:
    weights = cast(dict[str, float], candidate["weights"])
    return sum(abs(float(weights[name]) - 1.0) for name in VALUATION_CONSTITUENTS)


def run_optimization(
    data: pd.DataFrame,
    *,
    holder_weight: float = 1.0,
    thresholds: tuple[float, float, float] = DEFAULT_THRESHOLDS,
    output_path: Path | None = None,
) -> dict[str, Any]:
    """Run Step 3 and optionally write `.cache/optim/step3.json`."""
    ret = cast(pd.Series, data["btc_price"]).pct_change()
    grid = valuation_weight_grid()
    score_cache: dict[str, pd.Series] = {}

    def score_for(candidate: Candidate) -> pd.Series:
        candidate_id = str(candidate["id"])
        if candidate_id not in score_cache:
            score_cache[candidate_id] = build_score(data, candidate, holder_weight=holder_weight)
        return score_cache[candidate_id]

    def evaluate(candidate: Candidate, mask: pd.Series) -> Metrics | None:
        return backtest_score(score_for(candidate), ret, mask, thresholds=thresholds)

    wf = walk_forward_grid(
        data=data,
        candidates=grid,
        evaluate=evaluate,
        complexity=complexity,
        baseline_id=BASELINE_ID,
    )

    def perturb(candidate: Candidate) -> list[Candidate]:
        raw_weights = cast(dict[str, float], candidate["weights"])
        weights = {name: float(value) for name, value in raw_weights.items()}
        out: list[Candidate] = []
        for name in VALUATION_CONSTITUENTS:
            for delta in (-0.1, 0.1):
                perturbed = dict(weights)
                perturbed[name] = max(0.1, perturbed[name] + delta)
                total = sum(perturbed.values())
                renormalized = {key: value * 4.0 / total for key, value in perturbed.items()}
                out.append(
                    {
                        "id": f"{candidate['id']}_{name}_{delta:+.1f}",
                        "weights": renormalized,
                        "perturbation": f"{name} {delta:+.1f}, renormalized to sum 4",
                    }
                )
        return out

    payload = envelope(
        "valuation_constituent_weights",
        {
            "methodology": {
                "walk_forward": "Leave-one-cycle-out after Steps 1 and 2 acceptance.",
                "grid": (
                    "Each valuation constituent weight in {0.5,1.0,1.5,2.0}, "
                    "constrained to sum to 4."
                ),
                "thresholds": thresholds,
                "holder_weight": holder_weight,
            },
            "grid_results": grid_diagnostics(data=data, candidates=grid, evaluate=evaluate),
            "walk_forward": wf,
            "perturbation": perturbation_summary(
                data=data, folds=wf["folds"], evaluate=evaluate, perturb=perturb
            ),
        },
    )
    if output_path is not None:
        write_json(output_path, payload)
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Optimize Phase D valuation constituent weights.")
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--holder-weight", type=float, default=1.0)
    parser.add_argument("--thresholds", nargs=3, type=float, default=list(DEFAULT_THRESHOLDS))
    parser.add_argument("--output", type=Path, default=default_output_path("step3.json"))
    args = parser.parse_args(argv)

    data = load_data(cache_dir=cast(Path, args.cache_dir), use_cache=not bool(args.no_cache))
    thresholds = tuple(float(value) for value in cast(Sequence[float], args.thresholds))
    if len(thresholds) != 3 or not thresholds[0] < thresholds[1] < thresholds[2]:
        raise SystemExit("--thresholds must be three monotonic values")
    payload = run_optimization(
        data,
        holder_weight=float(args.holder_weight),
        thresholds=cast(tuple[float, float, float], thresholds),
        output_path=cast(Path, args.output),
    )
    print(json.dumps(json_ready(payload["walk_forward"]), indent=2, sort_keys=True))
    print(f"wrote {cast(Path, args.output)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
