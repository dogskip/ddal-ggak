"""Local, fail-closed Docker execution for the approved D2 boundary.

Only immutable local image IDs and host-owned checker commands are accepted.
The caller supplies private copies under owned_root, never the source repository.
Docker inspect is policy evidence; project output is not policy evidence.

Options: https://docs.docker.com/reference/cli/docker/container/run/
Networking: https://docs.docker.com/engine/network/#container-networks
Context precedence: https://docs.docker.com/reference/cli/docker/
Chromium: https://playwright.dev/python/docs/docker
Profile base: moby/profiles@6fe7deb1b9fb7c0397a4593480d7d22b9ee8caef
Namespace allowance: microsoft/playwright@ae935a43d9e376e4759548f6b3c6905c7b282333
The bundled profile retains current socket-family restrictions, denies socketcall,
and adds only Playwright's clone/setns/unshare allowance to the Docker default.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import platform
import re
import shutil
import stat
import tempfile
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol, cast
from urllib.parse import urlsplit
from uuid import uuid4

from ddk.adapters.build_runner import BuildResult
from ddk.adapters.subprocess_build_runner import start_owned_process, stop_owned_process
from ddk.security.file_access import read_regular

_MEMORY = 2 * 1024**3
_SHM = 256 * 1024**2
_PIDS = 256
_INPUT_LIMIT = 2 * 1024**2
_LABEL = "io.ddk.isolation.owner"
_PROFILE = Path(__file__).resolve().parents[1] / "assets/verified-change/chromium-seccomp.json"
_PROFILE_SHA256 = "4ff366b84d0d0d63dcc0f226696ad6c09dee37fd380dc0bcd184e2ef96f45efd"
_IMAGE = re.compile(r"sha256:[a-f0-9]{64}")
_ID = re.compile(r"[a-f0-9]{64}")
_TMPFS = "rw,noexec,nosuid,nodev,size=67108864,mode=1777"

_NODE_PROBE = r"""const f=require('fs'),net=require('net');
const text=p=>f.readFileSync(p,'utf8').trim();
const status=Object.fromEntries(text('/proc/self/status').split('\n').map(x=>x.split(/:\s*/,2)));
const cpu=text('/sys/fs/cgroup/cpu.max').split(' ');
const entries=text('/proc/self/mountinfo').split('\n').map(line=>line.split(' '));
const selected=['/','/tmp','/workspace','/criteria','/results'];
const mounts=Object.fromEntries(entries.filter(parts=>selected.includes(parts[4]))
.map(parts=>[parts[4],parts[5].split(',').includes('ro')?'ro':'rw']));
const tmp=entries.find(parts=>parts[4]==='/tmp');const shm=f.statfsSync('/dev/shm');
const result={uid:process.getuid(),gid:process.getgid(),no_new_privs:Number(status.NoNewPrivs),
seccomp:Number(status.Seccomp),cap_eff:parseInt(status.CapEff,16),
pid_ns:f.readlinkSync('/proc/self/ns/pid'),mnt_ns:f.readlinkSync('/proc/self/ns/mnt'),
net_ns:f.readlinkSync('/proc/self/ns/net'),interfaces:f.readdirSync('/sys/class/net'),
memory_max:Number(text('/sys/fs/cgroup/memory.max')),pids_max:Number(text('/sys/fs/cgroup/pids.max')),
cpu_quota:Number(cpu[0]),cpu_period:Number(cpu[1]),mounts:mounts,tmp_flags:tmp[5].split(','),shm_bytes:shm.bsize*shm.blocks};
const socket=net.createConnection({host:'192.0.2.1',port:9});
let done=false; const finish=blocked=>{if(done)return;done=true;socket.destroy();
result.external_blocked=blocked;console.log(JSON.stringify(result));};
socket.once('connect',()=>finish(false));socket.once('error',e=>finish(['ENETUNREACH','EHOSTUNREACH'].includes(e.code)));
setTimeout(()=>finish(false),500).unref();"""

_PYTHON_PROBE = r"""import json,os,socket
from pathlib import Path
text=lambda p:Path(p).read_text().strip()
status=dict(line.split(':',1) for line in text('/proc/self/status').splitlines())
quota,period=text('/sys/fs/cgroup/cpu.max').split()
entries=[line.split() for line in text('/proc/self/mountinfo').splitlines()]
selected={'/','/tmp','/workspace','/criteria','/results'}
mounts={parts[4]:('ro' if 'ro' in parts[5].split(',') else 'rw')
        for parts in entries if parts[4] in selected}
tmp=next(parts[5].split(',') for parts in entries if parts[4]=='/tmp')
shm=os.statvfs('/dev/shm')
s=socket.socket();s.settimeout(0.5)
try:
    s.connect(('192.0.2.1',9));blocked=False
except OSError as error:
    blocked=error.errno in (101,113)
finally:
    s.close()
print(json.dumps(dict(uid=os.getuid(),gid=os.getgid(),no_new_privs=int(status['NoNewPrivs']),
seccomp=int(status['Seccomp']),cap_eff=int(status['CapEff'],16),
pid_ns=os.readlink('/proc/self/ns/pid'),mnt_ns=os.readlink('/proc/self/ns/mnt'),
net_ns=os.readlink('/proc/self/ns/net'),interfaces=os.listdir('/sys/class/net'),external_blocked=blocked,
memory_max=int(text('/sys/fs/cgroup/memory.max')),pids_max=int(text('/sys/fs/cgroup/pids.max')),
cpu_quota=int(quota),cpu_period=int(period),mounts=mounts,tmp_flags=tmp,shm_bytes=shm.f_frsize*shm.f_blocks)))"""

_BROWSER_PROBE = """import json
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,chromium_sandbox=True)
    try:
        page=browser.new_page()
        page.set_content('<title>isolated</title>')
        assert page.title()=='isolated'
    finally:
        browser.close()
print(json.dumps(dict(started=True,headless=True,chromium_sandbox=True)))"""


class IsolationUnavailableError(ValueError):
    """A required execution boundary could not be established."""


@dataclass(frozen=True)
class DockerEndpoint:
    uri: str
    context: str


@dataclass(frozen=True)
class IsolationAvailability:
    available: bool
    reason: str = ""
    endpoint: DockerEndpoint | None = None
    boundary: str | None = None
    code: Literal["isolation_unavailable"] | None = "isolation_unavailable"


@dataclass(frozen=True)
class IsolationRequest:
    owned_root: Path
    app_dir: Path
    criteria_dir: Path
    results_dir: Path
    app_image: str
    checker_image: str
    app_command: tuple[str, ...]
    checker_command: tuple[str, ...]
    uid: int = field(default_factory=os.getuid)
    gid: int = field(default_factory=os.getgid)
    timeout_s: int = 300


@dataclass(frozen=True)
class IsolationPlan:
    request: IsolationRequest
    endpoint: DockerEndpoint
    owner: str
    app_name: str
    checker_name: str
    app_create: tuple[str, ...]
    checker_create: tuple[str, ...]
    seccomp_sha256: str


@dataclass(frozen=True)
class IsolationResult:
    completed: bool = False
    policy_verified: bool = False
    cleanup_complete: bool = True
    assurance: Literal["isolated"] = "isolated"
    code: Literal["isolation_unavailable"] | None = "isolation_unavailable"
    reason: str = ""
    stdout: str = ""
    stderr: str = ""
    returncode: int | None = None
    evidence: dict[str, object] = field(default_factory=dict[str, object])


class DockerRunner(Protocol):
    async def run(
        self, command: list[str], cwd: Path, timeout: int = 300, *, stdin: bytes | None = None
    ) -> BuildResult: ...


def _object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise IsolationUnavailableError("invalid_docker_response")
    return cast(dict[str, object], value)


def _decode(text: str) -> object:
    if len(text.encode()) > _INPUT_LIMIT:
        raise IsolationUnavailableError("docker_response_limit")
    try:
        return cast(object, json.loads(text))
    except ValueError as exc:
        raise IsolationUnavailableError("invalid_docker_response") from exc


def _one(text: str) -> dict[str, object]:
    value = _decode(text)
    if not isinstance(value, list) or len(cast(list[object], value)) != 1:
        raise IsolationUnavailableError("invalid_docker_inspect")
    return _object(cast(list[object], value)[0])


def resolve_endpoint(environ: Mapping[str, str], config_dir: Path) -> DockerEndpoint:
    """Read only local selection metadata before allowing any daemon command."""
    context = environ.get("DOCKER_CONTEXT", "")
    host = environ.get("DOCKER_HOST", "")
    if not context and not host:
        config = config_dir / "config.json"
        if config.exists():
            context_value = _object(
                _decode(read_regular(config.resolve(), _INPUT_LIMIT).decode())
            ).get("currentContext", "default")
            if not isinstance(context_value, str):
                raise IsolationUnavailableError("invalid_docker_context")
            context = context_value
    if context and context != "default":
        matches: list[str] = []
        for metadata in (config_dir / "contexts/meta").glob("*/meta.json"):
            data = _object(_decode(read_regular(metadata.resolve(), _INPUT_LIMIT).decode()))
            if data.get("Name") == context:
                endpoint = _object(_object(data.get("Endpoints")).get("docker")).get("Host")
                if not isinstance(endpoint, str):
                    raise IsolationUnavailableError("invalid_docker_endpoint")
                matches.append(endpoint)
        if len(matches) != 1:
            raise IsolationUnavailableError("docker_context_unavailable")
        host = matches[0]
    elif context == "default" or not host:
        host = "unix:///var/run/docker.sock"
    parsed = urlsplit(host)
    if (
        parsed.scheme != "unix"
        or parsed.netloc
        or parsed.query
        or parsed.fragment
        or not parsed.path.startswith("/")
        or "%" in parsed.path
        or any(ord(char) < 32 for char in host)
    ):
        raise IsolationUnavailableError("remote_or_invalid_endpoint")
    try:
        info = Path(parsed.path).stat()
    except OSError as exc:
        raise IsolationUnavailableError("local_socket_unavailable") from exc
    if not stat.S_ISSOCK(info.st_mode) or info.st_uid not in {0, os.getuid()}:
        raise IsolationUnavailableError("local_socket_unavailable")
    return DockerEndpoint(host, context or "environment")


class _BoundedDockerRunner:
    async def run(
        self, command: list[str], cwd: Path, timeout: int = 300, *, stdin: bytes | None = None
    ) -> BuildResult:
        deadline = time.monotonic_ns() + timeout * 1_000_000_000
        process, output = await start_owned_process(
            command, cwd, stdin=asyncio.subprocess.PIPE if stdin is not None else None
        )
        code: int | None = None
        reason = ""
        try:
            if stdin is not None:
                assert process.stdin is not None
                process.stdin.write(stdin)
                await asyncio.wait_for(
                    process.stdin.drain(), max(0, (deadline - time.monotonic_ns()) / 1e9)
                )
                process.stdin.close()
            if await output.wait(deadline):
                code, reason = 125, "docker_output_limit"
        except TimeoutError:
            code, reason = 124, "docker_timeout"
        finally:
            await stop_owned_process(process, output)
        stdout, stderr = output.text(reason)
        returncode = code if code is not None else (process.returncode or 0)
        return BuildResult(returncode == 0, stdout, stderr, returncode)


class LocalDockerIsolation:
    """Construct and verify two owned containers, without a host execution fallback."""

    def __init__(
        self,
        *,
        runner: DockerRunner | None = None,
        environ: Mapping[str, str] | None = None,
        config_dir: Path | None = None,
        executable: str | None = None,
    ) -> None:
        self._runner = runner or _BoundedDockerRunner()
        self._environ = dict(os.environ if environ is None else environ)
        self._config = config_dir or Path(
            self._environ.get("DOCKER_CONFIG", str(Path.home() / ".docker"))
        )
        self._docker = executable or shutil.which("docker") or "docker"

    async def _call(
        self,
        endpoint: DockerEndpoint,
        control: Path,
        args: list[str],
        timeout: float,
        stdin: bytes | None = None,
    ) -> BuildResult:
        if timeout <= 0:
            raise IsolationUnavailableError("isolation_deadline")
        try:
            return await asyncio.wait_for(
                self._runner.run(
                    [
                        self._docker,
                        "--config",
                        str(control / "client"),
                        "--host",
                        endpoint.uri,
                        *args,
                    ],
                    control,
                    math.ceil(timeout),
                    stdin=stdin,
                ),
                timeout,
            )
        except TimeoutError as exc:
            raise IsolationUnavailableError("isolation_deadline") from exc

    async def preflight(self, *, deadline_ns: int | None = None) -> IsolationAvailability:
        try:
            endpoint = resolve_endpoint(self._environ, self._config)
            with tempfile.TemporaryDirectory(prefix="ddk-isolation-") as folder:
                result = await self._call(
                    endpoint,
                    Path(folder),
                    ["info", "--format", "{{json .}}"],
                    min(10, (deadline_ns - time.monotonic_ns()) / 1e9)
                    if deadline_ns is not None
                    else 10,
                )
            if not result.success:
                raise IsolationUnavailableError("daemon_unavailable")
            data = _object(_decode(result.stdout))
            options = data.get("SecurityOptions")
            if (
                data.get("OSType") != "linux"
                or data.get("CgroupVersion") != "2"
                or not isinstance(options, list)
                or "name=seccomp,profile=builtin" not in options
                or any(
                    data.get(key) is not True for key in ["MemoryLimit", "PidsLimit", "CpuCfsQuota"]
                )
            ):
                raise IsolationUnavailableError("daemon_policy_unavailable")
            boundary = "linux-user" if platform.system() == "Linux" else "linux-vm"
            return IsolationAvailability(True, endpoint=endpoint, boundary=boundary, code=None)
        except (OSError, ValueError) as exc:
            return IsolationAvailability(False, str(exc))

    def plan(self, request: IsolationRequest) -> IsolationPlan:
        endpoint = resolve_endpoint(self._environ, self._config)
        if request.uid <= 0 or request.gid <= 0 or not 0 < request.timeout_s <= 1800:
            raise IsolationUnavailableError("invalid_isolation_limits_or_user")
        if not all(_IMAGE.fullmatch(value) for value in [request.app_image, request.checker_image]):
            raise IsolationUnavailableError("immutable_local_image_required")
        for value in [cast(object, request.app_command), cast(object, request.checker_command)]:
            if not isinstance(value, tuple):
                raise IsolationUnavailableError("command_array_required")
            parts = cast(tuple[object, ...], value)
            if not parts or any(
                not isinstance(arg, str) or not arg or "\x00" in arg for arg in parts
            ):
                raise IsolationUnavailableError("command_array_required")
            command = cast(tuple[str, ...], value)
            if (
                Path(command[0]).name in {"sh", "bash", "zsh", "dash", "fish", "ksh", "csh"}
                and "-c" in command
            ):
                raise IsolationUnavailableError("shell_control_forbidden")
        if any(
            arg == "--no-sandbox" or arg.startswith("--remote-debugging-")
            for arg in request.checker_command
        ):
            raise IsolationUnavailableError("unsafe_checker_command")
        root = request.owned_root.resolve()
        if (
            request.owned_root.is_symlink()
            or not root.is_dir()
            or root.stat().st_uid != os.getuid()
        ):
            raise IsolationUnavailableError("owned_copy_required")
        paths = [request.app_dir, request.criteria_dir, request.results_dir]
        for path in paths:
            if not path.is_dir() or path.is_symlink() or path.resolve().parent != root:
                raise IsolationUnavailableError("separate_owned_directories_required")
            if any(char in str(path) for char in [",", "\n", "\x00"]):
                raise IsolationUnavailableError("invalid_bind_path")
        if len({path.resolve() for path in paths}) != len(paths):
            raise IsolationUnavailableError("overlapping_mounts")
        payload = read_regular(_PROFILE, _INPUT_LIMIT)
        if hashlib.sha256(payload).hexdigest() != _PROFILE_SHA256:
            raise IsolationUnavailableError("checker_seccomp_changed")
        owner = str(uuid4())
        app_name, checker_name = f"ddk-{owner}-app", f"ddk-{owner}-checker"
        common = [
            "create",
            "--pull",
            "never",
            "--init",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges=true",
            "--user",
            f"{request.uid}:{request.gid}",
            "--cpus",
            "1",
            "--memory",
            str(_MEMORY),
            "--memory-swap",
            str(_MEMORY),
            "--pids-limit",
            str(_PIDS),
            "--shm-size",
            str(_SHM),
            "--ipc",
            "private",
            "--tmpfs",
            f"/tmp:{_TMPFS}",
            "--env",
            "HOME=/tmp",
            "--label",
            f"{_LABEL}={owner}",
        ]
        app = [
            *common,
            "--name",
            app_name,
            "--label",
            "io.ddk.isolation.role=app",
            "--network",
            "none",
            "--workdir",
            "/workspace",
            "--mount",
            f"type=bind,source={request.app_dir.resolve()},target=/workspace",
            "--entrypoint",
            request.app_command[0],
            request.app_image,
            *request.app_command[1:],
        ]
        checker = [
            *common,
            "--name",
            checker_name,
            "--label",
            "io.ddk.isolation.role=checker",
            "--network",
            f"container:{app_name}",
            "--security-opt",
            f"seccomp={_PROFILE}",
            "--workdir",
            "/results",
            "--mount",
            f"type=bind,source={request.criteria_dir.resolve()},target=/criteria,readonly",
            "--mount",
            f"type=bind,source={request.results_dir.resolve()},target=/results",
            "--entrypoint",
            "python3",
            request.checker_image,
            "-I",
            "-c",
            "import time;time.sleep(1800)",
        ]
        return IsolationPlan(
            request,
            endpoint,
            owner,
            app_name,
            checker_name,
            tuple(app),
            tuple(checker),
            _PROFILE_SHA256,
        )

    def _verify_record(
        self,
        plan: IsolationPlan,
        record: dict[str, object],
        role: str,
        app_id: object = None,
    ) -> None:
        config, host = _object(record.get("Config")), _object(record.get("HostConfig"))
        request = plan.request
        name = plan.app_name if role == "app" else plan.checker_name
        labels = _object(config.get("Labels"))
        expected_image = request.app_image if role == "app" else request.checker_image
        expected_network = "none" if role == "app" else f"container:{plan.app_name}"
        if (
            not _ID.fullmatch(str(record.get("Id")))
            or record.get("Name") != "/" + name
            or labels.get(_LABEL) != plan.owner
            or labels.get("io.ddk.isolation.role") != role
            or config.get("User") != f"{request.uid}:{request.gid}"
            or record.get("Image") != expected_image
            or host.get("Privileged") is not False
            or host.get("ReadonlyRootfs") is not True
            or host.get("Init") is not True
            or host.get("CapAdd") not in (None, [])
            or host.get("CapDrop") != ["ALL"]
            or host.get("NetworkMode")
            not in {expected_network, f"container:{app_id}" if role == "checker" else "none"}
            or host.get("PidMode") not in ("", "private")
            or host.get("IpcMode") != "private"
            or host.get("Memory") != _MEMORY
            or host.get("MemorySwap") != _MEMORY
            or host.get("NanoCpus") != 1_000_000_000
            or host.get("PidsLimit") != _PIDS
            or host.get("ShmSize") != _SHM
            or any(
                host.get(key) not in (None, {}, [])
                for key in ["PortBindings", "Devices", "Binds", "VolumesFrom"]
            )
            or host.get("Tmpfs") != {"/tmp": _TMPFS}
        ):
            raise IsolationUnavailableError("container_policy_mismatch")
        options = host.get("SecurityOpt")
        if not isinstance(options, list) or "no-new-privileges=true" not in options:
            raise IsolationUnavailableError("container_security_options_mismatch")
        seccomp = [
            option.removeprefix("seccomp=")
            for option in cast(list[object], options)
            if isinstance(option, str) and option.startswith("seccomp=")
        ]
        if role == "checker":
            if len(cast(list[object], options)) != 2 or len(seccomp) != 1:
                raise IsolationUnavailableError("container_seccomp_mismatch")
            profile = read_regular(_PROFILE, _INPUT_LIMIT)
            if hashlib.sha256(profile).hexdigest() != plan.seccomp_sha256:
                raise IsolationUnavailableError("checker_seccomp_changed")
            if _decode(seccomp[0]) != _decode(profile.decode()):
                raise IsolationUnavailableError("container_seccomp_mismatch")
        elif options != ["no-new-privileges=true"]:
            raise IsolationUnavailableError("container_seccomp_mismatch")
        expected = (
            [(str(request.app_dir.resolve()), "/workspace", True)]
            if role == "app"
            else [
                (str(request.criteria_dir.resolve()), "/criteria", False),
                (str(request.results_dir.resolve()), "/results", True),
            ]
        )
        mounts = record.get("Mounts")
        if not isinstance(mounts, list):
            raise IsolationUnavailableError("container_mounts_mismatch")
        observed = [
            (_object(item).get("Source"), _object(item).get("Destination"), _object(item).get("RW"))
            for item in cast(list[object], mounts)
        ]
        if observed != expected or any(
            _object(item).get("Type") != "bind" for item in cast(list[object], mounts)
        ):
            raise IsolationUnavailableError("container_mounts_mismatch")

    async def execute(self, request: IsolationRequest, checker_input: bytes) -> IsolationResult:
        if type(request.timeout_s) is not int or not 0 < request.timeout_s <= 1800:
            return IsolationResult(reason="invalid_isolation_deadline")
        deadline = time.monotonic_ns() + request.timeout_s * 1_000_000_000
        availability = await self.preflight(deadline_ns=deadline)
        if not availability.available:
            return IsolationResult(reason=availability.reason)
        if len(checker_input) > _INPUT_LIMIT:
            return IsolationResult(reason="checker_input_limit")
        try:
            plan = self.plan(request)
        except (OSError, ValueError) as exc:
            return IsolationResult(reason=str(exc))
        attempted: list[str] = []
        identities: dict[str, tuple[object, object]] = {}
        verified = False
        answer: BuildResult | None = None
        reason = ""
        cancelled: asyncio.CancelledError | None = None
        evidence: dict[str, object] = {
            "owner": plan.owner,
            "app_name": plan.app_name,
            "checker_name": plan.checker_name,
            "endpoint": plan.endpoint.uri,
            "context": plan.endpoint.context,
            "boundary": availability.boundary,
            "seccomp_sha256": plan.seccomp_sha256,
        }
        cleanup = True
        with tempfile.TemporaryDirectory(prefix="ddk-isolation-") as folder:
            control = Path(folder)

            async def call(args: list[str], stdin: bytes | None = None) -> BuildResult:
                remaining = (deadline - time.monotonic_ns()) / 1e9
                if remaining <= 0:
                    raise IsolationUnavailableError("isolation_deadline")
                result = await self._call(plan.endpoint, control, args, remaining, stdin)
                if not result.success:
                    raise IsolationUnavailableError("docker_operation_failed")
                return result

            try:
                for image in [request.app_image, request.checker_image]:
                    record = _one((await call(["image", "inspect", image])).stdout)
                    if (
                        record.get("Id") != image
                        or record.get("Os") != "linux"
                        or _object(record.get("Config")).get("Volumes") not in (None, {})
                    ):
                        raise IsolationUnavailableError("local_image_policy_mismatch")
                for name, argv, role in [
                    (plan.app_name, plan.app_create, "app"),
                    (plan.checker_name, plan.checker_create, "checker"),
                ]:
                    attempted.append(name)
                    await call(list(argv))
                    record = _one((await call(["inspect", name])).stdout)
                    self._verify_record(plan, record, role, evidence.get("app_id"))
                    identities[name] = (record.get("Id"), record.get("Created"))
                    evidence[role + "_id"] = record["Id"]
                    await call(["start", name])
                app = _object(
                    _decode((await call(["exec", plan.app_name, "node", "-e", _NODE_PROBE])).stdout)
                )
                checker = _object(
                    _decode(
                        (
                            await call(
                                ["exec", plan.checker_name, "python3", "-I", "-c", _PYTHON_PROBE]
                            )
                        ).stdout
                    )
                )
                for role, probe in [("app", app), ("checker", checker)]:
                    if any(
                        probe.get(key) != value
                        for key, value in {
                            "uid": request.uid,
                            "gid": request.gid,
                            "no_new_privs": 1,
                            "seccomp": 2,
                            "cap_eff": 0,
                            "interfaces": ["lo"],
                            "external_blocked": True,
                            "memory_max": _MEMORY,
                            "pids_max": _PIDS,
                            "cpu_quota": 100000,
                            "cpu_period": 100000,
                        }.items()
                    ):
                        raise IsolationUnavailableError("runtime_policy_mismatch")
                    expected_mounts = {"/": "ro", "/tmp": "rw"}
                    expected_mounts.update(
                        {"/workspace": "rw"}
                        if role == "app"
                        else {"/criteria": "ro", "/results": "rw"}
                    )
                    tmp_flags = probe.get("tmp_flags")
                    if (
                        probe.get("mounts") != expected_mounts
                        or probe.get("shm_bytes") != _SHM
                        or not isinstance(tmp_flags, list)
                        or not all(isinstance(item, str) for item in cast(list[object], tmp_flags))
                        or not {"noexec", "nosuid", "nodev"}.issubset(cast(list[str], tmp_flags))
                    ):
                        raise IsolationUnavailableError("runtime_mount_policy_mismatch")
                if (
                    not app.get("net_ns")
                    or app.get("net_ns") != checker.get("net_ns")
                    or any(
                        not app.get(key) or app.get(key) == checker.get(key)
                        for key in ["pid_ns", "mnt_ns"]
                    )
                ):
                    raise IsolationUnavailableError("runtime_namespace_mismatch")
                browser = _object(
                    _decode(
                        (
                            await call(
                                ["exec", plan.checker_name, "python3", "-I", "-c", _BROWSER_PROBE]
                            )
                        ).stdout
                    )
                )
                if browser != {"started": True, "headless": True, "chromium_sandbox": True}:
                    raise IsolationUnavailableError("browser_policy_unavailable")
                evidence.update({"app_probe": app, "checker_probe": checker, "browser": browser})
                verified = True
                remaining = (deadline - time.monotonic_ns()) / 1e9
                if remaining <= 0:
                    raise IsolationUnavailableError("isolation_deadline")
                answer = await self._call(
                    plan.endpoint,
                    control,
                    ["exec", "--interactive", plan.checker_name, *request.checker_command],
                    remaining,
                    checker_input,
                )
                if answer.returncode in {124, 125, 126, 127}:
                    raise IsolationUnavailableError("checker_execution_unavailable")
            except asyncio.CancelledError as exc:
                cancelled = exc
            except (OSError, ValueError) as exc:
                reason = str(exc)
            finally:
                cleanup_task = asyncio.create_task(
                    self._cleanup(plan, control, attempted, identities)
                )
                interrupted = False
                while not cleanup_task.done():
                    try:
                        await asyncio.shield(cleanup_task)
                    except asyncio.CancelledError:
                        interrupted = True
                cleanup = cleanup_task.result()
                if interrupted and cancelled is None:
                    cancelled = asyncio.CancelledError()
        completed = verified and answer is not None and cleanup and cancelled is None and not reason
        result = IsolationResult(
            completed,
            verified,
            cleanup,
            code=None if completed else "isolation_unavailable",
            reason=reason if cleanup else "isolation_cleanup_failed",
            stdout=answer.stdout if answer else "",
            stderr=answer.stderr if answer else "",
            returncode=answer.returncode if answer else None,
            evidence=evidence,
        )
        if cancelled is not None:
            cancelled.add_note(
                json.dumps(
                    {
                        "code": "isolation_cancelled",
                        "cleanup_complete": cleanup,
                        "evidence": evidence,
                    },
                    sort_keys=True,
                )
            )
            raise cancelled
        return result

    async def _cleanup(
        self,
        plan: IsolationPlan,
        control: Path,
        names: list[str],
        identities: dict[str, tuple[object, object]],
    ) -> bool:
        deadline = time.monotonic_ns() + 10_000_000_000
        complete = True

        async def call(args: list[str]) -> BuildResult:
            remaining = (deadline - time.monotonic_ns()) / 1e9
            return await self._call(plan.endpoint, control, args, remaining)

        for name in reversed(names):
            try:
                inspected = await call(["inspect", name])
                if not inspected.success and "No such" in inspected.stderr:
                    continue
                if not inspected.success:
                    complete = False
                    continue
                record = _one(inspected.stdout)
                labels = _object(_object(record.get("Config")).get("Labels"))
                identifier = str(record.get("Id"))
                if (
                    labels.get(_LABEL) != plan.owner
                    or record.get("Name") != "/" + name
                    or not _ID.fullmatch(identifier)
                    or (
                        name in identities
                        and identities[name] != (record.get("Id"), record.get("Created"))
                    )
                ):
                    complete = False
                    continue
                removed = await call(["rm", "--force", identifier])
                check = await call(["inspect", identifier])
                complete = (
                    complete and removed.success and not check.success and "No such" in check.stderr
                )
            except (OSError, ValueError):
                complete = False
        return complete and time.monotonic_ns() <= deadline
