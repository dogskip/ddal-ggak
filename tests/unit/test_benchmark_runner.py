"""Preparing a comparison must not silently grant project execution or overwrite output."""

import asyncio
import subprocess
import sys
from argparse import Namespace
from pathlib import Path
from urllib.request import urlopen

import pytest
from scripts import paired_benchmark as runner

from ddk.adapters.subprocess_preview import SubprocessPreviewLauncher
from ddk.models.verified_change import canonical_json, decode_json, record_digest
from ddk.services.case_bootstrapper import CaseBootstrapper
from ddk.services.source_snapshot import SnapshotFile, SourceSnapshot, manifest_digest
from ddk.services.verified_change_store import VerifiedChangeStore

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/paired_benchmark.py"


@pytest.mark.parametrize("command", ["oracle", "_worker"])
def test_execution_requires_explicit_trusted_local(command, tmp_path):
    if command == "oracle":
        arguments = [
            "oracle",
            "--task",
            "hyperapp-events",
            "--repo",
            str(tmp_path),
            "--seed",
            "1729",
            "--arm",
            "ddk",
        ]
    else:
        arguments = ["_worker", "hyperapp-events", str(tmp_path)]
    result = subprocess.run(
        [sys.executable, str(SCRIPT), *arguments], capture_output=True, text=True
    )
    assert result.returncode in (3, 4)
    assert list(tmp_path.iterdir()) == []


def test_preparation_preserves_existing_output(tmp_path):
    destination = tmp_path / "existing"
    destination.mkdir()
    original = destination / "keep.txt"
    original.write_text("keep")
    arguments = [sys.executable, str(SCRIPT), "prepare", "--out", str(destination)]
    for source in ["click", "clsx", "hyperapp"]:
        arguments += ["--source", source + "=" + str(tmp_path)]
    result = subprocess.run(arguments, capture_output=True, text=True)
    assert result.returncode == 4
    assert original.read_text() == "keep"
    assert list(destination.iterdir()) == [original]


@pytest.fixture
def preparation(tmp_path, monkeypatch):
    import hashlib

    plan, _ = runner.corpus()
    snapshots = {}
    for task in plan["tasks"]:
        content = (task["before"] + "\n").encode()
        if task["id"] == "click-short-name":
            content += (task["after"] + "\n").encode()
        source = SnapshotFile(
            task["source_path"], content, hashlib.sha256(content).hexdigest(), 0o644, len(content)
        )
        task["source_sha256"] = source.sha256
        snapshots[task["commit"]] = SourceSnapshot((source,), manifest_digest([source]))
        task["source_tree_sha256"] = snapshots[task["commit"]].tree_sha256
    monkeypatch.setattr(runner, "corpus", lambda: (plan, record_digest(plan)))
    monkeypatch.setattr(runner, "capture_git_source", lambda repo, ref, **kw: snapshots[ref])
    destination = tmp_path / "comparison"
    assert (
        runner.prepare(
            Namespace(
                source=[name + "=" + str(tmp_path) for name in ("click", "clsx", "hyperapp")],
                out=destination,
            )
        )
        == 0
    )
    return destination / "preparation.json", plan


async def test_preparation_provides_reviewable_drafts_without_compiling_cases(preparation):
    import hashlib

    path, plan = preparation
    manifest = decode_json(path.read_bytes())
    assert manifest["status"] == "criteria-approval-required"
    assert len(manifest["rows"]) == 18 and manifest["model_calls"] == 0
    assert set(manifest["case_drafts"]) == {task["id"] for task in plan["tasks"]}
    for task in plan["tasks"]:
        reference = manifest["case_drafts"][task["id"]]
        draft_bytes = (path.parent / reference["path"]).read_bytes()
        assert hashlib.sha256(draft_bytes).hexdigest() == reference["sha256"]
        draft = decode_json(draft_bytes)
        assert draft["draft"] is True and draft["scope_paths"] == [task["source_path"]]
        assert {check["role"] for check in draft["checks"]} == {"target", "preserve"}
        assert draft["limits"]["max_provider_requests"] == draft["limits"]["budget_micro_usd"] == 0
        for row in (row for row in manifest["rows"] if row["task_id"] == task["id"]):
            candidate = path.parent / row["candidate"]
            result = await CaseBootstrapper(candidate).initialize(
                task["request"], configuration=draft
            )
            assert result["actions"][0]["code"] == "draft_criteria_unapproved"
            assert not (candidate / ".ddk").exists()
            fixture = candidate / "ddk_benchmark_fixture.py"
            assert hashlib.sha256(fixture.read_bytes()).hexdigest() == plan["fixture_sha256"]


def test_sealing_without_exact_draft_approvals_writes_nothing(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "seal",
            "--preparation",
            str(tmp_path / "missing.json"),
            "--out",
            str(tmp_path / "sealed.json"),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 4 and "exact_draft_approvals_required" in result.stderr
    assert list(tmp_path.iterdir()) == []


async def test_sealing_reuses_the_same_case_for_three_independent_contexts(
    preparation, monkeypatch
):
    from tests.unit.adapters.test_verified_browser import environment

    path, plan = preparation
    manifest = decode_json(path.read_bytes())
    env = environment()
    env["assurance"] = "trusted-local"

    async def observed(repo):
        return env, None

    monkeypatch.setattr(runner, "observe_environment", observed)
    output = path.parent / "sealed.json"
    approvals = [
        f"{name}={reference['sha256']}" for name, reference in manifest["case_drafts"].items()
    ]
    assert await runner.seal(Namespace(preparation=path, approved_draft=approvals, out=output)) == 0
    sealed = decode_json(output.read_bytes())
    assert sealed["execution_approved"] is False and sealed["provider_approved"] is False
    assert sealed["calibrated"] is False and sealed["model_calls"] == 0
    assert set(sealed["cases"]) == {task["id"] for task in plan["tasks"]}
    for row in manifest["rows"]:
        candidate = path.parent / row["candidate"]
        if row["arm"] == "plain":
            assert not (candidate / ".ddk").exists()
            continue
        reference = sealed["cases"][row["task_id"]]
        case = VerifiedChangeStore(candidate, create=False).case(reference["case_id"])
        assert record_digest(case) == reference["case_sha256"]
        assert case["scope_paths"] == [
            next(t for t in plan["tasks"] if t["id"] == row["task_id"])["source_path"]
        ]
    assert decode_json(path.read_bytes()) == manifest


@pytest.mark.parametrize(
    "fault",
    [
        "approval",
        "changed-source",
        "duplicate-row",
        "draft-path",
        "fixture",
        "criteria",
        "forged-tree",
        "draft-symlink",
    ],
)
async def test_invalid_sealing_inputs_cannot_create_cases(preparation, tmp_path, fault):
    import hashlib

    path, plan = preparation
    manifest = decode_json(path.read_bytes())
    approvals = [
        f"{name}={reference['sha256']}" for name, reference in manifest["case_drafts"].items()
    ]
    if fault == "approval":
        approvals[0] = approvals[0].split("=")[0] + "=" + "0" * 64
    elif fault == "changed-source":
        candidate = path.parent / manifest["rows"][-1]["candidate"]
        (candidate / "extra.txt").write_text("unreviewed change")
    elif fault == "duplicate-row":
        manifest["rows"][-1] = manifest["rows"][0]
    elif fault == "draft-path":
        next(iter(manifest["case_drafts"].values()))["path"] = "../outside.json"
    elif fault == "fixture":
        candidate = path.parent / manifest["rows"][0]["candidate"]
        (candidate / "ddk_benchmark_fixture.py").write_text("changed")
    elif fault == "criteria":
        name, reference = next(iter(manifest["case_drafts"].items()))
        draft_path = path.parent / reference["path"]
        draft = decode_json(draft_path.read_bytes())
        draft["checks"] = draft["checks"][:1]
        draft_path.write_bytes(canonical_json(draft))
        approvals[0] = name + "=" + hashlib.sha256(draft_path.read_bytes()).hexdigest()
    elif fault == "forged-tree":
        from ddk.services.source_snapshot import capture_source

        task = plan["tasks"][0]
        for row in manifest["rows"]:
            if row["task_id"] == task["id"]:
                candidate = path.parent / row["candidate"]
                (candidate / "extra.txt").write_text("undeclared source")
                row["initial_tree_sha256"] = capture_source(candidate).tree_sha256
    else:
        reference = next(iter(manifest["case_drafts"].values()))
        draft_path = path.parent / reference["path"]
        external = tmp_path / "external.json"
        external.write_bytes(draft_path.read_bytes())
        draft_path.unlink()
        draft_path.symlink_to(external)
    path.write_bytes(canonical_json(manifest))
    with pytest.raises(ValueError):
        await runner.seal(
            Namespace(preparation=path, approved_draft=approvals, out=tmp_path / "sealed.json")
        )
    assert not (tmp_path / "sealed.json").exists()
    assert not list(path.parent.glob("*/*/*/.ddk"))


@pytest.mark.parametrize("mode", ["candidate", "missing", "error", "empty"])
async def test_python_fixture_uses_candidate_code_and_displays_safe_failure_states(tmp_path, mode):
    source = tmp_path / "src/click"
    source.mkdir(parents=True)
    if mode != "missing":
        body = {
            "candidate": "return 'candidate-short' if shorten else 'candidate-full'",
            "error": "raise RuntimeError('PRIVATE_EXCEPTION_DETAIL')",
            "empty": "return ''",
        }[mode]
        (source / "__init__.py").write_text(
            "def format_filename(value, shorten=False):\n    " + body + "\n"
        )
    fixture = (
        Path(__file__).resolve().parents[2] / "src/ddk/assets/benchmarks/browser-fixture.py.txt"
    )
    (tmp_path / "ddk_benchmark_fixture.py").write_bytes(fixture.read_bytes())
    session = await SubprocessPreviewLauncher().start(
        ["python3", "ddk_benchmark_fixture.py", "click-short-name", "{port}"], tmp_path
    )

    def response(route):
        with urlopen(session.url + route, timeout=5) as connection:
            return connection.read(1024**2).decode()

    try:
        target, preserved = await asyncio.gather(
            asyncio.to_thread(response, "target"), asyncio.to_thread(response, "preserve")
        )
        for route, content in (("short", target), ("full", preserved)):
            expected = (
                f"candidate-{route}"
                if mode == "candidate"
                else "No result"
                if mode == "empty"
                else "Source execution failed"
            )
            assert expected in content and "PRIVATE_EXCEPTION_DETAIL" not in content
    finally:
        await session.stop()


def test_preparation_cannot_execute_inherited_git_hooks(preparation, tmp_path, monkeypatch):
    import json
    import shlex

    hooks = tmp_path / "owner-hooks"
    hooks.mkdir()
    canary = tmp_path / "unexpected-hook-execution"
    hook = hooks / "post-commit"
    hook.write_text("#!/bin/sh\nprintf executed > " + shlex.quote(str(canary)) + "\n")
    hook.chmod(0o755)
    config = tmp_path / "owner.gitconfig"
    config.write_text("[core]\n\thooksPath = " + json.dumps(str(hooks)) + "\n")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    assert (
        runner.prepare(
            Namespace(
                source=[name + "=" + str(tmp_path) for name in ("click", "clsx", "hyperapp")],
                out=tmp_path / "isolated-preparation",
            )
        )
        == 0
    )
    assert not canary.exists()
