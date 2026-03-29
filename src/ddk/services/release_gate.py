"""Release decision gate for Phase 5 certification."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal, cast

from ddk.models.release import BlockerItem, ReleaseDecision
from ddk.models.scorecard import Scorecard
from ddk.models.validation import FailureRecord, RuntimeValidationReport
from ddk.models.visual import VisualRegressionReport


class ReleaseGate:
    """Turn validation evidence into a final release decision."""

    Decision = Literal["ready", "blocked", "manual-review"]
    BlockerSeverity = Literal["critical", "blocker", "major"]

    def decide(self, state: dict[str, Any], scorecard: Scorecard) -> ReleaseDecision:
        """Produce a ready / blocked / manual-review decision."""
        case_id = str(state["case_id"])
        runtime = cast(RuntimeValidationReport | None, state.get("runtime_validation_report"))
        visual = cast(VisualRegressionReport | None, state.get("visual_regression_report"))
        blockers = self._collect_blockers(case_id, runtime, visual)

        decision = self._decision_for(state, scorecard, blockers)
        summary = self._summary_for(decision, blockers, scorecard)
        approved_at = datetime.now(UTC) if decision == "ready" else None

        return ReleaseDecision(
            case_id=case_id,
            decision=decision,
            scorecard_ref=f"scorecard:{case_id}",
            blockers=blockers,
            summary=summary,
            approved_at=approved_at,
        )

    def _collect_blockers(
        self,
        case_id: str,
        runtime: RuntimeValidationReport | None,
        visual: VisualRegressionReport | None,
    ) -> list[BlockerItem]:
        blockers: list[BlockerItem] = []

        if runtime is None:
            blockers.append(
                BlockerItem(
                    id="missing-runtime-evidence",
                    category="evidence",
                    description="No runtime validation evidence provided",
                    severity="critical",
                )
            )
        if runtime is not None:
            for failure in runtime.failures:
                blockers.append(
                    BlockerItem(
                        id=failure.id,
                        category=self._category_for_failure(failure),
                        description=failure.message,
                        severity=self._blocker_severity(failure),
                    )
                )

        if visual is not None and not visual.pass_result:
            blockers.append(
                BlockerItem(
                    id=f"{case_id}-visual",
                    category="visual",
                    description=(
                        f"Visual regression below threshold "
                        f"({visual.ssim_score:.2f} < {visual.threshold:.2f})"
                    ),
                    severity="blocker",
                )
            )

        return blockers

    def _decision_for(
        self,
        state: dict[str, Any],
        scorecard: Scorecard,
        blockers: list[BlockerItem],
    ) -> Decision:
        if any(blocker.severity in {"critical", "blocker"} for blocker in blockers):
            return "blocked"

        if state.get("terminal_state") == "manual-review-required":
            return "manual-review"

        if scorecard.overall >= 0.85:
            return "ready"

        return "manual-review"

    def _summary_for(
        self,
        decision: Decision,
        blockers: list[BlockerItem],
        scorecard: Scorecard,
    ) -> str:
        if decision == "ready":
            return f"Release ready with overall score {scorecard.overall:.2f} ({scorecard.grade})."
        if decision == "blocked":
            return f"Release blocked by {len(blockers)} blocker(s)."
        return f"Manual review required with overall score {scorecard.overall:.2f}."

    def _category_for_failure(self, failure: FailureRecord) -> str:
        taxonomy = failure.taxonomy_id.lower()
        if taxonomy.startswith("ft-build"):
            return "build"
        if taxonomy.startswith("ft-type"):
            return "type-check"
        if taxonomy.startswith("ft-lint"):
            return "lint"
        if taxonomy.startswith("ft-runtime"):
            return "runtime"
        if taxonomy.startswith("ft-visual"):
            return "visual"
        return "validation"

    def _blocker_severity(self, failure: FailureRecord) -> BlockerSeverity:
        if failure.severity == "critical":
            return "critical"
        if failure.severity == "major":
            return "blocker"
        return "major"
