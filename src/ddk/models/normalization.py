from __future__ import annotations

from pydantic import Field

from ._base import DDKBaseModel


class ConventionFix(DDKBaseModel):
    file_path: str
    rule_id: str
    description: str
    before_snippet: str
    after_snippet: str


class NormalizationReport(DDKBaseModel):
    case_id: str
    fixes: list[ConventionFix] = []
    files_modified: list[str] = []
    skipped_rules: list[str] = []
    duration_ms: int = Field(default=0, ge=0)
