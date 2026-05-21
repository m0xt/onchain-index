from __future__ import annotations

import json

import numpy as np
import pandas as pd

from onchain_index.research.optimization.optimize_cohort_weights import (
    run_optimization as run_step1,
)
from onchain_index.research.optimization.optimize_constituent_weights import (
    run_optimization as run_step3,
)
from onchain_index.research.optimization.optimize_thresholds import run_optimization as run_step2
from onchain_index.research.optimization.optimize_tier_structure import (
    run_optimization as run_tier_structure,
)


def _optimization_sample_frame() -> pd.DataFrame:
    idx = pd.date_range("2012-01-01", periods=5300)
    t = np.arange(len(idx), dtype=float)
    wave = np.sin(t / 55.0)
    fast = np.sin(t / 17.0)
    slow = np.cos(t / 240.0)
    mstr = np.where(idx < pd.Timestamp("2020-08-10"), np.nan, 100_000 + t * 20 + fast * 500)
    etf = np.where(idx < pd.Timestamp("2024-01-11"), 0.0, np.sin(t / 19.0) * 120)
    price = 1_000 + np.exp(t / 900.0) + t * 3 + wave * 120
    return pd.DataFrame(
        {
            "btc_price": price,
            "sth_mvrv": 1.2 + wave + t / 7000,
            "rhodl_ratio": 2_000 + t * 0.4 + np.sin(t / 50.0) * 100,
            "puell_multiple": 1.0 + np.sin(t / 60.0) / 2,
            "mvrv_zscore": 1.5 + slow + t / 6000,
            "hodl_1yr_pct": 55 + np.sin(t / 120.0) * 8,
            "mstr_btc": mstr,
            "etf_net_flow_m": etf,
        },
        index=idx,
    )


def _assert_optimizer_json(path, expected_step: str) -> dict:
    assert path.exists()
    payload = json.loads(path.read_text())
    assert payload["step"] == expected_step
    assert payload["grid_results"]
    assert payload["walk_forward"]["folds"]
    assert "median_oos_alpha_improvement_pp" in payload["walk_forward"]
    return payload


def test_step1_optimizer_writes_expected_json_shape(tmp_path) -> None:
    output = tmp_path / "step1.json"

    payload = run_step1(_optimization_sample_frame(), output_path=output)

    assert payload["step"] == "cohort_dimension_weights"
    saved = _assert_optimizer_json(output, "cohort_dimension_weights")
    assert len(saved["grid_results"]) == 12
    assert "max_abs_oos_alpha_delta_pp" in saved["perturbation"]


def test_step2_optimizer_writes_expected_json_shape(tmp_path) -> None:
    output = tmp_path / "step2.json"

    payload = run_step2(_optimization_sample_frame(), output_path=output)

    assert payload["step"] == "tier_thresholds"
    saved = _assert_optimizer_json(output, "tier_thresholds")
    assert len(saved["grid_results"]) >= 18
    assert "continue_to_step3" in saved


def test_step3_optimizer_writes_expected_json_shape(tmp_path) -> None:
    output = tmp_path / "step3.json"

    payload = run_step3(_optimization_sample_frame(), output_path=output)

    assert payload["step"] == "valuation_constituent_weights"
    saved = _assert_optimizer_json(output, "valuation_constituent_weights")
    assert saved["grid_results"]
    assert "max_abs_oos_alpha_delta_pp" in saved["perturbation"]


def test_tier_structure_optimizer_writes_expected_json_shape(tmp_path) -> None:
    output = tmp_path / "tier_structure.json"

    payload = run_tier_structure(_optimization_sample_frame(), output_path=output)

    assert payload["step"] == "tier_structure_parsimony"
    saved = json.loads(output.read_text())
    assert len(saved["results"]) == 4
    assert [row["candidate"]["id"] for row in saved["results"]] == [
        "2_tier",
        "3_tier",
        "4_tier",
        "5_tier",
    ]
    assert "delta_vs_4tier_pp" in saved["results"][0]
    assert saved["recommendation"]["action"]
