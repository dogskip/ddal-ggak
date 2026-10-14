"""Evaluate frozen checks through two policy-verified, locally owned containers."""

from __future__ import annotations

import asyncio
import hashlib
import math
import tempfile
import time
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from ddk.adapters.build_runner import BuildResult
from ddk.adapters.verified_browser import BrowserSettings, validate_fragment
from ddk.adapters.verified_isolation import (
    POLICY_SHA256,
    IsolationRequest,
    IsolationSession,
    LocalDockerIsolation,
)
from ddk.adapters.verified_reports import check_result, command_report
from ddk.adapters.verified_worker import PORT
from ddk.models.verified_change import (
    Record,
    canonical_json,
    contract_validator,
    decode_json,
    safe_path,
)
from ddk.security.file_access import read_regular
from ddk.security.repo_paths import ensure_distinct_paths
from ddk.services.source_snapshot import SnapshotFile, source_matches
from ddk.services.verified_change_engine import (
    EvaluationArtifact,
    EvaluationOutcome,
    EvaluationRequest,
)

_MODULES = (
    "adapters/verified_worker.py",
    "adapters/verified_browser.py",
    "adapters/screenshot_diff_local.py",
    "adapters/screenshot_diff.py",
    "models/verified_change.py",
    "security/repo_paths.py",
    "security/secret_paths.py",
    "security/file_access.py",
)
_ENTRY = (
    "python3",
    "-I",
    "-c",
    "import sys;sys.path.insert(0,'/criteria/worker');"
    "from ddk.adapters.verified_worker import main;main()",
)
_NODE_ENV = (
    "const cp=require('child_process');console.log(JSON.stringify({"
    "node_version:process.versions.node,"
    "package_manager_version:cp.execFileSync(process.argv[1],['--version'],"
    "{encoding:'utf8',timeout:5000}).trim()}))"
)


def write_worker_bundle(criteria: Path) -> str:
    source = Path(__file__).resolve().parents[1]
    destination = criteria / "worker/ddk"
    for package in ("", "adapters", "models", "security"):
        directory = destination / package
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "__init__.py").write_bytes(b"")
    rows: list[Record] = []
    for name in _MODULES:
        data = read_regular(source / name, 2 * 1024**2)
        (destination / name).write_bytes(data)
        rows.append({"path": name, "sha256": hashlib.sha256(data).hexdigest()})
    schema = canonical_json(contract_validator().schema)
    path = destination / "assets/verified-change/contract.schema.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(schema)
    rows.append(
        {
            "path": "assets/verified-change/contract.schema.json",
            "sha256": hashlib.sha256(schema).hexdigest(),
        }
    )
    digest = hashlib.sha256(canonical_json(rows)).hexdigest()
    (criteria / "worker-manifest.json").write_bytes(
        canonical_json({"sha256": digest, "files": rows})
    )
    return digest


def _intact(request: EvaluationRequest, app: Path) -> bool:
    return source_matches(
        app,
        request.snapshot,
        max_file_bytes=request.limits["max_file_bytes"],
        max_total_bytes=min(200 * 1024**2, request.limits["max_artifact_bytes"]),
    )


def _unavailable(
    request: EvaluationRequest, detail: str, *, cleanup: bool = True
) -> EvaluationOutcome:
    artifact = EvaluationArtifact(
        f"{request.phase}-isolation",
        "log",
        f"artifacts/{request.phase}/isolation.log",
        detail.encode(),
    )
    results = tuple(
        check_result(request, check, "isolation_unavailable") for check in request.checks
    )
    for result in results:
        result["artifact_ids"] = [artifact.artifact_id]
    return EvaluationOutcome(
        results,
        (artifact,),
        None,
        request.environment_sha256,
        request.evaluator_sha256,
        request.input_tree_sha256,
        cleanup,
    )


async def evaluate_isolated(
    request: EvaluationRequest,
    *,
    plan: Record,
    files: Mapping[str, SnapshotFile],
    settings: BrowserSettings,
    isolation: LocalDockerIsolation,
) -> EvaluationOutcome:
    environment = settings.environment
    availability = await isolation.preflight(deadline_ns=request.deadline_ns)
    if not availability.available:
        return _unavailable(request, availability.reason)
    try:
        if (
            environment["assurance"] != "isolated"
            or environment["endpoint_kind"] != "local"
            or environment["runtime_name"] != "docker"
            or environment["runtime_version"] != availability.runtime_version
            or environment["policy_sha256"] != POLICY_SHA256
            or environment["package_manager"] not in {"npm", "pnpm", "yarn", "bun"}
            or any(
                not isinstance(environment[key], str)
                for key in ("app_image_sha256", "checker_image_sha256")
            )
        ):
            raise ValueError("isolated_environment_mismatch")
        locks = [
            file
            for file in request.snapshot.files
            if file.path
            in {"package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lock", "bun.lockb"}
        ]
        if len(locks) != 1 or locks[0].sha256 != environment["lockfile_sha256"]:
            raise ValueError("lockfile_environment_mismatch")
    except (KeyError, TypeError, ValueError) as error:
        return _unavailable(request, str(error))

    results: list[Record] = []
    artifacts: list[EvaluationArtifact] = []
    cleanup, intact, verified = True, True, True
    environment_verified = False
    output_bytes: int | None = 0
    artifact_bytes = 0
    halted: str | None = None

    def retain(artifact: EvaluationArtifact) -> None:
        nonlocal artifact_bytes, halted
        if artifact_bytes + len(artifact.content) > request.limits["max_artifact_bytes"]:
            halted = "artifact_limit"
            results[-1].update(status="unavailable", reason_code=halted)
            return
        artifacts.append(artifact)
        artifact_bytes += len(artifact.content)
        results[-1]["artifact_ids"].append(artifact.artifact_id)

    with tempfile.TemporaryDirectory(prefix="ddk-isolated-evaluate-") as folder:
        root = Path(folder).resolve()
        app = root / "app"
        app.mkdir(mode=0o700)
        for file in request.snapshot.files:
            path = app / file.path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(file.content)
            path.chmod(file.mode)
        if not _intact(request, app):
            return _unavailable(request, "private_copy_mismatch")
        criteria, output = root / "criteria", root / "results"
        criteria.mkdir()
        output.mkdir()
        inputs = criteria / "inputs"
        inputs.mkdir()
        for file in files.values():
            path = inputs / file.path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(file.content)
            path.chmod(0o400)
        worker_sha256 = write_worker_bundle(criteria)
        for index, check in enumerate(request.checks):
            reason = halted or ("cancelled" if request.cancelled() else None)
            if time.monotonic_ns() >= request.deadline_ns:
                reason = reason or "timeout"
            if reason:
                results.append(check_result(request, check, reason))
                continue
            if check["kind"] not in {"command", "test", "browser", "visual"}:
                results.append(check_result(request, check, "unsupported_check_kind"))
                continue
            started = time.monotonic_ns()
            deadline = min(
                request.deadline_ns,
                started + min(check["timeout_ms"], request.limits["step_timeout_ms"]) * 1_000_000,
            )
            browser = check["kind"] in {"browser", "visual"}
            command = (
                tuple(str(PORT) if arg == "{port}" else arg for arg in plan["preview_argv"])
                if browser
                else ("node", "-e", "setInterval(()=>{},1000)")
            )
            isolated_request = IsolationRequest(
                root,
                app,
                criteria,
                output,
                "sha256:" + environment["app_image_sha256"],
                "sha256:" + environment["checker_image_sha256"],
                command,
                _ENTRY,
                timeout_s=max(1, min(1800, math.ceil((deadline - time.monotonic_ns()) / 1e9))),
                cleanup_timeout_ms=min(10_000, request.limits["cleanup_timeout_ms"]),
            )
            results.append(check_result(request, check, "isolation_unavailable"))
            written = 0

            async def operation(
                session: IsolationSession,
                *,
                deadline: int = deadline,
                browser: bool = browser,
                check: Record = check,
                started: int = started,
                index: int = index,
                output: Path = output,
            ) -> BuildResult:
                nonlocal written, halted, output_bytes, environment_verified

                environment_verified = False

                def remaining() -> float:
                    return max(0.001, (deadline - time.monotonic_ns()) / 1e9)

                observed = await session.checker(
                    _ENTRY,
                    timeout_s=remaining(),
                    stdin=canonical_json(
                        {"mode": "probe", "browser_executable": plan["browser_executable"]}
                    ),
                )
                if not observed.success:
                    return observed
                metadata = decode_json(observed.stdout.encode())
                if (
                    not metadata
                    or any(environment.get(key) != value for key, value in metadata.items())
                    or set(metadata)
                    != {
                        "os_name",
                        "os_version",
                        "architecture",
                        "python_version",
                        "playwright_version",
                        "browser_version",
                        "browser_binary_sha256",
                        "font_manifest_sha256",
                    }
                ):
                    raise ValueError("checker_environment_mismatch")
                observed = await session.app(
                    ("node", "-e", _NODE_ENV, environment["package_manager"]), timeout_s=remaining()
                )
                if not observed.success:
                    return observed
                metadata = decode_json(observed.stdout.encode())
                if set(metadata) != {"node_version", "package_manager_version"} or any(
                    environment[key] != value for key, value in metadata.items()
                ):
                    raise ValueError("app_environment_mismatch")
                environment_verified = True
                if not browser:
                    answer = await session.app(tuple(check["command_argv"]), timeout_s=remaining())
                    results[-1] = command_report(request, check, answer)
                    results[-1]["duration_ms"] = (time.monotonic_ns() - started) // 1_000_000
                    written += len(answer.stdout.encode()) + len(answer.stderr.encode())
                    if answer.returncode in {124, 125}:
                        output_bytes = None
                        halted = "output_unknown"
                    retain(
                        EvaluationArtifact(
                            f"{request.phase}-command-{index}",
                            "log",
                            f"artifacts/{request.phase}/command-{index}.log",
                            (answer.stdout + "\n" + answer.stderr).encode(),
                        )
                    )
                    return BuildResult(True, "", "", 0)
                answer = await session.checker(
                    _ENTRY,
                    timeout_s=remaining(),
                    stdin=canonical_json(
                        {
                            "mode": "flow",
                            "plan": plan,
                            "environment": environment,
                            "check": check,
                            "phase": request.phase,
                            "timeout_ms": max(1, int(remaining() * 1000)),
                            "cleanup_timeout_ms": request.limits["cleanup_timeout_ms"],
                            "max_artifact_bytes": request.limits["max_artifact_bytes"]
                            - artifact_bytes,
                        }
                    ),
                )
                if not answer.success:
                    return answer
                report = decode_json(answer.stdout.encode())
                if (
                    set(report) != {"result", "artifacts", "cleanup_complete"}
                    or type(report["cleanup_complete"]) is not bool
                ):
                    raise ValueError("invalid_worker_report")
                validate_fragment(report["result"], "CheckResult")
                observed_result = report["result"]
                if (
                    observed_result["check_id"] != check["check_id"]
                    or observed_result["phase"] != request.phase
                    or observed_result["evidence_origin"] != "trusted-observer"
                ):
                    raise ValueError("worker_result_scope_mismatch")
                if not report["cleanup_complete"]:
                    raise ValueError("browser_cleanup_failed")
                if (
                    not isinstance(report["artifacts"], list)
                    or len(cast(list[object], report["artifacts"])) > 1000
                ):
                    raise ValueError("invalid_worker_artifacts")
                rows = cast(list[Record], report["artifacts"])
                for row in rows:
                    validate_fragment(row, "Artifact")
                ensure_distinct_paths([row["path"] for row in rows])
                if observed_result["artifact_ids"] != [row["artifact_id"] for row in rows] or len(
                    set(observed_result["artifact_ids"])
                ) != len(rows):
                    raise ValueError("worker_artifact_mismatch")
                results[-1] = observed_result
                results[-1]["artifact_ids"] = []
                for row in rows:
                    if not safe_path(row["path"]):
                        raise ValueError("unsafe_observation_path")
                    data = read_regular(
                        output / row["path"],
                        min(row["size_bytes"], request.limits["max_artifact_bytes"]),
                    )
                    if (
                        len(data) != row["size_bytes"]
                        or hashlib.sha256(data).hexdigest() != row["sha256"]
                    ):
                        raise ValueError("observation_hash_mismatch")
                    retain(
                        EvaluationArtifact(
                            row["artifact_id"],
                            row["kind"],
                            f"artifacts/{request.phase}/browser-{index}/" + row["path"],
                            data,
                            True,
                            False,
                        )
                    )
                return BuildResult(True, "", "", 0)

            task = asyncio.create_task(
                isolation.execute(isolated_request, b"", operation=operation)
            )
            try:
                while not task.done():
                    await asyncio.wait({task}, timeout=0.05)
                    if request.cancelled():
                        task.cancel()
                outcome = await task
            except asyncio.CancelledError:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                raise
            except (OSError, ValueError, RuntimeError) as error:
                results[-1].update(status="unavailable", reason_code="isolation_unavailable")
                halted, output_bytes = "isolation_unavailable", None
                cleanup, verified = False, False
                retain(
                    EvaluationArtifact(
                        f"{request.phase}-isolation-{index}",
                        "log",
                        f"artifacts/{request.phase}/isolation-{index}.log",
                        str(error).encode(),
                    )
                )
                continue
            cleanup = cleanup and outcome.cleanup_complete
            verified = verified and outcome.policy_verified
            if (
                not outcome.completed
                or not outcome.policy_verified
                or not outcome.app_output_complete
                or outcome.returncode != 0
            ):
                results[-1].update(status="unavailable", reason_code="isolation_unavailable")
                halted, output_bytes = "isolation_unavailable", None
            if not cleanup:
                halted = "cleanup_failed"
                results[-1].update(status="unavailable", reason_code=halted)
            if not _intact(request, app):
                intact, halted = False, "source_changed"
                results[-1].update(status="unavailable", reason_code=halted)
            if outcome.app_stdout or outcome.app_stderr or outcome.reason or outcome.stderr:
                retain(
                    EvaluationArtifact(
                        f"{request.phase}-isolation-{index}",
                        "log",
                        f"artifacts/{request.phase}/isolation-{index}.log",
                        (
                            outcome.reason
                            + "\n"
                            + outcome.stderr
                            + "\n"
                            + outcome.app_stdout
                            + "\n"
                            + outcome.app_stderr
                        ).encode(),
                    )
                )
            retain(
                EvaluationArtifact(
                    f"{request.phase}-policy-{index}",
                    "data",
                    f"artifacts/{request.phase}/policy-{index}.json",
                    canonical_json({"worker_sha256": worker_sha256, "policy": outcome.evidence}),
                )
            )
            if output_bytes is not None:
                output_bytes += (
                    written + len(outcome.app_stdout.encode()) + len(outcome.app_stderr.encode())
                )
                if output_bytes > request.limits["max_output_bytes"]:
                    halted = "output_limit"
                    results[-1].update(status="unavailable", reason_code=halted)
        intact = intact and _intact(request, app)
    return EvaluationOutcome(
        tuple(results),
        tuple(artifacts),
        "isolated" if cleanup and verified else None,
        request.environment_sha256 if environment_verified else None,
        request.evaluator_sha256,
        request.input_tree_sha256 if intact else None,
        cleanup,
        output_bytes=output_bytes,
    )
