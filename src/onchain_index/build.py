"""Build the onchain-index decision dashboard and Atlas."""

# ruff: noqa: E501

from __future__ import annotations

import argparse
import json
import math
import subprocess
import webbrowser
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
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
from onchain_index.brief import Brief, BriefContext, refresh_or_load_brief
from onchain_index.composite import (
    DAT_DELTA_DAYS,
    ETF_FLOW_SUM_DAYS,
    HODL_DELTA_DAYS,
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
THEORY_VERSION = "v0.8"

INDICATOR_DECISIONS: dict[str, tuple[str, str, str]] = {
    "STH MVRV": ("Valuation", "Diagnostic only", "Useful cycle-context lens; not used in the P4 posture."),
    "RHODL Ratio": ("Valuation", "Diagnostic only", "Age-band realized-value oscillator retained for Reference Library context."),
    "Puell Multiple": ("Valuation", "Diagnostic only", "Miner-revenue valuation lens retained for Reference Library context."),
    "MVRV-Z": ("Valuation", "Diagnostic only", "Canonical realized-cap deviation metric; chosen over NUPL for context."),
    "NUPL": ("Valuation", "Out / alternate", "Excluded because MVRV-Z/NUPL were highly colinear."),
    "LTH MVRV": ("Holder Behavior / on-chain", "Out", "Both tested signs were negative full-sample."),
    "HODL 1Y+": ("Holder Behavior / on-chain", "In transform", "Level rule failed; 30d-change inverted z is the included transform."),
    "Address Growth": ("Adoption / network", "Out", "Closer to adoption and negative under both tested signs."),
    "Reserve Risk": ("Holder / valuation hybrid", "Out", "Standalone rule failed; sign convention remains contested."),
    "Hash Ribbon": ("Out", "Out", "Miner-derived and outside the locked holder-behavior production spine."),
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
    "LONG": "100% long while the Bitcoin Demand Index is in its LONG state.",
    "CASH": "0% long while the Bitcoin Demand Index is in its CASH state.",
}


@dataclass(frozen=True)
class DashboardPaths:
    """Output paths for one dashboard build."""

    root: Path
    docs_index: Path
    docs_dashboard: Path
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
        docs_dashboard=output_root / "docs" / "dashboard.html",
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
        return "#4CAF50"
    if value >= 0.0:
        return "#8fd694"
    if value > -1.0:
        return "#D89B2B"
    return "#E84B5A"


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
        return f"Bitcoin Demand Index is in the HOLD band; posture remains {tier}."
    return f"Bitcoin Demand Index is in the {zone}; posture is {tier}."


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
    hodl_30d = cast(pd.Series, data["hodl_1yr_pct"].astype(float).diff(HODL_DELTA_DAYS))
    mstr_30d = cast(pd.Series, data["mstr_btc"].astype(float).diff(DAT_DELTA_DAYS))
    etf_30d = cast(
        pd.Series,
        data["etf_net_flow_m"].astype(float).rolling(window=ETF_FLOW_SUM_DAYS, min_periods=ETF_FLOW_SUM_DAYS).sum(),
    )
    joined = pd.DataFrame(
        {
            "btc_price": data["btc_price"],
            "raw_hodl_1yr_pct": data["hodl_1yr_pct"],
            "raw_hodl_1yr_delta_30d": hodl_30d,
            "raw_mstr_btc": data["mstr_btc"],
            "raw_mstr_btc_delta_30d": mstr_30d,
            "raw_etf_net_flow_m": data["etf_net_flow_m"],
            "raw_etf_net_flow_30d_sum": etf_30d,
            "raw_mvrv_zscore": data["mvrv_zscore"],
            "raw_sth_mvrv": data["sth_mvrv"],
            "raw_rhodl_ratio": data["rhodl_ratio"],
            "raw_puell_multiple": data["puell_multiple"],
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
            "raw_hodl_1yr_pct": _json_float(row["raw_hodl_1yr_pct"]),
            "raw_hodl_1yr_delta_30d": _json_float(row["raw_hodl_1yr_delta_30d"]),
            "raw_mstr_btc": _json_float(row["raw_mstr_btc"]),
            "raw_mstr_btc_delta_30d": _json_float(row["raw_mstr_btc_delta_30d"]),
            "raw_etf_net_flow_m": _json_float(row["raw_etf_net_flow_m"]),
            "raw_etf_net_flow_30d_sum": _json_float(row["raw_etf_net_flow_30d_sum"]),
            "raw_mvrv_zscore": _json_float(row["raw_mvrv_zscore"]),
            "raw_sth_mvrv": _json_float(row["raw_sth_mvrv"]),
            "raw_rhodl_ratio": _json_float(row["raw_rhodl_ratio"]),
            "raw_puell_multiple": _json_float(row["raw_puell_multiple"]),
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


def _component_delta(components: pd.DataFrame, column: str, latest_date: pd.Timestamp, days: int) -> float | None:
    if column not in components:
        return None
    latest = _json_float(components.loc[latest_date, column])
    if latest is None:
        return None
    cutoff = latest_date - timedelta(days=days)
    prior = components.loc[components.index <= cutoff, column].dropna()
    if prior.empty:
        return None
    previous = _json_float(prior.iloc[-1])
    if previous is None:
        return None
    return latest - previous


def _brief_context(latest: LatestScores, components: pd.DataFrame) -> BriefContext:
    return BriefContext(
        date=latest.date.strftime("%Y-%m-%d"),
        posture=TIER_LABELS[latest.tier],
        allocation_pct=latest.allocation_pct,
        mroi=latest.pi,
        mroi_7d_change=_component_delta(components, "mroi", latest.date, 7),
        valuation=latest.valuation,
        valuation_7d_change=_component_delta(components, "valuation", latest.date, 7),
        holder_behavior=latest.holder_behavior,
        holder_behavior_7d_change=_component_delta(components, "holder_behavior", latest.date, 7),
        signal_zone=_mroi_signal_zone(latest.pi),
        long_threshold=MROI_LONG_THRESHOLD,
        cash_threshold=MROI_CASH_THRESHOLD,
        valuation_constituents={
            VALUATION_LABELS.get(name, name): value for name, value in latest.valuation_constituents.items()
        },
        holder_cohorts={
            COHORT_LABELS.get(name, name): value for name, value in latest.holder_cohorts.items()
        },
    )


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
    """Horizontal CASH/HOLD/LONG bar for the Bitcoin Demand Index posture rule."""
    scale_min, scale_max = -2.0, 2.0
    clamped = max(scale_min, min(scale_max, pi_value))
    pct = (clamped - scale_min) / (scale_max - scale_min) * 100
    cash_pct = (MROI_CASH_THRESHOLD - scale_min) / (scale_max - scale_min) * 100
    long_pct = (MROI_LONG_THRESHOLD - scale_min) / (scale_max - scale_min) * 100
    hold_width = long_pct - cash_pct
    return f'''
      <div class="scale-bar" aria-label="Bitcoin Demand Index posture position">
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
      <thead><tr><th>Window</th><th>BTC B&amp;H</th><th>Demand Index tier</th><th>Alpha</th><th>BTC DD</th><th>Demand Index DD</th></tr></thead>
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
      <thead><tr><th>Indicator</th><th>Decision</th><th>Lens</th><th>Historical alpha</th><th>Note</th></tr></thead>
      <tbody>{body}</tbody>
    </table>
    '''

def _edit_link(path: str, label: str = "Suggest edit") -> str:
    return f'<a class="suggest" href="{GITHUB_EDIT_BASE}/{escape(path)}" target="_blank" rel="noreferrer">{escape(label)} ↗</a>'


def _render_brief(brief: Brief | None) -> str:
    if brief is None:
        return ""
    cached = " (cached)" if brief.stale else ""
    label = f"This week’s read · Bitcoin Demand Index · {brief.date}{cached}"
    return f'''
<div class="pillar-brief pillar-brief-headline">
  <div class="pillar-brief-eyebrow">{escape(label)}</div>
  {brief.html}
</div>
'''


def _render_html(
    *,
    latest: LatestScores,
    components: pd.DataFrame,
    historical: list[dict[str, float | str | None]],
    walk_forward_rows: list[dict[str, str | float | None]],
    indicator_rows: list[dict[str, str | float | None]],
    brief: Brief | None,
    generated_at: datetime,
) -> str:
    sha, _message = _latest_git_summary()
    status_label, status_class = _status_label(latest.date, generated_at)
    tier_color = TIER_COLORS[latest.tier]
    tier_label = TIER_LABELS[latest.tier]
    tier_subtitle = TIER_SUBTITLES[latest.tier]
    signal_zone = _mroi_signal_zone(latest.pi)
    signal_color = _mroi_signal_color(latest.pi)
    signal_subtitle = _mroi_signal_subtitle(latest.pi, tier_label)
    brief_html = _render_brief(brief)
    chart_json = json.dumps(historical, separators=(",", ":"))
    holder_driver_json = json.dumps(
        {
            "on_chain": {
                "label": "On-chain HODL",
                "field": "holder_on_chain",
                "group": "On-chain holders",
                "input": "HODL 1Y+ share / 30d delta",
                "raw_field": "raw_hodl_1yr_pct",
                "raw_label": "HODL 1Y+ share",
                "raw_unit": "%",
                "transform_field": "raw_hodl_1yr_delta_30d",
                "transform_label": "30d delta",
                "transform_unit": "pp",
                "desc": "Tracks whether long-term on-chain holders are adding or distributing supply; the final cohort score uses the inverted z-score of the 30-day HODL-share change.",
                "source": "Bitcoin Magazine Pro",
            },
            "corporate_dat": {
                "label": "MSTR DAT",
                "field": "holder_corporate_dat",
                "group": "Corporate treasury",
                "input": "Strategy BTC holdings / 30d delta",
                "raw_field": "raw_mstr_btc",
                "raw_label": "Strategy BTC holdings",
                "raw_unit": " BTC",
                "transform_field": "raw_mstr_btc_delta_30d",
                "transform_label": "30d delta",
                "transform_unit": " BTC",
                "desc": "Tracks Strategy/MSTR balance-sheet BTC accumulation as the current corporate DAT holder-behavior input.",
                "source": "Strategy filings / treasury history",
            },
            "institutional_etf": {
                "label": "ETF flows",
                "field": "holder_institutional_etf",
                "group": "Institutional ETF",
                "input": "Spot ETF net flow / 30d rolling sum",
                "raw_field": "raw_etf_net_flow_m",
                "raw_label": "Daily net flow",
                "raw_unit": "m",
                "transform_field": "raw_etf_net_flow_30d_sum",
                "transform_label": "30d rolling sum",
                "transform_unit": "m",
                "desc": "Tracks spot BTC ETF creations and redemptions as the cleanest post-2024 marginal-holder flow input.",
                "source": "Farside Investors",
            },
        },
        separators=(",", ":"),
    )
    reference_library_json = json.dumps(
        {
            "mvrv_zscore": {
                "label": "MVRV-Z",
                "category": "Valuation",
                "field": "raw_mvrv_zscore",
                "unit": "",
                "note": "Market value to realized value, z-scored variant.",
                "source": "Bitcoin Magazine Pro",
            },
            "sth_mvrv": {
                "label": "STH MVRV",
                "category": "Valuation",
                "field": "raw_sth_mvrv",
                "unit": "x",
                "note": "Short-term holder cost-basis pressure.",
                "source": "Bitcoin Magazine Pro",
            },
            "rhodl_ratio": {
                "label": "RHODL Ratio",
                "category": "Valuation",
                "field": "raw_rhodl_ratio",
                "unit": "",
                "note": "Realized-value age-band valuation oscillator.",
                "source": "Bitcoin Magazine Pro",
            },
            "puell_multiple": {
                "label": "Puell Multiple",
                "category": "Valuation",
                "field": "raw_puell_multiple",
                "unit": "x",
                "note": "Daily mining issuance revenue versus its 365-day average.",
                "source": "Bitcoin Magazine Pro",
            },
        },
        separators=(",", ":"),
    )
    scale_html = _make_pi_scale_bar(latest.pi, tier_color)
    info_svg = '<svg width="14" height="14" viewBox="0 0 14 14" fill="none"><circle cx="7" cy="7" r="6" stroke="currentColor" stroke-width="1.2"/><circle cx="7" cy="4" r="0.9" fill="currentColor"/><line x1="7" y1="6.5" x2="7" y2="10.5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Milk Road On-chain Dashboard · {latest.date.strftime('%Y-%m-%d')}</title>
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

  .pillar-brief {{
    margin: 20px 0 24px;
    padding: 16px 18px;
    background: #0d0d0d; border: 1px solid #1c1c1c; border-radius: 6px;
    border-left: 2px solid #333;
    color: #c8c8c8; font-size: 13.5px; line-height: 1.6;
  }}
  .pillar-brief-eyebrow {{
    font-size: 10px; text-transform: uppercase; letter-spacing: 1.8px;
    color: #666; font-weight: 500; margin-bottom: 10px;
  }}
  .pillar-brief p {{ margin: 0 0 10px; }}
  .pillar-brief p:last-child {{ margin-bottom: 0; }}
  .pillar-brief a {{ color: #cdaa6a; text-decoration: none; border-bottom: 1px dotted #6c5a36; }}
  .pillar-brief a:hover {{ color: #e6c98a; border-bottom-color: #cdaa6a; }}
  .pillar-brief.pillar-brief-headline {{
    color: #d4d4d4; font-size: 14px; line-height: 1.65;
    border-left-color: #cdaa6a; padding: 18px 20px;
  }}

  .hero-pillars {{ border-left: 1px solid #1f1f1f; padding: 4px 0 4px 32px; min-width: 285px; }}
  .hero-pillars-title {{ font-size: 10px; text-transform: uppercase; letter-spacing: 1.8px; color: #555; font-weight: 500; margin-bottom: 14px; }}
  .hero-secondary-note {{ margin-top: 14px; padding-top: 12px; border-top: 1px solid #161616; font-size: 11px; color: #555; line-height: 1.5; }}
  .hero-secondary-note strong {{ color: #888; font-weight: 600; }}
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
  .pillar-chip.holder {{ background: rgba(76,175,80,0.10); color:#8fd694; border:1px solid rgba(76,175,80,0.25); }}
  .pillar-chip.reference {{ background: rgba(167,139,250,0.10); color:#A78BFA; border:1px solid rgba(167,139,250,0.25); }}
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
  .drivers-desc {{ font-size:12px; color:#666; line-height:1.55; padding-bottom:12px; border-bottom:1px solid #1a1a1a; margin-bottom:4px; }}
  .drivers-desc strong {{ color:#999; }}
  #scorecard-holder table {{ width:100%; border-collapse:collapse; }}
  #scorecard-holder th {{ text-align:left; padding:10px 8px; border-bottom:1px solid #222; color:#555; font-size:10px; text-transform:uppercase; letter-spacing:1px; font-weight:600; }}
  #scorecard-holder th:first-child {{ padding-left:0; }}
  #scorecard-holder td {{ padding:12px 8px; border-bottom:1px solid #1a1a1a; font-size:13px; vertical-align:top; }}
  #scorecard-holder td:first-child {{ padding-left:0; }}
  .sc-row {{ cursor:pointer; transition:background .1s; }}
  .sc-row:hover {{ background:#161616; }}
  .sc-label {{ color:#ccc; font-weight:500; font-size:14px; }}
  .expanded-row {{ display:none; }}
  .expanded-row.active {{ display:table-row; }}
  .expanded-row td {{ padding:8px 0 16px; background:#0d0d0d; border-bottom:1px solid #222; }}
  .growth-drilldown-body {{ padding:4px 14px 0; }}
  .growth-inputs-table {{ width:100%; border-collapse:collapse; }}
  .growth-inputs-table th {{ text-align:left; padding:8px 6px; border-bottom:1px solid #222; color:#555; font-size:10px; text-transform:uppercase; letter-spacing:1px; font-weight:600; }}
  .growth-inputs-table td {{ padding:9px 6px; border-bottom:1px solid #1a1a1a; font-size:12px; vertical-align:top; }}
  .growth-inputs-table th:first-child, .growth-inputs-table td:first-child {{ padding-left:0; }}
  .growth-input-name {{ display:inline-flex; align-items:center; gap:6px; position:relative; }}
  .growth-info-icon {{ display:inline-flex; align-items:center; justify-content:center; width:14px; height:14px; border:1px solid #333; border-radius:50%; color:#8a8a8a; font-size:9px; font-weight:800; line-height:1; cursor:help; text-transform:lowercase; vertical-align:1px; position:relative; flex:0 0 auto; }}
  .growth-info-icon::after {{ content:attr(data-tooltip); position:absolute; left:50%; bottom:calc(100% + 8px); transform:translateX(-50%); width:max-content; max-width:min(280px, 70vw); padding:8px 10px; background:#111; color:#ddd; border:1px solid #333; border-radius:6px; box-shadow:0 8px 24px rgba(0,0,0,.42); font-size:11px; font-weight:500; line-height:1.45; text-transform:none; white-space:normal; opacity:0; visibility:hidden; pointer-events:none; z-index:30; }}
  .growth-info-icon:hover::after, .growth-info-icon:focus::after {{ opacity:1; visibility:visible; }}
  .growth-input-chart-panel {{ margin-top:18px; padding:12px 14px; background:#0d0d0d; border:1px solid #1c1c1c; border-radius:6px; }}
  .growth-input-chart-header {{ display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:10px; }}
  .growth-input-chart-title {{ color:#aaa; font-size:11px; text-transform:uppercase; letter-spacing:1.2px; font-weight:600; }}
  .chart-wrap {{ position:relative; height:200px; width:100%; padding:0 8px; }}
  .growth-input-chart-wrap {{ height:190px; padding:0; }}
  .chart-desc {{ font-size:12px; color:#666; line-height:1.55; padding:10px 12px 0; }}
  .val.neutral {{ color:#888; }}
  .dir {{ font-family:'SF Mono', Menlo, monospace; font-size:12px; }}
  .dir.up {{ color:#4CAF50; }}
  .dir.down {{ color:#E84B5A; }}
  .dir.flat {{ color:#555; }}
  .dot {{ display:inline-block; width:8px; height:8px; border-radius:50%; }}
  .dot.green {{ background:#4CAF50; }}
  .dot.red {{ background:#E84B5A; }}
  .library {{ background:#111; border:1px solid #222; border-radius:10px; padding:22px 26px; margin-bottom:24px; }}
  .library table {{ width:100%; border-collapse:collapse; margin-top:8px; }}
  .library th {{ text-align:left; padding:10px 14px; border-bottom:2px solid #222; color:#666; font-size:11px; text-transform:uppercase; letter-spacing:1px; font-weight:600; }}
  .library td {{ padding:10px 14px; border-bottom:1px solid #1a1a1a; font-size:14px; vertical-align:middle; }}
  .library tr:last-child td {{ border-bottom:none; }}
  .library .ind-name {{ color:#ddd; font-weight:500; }}
  .library .value {{ color:#fff; font-weight:600; }}
  .library-footer {{ margin-top:14px; font-size:12px; color:#666; }}
  .lib-row {{ cursor:pointer; transition:background .1s; }}
  .lib-row:hover {{ background:#161616; }}
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
  <span class="brand">MILK ROAD · ON-CHAIN DASHBOARD</span>
  <span class="meta-right">
    <span>data {latest.date.strftime('%Y-%m-%d')}</span>
    <span>built {generated_at.strftime('%Y-%m-%d %H:%M UTC')}</span>
    <span>epoch {escape(latest.epoch)}</span>
    <span><i class="status-dot {status_class}"></i>{status_label}</span>
  </span>
</div>

<header class="hero">
  <div class="hero-eyebrow">Bitcoin Demand Index · MROI technical series · {latest.date.strftime('%Y-%m-%d')}</div>
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
      <div class="hero-pillars-title">Index drivers</div>
      <div class="hero-pillar">
        <span class="hero-pillar-name">On-chain HODL delta</span>
        <span class="hero-pillar-right">
          <span class="hero-pillar-state" style="color:{_state_color(latest.holder_cohorts['on_chain'])};">{_state_label(latest.holder_cohorts['on_chain'])}</span>
          <span class="hero-pillar-value mono">{_format_score(latest.holder_cohorts['on_chain'])}</span>
        </span>
      </div>
      <div class="hero-pillar">
        <span class="hero-pillar-name">Strategy treasury delta</span>
        <span class="hero-pillar-right">
          <span class="hero-pillar-state" style="color:{_state_color(latest.holder_cohorts['corporate_dat'])};">{_state_label(latest.holder_cohorts['corporate_dat'])}</span>
          <span class="hero-pillar-value mono">{_format_score(latest.holder_cohorts['corporate_dat'])}</span>
        </span>
      </div>
      <div class="hero-pillar">
        <span class="hero-pillar-name">ETF flows</span>
        <span class="hero-pillar-right">
          <span class="hero-pillar-state" style="color:{_state_color(latest.holder_cohorts['institutional_etf'])};">{_state_label(latest.holder_cohorts['institutional_etf'])}</span>
          <span class="hero-pillar-value mono">{_format_score(latest.holder_cohorts['institutional_etf'])}</span>
        </span>
      </div>
      <div class="hero-secondary-note"><strong>BTC spot:</strong> <span class="mono">${latest.btc_price:,.0f}</span><br><strong>Valuation:</strong> {_format_score(latest.valuation)} diagnostic only — not an allocation input.</div>
    </aside>
  </div>
  <p class="hero-story">The Bitcoin Demand Index tracks the conviction of meaningful BTC holders — long-term on-chain holders, ETF flows, and corporate treasuries — then translates that composite into a simple posture signal inside the broader Milk Road On-chain Dashboard. Stay long while the demand index is above zero; move to cash when it drops below −0.3; hold your current position in between.</p>
</header>

{brief_html}

<div class="section-title"><span class="step-num">1</span>How the demand index has evolved</div>
<div class="mrmi-chart">
  <div class="mrmi-chart-header">
    <h3>Bitcoin Demand Index
      <span class="info-icon">{info_svg}<span class="tip-pop"><strong>How the signal works:</strong> the Bitcoin Demand Index is the holder-conviction z-score; <code>MROI</code> remains the internal technical handle. Green/amber/red backgrounds show LONG, HOLD, and CASH zones; the hero posture shows the current state.</span></span>
    </h3>
    <div class="range-tabs" aria-label="Global chart range">
      <button data-range="1y" class="active">1Y</button>
      <button data-range="3y">3Y</button>
      <button data-range="5y">5Y</button>
      <button data-range="all">ALL</button>
    </div>
  </div>
  <p class="mrmi-chart-subtitle">Bitcoin Demand Index over time; BTC can be toggled as a normalized reference overlay. Green is LONG, amber is HOLD, red is CASH.</p>
  <div class="legend">
    <span class="legend-item" data-series="pi"><span class="legend-dot" style="background:#fff"></span>Bitcoin Demand Index</span>
    <span class="legend-item" data-series="btc"><span class="legend-dot" style="background:#A78BFA"></span>BTC</span>
  </div>
  <div class="chart-container"><canvas id="historyChart"></canvas></div>
  <div class="chart-description">
    <details class="drivers backtest-toggle">
      <summary><span>How well does this work historically?</span></summary>
      <div class="drivers-body">
        <p class="details-copy">Walk-forward posture sizing by BTC cycle, using the same production 0% / 100% values and no leverage.</p>
        {_walk_forward_table(walk_forward_rows)}
      </div>
    </details>
  </div>
</div>

<div class="section-title"><span class="step-num">2</span>What drives the demand index<span class="pillar-chip holder">Decision inputs</span></div>
<p class="section-intro"><strong>Holder conviction.</strong> The Bitcoin Demand Index is driven by three cohorts: on-chain HODL behavior, Strategy treasury accumulation, and spot ETF flows. Click any row to open the input table and raw history behind the current z-score.</p>
<details class="drivers" open>
  <summary>
    <span><span class="status-dot green"></span>HOLDER CONVICTION COHORTS <span class="muted small">· On-chain HODL · MSTR DAT · ETF flows — click any row to expand</span></span>
  </summary>
  <div class="drivers-body">
    <p class="details-copy">Latest Bitcoin Demand Index: <span class="mono" style="color:{_state_color(latest.holder_behavior)};">{_format_score(latest.holder_behavior)}</span> · {_state_label(latest.holder_behavior)}. These are the actual decision inputs.</p>
    <p class="inline-disclosure"><strong>Strategy treasury cohort:</strong> Strategy is currently the corporate treasury input.</p>
    <div id="scorecard-holder"></div>
  </div>
</details>

<div class="section-title"><span class="step-num">3</span>Reference Library<span class="pillar-chip reference">Supplementary context</span></div>
<p class="section-intro"><strong>Supplementary context indicators — not part of the decision rule.</strong> These valuation lenses help with BTC cycle awareness, but they do not drive the Bitcoin Demand Index posture.</p>
<div class="library">
  <table>
    <thead><tr><th>Indicator</th><th>Category</th><th>Latest</th><th>Notes</th></tr></thead>
    <tbody>
      <tr class="lib-row" onclick="toggleReference('mvrv_zscore')"><td><span class="ind-name">MVRV-Z</span></td><td class="muted small">Valuation</td><td class="value mono" data-lib-latest="mvrv_zscore">—</td><td class="muted small">Market value to realized value, z-scored variant. Source: Bitcoin Magazine Pro.</td></tr>
      <tr class="expanded-row" id="exp-lib-mvrv_zscore"><td colspan="4"><div class="chart-wrap"><canvas id="canvas-lib-mvrv_zscore"></canvas></div><div class="chart-desc">Market value to realized value, z-scored variant. Source: Bitcoin Magazine Pro.</div></td></tr>
      <tr class="lib-row" onclick="toggleReference('sth_mvrv')"><td><span class="ind-name">STH MVRV</span></td><td class="muted small">Valuation</td><td class="value mono" data-lib-latest="sth_mvrv">—</td><td class="muted small">Short-term holder cost-basis pressure. Source: Bitcoin Magazine Pro.</td></tr>
      <tr class="expanded-row" id="exp-lib-sth_mvrv"><td colspan="4"><div class="chart-wrap"><canvas id="canvas-lib-sth_mvrv"></canvas></div><div class="chart-desc">Short-term holder cost-basis pressure. Source: Bitcoin Magazine Pro.</div></td></tr>
      <tr class="lib-row" onclick="toggleReference('rhodl_ratio')"><td><span class="ind-name">RHODL Ratio</span></td><td class="muted small">Valuation</td><td class="value mono" data-lib-latest="rhodl_ratio">—</td><td class="muted small">Realized-value age-band valuation oscillator. Source: Bitcoin Magazine Pro.</td></tr>
      <tr class="expanded-row" id="exp-lib-rhodl_ratio"><td colspan="4"><div class="chart-wrap"><canvas id="canvas-lib-rhodl_ratio"></canvas></div><div class="chart-desc">Realized-value age-band valuation oscillator. Source: Bitcoin Magazine Pro.</div></td></tr>
      <tr class="lib-row" onclick="toggleReference('puell_multiple')"><td><span class="ind-name">Puell Multiple</span></td><td class="muted small">Valuation</td><td class="value mono" data-lib-latest="puell_multiple">—</td><td class="muted small">Daily mining issuance revenue versus its 365-day average. Source: Bitcoin Magazine Pro.</td></tr>
      <tr class="expanded-row" id="exp-lib-puell_multiple"><td colspan="4"><div class="chart-wrap"><canvas id="canvas-lib-puell_multiple"></canvas></div><div class="chart-desc">Daily mining issuance revenue versus its 365-day average. Source: Bitcoin Magazine Pro.</div></td></tr>
    </tbody>
  </table>
  <div class="library-footer">Library entries do not drive the headline posture — they are context indicators that explain cycle narratives around the decision rule.</div>
</div>

<footer>
  Milk Road On-chain Dashboard · Core signal: Bitcoin Demand Index (<code>MROI</code> technical handle) · Repo: <a href="{PROJECT_REPO_URL}">{PROJECT_REPO_URL}</a> · Last commit: <span class="mono">{escape(sha)}</span> · Last refresh UTC: <span class="mono">{generated_at.strftime('%Y-%m-%d %H:%M:%S')}</span> · Theory doc: {THEORY_VERSION}
</footer>

<script>
const ALL_POINTS = {chart_json};
const HOLDER_DRIVER_META = {holder_driver_json};
const REFERENCE_LIBRARY_META = {reference_library_json};
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
function percentile(sorted, pct) {{
  if (!sorted.length) return null;
  const idx = (sorted.length - 1) * pct;
  const lo = Math.floor(idx);
  const hi = Math.ceil(idx);
  if (lo === hi) return sorted[lo];
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (idx - lo);
}}
function mroiAxis(points) {{
  const values = points.map(p => p.pi).filter(v => v !== null && Number.isFinite(v)).sort((a, b) => a - b);
  if (!values.length) return {{ min: -2.5, max: 2.5 }};
  const p01 = percentile(values, 0.01);
  const p99 = percentile(values, 0.99);
  const rawMin = Math.min(p01, {MROI_CASH_THRESHOLD});
  const rawMax = Math.max(p99, {MROI_LONG_THRESHOLD});
  const padding = Math.max((rawMax - rawMin) * 0.18, 0.35);
  return {{ min: Math.floor((rawMin - padding) * 10) / 10, max: Math.ceil((rawMax + padding) * 10) / 10 }};
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
function lastValidForField(field) {{
  for (let i = ALL_POINTS.length - 1; i >= 0; i--) {{
    const v = ALL_POINTS[i][field];
    if (v !== null && v !== undefined && Number.isFinite(v)) return {{ value: v, point: ALL_POINTS[i] }};
  }}
  return {{ value: null, point: null }};
}}
function previousValidForField(field, days) {{
  const latest = lastValidForField(field).point;
  if (!latest) return null;
  const cutoff = new Date(latest.date + 'T00:00:00Z');
  cutoff.setUTCDate(cutoff.getUTCDate() - days);
  for (let i = ALL_POINTS.length - 1; i >= 0; i--) {{
    const pointDate = new Date(ALL_POINTS[i].date + 'T00:00:00Z');
    if (pointDate > cutoff) continue;
    const v = ALL_POINTS[i][field];
    if (v !== null && v !== undefined && Number.isFinite(v)) return v;
  }}
  return null;
}}
function fmtZ(v) {{
  if (v === null || v === undefined || !Number.isFinite(v)) return '—';
  return (v >= 0 ? '+' : '') + v.toFixed(2);
}}
function fmtLatestValue(v, unit) {{
  if (v === null || v === undefined || !Number.isFinite(v)) return '—';
  if (Math.abs(v) >= 1000) return v.toLocaleString(undefined, {{ maximumFractionDigits: 0 }}) + (unit || '');
  return v.toFixed(Math.abs(v) >= 10 ? 1 : 2) + (unit || '');
}}
function valueClass(v) {{
  if (v === null || v === undefined || !Number.isFinite(v)) return 'neutral';
  if (v > 0) return 'pos';
  if (v < 0) return 'neg';
  return 'neutral';
}}
function fmtZDelta(current, previous) {{
  if (current === null || previous === null || current === undefined || previous === undefined) return '<span class="dir flat">—</span>';
  const diff = current - previous;
  if (Math.abs(diff) < 0.01) return `<span class="dir flat">${{diff >= 0 ? '+' : ''}}${{diff.toFixed(2)}}</span>`;
  const cls = diff > 0 ? 'up' : 'down';
  const sign = diff > 0 ? '▲ +' : '▼ ';
  return `<span class="dir ${{cls}}">${{sign}}${{diff.toFixed(2)}}</span>`;
}}
function holderRowValues(meta) {{
  const current = lastValidForField(meta.field).value;
  return {{
    current,
    prev7: previousValidForField(meta.field, 7),
    prev30: previousValidForField(meta.field, 30),
  }};
}}
function buildHolderScorecard() {{
  const container = document.getElementById('scorecard-holder');
  if (!container) return;
  const keys = ['on_chain', 'corporate_dat', 'institutional_etf'];
  let html = '<table><thead><tr>';
  html += '<th>Indicator</th><th>Value</th><th>7d</th><th>30d</th><th>Signal</th>';
  html += '</tr></thead><tbody>';
  keys.forEach(key => {{
    const meta = HOLDER_DRIVER_META[key];
    const values = holderRowValues(meta);
    const current = values.current;
    const z7 = fmtZDelta(current, values.prev7);
    const z30 = fmtZDelta(current, values.prev30);
    const isGreen = current !== null && current >= 0;
    const signalHtml = current === null ? '<span style="font-size:10px;color:#444;">—</span>' : `<span class="dot ${{isGreen ? 'green' : 'red'}}"></span>`;
    html += `<tr class="sc-row" onclick="toggleHolderDriver('${{key}}')">`;
    html += `<td><span class="sc-label">${{meta.label}}</span><span class="info-icon"><svg width="13" height="13" viewBox="0 0 14 14" fill="none"><circle cx="7" cy="7" r="6" stroke="currentColor" stroke-width="1.2"/><circle cx="7" cy="4" r="0.9" fill="currentColor"/><line x1="7" y1="6.5" x2="7" y2="10.5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg><span class="tip-pop">${{meta.desc}}</span></span><div class="muted small">${{meta.input}}</div></td>`;
    html += `<td><span class="val ${{valueClass(current)}}">${{fmtZ(current)}}</span></td>`;
    html += `<td>${{z7}}</td>`;
    html += `<td>${{z30}}</td>`;
    html += `<td>${{signalHtml}}</td>`;
    html += '</tr>';
    html += `<tr class="expanded-row" id="exp-holder-${{key}}"><td colspan="5"><div class="growth-drilldown-body"><p class="drivers-desc">${{meta.desc}}<br><span class="muted small">Source: ${{meta.source}}. Table columns match the macro dashboard driver drilldown: Input / Group / Current z / 7d zΔ / 30d zΔ.</span></p><table class="growth-inputs-table"><thead><tr><th>Input</th><th>Group</th><th title="Current z-score used in the cohort composite">Current z</th><th title="Input z-score change over the latest 7 calendar days">7d zΔ</th><th title="Input z-score change over the latest 30 calendar days">30d zΔ</th></tr></thead><tbody><tr class="driver-input-row"><td><div class="growth-input-name"><span class="sc-label">${{meta.input}}</span><span class="growth-info-icon" tabindex="0" aria-label="${{meta.desc}}" data-tooltip="${{meta.desc}}">i</span></div><div class="muted small">${{meta.source}}</div></td><td><span class="muted small">${{meta.group}}</span></td><td><span class="val ${{valueClass(current)}}">${{fmtZ(current)}}</span></td><td>${{z7}}</td><td>${{z30}}</td></tr></tbody></table><div class="growth-input-chart-panel"><div class="growth-input-chart-header"><span class="growth-input-chart-title">Raw input history</span><span class="muted small">${{meta.raw_label}} + ${{meta.transform_label}}</span></div><div class="chart-wrap growth-input-chart-wrap"><canvas id="canvas-holder-${{key}}"></canvas></div><div class="chart-desc">Raw ${{meta.raw_label}} is shown with ${{meta.transform_label}}; the cohort's final z-score is the value in the scorecard row above.</div></div></div></td></tr>`;
  }});
  html += '</tbody></table>';
  container.innerHTML = html;
}}
let holderCharts = {{}};
function toggleHolderDriver(key, forceOpen) {{
  const row = document.getElementById('exp-holder-' + key);
  if (!row) return;
  const isOpen = row.classList.contains('active');
  if (isOpen && !forceOpen) {{
    row.classList.remove('active');
    if (holderCharts[key]) {{ holderCharts[key].destroy(); delete holderCharts[key]; }}
  }} else if (!isOpen) {{
    row.classList.add('active');
    createHolderRawChart(key);
  }}
}}
function createHolderRawChart(key) {{
  const meta = HOLDER_DRIVER_META[key];
  const canvas = document.getElementById('canvas-holder-' + key);
  if (!meta || !canvas) return;
  const points = slicePoints().filter(p => p[meta.raw_field] !== null || p[meta.transform_field] !== null);
  const raw = points.map(p => p[meta.raw_field]);
  const transformed = points.map(p => p[meta.transform_field]);
  if (holderCharts[key]) holderCharts[key].destroy();
  holderCharts[key] = new Chart(canvas, {{
    type: 'line',
    data: {{ labels: points.map(p => p.date), datasets: [
      lineDataset(meta.raw_label, raw, '#ffffff', {{ yAxisID: 'y', borderWidth: 1.5 }}),
      lineDataset(meta.transform_label, transformed, '#cdaa6a', {{ yAxisID: 'yTransform', borderWidth: 1.3 }}),
    ] }},
    options: sharedChartOptions({{ small: true, annotations: {{}}, extraScales: {{ yTransform: {{ position: 'right', ticks: {{ color: '#6c5a36', font: {{ size: 9, family: SHARED_CHART_CONFIG.tickFont }}, maxTicksLimit: 5 }}, grid: {{ display: false }} }} }}, tooltipCallbacks: {{ label: ctx => ctx.dataset.label + ': ' + fmtLatestValue(ctx.parsed.y, ctx.datasetIndex === 0 ? meta.raw_unit : meta.transform_unit) }} }}),
  }});
}}
let referenceCharts = {{}};
function fillReferenceLatest() {{
  Object.entries(REFERENCE_LIBRARY_META).forEach(([key, meta]) => {{
    const node = document.querySelector(`[data-lib-latest="${{key}}"]`);
    if (!node) return;
    node.textContent = fmtLatestValue(lastValidForField(meta.field).value, meta.unit || '');
  }});
}}
function toggleReference(key) {{
  const row = document.getElementById('exp-lib-' + key);
  if (!row) return;
  if (row.classList.contains('active')) {{
    row.classList.remove('active');
    if (referenceCharts[key]) {{ referenceCharts[key].destroy(); delete referenceCharts[key]; }}
  }} else {{
    row.classList.add('active');
    createReferenceChart(key);
  }}
}}
function createReferenceChart(key) {{
  const meta = REFERENCE_LIBRARY_META[key];
  const canvas = document.getElementById('canvas-lib-' + key);
  if (!meta || !canvas) return;
  const points = slicePoints().filter(p => p[meta.field] !== null);
  if (referenceCharts[key]) referenceCharts[key].destroy();
  referenceCharts[key] = new Chart(canvas, {{
    type: 'line',
    data: {{ labels: points.map(p => p.date), datasets: [lineDataset(meta.label, points.map(p => p[meta.field]), '#ffffff', {{ borderWidth: 1.6 }})] }},
    options: sharedChartOptions({{ small: true, annotations: {{}}, tooltipCallbacks: {{ label: ctx => ctx.dataset.label + ': ' + fmtLatestValue(ctx.parsed.y, meta.unit || '') }} }}),
  }});
}}
function buildPiDatasets(points) {{
  const datasets = [];
  if (visibleSeries.btc) datasets.push(lineDataset('BTC', normalizePrices(points.map(p => p.price)), '#A78BFA', {{ yAxisID: 'yPrice', order: 2 }}));
  if (visibleSeries.pi) datasets.push(lineDataset('Bitcoin Demand Index', points.map(p => p.pi), '#ffffff', {{ yAxisID: 'y', order: 0 }}));
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
      yAxis: mroiAxis(points),
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
  Object.keys(holderCharts).forEach(key => createHolderRawChart(key));
  Object.keys(referenceCharts).forEach(key => createReferenceChart(key));
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
buildHolderScorecard();
fillReferenceLatest();
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
    force_brief: bool = False,
) -> DashboardPaths:
    """Build ``outputs/dashboard.html``, Pages copy, and dashboard status."""
    paths = _paths(output_root)
    generated_at = datetime.now(tz=UTC)
    try:
        data = fetch_all(use_cache=use_cache, cache_dir=cache_dir)
        latest, components, score, tiers = _latest_scores(data)
        brief = refresh_or_load_brief(
            _brief_context(latest, components),
            briefs_dir=output_root / "briefs",
            force=force_brief,
        )
        html = _render_html(
            latest=latest,
            components=components,
            historical=_historical_points(data, components),
            walk_forward_rows=_walk_forward_rows(tiers, data),
            indicator_rows=_indicator_rows(data),
            brief=brief,
            generated_at=generated_at,
        )
        html = "\n".join(line.rstrip() for line in html.splitlines()) + "\n"
        paths.outputs_dashboard.parent.mkdir(parents=True, exist_ok=True)
        paths.outputs_dashboard.write_text(html, encoding="utf-8")
        paths.docs_dashboard.parent.mkdir(parents=True, exist_ok=True)
        paths.docs_dashboard.write_bytes(paths.outputs_dashboard.read_bytes())
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
    parser.add_argument(
        "--force-brief",
        action="store_true",
        help="Regenerate the weekly AI brief even if this week's brief exists.",
    )
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
        force_brief=bool(args.force_brief),
    )
    print(f"wrote {paths.outputs_dashboard}")
    print(f"pages {paths.docs_dashboard}")
    print(f"status {paths.status_json}")
    if args.open:
        webbrowser.open(paths.outputs_dashboard.resolve().as_uri())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
