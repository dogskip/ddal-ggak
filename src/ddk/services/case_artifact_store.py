"""Persistence helpers for `.ddk/cases/<case_id>` artifacts and reports."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, cast

from ddk.models.evidence import EvidencePack
from ddk.models.generation import GeneratedArtifactSet
from ddk.models.input import CaseInput
from ddk.models.release import ReleaseDecision
from ddk.models.scorecard import Scorecard
from ddk.security.repo_paths import resolve_within_repository


class CaseArtifactStore:
    """Write and read case artifacts produced by the delivery pipeline."""

    def __init__(self, case_dir: Path) -> None:
        self.case_dir = case_dir
        self.reports_dir = case_dir / "reports"
        self.artifacts_dir = case_dir / "artifacts"

    def persist(self, case_input: CaseInput, state: dict[str, Any]) -> None:
        """Persist primary models, summaries, and generated files for a completed run."""
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

        self._write_model("case-input.json", case_input)
        for field_name, file_name in (
            ("repo_profile", "repo-profile.json"),
            ("intent_graph", "intent-graph.json"),
            ("generation_plan", "generation-plan.json"),
            ("generated_artifacts", "generated-artifacts.json"),
            ("normalization_report", "normalization-report.json"),
            ("runtime_validation_report", "runtime-validation-report.json"),
            ("visual_regression_report", "visual-regression-report.json"),
            ("scorecard", "scorecard.json"),
            ("release_decision", "release-decision.json"),
            ("evidence_pack", "evidence-pack.json"),
        ):
            value = state.get(field_name)
            if value is not None:
                self._write_model(file_name, value)

        self._write_json(
            "fix-attempts.json",
            [attempt.model_dump(mode="json") for attempt in state.get("fix_attempts", [])],
        )
        self._write_json("llm-call-records.json", list(state.get("llm_call_records", [])))
        if "llm_calls" in state:
            self._write_json("llm-calls.json", list(state["llm_calls"]))
        self._write_json("status.json", self.build_status_summary(state))
        self._persist_input_images(case_input)
        self._persist_generated_files(state)

    def build_status_summary(self, state: dict[str, Any]) -> dict[str, Any]:
        """Build a compact status summary for CLI presentation."""
        decision = state.get("release_decision")
        scorecard = state.get("scorecard")
        evidence = state.get("evidence_pack")
        return {
            "case_id": str(state.get("case_id")),
            "current_node": state.get("current_node"),
            "terminal_state": state.get("terminal_state"),
            "error_message": state.get("error_message"),
            "release_decision": decision.decision if decision is not None else None,
            "scorecard_grade": scorecard.grade if scorecard is not None else None,
            "scorecard_overall": scorecard.overall if scorecard is not None else None,
            "total_cost_usd": state.get("total_cost_usd", 0.0),
            "fix_attempts": len(state.get("fix_attempts", [])),
            "evidence_pack_terminal_state": (
                evidence.terminal_state if evidence is not None else None
            ),
        }

    def load_status(self) -> dict[str, Any]:
        """Load the saved status summary for a case."""
        return cast(
            dict[str, Any],
            json.loads((self.reports_dir / "status.json").read_text(encoding="utf-8")),
        )

    def load_scorecard(self) -> Scorecard:
        """Load the persisted scorecard for a case."""
        return Scorecard.model_validate_json(
            (self.reports_dir / "scorecard.json").read_text(encoding="utf-8")
        )

    def load_release_decision(self) -> ReleaseDecision:
        """Load the persisted release decision for a case."""
        return ReleaseDecision.model_validate_json(
            (self.reports_dir / "release-decision.json").read_text(encoding="utf-8")
        )

    def load_generated_artifacts(self) -> GeneratedArtifactSet:
        """Load the generated files of a case."""
        return GeneratedArtifactSet.model_validate_json(
            (self.reports_dir / "generated-artifacts.json").read_text(encoding="utf-8")
        )

    def load_evidence_pack(self) -> EvidencePack:
        """Load the persisted evidence pack for a case."""
        return EvidencePack.model_validate_json(
            (self.reports_dir / "evidence-pack.json").read_text(encoding="utf-8")
        )

    def _persist_input_images(self, case_input: CaseInput) -> None:
        inputs_dir = self.artifacts_dir / "inputs"
        inputs_dir.mkdir(parents=True, exist_ok=True)
        for image_path in case_input.image_paths:
            shutil.copy2(image_path, inputs_dir / image_path.name)

    def _persist_generated_files(self, state: dict[str, Any]) -> None:
        generated_artifacts = state.get("generated_artifacts")
        if generated_artifacts is None:
            return

        generated_dir = self.artifacts_dir / "generated"
        for generated_file in generated_artifacts.files:
            output_path = resolve_within_repository(generated_dir, generated_file.path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(generated_file.content, encoding="utf-8")

    def _write_model(self, file_name: str, model: Any) -> None:
        report_path = self.reports_dir / file_name
        report_path.write_text(model.model_dump_json(indent=2), encoding="utf-8")

    def _write_json(self, file_name: str, payload: Any) -> None:
        report_path = self.reports_dir / file_name
        report_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
