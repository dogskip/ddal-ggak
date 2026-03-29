"""Phase 5 CLI integration tests using fake runtime services."""

from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from typer.testing import CliRunner

from ddk.adapters.build_runner import BuildResult
from ddk.adapters.filesystem import FilesystemAdapter
from ddk.adapters.local_git import LocalGitAdapter
from ddk.adapters.screenshot_diff import SSIMResult
from ddk.cli import app
from ddk.services.pipeline_runner import RuntimeServices
from ddk.services.rollback_controller import RollbackController
from tests.fakes import FakeLLMAdapter, FakePlaywrightAdapter
from tests.fakes.fake_sandbox import TempDirSandbox

runner = CliRunner()

_INTENT_GRAPH_RESPONSE = json.dumps(
    {
        "layout_regions": [],
        "components": [],
        "interactions": [],
        "unresolved_items": [],
        "confidence": 0.9,
    }
)

_DESIGN_SYSTEM_RESPONSE = json.dumps(
    {
        "inferred_tokens": [],
        "primitive_components": ["Button"],
        "token_source": "llm",
    }
)

_GENERATION_PLAN_RESPONSE = json.dumps(
    {
        "nodes": [
            {
                "id": "node-btn",
                "node_type": "component",
                "target_path": "src/components/Button.tsx",
                "dependencies": [],
                "validation_hooks": [],
                "repair_hooks": [],
            }
        ],
        "execution_order": ["node-btn"],
        "target_files": ["src/components/Button.tsx"],
        "validation_hooks": [],
        "estimated_node_count": 1,
    }
)

_GENERATED_NODE_RESPONSE = json.dumps(
    {
        "files": [
            {
                "path": "src/components/Button.tsx",
                "content": "export const Button = () => <button>Click</button>;",
                "language": "typescript",
                "source_node_id": "node-btn",
                "is_new": True,
            }
        ],
        "entry_point": "src/components/Button.tsx",
        "component_exports": ["Button"],
    }
)

_NORMALIZATION_RESPONSE = json.dumps(
    {
        "convention_fixes": [],
        "unresolved_drift": [],
        "patched_files": {},
    }
)


def _runtime_services() -> RuntimeServices:
    fake_llm = FakeLLMAdapter(
        responses={
            "you": _INTENT_GRAPH_RESPONSE,
            "analyze": _DESIGN_SYSTEM_RESPONSE,
            "senior": _GENERATION_PLAN_RESPONSE,
            "generate": _GENERATED_NODE_RESPONSE,
            "normalize": _NORMALIZATION_RESPONSE,
        }
    )
    git_stub = MagicMock()
    git_stub.status = MagicMock(return_value={})
    git_stub.diff = MagicMock(return_value="")
    git_stub.log = MagicMock(return_value=[])
    git_stub.create_worktree = AsyncMock()
    git_stub.remove_worktree = AsyncMock()
    git_stub.create_checkpoint = AsyncMock(return_value="fake-checkpoint")
    git_stub.rollback_to = AsyncMock()

    build_stub = MagicMock()
    build_stub.run = AsyncMock(
        return_value=BuildResult(success=True, stdout="", stderr="", returncode=0)
    )

    ss_stub = MagicMock()
    ss_stub.compute_ssim = MagicMock(return_value=SSIMResult(score=1.0, mismatch_regions=[]))
    ss_stub.generate_diff_image = MagicMock(return_value=Path("/tmp/diff.png"))

    return RuntimeServices(
        llm=fake_llm,
        filesystem=FilesystemAdapter(),
        git=git_stub,
        sandbox=TempDirSandbox(),
        build_runner=build_stub,
        browser=FakePlaywrightAdapter(),
        screenshot_diff=ss_stub,
    )


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
    image_path = repo_path / "design.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 8)

    def _build_runtime_services_override(_cfg: object) -> RuntimeServices:
        return _runtime_services()

    with patch("ddk.cli._build_runtime_services", _build_runtime_services_override):
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
    assert run_result.exit_code == 0, run_result.stdout
    assert (repo_path / ".ddk" / "cases" / "C-001" / "reports" / "scorecard.json").exists()
    assert (repo_path / ".ddk" / "cases" / "C-001" / "reports" / "evidence-pack.json").exists()

    status_result = runner.invoke(app, ["status", "--repo", str(repo_path), "--json"])
    assert status_result.exit_code == 0, status_result.stdout
    status_payload = json.loads(status_result.stdout)
    assert status_payload["release_decision"] == "ready"
    assert status_payload["case_id"] == "C-001"

    certify_result = runner.invoke(app, ["certify", "--repo", str(repo_path), "--json"])
    assert certify_result.exit_code == 0, certify_result.stdout
    certify_payload = json.loads(certify_result.stdout)
    assert certify_payload["decision"] == "ready"
    assert certify_payload["case_id"] == "C-001"
    assert "evidence_pack" in certify_payload


def test_cli_rollback_delegates_to_checkpoint_ref(tmp_path: Path) -> None:
    class FakeGitAdapter:
        def __init__(self) -> None:
            self.calls: list[tuple[Path, str]] = []

        async def rollback_to(self, repo_path: Path, ref_name: str, *, force: bool = False) -> None:
            self.calls.append((repo_path, ref_name))

    fake_git = FakeGitAdapter()
    with patch("ddk.cli.LocalGitAdapter", new=lambda: fake_git):
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
