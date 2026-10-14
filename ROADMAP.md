# Roadmap

[한국어](ROADMAP.ko.md) · [Current behavior](docs/VERIFIED-CHANGES.md)

Status: beta. Public development is consolidated on `main`. These priorities are planned work, not
available commands. The goal is useful, repeatable change verification; stars and test counts alone
do not establish adoption or reliability.

| Order | Outcome | Completion criteria |
| --- | --- | --- |
| P0 — next | Repair and reverify one existing-change request | Freeze case, criteria, baseline and requirement mapping. Reserve round/call/time/output/cost budgets before provider work; charge retries to the same request. Unknown spend or repeated failure stops new work. Independently verify the candidate and preserve interruption recovery; never change criteria to obtain `ready`. |
| P1 | Easier first-case preparation | Validate inputs, show exact files/commands/grants, produce a reviewable case and actionable errors. Require explicit execution approval. Prove a clean-install flow with a new user. |
| P1 | Common test reports | Add narrow Vitest/Jest adapters with fixed report provenance. Missing, malformed, zero-test, skipped or failing reports cannot pass. Verify real framework examples, not only synthetic JSON. |
| P2 | Real-project and host evidence | Test at least three representative repositories and multiple host environments with independent users. Publish sanitized reproducible cases, failures, time, cost and repair effectiveness. Lockfile-based dependency preparation requires explicit installation approval and provenance. |

Each item begins with a written behavior contract and failing acceptance test. Completion requires
unit/integration checks, relevant headless browser E2E, negative/interruption cases, regression checks,
package-install verification and fresh review of the actual diff. Repeated repairs use the same fixed
budget; a green unit suite alone does not close a product claim.

Current isolated acceptance covers a static Node fixture on macOS ARM64 with OrbStack Linux.
Real-framework portability, first-use success and independent review of the latest feature work remain
open. P0 must retain current safe apply/recovery and isolation behavior.

Public docs, runtime schema, synthetic test fixtures and README images stay versioned. Internal
design/review notes, launch drafts and raw execution evidence stay local and are excluded from Git
and distributions. `.gitignore` does not remove prior commits or guarantee secret removal.
