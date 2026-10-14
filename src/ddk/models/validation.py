from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import Field

from ._base import DDKBaseModel

FAILURE_TAXONOMY: dict[str, str] = {
    "FT-BUILD-001": "Module resolution failure",
    "FT-BUILD-002": "Syntax error in generated code",
    "FT-BUILD-003": "Missing dependency",
    "FT-TYPE-001": "Type mismatch",
    "FT-TYPE-002": "Missing type annotation",
    "FT-TYPE-003": "Incompatible type assignment",
    "FT-LINT-001": "Unused import",
    "FT-LINT-002": "Style violation",
    "FT-LINT-003": "Naming convention violation",
    "FT-RUNTIME-001": "Unhandled exception",
    "FT-RUNTIME-002": "Null reference error",
    "FT-RUNTIME-003": "API call failure",
    "FT-VISUAL-001": "Layout shift detected",
    "FT-VISUAL-002": "Color mismatch",
    "FT-VISUAL-003": "Missing element",
    "FT-DATA-001": "Data binding failure",
    "FT-DATA-002": "Missing prop",
    "FT-ASYNC-001": "Race condition",
    "FT-ASYNC-002": "Unresolved promise",
}


FailureSource = Literal["build", "typecheck", "lint", "runtime", "visual"]
StepName = Literal["install", "build", "typecheck", "lint", "visual"]
StepStatus = Literal["passed", "failed", "skipped", "unavailable"]


class FailureRecord(DDKBaseModel):
    id: str
    taxonomy_id: str
    severity: Literal["critical", "major", "minor"]
    message: str
    file_path: str | None = None
    line_number: int | None = None
    raw_output: str = ""
    suggested_fix: str | None = None
    source: FailureSource | None = None
    code: str | None = None


class ValidationStep(DDKBaseModel):
    """One command the validator ran (or chose not to), and what came of it."""

    name: StepName
    command: list[str] = []
    status: StepStatus
    returncode: int | None = None
    duration_ms: int = Field(default=0, ge=0)
    summary: str = ""
    error_count: int = Field(default=0, ge=0)
    warning_count: int = Field(default=0, ge=0)


class RuntimeValidationReport(DDKBaseModel):
    case_id: str
    build_success: bool
    type_check_success: bool
    lint_success: bool
    runtime_errors: list[str] = []
    failures: list[FailureRecord] = []
    steps: list[ValidationStep] = []
    duration_ms: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def environment_issues(self) -> list[str]:
        """Steps that could not run because the toolchain is missing (not a code problem)."""
        return [
            f"{step.name}: {step.summary}" for step in self.steps if step.status == "unavailable"
        ]

    @property
    def verified_anything(self) -> bool:
        """Whether at least one step actually ran to a pass or a fail."""
        return any(step.status in {"passed", "failed"} for step in self.steps)
