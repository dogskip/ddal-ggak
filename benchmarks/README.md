# Proof Program — executable Claim Gate

This directory is the **machine-readable source of truth** for ddalggak's
evidence-gated claims about GSD parity / superset / superiority.

It turns two strategy documents into running code:

- `docs/design/27-identity-positioning.md` — the Claim Gate rules
- `docs/design/28-gsd-superset-matrix.md` — the capability matrix

## Files

| File | Role |
| --- | --- |
| `capability-matrix.json` | Canonical map: each capability family + repo-relative artifact paths. Resolution establishes mapping only, not behavioral equivalence. |
| `gsd-baseline.json` | GSD benchmark baseline. Ships as an **uncalibrated template** (`calibrated: false`) so superiority claims are gated OFF until real measured data lands. |
| `comparative-scorecard.json` | *(absent by design)* The measured ddalggak-vs-GSD comparison. Required for any superiority claim. |
| `standards-catalog.json` | Curated internal map (ISO/IEC/IEEE 42010, ISO/IEC 25010:2023, 12207, NIST AI RMF) to declared design artifacts. |
| `compliance-matrix.json` | *(generated)* Output of `ddk audit --write` — the resolved clause coverage snapshot. |

## Run it

```bash
ddk proof            # human-readable matrix + claim verdicts + maturity level
ddk proof --json     # machine output (CI-friendly)
ddk proof --strict   # exit 1 if the superset claim is not allowed
```

`ddk proof` resolves every evidence path, computes each family's state
(`mapped` / `partial` / `pending`), and evaluates the Claim Gate:

| Claim | Allowed when… |
| --- | --- |
| `identity` | identity doc + PRD present |
| `parity` (per family) | artifacts map **and** a current behavior-verification receipt exists |
| `superset` | identity allowed **and** every `inherit`/`elevate` family proved |
| `superiority` | parity evidence **and** calibrated baseline **and** comparative artifact |

## Why superiority is denied today

By design. There is no calibrated `gsd-baseline.json` and no
`comparative-scorecard.json`, so the gate **refuses** every superiority claim —
exactly as `docs/design/27` requires ("baseline 없이 superiority claim 금지").

The current implementation intentionally has no receipt-ingestion path, so artifact
mapping alone can never authorize parity, superset, or superiority. This fail-closed
boundary prevents a file-presence check from masquerading as comparative proof.

## How to earn a superiority claim

1. Capture GSD baseline outcomes on the P0 reference corpus per
   `docs/design/26-benchmark-calibration-ops.md` and `17-benchmark-baseline.md`.
2. Define and implement a commit-pinned behavior-receipt schema with freshness and
   integrity validation.
3. Set `calibrated: true` only after the baseline protocol passes.
4. Produce `comparative-scorecard.json` (ddalggak vs GSD, category-bounded).
5. Extend the Claim Gate to accept only validated receipts; until then the claim
   remains denied.

## Standards compliance (`ddk audit`)

```bash
ddk audit            # clause → artifact coverage table + per-standard summary
ddk audit --write    # also emit benchmarks/compliance-matrix.json
ddk audit --strict   # exit 1 if any clause is a gap
```

`ddk audit` maps recognized standard clauses to declared design artifacts and reports
**clause-mapping coverage** — never a certification or conformance
claim (doc 27 §메시징 원칙). A clause is `mapped` only when its declared artifacts
resolve on disk; genuine gaps (e.g. a missing compatibility or AI-incident-response
doc) are surfaced as `gap`, not hidden. Edit `standards-catalog.json` to refine the
clause set as the design package evolves.

## Adding a capability family

Add a row to `capability-matrix.json` with real evidence paths, then run
`ddk proof`. If the artifacts resolve, the family becomes `mapped`. A behavior claim
must remain denied until a separately validated receipt mechanism exists. Never
hand-edit a status.
