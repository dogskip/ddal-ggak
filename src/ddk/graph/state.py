"""GraphState TypedDict and initial_state factory — INFRA-04."""

from __future__ import annotations

from typing import TypedDict

from ddk.models.evidence import EvidencePack
from ddk.models.fix import FixAttempt
from ddk.models.generation import GeneratedArtifactSet, GenerationPlan
from ddk.models.input import CaseInput
from ddk.models.intent import IntentGraph
from ddk.models.normalization import NormalizationReport
from ddk.models.release import ReleaseDecision
from ddk.models.repo import RepoProfile
from ddk.models.scorecard import Scorecard
from ddk.models.validation import RuntimeValidationReport
from ddk.models.visual import VisualRegressionReport


class GraphState(TypedDict):
    """Immutable-by-convention state passed between LangGraph nodes.

    All optional fields start as None. List fields start empty.
    Nodes must return a *new* dict (never mutate in place).
    """

    case_id: str
    case_input: CaseInput | None
    repo_profile: RepoProfile | None
    intent_graph: IntentGraph | None
    generation_plan: GenerationPlan | None
    generated_artifacts: GeneratedArtifactSet | None
    normalization_report: NormalizationReport | None
    runtime_validation_report: RuntimeValidationReport | None
    visual_regression_report: VisualRegressionReport | None
    fix_attempts: list[FixAttempt]
    scorecard: Scorecard | None
    release_decision: ReleaseDecision | None
    evidence_pack: EvidencePack | None
    # Budget / control flow
    retry_budget_remaining: int
    current_node: str
    terminal_state: str | None
    error_message: str | None
    pre_run_checkpoint_ref: str | None
    failure_hash_history: list[int]  # oscillation detection — appended by autofix_node
    # Cost tracking
    llm_call_records: list[str]
    total_cost_usd: float
    reproducibility_seed: int | None


def initial_state(case_input: CaseInput, *, retry_budget: int = 3) -> GraphState:
    """Return a complete GraphState with all None/empty defaults.

    Args:
        case_input: Validated user input for this pipeline run.
        retry_budget: How many auto-fix attempts the run may use.

    Returns:
        GraphState dict ready for LangGraph invocation.
    """
    return GraphState(
        case_id=case_input.case_id,
        case_input=case_input,
        repo_profile=None,
        intent_graph=None,
        generation_plan=None,
        generated_artifacts=None,
        normalization_report=None,
        runtime_validation_report=None,
        visual_regression_report=None,
        fix_attempts=[],
        scorecard=None,
        release_decision=None,
        evidence_pack=None,
        retry_budget_remaining=retry_budget,
        current_node="start",
        terminal_state=None,
        error_message=None,
        pre_run_checkpoint_ref=None,
        failure_hash_history=[],
        llm_call_records=[],
        total_cost_usd=0.0,
        reproducibility_seed=None,
    )
