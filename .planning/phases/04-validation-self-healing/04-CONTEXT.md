# Phase 4 Context: Validation & Self-Healing

## 결정된 사항 (변경 불가)

### 자동화 수리 전략: 하이브리드
- **결정론적 패치** (R-01~R-07): string/AST 치환으로 처리
- **LLM 재생성** (R-08~R-09): 복잡한 syntax error, unhandled exception
- FakeLLM 키 추가 필요: `"autofix"` (AutoFixPlanner 노드용)

| 규칙 ID | 대상 Taxonomy | 구현 방식 |
|---------|--------------|----------|
| R-01 | FT-LINT-001 | 미사용 import 줄 삭제 (결정론적) |
| R-02 | FT-LINT-002/003 | eslint --fix 실행 (결정론적) |
| R-03 | FT-TYPE-002 | `: any` annotation 추가 (결정론적) |
| R-04 | FT-TYPE-001/003 | `as unknown as T` cast 삽입 (결정론적) |
| R-05 | FT-BUILD-003 | package.json dependencies 추가 (결정론적) |
| R-06 | FT-BUILD-001 | 상대경로 import 재작성 (결정론적) |
| R-07 | FT-RUNTIME-002 | Optional chaining `?.` 추가 (결정론적) |
| R-08 | FT-ASYNC-002 | `await` 누락 추가 (결정론적) |
| R-09 | FT-BUILD-002 / FT-RUNTIME-001 | LLM 재생성 (FakeLLM key: `"autofix"`) |

### Playwright 통합 범위: 실제 Playwright 포함
- Phase 4 통합 테스트에서 **실제 Playwright + dev server** 기동
- VALID-02: 실제 브라우저 콘솔 에러 + 네트워크 실패 수집
- VALID-03: scikit-image 또는 Pillow 기반 실제 SSIM 계산 (threshold=0.92)
- FakePlaywrightAdapter는 단위 테스트에서만 사용
- CI에서 playwright가 없을 경우: `pytest.mark.playwright` 마커로 skip 가능하게 구성

### Validation-Fix 루프: LangGraph 조건부 엣지
```
START → ... → normalize → validate → [router]
    ├─ "pass"           → END
    ├─ "fix_available"  → autofix → validate (루프, budget 소모)
    └─ "exhausted"      → END (terminal_state="manual-review-required")
```
- `add_conditional_edges("validate", route_after_validate, {...})` 사용
- oscillation 감지: `failure_set_hash = hash(frozenset((f.taxonomy_id, f.file_path or "") for f in failures))`
  - ⚠️ `failure.id`(UUID)는 매 실행마다 재생성되므로 절대 사용 금지
  - hash는 **autofix_node에서 fix 전에** `failure_hash_history`에 추가 (validate_node가 아님)
  - 동일 hash 재등장 → `route_after_validate`가 `"exhausted"` 반환
  - 동일 hash 재등장 → `oscillating=True` → `"exhausted"` 경로로 탈출
- `retry_budget_remaining` GraphState 필드 매 fix마다 차감

## 이미 결정된 사항 (Prior phases)

- SSIM threshold = 0.92 (visual.py VisualRegressionReport에 정의됨)
- retry_budget_remaining = 3 초기값 (state.py GraphState에 정의됨)
- FAILURE_TAXONOMY: 20개 FT-* 코드 (validation.py에 완전 정의됨)
- git checkpoint ref 형식: `refs/ddk/fix/{case_id}/attempt-{n}`
- additive-only 모델 정책: 기존 필드 삭제/rename 절대 금지

## Phase 4 신규 FakeLLM 키

| 키 | 담당 서비스 |
|----|-----------|
| `"autofix"` | AutoFixPlanner (R-09용 LLM 재생성) |
| `"validate"` | RuntimeValidator (LLM-assisted 실패 분류, 필요시) |

## 사용할 기존 인프라

- Models: `RuntimeValidationReport`, `VisualRegressionReport`, `FailureRecord`, `FixAttempt`, `MismatchRegion`
- Protocols: `GitAdapter`, `SandboxAdapter`, `BuildRunner`, `PlaywrightAdapter`
- Fakes: `TempDirSandbox`, `FakePlaywrightAdapter`, `FakeRollbackController`, `fake_sandbox.py`
- GraphState: `fix_attempts`, `retry_budget_remaining`, `pre_run_checkpoint_ref`, `runtime_validation_report`, `visual_regression_report`

## Phase 4 신규 서비스 (TDD로 구현)

1. `src/ddk/services/runtime_validator.py` — VALID-01~03 실행
2. `src/ddk/services/failure_classifier.py` — FAILURE_TAXONOMY 매핑
3. `src/ddk/services/auto_fix_planner.py` — 9개 규칙 적용 (hybrid)
4. `src/ddk/services/rollback_controller.py` — git checkpoint 관리
5. `src/ddk/graph/nodes/validate.py` — validate 노드 (thin adapter)
6. `src/ddk/graph/nodes/autofix.py` — autofix 노드 (thin adapter)

## Phase 4 그래프 변경

- `src/ddk/graph/builder.py`: normalize 이후 validate → conditional_edge → autofix 노드 추가
- `src/ddk/graph/router.py` (신규): `route_after_validate()` 함수

## TDD 사이클

1. **Red**: 서비스 stub 파일 생성 → `uv run pytest tests/unit/phase4/` FAIL
2. **Green**: 테스트만 보고 최소 구현 → 전부 pass
3. **Refactor**: pyright strict 0 errors, `uv run ruff check --fix`

## 연기된 아이디어

- 실제 CI 환경 Playwright 자동 설치 (`playwright install chromium`)
- SSIM 기반 diff 이미지 생성 (시각적 리포트)
- 외부 lint 도구 자동 선택 (eslint vs biome vs oxc)
→ Phase 5 이후 처리
