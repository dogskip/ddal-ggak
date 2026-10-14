"""Synthetic ready records exercise real durable application, not evaluator quality."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from ddk.models.verified_change import record_digest
from ddk.services.artifact_applier import ArtifactApplier
from ddk.services.verified_change_store import VerifiedChangeStore

_EXAMPLES = json.loads(
    (
        Path(__file__).resolve().parents[3] / "docs/design/verified-change/contract-examples.json"
    ).read_text()
)
_APPLY_ID = "00000000-0000-4000-8000-000000000004"


def ready_store(repository: Path, second_file: bool = False, *, create_first: bool = False):
    case = copy.deepcopy(_EXAMPLES["valid"][0]["record"])
    run = copy.deepcopy(_EXAMPLES["valid"][1]["record"])
    inputs = {}
    for index, item in enumerate(case["inputs"]):
        content = b"old\n" if item["role"] == "source" else f"input-{index}".encode()
        item.update(sha256=hashlib.sha256(content).hexdigest(), size_bytes=len(content))
        if item["role"] == "source":
            item["mode"] = 0o640
        inputs[item["path"]] = content
    for check in case["checks"]:
        check["definition_sha256"] = next(
            item["sha256"] for item in case["inputs"] if item["path"] == check["definition_path"]
        )
    artifacts = {}
    for item in run["artifacts"]:
        content = b"new\n" if item["kind"] == "source" else b"{}"
        item.update(sha256=hashlib.sha256(content).hexdigest(), size_bytes=len(content))
        artifacts[item["path"]] = content
    change = run["changes"][0]
    change.update(
        before_sha256=hashlib.sha256(b"old\n").hexdigest(),
        after_sha256=hashlib.sha256(b"new\n").hexdigest(),
        before_mode=0o640,
        after_mode=0o640,
    )
    if second_file:
        content = b"created\n"
        artifact = copy.deepcopy(run["artifacts"][-1])
        artifact.update(
            artifact_id="new-source-2",
            path="artifacts/new/New.tsx",
            sha256=hashlib.sha256(content).hexdigest(),
            size_bytes=len(content),
        )
        run["artifacts"].append(artifact)
        artifacts[artifact["path"]] = content
        created = copy.deepcopy(change)
        created.update(
            path="src/New.tsx",
            action="create",
            before_sha256=None,
            before_mode=None,
            after_sha256=artifact["sha256"],
            after_mode=0o644,
            after_artifact_id=artifact["artifact_id"],
        )
        run["changes"].append(created)
        case["scope_paths"].append("src/New.tsx")
    if create_first:
        run["changes"].reverse()
    run["case_sha256"] = record_digest(case)
    run["rounds"][0]["changes_sha256"] = record_digest(run["changes"])
    store = VerifiedChangeStore(repository)
    store.publish_case(case, inputs)
    pending = copy.deepcopy(run)
    pending.update(
        status="prepared",
        decision=None,
        finished_at=None,
        duration_ms=None,
        results=[],
        artifacts=[],
        model_calls=[],
        changes=[],
    )
    store.begin_run(pending)
    store.publish_run(run, artifacts)
    target = repository / "src/App.tsx"
    target.parent.mkdir()
    target.write_bytes(b"old\n")
    target.chmod(0o640)
    return store, run


def apply(store, run, **overrides):
    kwargs = {
        "apply_id": _APPLY_ID,
        "case_id": run["case_id"],
        "run_id": run["run_id"],
        "run_sha256": record_digest(run),
        "changes_sha256": record_digest(run["changes"]),
        "quiescence_confirmed": True,
        "local_storage_confirmed": True,
        "required_assurance": "isolated",
    }
    kwargs.update(overrides)
    return ArtifactApplier().apply_run(store, **kwargs)


def test_managed_apply_publishes_complete_record_and_preserves_mode(tmp_path):
    store, run = ready_store(tmp_path)
    result = apply(store, run)
    assert result["state"] == "applied"
    assert store.load_apply(_APPLY_ID) == result
    assert (tmp_path / "src/App.tsx").read_bytes() == b"new\n"
    assert (tmp_path / "src/App.tsx").stat().st_mode & 0o777 == 0o640
    assert not (store.base_path / "locks/apply.lock").exists()
    assert apply(store, run) == result


@pytest.mark.parametrize(
    "option,value",
    [
        ("run_sha256", "f" * 64),
        ("changes_sha256", "f" * 64),
        ("quiescence_confirmed", False),
        ("local_storage_confirmed", False),
    ],
)
def test_managed_apply_rejects_missing_authorization_or_hash(tmp_path, option, value):
    store, run = ready_store(tmp_path)
    with pytest.raises(ValueError):
        apply(store, run, **{option: value})
    assert (tmp_path / "src/App.tsx").read_bytes() == b"old\n"
    assert not (store.path_for("apply", _APPLY_ID) / "apply.json").exists()


@pytest.mark.parametrize("edit", ["delete", "mode", "content"])
def test_managed_apply_checks_all_original_state_before_preparation(tmp_path, edit):
    store, run = ready_store(tmp_path, True)
    target = tmp_path / "src/App.tsx"
    if edit == "delete":
        target.unlink()
    elif edit == "mode":
        target.chmod(0o600)
    else:
        target.write_bytes(b"foreign")
    with pytest.raises(ValueError, match="apply_conflict"):
        apply(store, run)
    assert not (tmp_path / "src/New.tsx").exists()
    assert not (store.base_path / "locks/apply.lock").exists()


def test_failure_on_second_file_restores_first_from_durable_record(tmp_path):
    store, run = ready_store(tmp_path, True)
    from ddk.services import artifact_applier as module

    original = module.atomic_write

    def fail(path, payload, *args, **kwargs):
        if path == tmp_path / "src/New.tsx":
            raise OSError("injected write failure")
        return original(path, payload, *args, **kwargs)

    with patch.object(module, "atomic_write", side_effect=fail):
        result = apply(store, run)
    assert result["state"] == "rolled_back"
    assert all(e["state"] == "restored" for e in result["entries"])
    assert (tmp_path / "src/App.tsx").read_bytes() == b"old\n"
    assert not (tmp_path / "src/New.tsx").exists()
    assert store.load_apply(_APPLY_ID) == result
    assert not (store.base_path / "locks/apply.lock").exists()


def test_external_edit_during_failure_is_preserved_and_blocks_further_writes(tmp_path):
    store, run = ready_store(tmp_path, True)
    from ddk.services import artifact_applier as module

    original = module.atomic_write

    def fail(path, payload, *args, **kwargs):
        if path == tmp_path / "src/New.tsx":
            (tmp_path / "src/App.tsx").write_bytes(b"foreign")
            raise OSError("injected write failure")
        return original(path, payload, *args, **kwargs)

    with patch.object(module, "atomic_write", side_effect=fail):
        result = apply(store, run)
    assert result["state"] == "unknown"
    assert (tmp_path / "src/App.tsx").read_bytes() == b"foreign"
    assert not (tmp_path / "src/New.tsx").exists()
    assert (store.base_path / "locks/apply.lock").is_file()
    assert store.load_apply(_APPLY_ID) == result


def test_uncertain_prepared_publication_retains_the_application_lock(tmp_path):
    store, run = ready_store(tmp_path)
    original = store.publish_apply

    def fail(record):
        saved = original(record)
        if record["state"] == "prepared":
            raise OSError("acknowledgement lost")
        return saved

    with patch.object(store, "publish_apply", side_effect=fail), pytest.raises(OSError):
        apply(store, run)
    assert (tmp_path / "src/App.tsx").read_bytes() == b"old\n"
    assert store.load_apply(_APPLY_ID)["state"] == "prepared"
    assert (store.base_path / "locks/apply.lock").is_file()


def test_completed_publication_is_preserved_when_its_acknowledgement_fails(tmp_path):
    store, run = ready_store(tmp_path)
    original = store.publish_apply

    def fail(record):
        saved = original(record)
        if record["state"] == "applied":
            raise OSError("acknowledgement lost")
        return saved

    with patch.object(store, "publish_apply", side_effect=fail):
        result = apply(store, run)
    assert result["state"] == "applied"
    assert (tmp_path / "src/App.tsx").read_bytes() == b"new\n"
    assert store.load_apply(_APPLY_ID) == result
    assert not (store.base_path / "locks/apply.lock").exists()


def crash_application(repository, run, point="before_second"):
    import os
    import subprocess
    import sys

    script = """
import json,os,sys
from pathlib import Path
from ddk.services import artifact_applier as module
from ddk.services.verified_change_store import VerifiedChangeStore
root=Path(sys.argv[1]); run=json.loads(sys.argv[2]); point=sys.argv[3]
store=VerifiedChangeStore(root)
original=module.atomic_write
publish=store.publish_apply
if point in {'prepared','completed'}:
 def die(record):
  saved=publish(record)
  if record['state']==('prepared' if point=='prepared' else 'applied'):os._exit(71)
  return saved
 store.publish_apply=die
else:
 def die(path,payload,*args,**kwargs):
  if path==root/'src/New.tsx':
   if point=='foreign':(root/'src/App.tsx').write_bytes(b'foreign')
   if point=='after_second':original(path,payload,*args,**kwargs)
   os._exit(71)
  return original(path,payload,*args,**kwargs)
 module.atomic_write=die
module.ArtifactApplier().apply_run(store,apply_id='00000000-0000-4000-8000-000000000004',case_id=run['case_id'],run_id=run['run_id'],run_sha256=module.record_digest(run),changes_sha256=module.record_digest(run['changes']),quiescence_confirmed=True,local_storage_confirmed=True)
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(repository), json.dumps(run), point],
        cwd=repository,
        env={
            **os.environ,
            "PYTHONPATH": str(Path(__file__).resolve().parents[3] / "src"),
            "ANTHROPIC_API_KEY": "",
            "OPENAI_API_KEY": "",
            "GEMINI_API_KEY": "",
            "PYTHONDONTWRITEBYTECODE": "1",
        },
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 71, result.stderr


def recover(store, **overrides):
    kwargs = {
        "local_storage_confirmed": True,
        "same_host_confirmed": True,
        "quiescence_confirmed": True,
    }
    kwargs.update(overrides)
    return ArtifactApplier().recover(store, _APPLY_ID, **kwargs)


@pytest.mark.parametrize("point", ["before_second", "after_second"])
def test_process_exit_recovers_only_owned_states_from_the_durable_journal(tmp_path, point):
    store, run = ready_store(tmp_path, True)
    crash_application(tmp_path, run, point)
    assert store.load_apply(_APPLY_ID)["state"] == "applying"
    assert (tmp_path / "src/App.tsx").read_bytes() == b"new\n"
    result = recover(store)
    assert result["state"] == "rolled_back"
    assert (tmp_path / "src/App.tsx").read_bytes() == b"old\n"
    assert (tmp_path / "src/App.tsx").stat().st_mode & 0o777 == 0o640
    assert not (tmp_path / "src/New.tsx").exists()
    assert not (store.base_path / "locks/apply.lock").exists()
    assert recover(store) == result


def test_process_exit_after_preparation_never_restarts_the_application(tmp_path):
    store, run = ready_store(tmp_path, True)
    crash_application(tmp_path, run, "prepared")
    assert store.load_apply(_APPLY_ID)["state"] == "prepared"
    result = recover(store)
    assert result["state"] == "conflict"
    assert (tmp_path / "src/App.tsx").read_bytes() == b"old\n"
    assert not (tmp_path / "src/New.tsx").exists()
    assert not (store.base_path / "locks/apply.lock").exists()


def test_recovery_rejects_missing_same_host_confirmation_without_changing_the_lock(tmp_path):
    store, run = ready_store(tmp_path, True)
    crash_application(tmp_path, run)
    lock = store.base_path / "locks/apply.lock"
    previous = lock.read_bytes()
    with pytest.raises(ValueError):
        recover(store, same_host_confirmed=False)
    assert lock.read_bytes() == previous
    assert (tmp_path / "src/App.tsx").read_bytes() == b"new\n"


def test_recovery_preserves_foreign_edits_and_keeps_unknown_blocked(tmp_path):
    store, run = ready_store(tmp_path, True)
    crash_application(tmp_path, run, "foreign")
    result = recover(store)
    assert result["state"] == "unknown"
    assert (tmp_path / "src/App.tsx").read_bytes() == b"foreign"
    assert (store.base_path / "locks/apply.lock").is_file()
    assert recover(store) == result
    assert (tmp_path / "src/App.tsx").read_bytes() == b"foreign"


def test_unknown_record_blocks_new_application_even_if_lock_marker_was_removed(tmp_path):
    store, run = ready_store(tmp_path, True)
    crash_application(tmp_path, run, "foreign")
    assert recover(store)["state"] == "unknown"
    (store.base_path / "locks/apply.lock").unlink()
    (tmp_path / "src/App.tsx").write_bytes(b"old\n")
    with pytest.raises(ValueError, match="application_recovery_required"):
        apply(store, run, apply_id="00000000-0000-4000-8000-000000000005")
    assert (tmp_path / "src/App.tsx").read_bytes() == b"old\n"
    assert not (tmp_path / "src/New.tsx").exists()


def test_missing_artifact_in_unknown_record_is_not_treated_as_missing_application(tmp_path):
    store, run = ready_store(tmp_path, True)
    crash_application(tmp_path, run, "foreign")
    assert recover(store)["state"] == "unknown"
    (store.base_path / "locks/apply.lock").unlink()
    (store.path_for("apply", _APPLY_ID) / "staged/src/App.tsx").unlink()
    (tmp_path / "src/App.tsx").write_bytes(b"old\n")
    with pytest.raises((ValueError, OSError)):
        apply(store, run, apply_id="00000000-0000-4000-8000-000000000005")
    assert (tmp_path / "src/App.tsx").read_bytes() == b"old\n"
    assert not (tmp_path / "src/New.tsx").exists()


@pytest.mark.parametrize("operation", ["initial", "retry", "recover"])
def test_completed_record_directory_sync_failure_never_returns_success_or_releases_lock(
    tmp_path, operation
):
    import os
    import stat

    store, run = ready_store(tmp_path)
    directory = store.path_for("apply", _APPLY_ID)
    original = os.fsync

    def fail(descriptor):
        info = os.fstat(descriptor)
        if (
            stat.S_ISDIR(info.st_mode)
            and directory.exists()
            and info.st_ino == directory.stat().st_ino
        ):
            manifest = directory / "apply.json"
            if manifest.is_file() and json.loads(manifest.read_bytes())["state"] == "applied":
                raise OSError("injected applied directory fsync failure")
        return original(descriptor)

    with patch("os.fsync", side_effect=fail):
        with pytest.raises(OSError, match="directory fsync failure"):
            apply(store, run)
        if operation == "retry":
            with pytest.raises(OSError, match="directory fsync failure"):
                apply(store, run)
        elif operation == "recover":
            with pytest.raises(OSError, match="directory fsync failure"):
                recover(store)
    assert store.load_apply(_APPLY_ID)["state"] == "applied"
    assert (store.base_path / "locks/apply.lock").is_file()
    assert (tmp_path / "src/App.tsx").read_bytes() == b"new\n"


def test_completed_publication_crash_clears_only_the_stale_owned_lock(tmp_path):
    store, run = ready_store(tmp_path, True)
    crash_application(tmp_path, run, "completed")
    previous = store.load_apply(_APPLY_ID)
    assert previous["state"] == "applied"
    assert (store.base_path / "locks/apply.lock").is_file()
    result = recover(store)
    assert result == previous
    assert (tmp_path / "src/App.tsx").read_bytes() == b"new\n"
    assert (tmp_path / "src/New.tsx").read_bytes() == b"created\n"
    assert not (store.base_path / "locks/apply.lock").exists()


@pytest.mark.parametrize("restored_operation", ["update", "create"])
def test_restore_directory_sync_failure_cannot_be_acknowledged_by_matching_bytes(
    tmp_path, restored_operation
):
    import os
    import stat

    from ddk.services import artifact_applier as module

    store, run = ready_store(tmp_path, True, create_first=restored_operation == "create")
    original_write = module.atomic_write
    original_sync = os.fsync
    failed = False
    faults = []

    def fail_write(path, payload, *args, **kwargs):
        nonlocal failed
        failed_path = "src/App.tsx" if restored_operation == "create" else "src/New.tsx"
        if path == tmp_path / failed_path:
            failed = True
            raise OSError("injected application failure")
        return original_write(path, payload, *args, **kwargs)

    def fail_sync(descriptor):
        info = os.fstat(descriptor)
        restored = (
            (tmp_path / "src/App.tsx").read_bytes() == b"old\n"
            if restored_operation == "update"
            else not (tmp_path / "src/New.tsx").exists()
        )
        if (
            failed
            and restored
            and stat.S_ISDIR(info.st_mode)
            and info.st_ino == (tmp_path / "src").stat().st_ino
        ):
            faults.append("source directory sync failure")
            raise OSError(faults[-1])
        return original_sync(descriptor)

    with (
        patch.object(module, "atomic_write", side_effect=fail_write),
        patch("os.fsync", side_effect=fail_sync),
    ):
        result = apply(store, run)
    assert faults
    assert result["state"] == "unknown"
    assert (store.base_path / "locks/apply.lock").is_file()
    assert store.load_apply(_APPLY_ID) == result
