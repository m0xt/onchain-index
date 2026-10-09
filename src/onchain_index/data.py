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

# Legacy Atlas reference. The BMP subscription ended in 2026-09.
BMP_BASE = "https://api.bitcoinmagazinepro.com"
COINMETRICS_COMMUNITY_URL = "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"
COINMETRICS_METRICS = "PriceUSD,CapMrktCurUSD,CapMVRVCur,IssTotUSD,HashRate,AdrActCnt"
BGEOMETRICS_HODL_1Y_URL = "https://api.bitcoin-data.com/v1/hodl-one-year"
FROZEN_HODL_CSV = PROJECT_ROOT / "data" / "hodl_1yr_pct_bmp_frozen.csv"
# Context-only columns with no free full-history source yet; shipped as NaN so the
# Reference Library / Phase B table render "—" instead of failing.
UNSOURCED_CONTEXT_COLUMNS: tuple[str, ...] = ("sth_mvrv", "rhodl_ratio", "lth_mvrv", "reserve_risk")
FARSIDE_ETF_FLOW_URL = "https://farside.co.uk/bitcoin-etf-flow-all-data/"
STRATEGY_TRACKER_MANIFEST_URL = "https://data.strategytracker.com/latest.json"
STRATEGY_TRACKER_BASE = "https://data.strategytracker.com"
COINBASE_CANDLES_URL = "https://api.exchange.coinbase.com/products/BTC-USD/candles"
BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"
BINANCE_VISION_KLINES_URL = "https://data-api.binance.vision/api/v3/klines"
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


def validate_secrets(env_file: Path = OPS_SECRET_ENV) -> str | None:
    """Load optional secrets. No key is required since the BMP subscription ended.

    ``BGEOMETRICS_TOKEN`` is optional: without it the free BGeometrics plan applies
    (10 req/hour, 15/day, last 4 years), which is enough for one daily refresh.
    """
    if env_file.exists():
        load_dotenv(env_file, override=False)
    return os.environ.get("BGEOMETRICS_TOKEN", "").strip() or None


def _series(frame: pd.DataFrame, column: str) -> pd.Series:
    """Return one DataFrame column as a Series for pandas/pyright interop."""
    return cast(pd.Series, frame[column])


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
    """Fetch on-chain indicators from Bitcoin Magazine Pro.

    Production refresh no longer calls this. ``fetch_all`` uses Coin Metrics
    and BGeometrics. Calling it still requires ``BMP_API_KEY``.
    """
    resolved_api_key = (api_key or os.environ.get("BMP_API_KEY", "")).strip()
    if not resolved_api_key:
        raise RuntimeError(
            "BMP_API_KEY is not set. Production data no longer uses Bitcoin Magazine Pro; "
            "call fetch_all() instead."
        )
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


def _fetch_text(url: str, *, timeout: int = 30) -> str:
    """GET text, using a browser TLS impersonation if Cloudflare returns 403."""
    response = requests.get(url, headers=UA_HEADERS, timeout=timeout)
    if response.status_code != 403:
        response.raise_for_status()
        return response.text
    try:
        from curl_cffi import requests as curl_requests
    except ImportError as exc:  # pragma: no cover - declared dependency
        raise RuntimeError("Farside returned 403 and curl_cffi is not installed.") from exc
    impersonated = curl_requests.get(url, impersonate="chrome", timeout=timeout)
    impersonated.raise_for_status()
    text = impersonated.text
    if not isinstance(text, str):
        raise ValueError(f"Unexpected text response from {url}")
    return text


def fetch_etf_flows() -> pd.DataFrame:
    """Fetch Farside daily spot BTC ETF flows in $M."""
    html = _fetch_text(FARSIDE_ETF_FLOW_URL, timeout=60)
    tables = pd.read_html(io.StringIO(html))
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
    params = {"symbol": "BTCUSDT", "interval": "1d", "limit": 1000}
    response = requests.get(BINANCE_KLINES_URL, params=params, timeout=30)
    # api.binance.com returns 451 from some regions. The public market-data
    # host serves the same klines.
    if response.status_code == 451:
        response = requests.get(BINANCE_VISION_KLINES_URL, params=params, timeout=30)
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


def fetch_coinmetrics(start_date: str = START_DATE) -> pd.DataFrame:
    """Daily BTC price/market metrics from Coin Metrics Community (no key; CC BY-NC 4.0).

    Also derives the context metrics that BMP used to serve:
    MVRV-Z = (market cap - realized cap) / expanding std(market cap);
    Puell = daily issuance USD / its 365d mean; NUPL = 1 - realized/market cap.
    """
    rows: list[dict[str, object]] = []
    url: str | None = COINMETRICS_COMMUNITY_URL
    params: dict[str, str | int] | None = {
        "assets": "btc",
        "metrics": COINMETRICS_METRICS,
        "frequency": "1d",
        "start_time": start_date,
        "page_size": 10000,
    }
    while url:
        response = requests.get(url, params=params, timeout=60)
        response.raise_for_status()
        payload = response.json()
        rows.extend(payload["data"])
        next_url = payload.get("next_page_url")
        url = next_url if isinstance(next_url, str) and next_url else None
        params = None
    raw = pd.DataFrame(rows)
    raw.index = pd.to_datetime(raw["time"], utc=True).dt.tz_convert(None).dt.normalize()
    raw.index.name = "date"
    raw = raw[~raw.index.duplicated(keep="last")]
    numeric = raw.drop(columns=["asset", "time"]).apply(pd.to_numeric, errors="coerce")
    num = cast(pd.DataFrame, numeric)
    market_cap = _series(num, "CapMrktCurUSD")
    realized_cap = cast(pd.Series, market_cap / _series(num, "CapMVRVCur"))
    issuance = _series(num, "IssTotUSD")
    hashrate = _series(num, "HashRate")
    addresses = _series(num, "AdrActCnt")
    out = pd.DataFrame(index=num.index)
    out["btc_price"] = _series(num, "PriceUSD")
    out["market_cap"] = market_cap
    out["realized_cap"] = realized_cap
    out["mvrv_zscore"] = (market_cap - realized_cap) / market_cap.expanding().std()
    out["nupl"] = 1 - realized_cap / market_cap
    out["puell_multiple"] = issuance / issuance.rolling(365).mean()
    out["hash_30dma"] = hashrate.rolling(30).mean()
    out["hash_60dma"] = hashrate.rolling(60).mean()
    out["adr_dma30"] = addresses.rolling(30).mean()
    out["adr_dma365"] = addresses.rolling(365).mean()
    return out.sort_index()


def fetch_hodl_1y(*, token: str | None = None, frozen_csv: Path = FROZEN_HODL_CSV) -> pd.Series:
    """1Y+ HODL share (%): frozen BMP history + BGeometrics /v1/hodl-one-year after it.

    BGeometrics is level-shifted to the frozen BMP value on the splice date so the
    30d change (the only thing the on-chain cohort uses) has no artificial jump.
    """
    frozen = cast(
        pd.Series,
        pd.read_csv(frozen_csv, index_col=0, parse_dates=True)["hodl_1yr_pct"].dropna(),
    )
    frozen_times = pd.Series(pd.to_datetime(frozen.index, utc=True))
    frozen.index = frozen_times.dt.tz_convert(None).dt.normalize()
    splice = cast(pd.Timestamp, frozen.index.max())
    splice_start = (splice - timedelta(days=30)).strftime("%Y-%m-%d")
    params: dict[str, str] = {"startday": splice_start, "size": "2000"}
    if token:
        params["token"] = token
    response = requests.get(BGEOMETRICS_HODL_1Y_URL, params=params, headers=UA_HEADERS, timeout=60)
    response.raise_for_status()
    bg = pd.DataFrame(response.json())
    live_index = pd.to_datetime(bg["d"], utc=True).dt.tz_convert(None).dt.normalize()
    hodl_fraction = cast(pd.Series, pd.to_numeric(bg["hodlOneYear"], errors="coerce"))
    live = pd.Series(hodl_fraction.to_numpy() * 100, index=live_index)
    live = cast(pd.Series, live.loc[~live.index.duplicated(keep="last")]).dropna()
    if splice not in live.index:
        raise ValueError(f"BGeometrics hodl-one-year has no value on splice date {splice:%Y-%m-%d}")
    offset = float(frozen.loc[splice] - live.loc[splice])
    live_tail = cast(pd.Series, live[live.index > splice]) + offset
    spliced = cast(pd.Series, pd.concat([frozen, live_tail]).sort_index())
    spliced.name = "hodl_1yr_pct"
    return spliced


def fetch_all(*, use_cache: bool = True, cache_dir: Path | str = DEFAULT_CACHE_DIR) -> pd.DataFrame:
    """Fetch all sources and return one merged daily DataFrame (no BMP).

    Spine: Coin Metrics Community daily index. Adds the spliced 1Y+ HODL share,
    `etf_net_flow_m`, `mstr_btc`, `cb_premium_pct`, and NaN placeholders for
    context-only metrics that have no free full-history source yet.
    """
    cache_path = _cache_path(cache_dir)
    if use_cache and _cache_is_fresh(cache_path):
        return cast(pd.DataFrame, pd.read_pickle(cache_path))

    cache_path.parent.mkdir(parents=True, exist_ok=True)

    token = validate_secrets()
    market = fetch_coinmetrics()
    hodl = fetch_hodl_1y(token=token)
    etf = fetch_etf_flows()
    strategy = fetch_strategy_holdings()
    premium = fetch_coinbase_premium()

    market_end = cast(pd.Timestamp, market.index.max())
    hodl_end = cast(pd.Timestamp, hodl.index.max())
    merged = market.loc[: min(market_end, hodl_end)].copy()
    merged["hodl_1yr_pct"] = hodl.reindex(merged.index).ffill()
    for column in UNSOURCED_CONTEXT_COLUMNS:
        merged[column] = np.nan
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

    token = validate_secrets()
    if args.dry_run:
        token_state = "set" if token else "not set (free plan)"
        print(
            f"OK: no required secrets; BGeometrics token {token_state}; cache_dir={args.cache_dir}"
        )
        return 0

    frame = fetch_all(use_cache=not args.no_cache, cache_dir=args.cache_dir)
    print(summarize_frame(frame))
    print(f"cache: {_cache_path(args.cache_dir)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
