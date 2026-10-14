# Pydantic 모델 완전 스키마 정의

> 이 문서는 딸깍의 모든 Pydantic v2 모델의 완전한 타입 정의를 포함한다.
> 이 파일이 없으면 contract test를 작성할 수 없다.

---

## 공통 타입

```python
# src/ddk/models/_base.py
from __future__ import annotations
from pydantic import BaseModel, ConfigDict

class DDKBaseModel(BaseModel):
    model_config = ConfigDict(
        frozen=False,
        validate_assignment=True,
        populate_by_name=True,
        extra="forbid",         # 미정의 필드 차단 (schema drift 조기 발견)
    )
```

---

## 1. CaseInput

```python
# src/ddk/models/input.py
from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
from pydantic import Field, field_validator
from ._base import DDKBaseModel


class CaseInput(DDKBaseModel):
    case_id: str                           # "C-001" 형식
    image_paths: list[Path]                # 최소 1개, 최대 5개
    prompt: str                            # 생성 지시 (1~2000자)
    repo_path: Path                        # 대상 repo 루트
    reference_notes: str | None = None     # 추가 컨텍스트
    visual_reference_paths: list[Path] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("image_paths")
    @classmethod
    def validate_image_count(cls, v: list[Path]) -> list[Path]:
        if not v:
            raise ValueError("image_paths는 최소 1개 이상이어야 합니다")
        if len(v) > 5:
            raise ValueError("image_paths는 최대 5개까지 허용됩니다")
        return v

    @field_validator("prompt")
    @classmethod
    def validate_prompt_length(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("prompt는 비어 있을 수 없습니다")
        if len(v) > 2000:
            raise ValueError("prompt는 2000자를 초과할 수 없습니다")
        return v
```

---

## 2. RepoProfile

```python
# src/ddk/models/repo.py
from __future__ import annotations
from typing import Literal
from pydantic import Field
from ._base import DDKBaseModel


class NamingRules(DDKBaseModel):
    component_pattern: Literal["PascalCase", "kebab-case"] = "PascalCase"
    file_pattern: Literal["PascalCase", "kebab-case", "camelCase"] = "kebab-case"
    hook_prefix: str = "use"
    test_suffix: str = ".test"
    story_suffix: str = ".stories"
    style_suffix: str = ".module.css"


class FileLayoutRules(DDKBaseModel):
    components_dir: str = "src/components"
    pages_dir: str = "src/pages"
    hooks_dir: str = "src/hooks"
    utils_dir: str = "src/utils"
    types_dir: str = "src/types"
    styles_dir: str = "src/styles"
    test_co_location: bool = True  # 컴포넌트 옆에 테스트 파일


class DesignTokens(DDKBaseModel):
    colors: dict[str, str] = Field(default_factory=dict)
    # {"primary": "#3B82F6", "secondary": "#6B7280", ...}
    spacing: dict[str, str] = Field(default_factory=dict)
    # {"xs": "0.25rem", "sm": "0.5rem", "md": "1rem", ...}
    typography: dict[str, dict] = Field(default_factory=dict)
    # {"heading1": {"size": "2rem", "weight": "700"}, ...}
    breakpoints: dict[str, str] = Field(default_factory=dict)
    # {"sm": "640px", "md": "768px", "lg": "1024px", ...}
    border_radius: dict[str, str] = Field(default_factory=dict)


class RepoProfile(DDKBaseModel):
    framework: Literal["react", "vue", "svelte", "next", "nuxt", "angular", "other"]
    language: Literal["typescript", "javascript"] = "typescript"
    package_manager: Literal["npm", "yarn", "pnpm", "bun"] = "pnpm"
    css_approach: Literal[
        "tailwind", "css-modules", "styled-components", "emotion", "scss", "other"
    ] = "tailwind"
    component_library: str | None = None
    # "shadcn/ui", "radix-ui", "mui", "antd", "chakra", "mantine" 등
    test_runner: str | None = None  # "vitest", "jest"
    build_tool: str = "vite"
    node_version: str | None = None  # "20", "22" 등
    naming_rules: NamingRules = Field(default_factory=NamingRules)
    file_layout: FileLayoutRules = Field(default_factory=FileLayoutRules)
    design_tokens: DesignTokens = Field(default_factory=DesignTokens)
    existing_components: list[str] = Field(default_factory=list)
    # 재사용 가능 컴포넌트 경로 목록
```

---

## 3. IntentGraph

```python
# src/ddk/models/intent.py
from __future__ import annotations
from typing import Literal, Any
from datetime import datetime, timezone
from pydantic import Field
from ._base import DDKBaseModel


class BoundingBox(DDKBaseModel):
    """이미지 내 상대 좌표 (0.0~1.0)"""
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    width: float = Field(gt=0.0, le=1.0)
    height: float = Field(gt=0.0, le=1.0)


class LayoutRegion(DDKBaseModel):
    id: str                            # "region-header", "region-main" 등
    region_type: Literal[
        "header", "nav", "sidebar", "main", "footer",
        "modal", "card", "form", "table", "hero", "cta", "list", "other"
    ]
    bounds: BoundingBox
    children: list[str] = Field(default_factory=list)  # child region IDs
    semantic_label: str | None = None   # "사용자 프로필", "검색 결과" 등


class PropValue(DDKBaseModel):
    """컴포넌트 prop 값 — 리터럴 또는 dynamic"""
    value: str | int | bool | None = None
    is_dynamic: bool = False            # True면 prop이 실제 데이터에서 옴


class ComponentSpec(DDKBaseModel):
    id: str                            # "comp-001", "comp-login-btn" 등
    component_type: str                # "Button", "Input", "Card", "Table" 등
    props: dict[str, PropValue] = Field(default_factory=dict)
    children: list["ComponentSpec"] = Field(default_factory=list)
    region_id: str | None = None       # 속한 LayoutRegion ID
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    notes: str | None = None           # 추가 추론 메모


class InteractionSpec(DDKBaseModel):
    id: str                            # "int-001"
    trigger: Literal["click", "hover", "focus", "submit", "change", "keydown", "scroll"]
    source_component_id: str
    action: Literal[
        "navigate", "open-modal", "close-modal", "submit-form",
        "toggle", "filter", "sort", "load-more", "other"
    ]
    target: str | None = None          # 이동 경로 또는 모달 ID
    params: dict[str, Any] = Field(default_factory=dict)


class IntentGraph(DDKBaseModel):
    id: str                            # case_id와 동일
    schema_version: str = "1.0"
    source_image_hash: str             # SHA256 hex[:16]
    layout_regions: list[LayoutRegion]
    components: list[ComponentSpec]
    interactions: list[InteractionSpec]
    confidence: float = Field(ge=0.0, le=1.0)
    # 전체 추출 신뢰도 (0.0 = 완전 불확실, 1.0 = 확실)
    unresolved_items: list[str] = Field(default_factory=list)
    # 추출 실패 항목 설명 문자열
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

---

## 4. GenerationPlan

```python
# src/ddk/models/generation.py
from __future__ import annotations
from typing import Literal
from datetime import datetime, timezone
from pydantic import Field
from ._base import DDKBaseModel


class GenerationNode(DDKBaseModel):
    id: str                            # "node-app-tsx", "node-button-component"
    node_type: Literal["file", "component", "hook", "style", "test", "route", "type"]
    target_path: str                   # 생성 대상 경로 (repo_path 기준 상대)
    dependencies: list[str] = Field(default_factory=list)  # 선행 node IDs
    validation_hooks: list[str] = Field(default_factory=list)
    repair_hooks: list[str] = Field(default_factory=list)
    generation_prompt_hint: str | None = None


class GenerationPlan(DDKBaseModel):
    case_id: str
    nodes: list[GenerationNode]
    execution_order: list[str]         # topological sort된 node ID 목록
    target_files: list[str]            # 생성/수정될 파일 경로 목록
    validation_hooks: list[str]        # 전체 플랜 완료 후 실행할 validation
    estimated_node_count: int
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class GeneratedFile(DDKBaseModel):
    path: str                          # repo_path 기준 상대 경로
    content: str                       # 생성된 파일 내용
    is_new: bool                       # True = 새 파일, False = 기존 파일 수정
    original_content: str | None = None


class GeneratedArtifactSet(DDKBaseModel):
    case_id: str
    schema_version: str = "1.0"
    files: list[GeneratedFile]
    changed_paths: list[str]
    trace: dict = Field(default_factory=dict)
    # {"model": "...", "total_tokens": 1234, ...}
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

---

## 5. NormalizationReport

```python
# src/ddk/models/normalization.py
from __future__ import annotations
from typing import Literal
from pydantic import Field
from ._base import DDKBaseModel


class ConventionFix(DDKBaseModel):
    fix_type: Literal[
        "naming", "import_order", "file_placement", "token_replace",
        "primitive_reuse", "helper_dedup", "type_annotation"
    ]
    file_path: str
    description: str
    before: str | None = None
    after: str | None = None
    severity: Literal["must-fix", "should-fix", "nice-to-have"] = "must-fix"


class NormalizationReport(DDKBaseModel):
    case_id: str
    convention_fixes: list[ConventionFix]
    unresolved_drift: list[str] = Field(default_factory=list)
    drift_score_before: float = Field(ge=0.0, le=10.0)
    # 10 = 완전히 다름, 0 = 완전히 일치
    drift_score_after: float = Field(ge=0.0, le=10.0)

    @staticmethod
    def compute_drift_score(fixes: list[ConventionFix]) -> float:
        """
        drift_score 계산 공식.

        각 ConventionFix의 severity에 따라 가중치를 부여해 합산하고,
        cap(10.0)을 적용한다.

        가중치:
            must-fix       → 2.0
            should-fix     → 1.0
            nice-to-have   → 0.5

        예시:
            3 must-fix + 2 should-fix + 1 nice-to-have
            = 3×2.0 + 2×1.0 + 1×0.5 = 8.5

        사용처:
            drift_score_before  = 생성 직후 전체 fixes 기준
            drift_score_after   = normalizer 통과 후 unresolved fixes 기준
        """
        WEIGHTS = {"must-fix": 2.0, "should-fix": 1.0, "nice-to-have": 0.5}
        raw = sum(WEIGHTS.get(f.severity, 1.0) for f in fixes)
        return min(raw, 10.0)
```

---

## 6. RuntimeValidationReport

```python
# src/ddk/models/validation.py
from __future__ import annotations
from typing import Literal
from datetime import datetime, timezone
from pydantic import Field
from ._base import DDKBaseModel


FAILURE_TAXONOMY: dict[str, str] = {
    # BUILD
    "BUILD-001": "TypeScript compilation error",
    "BUILD-002": "Missing module / import not found",
    "BUILD-003": "Syntax error",
    "BUILD-004": "Asset not found",
    # TYPE
    "TYPE-001": "Type mismatch",
    "TYPE-002": "Missing required prop",
    "TYPE-003": "Undefined variable",
    "TYPE-004": "Interface incompatibility",
    # LINT
    "LINT-001": "Unused import",
    "LINT-002": "Naming convention violation",
    "LINT-003": "Accessibility violation (a11y)",
    # RUNTIME
    "RUNTIME-001": "Uncaught TypeError",
    "RUNTIME-002": "Network request failed",
    "RUNTIME-003": "React rendering error",
    "RUNTIME-004": "App boot timeout",
    # VISUAL
    "VISUAL-001": "Layout structure mismatch",
    "VISUAL-002": "Critical region missing",
    "VISUAL-003": "Color/typography drift",
}


class FailureRecord(DDKBaseModel):
    taxonomy_id: str                    # "BUILD-001" 등
    severity: Literal["critical", "error", "warning"]
    message: str
    file_path: str | None = None
    line_number: int | None = None
    column_number: int | None = None
    raw_output: str | None = None


class RuntimeValidationReport(DDKBaseModel):
    case_id: str
    sandbox_id: str
    build_status: Literal["pass", "fail", "skip"]
    type_status: Literal["pass", "fail", "skip"]
    lint_status: Literal["pass", "fail", "skip"]
    runtime_status: Literal["pass", "fail", "skip"]
    console_errors: list[FailureRecord] = Field(default_factory=list)
    all_failures: list[FailureRecord] = Field(default_factory=list)
    overall_status: Literal["pass", "fail"]
    duration_seconds: float = 0.0
    sandbox_metadata: dict = Field(default_factory=dict)
    executed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

---

## 7. VisualRegressionReport

```python
# src/ddk/models/visual.py
from __future__ import annotations
from typing import Literal
from datetime import datetime, timezone
from pydantic import Field
from ._base import DDKBaseModel


class MismatchRegion(DDKBaseModel):
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    width: float = Field(gt=0.0, le=1.0)
    height: float = Field(gt=0.0, le=1.0)
    severity: Literal["critical", "major", "minor"]
    region_label: str | None = None    # 해당 영역의 semantic label


class VisualRegressionReport(DDKBaseModel):
    case_id: str
    schema_version: str = "1.0"
    reference_image_path: str
    generated_image_path: str
    diff_image_path: str | None = None
    ssim: float = Field(ge=0.0, le=1.0)
    changed_pixel_ratio: float = Field(ge=0.0, le=1.0)
    mismatch_regions: list[MismatchRegion] = Field(default_factory=list)
    critical_region_overlap: float = Field(ge=0.0, le=1.0)
    missing_critical_regions: int = Field(ge=0)
    overall_status: Literal["pass", "fail"]
    # 통과 기준: ssim >= 0.92, pixel_ratio <= 0.05,
    #           critical_overlap >= 0.90, missing_critical == 0
    viewport: str = "1280x800"
    executed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

---

## 8. FixAttempt

```python
# src/ddk/models/fix.py
from __future__ import annotations
from typing import Literal
from datetime import datetime, timezone
from pydantic import Field
from ._base import DDKBaseModel


class FixAttempt(DDKBaseModel):
    attempt_no: int = Field(ge=1)       # 1-based
    hypothesis: str                     # "BUILD-001, TYPE-002 해결 시도: import 경로 수정"
    failure_ids: list[str]              # 이번 시도에서 공략하는 taxonomy ID 목록
    changed_files: list[str]
    validation_delta: dict = Field(default_factory=dict)
    # {"before": {"build": "fail"}, "after": {"build": "pass"}}
    checkpoint_ref: str                 # git ref (체크포인트 커밋 hash)
    result: Literal["improved", "no_change", "regression", "pass"]
    context_pack_hash: str              # 이번 시도의 컨텍스트 해시 (재현용)
    llm_call_ref: str | None = None     # LLMCallRecord artifact ref
    executed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

---

## 9. Scorecard

```python
# src/ddk/models/scorecard.py
from __future__ import annotations
from datetime import datetime, timezone
from pydantic import Field
from ._base import DDKBaseModel


class Scorecard(DDKBaseModel):
    case_id: str
    schema_version: str = "1.0"
    precision: float = Field(ge=0.0, le=10.0)
    # 0~10. visual diff + intent graph match 기반
    maintainability: float = Field(ge=0.0, le=10.0)
    # 0~10. normalization drift score 역수
    automation: float = Field(ge=0.0, le=10.0)
    # 0~10. auto-fix success rate, human intervention 없음
    scalability: float = Field(ge=0.0, le=10.0)
    # 0~10. 복잡도 확장 가능성 (v1에서 reference only)
    composite: float = Field(ge=0.0, le=10.0)
    # 0~10. (precision*3 + maintainability*2 + automation*3 + scalability*2) / 10
    baseline_ref: str | None = None    # GSD baseline artifact 경로
    baseline_composite: float | None = None  # GSD 비교 기준 점수
    measured_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def compute_composite(self) -> float:
        return (self.precision * 3 + self.maintainability * 2 +
                self.automation * 3 + self.scalability * 2) / 10
```

---

## 10. ReleaseDecision

```python
# src/ddk/models/release.py
from __future__ import annotations
from typing import Literal
from datetime import datetime, timezone
from pydantic import Field
from ._base import DDKBaseModel


class BlockerItem(DDKBaseModel):
    blocker_id: str                    # "BLOCK-001"
    category: Literal["runtime", "visual", "security", "contract", "migration"]
    message: str
    severity: Literal["sev0", "sev1", "sev2"]


class ReleaseDecision(DDKBaseModel):
    case_id: str
    schema_version: str = "1.0"
    status: Literal["certified-ready", "certified-blocked", "manual-review-required"]
    blockers: list[BlockerItem] = Field(default_factory=list)
    human_actions: list[str] = Field(default_factory=list)
    # 사람이 해야 할 행동 목록
    scorecard_ref: str | None = None
    composite_score: float | None = None
    decided_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

---

## 11. LLMCallRecord

```python
# src/ddk/models/llm.py
from __future__ import annotations
from typing import Literal
from datetime import datetime, timezone
from pydantic import Field
from ._base import DDKBaseModel


class LLMCallRecord(DDKBaseModel):
    call_id: str                       # "{node_name}-{timestamp}"
    schema_version: str = "1.0"
    node_name: str                     # LangGraph 노드 이름
    model: str                         # "claude-sonnet-5-5"
    provider: str                      # "anthropic" | "openai"
    provider_model_id: str | None = None   # provider가 반환한 정확한 revision/header 값
    prompt_version: str | None = None      # "auto_fix@1.1" 형태
    temperature: float = Field(ge=0.0, le=2.0)
    seed: int | None = None
    context_pack_hash: str             # SHA256 hex[:16]
    replay_compatibility: Literal["strict", "weak", "non-equivalent"] = "strict"
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cost_usd: float | None = None      # None = 계산 불가
    duration_seconds: float = Field(ge=0.0)
    called_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

---

## 13-A. 에러 상태 모델

```python
# src/ddk/models/errors.py
from __future__ import annotations
from enum import Enum
from datetime import datetime, timezone
from pydantic import Field
from ._base import DDKBaseModel


class ErrorCategory(str, Enum):
    INPUT = "INPUT"
    LLM = "LLM"
    COST = "COST"
    VALIDATION = "VALIDATION"
    VISUAL = "VISUAL"
    SECURITY = "SECURITY"
    INFRA = "INFRA"
    FATAL = "FATAL"


class ErrorSeverity(str, Enum):
    WARNING = "warning"       # 진행 가능, 로그만
    RECOVERABLE = "recoverable"  # 재시도/auto-fix 가능
    BLOCKING = "blocking"     # 케이스 차단, 수동 검토 필요
    FATAL = "fatal"           # 즉시 중단, 에스컬레이션


class DDKError(DDKBaseModel):
    """모든 딸깍 에러의 공통 구조. EvidencePack에 포함된다."""
    error_id: str                          # "ERR-C001-003" 형식
    case_id: str
    category: ErrorCategory
    severity: ErrorSeverity
    error_code: str                        # "LLM_TIMEOUT", "BUILD_FAILED" 등
    message: str                           # 사람이 읽을 수 있는 설명
    source_node: str | None = None         # LangGraph 노드명
    source_layer: str | None = None        # "llm", "adapter", "sandbox", "graph"
    recoverable: bool = False
    retry_count: int = 0                   # 이 에러까지 시도한 재시도 횟수
    suggestion: str | None = None          # 사용자에게 제안할 다음 행동
    raw_error: str | None = None           # 원본 예외 메시지/스택 트레이스
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ErrorChain(DDKBaseModel):
    """케이스 실행 중 발생한 모든 에러의 시간순 체인."""
    case_id: str
    errors: list[DDKError] = Field(default_factory=list)
    has_blocking: bool = False             # blocking 이상 에러 존재 여부
    has_fatal: bool = False

    def append(self, error: DDKError) -> None:
        self.errors.append(error)
        if error.severity == ErrorSeverity.BLOCKING:
            self.has_blocking = True
        if error.severity == ErrorSeverity.FATAL:
            self.has_fatal = True

    @property
    def last_error(self) -> DDKError | None:
        return self.errors[-1] if self.errors else None

    @property
    def blocking_errors(self) -> list[DDKError]:
        return [e for e in self.errors if e.severity in (ErrorSeverity.BLOCKING, ErrorSeverity.FATAL)]
```

---

## 12. EvidencePack

```python
# src/ddk/models/evidence.py
from __future__ import annotations
from datetime import datetime, timezone
from pydantic import Field
from ._base import DDKBaseModel


class EvidencePack(DDKBaseModel):
    case_id: str
    schema_version: str = "1.0"
    # 각 artifact의 .ddk/ 내 상대 경로 (ref)
    case_input_ref: str
    repo_profile_ref: str
    intent_graph_ref: str
    generation_plan_ref: str
    generated_artifacts_ref: str
    normalization_report_ref: str | None = None
    runtime_validation_report_ref: str | None = None
    visual_regression_report_ref: str | None = None
    fix_attempts: list[str] = Field(default_factory=list)
    scorecard_ref: str | None = None
    release_decision_ref: str | None = None
    llm_call_records: list[str] = Field(default_factory=list)
    # 요약 통계
    total_llm_cost_usd: float = 0.0
    total_fix_attempts: int = 0
    final_status: str | None = None    # ReleaseDecision.status
    error_chain: ErrorChain | None = None  # 실행 중 발생한 에러 체인
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

---

## 13. InterviewTurn (Design Studio)

```python
# src/ddk/models/design_interview.py
from __future__ import annotations
from typing import Literal
from datetime import datetime, timezone
from pydantic import Field
from ._base import DDKBaseModel


class InterviewTurn(DDKBaseModel):
    """인터뷰 한 턴의 기록 — Design Studio 인터뷰 세션의 개별 대화 단위."""
    turn_id: str                           # "IT-001" 형식
    speaker: Literal["system", "user"]     # 발화자
    message: str                           # 발화 내용
    extracted_requirements: list[str] = Field(default_factory=list)
    # 이 턴에서 추출된 REQ IDs (e.g. ["REQ-001", "REQ-003"])
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

---

## 14. DesignRequirement (Design Studio)

```python
# src/ddk/models/design_requirement.py
from __future__ import annotations
from typing import Literal
from pydantic import Field, field_validator
from ._base import DDKBaseModel


class DesignRequirement(DDKBaseModel):
    """구조화된 요구사항 — MoSCoW 우선순위와 인수 기준을 포함."""
    req_id: str                            # "REQ-001" 형식
    title: str                             # 요구사항 제목 (1~200자)
    description: str                       # 상세 설명 (1~2000자)
    priority: Literal["must", "should", "could", "wont"]  # MoSCoW 우선순위
    acceptance_criteria: list[str]          # 인수 기준 (최소 1개)
    trace_id: str | None = None            # upstream trace 식별자
    source_turns: list[str] = Field(default_factory=list)
    # InterviewTurn.turn_id 참조 목록 — 요구사항 출처 추적

    @field_validator("acceptance_criteria")
    @classmethod
    def validate_ac(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("acceptance_criteria는 최소 1개 이상이어야 합니다")
        return v

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) > 200:
            raise ValueError("title은 1~200자여야 합니다")
        return v

    @field_validator("description")
    @classmethod
    def validate_description(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) > 2000:
            raise ValueError("description은 1~2000자여야 합니다")
        return v
```

---

## 15. DesignDocument (Design Studio)

```python
# src/ddk/models/design_document.py
from __future__ import annotations
from typing import Literal
from pydantic import Field
from ._base import DDKBaseModel


class DesignDocument(DDKBaseModel):
    """생성된 설계문서 하나 — 표준 기반의 마크다운 문서."""
    doc_type: Literal[
        "SRS", "PRD", "Architecture", "API", "DBSchema",
        "Security", "ADR", "TestStrategy", "ImplPlan", "AIHandoff"
    ]
    standard_ref: str                      # 적용 표준 (e.g. "IEEE 830", "ISO 42010", "OpenAPI 3.1")
    title: str                             # 문서 제목
    content_markdown: str                  # 마크다운 본문
    requirement_refs: list[str]            # 추적된 REQ-XXX ID 목록
    compliance_score: float = Field(ge=0.0, le=1.0)
    # 표준 적합도 (0.0 = 부적합, 1.0 = 완전 적합)
    metadata: dict[str, str] = Field(default_factory=dict)
    # 거버넌스 메타데이터 (e.g. {"Authority": "AI", "Status": "Draft", "Version": "1.0"})
```

---

## 16. StandardsComplianceResult (Design Studio)

```python
# src/ddk/models/design_compliance.py
from __future__ import annotations
from typing import Literal
from pydantic import Field
from ._base import DDKBaseModel


class ComplianceCheckItem(DDKBaseModel):
    """표준의 개별 조항에 대한 적합성 검증 항목."""
    clause_id: str                         # 조항 식별자 (e.g. "IEEE830-§3.2")
    clause_description: str                # 조항 설명
    status: Literal["pass", "partial", "fail", "not_applicable"]
    evidence: str | None = None            # 적합 증거 또는 위반 상세
    remediation: str | None = None         # 부적합 시 개선 방안


class StandardsComplianceResult(DDKBaseModel):
    """표준 적합성 검증 결과 — 개별 조항 단위 점검과 종합 점수."""
    standard_name: str                     # 적용 표준명 (e.g. "IEEE 830", "ISO 42010")
    doc_type: str                          # 검증 대상 문서 유형
    checks: list[ComplianceCheckItem]      # 조항별 점검 결과
    overall_score: float = Field(ge=0.0, le=1.0)
    # 종합 적합도 점수
    passed: bool                           # 전체 통과 여부
```

---

## 17. QualityGateScore (Design Studio)

```python
# src/ddk/models/design_quality.py
from __future__ import annotations
from typing import Literal
from pydantic import Field, field_validator
from ._base import DDKBaseModel


class QualityAxisScore(DDKBaseModel):
    """6축 품질 검증의 개별 축 점수."""
    axis: Literal[
        "completeness", "traceability", "implementability",
        "verifiability", "operability", "compliance"
    ]
    score: int = Field(ge=0, le=5)         # 0~5점
    rationale: str                         # 점수 근거


class QualityGateScore(DDKBaseModel):
    """6축 품질 게이트 점수 — 설계 패키지 전체의 품질 판정."""
    axes: list[QualityAxisScore]           # 정확히 6개 축
    total_score: int = Field(ge=0, le=30)  # 6축 합산 (0~30)
    verdict: Literal["pass", "flag", "block"]
    # pass: 전체 통과, flag: 경고 포함 통과, block: 재작업 필요
    hard_blocks: list[str] = Field(default_factory=list)
    # 즉시 수정 필요 항목
    recommendations: list[str] = Field(default_factory=list)
    # 개선 권고 사항

    @field_validator("axes")
    @classmethod
    def validate_six_axes(cls, v: list["QualityAxisScore"]) -> list["QualityAxisScore"]:
        if len(v) != 6:
            raise ValueError("axes는 정확히 6개여야 합니다")
        axis_names = {a.axis for a in v}
        expected = {
            "completeness", "traceability", "implementability",
            "verifiability", "operability", "compliance",
        }
        if axis_names != expected:
            raise ValueError(f"axes는 {expected} 각각 하나씩 포함해야 합니다")
        return v
```

---

## 18. DesignPackageManifest (Design Studio)

```python
# src/ddk/models/design_package.py
from __future__ import annotations
from datetime import datetime
from pydantic import Field, field_validator
from ._base import DDKBaseModel
from .design_interview import InterviewTurn
from .design_requirement import DesignRequirement
from .design_document import DesignDocument
from .design_compliance import StandardsComplianceResult
from .design_quality import QualityGateScore


class DesignPackageManifest(DDKBaseModel):
    """설계 패키지 전체 매니페스트 — 인터뷰부터 품질 게이트까지 전 산출물을 포함."""
    package_id: str                        # "DP-001" 형식
    project_name: str                      # 프로젝트 이름
    requirements: list[DesignRequirement]  # 추출된 요구사항 목록
    documents: list[DesignDocument]        # 생성된 설계문서 목록
    compliance_results: list[StandardsComplianceResult]
    # 표준 적합성 검증 결과
    quality_gate: QualityGateScore         # 6축 품질 게이트 점수
    interview_log: list[InterviewTurn]     # 인터뷰 대화 이력
    created_at: datetime                   # 패키지 생성 시각

    @field_validator("requirements")
    @classmethod
    def validate_requirements_non_empty(
        cls, v: list[DesignRequirement],
    ) -> list[DesignRequirement]:
        if not v:
            raise ValueError("requirements는 최소 1개 이상이어야 합니다")
        return v

    @field_validator("documents")
    @classmethod
    def validate_documents_non_empty(
        cls, v: list[DesignDocument],
    ) -> list[DesignDocument]:
        if not v:
            raise ValueError("documents는 최소 1개 이상이어야 합니다")
        return v
```

---

## 19. DdalggakConfig — 전역 설정 모델

> Phase 0 구현 착수 전 필수. 모든 환경변수와 기본값의 SSoT.

```python
# src/ddk/models/config.py

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings
from pathlib import Path
from enum import Enum


class LLMProvider(str, Enum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"


class DdalggakConfig(BaseSettings):
    """딸깍 전역 설정. 환경변수 또는 .env 파일에서 로드."""

    model_config = {"env_prefix": "DDK_"}

    # ── LLM 설정 ──
    llm_provider: LLMProvider = LLMProvider.ANTHROPIC
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    llm_default_model: str = "claude-sonnet-5-5"
    llm_cheap_model: str = "claude-haiku-5-5"
    llm_fallback_model: str = "gpt-4o-2024-11-20"
    llm_temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    llm_max_tokens: int = Field(default=4096, ge=256, le=200_000)
    llm_cost_cap_usd: float = Field(default=2.0, gt=0.0)
    llm_seed: int | None = None

    # ── 재시도 정책 ──
    llm_max_retries: int = Field(default=3, ge=0, le=10)
    llm_retry_base_delay: float = Field(default=1.0, gt=0.0)

    # ── 타임아웃 ──
    timeout_llm_call_seconds: int = Field(default=120, ge=10)
    timeout_build_seconds: int = Field(default=180, ge=30)
    timeout_playwright_seconds: int = Field(default=60, ge=10)
    timeout_sandbox_total_seconds: int = Field(default=300, ge=60)

    # ── Auto-fix ──
    auto_fix_max_retries: int = Field(default=2, ge=0, le=5)
    auto_fix_max_files: int = Field(default=3, ge=1)
    auto_fix_max_lines: int = Field(default=120, ge=10)

    # ── Sandbox ──
    sandbox_network_deny: bool = True
    sandbox_writable_paths: list[str] = Field(default_factory=lambda: [".ddk-workspace/", ".ddk-artifacts/"])

    # ── Visual ──
    visual_ssim_threshold: float = Field(default=0.92, ge=0.0, le=1.0)
    visual_changed_pixel_max_ratio: float = Field(default=0.05, ge=0.0, le=1.0)
    visual_critical_region_overlap_min: float = Field(default=0.90, ge=0.0, le=1.0)

    # ── 경로 ──
    workspace_base_dir: Path = Field(default=Path(".ddk-workspace"))
    artifacts_dir: Path = Field(default=Path(".ddk-artifacts"))

    # ── Playwright ──
    playwright_viewport_width: int = Field(default=1280, ge=320)
    playwright_viewport_height: int = Field(default=720, ge=240)
    playwright_browser: str = "chromium"

    @field_validator("anthropic_api_key", "openai_api_key")
    @classmethod
    def redact_key_in_repr(cls, v: str) -> str:
        return v  # 실제 키는 보존하되, __repr__에서 마스킹은 별도 처리

    def active_api_key(self) -> str:
        if self.llm_provider == LLMProvider.ANTHROPIC:
            if not self.anthropic_api_key:
                raise ValueError("DDK_ANTHROPIC_API_KEY 미설정")
            return self.anthropic_api_key
        if not self.openai_api_key:
            raise ValueError("DDK_OPENAI_API_KEY 미설정")
        return self.openai_api_key
```

### 로드 순서

1. 기본값 (위 Field defaults)
2. `.env` 파일 (`pydantic-settings` 자동 로드)
3. 환경변수 (`DDK_` prefix)
4. CLI `--option` override (Typer callback에서 주입)

### Preflight 검증

```python
def validate_config_for_run(config: DdalggakConfig) -> list[str]:
    """실행 전 설정 유효성 검사. 문제 목록 반환."""
    issues: list[str] = []
    if not config.active_api_key():
        issues.append("LLM API key 미설정")
    if config.llm_cost_cap_usd < 0.1:
        issues.append(f"비용 상한이 너무 낮음: ${config.llm_cost_cap_usd}")
    if config.auto_fix_max_retries > 0 and config.timeout_sandbox_total_seconds < 120:
        issues.append("auto-fix 활성화 시 sandbox 타임아웃이 120초 이상이어야 함")
    return issues
```

### 테스트 요구사항

- `test_config_defaults.py` — 기본값 로드 확인
- `test_config_env_override.py` — 환경변수 오버라이드
- `test_config_validation.py` — 범위 밖 값 거부 (temperature > 2.0 등)
- `test_config_preflight.py` — API key 누락 시 이슈 반환

---

## 20. 스키마 버전 관리

```json
// .ddk/schema-version.json
{
  "version": "1.0",
  "created_at": "2024-12-01T00:00:00Z",
  "models": {
    "CaseInput": "1.0",
    "RepoProfile": "1.0",
    "IntentGraph": "1.0",
    "GenerationPlan": "1.0",
    "GeneratedArtifactSet": "1.0",
    "NormalizationReport": "1.0",
    "RuntimeValidationReport": "1.0",
    "VisualRegressionReport": "1.0",
    "FixAttempt": "1.0",
    "Scorecard": "1.0",
    "ReleaseDecision": "1.0",
    "LLMCallRecord": "1.0",
    "EvidencePack": "1.0",
    "InterviewTurn": "1.0",
    "DesignRequirement": "1.0",
    "DesignDocument": "1.0",
    "ComplianceCheckItem": "1.0",
    "StandardsComplianceResult": "1.0",
    "QualityAxisScore": "1.0",
    "QualityGateScore": "1.0",
    "DesignPackageManifest": "1.0",
    "DdalggakConfig": "1.0"
  }
}
```

스키마 버전이 다른 artifact를 읽을 때의 기본 규칙:

- `patch` 차이: 그대로 읽기 허용
- `minor` 차이: additive optional field만 허용, 없으면 default 적용
- `major` 차이: 자동 읽기 금지, 명시적 migration 함수 필요

즉 새 required field 추가, field 의미 변경, enum 의미 변경은 모두 `major` bump 대상이다.

```python
def migrate_artifact(payload: dict, from_version: str, to_version: str) -> dict:
    """
    major version이 바뀐 artifact는 explicit migration 없이는 읽지 않는다.
    minor version은 additive optional field만 허용한다.
    """
    ...
```

스키마 버전이 호환 범위를 벗어나면 `SchemaVersionMismatchError`를 발생시킨다.

---

## 21. Fake LLM Provider (테스트용)

```python
# tests/e2e/fake_llm.py

class FakeLLMAdapter:
    """E2E 테스트용 결정론적 LLM — 실제 API 호출 없음."""

    def __init__(self, responses: dict[str, Any]):
        # {"intent_extract": IntentGraph(...), "generate": [GeneratedFile(...)], ...}
        self._responses = responses

    async def complete_structured(
        self,
        messages: list,
        config,
        output_schema: type,
    ) -> LLMResponse:
        node = config.schema_version  # node 식별자로 활용
        response_data = self._responses.get(node, {})
        return LLMResponse(
            content=output_schema(**response_data).model_dump_json(),
            model="fake-model-v1",
            provider="fake",
            input_tokens=100,
            output_tokens=200,
            cost_usd=0.0,
            raw={},
        )
```

## §22. conftest.py — 테스트 공용 Fixture

> 모든 테스트 파일이 공유하는 fixture. Phase 0 TDD 착수 시 첫 번째로 작성.

```python
# tests/conftest.py

import pytest
from pathlib import Path
from unittest.mock import AsyncMock
from ddk.models.config import DdalggakConfig
from ddk.models.intent import IntentGraph, LayoutRegion, ComponentSpec
from ddk.models.generation import GeneratedFile, GeneratedOutput
from ddk.adapters.llm.base import LLMAdapter, LLMResponse, LLMCallConfig, Message


@pytest.fixture
def test_config() -> DdalggakConfig:
    """테스트용 최소 설정. API key는 더미값."""
    return DdalggakConfig(
        anthropic_api_key="sk-ant-test-dummy-key",
        llm_cost_cap_usd=0.10,
        timeout_llm_call_seconds=10,
        timeout_build_seconds=30,
        timeout_playwright_seconds=10,
        timeout_sandbox_total_seconds=60,
        workspace_base_dir=Path("/tmp/ddk-test-workspace"),
        artifacts_dir=Path("/tmp/ddk-test-artifacts"),
    )


class FakeLLMAdapter:
    """테스트용 LLM 어댑터. 사전 정의된 응답을 반환."""

    def __init__(self, responses: dict[str, dict]):
        """
        Args:
            responses: {call_key: response_dict} 매핑.
                       call_key는 output_schema.__name__ 사용.
        """
        self._responses = responses
        self._call_log: list[tuple[str, list[Message], LLMCallConfig]] = []

    async def complete(self, messages: list[Message], config: LLMCallConfig) -> LLMResponse:
        self._call_log.append(("complete", messages, config))
        return LLMResponse(
            content="fake response",
            model=config.model,
            provider="fake",
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.001,
            raw={},
        )

    async def complete_structured(
        self,
        messages: list[Message],
        config: LLMCallConfig,
        output_schema: type,
    ) -> LLMResponse:
        key = output_schema.__name__
        self._call_log.append((key, messages, config))
        if key not in self._responses:
            raise KeyError(f"FakeLLM: no response configured for schema '{key}'")
        return LLMResponse(
            content=str(self._responses[key]),
            model=config.model,
            provider="fake",
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.001,
            raw=self._responses[key],
        )

    @property
    def call_count(self) -> int:
        return len(self._call_log)

    def assert_called_with_schema(self, schema_name: str) -> None:
        keys = [key for key, _, _ in self._call_log]
        assert schema_name in keys, f"Expected call with '{schema_name}', got {keys}"


@pytest.fixture
def fake_llm() -> FakeLLMAdapter:
    """빈 FakeLLM 어댑터. 테스트에서 responses를 직접 설정."""
    return FakeLLMAdapter(responses={})


@pytest.fixture
def fake_llm_with_intent() -> FakeLLMAdapter:
    """IntentGraph 응답이 사전 설정된 FakeLLM."""
    return FakeLLMAdapter(responses={
        "IntentGraph": {
            "id": "C-TEST-001",
            "source_image_hash": "testhash123",
            "layout_regions": [{
                "id": "LR-001",
                "semantic_label": "테스트 헤더",
                "bounds": {"x": 0.0, "y": 0.0, "w": 1.0, "h": 0.1},
                "children": [],
                "confidence": 0.95,
            }],
            "components": [{
                "id": "CS-001",
                "component_type": "Button",
                "props": {"label": "테스트"},
                "region_id": "LR-001",
                "confidence": 0.9,
            }],
            "interactions": [],
            "confidence": 0.92,
        }
    })


@pytest.fixture
def fixture_repo_path(tmp_path: Path) -> Path:
    """최소 React/Vite/TS fixture repo 구조."""
    repo = tmp_path / "fixture-repo"
    repo.mkdir()
    (repo / "package.json").write_text('{"name": "test", "scripts": {"build": "vite build"}}')
    (repo / "tsconfig.json").write_text('{"compilerOptions": {"strict": true}}')
    (repo / "src").mkdir()
    (repo / "src" / "App.tsx").write_text("export default function App() { return <div />; }")
    return repo


@pytest.fixture
def sample_image_path(tmp_path: Path) -> Path:
    """1x1 PNG 테스트 이미지."""
    from PIL import Image
    img_path = tmp_path / "test.png"
    Image.new("RGB", (100, 100), color="white").save(img_path)
    return img_path
```

### Fixture 사용 패턴

```python
# tests/unit/test_intent_extractor.py 예시

async def test_extract_returns_intent_graph(fake_llm_with_intent, sample_image_path, test_config):
    extractor = IntentExtractorService(llm=fake_llm_with_intent, config=test_config)
    result = await extractor.extract(image_path=sample_image_path, prompt="대시보드")
    assert isinstance(result, IntentGraph)
    assert result.confidence >= 0.9
    fake_llm_with_intent.assert_called_with_schema("IntentGraph")
```

---

## Design Studio ↔ Delivery 핸드오프 모델

> Design Studio 완료 후 Delivery 파이프라인 실행 시 필요한 데이터 계약.
> `package_handoff_node`가 이 구조로 저장하고, `ingest_node`가 이 구조를 읽는다.

### DesignHandoffPackage 모델

```python
from pathlib import Path
from pydantic import BaseModel, Field
from datetime import datetime


class DesignHandoffPackage(BaseModel):
    """
    Design Studio 완료 시 생성되는 핸드오프 패키지.
    
    저장 위치: {workspace_dir}/design-handoff/package.json
    이 파일이 존재하면 ddk run이 자동으로 읽어 CaseInput을 보강한다.
    """
    model_config = {"extra": "forbid"}

    # 패키지 메타데이터
    handoff_id: str = Field(description="핸드오프 패키지 고유 ID (dds-{uuid4})")
    created_at: datetime
    design_studio_version: str = Field(description="딸깍 버전 (pyproject.toml과 동일)")

    # 요구사항 (Design Studio에서 추출)
    requirements: list[dict] = Field(
        description="REQ-XXX 형식 요구사항 목록. [{id, title, priority, acceptance_criteria}]"
    )
    target_components: list[str] = Field(
        default_factory=list,
        description="구현 대상 컴포넌트 이름 목록 (GenerationPlan 생성에 활용)"
    )
    
    # 설계 문서 (Design Studio에서 생성)
    design_document_path: str | None = Field(
        default=None,
        description="생성된 설계 문서 파일 경로 (상대경로, workspace_dir 기준)"
    )
    quality_score: float | None = Field(
        default=None,
        description="Design Studio 품질 게이트 점수 (0~30)"
    )
    quality_verdict: str | None = Field(
        default=None,
        description="'pass' | 'flag' | 'block'"
    )
    
    # Delivery 입력 보강 정보
    prompt_override: str | None = Field(
        default=None,
        description="Design Studio에서 도출된 정밀 프롬프트 (ddk run --prompt의 기본값으로 사용)"
    )
    reference_notes: str | None = Field(
        default=None,
        description="구현자를 위한 참조 메모 (컨텍스트 팩에 포함됨)"
    )

    # 추적
    interview_summary: str | None = Field(
        default=None,
        description="인터뷰 핵심 내용 요약 (컨텍스트 팩 P5 항목으로 포함)"
    )


class HandoffManifest(BaseModel):
    """
    workspace_dir/design-handoff/MANIFEST.json 파일 구조.
    여러 핸드오프 패키지가 있을 때 목록 관리용.
    """
    model_config = {"extra": "forbid"}

    workspace_dir: str
    packages: list[str] = Field(description="package.json 파일 경로 목록")
    latest: str | None = Field(description="가장 최근 핸드오프 패키지 경로")
    created_at: datetime
    updated_at: datetime
```

### 핸드오프 파일 구조

```
{workspace_dir}/
  design-handoff/
    MANIFEST.json                    # HandoffManifest
    dds-{uuid4}/
      package.json                   # DesignHandoffPackage
      design-document.md             # 생성된 설계 문서 (선택)
      requirements.json              # requirements 상세 목록
```

### `ddk run`에서 핸드오프 읽기

```python
# ingest_node에서 handoff 패키지 자동 로드

async def ingest_node(state: GraphState) -> dict:
    case_input = state["case_input"]
    repo_path = Path(case_input.repo_path)
    
    # Design Studio 핸드오프 패키지 자동 로드 (있으면)
    handoff_path = repo_path / "design-handoff" / "MANIFEST.json"
    if handoff_path.exists():
        manifest = HandoffManifest.model_validate_json(handoff_path.read_text())
        if manifest.latest:
            pkg_path = repo_path / manifest.latest
            handoff = DesignHandoffPackage.model_validate_json(pkg_path.read_text())
            
            # prompt_override 적용 (명시적 --prompt가 없을 때만)
            if not case_input.prompt and handoff.prompt_override:
                case_input = case_input.model_copy(update={"prompt": handoff.prompt_override})
            
            # reference_notes를 context pack에 포함
            return {
                "case_input": case_input,
                "design_handoff": handoff,  # GraphState에 추가 필요
            }
    
    return {"case_input": case_input, "design_handoff": None}
```

> **참고:** `GraphState`에 `design_handoff: DesignHandoffPackage | None` 필드를 추가해야 한다.
> `04-system-design.md`의 GraphState 정의도 함께 업데이트하라.
