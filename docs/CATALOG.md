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

The catalog has sixteen logical tables including one FTS5 virtual table. FTS maintenance tables
are excluded. Optional Run.context_digests[], stall_diagnoses[] and workspace_leases[] are the only
source of new metadata rows. Old absent fields remain absent/NULL; lock files are not record authority.
Reindex compares frozen canonical record digests again before publishing the replacement.

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

Reservation/settlement records with observed model/provider, tokens and retained request/response digests. Cache counts are observations, not evidence of a discount. Unknown cache charges block ready. A stable prefix digest does not assert a provider cache hit.

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
| `cache_read_tokens` | INTEGER | nullable |
| `cache_write_tokens` | INTEGER | nullable |
| `cache_prefix_sha256` | TEXT | nullable |

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

Deterministic lesson IDs, redacted summaries, failure signatures and candidate/proposal digests. Rebuild uses only canonical runs/evidence. Resolution is attributed only to the same check in a later ready round. Lookup prefers resolved lessons and includes same-signature or FTS-ranked cases in this repository, up to three. Selected advice is regenerated from canonical artifacts; database edits cannot forge diagnostic text.

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
| `resolved_in_round` | INTEGER | nullable |
| `resolved_patch_sha256` | TEXT | nullable |

## gate_verdicts

Latest canonical run per case/plane, including pending/running blockers and ambiguous timestamp ties. IDs are not chronology. gate revalidates JSON, artifacts, costs, full current source and configuration; SQLite never authorizes delivery.

| Column | SQLite type | Required / key |
| --- | --- | --- |
| `case_id` | TEXT | primary key 1 |
| `plane` | TEXT | primary key 2 |
| `run_id` | TEXT | required |
| `case_sha256` | TEXT | required |
| `bound_tree_sha256` | TEXT | nullable |
| `evaluator_sha256` | TEXT | required |
| `verdict` | TEXT | required |
| `assurance_level` | TEXT | nullable |
| `verified_at` | TEXT | nullable |
| `selection_status` | TEXT | required |

Exact derived constraints:

```sql
CREATE TABLE gate_verdicts (case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,plane TEXT NOT NULL CHECK(plane IN ('all','command','test','browser','visual','policy')),run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,case_sha256 TEXT NOT NULL CHECK(length(case_sha256)=64),bound_tree_sha256 TEXT CHECK(bound_tree_sha256 IS NULL OR length(bound_tree_sha256)=64),evaluator_sha256 TEXT NOT NULL CHECK(length(evaluator_sha256)=64),verdict TEXT NOT NULL CHECK(verdict IN ('ready','blocked','manual-review')),assurance_level TEXT,verified_at TEXT,selection_status TEXT NOT NULL CHECK(selection_status IN ('selected','ambiguous')),PRIMARY KEY(case_id,plane));
```

## context_digests

Run.context_digests[] links original and compacted artifacts to an existing round. Raw size/hash describe the retained original; compacted size/hash describe the fully redacted excerpt. Bounds are 65,536 bytes (repair default 4,096). AX diffs/masking can expand small inputs; compacted <= raw is not required.

| Column | SQLite type | Required / key |
| --- | --- | --- |
| `run_id` | TEXT | primary key 1 |
| `round_no` | INTEGER | primary key 2 |
| `source_artifact_id` | TEXT | primary key 3 |
| `compacted_artifact_id` | TEXT | required |
| `compressor_kind` | TEXT | required |
| `raw_bytes` | INTEGER | required |
| `compacted_bytes` | INTEGER | required |
| `raw_sha256` | TEXT | required |
| `compacted_sha256` | TEXT | required |

Exact derived constraints:

```sql
CREATE TABLE context_digests (run_id TEXT NOT NULL,round_no INTEGER NOT NULL,source_artifact_id TEXT NOT NULL,compacted_artifact_id TEXT NOT NULL,compressor_kind TEXT NOT NULL CHECK(compressor_kind IN ('raw','log_frame_extract','ax_tree_diff','json_schema_crush')),raw_bytes INTEGER NOT NULL CHECK(raw_bytes>=0),compacted_bytes INTEGER NOT NULL CHECK(compacted_bytes BETWEEN 0 AND 65536),raw_sha256 TEXT NOT NULL CHECK(length(raw_sha256)=64),compacted_sha256 TEXT NOT NULL CHECK(length(compacted_sha256)=64),PRIMARY KEY(run_id,round_no,source_artifact_id),FOREIGN KEY(run_id,round_no) REFERENCES run_rounds(run_id,round_no) ON DELETE CASCADE,FOREIGN KEY(run_id,source_artifact_id) REFERENCES artifacts(run_id,artifact_id) ON DELETE CASCADE,FOREIGN KEY(run_id,compacted_artifact_id) REFERENCES artifacts(run_id,artifact_id) ON DELETE CASCADE);
```

## stall_diagnoses

Run.stall_diagnoses[] records progress control. The first exact repeated failure set requests a strategy change; the next exact repeat halts repair_stalled. Failure count alone never halts. Standard pytest summary durations and JUnit timing/hostname attributes are normalized; assertion values and source lines remain significant.

| Column | SQLite type | Required / key |
| --- | --- | --- |
| `run_id` | TEXT | primary key 1 |
| `round_no` | INTEGER | primary key 2 |
| `stall_category` | TEXT | required |
| `repeated_signature_sha256` | TEXT | required |
| `streak_count` | INTEGER | required |
| `action_taken` | TEXT | required |

Exact derived constraints:

```sql
CREATE TABLE stall_diagnoses (run_id TEXT NOT NULL,round_no INTEGER NOT NULL CHECK(round_no BETWEEN 1 AND 10),stall_category TEXT NOT NULL CHECK(stall_category IN ('identical_error_signature','patch_oscillation','failed_count_non_decreasing','scope_boundary_blocked')),repeated_signature_sha256 TEXT NOT NULL CHECK(length(repeated_signature_sha256)=64),streak_count INTEGER NOT NULL CHECK(streak_count>=2),action_taken TEXT NOT NULL CHECK(action_taken IN ('inject_anti_oscillation_constraint','halt_repair_stalled')),PRIMARY KEY(run_id,round_no),FOREIGN KEY(run_id,round_no) REFERENCES run_rounds(run_id,round_no) ON DELETE CASCADE);
```

## worktree_leases

Run.workspace_leases[] records actual owned snapshot-copy lifetimes, including multiple copies per run/round. Creation precedes active persistence; successful removal precedes released. Unknown removal records cleanup_failed. All retained leases must be released for ready/manual-review. No Git worktree or Docker volume receipt is invented.

| Column | SQLite type | Required / key |
| --- | --- | --- |
| `lease_id` | TEXT | primary key 1 |
| `run_id` | TEXT | required |
| `case_id` | TEXT | required |
| `round_no` | INTEGER | required |
| `phase` | TEXT | required |
| `isolation_kind` | TEXT | required |
| `base_tree_sha256` | TEXT | required |
| `state` | TEXT | required |
| `acquired_at` | TEXT | required |
| `released_at` | TEXT | nullable |

Exact derived constraints:

```sql
CREATE TABLE worktree_leases (lease_id TEXT PRIMARY KEY,run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,round_no INTEGER NOT NULL,phase TEXT NOT NULL CHECK(phase IN ('baseline','candidate')),isolation_kind TEXT NOT NULL CHECK(isolation_kind='snapshot_copy'),base_tree_sha256 TEXT NOT NULL CHECK(length(base_tree_sha256)=64),state TEXT NOT NULL CHECK(state IN ('active','released','cleanup_failed')),acquired_at TEXT NOT NULL,released_at TEXT,FOREIGN KEY(run_id,round_no) REFERENCES run_rounds(run_id,round_no) ON DELETE CASCADE);
```

## failure_lessons_fts

FTS5 external content is failure_lessons, joined by private rowid. Parameter-bound search is advisory; missing, corrupt or busy lookup omits history. Physical rowids and a five-millisecond target are not reproducibility or latency guarantees.

| Column | SQLite type | Required / key |
| --- | --- | --- |
| `check_id` | untyped | nullable |
| `reason_code` | untyped | nullable |
| `affected_paths_json` | untyped | nullable |
| `diagnostic_summary` | untyped | nullable |

New round/artifact foreign keys bind metadata to canonical parents. Refresh deletes dependent
metadata before artifacts/rounds. Contexts and diagnoses are append-only; leases permit only
active -> released/cleanup_failed. Reindex freezes input records, validates all evidence, checks
integrity, compares source digests again, fsyncs and atomically replaces the database. Logical rows,
not physical SQLite/WAL bytes, are reproducible. Use `ddk change reindex` after stale/corrupt warnings.
Never repair JSON by editing SQL rows.

Primary references: [SQLite FTS5](https://www.sqlite.org/fts5.html),
[SQLite PRAGMA reference](https://www.sqlite.org/pragma.html).
