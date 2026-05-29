from __future__ import annotations

import json
import os
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
    brief_dir = output_root / "briefs" / "2026-05-29"
    brief_dir.mkdir(parents=True)
    (brief_dir / "onchain.md").write_text(
        "MROI is LONG because holder behavior is positive and ETF flows improved.\n"
    )

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
        env={**os.environ, "ONCHAIN_INDEX_SKIP_BRIEF_REFRESH": "1"},
    )

    assert result.returncode == 0, result.stderr
    outputs_dashboard = output_root / "outputs" / "dashboard.html"
    docs_dashboard = output_root / "docs" / "dashboard.html"
    status_json = output_root / ".cache" / "status.json"
    assert outputs_dashboard.exists()
    assert outputs_dashboard.stat().st_size > 0
    assert docs_dashboard.read_bytes() == outputs_dashboard.read_bytes()

    latest_pi = mroi(frame).dropna().iloc[-1]
    html = outputs_dashboard.read_text()
    assert f"{latest_pi:+.2f}" in html
    assert "HOLDER CONVICTION COHORTS" in html
    assert "Input / Group / Current z / 7d zΔ / 30d zΔ" in html
    assert "Reference Library" in html
    assert "Supplementary context indicators — not part of the decision rule" in html
    assert "This week’s read · on-chain index" in html
    assert "MROI is LONG because holder behavior is positive" in html
    assert "Valuation is context only" not in html

    status = json.loads(status_json.read_text())
    assert set(status) == {"last_run_utc", "last_mroi", "last_tier", "last_error"}
    assert isinstance(status["last_run_utc"], str)
    assert isinstance(status["last_mroi"], float)
    assert status["last_tier"] in {"CASH", "LONG"}
    assert status["last_error"] is None


def test_latest_brief_missing_is_none(tmp_path) -> None:
    from onchain_index.brief import load_latest_brief

    assert load_latest_brief(briefs_dir=tmp_path / "briefs") is None


def test_brief_context_excludes_valuation_lens() -> None:
    from onchain_index.brief import BriefContext, _context_text

    text = _context_text(
        BriefContext(
            date="2026-05-29",
            posture="CASH",
            allocation_pct=0.0,
            mroi=-0.69,
            mroi_7d_change=-0.29,
            valuation=-1.01,
            valuation_7d_change=-0.29,
            holder_behavior=-0.69,
            holder_behavior_7d_change=-0.29,
            signal_zone="CASH zone",
            long_threshold=0.0,
            cash_threshold=-0.3,
            valuation_constituents={"MVRV-Z": -1.4},
            holder_cohorts={"ETF flows": -1.13},
        )
    )

    assert "Holder Behavior" in text
    assert "ETF flows" in text
    assert "Valuation" not in text
    assert "MVRV-Z" not in text


def test_latest_brief_loads_cached_markdown(tmp_path) -> None:
    from onchain_index.brief import load_latest_brief

    brief_dir = tmp_path / "briefs" / "2026-05-29"
    brief_dir.mkdir(parents=True)
    (brief_dir / "onchain.md").write_text(
        "**LONG** while [holder behavior](https://example.com) is firm.\n"
    )

    brief = load_latest_brief(context_date="2026-05-30", briefs_dir=tmp_path / "briefs")

    assert brief is not None
    assert brief.date == "2026-05-29"
    assert brief.stale is True
    assert "<strong>LONG</strong>" in brief.html
    assert 'href="https://example.com"' in brief.html


def test_index_page_imports_live_iteration_constants(tmp_path) -> None:
    from onchain_index.backtest import BTC_CYCLES, DEFAULT_ZSCORE_WINDOW
    from onchain_index.build import THEORY_VERSION
    from onchain_index.build_index_page import build_index_page
    from onchain_index.composite import (
        MROI_CASH_THRESHOLD,
        MROI_LONG_THRESHOLD,
        TIER_PCT,
        VALUATION_CONSTITUENTS,
    )
    from onchain_index.cost import COST_ESTIMATES, MODEL_PRICES_USD_PER_MTOK
    from onchain_index.data import BMP_BASE, START_DATE

    output_root = tmp_path / "site"
    status_dir = output_root / ".cache"
    status_dir.mkdir(parents=True)
    (status_dir / "status.json").write_text(
        json.dumps(
            {
                "last_run_utc": "2026-05-27T11:36:47Z",
                "last_mroi": 1.23,
                "last_tier": "LONG",
                "last_error": None,
            }
        )
    )

    output = build_index_page(output_root=output_root)
    html = output.read_text()

    assert "onchain-index / atlas" in html
    assert 'href="dashboard.html"' in html
    assert "Open shareable full dashboard" in html
    assert f"{DEFAULT_ZSCORE_WINDOW}d" in html
    assert f"MROI &gt; {MROI_LONG_THRESHOLD:.1f}" in html
    assert f"MROI &lt; {MROI_CASH_THRESHOLD:.1f}" in html
    assert f"{TIER_PCT['LONG']:.0f}%" in html
    assert next(iter(VALUATION_CONSTITUENTS)) in html
    assert next(iter(BTC_CYCLES)) in html
    assert BMP_BASE in html
    assert START_DATE in html
    assert THEORY_VERSION in html
    assert "Estimated weekly Claude spend" in html
    assert "Generated brief" in html
    assert "briefs/YYYY-MM-DD/onchain.md" in html
    assert "onchain_index.brief.generate_brief" in html
    assert "cost.py" in html
    assert len(COST_ESTIMATES) == 1
    assert COST_ESTIMATES[0]["site"] == "onchain_index.brief.generate_brief"
    assert MODEL_PRICES_USD_PER_MTOK["claude-haiku-4-5-20251001"] == (0.80, 4.00)
