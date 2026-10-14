"""The isolated executor refuses weaker boundaries and owns every created task."""

from __future__ import annotations

import asyncio
import json
import socket
import tempfile
from dataclasses import replace
from pathlib import Path

import pytest

from ddk.adapters.build_runner import BuildResult
from ddk.adapters.verified_isolation import (
    IsolationRequest,
    IsolationUnavailableError,
    LocalDockerIsolation,
    resolve_endpoint,
)

APP_IMAGE = "sha256:" + "a" * 64
CHECKER_IMAGE = "sha256:" + "b" * 64


@pytest.fixture
def local_socket(tmp_path: Path):
    with tempfile.TemporaryDirectory(dir="/tmp", prefix="ddk-socket-") as directory:
        path = Path(directory) / "socket"
        server = socket.socket(socket.AF_UNIX)
        server.bind(str(path))
        try:
            yield path
        finally:
            server.close()


def request(tmp_path: Path) -> IsolationRequest:
    owned = tmp_path / "owned"
    owned.mkdir()
    for name in ("app", "criteria", "results"):
        (owned / name).mkdir()
    return IsolationRequest(
        owned_root=owned,
        app_dir=owned / "app",
        criteria_dir=owned / "criteria",
        results_dir=owned / "results",
        app_image=APP_IMAGE,
        checker_image=CHECKER_IMAGE,
        uid=1000,
        gid=1000,
        app_command=("node", "server.js"),
        checker_command=("python3", "-m", "owned_checker"),
    )


class DockerFixture:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], bytes | None]] = []
        self.containers: dict[str, dict] = {}
        self.tamper: tuple[str, object] | None = None
        self.cancel_on_checker = False
        self.remove_fails = False
        self.info_available = True
        self.images_available = True

    async def run(
        self, command: list[str], cwd: Path, timeout: int = 300, *, stdin: bytes | None = None
    ) -> BuildResult:
        self.calls.append((command, stdin))
        args = command[command.index("--host") + 2 :]
        operation = args[0]
        code = 0
        data: object = ""
        if operation == "info":
            if not self.info_available:
                return BuildResult(False, "", "daemon unavailable", 1)
            data = {
                "OSType": "linux",
                "OperatingSystem": "Docker Desktop",
                "CgroupVersion": "2",
                "SecurityOptions": ["name=seccomp,profile=builtin"],
                "MemoryLimit": True,
                "PidsLimit": True,
                "CpuCfsQuota": True,
            }
        elif args[:2] == ["image", "inspect"]:
            if not self.images_available:
                return BuildResult(False, "", "No such image", 1)
            data = [{"Id": args[-1], "Os": "linux", "Config": {"Volumes": None}}]
        elif operation == "create":
            name = args[args.index("--name") + 1]
            identifier = ("c" if name.endswith("app") else "d") * 64
            labels = dict(
                value.split("=", 1)
                for index, value in enumerate(args)
                if args[index - 1] == "--label"
            )
            mounts = []
            for index, value in enumerate(args):
                if args[index - 1] == "--mount":
                    parts = dict(
                        item.split("=", 1) if "=" in item else (item, True)
                        for item in value.split(",")
                    )
                    mounts.append(
                        {
                            "Type": "bind",
                            "Source": parts["source"],
                            "Destination": parts["target"],
                            "RW": "readonly" not in parts,
                        }
                    )
            image = APP_IMAGE if name.endswith("app") else CHECKER_IMAGE
            role = "app" if name.endswith("app") else "checker"
            host = {
                "Privileged": False,
                "ReadonlyRootfs": True,
                "Init": True,
                "CapAdd": None,
                "CapDrop": ["ALL"],
                "SecurityOpt": [
                    value for index, value in enumerate(args) if args[index - 1] == "--security-opt"
                ],
                "NetworkMode": args[args.index("--network") + 1],
                "PidMode": "",
                "IpcMode": "private",
                "Memory": 2 * 1024**3,
                "MemorySwap": 2 * 1024**3,
                "NanoCpus": 1_000_000_000,
                "PidsLimit": 256,
                "ShmSize": 256 * 1024**2,
                "PortBindings": {},
                "Devices": [],
                "Binds": None,
                "VolumesFrom": None,
                "Tmpfs": {"/tmp": "rw,noexec,nosuid,nodev,size=67108864,mode=1777"},
            }
            if self.tamper is not None and role == "checker":
                host[self.tamper[0]] = self.tamper[1]
            host["SecurityOpt"] = [
                "seccomp=" + json.dumps(json.loads(Path(value.split("=", 1)[1]).read_text()))
                if value.startswith("seccomp=")
                else value
                for value in host["SecurityOpt"]
            ]
            self.containers[name] = {
                "Id": identifier,
                "Name": "/" + name,
                "Created": "2026-10-14T00:00:00Z",
                "Image": image,
                "Config": {"User": args[args.index("--user") + 1], "Labels": labels},
                "HostConfig": host,
                "Mounts": mounts,
                "State": {"Running": False, "Pid": 0},
                "NetworkSettings": {"Networks": {}},
            }
            data = identifier
        elif operation == "inspect":
            target = args[-1]
            record = next(
                (value for name, value in self.containers.items() if target in {name, value["Id"]}),
                None,
            )
            if record is None:
                return BuildResult(False, "", "No such object", 1)
            data = [record]
        elif operation == "start":
            self.containers[args[-1]]["State"] = {
                "Running": True,
                "Pid": 100 if args[-1].endswith("app") else 200,
            }
        elif operation == "exec":
            name = next(
                name
                for name, value in self.containers.items()
                if name in args or value["Id"] in args
            )
            if "node" in args or ("-c" in args and "sync_playwright" not in args[-1]):
                data = {
                    "uid": 1000,
                    "gid": 1000,
                    "no_new_privs": 1,
                    "seccomp": 2,
                    "cap_eff": 0,
                    "pid_ns": "pid:[100]" if name.endswith("app") else "pid:[200]",
                    "mnt_ns": "mnt:[100]" if name.endswith("app") else "mnt:[200]",
                    "net_ns": "net:[1]",
                    "interfaces": ["lo"],
                    "external_blocked": True,
                    "memory_max": 2 * 1024**3,
                    "pids_max": 256,
                    "cpu_quota": 100000,
                    "cpu_period": 100000,
                    "mounts": {"/": "ro", "/tmp": "rw", "/workspace": "rw"}
                    if name.endswith("app")
                    else {"/": "ro", "/tmp": "rw", "/criteria": "ro", "/results": "rw"},
                    "tmp_flags": ["rw", "noexec", "nosuid", "nodev"],
                    "shm_bytes": 256 * 1024**2,
                }
            elif "-c" in args:
                data = {"started": True, "headless": True, "chromium_sandbox": True}
            else:
                if self.cancel_on_checker:
                    raise asyncio.CancelledError
                return BuildResult(True, '{"checks":[]}', "", 0)
        elif operation == "rm":
            if self.remove_fails:
                return BuildResult(False, "", "remove refused", 1)
            target = args[-1]
            self.containers = {
                name: value for name, value in self.containers.items() if target != value["Id"]
            }
        else:
            raise AssertionError(args)
        return BuildResult(code == 0, data if isinstance(data, str) else json.dumps(data), "", code)


@pytest.mark.parametrize(
    "endpoint",
    ["ssh://remote", "tcp://127.0.0.1:2375", "https://remote", "npipe:////./pipe/docker_engine"],
)
async def test_remote_endpoints_are_refused_before_any_docker_call(
    tmp_path: Path, endpoint: str
) -> None:
    runner = DockerFixture()
    service = LocalDockerIsolation(
        runner=runner, environ={"DOCKER_HOST": endpoint}, config_dir=tmp_path
    )
    result = await service.preflight()
    assert not result.available and result.code == "isolation_unavailable"
    assert runner.calls == []


def test_context_override_precedes_host_without_remote_connection(
    tmp_path: Path, local_socket: Path
) -> None:
    metadata = tmp_path / "contexts/meta/local/meta.json"
    metadata.parent.mkdir(parents=True)
    metadata.write_text(
        json.dumps({"Name": "local", "Endpoints": {"docker": {"Host": f"unix://{local_socket}"}}})
    )
    resolved = resolve_endpoint(
        {"DOCKER_CONTEXT": "local", "DOCKER_HOST": "ssh://remote"}, tmp_path
    )
    assert resolved.context == "local" and resolved.uri == f"unix://{local_socket}"


async def test_daemon_or_missing_image_never_uses_host_fallback(
    tmp_path: Path, local_socket: Path
) -> None:
    runner = DockerFixture()
    runner.info_available = False
    service = LocalDockerIsolation(
        runner=runner, environ={"DOCKER_HOST": f"unix://{local_socket}"}, config_dir=tmp_path
    )
    result = await service.execute(request(tmp_path), b"{}")
    assert result.code == "isolation_unavailable"
    assert not any("create" in argv for argv, _ in runner.calls)


async def test_execution_uses_separate_spaces_and_cleans_owned_tasks(
    tmp_path: Path, local_socket: Path
) -> None:
    runner = DockerFixture()
    service = LocalDockerIsolation(
        runner=runner, environ={"DOCKER_HOST": f"unix://{local_socket}"}, config_dir=tmp_path
    )
    result = await service.execute(request(tmp_path), b'{"flow":"approved"}')
    assert result.completed and result.policy_verified and result.cleanup_complete
    assert result.assurance == "isolated" and result.stdout == '{"checks":[]}'
    creates = [argv for argv, _ in runner.calls if "create" in argv]
    assert len(creates) == 2
    app, checker = creates
    assert app[app.index("--network") + 1] == "none"
    assert checker[checker.index("--network") + 1].startswith("container:")
    assert not any(
        flag in argv
        for argv, _ in runner.calls
        for flag in ["--privileged", "--ipc=host", "--pid=host", "--publish", "--no-sandbox"]
    )
    assert all("--pull" in argv and argv[argv.index("--pull") + 1] == "never" for argv in creates)
    assert str(tmp_path / "owned/criteria") not in " ".join(app)
    assert any(stdin == b'{"flow":"approved"}' for _, stdin in runner.calls)
    assert runner.containers == {}


@pytest.mark.parametrize(
    "field,value",
    [
        ("Privileged", True),
        ("ReadonlyRootfs", False),
        ("PidsLimit", 0),
        ("NetworkMode", "host"),
        ("PidMode", "host"),
        ("CapAdd", ["SYS_ADMIN"]),
        ("SecurityOpt", []),
        ("ShmSize", 0),
    ],
)
async def test_daemon_policy_drift_blocks_execution_and_cleans(
    tmp_path: Path, local_socket: Path, field: str, value: object
) -> None:
    runner = DockerFixture()
    runner.tamper = (field, value)
    service = LocalDockerIsolation(
        runner=runner, environ={"DOCKER_HOST": f"unix://{local_socket}"}, config_dir=tmp_path
    )
    result = await service.execute(request(tmp_path), b"{}")
    assert not result.completed and result.code == "isolation_unavailable"
    assert result.cleanup_complete and runner.containers == {}
    assert not any(stdin is not None for _, stdin in runner.calls)


async def test_cancellation_cleans_owned_containers_then_propagates(
    tmp_path: Path, local_socket: Path
) -> None:
    runner = DockerFixture()
    runner.cancel_on_checker = True
    service = LocalDockerIsolation(
        runner=runner, environ={"DOCKER_HOST": f"unix://{local_socket}"}, config_dir=tmp_path
    )
    with pytest.raises(asyncio.CancelledError):
        await service.execute(request(tmp_path), b"{}")
    assert runner.containers == {}


async def test_cleanup_failure_prevents_completed_result(
    tmp_path: Path, local_socket: Path
) -> None:
    runner = DockerFixture()
    runner.remove_fails = True
    service = LocalDockerIsolation(
        runner=runner, environ={"DOCKER_HOST": f"unix://{local_socket}"}, config_dir=tmp_path
    )
    result = await service.execute(request(tmp_path), b"{}")
    assert not result.completed and not result.cleanup_complete
    assert result.code == "isolation_unavailable"


def test_plan_refuses_mutable_images_and_overlapping_mounts(
    tmp_path: Path, local_socket: Path
) -> None:
    service = LocalDockerIsolation(
        runner=DockerFixture(),
        environ={"DOCKER_HOST": f"unix://{local_socket}"},
        config_dir=tmp_path,
    )
    original = request(tmp_path)
    for changed in [
        replace(original, app_image="node:latest"),
        replace(original, criteria_dir=original.app_dir),
    ]:
        with pytest.raises(IsolationUnavailableError):
            service.plan(changed)


async def test_inspect_accepts_docker_canonical_profile_and_network_id(
    tmp_path: Path,
    local_socket: Path,
) -> None:
    runner = DockerFixture()
    original_run = runner.run

    async def docker_encoded(command, cwd, timeout=300, *, stdin=None):
        response = await original_run(command, cwd, timeout, stdin=stdin)
        if "inspect" in command and "image" not in command and response.success:
            data = json.loads(response.stdout)
            record = data[0]
            if record["Name"].endswith("checker"):
                profile = next(
                    value.split("=", 1)[1]
                    for value in record["HostConfig"]["SecurityOpt"]
                    if value.startswith("seccomp=")
                )
                record["HostConfig"]["SecurityOpt"] = [
                    "no-new-privileges=true",
                    "seccomp=" + json.dumps(json.loads(profile), separators=(",", ":")),
                ]
                record["HostConfig"]["NetworkMode"] = "container:" + "c" * 64
                response.stdout = json.dumps(data)
        return response

    runner.run = docker_encoded
    service = LocalDockerIsolation(
        runner=runner, environ={"DOCKER_HOST": f"unix://{local_socket}"}, config_dir=tmp_path
    )
    result = await service.execute(request(tmp_path), b"{}")
    assert result.completed, result.reason


async def test_checker_failure_is_observed_without_losing_its_report(
    tmp_path: Path, local_socket: Path
) -> None:
    runner = DockerFixture()
    original_run = runner.run

    async def failed_check(command, cwd, timeout=300, *, stdin=None):
        response = await original_run(command, cwd, timeout, stdin=stdin)
        if stdin is not None:
            return BuildResult(False, '{"checks":[{"passed":false}]}', "assertion failed", 1)
        return response

    runner.run = failed_check
    service = LocalDockerIsolation(
        runner=runner, environ={"DOCKER_HOST": f"unix://{local_socket}"}, config_dir=tmp_path
    )
    result = await service.execute(request(tmp_path), b"{}")
    assert result.completed and result.returncode == 1 and result.cleanup_complete
    assert '"passed":false' in result.stdout and result.stderr == "assertion failed"


async def test_foreign_replacement_is_never_removed(tmp_path: Path, local_socket: Path) -> None:
    runner = DockerFixture()
    original_run = runner.run
    replaced = False

    async def change_after_check(command, cwd, timeout=300, *, stdin=None):
        nonlocal replaced
        response = await original_run(command, cwd, timeout, stdin=stdin)
        if stdin is not None:
            for name, record in runner.containers.items():
                if name.endswith("checker"):
                    record["Id"] = "e" * 64
                    replaced = True
        return response

    runner.run = change_after_check
    service = LocalDockerIsolation(
        runner=runner, environ={"DOCKER_HOST": f"unix://{local_socket}"}, config_dir=tmp_path
    )
    result = await service.execute(request(tmp_path), b"{}")
    assert replaced and not result.cleanup_complete
    assert not any("rm" in command and "e" * 64 in command for command, _ in runner.calls)


async def test_preflight_consumes_the_same_request_deadline(
    tmp_path: Path, local_socket: Path
) -> None:
    runner = DockerFixture()
    original_run = runner.run

    async def slow_info(command, cwd, timeout=300, *, stdin=None):
        if "info" in command:
            await asyncio.sleep(1.02)
        return await original_run(command, cwd, timeout, stdin=stdin)

    runner.run = slow_info
    service = LocalDockerIsolation(
        runner=runner, environ={"DOCKER_HOST": f"unix://{local_socket}"}, config_dir=tmp_path
    )
    result = await service.execute(replace(request(tmp_path), timeout_s=1), b"{}")
    assert not result.completed and result.code == "isolation_unavailable"
    assert not any("create" in argv for argv, _ in runner.calls)


async def test_cleanup_never_extends_its_total_budget(
    tmp_path: Path, local_socket: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ddk.adapters.verified_isolation as isolation

    runner = DockerFixture()
    original_run = runner.run
    clock = {"ns": 0, "cleanup": False}
    monkeypatch.setattr(isolation.time, "monotonic_ns", lambda: clock["ns"])

    async def expensive_cleanup(command, cwd, timeout=300, *, stdin=None):
        response = await original_run(command, cwd, timeout, stdin=stdin)
        if clock["cleanup"]:
            clock["ns"] += 6_000_000_000
        if stdin is not None:
            clock["cleanup"] = True
        return response

    runner.run = expensive_cleanup
    service = LocalDockerIsolation(
        runner=runner, environ={"DOCKER_HOST": f"unix://{local_socket}"}, config_dir=tmp_path
    )
    result = await service.execute(request(tmp_path), b"{}")
    assert not result.cleanup_complete and not result.completed
    assert result.reason == "isolation_cleanup_failed"


async def test_runtime_readonly_mounts_are_required(tmp_path: Path, local_socket: Path) -> None:
    runner = DockerFixture()
    original_run = runner.run

    async def writable_criteria(command, cwd, timeout=300, *, stdin=None):
        result = await original_run(command, cwd, timeout, stdin=stdin)
        if "exec" in command and "-c" in command and "sync_playwright" not in command[-1]:
            payload = json.loads(result.stdout)
            payload["mounts"] = {"/criteria": "rw", "/results": "rw"}
            result.stdout = json.dumps(payload)
        return result

    runner.run = writable_criteria
    service = LocalDockerIsolation(
        runner=runner, environ={"DOCKER_HOST": f"unix://{local_socket}"}, config_dir=tmp_path
    )
    result = await service.execute(request(tmp_path), b"{}")
    assert not result.completed and result.cleanup_complete
    assert not any(stdin is not None for _, stdin in runner.calls)


@pytest.mark.parametrize(
    "change",
    [
        {"uid": 0},
        {"gid": 0},
        {"checker_command": ("python3", "--remote-debugging-address=0.0.0.0")},
        {"app_command": ("bash", "-c", "npm run dev")},
    ],
)
def test_plan_never_accepts_privileged_or_shell_control(
    tmp_path: Path, local_socket: Path, change: dict
) -> None:
    service = LocalDockerIsolation(
        runner=DockerFixture(),
        environ={"DOCKER_HOST": f"unix://{local_socket}"},
        config_dir=tmp_path,
    )
    with pytest.raises(IsolationUnavailableError):
        service.plan(replace(request(tmp_path), **change))


async def test_cancelled_cleanup_failure_retains_owned_ids(
    tmp_path: Path, local_socket: Path
) -> None:
    runner = DockerFixture()
    runner.cancel_on_checker = True
    runner.remove_fails = True
    service = LocalDockerIsolation(
        runner=runner, environ={"DOCKER_HOST": f"unix://{local_socket}"}, config_dir=tmp_path
    )
    with pytest.raises(asyncio.CancelledError) as cancelled:
        await service.execute(request(tmp_path), b"{}")
    notes = getattr(cancelled.value, "__notes__", [])
    assert any('"cleanup_complete": false' in note and '"app_id"' in note for note in notes)


async def test_bounded_runner_transmits_large_stdio_exactly(tmp_path: Path) -> None:
    import hashlib
    import sys

    from ddk.adapters.verified_isolation import _BoundedDockerRunner

    payload = b"approved input\n" * 100000
    command = [
        sys.executable,
        "-c",
        "import hashlib,sys;print(hashlib.sha256(sys.stdin.buffer.read()).hexdigest())",
    ]
    result = await _BoundedDockerRunner().run(command, tmp_path, timeout=5, stdin=payload)
    assert result.success and result.stdout.strip() == hashlib.sha256(payload).hexdigest()


async def test_bounded_runner_refuses_excessive_checker_output(tmp_path: Path) -> None:
    import sys

    from ddk.adapters.verified_isolation import _BoundedDockerRunner

    result = await _BoundedDockerRunner().run(
        [sys.executable, "-c", "import sys;sys.stdout.buffer.write(b'x'*(11*1024*1024))"],
        tmp_path,
        timeout=5,
    )
    assert not result.success and result.returncode == 125
    assert len(result.stdout.encode()) + len(result.stderr.encode()) <= 10 * 1024 * 1024


async def test_checker_output_limit_never_completes_execution(
    tmp_path: Path, local_socket: Path
) -> None:
    runner = DockerFixture()
    original_run = runner.run

    async def limited_checker(command, cwd, timeout=300, *, stdin=None):
        result = await original_run(command, cwd, timeout, stdin=stdin)
        if stdin is not None:
            return BuildResult(False, "partial report", "docker_output_limit", 125)
        return result

    runner.run = limited_checker
    service = LocalDockerIsolation(
        runner=runner, environ={"DOCKER_HOST": f"unix://{local_socket}"}, config_dir=tmp_path
    )
    result = await service.execute(request(tmp_path), b"{}")
    assert not result.completed and result.code == "isolation_unavailable"
    assert result.cleanup_complete and result.returncode == 125
