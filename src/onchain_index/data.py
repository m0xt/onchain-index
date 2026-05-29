"""Raw data fetch layer for onchain-index.

This module intentionally contains data acquisition only. Composite construction,
backtests, optimization, and dashboard rendering belong to later phases.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import time
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from io import StringIO
from pathlib import Path
from typing import cast

import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CACHE_DIR = PROJECT_ROOT / ".cache"
RAW_CACHE_NAME = "raw_data.pkl"
CACHE_MAX_AGE = timedelta(hours=12)
OPS_SECRET_ENV = Path.home() / "ops" / "secrets" / "onchain-index" / ".env"

BMP_BASE = "https://api.bitcoinmagazinepro.com"
FARSIDE_ETF_FLOW_URL = "https://farside.co.uk/bitcoin-etf-flow-all-data/"
STRATEGY_TRACKER_MANIFEST_URL = "https://data.strategytracker.com/latest.json"
STRATEGY_TRACKER_BASE = "https://data.strategytracker.com"
COINBASE_CANDLES_URL = "https://api.exchange.coinbase.com/products/BTC-USD/candles"
BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"
COINBASE_PREMIUM_START = datetime(2023, 1, 1, tzinfo=UTC)
START_DATE = "2012-01-01"

UA_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

BMP_METRICS: dict[str, dict[str, str]] = {
    "mvrv-zscore": {
        "ZScore": "mvrv_zscore",
        "MarketCap": "market_cap",
        "realized_cap": "realized_cap",
        "Price": "btc_price",
    },
    "nupl": {"NUPL": "nupl"},
    "long-term-holder-mvrv": {"lth_mvrv": "lth_mvrv"},
    "short-term-holder-mvrv": {"sth_mvrv": "sth_mvrv"},
    "puell-multiple": {"puell_multiple": "puell_multiple"},
    "hashrate-ribbons": {"30dma": "hash_30dma", "60dma": "hash_60dma"},
    "active-address-growth-trend": {"dma30": "adr_dma30", "dma365": "adr_dma365"},
    "hodl-1y": {"1yr+": "hodl_1yr_pct"},
    "reserve-risk": {"Reserve Risk": "reserve_risk"},
    "rhodl-ratio": {"rhodl_ratio": "rhodl_ratio"},
}


def validate_secrets(env_file: Path = OPS_SECRET_ENV) -> str:
    """Load and validate required secrets before network work starts."""
    if env_file.exists():
        load_dotenv(env_file, override=False)

    api_key = os.environ.get("BMP_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "BMP_API_KEY is missing. Add it to "
            f"{env_file} or export BMP_API_KEY in the process environment."
        )
    return api_key


def _cache_path(cache_dir: Path | str) -> Path:
    return Path(cache_dir).expanduser().resolve() / RAW_CACHE_NAME


def _cache_is_fresh(path: Path, max_age: timedelta = CACHE_MAX_AGE) -> bool:
    if not path.exists():
        return False
    age = datetime.now().timestamp() - path.stat().st_mtime
    return age < max_age.total_seconds()


def _read_bmp_csv_payload(response: requests.Response) -> pd.DataFrame:
    """BMP returns a JSON-encoded CSV string."""
    payload = json.loads(response.text)
    if not isinstance(payload, str):
        raise ValueError("BMP metric response was not a JSON-encoded CSV string")
    return pd.read_csv(StringIO(payload))


def _fetch_bmp_metric(
    metric: str,
    col_map: dict[str, str],
    *,
    api_key: str,
    start_date: str = START_DATE,
    session: requests.Session | None = None,
) -> pd.DataFrame:
    client = session or requests.Session()
    url = f"{BMP_BASE}/metrics/{metric}"
    response = client.get(
        url,
        params={"from_date": start_date},
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=60,
    )
    response.raise_for_status()

    raw = _read_bmp_csv_payload(response)
    if "Date" not in raw.columns:
        raise ValueError(f"BMP metric {metric} response is missing Date column")

    raw.index = pd.to_datetime(raw["Date"])
    raw.index.name = "date"

    result = pd.DataFrame(index=raw.index)
    missing_columns: list[str] = []
    for api_col, local_col in col_map.items():
        if api_col not in raw.columns:
            missing_columns.append(api_col)
            continue
        result[local_col] = pd.to_numeric(raw[api_col], errors="coerce")

    if missing_columns:
        raise ValueError(f"BMP metric {metric} missing expected columns: {missing_columns}")
    return result


def fetch_bmp(*, api_key: str | None = None, start_date: str = START_DATE) -> pd.DataFrame:
    """Fetch on-chain indicators from Bitcoin Magazine Pro."""
    resolved_api_key = api_key or validate_secrets()
    frames: list[pd.DataFrame] = []

    with requests.Session() as session:
        for metric, col_map in BMP_METRICS.items():
            frame = _fetch_bmp_metric(
                metric,
                col_map,
                api_key=resolved_api_key,
                start_date=start_date,
                session=session,
            )
            frames.append(frame)

    combined = pd.concat(frames, axis=1)
    deduped = combined[~combined.index.duplicated(keep="last")]
    merged = deduped.sort_index().ffill().dropna(how="all")
    return cast(pd.DataFrame, merged)


def fetch_etf_flows() -> pd.DataFrame:
    """Fetch Farside daily spot BTC ETF flows in $M."""
    response = requests.get(
        FARSIDE_ETF_FLOW_URL,
        headers=UA_HEADERS,
        timeout=30,
    )
    response.raise_for_status()

    tables = pd.read_html(io.StringIO(response.text))
    candidates = [table for table in tables if table.shape[0] > 100 and "Date" in table.columns]
    if not candidates:
        raise ValueError("Could not find Farside ETF flow table")

    table = candidates[0]
    table = table[table["Date"].astype(str).str.match(r"\d{1,2} \w{3} \d{4}")].copy()
    table["date"] = pd.to_datetime(table["Date"], format="%d %b %Y")
    table = table.set_index("date").drop(columns=["Date"])

    def clean(value: object) -> float:
        if bool(pd.isna(value)):
            return np.nan
        text = str(value).strip().replace(",", "")
        if text in {"-", ""}:
            return 0.0
        if text.startswith("(") and text.endswith(")"):
            return -float(text[1:-1])
        return float(text)

    for column in table.columns:
        table[column] = table[column].map(clean)

    if "Total" not in table.columns:
        raise ValueError("Farside ETF table is missing Total column")
    return table.sort_index()


def fetch_strategy_holdings() -> pd.DataFrame:
    """Fetch Strategy/MSTR BTC holdings from strategytracker.com."""
    manifest_response = requests.get(
        STRATEGY_TRACKER_MANIFEST_URL,
        headers=UA_HEADERS,
        timeout=20,
    )
    manifest_response.raise_for_status()
    manifest = manifest_response.json()

    try:
        full_file = manifest["files"]["full"]
    except KeyError as exc:
        raise ValueError("strategytracker manifest is missing files.full") from exc

    data_response = requests.get(
        f"{STRATEGY_TRACKER_BASE}/{full_file}",
        headers=UA_HEADERS,
        timeout=60,
    )
    data_response.raise_for_status()
    data = data_response.json()

    try:
        history = data["companies"]["MSTR"]["historicalData"]
        frame = pd.DataFrame(
            {
                "btc_balance": history["btc_balance"],
                "cost_basis": history["cost_basis"],
                "mstr_stock": history["stock_prices"],
            },
            index=pd.to_datetime(history["dates"]),
        )
    except KeyError as exc:
        raise ValueError("strategytracker payload is missing MSTR historicalData fields") from exc

    frame.index.name = "date"
    return frame.sort_index()


def _coinbase_daily_closes(start: datetime, end: datetime) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    current = start

    while current < end:
        chunk_end = min(current + timedelta(days=290), end)
        response = requests.get(
            COINBASE_CANDLES_URL,
            params={
                "granularity": 86400,
                "start": current.isoformat(),
                "end": chunk_end.isoformat(),
            },
            headers=UA_HEADERS,
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError(f"Unexpected Coinbase candles payload: {payload!r}")
        frames.append(pd.DataFrame(payload, columns=["ts", "low", "high", "open", "close", "vol"]))
        current = chunk_end + timedelta(days=1)
        time.sleep(0.3)

    if not frames:
        raise ValueError("Coinbase returned no candle frames")

    coinbase = pd.concat(frames).drop_duplicates(subset=["ts"]).sort_values("ts")
    coinbase["date"] = pd.to_datetime(coinbase["ts"], unit="s").dt.normalize()
    close_frame = coinbase.set_index("date").loc[:, ["close"]].copy()
    close_frame.columns = ["coinbase"]
    return cast(pd.DataFrame, close_frame)


def _binance_daily_closes() -> pd.DataFrame:
    response = requests.get(
        BINANCE_KLINES_URL,
        params={"symbol": "BTCUSDT", "interval": "1d", "limit": 1000},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise ValueError(f"Unexpected Binance klines payload: {payload!r}")

    frame = pd.DataFrame(
        [
            {
                "date": pd.Timestamp(datetime.fromtimestamp(row[0] / 1000, tz=UTC).date()),
                "binance": float(row[4]),
            }
            for row in payload
        ]
    )
    if frame.empty:
        raise ValueError("Binance returned no daily closes")
    return frame.set_index("date")


def fetch_coinbase_premium(
    *, start: datetime | None = None, end: datetime | None = None
) -> pd.DataFrame:
    """Fetch daily Coinbase premium versus Binance BTCUSDT close."""
    resolved_start = start or COINBASE_PREMIUM_START
    resolved_end = end or datetime.now(tz=UTC)

    coinbase = _coinbase_daily_closes(resolved_start, resolved_end)
    binance = _binance_daily_closes()
    both = pd.concat([coinbase, binance], axis=1).dropna()
    if both.empty:
        raise ValueError("No overlapping Coinbase/Binance closes for premium calculation")

    both["premium_pct"] = (both["coinbase"] - both["binance"]) / both["binance"] * 100
    return cast(pd.DataFrame, both[["premium_pct"]].sort_index())


def fetch_all(*, use_cache: bool = True, cache_dir: Path | str = DEFAULT_CACHE_DIR) -> pd.DataFrame:
    """Fetch all Phase A sources and return one merged daily DataFrame.

    The merged frame uses the BMP daily index as the spine, then adds:
    `etf_net_flow_m`, `mstr_btc`, and `cb_premium_pct`. Raw source-specific
    shapes remain available through the individual fetch functions.
    """
    cache_path = _cache_path(cache_dir)
    if use_cache and _cache_is_fresh(cache_path):
        return cast(pd.DataFrame, pd.read_pickle(cache_path))

    cache_path.parent.mkdir(parents=True, exist_ok=True)

    bmp = fetch_bmp()
    etf = fetch_etf_flows()
    strategy = fetch_strategy_holdings()
    premium = fetch_coinbase_premium()

    merged = bmp.copy()
    merged["etf_net_flow_m"] = etf["Total"].reindex(merged.index).fillna(0)
    merged["mstr_btc"] = strategy["btc_balance"].reindex(merged.index).ffill()
    merged["cb_premium_pct"] = premium["premium_pct"].reindex(merged.index)
    merged = merged.sort_index()

    merged.to_pickle(cache_path)
    return merged


def summarize_frame(frame: pd.DataFrame) -> str:
    """Return a compact human summary for CLI output."""
    if frame.empty:
        return "rows=0 columns=0 date_range=empty"
    start = str(frame.index.min())[:10]
    end = str(frame.index.max())[:10]
    columns = ", ".join(frame.columns)
    first_line = f"rows={len(frame)} columns={len(frame.columns)} date_range={start}→{end}"
    return f"{first_line}\ncolumns: {columns}"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch raw Bitcoin Demand Index dashboard data.")
    parser.add_argument("--no-cache", action="store_true", help="Force fresh source fetches.")
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=DEFAULT_CACHE_DIR,
        help="Cache directory containing raw_data.pkl.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate entry-point configuration without performing network fetches.",
    )
    args = parser.parse_args(argv)

    validate_secrets()
    if args.dry_run:
        print(f"OK: BMP_API_KEY present; cache_dir={args.cache_dir}")
        return 0

    frame = fetch_all(use_cache=not args.no_cache, cache_dir=args.cache_dir)
    print(summarize_frame(frame))
    print(f"cache: {_cache_path(args.cache_dir)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
