#!/usr/bin/env python3
"""Render docs/index.html for onchain-index's Atlas.

The page imports production constants from the data, composite, backtest, and
build modules so docs/index.html stays a generated view of the current framework
inputs rather than a second hand-maintained spec.
"""

# ruff: noqa: E501

from __future__ import annotations

import argparse
import html
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from onchain_index.backtest import (
    BTC_CYCLES,
    DEFAULT_ZSCORE_WINDOW,
    PHASE_B_INDICATORS,
    TRADING_DAYS_PER_YEAR,
)
from onchain_index.build import (
    COHORT_LABELS,
    GITHUB_EDIT_BASE,
    INDICATOR_DECISIONS,
    PROJECT_REPO_URL,
    THEORY_VERSION,
    TIER_LABELS,
    TIER_SUBTITLES,
    VALUATION_LABELS,
)
from onchain_index.composite import (
    DAT_DELTA_DAYS,
    ETF_FLOW_SUM_DAYS,
    ETF_START,
    HODL_DELTA_DAYS,
    MROI_CASH_THRESHOLD,
    MROI_LONG_THRESHOLD,
    MSTR_START,
    TIER_ORDER,
    TIER_PCT,
    VALUATION_CONSTITUENTS,
)
from onchain_index.cost import COST_ESTIMATES, MODEL_PRICES_USD_PER_MTOK
from onchain_index.data import (
    BINANCE_KLINES_URL,
    BMP_BASE,
    BMP_METRICS,
    CACHE_MAX_AGE,
    COINBASE_CANDLES_URL,
    COINBASE_PREMIUM_START,
    DEFAULT_CACHE_DIR,
    FARSIDE_ETF_FLOW_URL,
    PROJECT_ROOT,
    RAW_CACHE_NAME,
    START_DATE,
    STRATEGY_TRACKER_MANIFEST_URL,
)

OUTPUT_FILE = PROJECT_ROOT / "docs" / "index.html"
STATUS_FILE = PROJECT_ROOT / ".cache" / "status.json"
PAGES_DASHBOARD = "dashboard.html"

SOURCE_COMPOSITE = "src/onchain_index/composite.py"
SOURCE_BUILD = "src/onchain_index/build.py"
SOURCE_DATA = "src/onchain_index/data.py"
SOURCE_COST = "src/onchain_index/cost.py"
SOURCE_BRIEF = "src/onchain_index/brief.py"
SOURCE_BACKTEST = "src/onchain_index/backtest.py"
SOURCE_REFRESH = "scripts/refresh.sh"
SOURCE_ARCHITECTURE = "docs/architecture.md"
SOURCE_THEORY = "docs/theory.md"
ANTHROPIC_PRICING_AS_OF = "2026-05-27"


CSS = """
  * { box-sizing: border-box; }
  :root {
    color-scheme: dark;
    --bg: #09090b;
    --panel: #111113;
    --panel-2: #17171a;
    --border: #2a2a2e;
    --text: #e4e4e7;
    --muted: #a1a1aa;
    --dim: #71717a;
    --code: #050506;
  }
  body {
    margin: 0;
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", Inter, system-ui, sans-serif;
    background:
      radial-gradient(circle at 18% 0%, rgba(34, 197, 94, 0.12), transparent 28rem),
      radial-gradient(circle at 92% 8%, rgba(245, 158, 11, 0.11), transparent 26rem),
      var(--bg);
    color: var(--text);
    line-height: 1.55;
  }
  main { max-width: 1180px; margin: 0 auto; padding: 40px 22px 64px; }
  header { margin-bottom: 28px; }
  .eyebrow {
    font-family: "SF Mono", ui-monospace, Menlo, Consolas, monospace;
    color: var(--dim);
    font-size: 12px;
    letter-spacing: 0.14em;
    text-transform: uppercase;
  }
  h1 { font-size: clamp(32px, 5vw, 58px); line-height: 1; margin: 10px 0 14px; letter-spacing: -0.04em; }
  h2 { margin: 0 0 8px; font-size: 23px; letter-spacing: -0.02em; }
  h2 span { font-size: 22px; }
  .intro { max-width: 820px; color: var(--muted); font-size: 16px; }
  .intro.small { max-width: 620px; font-size: 14px; margin: 0; }
  .meta { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 18px; }
  .meta.compact { margin: 0 0 16px; }
  .pill {
    border: 1px solid var(--border);
    background: rgba(255,255,255,0.03);
    color: var(--muted);
    border-radius: 999px;
    padding: 5px 10px;
    font-family: "SF Mono", ui-monospace, Menlo, Consolas, monospace;
    font-size: 12px;
  }
  .pill.schedule {
    border-color: rgba(245, 158, 11, 0.55);
    background: rgba(245, 158, 11, 0.14);
    color: #fde68a;
    font-weight: 700;
    letter-spacing: 0.02em;
  }
  .dashboard-cta {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    margin-top: 18px;
    border: 1px solid rgba(34, 197, 94, 0.65);
    background: rgba(34, 197, 94, 0.15);
    color: #bbf7d0;
    border-radius: 14px;
    padding: 11px 14px;
    font-weight: 800;
    text-decoration: none;
  }
  .dashboard-cta:hover { background: rgba(34, 197, 94, 0.22); }
  .status-strip { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin: 22px 0 28px; }
  .status-cell { border: 1px solid var(--border); border-radius: 14px; background: rgba(255,255,255,0.03); padding: 10px 12px; min-width: 0; }
  .status-label { color: var(--dim); font-size: 11px; text-transform: uppercase; letter-spacing: 0.1em; }
  .status-value { color: var(--text); font-family: "SF Mono", ui-monospace, Menlo, Consolas, monospace; font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .cards { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; align-items: start; }
  .card, .flow-card {
    border: 1px solid color-mix(in srgb, var(--accent, #38bdf8), var(--border) 66%);
    border-radius: 18px;
    background: linear-gradient(180deg, color-mix(in srgb, var(--accent, #38bdf8), transparent 90%), rgba(17,17,19,0.96));
    box-shadow: 0 20px 60px rgba(0,0,0,0.24);
    overflow: hidden;
  }
  .card.wide { grid-column: span 3; }
  .card-top { display: flex; justify-content: space-between; gap: 16px; padding: 20px; border-bottom: 1px solid rgba(255,255,255,0.07); }
  .card p { margin: 0; color: var(--muted); font-size: 14px; }
  .shortcut {
    flex: 0 0 auto;
    align-self: start;
    border: 1px solid color-mix(in srgb, var(--accent), white 10%);
    background: color-mix(in srgb, var(--accent), transparent 82%);
    color: var(--text);
    border-radius: 12px;
    padding: 8px 10px;
    font-family: "SF Mono", ui-monospace, Menlo, Consolas, monospace;
    font-weight: 800;
    font-size: 20px;
  }
  .suggest { display: block; padding: 12px 20px; color: var(--accent); text-decoration: none; font-size: 13px; border-bottom: 1px solid rgba(255,255,255,0.07); }
  .suggest:hover { background: rgba(255,255,255,0.035); }
  .card-body { padding: 18px 20px 20px; }
  .formula { padding: 14px; background: var(--code); border: 1px solid var(--border); border-radius: 12px; margin-bottom: 14px; }
  .metrics { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin-bottom: 12px; }
  .metric { border: 1px solid rgba(255,255,255,0.07); border-radius: 12px; background: rgba(0,0,0,0.18); padding: 12px; }
  .metric-label { color: var(--dim); font-size: 11px; text-transform: uppercase; letter-spacing: 0.1em; }
  .metric-value { font-family: "SF Mono", ui-monospace, Menlo, Consolas, monospace; font-size: 18px; font-weight: 800; }
  .metric-note, .hint { color: var(--dim); font-size: 13px; }
  details summary { cursor: pointer; user-select: none; font-weight: 700; color: var(--text); }
  details[open] > summary { color: var(--accent); }
  table { width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 13px; }
  th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid rgba(255,255,255,0.07); vertical-align: top; }
  th { color: var(--dim); font-size: 11px; letter-spacing: 0.1em; text-transform: uppercase; }
  code { font-family: "SF Mono", ui-monospace, Menlo, Consolas, monospace; font-size: 12px; line-height: 1.55; color: #d4d4d8; }
  .flow-card { --accent: #94a3b8; margin-bottom: 16px; padding: 20px; }
  .flow-suggest { margin: 14px -20px 16px; }
  .arch-row { display: flex; flex-wrap: wrap; align-items: stretch; gap: 12px; }
  .node { border: 1px solid var(--border); border-radius: 12px; padding: 12px; min-width: 180px; flex: 1; background: var(--panel-2); }
  .node .role { font-weight: 700; }
  .node .desc { color: var(--muted); font-size: 12px; margin-top: 4px; }
  footer { margin-top: 24px; color: var(--dim); font-size: 12px; }
  footer code { color: var(--muted); }
  @media (max-width: 940px) {
    .cards, .status-strip { grid-template-columns: 1fr; }
    .card.wide { grid-column: span 1; }
    .metrics { grid-template-columns: 1fr; }
  }
"""


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _run_git(args: list[str], cwd: Path) -> str | None:
    try:
        return subprocess.check_output(
            ["git", *args], cwd=cwd, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return None


def suggest_link(path: str) -> str:
    return f"{GITHUB_EDIT_BASE}/{path}"


def source_link(path: str, label: str | None = None) -> str:
    label = label or Path(path).name
    return (
        f'<a class="suggest" href="{esc(suggest_link(path))}" target="_blank" '
        f'rel="noreferrer">Suggest edit → {esc(label)}</a>'
    )


def pill(text: str) -> str:
    return f'<span class="pill">{esc(text)}</span>'


def schedule_pill(text: str) -> str:
    return f'<span class="pill schedule">{esc(text)}</span>'


def render_metric(label: str, value: str, note: str) -> str:
    return f"""
      <div class="metric">
        <div class="metric-label">{esc(label)}</div>
        <div class="metric-value">{esc(value)}</div>
        <div class="metric-note">{esc(note)}</div>
      </div>"""


def render_table(headers: list[str], rows: list[list[str]]) -> str:
    head = "".join(f"<th>{esc(header)}</th>" for header in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _estimate_float(row: dict[str, object], key: str) -> float:
    value = row[key]
    if isinstance(value, int | float | str):
        return float(value)
    raise TypeError(f"cost estimate {key} must be numeric")


def _cost_usd_per_week(row: dict[str, object]) -> float:
    model = str(row["model"])
    input_price, output_price = MODEL_PRICES_USD_PER_MTOK[model]
    calls = _estimate_float(row, "calls_per_week")
    tokens_in = _estimate_float(row, "tokens_in")
    tokens_out = _estimate_float(row, "tokens_out")
    return calls * ((tokens_in * input_price) + (tokens_out * output_price)) / 1_000_000


def _model_short_name(model: str) -> str:
    for name in ("haiku", "sonnet", "opus"):
        if name in model:
            return name.title()
    return model


def _load_status(output_root: Path) -> dict[str, str]:
    status_file = output_root / ".cache" / "status.json"
    if not status_file.exists():
        return {"last_run": "—", "status": "missing", "last_error": "status.json not found"}
    try:
        raw = json.loads(status_file.read_text())
    except json.JSONDecodeError as exc:
        return {"last_run": "—", "status": "invalid", "last_error": str(exc)}

    last_error = raw.get("last_error") or "none"
    tier = raw.get("last_tier") or "—"
    mroi = raw.get("last_mroi")
    if isinstance(mroi, int | float):
        summary = f"ok · {tier} · Bitcoin Demand Index {mroi:+.2f}"
    else:
        summary = "error" if raw.get("last_error") else f"ok · {tier}"
    return {
        "last_run": str(raw.get("last_run_utc") or "—"),
        "status": summary,
        "last_error": str(last_error),
    }


def _last_commit(output_root: Path) -> str:
    return _run_git(["rev-parse", "--short", "HEAD"], output_root) or "—"


def render_status_strip(output_root: Path) -> str:
    status = _load_status(output_root)
    cells = [
        ("Last run", status["last_run"]),
        ("Status", status["status"]),
        ("Last commit", _last_commit(output_root)),
        ("Last error", status["last_error"]),
    ]
    rendered = "".join(
        f'<div class="status-cell"><div class="status-label">{esc(label)}</div>'
        f'<div class="status-value" title="{esc(value)}">{esc(value)}</div></div>'
        for label, value in cells
    )
    return f'<section class="status-strip">{rendered}</section>'


def render_flow_card() -> str:
    nodes = [
        ("Fetch", "BMP, Farside, StrategyTracker, Coinbase, and Binance raw daily inputs."),
        ("Cache", f"Merge on the BMP daily spine and cache {RAW_CACHE_NAME} for 12 hours."),
        ("Compute", "Holder Behavior z-score → Bitcoin Demand Index; valuation remains diagnostic."),
        ("Backtest", "Cycle walk-forward checks use the same lagged production signal path."),
        ("Publish", "Write outputs/dashboard.html, docs/dashboard.html, docs/index.html, status JSON, then cron commit."),
    ]
    row = "".join(
        f'<div class="node"><div class="role">{esc(role)}</div>'
        f'<div class="desc">{esc(desc)}</div></div>'
        for role, desc in nodes
    )
    return f"""
      <section class="flow-card">
        <div>
          <div class="eyebrow">architecture / flow</div>
          <h2>What feeds what.</h2>
          <p class="intro small">A compact map of the pipeline. The narrative source stays in <code>{SOURCE_ARCHITECTURE}</code>; this page links it rather than replacing it.</p>
        </div>
        {source_link(SOURCE_ARCHITECTURE, "architecture.md")}
        <div class="arch-row">{row}</div>
      </section>"""


def render_composite_card() -> str:
    metrics = [
        render_metric("z-score window", f"{DEFAULT_ZSCORE_WINDOW}d", "Lagged trailing window."),
        render_metric("LONG threshold", f"{MROI_LONG_THRESHOLD:.1f}", "Strictly above this enters LONG."),
        render_metric("CASH threshold", f"{MROI_CASH_THRESHOLD:.1f}", "Strictly below this exits to CASH."),
        render_metric(
            "valuation diagnostics",
            str(len(VALUATION_CONSTITUENTS)),
            "Equal-weighted; not in the demand index.",
        ),
        render_metric("holder cohorts", str(len(COHORT_LABELS)), "Equal-weighted when live."),
    ]
    valuation_rows = [
        [f"<code>{esc(name)}</code>", esc(VALUATION_LABELS.get(name, name)), esc("equal weight")]
        for name in VALUATION_CONSTITUENTS
    ]
    cohort_rows = [
        [
            f"<code>{esc(key)}</code>",
            esc(label),
            esc(_cohort_start(key)),
            esc(_cohort_transform(key)),
        ]
        for key, label in COHORT_LABELS.items()
    ]
    return f"""
      <article class="card wide" style="--accent: #22c55e">
        <div class="card-top"><div><h2>Bitcoin Demand Index construction <span>🧮</span></h2><p>Production composite math imported from <code>{SOURCE_COMPOSITE}</code> and <code>{SOURCE_BACKTEST}</code>; <code>MROI</code> remains the internal technical handle.</p></div><div class="shortcut">BDI</div></div>
        {source_link(SOURCE_COMPOSITE, "composite.py")}
        <div class="card-body">
          <div class="formula"><code>Bitcoin Demand Index (MROI) = holder_behavior_composite
Posture = LONG if Bitcoin Demand Index &gt; {MROI_LONG_THRESHOLD:.1f}; CASH if Bitcoin Demand Index &lt; {MROI_CASH_THRESHOLD:.1f}; otherwise hold prior state</code></div>
          <div class="metrics">{''.join(metrics)}</div>
          <details open><summary>Valuation diagnostics (not used in decision)</summary>{render_table(["Key", "Label", "Weight"], valuation_rows)}</details>
          <details open><summary>Holder-behavior cohorts</summary>{render_table(["Key", "Label", "Coverage", "Transform"], cohort_rows)}</details>
          <p class="hint">All z-scores are lagged by <code>rolling_zscore</code>, so a score dated T uses values available through T-1.</p>
        </div>
      </article>"""


def _cohort_start(key: str) -> str:
    if key == "on_chain":
        return f"{START_DATE} onward"
    if key == "corporate_dat":
        return f"{MSTR_START.date()} onward"
    if key == "institutional_etf":
        return f"{ETF_START.date()} onward"
    return "when available"


def _cohort_transform(key: str) -> str:
    if key == "on_chain":
        return f"-{HODL_DELTA_DAYS}d HODL 1Y+ change z-score"
    if key == "corporate_dat":
        return f"{DAT_DELTA_DAYS}d Strategy BTC-holdings change z-score"
    if key == "institutional_etf":
        return f"{ETF_FLOW_SUM_DAYS}d spot ETF net-flow sum z-score"
    return "production cohort series"


def render_decision_card() -> str:
    rows = [
        [esc(TIER_LABELS[tier]), esc(f"{TIER_PCT[tier]:.0f}%"), esc(TIER_SUBTITLES[tier])]
        for tier in TIER_ORDER
    ]
    decisions = [
        [esc(name), esc(group), esc(status), esc(reason)]
        for name, (group, status, reason) in INDICATOR_DECISIONS.items()
    ]
    return f"""
      <article class="card" style="--accent: #38bdf8">
        <div class="card-top"><div><h2>Decision rule <span>🚦</span></h2><p>Plain LONG/CASH posture thresholds imported from production constants.</p></div><div class="shortcut">R</div></div>
        {source_link(SOURCE_BUILD, "build.py")}
        <div class="card-body">
          {render_table(["Tier", "Allocation", "Meaning"], rows)}
          <p class="hint">Rule: <code>Bitcoin Demand Index &gt; {MROI_LONG_THRESHOLD:.1f}</code> → LONG; <code>Bitcoin Demand Index &lt; {MROI_CASH_THRESHOLD:.1f}</code> → CASH; otherwise HOLD current state. Theory doc version <code>{THEORY_VERSION}</code>.</p>
          <details><summary>Indicator inclusion decisions</summary>{render_table(["Indicator", "Group", "Status", "Reason"], decisions)}</details>
        </div>
      </article>"""


def render_data_card() -> str:
    source_rows = [
        ["Bitcoin Magazine Pro", esc(BMP_BASE), esc(f"metrics from {START_DATE}")],
        ["Farside", esc(FARSIDE_ETF_FLOW_URL), "spot BTC ETF net flows"],
        ["StrategyTracker", esc(STRATEGY_TRACKER_MANIFEST_URL), "MSTR BTC holdings"],
        ["Coinbase", esc(COINBASE_CANDLES_URL), esc(f"premium leg from {COINBASE_PREMIUM_START.date()}")],
        ["Binance", esc(BINANCE_KLINES_URL), "BTCUSDT comparison leg"],
    ]
    metric_rows = [
        [f"<code>{esc(metric)}</code>", esc(", ".join(columns.values()))]
        for metric, columns in BMP_METRICS.items()
    ]
    cache_hours = CACHE_MAX_AGE.total_seconds() / 3600
    return f"""
      <article class="card" style="--accent: #f59e0b">
        <div class="card-top"><div><h2>Data sources <span>🔌</span></h2><p>Source contracts and cache cadence imported from <code>{SOURCE_DATA}</code>.</p></div><div class="shortcut">D</div></div>
        {source_link(SOURCE_DATA, "data.py")}
        <div class="card-body">
          <div class="meta compact">{pill(f"cache: {DEFAULT_CACHE_DIR.name}/{RAW_CACHE_NAME}")}{pill(f"max age: {cache_hours:.0f}h")}</div>
          {render_table(["Source", "Endpoint", "Role"], source_rows)}
          <details><summary>BMP metric column map</summary>{render_table(["Metric", "Local columns"], metric_rows)}</details>
        </div>
      </article>"""


def render_brief_card() -> str:
    rows = [
        ["Prompt source", f"<code>{SOURCE_BRIEF}</code>", "One concise on-chain read generated from current dashboard values."],
        ["Cadence", "Weekly lazy refresh", "Regenerates once the latest cached brief is older than Tuesday; normal builds reuse cache."],
        ["Archive", "<code>briefs/YYYY-MM-DD/onchain.md</code>", "Durable markdown brief loaded into outputs/dashboard.html and docs/dashboard.html."],
        ["Failure mode", "Graceful fallback", "If Claude CLI is unavailable or fails, use the latest cached brief; otherwise omit the block."],
    ]
    return f"""
      <article class="card" style="--accent: #cdaa6a">
        <div class="card-top"><div><h2>Generated brief <span>✍️</span></h2><p>The dashboard has one Claude CLI-generated read, not separate market/economy/top briefs.</p></div><div class="shortcut">1</div></div>
        {source_link(SOURCE_BRIEF, "brief.py")}
        <div class="card-body">
          {render_table(["Input", "Setting", "Source / behavior"], rows)}
          <p class="hint">Prompt scope: headline posture, Bitcoin Demand Index/trend, Holder Behavior, main reason for the call, and what changes the view next; valuation diagnostics stay out of the generated brief.</p>
        </div>
      </article>"""


def render_cost_card() -> str:
    rows = []
    total = 0.0
    for estimate in COST_ESTIMATES:
        weekly_cost = _cost_usd_per_week(estimate)
        total += weekly_cost
        model = str(estimate["model"])
        rows.append(
            [
                f'<code>{esc(estimate["site"])}</code>',
                esc(_model_short_name(model)),
                esc(f'{_estimate_float(estimate, "calls_per_week"):,.0f}'),
                esc(f'{_estimate_float(estimate, "tokens_in"):,.0f}'),
                esc(f'{_estimate_float(estimate, "tokens_out"):,.0f}'),
                esc(f'${weekly_cost:,.2f}'),
            ]
        )

    if rows:
        table = render_table(
            ["Site", "Model", "Calls / week", "Est in", "Est out", "Est $ / week"],
            rows,
        )
        body_note = ""
    else:
        table = ""
        body_note = '<p class="hint">Phase A has no Claude call sites, so the estimate is zero. Phase C composite-design will populate <code>cost.py</code> when Claude calls land.</p>'

    return f"""
      <article class="card wide" style="--accent: #06b6d4">
        <div class="card-top"><div><h2>Estimated weekly Claude spend <span>💸</span></h2><p>Static token estimate for Anthropic API usage imported from <code>{SOURCE_COST}</code>.</p></div><div class="shortcut">${total:,.2f} / week</div></div>
        {source_link(SOURCE_COST, "cost.py")}
        <div class="card-body">
          <div class="metrics">
            {render_metric("weekly estimate", f"${total:,.2f} / week", "Anthropic API costs only.")}
            {render_metric("Claude call sites", str(len(COST_ESTIMATES)), "Enumerated in cost.py.")}
          </div>
          {table}
          {body_note}
          <p class="hint">Prices from Anthropic public pricing as of {ANTHROPIC_PRICING_AS_OF}. Token counts are hand-tuned estimates, not metered usage.</p>
        </div>
      </article>"""


def render_backtest_card() -> str:
    cycle_rows = [
        [esc(name), esc(start), esc(end)] for name, (start, end) in BTC_CYCLES.items()
    ]
    indicator_rows = [
        [esc(spec.name), esc(spec.rule), esc(", ".join(spec.source_columns))]
        for spec in PHASE_B_INDICATORS
    ]
    return f"""
      <article class="card" style="--accent: #a78bfa">
        <div class="card-top"><div><h2>Backtest parameters <span>📊</span></h2><p>Walk-forward constants and standalone signal specs imported from <code>{SOURCE_BACKTEST}</code>.</p></div><div class="shortcut">B</div></div>
        {source_link(SOURCE_BACKTEST, "backtest.py")}
        <div class="card-body">
          <div class="metrics">
            {render_metric("trading days / year", str(TRADING_DAYS_PER_YEAR), "Annualization constant.")}
            {render_metric("default z-window", f"{DEFAULT_ZSCORE_WINDOW}d", "Signal normalization window.")}
          </div>
          <details open><summary>BTC cycle splits</summary>{render_table(["Cycle", "Start", "End"], cycle_rows)}</details>
          <details><summary>Standalone Phase B indicator specs</summary>{render_table(["Indicator", "Rule", "Columns"], indicator_rows)}</details>
        </div>
      </article>"""


def render_docs_card() -> str:
    return f"""
      <article class="card wide" style="--accent: #ef4444">
        <div class="card-top"><div><h2>Human-editable source docs <span>📝</span></h2><p>The theory and refresh script are part of the iterable surface, but this page does not copy their prose.</p></div><div class="shortcut">S</div></div>
        {source_link(SOURCE_THEORY, "theory.md")}
        <div class="card-body">
          <div class="meta compact">
            {pill(f"repo: {PROJECT_REPO_URL}")}
            {pill(f"theory: {THEORY_VERSION}")}
            {pill("docs port: 8012")}
          </div>
          {render_table(["Artifact", "Why it matters", "Edit"], [
              [esc(SOURCE_THEORY), "Framework rationale and resolved decisions.", f'<a href="{esc(suggest_link(SOURCE_THEORY))}">edit</a>'],
              [esc(SOURCE_ARCHITECTURE), "Pipeline narrative and source-failure posture.", f'<a href="{esc(suggest_link(SOURCE_ARCHITECTURE))}">edit</a>'],
              [esc(SOURCE_REFRESH), "Nightly regeneration and commit wiring.", f'<a href="{esc(suggest_link(SOURCE_REFRESH))}">edit</a>'],
          ])}
        </div>
      </article>"""


def render_html(*, output_root: Path = PROJECT_ROOT) -> str:
    generated_at = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M UTC")
    meta = "".join(
        [
            schedule_pill("schedule: Mon–Fri 22:30 Prague"),
            pill("feedback: composite"),
            pill("feedback: sources"),
            pill("feedback: backtests"),
            pill("feedback: architecture"),
            pill(f"built {generated_at}"),
        ]
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>On-chain Dashboard Atlas</title>
<style>{CSS}</style>
</head>
<body>
<main>
  <header>
    <div class="eyebrow">onchain-index / atlas</div>
    <h1>Inputs to challenge.</h1>
    <p class="intro">A static, regenerated view of Milk Road On-chain Dashboard's iterable inputs: Bitcoin Demand Index construction, source contracts, backtest assumptions, architecture flow, and status. Values below are imported from production code at build time.</p>
    <div class="meta">{meta}</div>
    <a class="dashboard-cta" href="{PAGES_DASHBOARD}">Open shareable full dashboard →</a>
  </header>

  {render_status_strip(output_root)}
  {render_flow_card()}

  <section class="cards">
    {render_composite_card()}
    {render_decision_card()}
    {render_data_card()}
    {render_backtest_card()}
    {render_brief_card()}
    {render_cost_card()}
    {render_docs_card()}
  </section>

  <footer>
    Generated by <code>python -m onchain_index.build_index_page</code>. Full Pages dashboard copy: <code>docs/{PAGES_DASHBOARD}</code>; source dashboard remains <code>outputs/dashboard.html</code>.
  </footer>
</main>
</body>
</html>
"""


def build_index_page(*, output_root: Path = PROJECT_ROOT) -> Path:
    output_file = output_root / "docs" / "index.html"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    rendered = render_html(output_root=output_root)
    rendered = "\n".join(line.rstrip() for line in rendered.splitlines()) + "\n"
    output_file.write_text(rendered, encoding="utf-8")
    return output_file


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the onchain-index Atlas.")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=PROJECT_ROOT,
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args(argv)
    path = build_index_page(output_root=args.output_root)
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
