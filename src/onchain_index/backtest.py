"""Standalone binary-signal backtest helpers for onchain-index.

Phase B deliberately keeps this module small and reusable: the same signal
constructors used for the standalone audit should be reused by Phase C composite
construction so backtest and production paths do not drift.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

import numpy as np
import pandas as pd

TRADING_DAYS_PER_YEAR = 252
DEFAULT_ZSCORE_WINDOW = 504

CycleMap = Mapping[str, tuple[str, str]]

BTC_CYCLES: dict[str, tuple[str, str]] = {
    "2014-2017": ("2014-01-01", "2017-12-31"),
    "2018-2021": ("2018-01-01", "2021-12-31"),
    "2022-2024": ("2022-01-01", "2024-12-31"),
    "2025-now": ("2025-01-01", "2100-01-01"),
}


@dataclass(frozen=True)
class IndicatorSignalSpec:
    """Canonical standalone signal definition used in the Phase B audit."""

    name: str
    rule: str
    source_columns: tuple[str, ...]


PHASE_B_INDICATORS: tuple[IndicatorSignalSpec, ...] = (
    IndicatorSignalSpec("MVRV-Z", "504d trailing z-score > 0", ("mvrv_zscore",)),
    IndicatorSignalSpec("NUPL", "504d trailing z-score > 0", ("nupl",)),
    IndicatorSignalSpec("LTH MVRV", "504d trailing z-score > 0", ("lth_mvrv",)),
    IndicatorSignalSpec("STH MVRV", "504d trailing z-score > 0", ("sth_mvrv",)),
    IndicatorSignalSpec("Puell Multiple", "504d trailing z-score > 0", ("puell_multiple",)),
    IndicatorSignalSpec(
        "Hash Ribbon", "lagged 30d hashrate MA > 60d MA", ("hash_30dma", "hash_60dma")
    ),
    IndicatorSignalSpec(
        "Address Growth",
        "504d trailing z-score of (30d active-address MA / 365d MA − 1) > 0",
        ("adr_dma30", "adr_dma365"),
    ),
    IndicatorSignalSpec("HODL 1Y+", "504d trailing z-score > 0", ("hodl_1yr_pct",)),
    IndicatorSignalSpec(
        "Reserve Risk", "504d trailing z-score > 0; not inverted", ("reserve_risk",)
    ),
    IndicatorSignalSpec("RHODL Ratio", "504d trailing z-score > 0", ("rhodl_ratio",)),
    IndicatorSignalSpec("ETF Net Flow", "30d trailing net-flow sum > 0", ("etf_net_flow_m",)),
    IndicatorSignalSpec("MSTR Holdings Δ", "30d trailing holdings change > 0", ("mstr_btc",)),
    IndicatorSignalSpec("Coinbase Premium", "30d trailing premium mean > 0", ("cb_premium_pct",)),
)


def rolling_zscore(series: pd.Series, window: int = DEFAULT_ZSCORE_WINDOW) -> pd.Series:
    """Return a trailing rolling z-score using values available through yesterday.

    The one-day shift is intentional: a signal dated ``T`` must only use data
    available at ``T-1`` or earlier, because it is applied to the return on ``T``.
    """
    prior = series.astype(float).shift(1)
    mean = prior.rolling(window=window, min_periods=window).mean()
    std = prior.rolling(window=window, min_periods=window).std()
    return (prior - mean) / std.replace(0, np.nan)


def binary_signal_from_zscore(series: pd.Series, window: int = DEFAULT_ZSCORE_WINDOW) -> pd.Series:
    """Build a binary long/cash signal from a trailing z-score > 0."""
    zscore = rolling_zscore(series, window=window)
    return (zscore > 0).astype(float).where(zscore.notna())


def binary_signal_from_cross(fast: pd.Series, slow: pd.Series) -> pd.Series:
    """Build a binary long/cash signal from a lagged fast > slow cross."""
    aligned = pd.concat({"fast": fast.astype(float), "slow": slow.astype(float)}, axis=1)
    prior = aligned.shift(1)
    signal = prior["fast"] > prior["slow"]
    return signal.astype(float).where(prior.notna().all(axis=1))


def binary_signal_above(series: pd.Series, threshold: float = 0.0) -> pd.Series:
    """Build a binary long/cash signal from yesterday's value above a threshold."""
    prior = series.astype(float).shift(1)
    return (prior > threshold).astype(float).where(prior.notna())


def binary_signal_from_rolling_sum(
    series: pd.Series, window: int = 30, threshold: float = 0.0
) -> pd.Series:
    """Build a binary signal from a trailing rolling sum above ``threshold``."""
    prior = series.astype(float).shift(1)
    total = cast(pd.Series, prior.rolling(window=window, min_periods=window).sum())
    flag = cast(pd.Series, total.gt(threshold).astype(float))
    return flag.where(total.notna())


def binary_signal_from_rolling_mean(
    series: pd.Series, window: int = 30, threshold: float = 0.0
) -> pd.Series:
    """Build a binary signal from a trailing rolling mean above ``threshold``."""
    prior = series.astype(float).shift(1)
    mean = cast(pd.Series, prior.rolling(window=window, min_periods=window).mean())
    flag = cast(pd.Series, mean.gt(threshold).astype(float))
    return flag.where(mean.notna())


def binary_signal_from_delta(
    series: pd.Series, periods: int = 30, threshold: float = 0.0
) -> pd.Series:
    """Build a binary signal from a lagged multi-day change above ``threshold``."""
    prior = series.astype(float).shift(1)
    delta = prior.diff(periods)
    flag = cast(pd.Series, delta.gt(threshold).astype(float))
    return flag.where(delta.notna())


def _column(data: pd.DataFrame, name: str) -> pd.Series:
    """Return a named DataFrame column as a Series for pandas/pyright interop."""
    return cast(pd.Series, data[name])


def build_phase_b_indicator_signals(data: pd.DataFrame) -> dict[str, pd.Series]:
    """Build the canonical standalone signals for Phase B and later Phase C reuse."""
    adr_dma30 = _column(data, "adr_dma30")
    adr_dma365 = _column(data, "adr_dma365")
    address_growth = adr_dma30 / adr_dma365 - 1

    etf_flow = _column(data, "etf_net_flow_m").copy()
    etf_flow.loc[etf_flow.index < pd.Timestamp("2024-01-11")] = np.nan

    return {
        "MVRV-Z": binary_signal_from_zscore(_column(data, "mvrv_zscore")),
        "NUPL": binary_signal_from_zscore(_column(data, "nupl")),
        "LTH MVRV": binary_signal_from_zscore(_column(data, "lth_mvrv")),
        "STH MVRV": binary_signal_from_zscore(_column(data, "sth_mvrv")),
        "Puell Multiple": binary_signal_from_zscore(_column(data, "puell_multiple")),
        "Hash Ribbon": binary_signal_from_cross(
            _column(data, "hash_30dma"), _column(data, "hash_60dma")
        ),
        "Address Growth": binary_signal_from_zscore(address_growth),
        "HODL 1Y+": binary_signal_from_zscore(_column(data, "hodl_1yr_pct")),
        "Reserve Risk": binary_signal_from_zscore(_column(data, "reserve_risk")),
        "RHODL Ratio": binary_signal_from_zscore(_column(data, "rhodl_ratio")),
        "ETF Net Flow": binary_signal_from_rolling_sum(etf_flow, window=30),
        "MSTR Holdings Δ": binary_signal_from_delta(_column(data, "mstr_btc"), periods=30),
        "Coinbase Premium": binary_signal_from_rolling_mean(
            _column(data, "cb_premium_pct"), window=30
        ),
    }


def backtest_signal(
    signal: pd.Series,
    ret: pd.Series,
    delay: int = 0,
    cost_per_flip: float = 0.0,
) -> dict[str, float] | None:
    """Backtest a binary signal (>0 = invested) against daily returns.

    Metrics intentionally mirror ``macro_framework.backtest_production`` so BTC
    standalone-alpha results remain comparable with the macro-framework audit.
    """
    sig = signal.shift(delay) if delay > 0 else signal
    df = pd.DataFrame({"sig": sig, "ret": ret}).dropna()
    if len(df) < 100:
        return None

    invested = df["sig"] > 0
    n_years = len(df) / TRADING_DAYS_PER_YEAR

    strat_ret = df["ret"].where(invested, 0.0)
    flips = invested.astype(int).diff().abs().fillna(0)
    if cost_per_flip > 0:
        strat_ret = strat_ret - flips * cost_per_flip

    bh_cum = (1 + df["ret"]).cumprod()
    strat_cum = (1 + strat_ret).cumprod()

    bh_total = (bh_cum.iloc[-1] - 1) * 100
    strat_total = (strat_cum.iloc[-1] - 1) * 100
    bh_ann = ((1 + bh_total / 100) ** (1 / n_years) - 1) * 100 if n_years > 0 else 0.0
    strat_ann = ((1 + strat_total / 100) ** (1 / n_years) - 1) * 100 if n_years > 0 else 0.0

    bh_dd = ((bh_cum / bh_cum.cummax()) - 1).min() * 100
    strat_dd = ((strat_cum / strat_cum.cummax()) - 1).min() * 100

    n_flips = float(flips.sum())
    return {
        "bh_ann": float(bh_ann),
        "strat_ann": float(strat_ann),
        "alpha": float(strat_ann - bh_ann),
        "bh_dd": float(bh_dd),
        "strat_dd": float(strat_dd),
        "green_pct": float(invested.mean() * 100),
        "flips_yr": float(n_flips / n_years),
        "avg_dur": float(len(df) / max(n_flips, 1.0)) if n_flips else float(len(df)),
        "n_years": float(n_years),
        "n_obs": float(len(df)),
    }


def walk_forward_by_cycle(
    signal: pd.Series,
    ret: pd.Series,
    cycles: CycleMap = BTC_CYCLES,
) -> dict[str, dict[str, float] | None]:
    """Backtest one signal separately inside BTC cycle windows."""
    out: dict[str, dict[str, float] | None] = {}
    for name, (start, end) in cycles.items():
        mask = (signal.index >= pd.Timestamp(start)) & (signal.index <= pd.Timestamp(end))
        out[name] = backtest_signal(signal.loc[mask], ret.reindex(signal.index).loc[mask])
    return out
