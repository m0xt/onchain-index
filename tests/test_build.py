from __future__ import annotations

import json
import subprocess

import numpy as np
import pandas as pd

from onchain_index.composite import mroi


def _build_sample_frame() -> pd.DataFrame:
    idx = pd.date_range("2012-01-01", periods=5300)
    t = np.arange(len(idx), dtype=float)
    wave = np.sin(t / 45.0)
    slow = np.cos(t / 220.0)
    mstr = np.where(idx < pd.Timestamp("2020-08-10"), np.nan, 100_000 + t * 45 + wave * 500)
    etf = np.where(idx < pd.Timestamp("2024-01-11"), 0.0, np.sin(t / 17.0) * 120)
    return pd.DataFrame(
        {
            "mvrv_zscore": 1.5 + wave + t / 6000,
            "market_cap": 1_000_000_000 + t * 1_000_000,
            "realized_cap": 500_000_000 + t * 500_000,
            "btc_price": 1_000 + np.exp(t / 850) + wave * 150 + t * 5,
            "nupl": 0.4 + wave / 10,
            "lth_mvrv": 1.2 + slow,
            "sth_mvrv": 1.1 + wave + t / 7000,
            "puell_multiple": 1.0 + np.sin(t / 60.0) / 2,
            "hash_30dma": 100 + t / 20 + wave,
            "hash_60dma": 99 + t / 20 + slow,
            "adr_dma30": 900_000 + t * 10 + wave * 1_000,
            "adr_dma365": 850_000 + t * 8 + slow * 900,
            "hodl_1yr_pct": 55 + np.sin(t / 120.0) * 8,
            "reserve_risk": 0.002 + np.sin(t / 80.0) / 10_000,
            "rhodl_ratio": 2_000 + t * 0.5 + np.sin(t / 50.0) * 100,
            "etf_net_flow_m": etf,
            "mstr_btc": mstr,
            "cb_premium_pct": np.sin(t / 30.0) * 0.5,
        },
        index=idx,
    )


def test_build_entrypoint_writes_dashboard_and_status(tmp_path) -> None:
    cache_dir = tmp_path / "cache"
    output_root = tmp_path / "site"
    cache_dir.mkdir()
    frame = _build_sample_frame()
    frame.to_pickle(cache_dir / "raw_data.pkl")

    result = subprocess.run(
        [
            "uv",
            "run",
            "python",
            "-m",
            "onchain_index.build",
            "--cache-dir",
            str(cache_dir),
            "--output-root",
            str(output_root),
        ],
        cwd="/Users/max/projects/onchain-index",
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, result.stderr
    outputs_dashboard = output_root / "outputs" / "dashboard.html"
    status_json = output_root / ".cache" / "status.json"
    assert outputs_dashboard.exists()
    assert outputs_dashboard.stat().st_size > 0

    latest_pi = mroi(frame).dropna().iloc[-1]
    assert f"{latest_pi:+.2f}" in outputs_dashboard.read_text()

    status = json.loads(status_json.read_text())
    assert set(status) == {"last_run_utc", "last_mroi", "last_tier", "last_error"}
    assert isinstance(status["last_run_utc"], str)
    assert isinstance(status["last_mroi"], float)
    assert status["last_tier"] in {"CASH", "STAY LONG"}
    assert status["last_error"] is None


def test_index_page_imports_live_iteration_constants(tmp_path) -> None:
    from onchain_index.backtest import BTC_CYCLES, DEFAULT_ZSCORE_WINDOW
    from onchain_index.build import THEORY_VERSION
    from onchain_index.build_index_page import build_index_page
    from onchain_index.composite import MROI_THRESHOLD, TIER_PCT, VALUATION_CONSTITUENTS
    from onchain_index.data import BMP_BASE, START_DATE

    output_root = tmp_path / "site"
    status_dir = output_root / ".cache"
    status_dir.mkdir(parents=True)
    (status_dir / "status.json").write_text(
        json.dumps(
            {
                "last_run_utc": "2026-05-27T11:36:47Z",
                "last_mroi": 1.23,
                "last_tier": "STAY LONG",
                "last_error": None,
            }
        )
    )

    output = build_index_page(output_root=output_root)
    html = output.read_text()

    assert "onchain-index / iteration surface" in html
    assert f"{DEFAULT_ZSCORE_WINDOW}d" in html
    assert f"MROI &gt; {MROI_THRESHOLD:.1f}" in html
    assert f"{TIER_PCT['STAY LONG']:.0f}%" in html
    assert next(iter(VALUATION_CONSTITUENTS)) in html
    assert next(iter(BTC_CYCLES)) in html
    assert BMP_BASE in html
    assert START_DATE in html
    assert THEORY_VERSION in html
