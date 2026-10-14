"""Tests for CaseArtifactStore."""

from __future__ import annotations

from pathlib import Path

import pytest

from ddk.models.evidence import EvidencePack
from ddk.models.generation import GeneratedArtifactSet, GeneratedFile
from ddk.models.input import CaseInput
from ddk.models.release import ReleaseDecision
from ddk.models.scorecard import Scorecard
from ddk.services.case_artifact_store import CaseArtifactStore


def test_persist_writes_reports_and_generated_files(tmp_path: Path) -> None:
    case_dir = tmp_path / ".ddk" / "cases" / "C-001"
    image_path = tmp_path / "design.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\n")

    store = CaseArtifactStore(case_dir)
    case_input = CaseInput(
        case_id="C-001",
        image_paths=[image_path],
        prompt="테스트",
        repo_path=tmp_path,
    )
    state = {
        "case_id": "C-001",
        "current_node": "certify",
        "terminal_state": "ready",
        "error_message": None,
        "fix_attempts": [],
        "llm_call_records": [],
        "total_cost_usd": 0.01,
        "generated_artifacts": GeneratedArtifactSet(
            case_id="C-001",
            files=[
                GeneratedFile(
                    path="src/components/Button.tsx",
                    content="export const Button = () => null;",
                    language="typescript",
                    source_node_id="node-btn",
                    is_new=True,
                )
            ],
            file_map={"src/components/Button.tsx": "export const Button = () => null;"},
            generation_trace=["node-btn:src/components/Button.tsx"],
            changed_paths=["src/components/Button.tsx"],
        ),
        "scorecard": Scorecard(
            case_id="C-001",
            precision=1.0,
            maintainability=1.0,
            automation=1.0,
            scalability=1.0,
            overall=1.0,
            grade="A",
        ),
        "release_decision": ReleaseDecision(case_id="C-001", decision="ready"),
        "evidence_pack": EvidencePack(case_id="C-001", terminal_state="ready"),
    }

    store.persist(case_input, state)

    assert (case_dir / "reports" / "status.json").exists()
    assert (case_dir / "reports" / "scorecard.json").exists()
    assert (case_dir / "reports" / "release-decision.json").exists()
    assert (case_dir / "reports" / "evidence-pack.json").exists()
    assert (case_dir / "artifacts" / "generated" / "src/components/Button.tsx").exists()
    assert (case_dir / "artifacts" / "inputs" / "design.png").exists()


def test_loaders_roundtrip_persisted_certification_models(tmp_path: Path) -> None:
    case_dir = tmp_path / ".ddk" / "cases" / "C-001"
    case_dir.mkdir(parents=True)
    reports_dir = case_dir / "reports"
    reports_dir.mkdir()
    scorecard = Scorecard(
        case_id="C-001",
        precision=1.0,
        maintainability=1.0,
        automation=1.0,
        scalability=1.0,
        overall=1.0,
        grade="A",
    )
    decision = ReleaseDecision(case_id="C-001", decision="ready")
    evidence = EvidencePack(case_id="C-001", terminal_state="ready")
    (reports_dir / "scorecard.json").write_text(scorecard.model_dump_json(), encoding="utf-8")
    (reports_dir / "release-decision.json").write_text(
        decision.model_dump_json(),
        encoding="utf-8",
    )
    (reports_dir / "evidence-pack.json").write_text(
        evidence.model_dump_json(),
        encoding="utf-8",
    )
    (reports_dir / "status.json").write_text(
        '{"case_id":"C-001","release_decision":"ready","terminal_state":"ready"}',
        encoding="utf-8",
    )

    store = CaseArtifactStore(case_dir)

    assert store.load_status()["case_id"] == "C-001"
    assert store.load_scorecard().grade == "A"
    assert store.load_release_decision().decision == "ready"
    assert store.load_evidence_pack().terminal_state == "ready"


def test_generated_file_persistence_rejects_path_escape_after_validation_bypass(
    tmp_path: Path,
) -> None:
    store = CaseArtifactStore(tmp_path / "case")
    unsafe_file = GeneratedFile.model_construct(
        path="../../../escaped.ts",
        content="export const escaped = true;",
        source_node_id="unsafe",
    )
    artifacts = GeneratedArtifactSet.model_construct(case_id="C-unsafe", files=[unsafe_file])

    with pytest.raises(ValueError, match="unsafe repository-relative path"):
        store._persist_generated_files({"generated_artifacts": artifacts})

    assert not (tmp_path / "escaped.ts").exists()


def test_persist_writes_the_llm_call_log(tmp_path: Path) -> None:
    case_dir = tmp_path / ".ddk" / "cases" / "C-002"
    image_path = tmp_path / "design.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\n")
    case_input = CaseInput(
        case_id="C-002", image_paths=[image_path], prompt="x", repo_path=tmp_path
    )
    calls = [{"sequence": 1, "purpose": "autofix", "cost_usd": 0.01}]

    store = CaseArtifactStore(case_dir)
    store.persist(case_input, {"case_id": "C-002", "fix_attempts": [], "llm_calls": calls})

    import json  # noqa: PLC0415

    saved = json.loads((case_dir / "reports" / "llm-calls.json").read_text(encoding="utf-8"))
    assert saved == calls
