"""The default evaluator transports approved checks without host execution."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from unittest.mock import AsyncMock

import pytest

from ddk.adapters.build_runner import BuildResult
from ddk.adapters.verified_evaluator import VerifiedEvaluator
from ddk.adapters.verified_isolation import IsolationAvailability, IsolationResult
from ddk.models.verified_change import canonical_json
from ddk.services.source_snapshot import capture_source, manifest_digest
from tests.unit.adapters.test_verified_evaluator import request_for
from tests.unit.test_verified_change_engine import fixed_file

METADATA = {
    "os_name": "Linux",
    "os_version": "fixed-kernel",
    "architecture": "aarch64",
    "python_version": "3.12.13",
    "playwright_version": "1.61.0",
    "browser_version": "143.0.0.0",
    "browser_binary_sha256": "c" * 64,
    "font_manifest_sha256": "d" * 64,
}


def isolated_request(tmp_path, **kwargs):
    from ddk.adapters.verified_isolation import POLICY_SHA256

    request, original, env = request_for(tmp_path, **kwargs)
    (original / "package-lock.json").write_text("{}")
    snapshot = capture_source(original)
    env.update(
        METADATA,
        assurance="isolated",
        endpoint_kind="local",
        runtime_name="docker",
        runtime_version="29.8.2",
        package_manager="npm",
        package_manager_version="10.9.3",
        node_version="22.18.0",
        app_image_sha256="a" * 64,
        checker_image_sha256="b" * 64,
        lockfile_sha256=hashlib.sha256(b"{}").hexdigest(),
        policy_sha256=POLICY_SHA256,
    )
    frozen = (
        *request.frozen_inputs[:2],
        fixed_file("environment/environment.json", canonical_json(env)),
    )
    return (
        replace(
            request,
            snapshot=snapshot,
            input_tree_sha256=snapshot.tree_sha256,
            frozen_inputs=frozen,
            environment_sha256=manifest_digest(frozen[2:]),
        ),
        original,
        env,
    )


class Session:
    def __init__(self, command=None):
        self.command = command or BuildResult(True, "ran\n", "", 0)
        self.calls = []
        self.metadata = dict(METADATA)

    async def app(self, argv, *, timeout_s, stdin=None):
        self.calls.append(("app", argv))
        if "versions.node" in " ".join(argv):
            return BuildResult(
                True,
                json.dumps({"node_version": "22.18.0", "package_manager_version": "10.9.3"}),
                "",
                0,
            )
        return self.command

    async def checker(self, argv, *, timeout_s, stdin=None):
        self.calls.append(("checker", argv))
        assert "-I" in argv and "/criteria/worker" in " ".join(argv)
        return BuildResult(True, json.dumps(self.metadata), "", 0)


class Isolation:
    def __init__(self, session=None):
        self.session = session or Session()
        self.requests = []
        self.cleanup = True

    async def preflight(self, **kwargs):
        return IsolationAvailability(True, code=None, runtime_version="29.8.2")

    async def execute(self, request, data, *, operation):
        self.requests.append(request)
        assert (request.criteria_dir / "worker/ddk/adapters/verified_browser.py").is_file()
        result = await operation(self.session)
        return IsolationResult(
            completed=self.cleanup,
            policy_verified=True,
            cleanup_complete=self.cleanup,
            code=None if self.cleanup else "isolation_unavailable",
            reason="" if self.cleanup else "isolation_cleanup_failed",
            stdout=result.stdout,
            stderr=result.stderr,
            returncode=result.returncode,
        )


async def test_default_evaluator_executes_command_in_verified_app_and_preserves_original(
    tmp_path, monkeypatch
):
    request, original, _ = isolated_request(tmp_path)
    host = AsyncMock()
    monkeypatch.setattr("ddk.adapters.verified_evaluator.SubprocessBuildRunner", lambda: host)
    isolation = Isolation()
    outcome = await VerifiedEvaluator(isolation=isolation).evaluate(request)
    assert outcome.assurance == "isolated"
    assert outcome.results[0]["status"] == "passed"
    assert outcome.results[0]["evidence_origin"] == "project-report"
    assert outcome.cleanup_complete and outcome.input_tree_sha256 == request.input_tree_sha256
    assert isolation.requests[0].app_image == "sha256:" + "a" * 64
    assert isolation.requests[0].app_dir != original
    assert not isolation.requests[0].app_dir.exists()
    host.run.assert_not_called()
    assert capture_source(original).tree_sha256 == request.input_tree_sha256


@pytest.mark.parametrize(
    "field", ["python_version", "font_manifest_sha256", "browser_binary_sha256", "os_version"]
)
async def test_actual_environment_mismatch_blocks_project_command(tmp_path, field):
    request, _, _ = isolated_request(tmp_path)
    session = Session()
    session.metadata[field] = "different"
    outcome = await VerifiedEvaluator(isolation=Isolation(session)).evaluate(request)
    assert outcome.results[0]["status"] == "unavailable"
    assert not any(argv == tuple(request.checks[0]["command_argv"]) for role, argv in session.calls)
    assert outcome.environment_sha256 is None


async def test_cleanup_failure_cannot_supply_isolated_success(tmp_path):
    request, _, _ = isolated_request(tmp_path)
    isolation = Isolation()
    isolation.cleanup = False
    outcome = await VerifiedEvaluator(isolation=isolation).evaluate(request)
    assert not outcome.cleanup_complete
    assert outcome.results[0]["status"] == "unavailable"


async def test_unverified_policy_cannot_report_isolated_assurance(tmp_path):
    request, _, _ = isolated_request(tmp_path)
    isolation = Isolation()
    original = isolation.execute

    async def execute(*args, **kwargs):
        return replace(await original(*args, **kwargs), policy_verified=False, completed=False)

    isolation.execute = execute
    outcome = await VerifiedEvaluator(isolation=isolation).evaluate(request)
    assert outcome.assurance is None


async def test_output_cap_stops_later_checks_and_preserves_observed_size(tmp_path):
    request, _, _ = isolated_request(tmp_path)
    later = dict(request.checks[0], check_id="later")
    request = replace(
        request, checks=(*request.checks, later), limits={**request.limits, "max_output_bytes": 3}
    )
    isolation = Isolation(Session(BuildResult(True, "한국어", "", 0)))
    outcome = await VerifiedEvaluator(isolation=isolation).evaluate(request)
    assert outcome.results[0]["reason_code"] == "output_limit"
    assert outcome.results[1]["status"] == "unavailable"
    assert outcome.output_bytes == 9 and len(isolation.requests) == 1


async def test_mutating_app_copy_blocks_later_checks_and_invalidates_input_hash(tmp_path):
    request, original, _ = isolated_request(tmp_path)
    request = replace(request, checks=(*request.checks, dict(request.checks[0], check_id="later")))
    isolation = Isolation()
    execute = isolation.execute

    async def mutate(req, *args, **kwargs):
        result = await execute(req, *args, **kwargs)
        (req.app_dir / "index.html").write_text("changed")
        return result

    isolation.execute = mutate
    outcome = await VerifiedEvaluator(isolation=isolation).evaluate(request)
    assert outcome.input_tree_sha256 is None
    assert outcome.results[0]["reason_code"] == "source_changed"
    assert len(isolation.requests) == 1
    assert capture_source(original).tree_sha256 == request.input_tree_sha256


async def test_multiple_checks_reuse_private_source_without_recreating_originals(tmp_path):
    request, _, _ = isolated_request(tmp_path)
    request = replace(request, checks=(*request.checks, dict(request.checks[0], check_id="later")))
    isolation = Isolation()
    outcome = await VerifiedEvaluator(isolation=isolation).evaluate(request)
    assert len(isolation.requests) == 2
    assert all(row["status"] == "passed" for row in outcome.results)


async def test_failed_worker_start_stops_later_checks_even_if_container_policy_passed(tmp_path):
    request, _, _ = isolated_request(tmp_path)
    request = replace(request, checks=(*request.checks, dict(request.checks[0], check_id="later")))
    session = Session()

    async def failed(*args, **kwargs):
        return BuildResult(False, "", "worker failed", 1)

    session.checker = failed
    isolation = Isolation(session)
    outcome = await VerifiedEvaluator(isolation=isolation).evaluate(request)
    assert len(isolation.requests) == 1
    assert outcome.environment_sha256 is None
    assert all(row["status"] == "unavailable" for row in outcome.results)
