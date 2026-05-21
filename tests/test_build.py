from __future__ import annotations

import json
import subprocess

import numpy as np
import pandas as pd

from onchain_index.composite import pi_score


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
    docs_index = output_root / "docs" / "index.html"
    outputs_dashboard = output_root / "outputs" / "dashboard.html"
    status_json = output_root / ".cache" / "status.json"
    assert docs_index.exists()
    assert docs_index.stat().st_size > 0
    assert outputs_dashboard.read_text() == docs_index.read_text()

    latest_pi = pi_score(frame).dropna().iloc[-1]
    assert f"{latest_pi:+.2f}" in docs_index.read_text()

    status = json.loads(status_json.read_text())
    assert set(status) == {"last_run_utc", "last_pi_score", "last_tier", "last_error"}
    assert isinstance(status["last_run_utc"], str)
    assert isinstance(status["last_pi_score"], float)
    assert status["last_tier"] in {"CASH", "STAY LONG"}
    assert status["last_error"] is None
