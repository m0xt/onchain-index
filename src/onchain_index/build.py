"""Build the onchain-index decision dashboard and iteration surface."""

# ruff: noqa: E501

from __future__ import annotations

import argparse
import json
import math
import subprocess
import webbrowser
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import Any, cast

import pandas as pd

from onchain_index.backtest import (
    BTC_CYCLES,
    PHASE_B_INDICATORS,
    backtest_signal,
    backtest_tiered_signal,
    build_phase_b_indicator_signals,
    walk_forward_tiered_by_cycle,
)
from onchain_index.composite import (
    MROI_CASH_THRESHOLD,
    MROI_LONG_THRESHOLD,
    TIER_PCT,
    epoch_for_date,
    holder_behavior_cohorts,
    holder_behavior_composite,
    mroi,
    sizing_tier,
    valuation_composite,
    valuation_constituents,
)
from onchain_index.data import DEFAULT_CACHE_DIR, PROJECT_ROOT, fetch_all

GITHUB_EDIT_BASE = "https://github.com/m0xt/onchain-index/edit/main"
PROJECT_REPO_URL = "https://github.com/m0xt/onchain-index"
THEORY_VERSION = "v0.7"

INDICATOR_DECISIONS: dict[str, tuple[str, str, str]] = {
    "STH MVRV": ("Valuation", "In", "Best cycle-robust valuation survivor; 4/4 cycles positive."),
    "RHODL Ratio": ("Valuation", "In", "Age-band realized-value valuation oscillator; 4/4 cycles positive."),
    "Puell Multiple": ("Valuation", "In", "Miner-revenue valuation lens; modest standalone, diversifying."),
    "MVRV-Z": ("Valuation", "In", "Canonical realized-cap deviation metric; chosen over NUPL."),
    "NUPL": ("Valuation", "Out / alternate", "Excluded because MVRV-Z/NUPL were highly colinear."),
    "LTH MVRV": ("Holder Behavior / on-chain", "Out", "Both tested signs were negative full-sample."),
    "HODL 1Y+": ("Holder Behavior / on-chain", "Out level rule", "Level rule failed; 30d-change inverted z is the included transform."),
    "Address Growth": ("Adoption / holder-ish", "Out", "Closer to adoption and negative under both tested signs."),
    "Reserve Risk": ("Holder / valuation hybrid", "Out", "Standalone rule failed; sign convention remains contested."),
    "Hash Ribbon": ("Out", "Out", "Miner-derived and not cleanly in the locked two-dimension theory."),
    "ETF Net Flow": ("Holder Behavior / institutional ETF", "In", "Cleanest post-2024 marginal-holder flow input."),
    "MSTR Holdings Δ": ("Holder Behavior / corporate DAT", "In as cohort", "Weak standalone but structurally part of holder behavior."),
    "Coinbase Premium": ("Uncertain", "Out", "Not a valid exchange-flow substitute; behaved like microstructure sentiment."),
}

COHORT_LABELS: dict[str, str] = {
    "on_chain": "On-chain holders",
    "corporate_dat": "Corporate DAT",
    "institutional_etf": "Institutional ETF",
}

COHORT_CONCENTRATION_THRESHOLD = 0.50

VALUATION_LABELS: dict[str, str] = {
    "sth_mvrv": "STH MVRV",
    "rhodl_ratio": "RHODL Ratio",
    "puell_multiple": "Puell Multiple",
    "mvrv_zscore": "MVRV-Z",
}

TIER_COLORS: dict[str, str] = {
    "LONG": "#4CAF50",
    "CASH": "#E84B5A",
}

TIER_LABELS: dict[str, str] = {
    "LONG": "LONG",
    "CASH": "CASH",
}

TIER_SUBTITLES: dict[str, str] = {
    "LONG": "100% long · P4 state machine is LONG.",
    "CASH": "0% long · P4 state machine is CASH.",
}


@dataclass(frozen=True)
class DashboardPaths:
    """Output paths for one dashboard build."""

    root: Path
    docs_index: Path
    outputs_dashboard: Path
    status_json: Path


@dataclass(frozen=True)
class LatestScores:
    """Current headline and decomposition values."""

    date: pd.Timestamp
    pi: float
    tier: str
    allocation_pct: float
    btc_price: float
    valuation: float
    holder_behavior: float
    valuation_constituents: dict[str, float | None]
    holder_cohorts: dict[str, float | None]
    epoch: str


def _paths(output_root: Path = PROJECT_ROOT) -> DashboardPaths:
    return DashboardPaths(
        root=output_root,
        docs_index=output_root / "docs" / "index.html",
        outputs_dashboard=output_root / "outputs" / "dashboard.html",
        status_json=output_root / ".cache" / "status.json",
    )


def _format_score(value: float | None, digits: int = 2, *, signed: bool = True) -> str:
    if value is None or not math.isfinite(value):
        return "N/A"
    prefix = "+" if signed and value >= 0 else ""
    return f"{prefix}{value:.{digits}f}"


def _format_pct(value: float | None, digits: int = 1, *, signed: bool = True) -> str:
    if value is None or not math.isfinite(value):
        return "—"
    prefix = "+" if signed and value >= 0 else ""
    return f"{prefix}{value:.{digits}f}%"


def _json_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        number = float(cast(Any, value))
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _latest_valid_index(score: pd.Series) -> pd.Timestamp:
    valid = score.dropna()
    if valid.empty:
        raise ValueError("MROI has no non-NaN observations")
    return cast(pd.Timestamp, valid.index[-1])


def _score_color(value: float | None) -> str:
    if value is None or not math.isfinite(value):
        return "#6b7280"
    if value >= 1.0:
        return "#166534"
    if value >= 0.0:
        return "#2563eb"
    if value > -1.0:
        return "#92400e"
    return "#991b1b"


def _mroi_signal_zone(value: float | None) -> str:
    if value is None or not math.isfinite(value):
        return "WARMING"
    if value > MROI_LONG_THRESHOLD:
        return "LONG signal"
    if value < MROI_CASH_THRESHOLD:
        return "CASH signal"
    return "HOLD band"


def _mroi_signal_color(value: float | None) -> str:
    if value is None or not math.isfinite(value):
        return "#6b7280"
    if value > MROI_LONG_THRESHOLD:
        return "#4CAF50"
    if value < MROI_CASH_THRESHOLD:
        return "#E84B5A"
    return "#D89B2B"


def _mroi_signal_subtitle(value: float | None, tier: str) -> str:
    zone = _mroi_signal_zone(value)
    if zone == "HOLD band":
        return f"MROI is in the HOLD band; posture remains {tier}."
    return f"Raw holder MROI is a {zone}; posture is {tier}."


def _git_text(args: list[str], fallback: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return fallback
    text = result.stdout.strip()
    return text or fallback


def _latest_git_summary() -> tuple[str, str]:
    sha = _git_text(["rev-parse", "--short", "HEAD"], "unknown")
    message = _git_text(["log", "-1", "--pretty=%s"], "unknown")
    return sha, message


def _status_label(latest_date: pd.Timestamp, generated_at: datetime) -> tuple[str, str]:
    age_days = (generated_at.date() - latest_date.date()).days
    if age_days <= 3:
        return "OK", "green"
    if age_days <= 7:
        return "STALE", "yellow"
    return "STALE", "red"


def _last_row_values(frame: pd.DataFrame, date: pd.Timestamp) -> dict[str, float | None]:
    row = frame.loc[date]
    return {str(column): _json_float(value) for column, value in row.items()}


def _latest_scores(data: pd.DataFrame) -> tuple[LatestScores, pd.DataFrame, pd.Series, pd.Series]:
    valuation_parts = valuation_constituents(data)
    valuation = valuation_composite(data)
    cohorts = pd.DataFrame(holder_behavior_cohorts(data), index=data.index)
    holder = holder_behavior_composite(data)
    score = mroi(data)
    tiers = sizing_tier(score)
    latest_date = _latest_valid_index(score)
    tier = str(tiers.astype("object").loc[latest_date])
    latest = LatestScores(
        date=latest_date,
        pi=float(score.loc[latest_date]),
        tier=tier,
        allocation_pct=float(TIER_PCT[tier]),
        btc_price=float(data.loc[latest_date, "btc_price"]),
        valuation=float(valuation.loc[latest_date]),
        holder_behavior=float(holder.loc[latest_date]),
        valuation_constituents=_last_row_values(valuation_parts, latest_date),
        holder_cohorts=_last_row_values(cohorts, latest_date),
        epoch=epoch_for_date(latest_date),
    )
    components = pd.concat(
        {
            "mroi": score,
            "valuation": valuation,
            "holder_behavior": holder,
            **{f"valuation_{name}": series for name, series in valuation_parts.items()},
            **{f"cohort_{name}": series for name, series in cohorts.items()},
        },
        axis=1,
    )
    return latest, components, score, tiers


def _historical_points(data: pd.DataFrame, components: pd.DataFrame) -> list[dict[str, float | str | None]]:
    joined = pd.DataFrame(
        {
            "btc_price": data["btc_price"],
            **{column: components[column] for column in components.columns},
        },
        index=data.index,
    ).dropna(subset=["mroi", "btc_price"])
    points: list[dict[str, float | str | None]] = []
    for index, row in joined.iterrows():
        point: dict[str, float | str | None] = {
            "date": str(index)[:10],
            "pi": _json_float(row["mroi"]),
            "price": _json_float(row["btc_price"]),
            "valuation": _json_float(row["valuation"]),
            "holder": _json_float(row["holder_behavior"]),
        }
        for name in VALUATION_LABELS:
            point[f"valuation_{name}"] = _json_float(row[f"valuation_{name}"])
        for name in COHORT_LABELS:
            point[f"holder_{name}"] = _json_float(row[f"cohort_{name}"])
        points.append(point)
    return points


def _walk_forward_rows(tiers: pd.Series, data: pd.DataFrame) -> list[dict[str, str | float | None]]:
    ret = cast(pd.Series, data["btc_price"].pct_change())
    rows: list[dict[str, str | float | None]] = []
    full = backtest_tiered_signal(tiers, ret, TIER_PCT)
    if full is not None:
        rows.append({"window": "Full sample", **full})
    for window, metrics in walk_forward_tiered_by_cycle(tiers, ret, TIER_PCT, BTC_CYCLES).items():
        if metrics is not None:
            rows.append({"window": window, **metrics})
    return rows


def _indicator_rows(data: pd.DataFrame) -> list[dict[str, str | float | None]]:
    ret = cast(pd.Series, data["btc_price"].pct_change())
    signals = build_phase_b_indicator_signals(data)
    rows: list[dict[str, str | float | None]] = []
    for spec in PHASE_B_INDICATORS:
        dimension, decision, note = INDICATOR_DECISIONS[spec.name]
        metrics = backtest_signal(signals[spec.name], ret)
        rows.append(
            {
                "indicator": spec.name,
                "rule": spec.rule,
                "dimension": dimension,
                "decision": decision,
                "alpha": metrics["alpha"] if metrics is not None else None,
                "note": note,
            }
        )
    return rows


def _availability(series: pd.Series) -> str:
    valid = series.dropna()
    if valid.empty:
        return "pending source"
    return f"{str(valid.index[0])[:10]} → {str(valid.index[-1])[:10]}"


def _cohort_constituents(latest: LatestScores) -> dict[str, tuple[tuple[str, float | None], ...]]:
    """Return current constituent-level drivers for each holder cohort."""
    return {
        "on_chain": (("HODL 1Y+ 30d-change", latest.holder_cohorts["on_chain"]),),
        "corporate_dat": (("MSTR / Strategy", latest.holder_cohorts["corporate_dat"]),),
        "institutional_etf": (("Farside spot ETF complex", latest.holder_cohorts["institutional_etf"]),),
    }


def _concentration_disclosure(items: tuple[tuple[str, float | None], ...]) -> tuple[str, float | None]:
    finite = [(label, float(value)) for label, value in items if value is not None and math.isfinite(value)]
    if not finite:
        return "Constituent concentration unavailable while the cohort warms up.", None
    total_abs = sum(abs(value) for _, value in finite)
    if total_abs == 0:
        return "No non-zero constituent contribution in the latest cohort score.", 0.0
    leader, leader_value = max(finite, key=lambda item: abs(item[1]))
    share = abs(leader_value) / total_abs
    return f"{leader}: {share * 100:.0f}% of cohort", share


def _state_label(value: float | None) -> str:
    if value is None or not math.isfinite(value):
        return "WARMING"
    if value >= 1.0:
        return "STRONG"
    if value >= 0.0:
        return "POSITIVE"
    if value > -1.0:
        return "SOFT"
    return "WEAK"


def _state_color(value: float | None) -> str:
    return _score_color(value)


def _make_pi_scale_bar(pi_value: float, tier_color: str) -> str:
    """Horizontal CASH/HOLD/LONG bar for the P4 asymmetric MROI rule."""
    scale_min, scale_max = -2.0, 2.0
    clamped = max(scale_min, min(scale_max, pi_value))
    pct = (clamped - scale_min) / (scale_max - scale_min) * 100
    cash_pct = (MROI_CASH_THRESHOLD - scale_min) / (scale_max - scale_min) * 100
    long_pct = (MROI_LONG_THRESHOLD - scale_min) / (scale_max - scale_min) * 100
    hold_width = long_pct - cash_pct
    return f'''
      <div class="scale-bar" aria-label="P4 MROI tier position">
        <div class="scale-track">
          <div class="scale-zone scale-zone-cash" style="width:{cash_pct:.2f}%;"></div>
          <div class="scale-zone scale-zone-hold" style="width:{hold_width:.2f}%;"></div>
          <div class="scale-zone scale-zone-long" style="width:{100 - long_pct:.2f}%;"></div>
          <div class="scale-threshold" style="left: {cash_pct:.2f}%;"></div>
          <div class="scale-zero" style="left: {long_pct:.2f}%;"></div>
          <div class="scale-marker" style="left: {pct:.2f}%; background: {tier_color}; box-shadow: 0 0 0 4px {tier_color}33;"></div>
        </div>
        <div class="scale-axis">
          <span style="left:0%;">−2</span>
          <span style="left:{cash_pct:.2f}%; color:#888;">−0.3</span>
          <span style="left:{long_pct:.2f}%; color:#888;">0</span>
          <span style="left:100%;">+2</span>
        </div>
        <div class="scale-legend">
          <span class="scale-cash-label">CASH signal</span>
          <span class="scale-hold-label">HOLD band</span>
          <span class="scale-long-label">LONG signal</span>
        </div>
      </div>'''


def _cohort_cards(components: pd.DataFrame, latest: LatestScores) -> str:
    specs = (
        ("on_chain", "HODL 1Y+ 30d-change inverted z", "on-chain holder acceleration"),
        ("corporate_dat", "MSTR 30d holdings change z", "corporate treasury accumulation"),
        ("institutional_etf", "Rolling 30d ETF net-flow z", "institutional fund flows"),
    )
    constituent_map = _cohort_constituents(latest)
    cards: list[str] = []
    for key, constituents, description in specs:
        value = latest.holder_cohorts[key]
        label = COHORT_LABELS[key]
        availability = _availability(cast(pd.Series, components[f"cohort_{key}"]))
        tag = "active" if value is not None else "warming up"
        disclosure, share = _concentration_disclosure(constituent_map[key])
        if key == "corporate_dat":
            disclosure = "MSTR / Strategy: 100% of cohort"
            share = 1.0
        concentrated = share is not None and share >= COHORT_CONCENTRATION_THRESHOLD
        cards.append(
            f'''
            <article class="sub-card">
              <div class="sub-card-top">
                <div>
                  <div class="sub-eyebrow">{escape(description)}</div>
                  <h3>{escape(label)}</h3>
                </div>
                <span class="mini-chip {'warn' if concentrated else ''}">{escape(tag)}</span>
              </div>
              <div class="sub-score mono" style="color:{_state_color(value)}">{_format_score(value)}</div>
              <div class="sub-state" style="color:{_state_color(value)}">{escape(_state_label(value))}</div>
              <dl class="sub-meta">
                <dt>Constituent</dt><dd>{escape(constituents)}</dd>
                <dt>Coverage</dt><dd>{escape(availability)}</dd>
                <dt>Disclosure</dt><dd class="{'hot' if concentrated else ''}">{escape(disclosure)}</dd>
              </dl>
            </article>
            '''
        )
    return "\n".join(cards)

def _dimension_card(title: str, value: float, items: dict[str, float | None], summary: str) -> str:
    rows = "".join(
        f"<li><span>{escape(label)}</span><strong class=\"mono\">{_format_score(score)}</strong></li>"
        for label, score in items.items()
    )
    return f'''
    <article class="pillar-card">
      <div class="pillar-card-head">
        <span class="pillar-name">{escape(title)}</span>
        <span class="pillar-state" style="color:{_state_color(value)}">{escape(_state_label(value))}</span>
      </div>
      <div class="pillar-score mono" style="color:{_state_color(value)}">{_format_score(value)}</div>
      <p>{escape(summary)}</p>
      <ul class="metric-list">{rows}</ul>
    </article>
    '''

def _walk_forward_table(rows: list[dict[str, str | float | None]]) -> str:
    body = "".join(
        "<tr>"
        f"<td>{escape(str(row['window']))}</td>"
        f"<td class=\"mono\">{_format_pct(_json_float(row.get('bh_ann')))}</td>"
        f"<td class=\"mono\">{_format_pct(_json_float(row.get('strat_ann')))}</td>"
        f"<td class=\"mono val {'pos' if (_json_float(row.get('alpha')) or 0) >= 0 else 'neg'}\">{_format_pct(_json_float(row.get('alpha')))}</td>"
        f"<td class=\"mono\">{_format_pct(_json_float(row.get('bh_dd')))}</td>"
        f"<td class=\"mono\">{_format_pct(_json_float(row.get('strat_dd')))}</td>"
        "</tr>"
        for row in rows
    )
    return f'''
    <table>
      <thead><tr><th>Window</th><th>BTC B&amp;H</th><th>MROI tier</th><th>Alpha</th><th>BTC DD</th><th>MROI DD</th></tr></thead>
      <tbody>{body}</tbody>
    </table>
    '''

def _indicator_table(rows: list[dict[str, str | float | None]]) -> str:
    body = "".join(
        "<tr>"
        f"<td><span class=\"ind-name\">{escape(str(row['indicator']))}</span><div class=\"muted small\">{escape(str(row['rule']))}</div></td>"
        f"<td>{escape(str(row['decision']))}</td>"
        f"<td>{escape(str(row['dimension']))}</td>"
        f"<td class=\"mono\">{_format_pct(_json_float(row.get('alpha')))}</td>"
        f"<td class=\"muted\">{escape(str(row['note']))}</td>"
        "</tr>"
        for row in rows
    )
    return f'''
    <table>
      <thead><tr><th>Indicator</th><th>Decision</th><th>Composite</th><th>Phase B alpha</th><th>Note</th></tr></thead>
      <tbody>{body}</tbody>
    </table>
    '''

def _edit_link(path: str, label: str = "Suggest edit") -> str:
    return f'<a class="suggest" href="{GITHUB_EDIT_BASE}/{escape(path)}" target="_blank" rel="noreferrer">{escape(label)} ↗</a>'


def _render_html(
    *,
    latest: LatestScores,
    components: pd.DataFrame,
    historical: list[dict[str, float | str | None]],
    walk_forward_rows: list[dict[str, str | float | None]],
    indicator_rows: list[dict[str, str | float | None]],
    generated_at: datetime,
) -> str:
    sha, message = _latest_git_summary()
    status_label, status_class = _status_label(latest.date, generated_at)
    tier_color = TIER_COLORS[latest.tier]
    tier_label = TIER_LABELS[latest.tier]
    tier_subtitle = TIER_SUBTITLES[latest.tier]
    signal_zone = _mroi_signal_zone(latest.pi)
    signal_color = _mroi_signal_color(latest.pi)
    signal_subtitle = _mroi_signal_subtitle(latest.pi, tier_label)
    chart_json = json.dumps(historical, separators=(",", ":"))
    scale_html = _make_pi_scale_bar(latest.pi, tier_color)
    info_svg = '<svg width="14" height="14" viewBox="0 0 14 14" fill="none"><circle cx="7" cy="7" r="6" stroke="currentColor" stroke-width="1.2"/><circle cx="7" cy="4" r="0.9" fill="currentColor"/><line x1="7" y1="6.5" x2="7" y2="10.5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Milk Road on-chain index · {latest.date.strftime('%Y-%m-%d')}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-annotation@3.0.1/dist/chartjs-plugin-annotation.min.js"></script>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', system-ui, sans-serif;
    background: #0a0a0a; color: #ccc;
    padding: 24px 32px 48px; max-width: 1280px; margin: 0 auto;
  }}
  a {{ color: #cdaa6a; text-decoration: none; border-bottom: 1px dotted #6c5a36; }}
  a:hover {{ color: #e6c98a; border-bottom-color: #cdaa6a; }}
  .mono {{ font-family: 'SF Mono', Menlo, monospace; }}
  .muted {{ color: #666; }}
  .small {{ font-size: 13px; }}
  .val.pos {{ color: #4CAF50; }}
  .val.neg {{ color: #E84B5A; }}

  .meta-bar {{
    display: flex; justify-content: space-between; align-items: baseline;
    margin-bottom: 18px; font-size: 13px; color: #555;
  }}
  .meta-bar .brand {{ color: #888; font-weight: 600; letter-spacing: 0.5px; }}
  .meta-bar .meta-right {{ display:flex; gap: 14px; align-items: baseline; flex-wrap: wrap; justify-content: flex-end; }}
  .status-dot {{ display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:7px; }}
  .status-dot.green {{ background:#4CAF50; }}
  .status-dot.yellow {{ background:#FF9800; }}
  .status-dot.red {{ background:#E84B5A; }}

  .hero {{ margin-bottom: 36px; padding: 8px 4px 0; }}
  .hero-eyebrow {{
    font-size: 11px; text-transform: uppercase; letter-spacing: 2px;
    color: #555; font-weight: 500; margin-bottom: 18px;
  }}
  .hero-grid {{
    display: grid; grid-template-columns: minmax(0, 1fr) auto;
    gap: 48px; align-items: start;
  }}
  .hero-main {{ min-width: 0; }}
  .hero-row {{ display:flex; align-items: baseline; gap:28px; margin-bottom: 24px; }}
  .hero-value {{ font-size: 80px; font-weight: 600; line-height: 1; letter-spacing: -3px; }}
  .hero-action-label {{ font-size: 22px; font-weight: 600; letter-spacing: -0.4px; line-height: 1.1; }}
  .hero-action-sub {{ font-size: 13px; color: #777; margin-top: 4px; }}
  .hero-story {{ margin: 22px 0 0; color: #999; font-size: 14px; line-height: 1.55; max-width: 820px; }}

  .hero-pillars {{ border-left: 1px solid #1f1f1f; padding: 4px 0 4px 32px; min-width: 285px; }}
  .hero-pillars-title {{ font-size: 10px; text-transform: uppercase; letter-spacing: 1.8px; color: #555; font-weight: 500; margin-bottom: 14px; }}
  .hero-pillar {{ display: flex; align-items: baseline; justify-content: space-between; gap: 16px; padding: 10px 0; }}
  .hero-pillar + .hero-pillar {{ border-top: 1px solid #161616; }}
  .hero-pillar-name {{ font-size: 13px; color: #aaa; }}
  .hero-pillar-right {{ display: flex; align-items: baseline; gap: 10px; }}
  .hero-pillar-state {{ font-size: 13px; font-weight: 600; letter-spacing: 0.4px; }}
  .hero-pillar-value {{ font-size: 13px; color: #777; }}
  .hero-pillar-note {{ margin-top: 14px; font-size: 11px; color: #555; line-height: 1.5; }}

  .scale-bar {{ max-width: 720px; margin-top: 4px; }}
  .scale-track {{ position: relative; height: 8px; border-radius: 4px; background: #1a1a1a; display: flex; overflow: visible; }}
  .scale-zone {{ height: 100%; }}
  .scale-zone:first-child {{ border-radius: 4px 0 0 4px; }}
  .scale-zone:nth-child(3) {{ border-radius: 0 4px 4px 0; }}
  .scale-zone-cash {{ background: linear-gradient(to right, #E84B5A28, #E84B5A16); }}
  .scale-zone-hold {{ background: linear-gradient(to right, #D89B2B22, #D89B2B14); }}
  .scale-zone-long {{ background: linear-gradient(to right, #4CAF5016, #4CAF5028); }}
  .scale-threshold, .scale-zero {{ position: absolute; top: -3px; bottom: -3px; width: 1px; background: #555; }}
  .scale-marker {{ position: absolute; top: -4px; width: 16px; height: 16px; border-radius: 50%; transform: translateX(-50%); transition: left 0.3s; }}
  .scale-axis {{ position: relative; height: 14px; margin-top: 8px; font-size: 10px; color: #555; font-family: 'SF Mono', Menlo, monospace; }}
  .scale-axis span {{ position: absolute; transform: translateX(-50%); }}
  .scale-axis span:first-child {{ transform: translateX(0); }}
  .scale-axis span:last-child {{ transform: translateX(-100%); }}
  .scale-legend {{ display: flex; justify-content: space-between; gap: 12px; margin-top: 4px; font-size: 10px; letter-spacing: 1.5px; text-transform: uppercase; font-weight: 600; }}
  .scale-cash-label {{ color: #E84B5A88; }}
  .scale-hold-label {{ color: #D89B2B88; text-align:center; }}
  .scale-long-label {{ color: #4CAF5088; text-align:right; }}

  .section-title {{
    font-size: 19px; letter-spacing: -0.3px;
    color: #e0e0e0; margin: 56px 0 14px; font-weight: 600;
    display: flex; align-items: center; gap: 14px;
    text-transform: none;
  }}
  .step-num {{
    display: inline-flex; align-items: center; justify-content: center;
    width: 30px; height: 30px; flex: 0 0 30px;
    background: #1a1a1a; border: 1px solid #2a2a2a;
    color: #888; font-size: 13px; font-weight: 600;
    border-radius: 50%; letter-spacing: 0;
    font-family: 'SF Mono', Menlo, monospace;
  }}
  .pillar-chip {{ display:inline-block; padding:2px 9px; border-radius:4px; font-size:10px; text-transform:uppercase; letter-spacing:1.5px; font-weight:600; margin-left:auto; }}
  .pillar-chip.valuation {{ background: rgba(255,255,255,0.06); color:#ccc; border:1px solid #2a2a2a; }}
  .pillar-chip.holder {{ background: rgba(205,170,106,0.10); color:#cdaa6a; border:1px solid rgba(205,170,106,0.25); }}
  .section-intro {{ color:#aaa; font-size:13px; line-height:1.55; margin:0 0 16px 0; }}
  .section-intro strong {{ color:#ddd; }}
  .dimension-reading {{ display:flex; align-items:baseline; gap:10px; }}
  .dimension-reading-value {{ font-size:18px; font-weight:600; }}
  .dimension-reading-label {{ font-size:11px; color:#555; text-transform:uppercase; letter-spacing:1.2px; font-weight:600; }}
  .inline-disclosure {{ margin: -2px 0 12px; color:#aaa; font-size:12px; line-height:1.5; }}
  .inline-disclosure strong {{ color:#cdaa6a; font-weight:600; }}

  .mrmi-chart {{ background:#111; border:1px solid #222; border-radius:10px; padding:18px 24px 18px; margin-bottom:24px; }}
  .mrmi-chart-header {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:6px; }}
  .mrmi-chart-header h3 {{ color:#ddd; font-size:16px; font-weight:600; display:inline-flex; align-items:center; gap:8px; }}
  .mrmi-chart-header h3 .info-icon {{ color:#555; }}
  .mrmi-chart-subtitle {{ font-size:13px; color:#888; margin:-4px 0 14px; line-height:1.5; }}
  .chart-container {{ position:relative; height:280px; width:100%; }}
  .chart-container.dimension {{ height:220px; }}
  .drivers-chart-grid {{ display:grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap:14px; margin-top:12px; }}
  .driver-chart-card {{ background:#0d0d0d; border:1px solid #1c1c1c; border-radius:8px; padding:14px 16px; }}
  .driver-chart-card h4 {{ color:#ddd; font-size:13px; font-weight:600; margin-bottom:4px; display:flex; justify-content:space-between; gap:10px; }}
  .driver-value {{ color:#aaa; font-weight:500; }}
  .driver-chart-card p {{ color:#666; font-size:11px; line-height:1.45; margin-bottom:10px; }}
  .driver-chart-wrap {{ position:relative; height:200px; width:100%; padding:0 8px; }}
  .mrmi-chart .legend {{ font-size:12px; color:#888; margin-bottom:10px; }}
  .mrmi-chart .legend-item {{ margin-right:14px; display:inline-flex; align-items:center; cursor:pointer; user-select:none; transition: opacity .15s, color .15s; }}
  .mrmi-chart .legend-item:hover {{ color:#fff; }}
  .mrmi-chart .legend-item.inactive {{ opacity:.4; color:#555; }}
  .mrmi-chart .legend-item.inactive .legend-dot {{ opacity:.5; }}
  .mrmi-chart .legend-dot {{ display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:6px; }}
  .range-tabs {{ display:inline-flex; gap:2px; }}
  .range-tabs button {{ background:#161616; border:1px solid #222; color:#777; font-size:11px; padding:4px 10px; border-radius:4px; cursor:pointer; font-family:inherit; font-weight:500; letter-spacing:.5px; }}
  .range-tabs button:hover {{ color:#ccc; border-color:#333; }}
  .range-tabs button.active {{ color:#fff; background:#1f1f1f; border-color:#333; }}
  .chart-description {{ margin-top:18px; padding-top:16px; border-top:1px solid #1f1f1f; }}
  .chart-description p {{ font-size:13px; color:#aaa; line-height:1.6; margin:0 0 10px 0; }}
  .chart-description strong {{ color:#ddd; }}

  .iteration-surface {{ margin-top:40px; }}
  table {{ width:100%; border-collapse:collapse; margin-top:8px; }}
  th {{ text-align:left; padding:10px 8px; border-bottom:1px solid #222; color:#555; font-size:10px; text-transform:uppercase; letter-spacing:1px; font-weight:600; }}
  th:first-child {{ padding-left:0; }}
  td {{ padding:12px 8px; border-bottom:1px solid #1a1a1a; font-size:13px; vertical-align:top; }}
  td:first-child {{ padding-left:0; }}
  tr:last-child td {{ border-bottom:none; }}
  .ind-name {{ color:#ddd; font-weight:500; }}

  details.drivers {{ background:#111; border:1px solid #222; border-radius:10px; padding:0; margin-bottom:12px; overflow:hidden; }}
  details.drivers > summary {{ list-style:none; padding:14px 24px; cursor:pointer; display:flex; justify-content:space-between; align-items:center; color:#aaa; font-size:12px; text-transform:uppercase; letter-spacing:1.5px; font-weight:600; }}
  details.drivers > summary::-webkit-details-marker {{ display:none; }}
  details.drivers > summary::after {{ content:'▾'; color:#555; font-size:12px; transition: transform .15s; }}
  details.drivers[open] > summary::after {{ transform: rotate(180deg); }}
  details.drivers > summary:hover {{ color:#fff; }}
  .drivers-body {{ padding:0 24px 18px; }}
  .details-copy {{ font-size:13px; color:#aaa; line-height:1.6; margin:12px 0; }}
  .formula {{ font-family:'SF Mono', Menlo, monospace; font-size:12px; color:#ccc; background:#0e0e0e; border:1px solid #1f1f1f; border-radius:6px; padding:12px 14px; white-space:pre-wrap; }}
  .suggest {{ margin-left:10px; font-size:11px; text-transform:none; letter-spacing:0; font-weight:500; }}
  code {{ font-family:'SF Mono', Menlo, monospace; color:#ddd; background:#171717; padding:1px 4px; border-radius:3px; }}

  .info-icon {{ color:#555; cursor:help; display:inline-flex; vertical-align:middle; margin-left:4px; transition:color .15s; position:relative; }}
  .info-icon:hover {{ color:#ccc; }}
  .info-icon .tip-pop {{ position:absolute; left:100%; top:50%; transform:translateY(-50%); margin-left:8px; z-index:50; width:420px; background:#1c1c1c; color:#ddd; font-size:12px; padding:10px 14px; border:1px solid #333; border-radius:6px; line-height:1.5; opacity:0; pointer-events:none; transition:opacity .15s; box-shadow:0 4px 12px rgba(0,0,0,.5); font-weight:400; text-transform:none; letter-spacing:normal; }}
  .info-icon:hover .tip-pop {{ opacity:1; }}
  .info-icon .tip-pop strong {{ color:#fff; }}
  .info-icon .tip-pop em {{ color:#cdaa6a; font-style:normal; }}

  footer {{ margin:44px 0 0; color:#666; font-size:12px; border-top:1px solid #1a1a1a; padding-top:16px; line-height:1.7; }}

  @media (max-width: 920px) {{
    body {{ padding:20px 18px 40px; }}
    .meta-bar {{ flex-direction:column; gap:6px; }}
    .meta-bar .meta-right {{ justify-content:flex-start; }}
    .hero-grid, .drivers-chart-grid {{ grid-template-columns:1fr; gap:22px; }}
    .hero-pillars {{ border-left:none; border-top:1px solid #1f1f1f; padding:20px 0 0; }}
    .hero-row {{ flex-direction:column; align-items:flex-start; gap:10px; }}
    .hero-value {{ font-size:64px; }}
    .chart-container {{ height:280px; }}
  }}
</style>
</head>
<body>

<div class="meta-bar">
  <span class="brand">MILK ROAD · ON-CHAIN INDEX</span>
  <span class="meta-right">
    <span>data {latest.date.strftime('%Y-%m-%d')}</span>
    <span>built {generated_at.strftime('%Y-%m-%d %H:%M UTC')}</span>
    <span>epoch {escape(latest.epoch)}</span>
    <span><i class="status-dot {status_class}"></i>{status_label}</span>
  </span>
</div>

<header class="hero">
  <div class="hero-eyebrow">Milk Road on-chain index · MROI · {latest.date.strftime('%Y-%m-%d')}</div>
  <div class="hero-grid">
    <div class="hero-main">
      <div class="hero-row">
        <div class="hero-value mono" style="color:{tier_color};">{_format_score(latest.pi)}</div>
        <div class="hero-action">
          <div class="hero-action-label" style="color:{tier_color};">Posture: {tier_label} · {latest.allocation_pct:.0f}% long</div>
          <div class="hero-action-sub">{tier_subtitle}</div>
          <div class="hero-action-sub" style="color:{signal_color};">Signal zone: {signal_zone} · {signal_subtitle}</div>
        </div>
      </div>
      {scale_html}
    </div>

    <aside class="hero-pillars">
      <div class="hero-pillars-title">What's behind it</div>
      <div class="hero-pillar">
        <span class="hero-pillar-name">Valuation</span>
        <span class="hero-pillar-right">
          <span class="hero-pillar-state" style="color:{_state_color(latest.valuation)};">{_state_label(latest.valuation)}</span>
          <span class="hero-pillar-value mono">{_format_score(latest.valuation)}</span>
        </span>
      </div>
      <div class="hero-pillar">
        <span class="hero-pillar-name">Holder Behavior</span>
        <span class="hero-pillar-right">
          <span class="hero-pillar-state" style="color:{_state_color(latest.holder_behavior)};">{_state_label(latest.holder_behavior)}</span>
          <span class="hero-pillar-value mono">{_format_score(latest.holder_behavior)}</span>
        </span>
      </div>
      <div class="hero-pillar">
        <span class="hero-pillar-name">BTC spot</span>
        <span class="hero-pillar-right"><span class="hero-pillar-value mono">${latest.btc_price:,.0f}</span></span>
      </div>
      <div class="hero-pillar-note">MROI = Holder Behavior only. Valuation is shown as a diagnostic, not an allocation input.</div>
    </aside>
  </div>
  <p class="hero-story">Milk Road Macro Index reads the outside risk-asset regime. Milk Road on-chain index now uses the validated P4 inside view: holder behavior as the spine, asymmetric thresholds for posture, and valuation retained only as cycle-context diagnostics. The technical math handle remains <code>MROI</code>.</p>
</header>

<div class="section-title"><span class="step-num">1</span>Holder-behavior MROI with P4 zones</div>
<div class="mrmi-chart">
  <div class="mrmi-chart-header">
    <h3>Milk Road on-chain index
      <span class="info-icon">{info_svg}<span class="tip-pop"><strong>How MROI works:</strong> MROI is the holder-behavior z-score. Green/amber/red backgrounds show the raw signal zones; the hero posture shows the state-machine output.</span></span>
    </h3>
    <div class="range-tabs" aria-label="Global chart range">
      <button data-range="1y" class="active">1Y</button>
      <button data-range="3y">3Y</button>
      <button data-range="5y">5Y</button>
      <button data-range="all">ALL</button>
    </div>
  </div>
  <p class="mrmi-chart-subtitle">Production holder-behavior MROI over time; BTC can be toggled as a normalized overlay. Green is raw LONG signal, amber holds the prior posture, red is raw CASH signal.</p>
  <div class="legend">
    <span class="legend-item" data-series="pi"><span class="legend-dot" style="background:#fff"></span>MROI</span>
    <span class="legend-item" data-series="btc"><span class="legend-dot" style="background:#A78BFA"></span>BTC</span>
  </div>
  <div class="chart-container"><canvas id="historyChart"></canvas></div>
  <div class="chart-description">
    <details class="drivers backtest-toggle">
      <summary><span>How well does this work historically?</span></summary>
      <div class="drivers-body">
        <p class="details-copy">Walk-forward P4 state-machine sizing by BTC cycle, using the same production 0% / 100% values and no leverage.</p>
        {_walk_forward_table(walk_forward_rows)}
      </div>
    </details>
  </div>
</div>

<div class="section-title"><span class="step-num">2</span>Valuation diagnostic<span class="pillar-chip valuation">Not in decision</span></div>
<p class="section-intro"><strong>Valuation.</strong> Answers where BTC trades relative to realized cost-basis and miner-revenue anchors. It remains useful for cycle awareness, but Phase G–P testing removed it from the allocation decision.</p>
<div class="mrmi-chart">
  <div class="mrmi-chart-header">
    <h3>Valuation
      <span class="info-icon">{info_svg}<span class="tip-pop"><strong>What you're seeing:</strong> the Valuation diagnostic z-score over time. It is the equal-weighted mean of the lagged 504d z-scored valuation constituents. The zero line is neutral; valuation is no longer part of production <code>MROI</code>.</span></span>
    </h3>

  </div>
  <p class="mrmi-chart-subtitle">Latest: <span class="mono" style="color:{_state_color(latest.valuation)};">{_format_score(latest.valuation)}</span> · {_state_label(latest.valuation)} · diagnostic only</p>
  <div class="chart-container dimension"><canvas id="valuationChart"></canvas></div>
</div>
<details class="drivers" id="valuation-drivers">
  <summary><span>Valuation drivers</span></summary>
  <div class="drivers-body">
    <p class="details-copy">Each driver is the production lagged 504d rolling z-score imported from <code>onchain_index.composite.valuation_constituents</code>.</p>
    <div class="drivers-chart-grid">
      <article class="driver-chart-card"><h4>z(STH MVRV)<span class="driver-value mono">{_format_score(latest.valuation_constituents['sth_mvrv'])}</span></h4><p>Short-term holder cost-basis valuation.</p><div class="driver-chart-wrap"><canvas id="driverValSth"></canvas></div></article>
      <article class="driver-chart-card"><h4>z(RHODL Ratio)<span class="driver-value mono">{_format_score(latest.valuation_constituents['rhodl_ratio'])}</span></h4><p>Realized-value age-band valuation oscillator.</p><div class="driver-chart-wrap"><canvas id="driverValRhodl"></canvas></div></article>
      <article class="driver-chart-card"><h4>z(Puell Multiple)<span class="driver-value mono">{_format_score(latest.valuation_constituents['puell_multiple'])}</span></h4><p>Miner-revenue valuation lens.</p><div class="driver-chart-wrap"><canvas id="driverValPuell"></canvas></div></article>
      <article class="driver-chart-card"><h4>z(MVRV-Z)<span class="driver-value mono">{_format_score(latest.valuation_constituents['mvrv_zscore'])}</span></h4><p>Canonical realized-cap deviation metric.</p><div class="driver-chart-wrap"><canvas id="driverValMvrvZ"></canvas></div></article>
    </div>
  </div>
</details>

<div class="section-title"><span class="step-num">3</span>How holders are positioning<span class="pillar-chip holder">Holder Behavior lens</span></div>
<p class="section-intro"><strong>Holder Behavior.</strong> Answers whether meaningful holders are adding or shedding conviction across on-chain, corporate DAT and ETF cohorts. This is now the sole production MROI spine.</p>
<div class="mrmi-chart">
  <div class="mrmi-chart-header">
    <h3>Holder Behavior
      <span class="info-icon">{info_svg}<span class="tip-pop"><strong>What you're seeing:</strong> the Holder Behavior z-score over time. It is the equal-weighted mean of available holder cohorts for each epoch: on-chain holders, corporate DAT, and institutional ETF flows. This series is production <code>MROI</code>.</span></span>
    </h3>

  </div>
  <p class="mrmi-chart-subtitle">Latest: <span class="mono" style="color:{_state_color(latest.holder_behavior)};">{_format_score(latest.holder_behavior)}</span> · {_state_label(latest.holder_behavior)}</p>
  <div class="chart-container dimension"><canvas id="holderChart"></canvas></div>
  <p class="inline-disclosure"><strong>Corporate DAT cohort:</strong> MSTR / Strategy, 100% of cohort signal.</p>
</div>
<details class="drivers" id="holder-drivers">
  <summary><span>Holder behavior drivers</span></summary>
  <div class="drivers-body">
    <p class="details-copy">Current cohorts each have one production constituent, so the cohort score is the drill-down series. The layout keeps room for multi-constituent cohorts later.</p>
    <div class="drivers-chart-grid">
      <article class="driver-chart-card"><h4>On-chain holders<span class="driver-value mono">{_format_score(latest.holder_cohorts['on_chain'])}</span></h4><p>z(HODL 1Y+ 30d-change, inverted).</p><div class="driver-chart-wrap"><canvas id="driverHolderOnChain"></canvas></div></article>
      <article class="driver-chart-card"><h4>Corporate DAT<span class="driver-value mono">{_format_score(latest.holder_cohorts['corporate_dat'])}</span></h4><p>z(MSTR / Strategy BTC holdings Δ 30d).</p><div class="driver-chart-wrap"><canvas id="driverHolderDat"></canvas></div></article>
      <article class="driver-chart-card"><h4>Institutional ETF<span class="driver-value mono">{_format_score(latest.holder_cohorts['institutional_etf'])}</span></h4><p>z(spot BTC ETF flow rolling 30d sum).</p><div class="driver-chart-wrap"><canvas id="driverHolderEtf"></canvas></div></article>
    </div>
  </div>
</details>

<section class="iteration-surface">
  <details class="drivers" open>
    <summary><span>Composite formulas {_edit_link('src/onchain_index/composite.py')}</span></summary>
    <div class="drivers-body">
      <div class="formula">Valuation diagnostic = mean_available(z(STH MVRV), z(RHODL), z(Puell Multiple), z(MVRV-Z))\nHolder Behavior = mean_available(on-chain, corporate DAT, institutional ETF)\nMROI = Holder Behavior\nPosture = LONG if MROI &gt; 0.0; CASH if MROI &lt; -0.3; otherwise hold prior state</div>
      <p class="details-copy">The renderer imports production composite functions directly; there is no dashboard-only signal path.</p>
    </div>
  </details>

  <details class="drivers" id="indicator-slate">
    <summary><span>Indicator slate {_edit_link('reports/phase-b-indicator-audit-2026-05-20.md', 'Suggest edit Phase B')} {_edit_link('reports/phase-c-composite-2026-05-20.md', 'Suggest edit Phase C')}</span></summary>
    <div class="drivers-body">{_indicator_table(indicator_rows)}</div>
  </details>

  <details class="drivers">
    <summary><span>Tier thresholds {_edit_link('src/onchain_index/composite.py')}</span></summary>
    <div class="drivers-body">
      <table><thead><tr><th>Raw MROI zone</th><th>State-machine action</th><th>Allocation</th></tr></thead><tbody>
        <tr><td class="mono">&lt; -0.3</td><td>CASH</td><td class="mono">0%</td></tr>
        <tr><td class="mono">-0.3 to 0.0</td><td>Hold prior LONG/CASH state</td><td class="mono">unchanged</td></tr>
        <tr><td class="mono">&gt; 0.0</td><td>LONG</td><td class="mono">100%</td></tr>
      </tbody></table>
    </div>
  </details>

  <details class="drivers">
    <summary><span>Walk-forward methodology {_edit_link('src/onchain_index/backtest.py')}</span></summary>
    <div class="drivers-body"><p class="details-copy">Backtests use BTC daily returns from BMP <code>btc_price</code>, apply the tier allocation to each day's return, and evaluate fixed cycle windows: 2014-2017, 2018-2021, 2022-2024, and 2025-now. Composite inputs are lagged through the rolling z-score helper, so a score dated T uses source data through T-1.</p></div>
  </details>

  <details class="drivers">
    <summary><span>Resolved framework choices {_edit_link('docs/theory.md')}</span></summary>
    <div class="drivers-body">
      <table><thead><tr><th>Question</th><th>Current v1 posture</th></tr></thead><tbody>
        <tr><td>Sizing floor</td><td>Resolved at 0% for CASH and 100% for LONG.</td></tr>
        <tr><td>Tier naming</td><td>Resolved to P4 binary wording: CASH / LONG.</td></tr>
        <tr><td>Threshold method</td><td>Resolved to asymmetric P4: LONG above 0.0, CASH below -0.3, hold prior state between.</td></tr>
        <tr><td>Diagnostic surface</td><td>Keep holder sub-cohorts prominent so composition drift is visible.</td></tr>
      </tbody></table>
    </div>
  </details>
</section>

<footer>
  Milk Road on-chain index · Technical handle: <code>MROI</code> · Repo: <a href="{PROJECT_REPO_URL}">{PROJECT_REPO_URL}</a> · Last commit: <span class="mono">{escape(sha)}</span> {escape(message)} · Last refresh UTC: <span class="mono">{generated_at.strftime('%Y-%m-%d %H:%M:%S')}</span> · Theory doc: {THEORY_VERSION}
</footer>

<script>
const ALL_POINTS = {chart_json};
const RANGE_DAYS = {{ '1y': 365, '3y': 1095, '5y': 1825, 'all': 0 }};
const visibleSeries = {{ pi: true, btc: true }};
const charts = {{}};
let activeRange = '1y';

function slicePoints(rangeKey = activeRange) {{
  const n = RANGE_DAYS[rangeKey] || 0;
  return n > 0 ? ALL_POINTS.slice(Math.max(ALL_POINTS.length - n, 0)) : ALL_POINTS.slice();
}}
function normalizePrices(arr) {{
  let first = null;
  for (const v of arr) {{ if (v !== null && v !== undefined) {{ first = v; break; }} }}
  if (!first) return arr;
  return arr.map(v => v !== null && v !== undefined ? (v / first) * 100 : null);
}}
function destroyChart(key) {{
  if (charts[key]) charts[key].destroy();
}}
const SHARED_LINE_STYLE = {{ borderWidth: 2.0, pointRadius: 0, tension: 0.1, spanGaps: true }};
const SHARED_CHART_CONFIG = {{
  responsive: true,
  maintainAspectRatio: false,
  animation: false,
  interaction: {{ mode: 'index', intersect: false }},
  legend: {{ display: false }},
  gridColor: '#1a1a1a',
  tickColor: '#555',
  tickFont: "'SF Mono', Menlo, monospace",
}};
function tooltipLabel(ctx) {{
  const value = ctx.parsed.y;
  return ctx.dataset.label + ': ' + (value !== null && Number.isFinite(value) ? value.toFixed(2) : '—');
}}
function sharedTooltip(extraCallbacks = {{}}) {{
  return {{
    backgroundColor: '#1a1a1a', borderColor: '#333', borderWidth: 1,
    titleColor: '#999', bodyColor: '#e0e0e0', titleFont: {{ size: 11 }},
    bodyFont: {{ size: 11, family: SHARED_CHART_CONFIG.tickFont }}, padding: 8,
    callbacks: {{ label: tooltipLabel, ...extraCallbacks }},
  }};
}}
function zeroLineAnnotation() {{
  return {{ zero: {{ type: 'line', yMin: 0, yMax: 0, borderColor: '#333', borderWidth: 1, scaleID: 'y' }} }};
}}
function tierBandAnnotations() {{
  return {{
    longZone: {{ type: 'box', yMin: {MROI_LONG_THRESHOLD}, yMax: 100, backgroundColor: 'rgba(76,175,80,0.10)', borderWidth: 0, drawTime: 'beforeDatasetsDraw' }},
    holdZone: {{ type: 'box', yMin: {MROI_CASH_THRESHOLD}, yMax: {MROI_LONG_THRESHOLD}, backgroundColor: 'rgba(216,155,43,0.14)', borderWidth: 0, drawTime: 'beforeDatasetsDraw' }},
    cashZone: {{ type: 'box', yMin: -100, yMax: {MROI_CASH_THRESHOLD}, backgroundColor: 'rgba(232,75,90,0.10)', borderWidth: 0, drawTime: 'beforeDatasetsDraw' }},
    longThreshold: {{ type: 'line', yMin: {MROI_LONG_THRESHOLD}, yMax: {MROI_LONG_THRESHOLD}, borderColor: '#4CAF5088', borderWidth: 1, scaleID: 'y' }},
    cashThreshold: {{ type: 'line', yMin: {MROI_CASH_THRESHOLD}, yMax: {MROI_CASH_THRESHOLD}, borderColor: '#E84B5A88', borderWidth: 1, scaleID: 'y' }},
  }};
}}
function sharedChartOptions({{ small = false, annotations = zeroLineAnnotation(), yAxis = {{}}, extraScales = {{}}, tooltipCallbacks = {{}} }} = {{}}) {{
  const tickSize = small ? 9 : 10;
  const tickLimit = small ? 10 : 12;
  return {{
    responsive: SHARED_CHART_CONFIG.responsive,
    maintainAspectRatio: SHARED_CHART_CONFIG.maintainAspectRatio,
    animation: SHARED_CHART_CONFIG.animation,
    interaction: SHARED_CHART_CONFIG.interaction,
    plugins: {{
      legend: SHARED_CHART_CONFIG.legend,
      tooltip: sharedTooltip(tooltipCallbacks),
      annotation: {{ annotations }},
    }},
    scales: {{
      x: {{ type: 'category', ticks: {{ color: SHARED_CHART_CONFIG.tickColor, font: {{ size: tickSize }}, maxTicksLimit: tickLimit, maxRotation: 0 }}, grid: {{ display: false }} }},
      y: {{ position: 'left', ...yAxis, ticks: {{ color: SHARED_CHART_CONFIG.tickColor, font: {{ size: tickSize, family: SHARED_CHART_CONFIG.tickFont }}, maxTicksLimit: small ? 6 : 7 }}, grid: {{ color: SHARED_CHART_CONFIG.gridColor }} }},
      ...extraScales,
    }},
  }};
}}
function lineDataset(label, data, color, extra = {{}}) {{
  return {{ label, data, borderColor: color, ...SHARED_LINE_STYLE, ...extra }};
}}
function buildPiDatasets(points) {{
  const datasets = [];
  if (visibleSeries.btc) datasets.push(lineDataset('BTC', normalizePrices(points.map(p => p.price)), '#A78BFA', {{ yAxisID: 'yPrice', order: 2 }}));
  if (visibleSeries.pi) datasets.push(lineDataset('MROI', points.map(p => p.pi), '#ffffff', {{ yAxisID: 'y', order: 0 }}));
  return datasets;
}}
function renderPi() {{
  const points = slicePoints();
  destroyChart('pi');
  charts.pi = new Chart(document.getElementById('historyChart'), {{
    type: 'line',
    data: {{ labels: points.map(p => p.date), datasets: buildPiDatasets(points) }},
    options: sharedChartOptions({{
      annotations: tierBandAnnotations(),
      extraScales: {{ yPrice: {{ display: visibleSeries.btc, position: 'right', ticks: {{ color: '#444', font: {{ size: 9, family: SHARED_CHART_CONFIG.tickFont }}, maxTicksLimit: 5 }}, grid: {{ display: false }} }} }},
    }}),
  }});
}}
function renderZChart(key, canvasId, field, label, color, small = false) {{
  const points = slicePoints().filter(p => p[field] !== null);
  destroyChart(key);
  charts[key] = new Chart(document.getElementById(canvasId), {{
    type: 'line',
    data: {{ labels: points.map(p => p.date), datasets: [lineDataset(label, points.map(p => p[field]), color, {{ fill: {{ target: 'origin', above: 'rgba(76,175,80,0.18)', below: 'rgba(232,75,90,0.18)' }} }})] }},
    options: sharedChartOptions({{ small }}),
  }});
}}
function renderAllCharts() {{
  renderPi();
  renderZChart('valuation', 'valuationChart', 'valuation', 'Valuation dimension', '#ffffff');
  renderZChart('holder', 'holderChart', 'holder', 'Holder Behavior dimension', '#ffffff');
  renderZChart('driverValSth', 'driverValSth', 'valuation_sth_mvrv', 'z(STH MVRV)', '#ffffff', true);
  renderZChart('driverValRhodl', 'driverValRhodl', 'valuation_rhodl_ratio', 'z(RHODL Ratio)', '#ffffff', true);
  renderZChart('driverValPuell', 'driverValPuell', 'valuation_puell_multiple', 'z(Puell Multiple)', '#ffffff', true);
  renderZChart('driverValMvrvZ', 'driverValMvrvZ', 'valuation_mvrv_zscore', 'z(MVRV-Z)', '#ffffff', true);
  renderZChart('driverHolderOnChain', 'driverHolderOnChain', 'holder_on_chain', 'On-chain holders', '#ffffff', true);
  renderZChart('driverHolderDat', 'driverHolderDat', 'holder_corporate_dat', 'Corporate DAT', '#ffffff', true);
  renderZChart('driverHolderEtf', 'driverHolderEtf', 'holder_institutional_etf', 'Institutional ETF', '#ffffff', true);
}}

document.querySelectorAll('.range-tabs button').forEach(button => {{
  button.addEventListener('click', () => {{
    activeRange = button.dataset.range || '1y';
    document.querySelectorAll('.range-tabs button').forEach(b => b.classList.toggle('active', b === button));
    renderAllCharts();
  }});
}});
document.querySelectorAll('.legend-item').forEach(item => {{
  item.addEventListener('click', () => {{
    const key = item.dataset.series;
    visibleSeries[key] = !visibleSeries[key];
    item.classList.toggle('inactive', !visibleSeries[key]);
    renderPi();
  }});
}});
document.querySelectorAll('details.drivers').forEach(details => {{
  details.addEventListener('toggle', () => {{
    if (details.open) requestAnimationFrame(() => Object.values(charts).forEach(chart => chart.resize()));
  }});
}});
renderAllCharts();
</script>
</body>
</html>
"""

def _write_status(paths: DashboardPaths, payload: dict[str, Any]) -> None:
    paths.status_json.parent.mkdir(parents=True, exist_ok=True)
    paths.status_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def build_dashboard(
    *,
    use_cache: bool = True,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    output_root: Path = PROJECT_ROOT,
) -> DashboardPaths:
    """Build ``outputs/dashboard.html`` and dashboard status."""
    paths = _paths(output_root)
    generated_at = datetime.now(tz=UTC)
    try:
        data = fetch_all(use_cache=use_cache, cache_dir=cache_dir)
        latest, components, score, tiers = _latest_scores(data)
        html = _render_html(
            latest=latest,
            components=components,
            historical=_historical_points(data, components),
            walk_forward_rows=_walk_forward_rows(tiers, data),
            indicator_rows=_indicator_rows(data),
            generated_at=generated_at,
        )
        paths.outputs_dashboard.parent.mkdir(parents=True, exist_ok=True)
        paths.outputs_dashboard.write_text(html, encoding="utf-8")
        _write_status(
            paths,
            {
                "last_run_utc": generated_at.isoformat().replace("+00:00", "Z"),
                "last_mroi": latest.pi,
                "last_tier": latest.tier,
                "last_error": None,
            },
        )
    except Exception as exc:
        _write_status(
            paths,
            {
                "last_run_utc": generated_at.isoformat().replace("+00:00", "Z"),
                "last_mroi": None,
                "last_tier": None,
                "last_error": str(exc),
            },
        )
        raise
    return paths


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the onchain-index dashboard.")
    parser.add_argument("--no-cache", action="store_true", help="Force fresh source fetches.")
    parser.add_argument("--open", action="store_true", help="Open outputs/dashboard.html after build.")
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path(str(DEFAULT_CACHE_DIR)),
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=PROJECT_ROOT,
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args(argv)

    paths = build_dashboard(
        use_cache=not args.no_cache,
        cache_dir=cast(Path, args.cache_dir),
        output_root=cast(Path, args.output_root),
    )
    print(f"wrote {paths.outputs_dashboard}")
    print(f"status {paths.status_json}")
    if args.open:
        webbrowser.open(paths.outputs_dashboard.resolve().as_uri())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
