# Decisions

## 2026-05-20 — Renamed `onchain‑pulse‑index` → `onchain-index`

Reason: Martin created the GitHub remote as `m0xt/onchain-index`; collision-prone with the archived `on-chain-index` prototype (one hyphen difference) but Martin accepted that trade-off; consistency with GitHub wins.

## 2026-05-20 — Project bootstrapped as fresh repo, 4-phase plan

Reason: April 2026 prototype at `~/Projects/on-chain-index-archive/` exists but is not git, follows a four-layer "reader-aid" pattern Martin no longer wants, and was never validated against PROJECT_SKELETON.md. Fresh repo is cheaper than retrofitting. Phases A (bootstrap) → B (indicator audit) → C (composite design) → D (optimize, conditional). Structure inherits MRMI-shaped logic from macro-framework but does NOT auto-inherit the binary in/out rule or the indicator slate — both must be validated empirically before locking. See `~/ops/tasks/task-18-onchain-index-bootstrap.md`.

## 2026-05-20 — Secret relocation created, git-crypt tracking blocked by ops state

Reason: Runtime secret file exists at `~/ops/secrets/onchain-index/.env`, but `~/ops/.gitignore` currently ignores `secrets/**` until git-crypt phase 2 and no `git-crypt` command/config is available in this environment. Do not commit the plaintext secret to force tracking; finish ops git-crypt setup separately.

## 2026-05-21 — LAN HTTP serve on :8002 + webloc shortcut shipped (Phase C.5.1)

Reason: Pattern mirrors macro-framework's :8001 setup; consolidated port allocation in repo_map.md.

## 2026-05-21 — Auto-refresh wired via launchd

Reason: Auto-refresh wired via launchd Mon–Fri 22:30 CEST, mirroring macro-framework's pattern. See `scripts/com.milkroad.onchain-index-refresh-daily.plist`.

## 2026-05-21 — Rebranded display name to "Milk Road on-chain index" (superseded)

Reason: Rebranded display name to "Milk Road on-chain index" for product-family consistency with Milk Road Macro Index. MROI remained the technical handle; no acronym (MROCI) was adopted. Superseded on 2026-05-29 by the Bitcoin Demand Index public signal name and Milk Road On-chain Dashboard container name.

## 2026-05-21 — Simplified to 2-tier binary (STAY LONG / CASH)

Reason: Simplified to 2-tier binary (STAY LONG / CASH) per task-26 walk-forward finding that 4-tier under-performed by 4.2pp OOS. MRMI-shape parity. Threshold at MROI = 0. See reports/phase-f-tier-structure-2026-05-21.md.

## 2026-05-21 — Adopted MROI technical handle

Reason: Adopted "MROI" as the technical-handle shorthand for the former Milk Road on-chain index score, now publicly named Bitcoin Demand Index. Reverses the earlier "no acronym" call from this morning's task-24; Martin's revised view after seeing 'PI_score' on the live dashboard was that the abstract variable name was confusing. Internal Python function renamed pi_score() → mroi() for consistency.

## 2026-05-28 — Switched MROI to P4 asymmetric holder-only architecture

Reason: Phase G–P research exhausted valuation overrides, BTC/equity spines, symmetric thresholds, confirmation rules, and CAUTION-tier variants. The validated winner was Phase P's P4 asymmetric binary state machine: `MROI = z(holder_behavior)` only; enter LONG when MROI > 0.0, exit CASH when MROI < -0.3, and hold the prior state in between. P4 improved OOS median cycle alpha to +24.2% versus the prior additive reference at +18.1% and reduced cadence to 13.8 switches/cycle versus 33.2. See reports/phase-g-asymmetric-override-2026-05-28.md through reports/phase-p-tier-confirmation-2026-05-28.md.

## 2026-05-29 — Renamed core signal to Bitcoin Demand Index

Reason: Martin chose “Bitcoin Demand Index” as the public name for the core signal/model. The broader page remains Milk Road On-chain Dashboard because future charts may cover other on-chain stats. `MROI` remains the internal technical handle and repo/package identifiers stay `onchain-index` for now.
