"""EvidencePack construction for Phase 5 certification."""

from __future__ import annotations

from typing import Any, cast

from ddk.models.evidence import EvidencePack
from ddk.models.fix import FixAttempt
from ddk.models.normalization import NormalizationReport
from ddk.models.release import ReleaseDecision
from ddk.models.scorecard import Scorecard
from ddk.models.validation import RuntimeValidationReport


class EvidencePackBuilder:
    """Bundle pipeline outputs into a replayable evidence reference pack."""

    def build(
        self,
        state: dict[str, Any],
        scorecard: Scorecard,
        release_decision: ReleaseDecision,
    ) -> EvidencePack:
        """Build an EvidencePack from graph state and certification outputs."""
        case_id = str(state["case_id"])
        fix_attempts = cast(list[FixAttempt], state.get("fix_attempts", []))
        llm_refs = cast(list[str], state.get("llm_call_records", []))

        return EvidencePack(
            case_id=case_id,
            input_ref=self._ref("case-input", state.get("case_input"), case_id),
            repo_profile_ref=self._ref("repo-profile", state.get("repo_profile"), case_id),
            intent_graph_ref=self._ref("intent-graph", state.get("intent_graph"), case_id),
            generation_plan_ref=self._ref(
                "generation-plan",
                state.get("generation_plan"),
                case_id,
            ),
            artifact_set_ref=self._ref("artifact-set", state.get("generated_artifacts"), case_id),
            normalization_ref=self._ref(
                "normalization-report",
                state.get("normalization_report"),
                case_id,
            ),
            runtime_validation_ref=self._ref(
                "runtime-validation",
                state.get("runtime_validation_report"),
                case_id,
            ),
            visual_regression_ref=self._ref(
                "visual-regression",
                state.get("visual_regression_report"),
                case_id,
            ),
            fix_attempt_refs=[
                f"fix-attempt:{case_id}:{attempt.attempt_number}" for attempt in fix_attempts
            ],
            scorecard_ref=f"scorecard:{case_id}",
            release_decision_ref=f"release-decision:{case_id}",
            llm_call_record_refs=list(llm_refs),
            total_cost_usd=float(state.get("total_cost_usd", 0.0)),
            pipeline_duration_ms=self._duration_ms(state, fix_attempts),
            terminal_state=release_decision.decision,
        )

    def _duration_ms(
        self,
        state: dict[str, Any],
        fix_attempts: list[FixAttempt],
    ) -> int:
        runtime = cast(RuntimeValidationReport | None, state.get("runtime_validation_report"))
        normalization = cast(NormalizationReport | None, state.get("normalization_report"))

        total = 0
        if runtime is not None:
            total += runtime.duration_ms
        if normalization is not None:
            total += normalization.duration_ms
        total += sum(attempt.duration_ms for attempt in fix_attempts)
        return total

    def _ref(self, prefix: str, value: object | None, case_id: str) -> str | None:
        if value is None:
            return None
        return f"{prefix}:{case_id}"
