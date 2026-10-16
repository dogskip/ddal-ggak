# Roadmap

[한국어](ROADMAP.ko.md) · [Current commands](docs/ONECLICK.md)

Beta; public development uses `main`. Features and product effectiveness require different evidence.

| Priority | Status | Outcome and remaining acceptance |
| --- | --- | --- |
| P0: verified core | Implemented | Frozen criteria, one bounded repair budget, observed costs, independent checks, exact-state apply/recovery, explicit deletion authority and candidate-bound application. |
| P1: first case and one command | Implemented; broader usability evidence open | Hash-free `init`, `doctor`, Git snapshots, `up`, headless `probe`, strict MCP grants and rebuildable SQLite/FTS5. Missing request-specific acceptance remains blocked. Validate first-use success with independent users. |
| P1: native reports and policy | Implemented; framework matrix open | JUnit/pytest/Jest/Vitest/Playwright normalization, explicit skips, bounded policy checks and AX diagnostics. Expand real-framework/version fixtures without equating parser fixtures with framework support. |
| W1–W5: harness runtime | Implemented; measured adoption open | Unapproved discovery drafts, hash-linked diagnostic excerpts/retrieval, exact-error stall control, canonical current-source gates, opt-in Stop/pre-push checks, 16-table reconstruction, owned-copy receipts and offline evidence replay. |
| P2: reproduction | Fixed examples implemented; representative projects and users still open | [Python/JS/browser examples](benchmarks/REPRODUCTION.md) exercise host and Linux-container execution with correct and rejected changes. Retain source/environment hashes, elapsed time and observed model cost. Add three independently selected real projects, native Linux installation and first-time-user evidence before broader effectiveness claims. |
| P2: provider evidence | Planned | Evaluate paid-model repair quality with an approved fixed budget. Verify CLI tool isolation against recorded local transports and explicit billing evidence before CLI-backed calls can produce ready. |
| P3: dependency preparation | Planned | Explicitly approved lockfile-based preparation with provenance, no implicit dependency installation or lifecycle scripts. |

Each change starts with a behavior contract and failing acceptance cases. Completion requires relevant
unit/integration/headless/interruption/regression checks, strict typing, package installation and fresh
review. One passing suite is evidence for that revision and environment, not universal reliability.
Current evidence includes recorded proposals and local headless/isolated fixtures; it does not establish
paid-model effectiveness, independent adoption, superiority or a GitHub star target.

Canonical JSON remains authoritative. The SQLite catalog is fully derived; reconstruction compares
normalized rows, not physical database bytes. Unknown facts in older records remain null. Internal
plans/reviews, raw execution evidence and launch drafts stay local and are excluded from Git and
source distributions. Public user docs, runtime schemas, fixtures and README images remain versioned.
Ignore rules do not erase history or replace secret review.

Deferred until separate contracts and acceptance evidence exist: complete image-generation engine
unification, `ddk bench` with a calibrated corpus, automatic policy promotion, additional agent hooks
and mutable warm-container reuse. W1–W5 does not claim these features or unconditional latency,
compression savings, cache hit rates, GitHub stars or top-percentile rankings.
