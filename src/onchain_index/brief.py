"""Generate and load the single on-chain dashboard brief."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from onchain_index.data import PROJECT_ROOT

BRIEFS_DIR = PROJECT_ROOT / "briefs"
BRIEF_FILENAME = "onchain.md"
MODEL = "sonnet"
SKIP_REFRESH_ENV = "ONCHAIN_INDEX_SKIP_BRIEF_REFRESH"

SYSTEM_PROMPT = """\
You are an on-chain analyst for Milk Road, a crypto publication.
Audience: smart colleagues and investors who want the dashboard call in plain English.
Style: concise, direct, plain English, no fluff. Write flowing prose only — no bullets.
Do not open with "In today's" or similar. Do not add a title.

Framework context: the core signal is the Bitcoin Demand Index. MROI is only
the internal technical handle for the same z-score series when a code-level
reference is needed. Production posture is binary: LONG means 100% long BTC
exposure, CASH means 0% long. The production rule is explicit: enter LONG only
when the Bitcoin Demand Index is strictly above the LONG threshold, exit to CASH
only when it is strictly below the CASH threshold, and otherwise hold the prior
posture. The Bitcoin Demand Index is currently driven by Holder Behavior only:
long-term on-chain holders, Strategy treasury accumulation, and spot ETF flows.
Valuation is not an allocation input. Do not discuss or mention the Valuation
lens in this brief; the dashboard can display valuation diagnostics elsewhere,
but this current read must ignore them unless Martin later asks. Do not invent
thresholds or extra model rules.

Required content: headline posture, current Bitcoin Demand Index value and trend
if available, what Holder Behavior says, the main reason for the current call,
and what would change the view next.
Length: 4–6 sentences.
"""

USER_TEMPLATE = """\
This on-chain dashboard brief is dated {date}.

Current readings:
{context}

Write one concise dashboard brief. Use the current readings only; do not invent
news or sources. Explain the posture, why the dashboard is there, and what
would change the view next. Write the brief only — no preamble.
"""


@dataclass(frozen=True)
class BriefContext:
    """Inputs passed from the dashboard renderer into the brief prompt."""

    date: str
    posture: str
    allocation_pct: float
    mroi: float
    mroi_7d_change: float | None
    valuation: float
    valuation_7d_change: float | None
    holder_behavior: float
    holder_behavior_7d_change: float | None
    signal_zone: str
    long_threshold: float
    cash_threshold: float
    valuation_constituents: Mapping[str, float | None]
    holder_cohorts: Mapping[str, float | None]


@dataclass(frozen=True)
class Brief:
    """A loaded dashboard brief."""

    html: str
    date: str
    stale: bool


def _fmt(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:+.2f}"


def _trend(delta: float | None) -> str:
    if delta is None:
        return "trend unavailable"
    if delta > 0.05:
        return f"improving over 7d ({delta:+.2f})"
    if delta < -0.05:
        return f"deteriorating over 7d ({delta:+.2f})"
    return f"little changed over 7d ({delta:+.2f})"


def _context_text(context: BriefContext) -> str:
    holder_lines = "\n".join(
        f"  - {name}: {_fmt(value)}" for name, value in context.holder_cohorts.items()
    )
    return "\n".join(
        [
            f"Date: {context.date}",
            f"Headline posture: {context.posture} ({context.allocation_pct:.0f}% long)",
            (
                f"Bitcoin Demand Index: {_fmt(context.mroi)} — "
                f"{context.signal_zone}; {_trend(context.mroi_7d_change)}"
            ),
            "Posture rule: "
            f"enter LONG only if Bitcoin Demand Index > {context.long_threshold:.2f}; "
            f"exit to CASH only if Bitcoin Demand Index < {context.cash_threshold:.2f}; "
            "otherwise hold prior posture.",
            (
                f"Holder Behavior: {_fmt(context.holder_behavior)} — production decision input; "
                f"{_trend(context.holder_behavior_7d_change)}"
            ),
            "Holder Behavior cohorts:",
            holder_lines or "  - unavailable",
        ]
    )


def _list_brief_dates(briefs_dir: Path = BRIEFS_DIR) -> list[date]:
    if not briefs_dir.exists():
        return []
    out = []
    for path in briefs_dir.iterdir():
        if not path.is_dir():
            continue
        try:
            out.append(datetime.strptime(path.name, "%Y-%m-%d").date())
        except ValueError:
            continue
    out.sort()
    return out


def latest_brief_dir(briefs_dir: Path = BRIEFS_DIR) -> Path | None:
    dates = _list_brief_dates(briefs_dir)
    if not dates:
        return None
    return briefs_dir / dates[-1].isoformat()


def _most_recent_monday(today: date) -> date:
    days_back = today.weekday() % 7
    return today - timedelta(days=days_back)


def _is_stale(briefs_dir: Path, today: date) -> bool:
    cutoff = _most_recent_monday(today)
    for brief_date in reversed(_list_brief_dates(briefs_dir)):
        if (briefs_dir / brief_date.isoformat() / BRIEF_FILENAME).exists():
            return brief_date < cutoff
    return True


def _archive_dir_for(context_date: str, briefs_dir: Path) -> Path:
    archive = briefs_dir / context_date
    archive.mkdir(parents=True, exist_ok=True)
    return archive


def _run_claude(prompt: str, timeout: int = 180) -> str | None:
    if not shutil.which("claude"):
        print("  On-chain brief: `claude` CLI not on PATH — skipping.")
        return None
    print("  On-chain brief: calling claude CLI...", end="", flush=True)
    try:
        result = subprocess.run(
            [
                "claude",
                "-p",
                prompt,
                "--model",
                MODEL,
                "--system-prompt",
                SYSTEM_PROMPT,
                "--no-session-persistence",
                "--disable-slash-commands",
                "--output-format",
                "text",
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        print(f" timed out after {timeout}s.")
        return None
    except OSError as exc:
        print(f" failed: {exc}")
        return None
    if result.returncode != 0:
        print(f" failed (exit {result.returncode}): {result.stderr.strip()[:200]}")
        return None
    body = result.stdout.strip()
    if not body:
        print(" no text in response.")
        return None
    print(" done.")
    return body


def generate_brief(
    context: BriefContext,
    *,
    briefs_dir: Path = BRIEFS_DIR,
    force: bool = False,
    today: date | None = None,
) -> bool:
    """Lazy-generate the weekly dashboard brief via the local Claude CLI."""
    today = today or date.today()
    if not force and not _is_stale(briefs_dir, today):
        print("  On-chain brief: fresh (this week's Monday) — skipping.")
        return True

    prompt = USER_TEMPLATE.format(date=context.date, context=_context_text(context))
    body = _run_claude(prompt)
    if not body:
        return False
    (_archive_dir_for(context.date, briefs_dir) / BRIEF_FILENAME).write_text(
        body + "\n", encoding="utf-8"
    )
    return True


def _md_to_html(text: str) -> str:
    out = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    out = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        r'<a href="\2" target="_blank" rel="noopener">\1</a>',
        out,
    )
    out = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"(?<![*])\*([^*\n]+)\*(?![*])", r"<em>\1</em>", out)
    paragraphs = [paragraph.strip() for paragraph in out.split("\n\n") if paragraph.strip()]
    return "".join(f"<p>{paragraph}</p>" for paragraph in paragraphs)


def load_latest_brief(
    *, context_date: str | None = None, briefs_dir: Path = BRIEFS_DIR
) -> Brief | None:
    """Load the most recent archived brief, if one exists."""
    latest_dir = latest_brief_dir(briefs_dir)
    if latest_dir is None:
        return None
    path = latest_dir / BRIEF_FILENAME
    if not path.exists():
        return None
    body = path.read_text(encoding="utf-8").strip()
    if not body:
        return None
    brief_date = latest_dir.name
    return Brief(
        html=_md_to_html(body),
        date=brief_date,
        stale=bool(context_date and brief_date < context_date),
    )


def refresh_or_load_brief(
    context: BriefContext,
    *,
    briefs_dir: Path = BRIEFS_DIR,
    force: bool = False,
    refresh: bool = True,
) -> Brief | None:
    """Refresh when possible, then return the latest cached brief."""
    if refresh and not os.environ.get(SKIP_REFRESH_ENV):
        try:
            generated = generate_brief(context, briefs_dir=briefs_dir, force=force)
        except Exception as exc:  # pragma: no cover - defensive build fallback
            generated = False
            print(f"  Warning: dashboard brief refresh failed: {exc}")
        if not generated:
            print("  Warning: using cached dashboard brief if available.")
    brief = load_latest_brief(context_date=context.date, briefs_dir=briefs_dir)
    if brief is None:
        print("  Warning: no cached dashboard brief available; dashboard brief block omitted.")
    return brief


def main() -> None:
    print("Use `python -m onchain_index.build` to generate the brief from current dashboard data.")


if __name__ == "__main__":
    main()
