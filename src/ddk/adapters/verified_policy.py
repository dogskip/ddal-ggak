"""Bounded host-owned policy checks over frozen source and baseline bytes."""

from __future__ import annotations

import asyncio
import difflib
import fnmatch
import re
import sys
import tempfile
import time
from pathlib import Path

from ddk.adapters.verified_reports import check_result
from ddk.models.verified_change import Record, canonical_json, decode_json, safe_path, string_values
from ddk.services.verified_change_engine import EvaluationArtifact, EvaluationRequest

_KEYS = {
    "forbidden_paths",
    "forbid_secret_patterns",
    "forbid_regex",
    "max_changed_files",
    "max_changed_lines",
    "review_required",
}


def _patterns(value: object) -> list[re.Pattern[str]]:
    values = string_values(value)
    if len(values) > 32:
        raise ValueError("policy_definition_invalid")
    patterns: list[re.Pattern[str]] = []
    for text in values:
        if not text or len(text) > 256:
            raise ValueError("policy_pattern_invalid")
        # Only a bounded subset without groups or backreferences is accepted.
        if re.search(r"(?<!\\)[()]|\\[1-9]", text) or len(re.findall(r"(?<!\\)[*+?{]", text)) > 1:
            raise ValueError("policy_pattern_unsupported")
        try:
            patterns.append(re.compile(text))
        except re.error as error:
            raise ValueError("policy_pattern_invalid") from error
    return patterns


def evaluate_policy(
    request: EvaluationRequest, check: Record, definition: bytes
) -> tuple[Record, EvaluationArtifact]:
    result = check_result(request, check)
    violations: list[Record] = []
    try:
        policy = decode_json(definition)
        if not set(policy) <= _KEYS:
            raise ValueError("policy_definition_invalid")
        if policy.get("review_required", False) is not False:
            raise ValueError("acceptance_checks_required")
        forbidden = string_values(policy.get("forbidden_paths", []))
        if len(forbidden) > 1000 or any(not safe_path(p) for p in forbidden):
            raise ValueError("policy_definition_invalid")
        patterns = [
            ("secret_pattern", p) for p in _patterns(policy.get("forbid_secret_patterns", []))
        ] + [("forbidden_pattern", p) for p in _patterns(policy.get("forbid_regex", []))]
        before = (
            {f.path: f for f in request.baseline_snapshot.files}
            if request.baseline_snapshot is not None
            else {}
        )
        after = {f.path: f for f in request.snapshot.files}
        changed = [
            p
            for p in sorted(set(before) | set(after))
            if (before[p].manifest_entry() if p in before else None)
            != (after[p].manifest_entry() if p in after else None)
        ]
        if (
            forbidden or "max_changed_lines" in policy or "max_changed_files" in policy
        ) and request.baseline_snapshot is None:
            raise ValueError("policy_baseline_missing")
        for path in changed:
            if any(fnmatch.fnmatchcase(path, pattern) for pattern in forbidden):
                violations.append({"path": path, "line": 0, "reason_code": "forbidden_path"})
        lines = 0
        for path in sorted(set(before) | set(after)):
            if request.cancelled() or time.monotonic_ns() >= request.deadline_ns:
                raise ValueError("policy_timeout")
            previous = (
                before[path].content.decode("utf-8", errors="replace").splitlines()
                if path in before and "max_changed_lines" in policy
                else []
            )
            current = (
                after[path].content.decode("utf-8", errors="replace").splitlines()
                if path in after and (patterns or "max_changed_lines" in policy)
                else []
            )
            if path in changed and "max_changed_lines" in policy:
                lines += sum(
                    tag != "equal" and (b - a + d - c) or 0
                    for tag, a, b, c, d in difflib.SequenceMatcher(
                        a=previous, b=current, autojunk=False
                    ).get_opcodes()
                )
            for number, line in enumerate(current, 1):
                if len(line) > 8192 and patterns:
                    raise ValueError("policy_line_limit")
                for code, pattern in patterns:
                    if pattern.search(line):
                        violations.append({"path": path, "line": number, "reason_code": code})
                if len(violations) > 1000:
                    raise ValueError("policy_observation_limit")
        for key, actual in [("max_changed_files", len(changed)), ("max_changed_lines", lines)]:
            value = policy.get(key)
            if value is not None:
                if type(value) is not int or not 0 <= value <= 10**7:
                    raise ValueError("policy_definition_invalid")
                if actual > value:
                    violations.append({"path": "", "line": 0, "reason_code": key})
        result.update(
            status="failed" if violations else "passed",
            reason_code=violations[0]["reason_code"] if violations else None,
            executed_count=1,
            failed_count=int(bool(violations)),
            skipped_count=0,
        )
    except (ValueError, TypeError, KeyError, UnicodeError) as error:
        result.update(status="unavailable", reason_code=str(error)[:128])
    artifact = EvaluationArtifact(
        f"{request.phase}-policy-{check['check_id']}",
        "log",
        f"artifacts/{request.phase}/policy-{check['check_id']}.json",
        canonical_json({"violations": violations, "reason_code": result["reason_code"]}),
    )
    result["artifact_ids"] = [artifact.artifact_id]
    return result, artifact


async def evaluate_policy_owned(
    request: EvaluationRequest, check: Record, definition: bytes
) -> tuple[Record, EvaluationArtifact]:
    """Keep untrusted regex and diff computation inside an owned, deadline-bound process."""
    from ddk.adapters.subprocess_build_runner import start_owned_process, stop_owned_process

    def fallback(reason: str) -> tuple[Record, EvaluationArtifact]:
        result = check_result(request, check, reason)
        artifact = EvaluationArtifact(
            f"{request.phase}-policy-{check['check_id']}",
            "log",
            f"artifacts/{request.phase}/policy-{check['check_id']}.json",
            canonical_json({"violations": [], "reason_code": reason}),
        )
        result["artifact_ids"] = [artifact.artifact_id]
        return result, artifact

    deadline = min(request.deadline_ns, time.monotonic_ns() + check["timeout_ms"] * 1_000_000)
    if request.cancelled() or deadline <= time.monotonic_ns():
        return fallback("policy_timeout")
    code = (
        "import sys;sys.path.insert(0,"
        + repr(str(Path(__file__).resolve().parents[2]))
        + ");from ddk.adapters.verified_policy import policy_worker;policy_worker()"
    )
    with tempfile.TemporaryDirectory(prefix="ddk-policy-") as directory:
        from ddk.services.source_snapshot import materialize_snapshot

        root = Path(directory).resolve()
        materialize_snapshot(request.snapshot, root / "after")
        if request.baseline_snapshot is not None:
            materialize_snapshot(request.baseline_snapshot, root / "before")
        payload = canonical_json(
            {
                "case_id": request.case_id,
                "phase": request.phase,
                "check": check,
                "definition": decode_json(definition),
                "after_sha256": request.snapshot.tree_sha256,
                "before_sha256": request.baseline_snapshot.tree_sha256
                if request.baseline_snapshot is not None
                else None,
                "deadline_ns": deadline,
                "limits": dict(request.limits),
            }
        )
        process, output = await start_owned_process(
            [sys.executable, "-I", "-c", code],
            Path(directory),
            stdin=asyncio.subprocess.PIPE,
            max_output_bytes=2 * 1024**2,
        )
        waiter: asyncio.Task[bool] | None = None
        try:
            async with asyncio.timeout(max(0.001, (deadline - time.monotonic_ns()) / 1e9)):
                assert process.stdin is not None
                process.stdin.write(payload)
                await process.stdin.drain()
                process.stdin.close()
                waiter = asyncio.create_task(output.wait(deadline))
                while not waiter.done():
                    if request.cancelled():
                        return fallback("policy_cancelled")
                    await asyncio.wait({waiter}, timeout=0.05)
                if await waiter or process.returncode != 0:
                    return fallback("policy_worker_failed")
                answer = decode_json(bytes(output.stdout))
                result: Record = answer["result"]
                artifact = EvaluationArtifact(
                    f"{request.phase}-policy-{check['check_id']}",
                    "log",
                    f"artifacts/{request.phase}/policy-{check['check_id']}.json",
                    canonical_json(answer["diagnostic"]),
                )
                result["artifact_ids"] = [artifact.artifact_id]
                return result, artifact
        except TimeoutError:
            return fallback("policy_timeout")
        finally:
            await stop_owned_process(process, output)
            if waiter is not None:
                waiter.cancel()
                await asyncio.gather(waiter, return_exceptions=True)


def policy_worker() -> None:
    """Private stdio worker; all input and output are bounded canonical JSON."""
    from ddk.services.source_snapshot import SourceSnapshot, capture_source

    data = decode_json(sys.stdin.buffer.read(2 * 1024**2 + 1))

    def snapshot(name: str) -> SourceSnapshot:
        result = capture_source(
            Path.cwd() / name,
            max_file_bytes=data["limits"]["max_file_bytes"],
            max_total_bytes=data["limits"]["max_artifact_bytes"],
        )
        if result.tree_sha256 != data[name + "_sha256"]:
            raise ValueError("policy_source_changed")
        return result

    request = EvaluationRequest(
        data["case_id"],
        (data["check"],),
        data["phase"],
        snapshot("after"),
        (),
        "",
        "",
        "",
        data["deadline_ns"],
        lambda: False,
        data["limits"],
        snapshot("before") if data["before_sha256"] is not None else None,
    )
    result, artifact = evaluate_policy(request, data["check"], canonical_json(data["definition"]))
    sys.stdout.buffer.write(
        canonical_json({"result": result, "diagnostic": decode_json(artifact.content)})
    )
