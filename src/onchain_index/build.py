"""Build the onchain-index decision dashboard and iteration surface."""

# ruff: noqa: E501

from __future__ import annotations

import argparse
import json
import math
import shutil
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
    TIER_PCT,
    epoch_for_date,
    holder_behavior_cohorts,
    holder_behavior_composite,
    pi_score,
    sizing_tier,
    valuation_composite,
    valuation_constituents,
)
from onchain_index.data import DEFAULT_CACHE_DIR, PROJECT_ROOT, fetch_all

GITHUB_EDIT_BASE = "https://github.com/m0xt/onchain-index/edit/main"
PROJECT_REPO_URL = "https://github.com/m0xt/onchain-index"
THEORY_VERSION = "v0.3"

CYCLE_REFERENCE_POINTS: tuple[tuple[str, str], ...] = (
    ("2013 top", "2013-12-04"),
    ("2015 bottom", "2015-01-14"),
    ("2017 top", "2017-12-17"),
    ("2018 bottom", "2018-12-15"),
    ("2021 top", "2021-11-10"),
    ("2022 bottom / FTX", "2022-11-21"),
)

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
    "exchange_flow": "Exchange flow",
}

VALUATION_LABELS: dict[str, str] = {
    "sth_mvrv": "STH MVRV",
    "rhodl_ratio": "RHODL Ratio",
    "puell_multiple": "Puell Multiple",
    "mvrv_zscore": "MVRV-Z",
}

TIER_COLORS: dict[str, str] = {
    "Strong": "#166534",
    "Sized": "#2563eb",
    "Trim": "#92400e",
    "Cash": "#991b1b",
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
        raise ValueError("PI_score has no non-NaN observations")
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
    score = pi_score(data)
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
            "pi_score": score,
            "valuation": valuation,
            "holder_behavior": holder,
            **{f"cohort_{name}": series for name, series in cohorts.items()},
        },
        axis=1,
    )
    return latest, components, score, tiers


def _historical_points(data: pd.DataFrame, components: pd.DataFrame) -> list[dict[str, float | str | None]]:
    joined = pd.DataFrame(
        {
            "btc_price": data["btc_price"],
            "pi_score": components["pi_score"],
        },
        index=data.index,
    ).dropna(subset=["pi_score", "btc_price"])
    points: list[dict[str, float | str | None]] = []
    for index, row in joined.iterrows():
        points.append(
            {
                "date": str(index)[:10],
                "pi": _json_float(row["pi_score"]),
                "price": _json_float(row["btc_price"]),
            }
        )
    return points


def _cycle_markers(score: pd.Series) -> list[dict[str, str | float | None]]:
    markers: list[dict[str, str | float | None]] = []
    for label, date_text in CYCLE_REFERENCE_POINTS:
        date = pd.Timestamp(date_text)
        if date not in score.index:
            continue
        markers.append(
            {
                "label": label,
                "date": date.strftime("%Y-%m-%d"),
                "pi": _json_float(score.loc[date]),
            }
        )
    return markers


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


def _cohort_cards(components: pd.DataFrame, latest: LatestScores) -> str:
    specs = (
        ("on_chain", "HODL 1Y+ 30d-change inverted z", "on-chain holder acceleration"),
        ("corporate_dat", "MSTR 30d holdings change z", "corporate treasury accumulation"),
        ("institutional_etf", "Rolling 30d ETF net-flow z", "institutional fund flows"),
        ("exchange_flow", "Pending real exchange net-flow source", "data gap"),
    )
    cards: list[str] = []
    for key, constituents, description in specs:
        value = latest.holder_cohorts[key]
        label = COHORT_LABELS[key]
        availability = _availability(cast(pd.Series, components[f"cohort_{key}"]))
        gap = key == "exchange_flow"
        tag = "pending source" if gap else "active" if value is not None else "warming up"
        cards.append(
            f"""
            <article class=\"card cohort\">
              <div class=\"card-title-row\">
                <h3>{escape(label)}</h3>
                <span class=\"tag {'gap' if gap else ''}\">{escape(tag)}</span>
              </div>
              <div class=\"score\" style=\"color:{_score_color(value)}\">{_format_score(value)}</div>
              <p>{escape(description)}</p>
              <dl>
                <dt>Constituents</dt><dd>{escape(constituents)}</dd>
                <dt>Epoch availability</dt><dd>{escape(availability)}</dd>
              </dl>
              {('<a href=\"reports/phase-c-composite-2026-05-20.md#5-sub-cohort-epoch-evolution\">Read gap note</a>' if gap else '')}
            </article>
            """
        )
    return "\n".join(cards)


def _dimension_card(title: str, value: float, items: dict[str, float | None], summary: str) -> str:
    rows = "".join(
        f"<li><span>{escape(label)}</span><strong>{_format_score(score)}</strong></li>"
        for label, score in items.items()
    )
    return f"""
    <article class=\"card dimension\">
      <h3>{escape(title)}</h3>
      <div class=\"score\" style=\"color:{_score_color(value)}\">{_format_score(value)}</div>
      <p>{escape(summary)}</p>
      <ul class=\"metric-list\">{rows}</ul>
    </article>
    """


def _walk_forward_table(rows: list[dict[str, str | float | None]]) -> str:
    body = "".join(
        "<tr>"
        f"<td>{escape(str(row['window']))}</td>"
        f"<td>{_format_pct(_json_float(row.get('bh_ann')))}</td>"
        f"<td>{_format_pct(_json_float(row.get('strat_ann')))}</td>"
        f"<td>{_format_pct(_json_float(row.get('alpha')))}</td>"
        f"<td>{_format_pct(_json_float(row.get('bh_dd')))}</td>"
        f"<td>{_format_pct(_json_float(row.get('strat_dd')))}</td>"
        "</tr>"
        for row in rows
    )
    return f"""
    <table>
      <thead><tr><th>Window</th><th>BTC B&amp;H</th><th>PI tier</th><th>Alpha</th><th>BTC DD</th><th>PI DD</th></tr></thead>
      <tbody>{body}</tbody>
    </table>
    """


def _indicator_table(rows: list[dict[str, str | float | None]]) -> str:
    body = "".join(
        "<tr>"
        f"<td>{escape(str(row['indicator']))}</td>"
        f"<td>{escape(str(row['decision']))}</td>"
        f"<td>{escape(str(row['dimension']))}</td>"
        f"<td>{_format_pct(_json_float(row.get('alpha')))}</td>"
        f"<td>{escape(str(row['note']))}</td>"
        "</tr>"
        for row in rows
    )
    return f"""
    <table>
      <thead><tr><th>Indicator</th><th>Decision</th><th>Composite</th><th>Phase B alpha</th><th>Note</th></tr></thead>
      <tbody>{body}</tbody>
    </table>
    """


def _edit_link(path: str, label: str = "Suggest edit") -> str:
    return f'<a class="suggest" href="{GITHUB_EDIT_BASE}/{escape(path)}" target="_blank" rel="noreferrer">{escape(label)} ↗</a>'


def _render_html(
    *,
    latest: LatestScores,
    components: pd.DataFrame,
    historical: list[dict[str, float | str | None]],
    markers: list[dict[str, str | float | None]],
    walk_forward_rows: list[dict[str, str | float | None]],
    indicator_rows: list[dict[str, str | float | None]],
    generated_at: datetime,
) -> str:
    sha, message = _latest_git_summary()
    status_label, status_class = _status_label(latest.date, generated_at)
    tier_color = TIER_COLORS[latest.tier]
    valuation_items = {
        VALUATION_LABELS[name]: latest.valuation_constituents[name]
        for name in VALUATION_LABELS
    }
    holder_items = {COHORT_LABELS[name]: latest.holder_cohorts[name] for name in COHORT_LABELS}
    chart_json = json.dumps(historical, separators=(",", ":"))
    markers_json = json.dumps(markers, separators=(",", ":"))

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>onchain-index — BTC regime score</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ font: 14px/1.5 -apple-system, BlinkMacSystemFont, "SF Pro Text", Inter, system-ui, sans-serif; max-width: 1120px; margin: 2em auto; padding: 0 1em; color: #111827; background: #ffffff; }}
  h1 {{ font-size: 24px; margin: 0 0 .25em; letter-spacing: -0.02em; }}
  h2 {{ font-size: 17px; margin: 0 0 .75em; }}
  h3 {{ font-size: 14px; margin: 0 0 .4em; }}
  a {{ color: #2563eb; }}
  .muted {{ color: #6b7280; }}
  .status-row, .hero, .grid, .cohort-grid {{ display: grid; gap: 12px; }}
  .status-row {{ grid-template-columns: repeat(4, minmax(0, 1fr)); margin: 1em 0 1.5em; }}
  .hero {{ grid-template-columns: 1.3fr repeat(3, 1fr); align-items: stretch; margin-bottom: 1.5em; }}
  .grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); margin-bottom: 1.5em; }}
  .cohort-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); margin-bottom: 1.5em; }}
  .card, .stat, details {{ border: 1px solid #d1d5db; border-radius: 10px; background: #fff; box-shadow: 0 1px 2px rgba(0,0,0,.04); padding: 12px 14px; }}
  .stat {{ background: #f9fafb; }}
  .label {{ display: block; color: #6b7280; font-size: 11.5px; text-transform: uppercase; letter-spacing: .06em; }}
  .value {{ display: block; font-weight: 700; margin-top: 2px; }}
  .big-score {{ font-size: clamp(42px, 8vw, 76px); line-height: .95; font-weight: 800; letter-spacing: -.06em; color: {tier_color}; }}
  .tier-badge, .status-badge, .tag {{ display: inline-block; border-radius: 999px; padding: 3px 9px; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; }}
  .tier-badge {{ background: {tier_color}; color: #fff; }}
  .status-badge.green {{ background: #dcfce7; color: #166534; }}
  .status-badge.yellow {{ background: #fef3c7; color: #92400e; }}
  .status-badge.red {{ background: #fee2e2; color: #991b1b; }}
  .tag {{ background: #e5e7eb; color: #374151; }}
  .tag.gap {{ background: #fee2e2; color: #991b1b; }}
  .score {{ font-size: 30px; line-height: 1; font-weight: 800; letter-spacing: -.04em; margin: 8px 0; }}
  .metric-list {{ list-style: none; margin: 12px 0 0; padding: 0; }}
  .metric-list li {{ display: flex; justify-content: space-between; gap: 16px; padding: 6px 0; border-bottom: 1px solid #f3f4f6; }}
  .card-title-row {{ display: flex; align-items: start; justify-content: space-between; gap: 10px; }}
  dl {{ display: grid; grid-template-columns: 105px 1fr; gap: 4px 10px; margin: 10px 0 0; }}
  dt {{ color: #6b7280; }}
  dd {{ margin: 0; }}
  table {{ width: 100%; border-collapse: collapse; margin: .5em 0 0; }}
  th, td {{ text-align: left; padding: 7px 8px; border-bottom: 1px solid #e5e7eb; vertical-align: top; }}
  th {{ color: #374151; font-size: 12px; }}
  .chart-card {{ padding: 14px; margin-bottom: 1.5em; }}
  .chart-wrap {{ position: relative; height: 430px; background: linear-gradient(to bottom, rgba(22,101,52,.06) 0 41.7%, rgba(37,99,235,.05) 41.7% 50%, rgba(146,64,14,.06) 50% 58.3%, rgba(153,27,27,.06) 58.3% 100%); border: 1px solid #e5e7eb; border-radius: 10px; padding: 8px; }}
  .range-buttons {{ display: flex; gap: 6px; margin: 0 0 10px; }}
  .range-buttons button {{ border: 1px solid #d1d5db; background: #fff; border-radius: 8px; padding: 4px 9px; cursor: pointer; }}
  .range-buttons button.active {{ background: #111827; color: #fff; border-color: #111827; }}
  details {{ padding: 0; margin-bottom: 10px; overflow: hidden; }}
  summary {{ cursor: pointer; user-select: none; padding: 12px 14px; font-weight: 700; }}
  details[open] summary {{ border-bottom: 1px solid #e5e7eb; }}
  .details-body {{ padding: 12px 14px 14px; }}
  .formula {{ font-family: "SF Mono", ui-monospace, Menlo, Consolas, monospace; font-size: 12px; background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; padding: 10px; white-space: pre-wrap; }}
  .suggest {{ float: right; font-size: 12px; font-weight: 500; }}
  footer {{ margin: 2em 0 0; color: #6b7280; font-size: 12px; border-top: 1px solid #e5e7eb; padding-top: 12px; }}
  @media (max-width: 820px) {{ .status-row, .hero, .grid, .cohort-grid {{ grid-template-columns: 1fr; }} .chart-wrap {{ height: 340px; }} }}
</style>
</head>
<body>
  <header>
    <h1>onchain-index — BTC regime score</h1>
    <div class="muted">PI_score = Valuation + Holder Behavior. Multi-month positioning, on-chain perspective.</div>
    <div class="status-row">
      <div class="stat"><span class="label">As-of data</span><span class="value">{latest.date.strftime('%Y-%m-%d')}</span></div>
      <div class="stat"><span class="label">Last refresh</span><span class="value">{generated_at.strftime('%Y-%m-%d %H:%M UTC')}</span></div>
      <div class="stat"><span class="label">Status</span><span class="status-badge {status_class}">{status_label}</span></div>
      <div class="stat"><span class="label">Epoch</span><span class="value">{escape(latest.epoch)} — on-chain + DAT + ETF</span></div>
    </div>
  </header>

  <section class="hero">
    <article class="card">
      <span class="label">Current PI_score</span>
      <div class="big-score">{_format_score(latest.pi)}</div>
      <div class="muted">Valuation {_format_score(latest.valuation)} + Holder Behavior {_format_score(latest.holder_behavior)}</div>
    </article>
    <article class="card"><span class="label">Tier</span><p><span class="tier-badge">{escape(latest.tier.upper())}</span></p><div class="muted">Fixed thresholds: -1, 0, +1</div></article>
    <article class="card"><span class="label">Allocation</span><div class="score">{latest.allocation_pct:.0f}%</div><div class="muted">Tier-driven BTC exposure</div></article>
    <article class="card"><span class="label">BTC spot</span><div class="score">${latest.btc_price:,.0f}</div><div class="muted">Last data point used: {latest.date.strftime('%Y-%m-%d')}</div></article>
  </section>

  <section class="grid">
    {_dimension_card('Valuation', latest.valuation, valuation_items, 'Mean of available z-scored valuation constituents.')}
    {_dimension_card('Holder Behavior', latest.holder_behavior, holder_items, 'Epoch-aware mean of available holder cohorts.')}
  </section>

  <section>
    <h2>Holder sub-cohorts</h2>
    <div class="cohort-grid">{_cohort_cards(components, latest)}</div>
  </section>

  <section class="card chart-card">
    <h2>Historical chart</h2>
    <div class="range-buttons" aria-label="Date range">
      <button data-range="365">1y</button><button data-range="1095">3y</button><button data-range="1825">5y</button><button data-range="all" class="active">all</button>
    </div>
    <div class="chart-wrap"><canvas id="historyChart"></canvas></div>
    <p class="muted">Gray line is BTC log price on the right axis. PI_score is on the left axis with tier bands: Cash, Trim, Sized, Strong. Markers show Phase C cycle reference points.</p>
  </section>

  <section class="card">
    <h2>Walk-forward backtest</h2>
    {_walk_forward_table(walk_forward_rows)}
  </section>

  <section>
    <h2>Iteration surface</h2>
    <details open>
      <summary>Composite formulas {_edit_link('src/onchain_index/composite.py')}</summary>
      <div class="details-body">
        <div class="formula">Valuation = mean_available(z(STH MVRV), z(RHODL), z(Puell Multiple), z(MVRV-Z))\nHolder Behavior = mean_available(on-chain, corporate DAT, institutional ETF, exchange flow)\nPI_score = Valuation + Holder Behavior</div>
        <p>The renderer imports the production composite functions directly; there is no dashboard-only signal path.</p>
      </div>
    </details>

    <details id="indicator-slate">
      <summary>Indicator slate {_edit_link('reports/phase-b-indicator-audit-2026-05-20.md', 'Suggest edit Phase B')} {_edit_link('reports/phase-c-composite-2026-05-20.md', 'Suggest edit Phase C')}</summary>
      <div class="details-body">{_indicator_table(indicator_rows)}</div>
    </details>

    <details>
      <summary>Tier thresholds {_edit_link('src/onchain_index/composite.py')}</summary>
      <div class="details-body">
        <table><thead><tr><th>PI_score bucket</th><th>Tier</th><th>Allocation</th></tr></thead><tbody>
          <tr><td>&lt; -1.0</td><td>Cash</td><td>0%</td></tr>
          <tr><td>[-1.0, 0.0)</td><td>Trim</td><td>50%</td></tr>
          <tr><td>[0.0, +1.0)</td><td>Sized</td><td>75%</td></tr>
          <tr><td>&gt;= +1.0</td><td>Strong</td><td>100%</td></tr>
        </tbody></table>
      </div>
    </details>

    <details>
      <summary>Walk-forward methodology {_edit_link('src/onchain_index/backtest.py')}</summary>
      <div class="details-body">
        <p>Backtests use BTC daily returns from BMP <code>btc_price</code>, apply the tier allocation to each day's return, and evaluate fixed cycle windows: 2014-2017, 2018-2021, 2022-2024, and 2025-now. Composite inputs are lagged through the rolling z-score helper, so a score dated T uses source data through T-1.</p>
      </div>
    </details>

    <details>
      <summary>Open questions {_edit_link('docs/theory.md')}</summary>
      <div class="details-body">
        <ul>
          <li><strong>Sizing floor:</strong> v1 default locked at 0% Cash; revisit only as a portfolio-policy choice.</li>
          <li><strong>Tier naming:</strong> v1 labels locked as Strong / Sized / Trim / Cash.</li>
          <li><strong>Threshold method:</strong> v1 uses fixed (-1, 0, +1); future work can compare rolling percentiles or transition-calibrated thresholds.</li>
          <li><strong>Diagnostic surface:</strong> keep holder sub-cohorts prominent so composition drift is visible.</li>
        </ul>
      </div>
    </details>
  </section>

  <footer>
    Repo: <a href="{PROJECT_REPO_URL}">{PROJECT_REPO_URL}</a> · Last commit: {escape(sha)} {escape(message)} · Last refresh UTC: {generated_at.strftime('%Y-%m-%d %H:%M:%S')} · Theory doc: {THEORY_VERSION}
  </footer>

<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<script>
const ALL_POINTS = {chart_json};
const MARKERS = {markers_json};
const ctx = document.getElementById('historyChart');
let chart;
function slicePoints(range) {{
  if (range === 'all') return ALL_POINTS;
  return ALL_POINTS.slice(Math.max(ALL_POINTS.length - Number(range), 0));
}}
function markerPoints(points) {{
  const dates = new Set(points.map(p => p.date));
  return MARKERS.filter(m => dates.has(m.date) && m.pi !== null).map(m => ({{x: m.date, y: m.pi, label: m.label}}));
}}
function render(range) {{
  const points = slicePoints(range);
  const labels = points.map(p => p.date);
  const data = {{
    labels,
    datasets: [
      {{label: 'PI_score', data: points.map(p => p.pi), borderColor: '#111827', borderWidth: 2, pointRadius: 0, yAxisID: 'y'}},
      {{label: 'BTC log price', data: points.map(p => p.price), borderColor: 'rgba(107,114,128,.45)', borderWidth: 1.5, pointRadius: 0, yAxisID: 'y1'}},
      {{type: 'scatter', label: 'Cycle references', data: markerPoints(points), parsing: false, backgroundColor: '#991b1b', borderColor: '#991b1b', pointRadius: 4, yAxisID: 'y'}}
    ]
  }};
  const options = {{
    responsive: true,
    maintainAspectRatio: false,
    interaction: {{mode: 'index', intersect: false}},
    scales: {{
      x: {{ticks: {{maxTicksLimit: 10}}}},
      y: {{min: -6, max: 6, title: {{display: true, text: 'PI_score'}}}},
      y1: {{type: 'logarithmic', position: 'right', grid: {{drawOnChartArea: false}}, title: {{display: true, text: 'BTC price'}}}}
    }},
    plugins: {{
      legend: {{display: true}}
    }}
  }};
  if (chart) chart.destroy();
  chart = new Chart(ctx, {{type: 'line', data, options}});
}}
document.querySelectorAll('.range-buttons button').forEach(button => {{
  button.addEventListener('click', () => {{
    document.querySelectorAll('.range-buttons button').forEach(b => b.classList.remove('active'));
    button.classList.add('active');
    render(button.dataset.range);
  }});
}});
render('all');
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
    """Build ``docs/index.html`` and mirrored ``outputs/dashboard.html``."""
    paths = _paths(output_root)
    generated_at = datetime.now(tz=UTC)
    try:
        data = fetch_all(use_cache=use_cache, cache_dir=cache_dir)
        latest, components, score, tiers = _latest_scores(data)
        html = _render_html(
            latest=latest,
            components=components,
            historical=_historical_points(data, components),
            markers=_cycle_markers(score),
            walk_forward_rows=_walk_forward_rows(tiers, data),
            indicator_rows=_indicator_rows(data),
            generated_at=generated_at,
        )
        paths.docs_index.parent.mkdir(parents=True, exist_ok=True)
        paths.outputs_dashboard.parent.mkdir(parents=True, exist_ok=True)
        paths.docs_index.write_text(html, encoding="utf-8")
        shutil.copyfile(paths.docs_index, paths.outputs_dashboard)
        _write_status(
            paths,
            {
                "last_run_utc": generated_at.isoformat().replace("+00:00", "Z"),
                "last_pi_score": latest.pi,
                "last_tier": latest.tier,
                "last_error": None,
            },
        )
    except Exception as exc:
        _write_status(
            paths,
            {
                "last_run_utc": generated_at.isoformat().replace("+00:00", "Z"),
                "last_pi_score": None,
                "last_tier": None,
                "last_error": str(exc),
            },
        )
        raise
    return paths


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the onchain-index dashboard.")
    parser.add_argument("--no-cache", action="store_true", help="Force fresh source fetches.")
    parser.add_argument("--open", action="store_true", help="Open docs/index.html after build.")
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
    print(f"wrote {paths.docs_index}")
    print(f"mirrored {paths.outputs_dashboard}")
    print(f"status {paths.status_json}")
    if args.open:
        webbrowser.open(paths.docs_index.resolve().as_uri())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
