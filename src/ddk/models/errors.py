from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import Field

from ._base import DDKBaseModel


class ErrorCategory(StrEnum):
    LLM = "llm"
    BUILD = "build"
    TYPE_CHECK = "type_check"
    LINT = "lint"
    RUNTIME = "runtime"
    VISUAL = "visual"
    DATA_BINDING = "data_binding"
    ASYNC_TIMING = "async_timing"
    UNKNOWN = "unknown"


class ErrorSeverity(StrEnum):
    CRITICAL = "critical"
    BLOCKER = "blocker"
    MAJOR = "major"
    MINOR = "minor"
    INFO = "info"


class DDKError(DDKBaseModel):
    code: str
    category: ErrorCategory
    severity: ErrorSeverity
    message: str
    node: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    recoverable: bool = True


class ErrorChain(DDKBaseModel):
    case_id: str
    errors: list[DDKError] = Field(default_factory=list)
    terminal_state: str | None = None

    @property
    def has_critical(self) -> bool:
        return any(e.severity == ErrorSeverity.CRITICAL for e in self.errors)

    @property
    def has_blocker(self) -> bool:
        return any(e.severity == ErrorSeverity.BLOCKER for e in self.errors)
