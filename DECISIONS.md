# Decisions

## 2026-05-20 — Project bootstrapped as fresh repo, 4-phase plan

Reason: April 2026 prototype at `~/Projects/on-chain-index/` exists but is not git, follows a four-layer "reader-aid" pattern Martin no longer wants, and was never validated against PROJECT_SKELETON.md. Fresh repo is cheaper than retrofitting. Phases A (bootstrap) → B (indicator audit) → C (composite design) → D (optimize, conditional). Structure inherits MRMI-shaped logic from macro-framework but does NOT auto-inherit the binary in/out rule or the indicator slate — both must be validated empirically before locking. See `~/ops/tasks/task-18-onchain-pulse-index-bootstrap.md`.
