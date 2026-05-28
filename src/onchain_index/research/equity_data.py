"""Research-only Yahoo close fetches for relative-strength audits."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pandas as pd
import yfinance as yf

from onchain_index.backtest import DEFAULT_ZSCORE_WINDOW, rolling_zscore
from onchain_index.data import DEFAULT_CACHE_DIR

YAHOO_TICKERS: dict[str, str] = {
    "BTC-USD": "btc_usd_close",
    "^IXIC": "nasdaq_close",
    "^GSPC": "spx_close",
}
YAHOO_CLOSE_CACHE = "yahoo_daily_closes.pkl"


def _cache_path(cache_dir: Path) -> Path:
    """Return the local research cache path for Yahoo closes."""
    return Path(cache_dir).expanduser().resolve() / "research" / YAHOO_CLOSE_CACHE


def _daily_index(index: pd.Index) -> pd.DatetimeIndex:
    """Return midnight-naive daily timestamps for a pandas index."""
    values = pd.DatetimeIndex(pd.to_datetime(index)).tz_localize(None)
    return pd.DatetimeIndex(
        [cast(pd.Timestamp, pd.Timestamp(value)).normalize() for value in values]
    )


def _normalize_index(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize a Yahoo frame to midnight-naive daily timestamps."""
    normalized = frame.copy()
    normalized.index = _daily_index(normalized.index)
    return normalized.sort_index()


def _extract_close(downloaded: pd.DataFrame) -> pd.DataFrame:
    """Extract close columns from a yfinance download frame."""
    if isinstance(downloaded.columns, pd.MultiIndex):
        close_key = "Close" if "Close" in downloaded.columns.get_level_values(0) else "Adj Close"
        closes = downloaded[close_key]
    else:
        closes = downloaded[["Close"]]
    result = cast(pd.DataFrame, closes).rename(columns=YAHOO_TICKERS)
    return cast(pd.DataFrame, result[list(YAHOO_TICKERS.values())])


def _read_cached(path: Path, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame | None:
    """Return cached closes when they cover the requested window."""
    if not path.exists():
        return None
    cached = cast(pd.DataFrame, pd.read_pickle(path))
    if cached.empty or not set(YAHOO_TICKERS.values()).issubset(cached.columns):
        return None
    cached = _normalize_index(cached)
    cached_start = cast(pd.Timestamp, cached.index.min())
    cached_end = cast(pd.Timestamp, cached.index.max())
    if cached_start <= start and cached_end >= end:
        return cached
    return None


def yahoo_daily_closes(
    index: pd.Index,
    *,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    use_cache: bool = True,
) -> pd.DataFrame:
    """Fetch Yahoo BTC/equity closes and align them to the Phase A daily index."""
    daily_index = _daily_index(index)
    start = cast(pd.Timestamp, daily_index.min())
    end = cast(pd.Timestamp, daily_index.max())
    path = _cache_path(cache_dir)

    closes = _read_cached(path, start, end) if use_cache else None
    if closes is None:
        downloaded = cast(
            pd.DataFrame,
            yf.download(
                list(YAHOO_TICKERS),
                start=start.strftime("%Y-%m-%d"),
                end=(end + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
                auto_adjust=False,
                progress=False,
            ),
        )
        if downloaded.empty:
            raise RuntimeError("Yahoo close fetch returned no rows")
        closes = _normalize_index(_extract_close(downloaded))
        path.parent.mkdir(parents=True, exist_ok=True)
        closes.to_pickle(path)

    aligned = closes.reindex(daily_index).ffill()
    aligned.index = pd.DatetimeIndex(index)
    return aligned


def relative_strength_z(
    closes: pd.DataFrame, numerator: str, denominator: str, lookback: int
) -> pd.Series:
    """Return trailing z-score of BTC relative strength over a fixed lookback."""
    ratio = cast(pd.Series, closes[numerator].astype(float) / closes[denominator].astype(float))
    strength = cast(pd.Series, ratio.pct_change(lookback))
    result = rolling_zscore(strength, window=DEFAULT_ZSCORE_WINDOW)
    result.name = f"{numerator}_over_{denominator}_rs_z_{lookback}d"
    return result


def multi_timeframe_relative_strength_blend(
    closes: pd.DataFrame,
    numerator: str,
    denominator: str,
    lookbacks: tuple[int, ...],
) -> pd.Series:
    """Return the mean of fixed-lookback relative-strength z-scores."""
    components = [
        relative_strength_z(closes, numerator, denominator, lookback)
        for lookback in lookbacks
    ]
    result = pd.concat(components, axis=1).mean(axis=1)
    result.name = f"{numerator}_over_{denominator}_rs_blend_z"
    return cast(pd.Series, result)


def outperformance_frequency_z(
    closes: pd.DataFrame, numerator: str, denominator: str, window: int
) -> pd.Series:
    """Return z-score of rolling share of days numerator outperformed denominator."""
    returns = closes[[numerator, denominator]].astype(float).pct_change()
    numerator_ret = cast(pd.Series, returns[numerator])
    denominator_ret = cast(pd.Series, returns[denominator])
    outperformed = cast(pd.Series, numerator_ret.gt(denominator_ret).astype(float))
    frequency = cast(pd.Series, outperformed.rolling(window=window, min_periods=window).mean())
    result = rolling_zscore(frequency, window=DEFAULT_ZSCORE_WINDOW)
    result.name = f"{numerator}_over_{denominator}_outperf_freq_z_{window}d"
    return result
