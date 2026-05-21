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
