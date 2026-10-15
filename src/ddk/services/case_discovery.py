"""Conservative command suggestions and explicitly reviewed acceptance drafts."""

from __future__ import annotations

import hashlib
import json
import shlex
import tomllib
from pathlib import Path
from typing import cast
from uuid import uuid4

from ddk.models.verified_change import Record, decode_json, object_record, object_records
from ddk.security.file_access import file_identity, read_regular
from ddk.security.redact import redact_string
from ddk.security.repo_paths import normalize_change_path
from ddk.services.durable_files import OwnedLock, atomic_write, ensure_directory

CONFIGURATION_PATHS = (".ddk/verify.toml", "ddk.toml", "pyproject.toml")
_MAX_BYTES = 2 * 1024**2


def configuration_binding(repository: Path, *, explicit: bool = False) -> Record:
    files: Record = {}
    for name in CONFIGURATION_PATHS:
        path = repository / name
        try:
            path.lstat()
        except FileNotFoundError:
            files[name] = None
        else:
            files[name] = hashlib.sha256(read_regular(path, _MAX_BYTES)).hexdigest()
    return {
        "format": "ddk-configuration/1",
        "origin": "explicit" if explicit else "repository",
        "selected_path": None if explicit else next((p for p in files if files[p]), None),
        "files": files,
    }


def has_acceptance(configuration: Record) -> bool:
    return {"target", "preserve"} <= {
        c.get("role")
        for c in object_records(configuration.get("checks", []))
        if c.get("kind", "browser") in {"browser", "visual"} and c.get("required", True)
    }


def _toml_value(value: object) -> str:
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if type(value) is bool:
        return "true" if value else "false"
    if type(value) is int:
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in cast(list[object], value)) + "]"
    if isinstance(value, dict):
        return (
            "{ "
            + ", ".join(
                f"{_toml_value(key)} = {_toml_value(item)}"
                for key, item in sorted(cast(dict[str, object], value).items())
                if item is not None
            )
            + " }"
        )
    raise ValueError("draft_value_invalid")


def _toml(configuration: Record) -> bytes:
    lines = ["# Observed suggestions only. Add independent target checks before approval."]
    for key, value in configuration.items():
        if key != "checks" and value is not None:
            lines.append(f"{_toml_value(key)} = {_toml_value(value)}")
    for check in object_records(configuration.get("checks", [])):
        lines.extend(["", "[[checks]]"])
        lines.extend(
            f"{_toml_value(key)} = {_toml_value(value)}"
            for key, value in check.items()
            if value is not None
        )
    payload = ("\n".join(lines) + "\n").encode()
    if len(payload) > _MAX_BYTES:
        raise ValueError("draft_size_limit")
    tomllib.loads(payload.decode())
    return payload


def _suggestions(repository: Path) -> list[Record]:
    checks: list[Record] = []

    def add(ident: str, argv: list[str], adapter: str | None = None) -> None:
        check: Record = {
            "check_id": ident,
            "role": "preserve",
            "kind": "test" if adapter else "command",
            "command_argv": argv,
        }
        if adapter:
            check["report_adapter"] = adapter
        checks.append(check)

    package = repository / "package.json"
    if package.exists() or package.is_symlink():
        scripts = object_record(decode_json(read_regular(package, _MAX_BYTES)).get("scripts", {}))
        for name in ("build", "typecheck", "type-check", "lint", "test"):
            script = scripts.get(name)
            if not isinstance(script, str) or not script.strip():
                continue
            argv = ["npm", "run", name]
            parts = shlex.split(script)
            runner = Path(parts[0]).name if parts else ""
            if name == "test" and runner in {"vitest", "jest", "playwright"}:
                adapter = {
                    "vitest": "vitest-json",
                    "jest": "jest-json",
                    "playwright": "playwright-json",
                }[runner]
                if runner == "playwright":
                    add(
                        "discovered-test",
                        [
                            "env",
                            "PLAYWRIGHT_JSON_OUTPUT_FILE={report}",
                            *argv,
                            "--",
                            "--reporter=json",
                        ],
                        adapter,
                    )
                else:
                    add(
                        "discovered-test",
                        [*argv, "--", "--reporter=json", "--outputFile={report}"]
                        if runner == "vitest"
                        else [*argv, "--", "--json", "--outputFile={report}"],
                        adapter,
                    )
            else:
                add("discovered-" + name, argv)
    if any(repository.glob("playwright.config.*")) and not any(
        c.get("report_adapter") == "playwright-json" for c in checks
    ):
        add(
            "discovered-playwright",
            [
                "env",
                "PLAYWRIGHT_JSON_OUTPUT_FILE={report}",
                "npx",
                "--no-install",
                "playwright",
                "test",
                "--reporter=json",
            ],
            "playwright-json",
        )
    project = repository / "pyproject.toml"
    if project.exists() or project.is_symlink():
        config = tomllib.loads(read_regular(project, _MAX_BYTES).decode())
        tool = object_record(config.get("tool", {}))
        if "pytest" in tool or (repository / "tests").is_dir():
            add(
                "discovered-pytest", ["python3", "-m", "pytest", "--junitxml={report}"], "junit-xml"
            )
        for name, argv in (
            ("ruff", ["ruff", "check", "."]),
            ("mypy", ["mypy", "."]),
            ("pyright", ["pyright"]),
        ):
            if name in tool:
                add("discovered-" + name, argv)
    return checks


async def discover(
    repository: Path,
    preview_url_or_cmd: str | None = None,
    *,
    viewport: tuple[int, int] = (1280, 800),
    confirm_execution: bool = False,
    dry_run: bool = False,
) -> Record:
    if (
        preview_url_or_cmd
        and not preview_url_or_cmd.startswith(("http://", "https://"))
        and not confirm_execution
    ):
        raise ValueError("preview_execution_confirmation_required")
    checks = _suggestions(repository)
    config: Record = {"draft": True, "scope_paths": [], "preview_argv": [], "checks": checks}
    observations: Record | None = None
    if preview_url_or_cmd and not preview_url_or_cmd.startswith(("http://", "https://")):
        config["preview_argv"] = shlex.split(preview_url_or_cmd)
    elif (repository / "index.html").is_file():
        config["preview_argv"] = ["python3", "-m", "http.server", "{port}", "--bind", "127.0.0.1"]
    if preview_url_or_cmd and not dry_run:
        from ddk.services.probe_capture import capture_preview_probe

        output = repository / ".ddk/probes" / str(uuid4())
        observations = await capture_preview_probe(
            preview_url_or_cmd,
            output,
            repository=repository,
            viewport=viewport,
            confirm_execution=confirm_execution,
        )
        steps: list[Record] = [{"action": "expect-no-console-error"}]
        for artifact in object_records(observations.get("artifacts", [])):
            if artifact["path"] != "probe.ax.json":
                continue
            raw = read_regular(output / artifact["path"], _MAX_BYTES)
            if hashlib.sha256(raw).hexdigest() != artifact["sha256"]:
                raise ValueError("probe_artifact_mismatch")
            snapshot = decode_json(raw).get("snapshot", "")
            if not isinstance(snapshot, str):
                raise ValueError("probe_snapshot_invalid")
            for line in snapshot.splitlines():
                node = line.strip().removeprefix("- ")
                if node.startswith(("heading ", "navigation", "main")):
                    steps.append({"action": "expect-ax-tree", "value": redact_string(node)[:512]})
                    if len(steps) >= 9:
                        break
        checks.append(
            {
                "check_id": "discovered-browser",
                "kind": "browser",
                "role": "preserve",
                "viewport": {"width": viewport[0], "height": viewport[1]},
                "steps": steps,
            }
        )
    payload = _toml(config)
    if not dry_run:
        ensure_directory(repository / ".ddk")
        atomic_write(repository / ".ddk/verify.draft.toml", payload, exclusive=True)
    return {
        "status": "draft",
        **config,
        "dry_run": dry_run,
        "execution_approved": False,
        "draft_path": ".ddk/verify.draft.toml",
        "draft_sha256": hashlib.sha256(payload).hexdigest(),
        "observation": observations,
        "actions": [
            {
                "code": "draft_criteria_unapproved",
                "message": "Define independent target/preserve checks and review the draft.",
            }
        ],
    }


def approve_draft(repository: Path, *, dry_run: bool = False) -> Record:
    path = repository / ".ddk/verify.draft.toml"
    identity = file_identity(path.lstat())
    raw = read_regular(path, _MAX_BYTES)
    config = tomllib.loads(raw.decode())
    if config.get("draft") is not True:
        raise ValueError("draft_flag_required")
    if not has_acceptance(config):
        return {
            "status": "blocked",
            "dry_run": dry_run,
            "actions": [
                {
                    "code": "acceptance_checks_required",
                    "message": "Add independent target and preserve browser checks to the draft.",
                }
            ],
        }
    for name in config.get("scope_paths", []):
        normalize_change_path(name)
    from ddk.services.case_criteria import compile_checks

    compile_checks(config, "0" * 64)
    config["draft"] = False
    payload = _toml(config)
    if not dry_run:
        lock = OwnedLock(repository / ".ddk/approve.lock", str(uuid4())).acquire()
        try:
            if file_identity(path.lstat()) != identity or read_regular(path, _MAX_BYTES) != raw:
                raise ValueError("draft_changed")
            atomic_write(repository / ".ddk/verify.toml", payload, exclusive=True)
        finally:
            lock.release()
    return {
        "status": "approved",
        "dry_run": dry_run,
        "draft_sha256": hashlib.sha256(raw).hexdigest(),
        "configuration_sha256": hashlib.sha256(payload).hexdigest(),
        "actions": [],
    }
