# Engineer progress — onchain-index

Append a structured entry at the bottom on every dispatch. Format:

```
## <UTC timestamp> — <short title>
- What: <1-2 line summary>
- Files touched: <list>
- Commit: <SHA or "none">
- Status: completed | partial | blocked
- Open thread for next dispatch: <if any, else "none">
```

Keep entries terse — this file is read by every stateless dispatch.

## 2026-05-20T11:48:23Z — Internal rename to onchain-index
- What: Renamed Python package/project metadata/docs from the Phase A inferred name to `onchain-index`; regenerated uv lock/sync under the new package name.
- Files touched: src/onchain_index/, pyproject.toml, uv.lock, tests/test_smoke.py, README.md, AGENTS.md, DECISIONS.md, docs/architecture.md, agent_docs/*.md, .env.example, .engineer/progress.md
- Commit: pending in this commit
- Status: completed
- Open thread for next dispatch: none

## 2026-05-20T11:55:20Z — Phase B standalone indicator audit
- What: Added reusable lagged binary-signal/backtest helpers, measured 13 standalone on-chain signals vs BTC buy-and-hold, and wrote ranked/cycle/correlation Phase B report.
- Files touched: src/onchain_index/backtest.py, tests/test_backtest.py, reports/phase-b-indicator-audit-2026-05-20.md, .engineer/progress.md
- Commit: pending in this commit
- Status: completed
- Open thread for next dispatch: Phase C should choose the composite slate from the report; funding rate/SOPR/exchange net flow remain source-expansion gaps.

## 2026-05-20T13:02:25Z — Phase C PI_score composite
- What: Built production PI_score composite, tiered sizing backtest, cycle walk-forward report, and lock-style composite tests; sign gate passed via HODL 1Y+ 30d-change z<0 as the only on-chain holder survivor.
- Files touched: src/onchain_index/composite.py, src/onchain_index/backtest.py, tests/test_composite.py, tests/test_backtest.py, reports/phase-c-composite-2026-05-20.md, .engineer/progress.md
- Commit: pending in this commit
- Status: completed
- Open thread for next dispatch: Phase C.5 dashboard surface; exchange-flow data remains missing and Coinbase Premium is not a valid substitute.

## 2026-05-21T08:50:26Z — Phase C.5 dashboard iteration surface
- What: Added `onchain_index.build` to refresh/cache data, render the single-page PI_score dashboard/iteration surface, mirror it to `outputs/dashboard.html`, and write `.cache/status.json`; added build smoke/status tests.
- Files touched: src/onchain_index/build.py, tests/test_build.py, docs/index.html, outputs/dashboard.html, .engineer/progress.md
- Commit: pending in this commit
- Status: completed
- Open thread for next dispatch: Review dashboard layout with Martin; launchd/cron wiring intentionally deferred.

## 2026-05-21T09:04:10Z — Phase C.5.1 LAN dashboard serve
- What: Added launchd LAN serve for outputs/dashboard.html on :8002, documented the port allocation/LAN URL, generated the MacBook webloc, loaded/smoke-tested the job, and placed fallback relay copies in ~/Public.
- Files touched: scripts/com.milkroad.onchain-index-serve.plist, AGENTS.md, agent_docs/repo_map.md, DECISIONS.md, .engineer/progress.md, /tmp/onchain-index-dashboard.webloc, ~/Public/onchain-index-dashboard.webloc
- Commit: pending in this commit
- Status: completed
- Open thread for next dispatch: none

## 2026-05-21T09:13:43Z — Phase D optimization research
- What: Added gated Phase D research optimizers, ran Step 1 cohort-weight walk-forward, stopped because optimized ratios underperformed equal-weight OOS; wrote the Phase D report.
- Files touched: src/onchain_index/research/, research/optimization/, tests/test_optimization.py, reports/phase-d-optimization-2026-05-21.md, .engineer/progress.md
- Commit: pending in this commit
- Status: completed
- Open thread for next dispatch: none — equal-weight production composite remains the recommendation; Step 2/3 were not reached on live data.

## 2026-05-21T10:04:35Z — Phase D structural audit
- What: Measured Valuation-vs-Holder dimension correlation and tiered null benchmarks; found moderate dimension overlap but full composite clears parsimony gaps vs STH/Valuation/Holder nulls.
- Files touched: reports/phase-d-audit-2026-05-21.md, .engineer/progress.md
- Commit: pending in this commit
- Status: completed
- Open thread for next dispatch: Dashboard/report wording should avoid claiming independent dimensions; consider adding rolling correlation panel after DAT concentration rebuild.

## 2026-05-21T10:22:14Z — Phase E exchange-flow gate stopped
- What: Found Coin Metrics Community as a free daily BTC exchange inflow/outflow source, ran the canonical 30d net-flow z-score tiered audit, and stopped because canonical exchange flow was negative in 2/4 cycles while the inverted sign also failed.
- Files touched: reports/phase-e-exchange-flow-2026-05-21.md, .engineer/progress.md
- Commit: pending in this commit
- Status: completed
- Open thread for next dispatch: Exchange-flow data availability is solved, but the locked Phase B/C rule fails; do not integrate without a new Martin-approved thesis/rule change.

## 2026-05-21T10:32:55Z — Framework honesty pass v0.4
- What: Removed Exchange Flow as a production holder cohort after the failed Phase E gate, softened Valuation/Holder framing to partially correlated complementary lenses, and surfaced holder-cohort concentration disclosures on the dashboard.
- Files touched: src/onchain_index/composite.py, src/onchain_index/build.py, tests/test_composite.py, docs/theory.md, docs/index.html, outputs/dashboard.html, reports/phase-e-exchange-flow-2026-05-21.md, .engineer/progress.md
- Commit: pending in this commit
- Status: completed
- Open thread for next dispatch: none

## 2026-05-21T10:48:15Z — Macro-family dashboard rebuild
- What: Rebuilt the onchain-index dashboard renderer/page around macro-framework's dark visual language, hero/scale-bar/pillar/chart/details skeleton, while preserving PI_score math and three holder cohorts.
- Files touched: src/onchain_index/build.py, docs/index.html, outputs/dashboard.html, .engineer/progress.md
- Commit: pending in this commit
- Status: completed
- Open thread for next dispatch: none

## 2026-05-21T10:56:45Z — Nightly dashboard refresh launchd wiring
- What: Added macro-pattern `scripts/refresh.sh`, weekday 22:30 Prague refresh plist, recovery runbook, launchd install/smoke verification, and docs/decision notes for onchain dashboard auto-refresh.
- Files touched: scripts/refresh.sh, scripts/com.milkroad.onchain-index-refresh-daily.plist, agent_docs/cron_failure_recovery.md, AGENTS.md, DECISIONS.md, docs/index.html, outputs/dashboard.html, .engineer/progress.md
- Commit: pending in this commit
- Status: completed
- Open thread for next dispatch: none

## 2026-05-21T11:23:00Z — Milk Road on-chain index UI pass
- What: Rebranded dashboard/docs to Milk Road on-chain index while keeping `PI_score`, added Valuation and Holder Behavior dimension charts, and added constituent driver fold-outs mirroring macro-framework's headline/drivers/backdrop pattern.
- Files touched: src/onchain_index/build.py, docs/index.html, outputs/dashboard.html, docs/theory.md, README.md, AGENTS.md, DECISIONS.md, .engineer/progress.md
- Commit: pending in this commit
- Status: completed
- Open thread for next dispatch: none

## 2026-05-21T11:35:03Z — Dashboard structural realignment
- What: Reworked the dashboard into the macro-framework three-section pattern: PI_score history/backtest, Valuation lens, and Holder Behavior lens; removed standalone pillar/sub-cohort card sections and factored shared Chart.js options for all charts.
- Files touched: src/onchain_index/build.py, docs/index.html, outputs/dashboard.html, .engineer/progress.md
- Commit: pending in this commit
- Status: completed
- Open thread for next dispatch: Martin review of the rebuilt structure; no macro-framework changes made.

## 2026-05-21T11:54:54Z — Phase F tier-structure parsimony audit
- What: Added fixed 2/3/4/5-tier PI_score comparison CLI, wrote structured JSON output, and reported that binary 2-tier beats the 4-tier baseline on OOS median alpha while 5-tier does not clear the +1pp bar.
- Files touched: src/onchain_index/research/optimization/optimize_tier_structure.py, tests/test_optimization.py, reports/phase-f-tier-structure-2026-05-21.md, .engineer/progress.md
- Commit: pending in this commit
- Status: completed
- Open thread for next dispatch: Production tier simplification decision remains separate; no dashboard/composite change made.

## 2026-05-21T12:07:56Z — Binary MRMI-shape tier rule
- What: Simplified production PI_score interpretation from the former 4-tier sizing map to MRMI-shaped CASH / STAY LONG at zero; rebuilt dashboard, v0.5 theory, decisions, tests, and Phase F addendum.
- Files touched: src/onchain_index/composite.py, src/onchain_index/build.py, src/onchain_index/research/optimization/common.py, src/onchain_index/research/optimization/optimize_tier_structure.py, tests/test_*.py, docs/theory.md, docs/index.html, outputs/dashboard.html, reports/phase-f-tier-structure-2026-05-21.md, DECISIONS.md, .engineer/progress.md
- Commit: pending in this commit
- Status: completed
- Open thread for next dispatch: none

## 2026-05-21T12:24:12Z — Macro-style chart pass
- What: Updated all onchain dashboard canvases to use one macro-framework-style Chart.js options path, switched range tabs to 1Y/2Y/5Y/ALL, removed PI_score cycle-reference markers and decision-rule explainer clutter while preserving green/red regime shading.
- Files touched: src/onchain_index/build.py, docs/index.html, outputs/dashboard.html, .engineer/progress.md
- Commit: pending in this commit
- Status: completed
- Open thread for next dispatch: none

## 2026-05-21T12:36:30Z — Task 29 MROI rename and global chart range
- What: Renamed PI_score/pi_score to MROI/mroi, removed hardcoded chart y-axis bounds, and made one global 1Y/3Y/5Y/ALL range selector drive main, dimension, and drill-down charts.
- Files touched: src/onchain_index/composite.py, src/onchain_index/build.py, src/onchain_index/research/optimization/*.py, tests/test_*.py, docs/theory.md, docs/index.html, outputs/dashboard.html, README.md, AGENTS.md, DECISIONS.md, reports/phase-{c,d,f}-*.md, .engineer/progress.md
- Commit: pending in this commit
- Status: completed
- Open thread for next dispatch: none

## 2026-05-27T11:17:27Z — Docs LAN serve on 8012
- What: Added a launchd docs server for `docs/index.html` on port 8012, installed/loaded the LaunchAgent, and smoke-tested the local docs URL with HTTP 200.
- Files touched: scripts/com.milkroad.onchain-index-docs-serve.plist, AGENTS.md, .engineer/progress.md
- Commit: pending in this commit
- Status: completed
- Open thread for next dispatch: none

## 2026-05-27T11:45:53Z — Task 58a iteration surface
- What: Replaced the docs/dashboard duplicate with a generated iteration surface for MROI construction, data sources, backtest params, architecture flow, and status; dashboard output remains in outputs/dashboard.html.
- Files touched: src/onchain_index/build_index_page.py, src/onchain_index/build.py, src/onchain_index/composite.py, src/onchain_index/data.py, scripts/refresh.sh, tests/test_build.py, docs/index.html, .engineer/progress.md
- Commit: pending in this commit
- Status: completed
- Open thread for next dispatch: none

## 2026-05-27T13:12:42Z — Task 62c weekly Claude cost placeholder
- What: Confirmed no Claude API call sites, added `onchain_index.cost` with Anthropic price constants and an empty estimate list, and rendered the iteration-surface weekly Claude spend card at $0.00/week with a Phase C placeholder note.
- Files touched: src/onchain_index/cost.py, src/onchain_index/build_index_page.py, tests/test_build.py, docs/index.html, .engineer/progress.md
- Commit: pending in this commit
- Status: completed
- Open thread for next dispatch: none

## 2026-05-28T11:51:28Z — Phase G asymmetric override audit
- What: Added the Phase G valuation-override research script, generated `.cache/optim/phase_g.json`, and wrote the asymmetric-override report; additive baseline won OOS and recommendation is keep-additive.
- Files touched: src/onchain_index/research/optimization/phase_g_asymmetric_override.py, reports/phase-g-asymmetric-override-2026-05-28.md, .engineer/progress.md
- Commit: pending in this commit
- Status: completed
- Open thread for next dispatch: Martin review of the Phase G report; no production MROI/dashboard changes made.

## 2026-05-28T12:08:56Z — Phase H spine-candidate audit
- What: Added research-only Yahoo BTC/equity close helper, evaluated holder-only and BTC/equity relative-strength spines with T=2 valuation override, and wrote the Phase H report; best spine was H1 at +8.0% OOS, below additive +18.1%.
- Files touched: pyproject.toml, uv.lock, src/onchain_index/research/equity_data.py, src/onchain_index/research/optimization/phase_h_spine_candidates.py, reports/phase-h-spine-candidates-2026-05-28.md, .engineer/progress.md
- Commit: pending in this commit
- Status: completed
- Open thread for next dispatch: Martin review of the Phase H keep-additive recommendation; no production MROI/dashboard changes made.

## 2026-05-28T12:23:01Z — Phase I blended-spine audit
- What: Added Phase I blended BTC/equity spine research script, generated `.cache/optim/phase_i.json`, and wrote the report; no candidate cleared the +19.1% switch hurdle, with I4 best at +10.7% OOS, so recommendation is keep-additive.
- Files touched: src/onchain_index/research/equity_data.py, src/onchain_index/research/optimization/phase_i_blended_spines.py, reports/phase-i-blended-spines-2026-05-28.md, .engineer/progress.md
- Commit: pending in this commit
- Status: completed
- Open thread for next dispatch: docs/theory honesty update should frame MROI as empirical-first additive evidence rather than an MRMI-shaped spine+modifier system.

## 2026-05-28T12:38:38Z — Phase J duration-magnitude audit
- What: Added research-only Phase J BTC/NASDAQ duration×magnitude spines, generated `.cache/optim/phase_j.json`, and wrote the final report; all six variants lost to additive by 5+pp, so recommendation is architecture-search exhausted and docs/theory honesty update next.
- Files touched: src/onchain_index/research/equity_data.py, src/onchain_index/research/optimization/phase_j_duration_magnitude.py, reports/phase-j-duration-magnitude-2026-05-28.md, .engineer/progress.md
- Commit: pending in this commit
- Status: completed
- Open thread for next dispatch: docs/theory honesty update should state MROI is empirical-first additive evidence after Phase G/H/I/J spine/override searches failed OOS.
