from __future__ import annotations

from typing import Literal

from pydantic import Field

from ._base import DDKBaseModel


class ConventionFix(DDKBaseModel):
    file_path: str
    rule_id: str
    description: str
    before_snippet: str
    after_snippet: str
    # Design-spec fields (12-data-models.md §5) — additive, defaults provided
    fix_type: Literal[
        "naming", "import_order", "file_placement", "token_replace",
        "primitive_reuse", "helper_dedup", "type_annotation"
    ] = "naming"
    severity: Literal["must-fix", "should-fix", "nice-to-have"] = "must-fix"
    before: str | None = None
    after: str | None = None


class NormalizationReport(DDKBaseModel):
    case_id: str
    fixes: list[ConventionFix] = []
    files_modified: list[str] = []
    skipped_rules: list[str] = []
    duration_ms: int = Field(default=0, ge=0)
    # Design-spec fields (12-data-models.md §5) — additive, defaults provided
    convention_fixes: list[ConventionFix] = Field(default_factory=list)
    drift_score_before: float = Field(default=0.0, ge=0.0, le=10.0)
    drift_score_after: float = Field(default=0.0, ge=0.0, le=10.0)
    unresolved_drift: list[str] = Field(default_factory=list)

    @staticmethod
    def compute_drift_score(fixes: list[ConventionFix]) -> float:
        """Compute drift score from fixes. must-fix=2.0, should-fix=1.0, nice-to-have=0.5. Cap=10.0."""
        WEIGHTS = {"must-fix": 2.0, "should-fix": 1.0, "nice-to-have": 0.5}
        raw = sum(WEIGHTS.get(f.severity, 1.0) for f in fixes)
        return float(min(raw, 10.0))
