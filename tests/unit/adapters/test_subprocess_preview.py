"""SubprocessPreviewLauncher: starts a local server, waits until it listens, always cleans up."""

from __future__ import annotations

import shutil
import socket
import urllib.request
from pathlib import Path

import pytest

from ddk.adapters.preview import PreviewStartError
from ddk.adapters.subprocess_preview import SubprocessPreviewLauncher

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is required")

_SERVER = (
    "require('http').createServer((q, r) => r.end('served'))"
    ".listen(Number(process.argv[1]), '127.0.0.1')"
)


def _refused(host: str, port: int) -> bool:
    with socket.socket() as sock:
        sock.settimeout(1)
        return sock.connect_ex((host, port)) != 0


class TestStart:
    async def test_owned_output_is_available_without_private_session_access(self, tmp_path):
        script = "console.log('preview-ready');console.error('preview-warning');" + _SERVER
        session = await SubprocessPreviewLauncher().start(
            ["node", "-e", script, "{port}"], tmp_path, timeout_s=20
        )
        try:
            stdout, stderr = session.output()
            assert "preview-ready" in stdout
            assert "preview-warning" in stderr
        finally:
            await session.stop()

    async def test_serves_on_the_chosen_port_and_stop_releases_it(self, tmp_path: Path) -> None:
        launcher = SubprocessPreviewLauncher()

        session = await launcher.start(["node", "-e", _SERVER, "{port}"], tmp_path, timeout_s=20)
        try:
            with urllib.request.urlopen(session.url, timeout=5) as response:  # noqa: S310
                assert response.read() == b"served"
            assert session.url.startswith("http://127.0.0.1:")
        finally:
            await session.stop()

        port = int(session.url.rsplit(":", 1)[1].rstrip("/"))
        assert _refused("127.0.0.1", port)

    async def test_stop_twice_is_harmless(self, tmp_path: Path) -> None:
        session = await SubprocessPreviewLauncher().start(
            ["node", "-e", _SERVER, "{port}"], tmp_path, timeout_s=20
        )

        await session.stop()
        await session.stop()

    async def test_early_exit_reports_what_the_server_said(self, tmp_path: Path) -> None:
        script = "console.error('config exploded'); process.exit(3)"

        with pytest.raises(PreviewStartError, match=r"exited with code 3.*config exploded"):
            await SubprocessPreviewLauncher().start(["node", "-e", script], tmp_path, timeout_s=20)

    async def test_server_that_never_listens_times_out_and_is_killed(self, tmp_path: Path) -> None:
        marker = tmp_path / "pid.txt"
        script = (
            f"require('fs').writeFileSync({str(marker)!r}, String(process.pid));"
            " setTimeout(() => {}, 60000)"
        )

        with pytest.raises(PreviewStartError, match="did not start listening within 1s"):
            await SubprocessPreviewLauncher().start(["node", "-e", script], tmp_path, timeout_s=1)

        pid = int(marker.read_text())
        with pytest.raises(ProcessLookupError):
            import os

            os.kill(pid, 0)

    async def test_commands_outside_the_allow_list_are_refused(self, tmp_path: Path) -> None:
        with pytest.raises(PreviewStartError, match="not allowed"):
            await SubprocessPreviewLauncher().start(["python3", "-m", "http.server"], tmp_path)

    async def test_secrets_in_the_environment_do_not_reach_the_server(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-secret-value")
        script = "console.error(JSON.stringify(Object.keys(process.env))); process.exit(1)"

        with pytest.raises(PreviewStartError) as raised:
            await SubprocessPreviewLauncher().start(["node", "-e", script], tmp_path, timeout_s=20)

        assert "ANTHROPIC_API_KEY" not in str(raised.value)
        assert "PATH" in str(raised.value)
