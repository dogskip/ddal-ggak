# Rebuildable catalog reference

[User guide](ONECLICK.md) · [한국어 사용 안내](ONECLICK.ko.md)

`index.sqlite3` projects validated canonical JSON; it is never the source of a verdict.
Canonical paths/states remain compatible: cases/<id>/case.json, runs/<id>/run.json and
applies/<id>/apply.json; decisions are ready/blocked/manual-review, not renamed to passed.
WAL, synchronous NORMAL, foreign keys and a 5000 ms SQLite busy timeout are set on write connections.
The shared file lock has a 250 ms acquisition limit. Atomic rebuild validates every input first and
preserves the previous database if reconstruction fails. Database files and sidecars must be regular,
single-link files; the database is private (0600). Logical rows and stable primary-key query order are
reproducible; SQLite page layout, rowids and WAL bytes are not a reproducibility contract.

Fields below are the actual schema, not a second planned schema. JSON fields use the canonical UTF-8
encoding. UUIDs, hashes, modes, counts and enum values are validated by the canonical JSON contract
before indexing. Nullable fields preserve absent evidence in older or unfinished records rather than
inventing values. The catalog retains full private records locally; MCP selects a restricted metadata
projection in SQL and does not expose record_json, requests, source or diagnostic text.

`size_delta_bytes` uses sealed before/after sizes. Text `hunk_count` is the number of Unified Diff
blocks with standard three-line context, calculated in a separate bounded worker. Binary changes use
one binary change unit. Pending records without a staged source may have no hunk count yet. A worker
failure leaves the canonical record intact and requests reindexing. `before_artifact_id` is null when
the original lives in the case's frozen source input. Apply root hashes cover the sorted target file
set (path/hash/mode, including absence); they do not claim a hash of unrelated repository files.
Legacy model calls without retained prompt/response artifacts keep those digests null.

## cases

One row per frozen case. Host assurance has no invented container network policy.

| Column | SQLite type | Required / key |
| --- | --- | --- |
| `case_id` | TEXT | primary key 1 |
| `schema_version` | TEXT | required |
| `created_at` | TEXT | required |
| `request` | TEXT | required |
| `source_origin` | TEXT | required |
| `git_base_ref` | TEXT | nullable |
| `baseline_tree_sha256` | TEXT | required |
| `environment_sha256` | TEXT | required |
| `evaluator_sha256` | TEXT | required |
| `font_manifest_sha256` | TEXT | nullable |
| `container_network_policy` | TEXT | nullable |
| `limits_json` | TEXT | required |
| `fixed_inputs_json` | TEXT | required |
| `container_json` | TEXT | required |
| `record_sha256` | TEXT | required |
| `record_json` | TEXT | required |

## requirements

Explicit case-scoped requirements; allow_delete defaults to false and allowed paths must be in case scope.

| Column | SQLite type | Required / key |
| --- | --- | --- |
| `case_id` | TEXT | primary key 1 |
| `requirement_id` | TEXT | primary key 2 |
| `summary` | TEXT | required |
| `allowed_paths_json` | TEXT | required |
| `allow_delete` | INTEGER | required |

## checks

Frozen check definitions, runner format/skip policy and browser viewport. A target baseline expectation remains null when the canonical contract does not require baseline failure.

| Column | SQLite type | Required / key |
| --- | --- | --- |
| `case_id` | TEXT | primary key 1 |
| `check_id` | TEXT | primary key 2 |
| `kind` | TEXT | required |
| `required` | INTEGER | required |
| `baseline_expectation` | TEXT | nullable |
| `candidate_expectation` | TEXT | nullable |
| `definition_path` | TEXT | required |
| `definition_sha256` | TEXT | required |
| `command_argv_json` | TEXT | required |
| `report_adapter` | TEXT | required |
| `allow_skipped` | INTEGER | required |
| `timeout_ms` | INTEGER | required |
| `max_retries` | INTEGER | required |
| `viewport_width` | INTEGER | nullable |
| `viewport_height` | INTEGER | nullable |
| `requirement_ids_json` | TEXT | required |

## runs

Current/final canonical run projection, explicit assurance, integrity and settled/reserved micro-USD totals.

| Column | SQLite type | Required / key |
| --- | --- | --- |
| `run_id` | TEXT | primary key 1 |
| `case_id` | TEXT | required |
| `source_run_id` | TEXT | nullable |
| `operation` | TEXT | required |
| `status` | TEXT | required |
| `verdict` | TEXT | nullable |
| `stop_reason` | TEXT | nullable |
| `started_at` | TEXT | required |
| `finished_at` | TEXT | nullable |
| `duration_ms` | INTEGER | nullable |
| `request_sha256` | TEXT | required |
| `baseline_tree_sha256` | TEXT | nullable |
| `candidate_tree_sha256` | TEXT | nullable |
| `latest_round` | INTEGER | nullable |
| `assurance_level` | TEXT | nullable |
| `total_cost_microusd` | INTEGER | required |
| `reserved_cost_microusd` | INTEGER | required |
| `integrity_json` | TEXT | required |
| `actions_json` | TEXT | required |
| `record_sha256` | TEXT | required |
| `record_json` | TEXT | required |

## run_rounds

Immutable candidate/check-change digests and times for every repair round.

| Column | SQLite type | Required / key |
| --- | --- | --- |
| `run_id` | TEXT | primary key 1 |
| `round_no` | INTEGER | primary key 2 |
| `candidate_tree_sha256` | TEXT | required |
| `changes_sha256` | TEXT | required |
| `started_at` | TEXT | required |
| `finished_at` | TEXT | nullable |

## check_results

Separate baseline/candidate observations for each round. Project reports retain their lower evidence origin.

| Column | SQLite type | Required / key |
| --- | --- | --- |
| `run_id` | TEXT | primary key 1 |
| `round_no` | INTEGER | primary key 2 |
| `phase` | TEXT | primary key 3 |
| `check_id` | TEXT | primary key 4 |
| `status` | TEXT | required |
| `exit_code` | INTEGER | nullable |
| `executed_count` | INTEGER | nullable |
| `failed_count` | INTEGER | nullable |
| `skipped_count` | INTEGER | nullable |
| `duration_ms` | INTEGER | required |
| `reason_code` | TEXT | nullable |
| `evidence_origin` | TEXT | required |
| `artifact_ids_json` | TEXT | required |

## file_changes

Final baseline-relative source changes; deletion has null after fields. Hunk counting is bounded and never runs arbitrary project code.

| Column | SQLite type | Required / key |
| --- | --- | --- |
| `run_id` | TEXT | primary key 1 |
| `path` | TEXT | primary key 2 |
| `change_kind` | TEXT | required |
| `before_sha256` | TEXT | nullable |
| `after_sha256` | TEXT | nullable |
| `before_mode` | INTEGER | nullable |
| `after_mode` | INTEGER | nullable |
| `size_delta_bytes` | INTEGER | nullable |
| `hunk_count` | INTEGER | nullable |
| `before_artifact_id` | TEXT | nullable |
| `after_artifact_id` | TEXT | nullable |
| `requirement_ids_json` | TEXT | required |

## artifacts

Verified evidence paths/digests, private/public flags and AX snapshots.

| Column | SQLite type | Required / key |
| --- | --- | --- |
| `run_id` | TEXT | primary key 1 |
| `artifact_id` | TEXT | primary key 2 |
| `kind` | TEXT | required |
| `path` | TEXT | required |
| `sha256` | TEXT | required |
| `size_bytes` | INTEGER | required |
| `sensitive` | INTEGER | required |
| `public_export_allowed` | INTEGER | required |

## model_calls

Reservation/settlement records with observed model/provider, tokens and retained request/response digests.

| Column | SQLite type | Required / key |
| --- | --- | --- |
| `run_id` | TEXT | primary key 1 |
| `call_id` | TEXT | primary key 2 |
| `round_no` | INTEGER | required |
| `provider_kind` | TEXT | required |
| `model` | TEXT | required |
| `state` | TEXT | required |
| `input_tokens` | INTEGER | nullable |
| `output_tokens` | INTEGER | nullable |
| `reserved_cost_microusd` | INTEGER | required |
| `actual_cost_microusd` | INTEGER | nullable |
| `prompt_sha256` | TEXT | nullable |
| `response_sha256` | TEXT | nullable |

## apply_transactions

Durable apply/recovery receipts projected with exact target and applied state digests.

| Column | SQLite type | Required / key |
| --- | --- | --- |
| `transaction_id` | TEXT | primary key 1 |
| `run_id` | TEXT | required |
| `case_id` | TEXT | required |
| `state` | TEXT | required |
| `created_at` | TEXT | required |
| `updated_at` | TEXT | nullable |
| `target_root_sha256` | TEXT | nullable |
| `applied_root_sha256` | TEXT | nullable |
| `targets_json` | TEXT | required |
| `record_sha256` | TEXT | required |
| `record_json` | TEXT | required |

## failure_lessons

Deterministic lesson IDs, redacted summaries, failure signatures and candidate/proposal digests. Rebuild uses only canonical runs/evidence.

| Column | SQLite type | Required / key |
| --- | --- | --- |
| `lesson_id` | TEXT | primary key 1 |
| `case_id` | TEXT | required |
| `run_id` | TEXT | required |
| `round_no` | INTEGER | required |
| `check_id` | TEXT | required |
| `reason_code` | TEXT | required |
| `error_signature_sha256` | TEXT | required |
| `failed_patch_sha256` | TEXT | required |
| `affected_paths_json` | TEXT | required |
| `diagnostic_summary` | TEXT | required |
| `created_at` | TEXT | required |

## failure_lessons_fts

The twelfth table is an FTS5 virtual table with `check_id`, `reason_code`, `affected_paths_json`,
and `diagnostic_summary`. External content is `failure_lessons`, with rowid as its private join key.
Rebuild regenerates the FTS contents. Search is parameter-bound, case/check filtered, ranked and
limited to three lessons; rowids are not public identities. Lookup failure omits advisory history.
A five-millisecond lookup is a benchmark target, not an unconditional hardware-independent guarantee.
SQLite creates internal FTS maintenance tables in addition to the twelve logical tables.

The only foreign references are case/run ownership and run ancestry; child tables are regenerated
from their parent records, not edited through a second write API. Use `ddk change reindex` after a
missing/corrupt/stale catalog warning. Never repair canonical JSON by editing SQLite rows.

Primary references: [SQLite FTS5](https://www.sqlite.org/fts5.html),
[SQLite PRAGMA reference](https://www.sqlite.org/pragma.html).
