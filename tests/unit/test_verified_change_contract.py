"""Exercise the approved contract through the runtime entry points."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from ddk.models.verified_change import (
    ContractError,
    canonical_json,
    parse_record,
    record_digest,
    validate_record,
)

DATA = Path(__file__).resolve().parents[2] / "tests/fixtures/verified-change"
EXAMPLES = json.loads((DATA / "contract-examples.json").read_text())
CASES = {
    x["record"]["case_id"]: x["record"]
    for x in EXAMPLES["valid"]
    if x["record"]["record_type"] == "case"
}
RUNS = {
    x["record"]["run_id"]: x["record"]
    for x in EXAMPLES["valid"]
    if x["record"]["record_type"] == "run"
}


@pytest.mark.parametrize("example", EXAMPLES["valid"], ids=lambda x: x["name"])
def test_approved_examples(example):
    record = example["record"]
    validate_record(record, CASES, RUNS)
    assert parse_record(canonical_json(record), CASES, RUNS) == record


@pytest.mark.parametrize("example", EXAMPLES["invalid"], ids=lambda x: x["name"])
def test_rejected_examples(example):
    with pytest.raises(ContractError):
        validate_record(example["record"], CASES, RUNS)


@pytest.mark.parametrize(
    "payload",
    [
        b'{"a":1,"a":2}',
        b'{"a":NaN}',
        b'{"a":Infinity}',
        b'{"a":-Infinity}',
        b'{"a":"\xff"}',
        b"[" * 33 + b"0" + b"]" * 33,
        b" " * (2 * 1024 * 1024 + 1),
    ],
)
def test_parser_refuses_ambiguous_or_unbounded_bytes(payload):
    with pytest.raises(ContractError):
        parse_record(payload)


def test_canonical_bytes_match_the_approved_hash_method():
    case = next(iter(CASES.values()))
    assert canonical_json({"b": 2, "a": "한"}) == '{"a":"한","b":2}'.encode()
    assert record_digest(case) == next(iter(RUNS.values()))["case_sha256"]


def test_format_validation_is_enabled():
    case = copy.deepcopy(next(iter(CASES.values())))
    case["created_at"] = "2026-99-99T99:99:99Z"
    with pytest.raises(ContractError):
        validate_record(case)


def test_casefold_input_collision_is_rejected():
    case = copy.deepcopy(next(iter(CASES.values())))
    extra = copy.deepcopy(case["inputs"][0])
    extra["path"] = extra["path"].upper()
    case["inputs"].append(extra)
    with pytest.raises(ContractError, match="path_collision"):
        validate_record(case)


@pytest.mark.parametrize("value", ["https://outside.invalid/schema", "file:///etc/passwd"])
def test_external_schema_references_are_rejected(value):
    case = copy.deepcopy(next(iter(CASES.values())))
    case["$ref"] = value
    with pytest.raises(ContractError, match="external_schema_reference"):
        validate_record(case)


@pytest.mark.parametrize(
    "path", [".GIT/config", ".Env.local", "src/with\ncontrol.ts", "src/space.ts "]
)
def test_case_inputs_share_the_repository_path_policy(path):
    case = copy.deepcopy(next(iter(CASES.values())))
    item = copy.deepcopy(case["inputs"][0])
    item["path"] = path
    case["inputs"].append(item)
    with pytest.raises(ContractError, match="unsafe_input|schema"):
        validate_record(case)


def test_verify_cannot_claim_a_repair_round():
    run = copy.deepcopy(next(iter(RUNS.values())))
    run["decision"] = "blocked"
    run["latest_round"] = 1
    run["rounds"].append(copy.deepcopy(run["rounds"][0]))
    run["rounds"][1]["round_no"] = 1
    with pytest.raises(ContractError, match="verify_round"):
        validate_record(run, CASES, RUNS)


def test_superseded_case_must_exist_and_cannot_reference_itself():
    case = copy.deepcopy(next(iter(CASES.values())))
    case["supersedes_case_id"] = case["case_id"]
    with pytest.raises(ContractError, match="superseded_case"):
        validate_record(case, CASES, RUNS)
    case["supersedes_case_id"] = "00000000-0000-4000-8000-000000000099"
    with pytest.raises(ContractError, match="superseded_case"):
        validate_record(case, CASES, RUNS)
