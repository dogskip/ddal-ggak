# Evidence catalogs and claim gates

These public JSON catalogs are inputs to `ddk proof` and `ddk audit`. They map declared
capabilities/standards to repository-relative files; a path match is not behavioral proof,
certification or comparative superiority.

| File | Role |
| --- | --- |
| `capability-matrix.json` | Capability families and expected evidence paths |
| `gsd-baseline.json` | Uncalibrated comparison template (`calibrated: false`) |
| `standards-catalog.json` | Declared clause-to-artifact mappings |
| `comparative-scorecard.json` | Optional measured comparison, not shipped |
| `compliance-matrix.json` | Local generated output of `ddk audit --write`, ignored by Git |

Some expected evidence paths refer to optional local internal documents under `docs/design/`.
Those documents are intentionally absent from the public checkout and distributions. Their absence
must appear as a gap or denied claim; do not create placeholders or substitute unrelated public docs
to turn a result green. `ddk proof` currently checks two such files for the identity gate, so identity
is also denied on a clean public checkout. Normal reporting still works; strict mode may exit 1.

The [repository reproduction suite](REPRODUCTION.md) separately exercises Python, JavaScript and
browser fixtures through real native tests, headless observation, replay and current-source gates.
Its expected failures are acceptance counterexamples, not a comparative score or model repair rate.

## Run the checks

```bash
ddk proof --json
ddk proof --strict
ddk audit
ddk audit --write
ddk audit --strict
```

Proof resolves paths into `mapped`, `partial` or `pending`. The current implementation has no
validated behavior-receipt ingestion path, so parity, superset and superiority remain denied even
when every path resolves. A calibrated baseline or comparative file alone cannot authorize them.
`ddk audit` reports declared clause-mapping coverage, never standards conformance.

## Comparative preparation and remaining evidence

Before enabling comparative claims, define a fixed reference corpus and protocol, pin both tool
revisions, record equivalent inputs/environment/criteria, and preserve successes, failures, elapsed
time and cost. Add a receipt contract with freshness and integrity validation, then independently
review the measured category-bounded comparison. Set `calibrated: true` only after that protocol
passes. The [paired protocol](PAIRING.md), fixed upstream corpus, preparation/oracle runner and `ddk bench`
receipt checks are implemented. Paid model comparisons and independent review remain unexecuted;
review-to-calibration ingestion is not implemented. See the [roadmap](../ROADMAP.md).

Add a capability with real evidence paths and rerun proof. Let the resolver report missing evidence;
never hand-edit a computed state or treat a synthetic test count as proof of product value.
