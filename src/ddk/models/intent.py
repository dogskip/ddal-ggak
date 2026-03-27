from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import Field

from ._base import DDKBaseModel


class BoundingBox(DDKBaseModel):
    """이미지 내 상대 좌표 (0.0~1.0)"""

    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    width: float = Field(gt=0.0, le=1.0)
    height: float = Field(gt=0.0, le=1.0)


class LayoutRegion(DDKBaseModel):
    id: str  # "region-header", "region-main" 등
    region_type: Literal[
        "header",
        "nav",
        "sidebar",
        "main",
        "footer",
        "modal",
        "card",
        "form",
        "table",
        "hero",
        "cta",
        "list",
        "other",
    ]
    bounds: BoundingBox
    children: list[str] = Field(default_factory=list)  # child region IDs
    semantic_label: str | None = None  # "사용자 프로필", "검색 결과" 등


class PropValue(DDKBaseModel):
    """컴포넌트 prop 값 — 리터럴 또는 dynamic"""

    value: str | int | bool | None = None
    is_dynamic: bool = False  # True면 prop이 실제 데이터에서 옴


class ComponentSpec(DDKBaseModel):
    id: str  # "comp-001", "comp-login-btn" 등
    component_type: str  # "Button", "Input", "Card", "Table" 등
    props: dict[str, PropValue] = Field(default_factory=dict)
    children: list[ComponentSpec] = Field(default_factory=list)
    region_id: str | None = None  # 속한 LayoutRegion ID
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    notes: str | None = None  # 추가 추론 메모


class InteractionSpec(DDKBaseModel):
    id: str  # "int-001"
    trigger: Literal[
        "click", "hover", "focus", "submit", "change", "keydown", "scroll"
    ]
    source_component_id: str
    action: Literal[
        "navigate",
        "open-modal",
        "close-modal",
        "submit-form",
        "toggle",
        "filter",
        "sort",
        "load-more",
        "other",
    ]
    target: str | None = None  # 이동 경로 또는 모달 ID
    params: dict[str, Any] = Field(default_factory=dict)


class IntentGraph(DDKBaseModel):
    id: str  # case_id와 동일
    schema_version: str = "1.0"
    source_image_hash: str  # SHA256 hex[:16]
    layout_regions: list[LayoutRegion]
    components: list[ComponentSpec]
    interactions: list[InteractionSpec]
    confidence: float = Field(ge=0.0, le=1.0)
    # 전체 추출 신뢰도 (0.0 = 완전 불확실, 1.0 = 확실)
    unresolved_items: list[str] = Field(default_factory=list)
    # 추출 실패 항목 설명 문자열
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
