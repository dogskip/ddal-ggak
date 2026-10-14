"""`ddk apply` puts the files of a finished case into the repository."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from ddk.cli import app
from ddk.models.generation import GeneratedArtifactSet, GeneratedFile
from ddk.models.input import CaseInput
from ddk.models.release import ReleaseDecision
from ddk.services.case_artifact_store import CaseArtifactStore
from ddk.workspace.manager import WorkspaceManager
from tests.fakes.images import write_png

runner = CliRunner()


def _finished_case(
    repo: Path, *, decision: str = "ready", files: list[GeneratedFile] | None = None
) -> Path:
    repo.mkdir(exist_ok=True)
    manager = WorkspaceManager(repo)
    manager.init()
    case_path = manager.init_case("C-001")
    case_input = CaseInput(
        case_id="C-001",
        image_paths=[write_png(repo / "design.png")],
        prompt="a card",
        repo_path=repo,
    )
    generated = files or [
        GeneratedFile(path="src/Card.tsx", content="card\n", source_node_id="n1", is_new=True)
    ]
    state = {
        "case_id": "C-001",
        "release_decision": ReleaseDecision(case_id="C-001", decision=decision),  # type: ignore[arg-type]
        "generated_artifacts": GeneratedArtifactSet(case_id="C-001", files=generated),
        "fix_attempts": [],
    }
    CaseArtifactStore(case_path).persist(case_input, state)
    return case_path


def _apply(repo: Path, *args: str) -> object:
    return runner.invoke(app, ["apply", "--repo", str(repo), *args])


def test_ready_case_is_written_into_the_repository(tmp_path: Path) -> None:
    _finished_case(tmp_path)

    result = _apply(tmp_path)

    assert result.exit_code == 0, result.output  # type: ignore[attr-defined]
    assert (tmp_path / "src/Card.tsx").read_text() == "card\n"
    assert "src/Card.tsx" in result.output  # type: ignore[attr-defined]


def test_case_that_is_not_ready_is_refused(tmp_path: Path) -> None:
    _finished_case(tmp_path, decision="blocked")

    result = _apply(tmp_path)

    assert result.exit_code == 1  # type: ignore[attr-defined]
    assert "ready" in result.output  # type: ignore[attr-defined]
    assert not (tmp_path / "src/Card.tsx").exists()


def test_blocked_case_cannot_bypass_the_decision(tmp_path: Path) -> None:
    _finished_case(tmp_path, decision="blocked")

    result = _apply(tmp_path, "--allow-blocked")

    assert result.exit_code == 2, result.output  # type: ignore[attr-defined]
    assert not (tmp_path / "src/Card.tsx").exists()


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    _finished_case(tmp_path)

    result = _apply(tmp_path, "--dry-run")

    assert result.exit_code == 0, result.output  # type: ignore[attr-defined]
    assert "src/Card.tsx" in result.output  # type: ignore[attr-defined]
    assert not (tmp_path / "src/Card.tsx").exists()


def test_a_conflict_stops_everything_including_force(tmp_path: Path) -> None:
    files = [
        GeneratedFile(
            path="src/App.tsx", content="new\n", source_node_id="n", original_content="old\n"
        ),
        GeneratedFile(path="src/Card.tsx", content="card\n", source_node_id="n", is_new=True),
    ]
    case_path = _finished_case(tmp_path, files=files)
    (tmp_path / "src").mkdir(exist_ok=True)
    (tmp_path / "src/App.tsx").write_text("my edit\n")

    refused = _apply(tmp_path)

    assert refused.exit_code == 1  # type: ignore[attr-defined]
    assert (tmp_path / "src/App.tsx").read_text() == "my edit\n"
    assert not (tmp_path / "src/Card.tsx").exists()

    forced = _apply(tmp_path, "--force")

    assert forced.exit_code == 2, forced.output  # type: ignore[attr-defined]
    assert (tmp_path / "src/App.tsx").read_text() == "my edit\n"
    assert not (case_path / "artifacts/replaced/src/App.tsx").exists()
    assert not (tmp_path / "src/Card.tsx").exists()


def test_json_output_lists_every_file(tmp_path: Path) -> None:
    _finished_case(tmp_path)

    result = _apply(tmp_path, "--json")

    payload = json.loads(result.stdout)  # type: ignore[attr-defined]
    assert payload["case_id"] == "C-001"
    assert payload["files"] == [{"path": "src/Card.tsx", "action": "create", "reason": ""}]
    assert payload["written"] == ["src/Card.tsx"]


def test_repository_without_a_case_is_an_error(tmp_path: Path) -> None:
    result = _apply(tmp_path)

    assert result.exit_code == 1  # type: ignore[attr-defined]
