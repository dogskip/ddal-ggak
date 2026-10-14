"""User workflows share storage, verification and owned application rules."""

from __future__ import annotations

import copy
import hashlib
import json
from zipfile import ZipFile

import pytest

from ddk.models.verified_change import canonical_json, record_digest
from ddk.services.verified_change_service import VerifiedChangeService
from tests.unit.services.test_managed_application import ready_store
from tests.unit.test_verified_change_engine import RUN_ID, Evaluator
from tests.unit.test_verified_change_engine import scenario as scenario


def test_status_reads_complete_record_and_rejects_damaged_artifacts(tmp_path):
    store, run = ready_store(tmp_path)
    service = VerifiedChangeService(tmp_path)
    assert service.status(run["run_id"]) == run
    artifact = store.path_for("run", run["run_id"]) / run["artifacts"][0]["path"]
    artifact.unlink()
    with pytest.raises((OSError, ValueError)):
        service.status(run["run_id"])


@pytest.mark.asyncio
async def test_verify_without_model_uses_same_engine_and_has_no_original_writes(scenario):
    store, case, baseline, candidate = scenario
    service = VerifiedChangeService(store.repository, evaluator=Evaluator())
    result = await service.verify(
        case["case_id"],
        baseline=baseline,
        candidate=candidate,
        run_id=RUN_ID,
        change_requirements={"src/App.tsx": ["R2"]},
    )
    assert result["decision"] == "ready"
    assert result["model_calls"] == []
    assert service.status(RUN_ID) == result
    assert (baseline / "src/App.tsx").read_bytes() == b"before"
    assert (candidate / "src/App.tsx").read_bytes() == b"after"


@pytest.mark.asyncio
async def test_explicit_local_choice_cannot_lower_an_isolated_case(scenario):
    store, case, baseline, candidate = scenario
    evaluator = Evaluator()
    service = VerifiedChangeService(store.repository, evaluator=evaluator)
    with pytest.raises(ValueError, match="assurance_mismatch"):
        await service.verify(
            case["case_id"],
            baseline=baseline,
            candidate=candidate,
            run_id=RUN_ID,
            trusted_local_approved=True,
        )
    assert evaluator.requests == []


def test_case_import_reads_bounded_inputs_and_preserves_immutable_definition(tmp_path):
    original, run = ready_store(tmp_path / "original")
    definition = original.path_for("case", run["case_id"]) / "case.json"
    service = VerifiedChangeService(tmp_path / "destination")
    imported = service.import_case(definition)
    assert imported == original.case(run["case_id"])
    assert service.import_case(definition) == imported


def test_case_import_refuses_a_symbolic_input(tmp_path):
    original, run = ready_store(tmp_path / "original")
    definition = original.path_for("case", run["case_id"]) / "case.json"
    case = original.case(run["case_id"])
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    for item in case["inputs"]:
        target = inputs / item["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.symlink_to(original.path_for("case", run["case_id"]) / "inputs" / item["path"])
    with pytest.raises((OSError, ValueError)):
        VerifiedChangeService(tmp_path / "destination").import_case(definition, inputs)


def test_case_import_refuses_a_symbolic_ancestor_of_the_input_directory(tmp_path):
    original, run = ready_store(tmp_path / "original")
    case_dir = original.path_for("case", run["case_id"])
    alias = tmp_path / "alias"
    alias.symlink_to(case_dir, target_is_directory=True)
    with pytest.raises((OSError, ValueError)):
        VerifiedChangeService(tmp_path / "destination").import_case(
            case_dir / "case.json", alias / "inputs"
        )


def test_default_export_contains_review_metadata_without_private_payloads(tmp_path):
    store, run = ready_store(tmp_path / "repo")
    destination = tmp_path / "review.zip"
    receipt = VerifiedChangeService(store.repository).export(run["run_id"], destination)
    assert receipt["run_id"] == run["run_id"]
    assert receipt["included_artifacts"] == []
    with ZipFile(destination) as archive:
        assert archive.namelist() == ["report.json"]
        report = json.loads(archive.read("report.json"))
        assert report["decision"] == "ready"
        assert report["assurance"] == "isolated"
        assert "request" not in report and "messages" not in report
    assert b"new\\n" not in destination.read_bytes()


def test_private_export_is_explicit_and_retains_verified_bytes(tmp_path):
    store, run = ready_store(tmp_path / "repo")
    destination = tmp_path / "private.zip"
    receipt = VerifiedChangeService(store.repository).export(
        run["run_id"],
        destination,
        include_sensitive=True,
    )
    assert set(receipt["included_artifacts"]) == {item["artifact_id"] for item in run["artifacts"]}
    with ZipFile(destination) as archive:
        for artifact in run["artifacts"]:
            assert (
                archive.read(artifact["path"])
                == (store.path_for("run", run["run_id"]) / artifact["path"]).read_bytes()
            )
    assert destination.stat().st_mode & 0o777 == 0o600


def test_export_never_replaces_an_existing_file(tmp_path):
    store, run = ready_store(tmp_path / "repo")
    destination = tmp_path / "user.zip"
    destination.write_bytes(b"user data")
    with pytest.raises(FileExistsError):
        VerifiedChangeService(store.repository).export(run["run_id"], destination)
    assert destination.read_bytes() == b"user data"


def test_managed_application_is_available_through_the_shared_service(tmp_path):
    store, run = ready_store(tmp_path)
    result = VerifiedChangeService(store.repository).apply(
        apply_id="00000000-0000-4000-8000-000000000004",
        case_id=run["case_id"],
        run_id=run["run_id"],
        run_sha256=record_digest(run),
        changes_sha256=record_digest(run["changes"]),
        quiescence_confirmed=True,
        local_storage_confirmed=True,
    )
    assert result["state"] == "applied"
    assert (tmp_path / "src/App.tsx").read_bytes() == b"new\n"


def test_case_import_rejects_duplicate_json_keys(tmp_path):
    definition = tmp_path / "case.json"
    definition.write_bytes(b'{"record_type":"case","record_type":"run"}')
    with pytest.raises(ValueError):
        VerifiedChangeService(tmp_path / "repo").import_case(definition)


def test_status_returns_pending_without_restarting_it(tmp_path):
    store, run = ready_store(tmp_path)
    other = dict(run)
    other.update(
        run_id="00000000-0000-4000-8000-000000000056",
        status="prepared",
        decision=None,
        finished_at=None,
        duration_ms=None,
        changes=[],
        artifacts=[],
        model_calls=[],
        results=[],
    )
    store.begin_run(other)
    assert VerifiedChangeService(tmp_path).status(other["run_id"]) == other
    assert not (store.path_for("run", other["run_id"]) / "run.json").exists()
    assert canonical_json(store.pending_run(other["run_id"])) == canonical_json(other)


def test_missing_status_is_read_only_and_does_not_create_a_workspace(tmp_path):
    repository = tmp_path / "absent"
    service = VerifiedChangeService(repository)
    with pytest.raises(FileNotFoundError):
        service.status("00000000-0000-4000-8000-000000000056")
    assert not repository.exists()


def publish_variant(store, original, *, log=None, reason=None):
    run = copy.deepcopy(original)
    run["run_id"] = "00000000-0000-4000-8000-000000000056"
    payloads = {
        item["path"]: (store.path_for("run", original["run_id"]) / item["path"]).read_bytes()
        for item in run["artifacts"]
    }
    if log is not None:
        item = next(item for item in run["artifacts"] if item["kind"] != "source")
        item.update(size_bytes=len(log), sha256=hashlib.sha256(log).hexdigest())
        payloads[item["path"]] = log
    if reason is not None:
        run["results"][0]["reason_code"] = reason
    pending = copy.deepcopy(run)
    pending.update(
        status="prepared",
        decision=None,
        finished_at=None,
        duration_ms=None,
        results=[],
        artifacts=[],
        changes=[],
        model_calls=[],
    )
    store.begin_run(pending)
    store.publish_run(run, payloads)
    return run


def test_private_export_uses_artifact_limit_instead_of_source_file_limit(tmp_path):
    store, original = ready_store(tmp_path / "repo")
    payload = b"x" * (2 * 1024**2 + 1)
    run = publish_variant(store, original, log=payload)
    destination = tmp_path / "large.zip"
    VerifiedChangeService(store.repository).export(
        run["run_id"], destination, include_sensitive=True
    )
    with ZipFile(destination) as archive:
        assert payload in [archive.read(name) for name in archive.namelist()]


def test_public_export_excludes_free_text_failure_details(tmp_path):
    store, original = ready_store(tmp_path / "repo")
    private = "Preview exited: PRIVATE_TOKEN=synthetic-only"
    run = publish_variant(store, original, reason=private)
    destination = tmp_path / "public.zip"
    VerifiedChangeService(store.repository).export(run["run_id"], destination)
    with ZipFile(destination) as archive:
        report = archive.read("report.json")
    assert private.encode() not in report
