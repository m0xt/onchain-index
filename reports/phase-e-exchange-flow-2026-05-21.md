# Phase E exchange-flow source audit — 2026-05-21

**Gate result:** STOP before production integration. Coin Metrics Community now exposes free daily BTC exchange inflow/outflow series, but the canonical exchange-flow rule failed the Phase B-style standalone gate: negative alpha in 2 of 4 cycles. The inverted sign was also negative in 4 of 4 cycles. Per the dispatch constraint, exchange flow stays out of the production composite and the existing `exchange_flow = NaN` placeholder remains an honest gap.

## 1. Source discovery notes

| Source checked | Result | Endpoint / metric | Coverage / granularity | Friction / implications |
| --- | --- | --- | --- | --- |
| Bitcoin Magazine Pro (BMP) | Not viable for exchange flow | `GET https://api.bitcoinmagazinepro.com/metrics` under existing `BMP_API_KEY` returned 104 metrics. Search hits for `exchange`, `inflow`, `outflow`, `netflow`, `transfer`: none. Only `flow` hit was `stock-to-flow`. | N/A | Existing key works for current on-chain metrics, but BMP does not expose BTC exchange-flow metrics under this API catalog. |
| Glassnode free/basic API | Viable in principle, not lowest-friction here | Docs expose `GET https://api.glassnode.com/v1/metrics/transactions/transfers_volume_exchanges_net` and related inflow/outflow endpoints for BTC at `24h`, `1h`, `10m`; also `distribution/exchange_net_position_change`. | Daily/hourly/10m per docs; free tier is delayed, acceptable for backtests/nightly use. | Requires a Glassnode API key (`api_key` query auth). No `GLASSNODE_API_KEY` is present in this repo/ops secret state, so wiring it would create a new account/key dependency. |
| CryptoQuant | Skipped after lower-friction source found | Exchange Netflow (Total): inflow - outflow. | Daily/hourly product data. | Known/paywalled vendor path; no new paid data relationship without Martin/Bob approval. |
| Coin Metrics Community | **Used for audit; production integration rejected by signal gate** | `GET https://community-api.coinmetrics.io/v4/timeseries/asset-metrics?assets=btc&metrics=FlowInExNtv,FlowOutExNtv&frequency=1d&start_time=2011-04-24&page_size=10000`; compute `exchange_net_flow_btc = FlowInExNtv - FlowOutExNtv`. | Daily, `2011-04-24 → 2026-05-20` as of this run; latest row status timestamps around `2026-05-21 02:11 UTC`, so practical refresh latency is daily / roughly T+hours. | No API key required for these two aggregate exchange-flow native-BTC metrics. Community catalog marks daily `FlowInExNtv` and `FlowOutExNtv` as `community: true`. |

**Source choice:** Coin Metrics Community was the lowest-friction viable source for the Phase E standalone audit because BMP does not expose the series, Glassnode requires a new API key, CryptoQuant is a paid/vendor path, and Coin Metrics now provides aggregate exchange inflow/outflow in the public community API.

## 2. Standalone rule + Phase B-style alpha audit

Definition used exactly as requested:

```text
exchange_net_flow_btc = FlowInExNtv - FlowOutExNtv
signal_exchange_flow = -z(rolling_30d_sum(exchange_net_flow_btc))
```

Interpretation: positive net flow means BTC moving into exchanges (distribution / bearish), negative net flow means BTC leaving exchanges (accumulation / bullish), so the canonical signal is inverted so higher values are bullish.

Backtest convention:

- 504d trailing z-score via the existing `rolling_zscore` helper, lagged one day.
- 30d rolling net-flow sum before z-scoring.
- Production tier thresholds via `sizing_tier`: `<-1 Cash`, `[-1,0) Trim`, `[0,1) Sized`, `>=1 Strong`.
- Production allocation map: `0/50/75/100`.
- Same BTC cycle windows as Phase B/C.

| Rule | Full-sample alpha | 2014-2017 α | 2018-2021 α | 2022-2024 α | 2025-now α | Gate read |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Canonical `-z(rolling_30d_sum(net flow))` | **-23.8%** | **-35.3%** | +3.3% | **-10.1%** | +10.4% | **Fails**: negative in 2/4 cycles. |
| Inverted sign `+z(rolling_30d_sum(net flow))` | **-13.0%** | **-14.5%** | **-21.8%** | **-2.8%** | **-2.4%** | Also fails: negative in 4/4 cycles. |

Full canonical metrics: BTC B&H ann `+42.7%`, exchange-flow tier ann `+18.9%`, BTC DD `-84.5%`, strategy DD `-64.9%`, average allocation `58.4%`, tier transitions/year `27.0`.

## 3. Re-backtest deltas vs Phase C

Not run. The Phase 3 hard gate failed, so Phase 4 composite integration and Phase 5 full re-backtest were intentionally skipped.

Current Phase C production numbers therefore remain the latest production baseline:

| Metric | Phase C baseline | Phase E production change |
| --- | ---: | --- |
| Full-sample PI alpha | +13.1% | No change — exchange flow not integrated. |
| Cycle alphas | +11.0 / +14.1 / +17.0 / +13.2 | No change. |
| Drawdown | BTC `-84.5%`, PI `-64.5%` | No change. |
| Holder sub-cohort table | On-chain / DAT / ETF live; exchange flow `NaN` | No change; exchange-flow slot remains `NaN`. |

## 4. Honest read

Data availability is no longer the blocker: Coin Metrics Community can provide free daily BTC exchange inflow/outflow without a new key. The blocker is signal quality under the locked Phase B/C discipline. At the requested 30d rolling-sum / 504d z-score / production-tier horizon, exchange net flow is materially worse than BTC buy-and-hold full-sample and fails in more than one cycle. The inverted sign does not rescue it.

**Decision:** do not wire exchange flow into `holder_behavior_composite` or refresh the dashboard card as active data. The framework is stronger if the fourth slot remains an explicit gap/fail than if a bad constituent is forced into production.
