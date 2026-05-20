"""Production PI_score composite for onchain-index.

The functions in this module are the canonical signal-construction path for both
live evaluation and Phase C backtests. Inputs are lagged through ``rolling_zscore``
so a score dated T only uses source data through T-1.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import cast

import numpy as np
import pandas as pd
from pandas.api.types import CategoricalDtype

from onchain_index.backtest import DEFAULT_ZSCORE_WINDOW, rolling_zscore

VALUATION_CONSTITUENTS: tuple[str, ...] = (
    "sth_mvrv",
    "rhodl_ratio",
    "puell_multiple",
    "mvrv_zscore",
)

TIER_ORDER: tuple[str, ...] = ("Cash", "Trim", "Sized", "Strong")
TIER_PCT: dict[str, float] = {
    "Cash": 0.0,
    "Trim": 50.0,
    "Sized": 75.0,
    "Strong": 100.0,
}
TIER_DTYPE = CategoricalDtype(categories=list(TIER_ORDER), ordered=True)

MSTR_START = pd.Timestamp("2020-08-10")
ETF_START = pd.Timestamp("2024-01-11")


def _column(data: pd.DataFrame, name: str) -> pd.Series:
    """Return a named DataFrame column as a Series for pandas/pyright interop."""
    return cast(pd.Series, data[name])


def _mean_available(frame: pd.DataFrame) -> pd.Series:
    """Mean across available constituent scores, leaving all-missing rows as NaN."""
    return cast(pd.Series, frame.mean(axis=1, skipna=True).where(frame.notna().any(axis=1)))


def valuation_constituents(data: pd.DataFrame, window: int = DEFAULT_ZSCORE_WINDOW) -> pd.DataFrame:
    """Return lagged z-scored valuation constituents used in ``valuation_composite``."""
    constituents = {
        name: rolling_zscore(_column(data, name), window=window)
        for name in VALUATION_CONSTITUENTS
    }
    return pd.DataFrame(constituents, index=data.index)


def valuation_composite(data: pd.DataFrame, window: int = DEFAULT_ZSCORE_WINDOW) -> pd.Series:
    """Equal-weighted z-score of the agreed valuation constituents.

    Constituents are STH MVRV, RHODL Ratio, Puell Multiple, and MVRV-Z. NUPL is
    deliberately excluded because Phase B found it highly colinear with MVRV-Z.
    """
    result = _mean_available(valuation_constituents(data, window=window))
    result.name = "valuation_composite"
    return result


def _on_chain_holder_cohort(data: pd.DataFrame, window: int) -> pd.Series:
    """On-chain holder-behavior cohort.

    Phase C keeps only the sign-corrected HODL-wave acceleration signal: a
    below-trend 30d change in 1Y+ HODL share. Level-based HODL, address-growth,
    Reserve Risk, and LTH MVRV rules failed the standalone gate.
    """
    hodl_delta_30d = _column(data, "hodl_1yr_pct").astype(float).diff(30)
    result = -rolling_zscore(hodl_delta_30d, window=window)
    result.name = "on_chain"
    return result


def _corporate_dat_cohort(data: pd.DataFrame, window: int) -> pd.Series:
    """Corporate DAT cohort from Strategy/MSTR 30d holdings change."""
    mstr = _column(data, "mstr_btc").astype(float).where(data.index >= MSTR_START)
    result = rolling_zscore(mstr.diff(30), window=window)
    result.name = "corporate_dat"
    return result


def _institutional_etf_cohort(data: pd.DataFrame, window: int) -> pd.Series:
    """Institutional ETF cohort from 30d net spot BTC ETF flow."""
    etf_flow = _column(data, "etf_net_flow_m").astype(float).where(data.index >= ETF_START)
    flow_sum = cast(pd.Series, etf_flow.rolling(window=30, min_periods=30).sum())
    result = rolling_zscore(flow_sum, window=window)
    result.name = "institutional_etf"
    return result


def holder_behavior_cohorts(
    data: pd.DataFrame, window: int = DEFAULT_ZSCORE_WINDOW
) -> dict[str, pd.Series]:
    """Return epoch-aware holder-behavior sub-cohort scores.

    ``exchange_flow`` is an all-NaN placeholder until a real exchange-flow source
    is added; it is surfaced explicitly so dashboards can show the data gap.
    """
    exchange_flow = pd.Series(np.nan, index=data.index, name="exchange_flow", dtype="float64")
    return {
        "on_chain": _on_chain_holder_cohort(data, window),
        "corporate_dat": _corporate_dat_cohort(data, window),
        "institutional_etf": _institutional_etf_cohort(data, window),
        "exchange_flow": exchange_flow,
    }


def holder_behavior_composite(
    data: pd.DataFrame, window: int = DEFAULT_ZSCORE_WINDOW
) -> pd.Series:
    """Equal-weighted z-score of available holder-behavior cohorts per date."""
    cohorts = pd.DataFrame(holder_behavior_cohorts(data, window=window), index=data.index)
    result = _mean_available(cohorts)
    result.name = "holder_behavior_composite"
    return result


def pi_score(data: pd.DataFrame, window: int = DEFAULT_ZSCORE_WINDOW) -> pd.Series:
    """Return the production PI_score: valuation dimension + holder dimension."""
    score = valuation_composite(data, window=window) + holder_behavior_composite(
        data, window=window
    )
    score.name = "pi_score"
    return score


def sizing_tier(
    pi_score: pd.Series,
    thresholds: tuple[float, float, float] = (-1.0, 0.0, 1.0),
    floor_pct: float = 0.0,
) -> pd.Series:
    """Map PI_score values into ordered sizing tiers.

    ``floor_pct`` is accepted so callers can switch the bottom bucket from cash to
    a structural-long floor without changing the public function signature. Labels
    remain descriptive; sizing percentages live in the backtest tier map.
    """
    del floor_pct  # label assignment is independent of the chosen bottom allocation.
    low, mid, high = thresholds
    values = pd.Series(pd.NA, index=pi_score.index, dtype="object")
    values = values.mask(pi_score < low, "Cash")
    values = values.mask((pi_score >= low) & (pi_score < mid), "Trim")
    values = values.mask((pi_score >= mid) & (pi_score < high), "Sized")
    values = values.mask(pi_score >= high, "Strong")
    return values.astype(TIER_DTYPE)


def epoch_for_date(value: str | date | datetime | pd.Timestamp) -> str:
    """Return the holder-cohort composition epoch label for a date-like value."""
    ts = pd.Timestamp(value)
    if ts < MSTR_START:
        return "2012-2020"
    if ts < ETF_START:
        return "2020-2024"
    return "2024-onward"
