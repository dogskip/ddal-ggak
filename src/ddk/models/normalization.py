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
    fixes: list[ConventionFix] = Field(default_factory=list)
    files_modified: list[str] = Field(default_factory=list)
    skipped_rules: list[str] = Field(default_factory=list)
    duration_ms: int = Field(default=0, ge=0)
