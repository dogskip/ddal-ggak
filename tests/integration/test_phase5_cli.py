"""Phase 5 CLI integration tests using fake runtime services."""

from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from ddk.adapters.local_git import LocalGitAdapter
from ddk.cli import app
from ddk.services.pipeline_runner import RuntimeServices
from ddk.services.rollback_controller import RollbackController
from tests.fakes.images import write_png
from tests.fakes.runtime_services import stub_runtime_services

runner = CliRunner()


def _run_git(repo_path: Path, *args: str) -> str:
    """Run a git command in the test repository and return stdout."""
    result = subprocess.run(
        ["git", "-C", str(repo_path), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _init_git_repo(repo_path: Path) -> None:
    """Create a minimal real git repository for rollback integration tests."""
    repo_path.mkdir()
    _run_git(repo_path, "init")
    _run_git(repo_path, "config", "user.name", "DDK Test")
    _run_git(repo_path, "config", "user.email", "ddk@example.com")
    (repo_path / "tracked.txt").write_text("original\n", encoding="utf-8")
    _run_git(repo_path, "add", "tracked.txt")
    _run_git(repo_path, "commit", "-m", "initial")


def test_cli_run_status_and_certify_roundtrip(tmp_path: Path) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    (repo_path / "package.json").write_text(
        json.dumps(
            {
                "name": "phase5-cli",
                "dependencies": {"react": "^18.3.0", "react-dom": "^18.3.0"},
                "devDependencies": {"typescript": "^5.0.0"},
            }
        ),
        encoding="utf-8",
    )
    image_path = write_png(repo_path / "design.png")

    def _build_runtime_services_override(_cfg: object) -> RuntimeServices:
        return stub_runtime_services()

    with patch("ddk.cli.delivery.build_runtime_services", _build_runtime_services_override):
        run_result = runner.invoke(
            app,
            [
                "run",
                str(image_path),
                "--prompt",
                "버튼 컴포넌트 생성",
                "--repo",
                str(repo_path),
            ],
        )
    assert run_result.exit_code == 1, run_result.stdout
    for line in ("저장소 분석 — react", "코드 생성 — 파일 1개", "검증 — ", "판정 — blocked"):
        assert line in run_result.output
    assert (repo_path / ".ddk" / "cases" / "C-001" / "reports" / "scorecard.json").exists()
    assert (repo_path / ".ddk" / "cases" / "C-001" / "reports" / "evidence-pack.json").exists()
    release_payload = json.loads(
        (repo_path / ".ddk" / "cases" / "C-001" / "reports" / "release-decision.json").read_text(
            encoding="utf-8"
        )
    )
    assert "missing-visual-evidence" in {blocker["id"] for blocker in release_payload["blockers"]}

    status_result = runner.invoke(app, ["status", "--repo", str(repo_path), "--json"])
    assert status_result.exit_code == 1, status_result.stdout
    status_payload = json.loads(status_result.stdout)
    assert status_payload["release_decision"] == "blocked"
    assert status_payload["case_id"] == "C-001"

    certify_result = runner.invoke(app, ["certify", "--repo", str(repo_path), "--json"])
    assert certify_result.exit_code == 1, certify_result.stdout
    certify_payload = json.loads(certify_result.stdout)
    assert certify_payload["decision"] == "blocked"
    assert certify_payload["case_id"] == "C-001"
    assert "evidence_pack" in certify_payload


def test_cli_rollback_delegates_to_checkpoint_ref(tmp_path: Path) -> None:
    class FakeGitAdapter:
        def __init__(self) -> None:
            self.calls: list[tuple[Path, str]] = []

        async def rollback_to(self, repo_path: Path, ref_name: str, *, force: bool = False) -> None:
            self.calls.append((repo_path, ref_name))

    fake_git = FakeGitAdapter()
    with patch("ddk.cli.delivery.LocalGitAdapter", new=lambda: fake_git):
        result = runner.invoke(
            app,
            [
                "rollback",
                "--repo",
                str(tmp_path),
                "--case-id",
                "C-123",
                "--attempt",
                "2",
            ],
        )

    assert result.exit_code == 0, result.stdout
    assert fake_git.calls == [(tmp_path.resolve(), "refs/ddk/fix/C-123/attempt-2")]


def test_cli_rollback_restores_real_git_checkpoint(tmp_path: Path) -> None:
    """CLI rollback should restore tracked files to the saved checkpoint ref."""
    repo_path = tmp_path / "repo"
    _init_git_repo(repo_path)
    tracked_file = repo_path / "tracked.txt"

    controller = RollbackController(git=LocalGitAdapter(), repo_path=repo_path)
    asyncio.run(controller.create_checkpoint(case_id="C-456", attempt_number=1))

    tracked_file.write_text("changed\n", encoding="utf-8")
    assert tracked_file.read_text(encoding="utf-8") == "changed\n"

    result = runner.invoke(
        app,
        [
            "rollback",
            "--repo",
            str(repo_path),
            "--case-id",
            "C-456",
            "--attempt",
            "1",
            "--force",
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert tracked_file.read_text(encoding="utf-8") == "original\n"
    assert _run_git(repo_path, "rev-parse", "--verify", "refs/ddk/fix/C-456/attempt-1")


def test_cli_run_json_keeps_stdout_machine_readable(tmp_path: Path) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    (repo_path / "package.json").write_text(
        json.dumps({"name": "x", "dependencies": {"react": "^18.3.0"}}), encoding="utf-8"
    )
    image_path = write_png(repo_path / "design.png")

    with patch("ddk.cli.delivery.build_runtime_services", lambda _cfg: stub_runtime_services()):
        result = runner.invoke(
            app, ["run", str(image_path), "--prompt", "x", "--repo", str(repo_path), "--json"]
        )

    assert json.loads(result.stdout)["case_id"] == "C-001"
    assert "코드 생성" in result.output
