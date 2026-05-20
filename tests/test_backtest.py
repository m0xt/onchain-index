from __future__ import annotations

import pandas as pd

from onchain_index.backtest import (
    BTC_CYCLES,
    backtest_signal,
    backtest_tiered_signal,
    binary_signal_from_cross,
    binary_signal_from_zscore,
    walk_forward_by_cycle,
)


def test_zscore_signal_is_lagged() -> None:
    series = pd.Series([2.0, 1.0, 10.0, 10.0, 10.0], index=pd.date_range("2024-01-01", periods=5))

    signal = binary_signal_from_zscore(series, window=2)

    assert signal.iloc[2] == 0.0  # the day-3 spike is not visible until the next bar
    assert signal.iloc[3] == 1.0


def test_cross_signal_is_lagged() -> None:
    idx = pd.date_range("2024-01-01", periods=4)
    fast = pd.Series([1.0, 1.0, 3.0, 3.0], index=idx)
    slow = pd.Series([2.0, 2.0, 2.0, 2.0], index=idx)

    signal = binary_signal_from_cross(fast, slow)

    assert signal.iloc[2] == 0.0
    assert signal.iloc[3] == 1.0


def test_backtest_signal_metrics_smoke() -> None:
    idx = pd.date_range("2024-01-01", periods=130)
    signal = pd.Series([1.0] * 65 + [0.0] * 65, index=idx)
    ret = pd.Series([0.001] * 130, index=idx)

    result = backtest_signal(signal, ret)

    assert result is not None
    assert result["green_pct"] == 50.0
    assert result["flips_yr"] > 0
    assert result["strat_ann"] < result["bh_ann"]


def test_walk_forward_by_cycle_returns_all_cycles() -> None:
    idx = pd.date_range("2014-01-01", periods=3650)
    signal = pd.Series(1.0, index=idx)
    ret = pd.Series(0.001, index=idx)

    result = walk_forward_by_cycle(signal, ret)

    assert set(result) == set(BTC_CYCLES)
    assert result["2014-2017"] is not None


def test_backtest_tiered_signal_metrics_smoke() -> None:
    idx = pd.date_range("2024-01-01", periods=130)
    tiers = pd.Series(["Strong"] * 65 + ["Cash"] * 65, index=idx)
    ret = pd.Series([0.001] * 130, index=idx)

    result = backtest_tiered_signal(
        tiers, ret, {"Cash": 0.0, "Trim": 50.0, "Sized": 75.0, "Strong": 100.0}
    )

    assert result is not None
    assert result["avg_allocation_pct"] == 50.0
    assert result["tier_transitions_yr"] > 0
    assert result["strat_ann"] < result["bh_ann"]
