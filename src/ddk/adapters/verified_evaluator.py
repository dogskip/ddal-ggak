"""Evaluate frozen checks in owned copies with an explicit execution grant."""

from __future__ import annotations

import asyncio
import hashlib
import io
import math
import platform
import tempfile
import time
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Literal, cast

from PIL import Image

from ddk.adapters.subprocess_build_runner import SubprocessBuildRunner
from ddk.adapters.subprocess_preview import SubprocessPreviewLauncher
from ddk.adapters.verified_browser import BrowserSettings, VisualReference, run_flow
from ddk.adapters.verified_isolation import LocalDockerIsolation
from ddk.models.verified_change import (
    Record,
    decode_json,
    parse_record,
    record_digest,
    safe_path,
)
from ddk.security.file_access import read_regular
from ddk.security.repo_paths import ensure_distinct_paths
from ddk.services.source_snapshot import SnapshotFile, capture_source, manifest_digest
from ddk.services.verified_change_engine import (
    EvaluationArtifact,
    EvaluationOutcome,
    EvaluationRequest,
)

EXECUTION_PLAN_PATH = "criteria/execution.json"
_PLAN_KEYS = {
    "format",
    "environment_path",
    "criteria_paths",
    "environment_paths",
    "preview_argv",
    "frozen_time",
    "browser_executable",
    "visual_references",
}
_MAX_BYTES = 200 * 1024 * 1024


@dataclass(frozen=True)
class _Inputs:
    plan: Record
    files: dict[str, SnapshotFile]
    settings: BrowserSettings
    references: dict[str, VisualReference]


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise ValueError(code)


def _files(
    files: tuple[SnapshotFile, ...], *, max_file_bytes: int, max_total_bytes: int
) -> dict[str, SnapshotFile]:
    ensure_distinct_paths([item.path for item in files])
    _require(sum(len(item.content) for item in files) <= max_total_bytes, "input_size_limit")
    for item in files:
        _require(safe_path(item.path), "unsafe_input_path")
        _require(type(item.mode) is int and 0 <= item.mode <= 0o777, "invalid_input_mode")
        _require(len(item.content) <= max_file_bytes, "input_file_size_limit")
        _require(
            len(item.content) == item.size_bytes
            and hashlib.sha256(item.content).hexdigest() == item.sha256,
            "input_hash_mismatch",
        )
    return {item.path: item for item in files}


def _paths(value: object, files: dict[str, SnapshotFile]) -> list[str]:
    _require(isinstance(value, list), "invalid_manifest_paths")
    paths = cast(list[object], value)
    _require(bool(paths), "invalid_manifest_paths")
    _require(all(isinstance(path, str) and path in files for path in paths), "missing_fixed_input")
    result = cast(list[str], paths)
    ensure_distinct_paths(result)
    return result


def _argv(value: object, *, allow_empty: bool = False) -> list[str]:
    _require(isinstance(value, list), "invalid_command_argv")
    parts = cast(list[object], value)
    _require(allow_empty or bool(parts), "invalid_command_argv")
    _require(
        len(parts) <= 100
        and all(
            isinstance(arg, str) and 0 < len(arg) <= 2048 and "\x00" not in arg for arg in parts
        ),
        "invalid_command_argv",
    )
    return cast(list[str], parts)


def _prepare(request: EvaluationRequest, *, trusted_local: bool) -> _Inputs:
    _require(request.phase in {"baseline", "candidate"}, "invalid_result_phase")
    for key in (
        "max_file_bytes",
        "max_artifact_bytes",
        "max_output_bytes",
        "cleanup_timeout_ms",
        "step_timeout_ms",
    ):
        value = request.limits[key]
        _require(
            type(value) is int and value >= (0 if key == "max_output_bytes" else 1),
            "invalid_execution_limits",
        )
    file_limits = {
        "max_file_bytes": request.limits["max_file_bytes"],
        "max_total_bytes": min(_MAX_BYTES, request.limits["max_artifact_bytes"]),
    }
    source = _files(request.snapshot.files, **file_limits)
    _require(
        manifest_digest(source.values()) == request.snapshot.tree_sha256, "snapshot_hash_mismatch"
    )
    files = _files(request.frozen_inputs, **file_limits)
    _require(EXECUTION_PLAN_PATH in files, "execution_plan_missing")
    plan = decode_json(files[EXECUTION_PLAN_PATH].content)
    _require(
        set(plan) == _PLAN_KEYS and plan["format"] == "verified-evaluator/1",
        "invalid_execution_plan",
    )
    criteria = _paths(plan["criteria_paths"], files)
    environments = _paths(plan["environment_paths"], files)
    _require(not set(criteria).intersection(environments), "input_role_overlap")
    _require(EXECUTION_PLAN_PATH in criteria, "execution_plan_not_frozen")
    _require(
        manifest_digest(files[path] for path in criteria) == request.evaluator_sha256,
        "criteria_hash_mismatch",
    )
    _require(
        manifest_digest(files[path] for path in environments) == request.environment_sha256,
        "environment_hash_mismatch",
    )
    _require(
        isinstance(plan["environment_path"], str) and plan["environment_path"] in environments,
        "environment_missing",
    )
    environment = parse_record(files[plan["environment_path"]].content)
    _require(environment.get("record_type") == "environment", "environment_record_required")
    if trusted_local:
        _require(environment["assurance"] == "trusted-local", "environment_assurance_mismatch")
        _require(
            all(
                environment[key] == value
                for key, value in {
                    "os_name": platform.system(),
                    "os_version": platform.release(),
                    "architecture": platform.machine(),
                    "python_version": platform.python_version(),
                }.items()
            ),
            "environment_host_mismatch",
        )
    preview = _argv(plan["preview_argv"], allow_empty=True)
    _require(
        all("{port}" not in arg or arg == "{port}" for arg in preview), "embedded_preview_port"
    )
    _require(preview.count("{port}") == (1 if preview else 0), "preview_port_missing")
    _require(isinstance(plan["frozen_time"], str), "invalid_fixed_time")
    frozen = datetime.fromisoformat(plan["frozen_time"])
    _require(frozen.tzinfo is not None, "fixed_time_timezone_missing")
    executable = plan["browser_executable"]
    _require(
        executable is None or isinstance(executable, str) and Path(executable).is_absolute(),
        "invalid_browser_executable",
    )
    settings = BrowserSettings(
        environment=environment,
        environment_sha256=record_digest(environment),
        frozen_time=plan["frozen_time"],
        executable_path=executable,
        cleanup_timeout_ms=min(10_000, request.limits["cleanup_timeout_ms"]),
        max_artifact_bytes=min(_MAX_BYTES, request.limits["max_artifact_bytes"]),
    )
    refs = plan["visual_references"]
    _require(isinstance(refs, list), "invalid_visual_references")
    references: dict[str, VisualReference] = {}
    for value in cast(list[object], refs):
        _require(isinstance(value, dict), "invalid_visual_reference")
        reference = cast(Record, value)
        _require(
            set(reference) == {"path", "viewport", "environment_sha256", "mask_sha256"},
            "invalid_visual_reference",
        )
        path = reference["path"]
        _require(
            isinstance(path, str) and path in files and path not in references,
            "reference_missing_or_duplicate",
        )
        _require(
            reference["environment_sha256"] == settings.environment_sha256,
            "reference_environment_mismatch",
        )
        _require(reference["mask_sha256"] is None, "mask_unsupported")
        _require(isinstance(reference["viewport"], dict), "invalid_reference_viewport")
        viewport = cast(Record, reference["viewport"])
        _require(
            set(viewport) == {"width", "height"}
            and all(type(viewport[key]) is int and 1 <= viewport[key] <= 16384 for key in viewport),
            "invalid_reference_viewport",
        )
        with Image.open(io.BytesIO(files[path].content)) as image:
            width, height = image.size
        _require(
            width == viewport["width"] and height == viewport["height"],
            "reference_viewport_mismatch",
        )
        references[path] = VisualReference(
            files[path].content,
            files[path].sha256,
            width,
            height,
            (viewport["width"], viewport["height"]),
            settings.environment_sha256,
        )
    ensure_distinct_paths([check["check_id"] for check in request.checks])
    for check in request.checks:
        path = check["definition_path"]
        _require(
            path in criteria and files[path].sha256 == check["definition_sha256"],
            "check_definition_mismatch",
        )
        if check["kind"] in {"command", "test"}:
            _argv(check["command_argv"])
        elif check["kind"] in {"browser", "visual"}:
            _require(bool(preview) and not check["command_argv"], "preview_command_missing")
    return _Inputs(plan, files, settings, references)


def _result(request: EvaluationRequest, check: Record, reason: str | None = None) -> Record:
    return {
        "check_id": check["check_id"],
        "phase": request.phase,
        "status": "unavailable",
        "exit_code": None,
        "executed_count": None,
        "failed_count": None,
        "skipped_count": None,
        "retry_count": 0,
        "duration_ms": 0,
        "reason_code": reason,
        "artifact_ids": [],
        "evidence_origin": "project-report"
        if check["kind"] in {"command", "test"}
        else "trusted-observer",
        "round_no": 0,
    }


def _stopped(request: EvaluationRequest) -> str | None:
    if time.monotonic_ns() >= request.deadline_ns:
        return "timeout"
    return "cancelled" if request.cancelled() else None


async def _command(
    request: EvaluationRequest, check: Record, app: Path, index: int
) -> tuple[Record, EvaluationArtifact, bool, int | None]:
    result = _result(request, check)
    started = time.monotonic_ns()
    deadline = min(
        request.deadline_ns,
        started + min(check["timeout_ms"], request.limits["step_timeout_ms"]) * 1_000_000,
    )
    timeout = max(0.001, (deadline - time.monotonic_ns()) / 1e9)
    output_bytes: int | None = 0
    try:
        async with asyncio.timeout(timeout):
            answer = await SubprocessBuildRunner().run(
                check["command_argv"], app, math.ceil(timeout)
            )
    except TimeoutError as error:
        cleanup = not _cleanup_failed(error)
        result["reason_code"] = "timeout" if cleanup else "cleanup_failed"
        payload = b"Command deadline exceeded; partial output size is unknown"
        output_bytes = None
    else:
        result["exit_code"] = answer.returncode
        result["status"] = "passed" if answer.success else "failed"
        result["reason_code"] = None if answer.success else "command_failed"
        cleanup = answer.returncode != 125
        payload = (answer.stdout + "\n" + answer.stderr).encode()
        output_bytes = len(answer.stdout.encode()) + len(answer.stderr.encode())
        if answer.returncode in {124, 125, 126, 127}:
            result.update(status="unavailable", reason_code="command_unavailable")
        elif check["kind"] == "test":
            try:
                counts = decode_json(answer.stdout.encode())
                keys = {"executed_count", "failed_count", "skipped_count"}
                _require(
                    set(counts) == keys
                    and all(
                        type(counts[key]) is int and 0 <= counts[key] <= 2**53 - 1 for key in keys
                    ),
                    "test_report_invalid",
                )
                _require(counts["failed_count"] <= counts["executed_count"], "test_report_invalid")
                result.update(counts)
                if counts["executed_count"] == 0 or counts["skipped_count"]:
                    result.update(status="unavailable", reason_code="test_report_incomplete")
                elif counts["failed_count"]:
                    result.update(status="failed", reason_code="test_failed")
            except ValueError:
                result.update(status="unavailable", reason_code="test_report_invalid")
    artifact = EvaluationArtifact(
        f"{request.phase}-command-{index}",
        "log",
        f"artifacts/{request.phase}/command-{index}.log",
        payload,
    )
    result["artifact_ids"] = [artifact.artifact_id]
    result["duration_ms"] = (time.monotonic_ns() - started) // 1_000_000
    return result, artifact, cleanup, output_bytes


def _cleanup_failed(error: BaseException) -> bool:
    pending = [error]
    visited: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in visited:
            continue
        visited.add(id(current))
        if any("cleanup failed" in str(note).lower() for note in getattr(current, "__notes__", ())):
            return True
        pending.extend(
            item for item in (current.__cause__, current.__context__) if item is not None
        )
    return False


def _copy_intact(request: EvaluationRequest, app: Path) -> bool:
    try:
        observed = capture_source(
            app,
            max_file_bytes=request.limits["max_file_bytes"],
            max_total_bytes=min(_MAX_BYTES, request.limits["max_artifact_bytes"]),
        )
    except (OSError, ValueError):
        return False
    return observed.tree_sha256 == request.snapshot.tree_sha256


class VerifiedEvaluator:
    """Use local execution only when the CLI explicitly supplied its separate grant.

    Docker policy preflight is available; its checker transport is not implemented.
    An available daemon therefore never silently enables host execution.
    """

    def __init__(
        self, *, trusted_local_approved: bool = False, isolation: LocalDockerIsolation | None = None
    ) -> None:
        if type(trusted_local_approved) is not bool:
            raise ValueError("explicit_local_boolean_required")
        self._local = trusted_local_approved
        self._isolation = isolation or LocalDockerIsolation()

    async def evaluate(self, request: EvaluationRequest) -> EvaluationOutcome:
        try:
            inputs = _prepare(request, trusted_local=self._local)
        except (KeyError, TypeError, OSError, ValueError) as error:
            return EvaluationOutcome(
                tuple(
                    _result(request, check, str(error)[:128] or "invalid_execution_input")
                    for check in request.checks
                ),
                input_tree_sha256=request.input_tree_sha256,
                cleanup_complete=True,
            )
        if not self._local:
            availability = await self._isolation.preflight(deadline_ns=request.deadline_ns)
            detail = (
                "isolated_worker_unavailable" if availability.available else availability.reason
            )
            artifact = EvaluationArtifact(
                f"{request.phase}-isolation",
                "log",
                f"artifacts/{request.phase}/isolation.log",
                detail.encode(),
            )
            unavailable = tuple(
                _result(request, check, "isolation_unavailable") for check in request.checks
            )
            for result in unavailable:
                result["artifact_ids"] = [artifact.artifact_id]
            return EvaluationOutcome(
                unavailable,
                (artifact,),
                None,
                request.environment_sha256,
                request.evaluator_sha256,
                request.input_tree_sha256,
                True,
            )
        results: list[Record] = []
        artifacts: list[EvaluationArtifact] = []
        cleanup = True
        source_intact = True
        output_bytes: int | None = 0
        artifact_bytes = 0
        artifact_limit = min(_MAX_BYTES, request.limits["max_artifact_bytes"])
        halted: str | None = None

        def retain(artifact: EvaluationArtifact) -> bool:
            nonlocal artifact_bytes, halted
            if artifact_bytes + len(artifact.content) > artifact_limit:
                results[-1].update(status="unavailable", reason_code="artifact_limit")
                halted = "artifact_limit"
                return False
            artifacts.append(artifact)
            artifact_bytes += len(artifact.content)
            return True

        def count_output(size: int | None) -> None:
            nonlocal output_bytes, halted
            if size is None or output_bytes is None:
                output_bytes = None
                halted = "output_unknown"
                return
            output_bytes += size
            if output_bytes > request.limits["max_output_bytes"]:
                results[-1].update(status="unavailable", reason_code="output_limit")
                halted = "output_limit"

        def finish_check(app: Path) -> None:
            nonlocal source_intact, halted
            if not cleanup:
                results[-1].update(status="unavailable", reason_code="cleanup_failed")
                halted = "cleanup_failed"
            if not _copy_intact(request, app):
                source_intact = False
                results[-1].update(status="unavailable", reason_code="source_changed")
                halted = "source_changed"

        with tempfile.TemporaryDirectory(prefix="ddk-evaluate-") as folder:
            root = Path(folder).resolve()
            app, output = root / "app", root / "results"
            app.mkdir(mode=0o700)
            output.mkdir(mode=0o700)
            for file in request.snapshot.files:
                path = app / file.path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(file.content)
                path.chmod(file.mode)
            _require(_copy_intact(request, app), "private_copy_mismatch")
            for index, check in enumerate(request.checks):
                reason = halted or _stopped(request)
                if not reason and artifact_bytes >= artifact_limit:
                    reason = "artifact_limit"
                if reason:
                    results.append(_result(request, check, reason))
                    continue
                if check["kind"] in {"command", "test"}:
                    result, artifact, finished, written = await _command(request, check, app, index)
                    results.append(result)
                    if not retain(artifact):
                        result["artifact_ids"] = []
                    count_output(written)
                    cleanup = cleanup and finished
                    finish_check(app)
                    continue
                if check["kind"] not in {"browser", "visual"}:
                    results.append(_result(request, check, "unsupported_check_kind"))
                    continue
                session = None
                try:
                    deadline = min(
                        request.deadline_ns,
                        time.monotonic_ns()
                        + min(check["timeout_ms"], request.limits["step_timeout_ms"]) * 1_000_000,
                    )
                    session = await SubprocessPreviewLauncher().start(
                        inputs.plan["preview_argv"],
                        app,
                        timeout_s=max(0.001, (deadline - time.monotonic_ns()) / 1e9),
                    )
                    run = await run_flow(
                        inputs.files[check["definition_path"]].content,
                        check=check,
                        base_url=session.url,
                        output_dir=output,
                        fixture_sha256=inputs.settings.environment["fixture_sha256"],
                        references=inputs.references,
                        settings=replace(
                            inputs.settings, max_artifact_bytes=artifact_limit - artifact_bytes
                        ),
                        phase=cast(Literal["baseline", "candidate"], request.phase),
                        deadline_ns=deadline,
                    )
                    cleanup = cleanup and run.cleanup_complete
                    results.append(run.result)
                    retained_ids: list[str] = []
                    for item in run.artifacts:
                        _require(safe_path(item["path"]), "unsafe_observation_path")
                        data = read_regular(output / item["path"], item["size_bytes"])
                        _require(
                            len(data) == item["size_bytes"]
                            and hashlib.sha256(data).hexdigest() == item["sha256"],
                            "observation_hash_mismatch",
                        )
                        if retain(
                            EvaluationArtifact(
                                item["artifact_id"],
                                item["kind"],
                                f"artifacts/{request.phase}/browser-{index}/" + item["path"],
                                data,
                                item["sensitive"],
                                item["public_export_allowed"],
                            )
                        ):
                            retained_ids.append(item["artifact_id"])
                    run.result["artifact_ids"] = retained_ids
                except (OSError, ValueError, RuntimeError) as error:
                    cleanup = cleanup and not _cleanup_failed(error)
                    if results and results[-1]["check_id"] == check["check_id"]:
                        results[-1].update(
                            status="unavailable", reason_code="observation_unavailable"
                        )
                    else:
                        results.append(
                            _result(request, check, str(error)[:128] or "preview_unavailable")
                        )
                    if session is None:
                        count_output(None)
                finally:
                    if session is not None:
                        try:
                            await session.stop()
                        except Exception:
                            cleanup = False
                        stdout, stderr = session.output()
                        count_output(len(stdout.encode()) + len(stderr.encode()))
                        if stdout or stderr:
                            retain(
                                EvaluationArtifact(
                                    f"{request.phase}-preview-{index}",
                                    "log",
                                    f"artifacts/{request.phase}/preview-{index}.log",
                                    (stdout + "\n" + stderr).encode(),
                                )
                            )
                finish_check(app)
        return EvaluationOutcome(
            tuple(results),
            tuple(artifacts),
            "trusted-local",
            request.environment_sha256,
            request.evaluator_sha256,
            request.input_tree_sha256 if source_intact else None,
            cleanup,
            output_bytes=output_bytes,
        )
