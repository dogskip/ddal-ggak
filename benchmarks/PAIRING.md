# Paired comparison protocol

This program prepares inputs and validates recorded comparisons. It does not call a model,
authorize spending, certify a host transcript, or publish results. `calibrated` remains false.
The existing [synthetic reproduction suite](REPRODUCTION.md) is a separate acceptance check.

## Fixed corpus

The [canonical corpus](../src/ddk/assets/benchmarks/paired-corpus.json) pins three upstream sources.
These are controlled regressions introduced into real source, selected for small reproducible
interfaces. They are not naturally discovered upstream bugs or a representative project sample.

| Source | Commit | Controlled task |
| --- | --- | --- |
| [Click 8.3.0](https://github.com/pallets/click/tree/00fadb8904387158ce6e9aa1573be770446895c1) | `00fadb8904387158ce6e9aa1573be770446895c1` | Restore basename formatting; preserve full paths and invalid-byte handling |
| [clsx 2.1.1](https://github.com/lukeed/clsx/tree/925494cf31bcd97d3337aacd34e659e80cae7fe2) | `925494cf31bcd97d3337aacd34e659e80cae7fe2` | Restore truthy object flags; preserve nested arrays and falsy omission |
| [Hyperapp 2.0.22](https://github.com/hyperapp/hyperapp/tree/876d3f44d0ae601de181714c583a07d83d3472c9) | `876d3f44d0ae601de181714c583a07d83d3472c9` | Restore event registration; preserve initial rendering and reset |

Each task has three trial labels (1729, 2718, 3141), two arms and a byte-identical initial source
per pair: 18 episodes. A label is not evidence that a host supports deterministic sampling.
Pin the actual sampling configuration and record unsupported seed controls.

## Preparation and approval

Fetch the pinned public tags into private local clones. Preparation accepts existing clones and
uses the existing Git snapshot/materialization code. It checks the commit, target-file hash and
unique mutation position, creates independent `bench-source` Git repositories, and records initial
hashes and exact request hashes. It never fetches dependencies or invokes a model.

```sh
uv run python scripts/paired_benchmark.py prepare \
  --source click=/tmp/ddk-upstreams/click \
  --source clsx=/tmp/ddk-upstreams/clsx \
  --source hyperapp=/tmp/ddk-upstreams/hyperapp \
  --out /tmp/ddk-paired
```

The destination must be new; an unsuccessful attempt is retained. `preparation.json` explicitly
requires criteria approval. Before a model episode, an owner must approve the target/preservation
criteria, fixed Case hashes, host/model revision, token/deadline limits and a total spend ceiling.
For command-only projects, use the explicit [Case contract](../src/ddk/assets/verified-change/contract.schema.json);
the current browser-oriented bootstrap does not automatically compile these three native cases.
Preparation does not grant `trusted-local` execution or provider permission.

## Matched execution

Use the same host/version, exact model revision, sampling settings, base instructions, request,
initial source, environment, token limits, deadline and spend ceiling. The allowed difference is
DDK gate access/feedback. Ordinary host test tools remain identical. Pin the DDK commit and
oracle program SHA. The three canonical skills are not additional experimental treatments.

Counterbalance arm order by trial, use a fresh host session and independent work directory for
every episode, and preserve the session ID. Do not transfer repair advice or results between arms.
Store host observations, actual usage and session artifacts outside the agent-editable candidate.
Preserve all failures, timeouts, cancellations, blocked decisions and exhausted limits. No retry
may silently replace an earlier observation.

A host spend cap must be verified before any paid invocation. This receipt reader cannot enforce
an external coding host's spending. Unknown charges remain null; a free local model needs an
explicit zero-price basis, not missing usage. Infrastructure and human time are not model API cost.

## Independent observations

The frozen oracle checks real upstream code outside the candidate's test files. Python and Node
workers have bounded output, a deadline, owned-process cleanup and a restricted environment.
Hyperapp uses a fresh headless Chromium with its sandbox enabled and external requests aborted.
Execution is explicitly `trusted-local`; Python/Node project code has host permissions and no OS
isolation. It is suitable only for approved trusted sources and candidate changes.

```sh
uv run python scripts/paired_benchmark.py oracle \
  --task hyperapp-events --repo /tmp/ddk-paired/hyperapp-events/1729/ddk \
  --seed 1729 --arm ddk --trusted-local --out /tmp/hyperapp-observation.json
```

The oracle retains target, preservation and additional behavior checks through three test counts,
the actual candidate hash, duration and oracle SHA. Failed assertions exit 1. Execution failure
cannot become a passing zero-test report. Source changes during observation are rejected. Run it
after each arm; keep its actual process exit independently of the JSON contents.

DDK-arm records additionally require a complete canonical Run, matching candidate/Case hashes,
valid evidence and a matching Run SHA. A frozen gate result and the independent oracle remain
separate observations; `ready` plus failed independent checks is a false acceptance.

## Receipt contract

`ddk.services.paired_benchmark` defines strict `Cohort`, `HostRecord`, `Observation`, `OracleReport`
and `Receipts` models. A `ddk-paired-receipts/1` record contains the corpus hash, declared provenance,
one fixed cohort and all 18 rows. Each host record binds the same cohort/episode fields and a unique
session plus its bounded session artifact. Every referenced file has a relative path and SHA-256.
No path may escape the receipt directory or traverse a link.

The cohort includes host/model revisions, DDK commit, environment/sampling/permission hashes,
three approved Case hashes, token limits, deadline, oracle SHA and budget. Rows retain source/request
hashes, observed calls/cost/time, the host's completion claim, independent oracle exit/report, and
DDK Run references for the gated arm. Session artifacts still require independent review; hashing
a declaration does not authenticate a provider account, model revision, spend or absence of gate
use in the plain arm.

```sh
ddk bench --json
ddk bench --receipts /tmp/ddk-paired/receipts.json --json
```

No records gives `unmeasured` and exit 1. Missing cells, unknown cost, skipped/zero tests and exceeded
bounds remain explicit, incomplete results; integrity/schema/matching failures exit 5. Normal failed
checks remain in a complete matrix. A green report never overrides a nonzero process exit.

## Interpretation

Reports retain per-arm ready decisions, independent pass/fail counts, false acceptances/blocks,
agent/observer durations and recorded cost. They describe submitted records. Fixture records have
zero measured episodes. Relabeling fixtures as measured only changes the declared count;
`measured_records` stays 0, `measurement_review` stays `not-reviewed`, and `calibrated` stays false.
No review-to-calibration ingestion is implemented. Independent review and an approved measurement
program remain necessary before comparative claims or changes to `gsd-baseline.json`.

The initial local check prepared 18 independent contexts and checked nine original/broken/restored
source states with zero model calls. This validates preparation and oracle discrimination only;
it is not a paired model experiment, repair success rate or product superiority result.
