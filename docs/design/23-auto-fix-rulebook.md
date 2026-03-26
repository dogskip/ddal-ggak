# Auto-fix Rulebook

> P0 auto-fix를 open-ended code generation이 아니라 **deterministic repair system** 으로 제한한다.
> 이 문서가 없으면 `04-system-design.md` 의 failure-class 전략은 방향만 있고 구현 규칙은 비어 있게 된다.

---

## 1. 목적

`딸깍`의 auto-fix는 "다시 한 번 생성해 보기"가 아니다.

정의는 다음과 같다:

1. 실패를 안정된 taxonomy로 분류한다.
2. taxonomy를 **고정된 repair rule** 에 매핑한다.
3. 한 번의 시도에서 **하나의 primary rule** 만 적용한다.
4. 검증 결과가 개선되지 않으면 rule rotation 또는 manual review로 종료한다.

즉 auto-fix의 목표는 **무한한 창의성** 이 아니라 **제한된 범위의 안전한 수리** 다.

---

## 2. 전역 원칙

### 2.1 한 시도당 변경 한도

- 최대 변경 파일 수: `3`
- 최대 변경 라인 수: `120`
- 최대 primary rule 수: `1`
- 최대 secondary rule 수: `1` (`normalize-only` 보조 정리 허용)

이 한도를 넘으면 `manual-review-required` 로 전환한다.

### 2.2 금지되는 수리

아래가 필요하면 auto-fix 대상이 아니다:

- 새 dependency 추가
- package manager lockfile 수정
- build config/vite/tsconfig/eslint config 수정
- DB schema/API contract/auth policy 변경
- 4개 이상 파일에 걸친 구조 리팩터링
- 사용자 prompt 의미를 바꾸는 UI 재설계

### 2.3 우선순위

한 케이스에 failure family가 여러 개 섞여 있으면 아래 순서로 고친다.

1. `build/import`
2. `type`
3. `lint`
4. `runtime`
5. `visual`

이 순서는 하위 단계가 상위 단계 성공에 의존하기 때문이다.

## 2.5 Failure Classification Algorithm

> auto-fix는 failure를 분류해야 rule을 선택할 수 있다.
> 아래 알고리즘이 classify_failures()의 구현 계약이다.

### 입력

- `build_output: str` — tsc/vite build 출력
- `lint_output: str` — eslint 출력
- `runtime_log: str` — console capture (Playwright)
- `visual_report: VisualReport` — screenshot diff 결과

### Failure Taxonomy

| Family | ID | Trigger Pattern | Severity |
| --- | --- | --- | --- |
| build | `BUILD-001` | `vite build` exit code ≠ 0, 원인 불명 | critical |
| build | `BUILD-002` | `Cannot find module` / `Module not found` | error |
| build | `BUILD-003` | `SyntaxError` / `Unexpected token` | error |
| type | `TYPE-001` | `Type '...' is not assignable to type '...'` | error |
| type | `TYPE-002` | `Property '...' does not exist on type` | error |
| type | `TYPE-003` | `'...' is possibly 'undefined'` / `'null'` | error |
| type | `TYPE-004` | `Cannot find name '...'` | error |
| lint | `LINT-001` | `'...' is defined but never used` | warning |
| lint | `LINT-002` | naming convention violation | warning |
| runtime | `RUNTIME-001` | `Cannot read properties of undefined/null` | critical |
| runtime | `RUNTIME-002` | `Unhandled promise rejection` | critical |
| runtime | `RUNTIME-003` | React hook violation / render loop | error |
| visual | `VISUAL-001` | SSIM < threshold | error |
| visual | `VISUAL-002` | critical region missing | critical |
| visual | `VISUAL-003` | changed pixel ratio > threshold (but critical regions OK) | warning |

### Classification 알고리즘

```python
# src/ddk/services/failure_classifier.py

import re
from ddk.models.validation import FailureRecord

# Pattern → (family, taxonomy_id, severity)
BUILD_PATTERNS: list[tuple[str, str, str, str]] = [
    (r"Cannot find module|Module not found", "build", "BUILD-002", "error"),
    (r"SyntaxError|Unexpected token", "build", "BUILD-003", "error"),
]
TYPE_PATTERNS: list[tuple[str, str, str, str]] = [
    (r"is not assignable to type", "type", "TYPE-001", "error"),
    (r"does not exist on type", "type", "TYPE-002", "error"),
    (r"is possibly '(?:undefined|null)'", "type", "TYPE-003", "error"),
    (r"Cannot find name", "type", "TYPE-004", "error"),
]
LINT_PATTERNS: list[tuple[str, str, str, str]] = [
    (r"is defined but never used", "lint", "LINT-001", "warning"),
    (r"naming convention", "lint", "LINT-002", "warning"),
]
RUNTIME_PATTERNS: list[tuple[str, str, str, str]] = [
    (r"Cannot read properties of (?:undefined|null)", "runtime", "RUNTIME-001", "critical"),
    (r"Unhandled promise rejection", "runtime", "RUNTIME-002", "critical"),
    (r"rendered more hooks|hook order", "runtime", "RUNTIME-003", "error"),
]

def classify_failures(
    build_output: str,
    lint_output: str,
    runtime_log: str,
    visual_report: "VisualReport",
) -> list[FailureRecord]:
    """모든 검증 출력을 분석하여 안정된 taxonomy로 분류."""
    failures: list[FailureRecord] = []

    for patterns, source in [
        (BUILD_PATTERNS, build_output),
        (TYPE_PATTERNS, build_output),
        (LINT_PATTERNS, lint_output),
        (RUNTIME_PATTERNS, runtime_log),
    ]:
        for pattern, family, taxonomy_id, severity in patterns:
            matches = re.findall(pattern, source)
            if matches:
                failures.append(FailureRecord(
                    family=family,
                    taxonomy_id=taxonomy_id,
                    severity=severity,
                    count=len(matches),
                    sample_message=matches[0][:200],
                ))

    # Visual failures from report
    if visual_report.ssim < visual_report.ssim_threshold:
        failures.append(FailureRecord(
            family="visual", taxonomy_id="VISUAL-001",
            severity="error", count=1,
            sample_message=f"SSIM {visual_report.ssim:.4f} < {visual_report.ssim_threshold}",
        ))
    if visual_report.missing_critical_regions:
        failures.append(FailureRecord(
            family="visual", taxonomy_id="VISUAL-002",
            severity="critical", count=len(visual_report.missing_critical_regions),
            sample_message=f"Missing: {', '.join(visual_report.missing_critical_regions[:3])}",
        ))
    if visual_report.changed_pixel_ratio > visual_report.changed_pixel_max_ratio:
        if not visual_report.missing_critical_regions:
            failures.append(FailureRecord(
                family="visual", taxonomy_id="VISUAL-003",
                severity="warning", count=1,
                sample_message=f"Pixel ratio {visual_report.changed_pixel_ratio:.4f}",
            ))

    # Build catch-all
    if not any(f.family == "build" for f in failures) and "exit code" in build_output.lower():
        failures.append(FailureRecord(
            family="build", taxonomy_id="BUILD-001",
            severity="critical", count=1,
            sample_message="Build failed with unknown cause",
        ))

    return failures
```

### 테스트 요구사항

- `test_classify_build_import_error.py` — "Cannot find module" → BUILD-002
- `test_classify_type_prop_mismatch.py` — "is not assignable" → TYPE-001
- `test_classify_runtime_null.py` — "Cannot read properties" → RUNTIME-001
- `test_classify_visual_ssim.py` — SSIM 미달 → VISUAL-001
- `test_classify_multiple_families.py` — 복합 실패 시 모든 family 포착
- `test_classify_build_catch_all.py` — 패턴 매칭 실패 시 BUILD-001 fallback

---

## 3. Repair Rule Catalog (P0)

| Rule ID | Trigger Predicate | 대상 Taxonomy | 허용 Patch Scope | Prompt Augmentation | 검증 재실행 |
|---|---|---|---|---|---|
| `FX-BUILD-IMPORT-001` | `"Cannot find module"` 또는 `"Module not found"` | `BUILD-002`, `TYPE-004` | import path, export name, same-feature barrel file | "새 dependency 추가 금지. import/export 경로와 심볼명만 맞춰라." | build → type → lint |
| `FX-BUILD-SYNTAX-001` | 파서/문법 오류가 단일 파일에 집중 | `BUILD-003` | 해당 파일 문법 복구만 허용 | "구조 변경 금지. 구문 오류만 고쳐라." | build |
| `FX-TYPE-PROP-001` | prop mismatch / missing required prop | `TYPE-001`, `TYPE-002` | caller/callee 2파일 이내 prop 이름·타입 정렬 | "props contract를 최소 수정으로 맞춰라. 새 public API 추가 금지." | type → build → lint |
| `FX-TYPE-NULL-001` | undefined variable / nullable misuse | `TYPE-003`, `TYPE-001` | default init, guard clause, optional chaining | "state 초기화 또는 null guard만 허용. 의미 변경 금지." | type → build → runtime |
| `FX-LINT-CLEANUP-001` | unused import, naming drift, trivial style | `LINT-001`, `LINT-002` | import cleanup, rename in local scope, formatting-safe edits | "business logic 건드리지 말고 lint만 정리해라." | lint |
| `FX-RUNTIME-NULL-001` | `Cannot read properties of undefined/null` | `RUNTIME-001`, `RUNTIME-003` | state init, guard, fallback render | "null/undefined 접근만 막아라. API 의미 변경 금지." | runtime → visual |
| `FX-RUNTIME-LIFECYCLE-001` | render loop/effect dependency/hook misuse | `RUNTIME-003` | hook deps, effect guard, derived state correction | "hook 규칙 위반과 lifecycle 문제만 수정해라." | runtime → build → lint |
| `FX-VISUAL-SPACING-001` | critical region은 유지되나 spacing/token drift 존재 | `VISUAL-003` | TSX/CSS 내 spacing, color, typography token 치환 | "레이아웃 구조는 유지하고 token usage만 맞춰라." | visual |
| `FX-VISUAL-HIERARCHY-001` | CTA/hero/form/nav missing or hierarchy broken | `VISUAL-001`, `VISUAL-002` | wrapper/div hierarchy, missing region restore, className alignment | "critical region을 복원하되 business logic은 건드리지 말라." | visual → runtime |

### 3.1 Rule 선택 tie-break

동일 severity, 동일 family에서 여러 rule이 후보면 다음 순서로 선택한다.

1. 더 적은 파일을 수정하는 rule
2. 더 적은 validation stage를 재실행하는 rule
3. `Rule ID` lexical order

이 tie-break는 반드시 deterministic 해야 한다.

---

## 4. AutoFixPlanner 알고리즘

```python
class AutoFixPlanner:
    def select_rule(self, failures: list[FailureRecord], prior_attempts: list[FixAttempt]) -> FixRulePlan:
        families = classify_failures(failures)
        ordered = sort_families(
            families,
            family_order=["build", "type", "lint", "runtime", "visual"],
            severity_order=["critical", "error", "warning"],
        )

        primary_family = ordered[0]
        candidate_rules = RULES_BY_FAMILY[primary_family.name]
        candidate_rules = [r for r in candidate_rules if r.matches(primary_family)]
        candidate_rules = exclude_repeated_no_improvement(candidate_rules, prior_attempts)

        if not candidate_rules:
            raise ManualReviewRequired("No deterministic fix rule matched")

        selected = sorted(candidate_rules, key=lambda r: r.tie_break_key())[0]

        if selected.requires_config_change or selected.max_files > 3:
            raise ManualReviewRequired("Patch exceeds safe repair scope")

        return FixRulePlan(
            rule_id=selected.rule_id,
            target_files=selected.infer_target_files(primary_family),
            prompt_bullets=selected.prompt_bullets(primary_family),
            rerun_stages=selected.rerun_stages,
        )
```

### 4.1 Rotation 규칙

- 동일 `rule_id` + 동일 `context_pack_hash` + `result=no_change` 가 2회 연속이면 같은 rule 재사용 금지
- alternative rule이 없으면 즉시 `manual-review-required`
- visual rule 적용 후 runtime regression이 생기면 즉시 rollback 후 다른 visual rule을 시도하지 않고 종료

---

## 5. Failure Family별 상세 규칙

### 5.1 Build / Import

수정 허용:

- 상대/절대 import 경로 수정
- named/default export 이름 정렬
- barrel file re-export 누락 보완

수정 금지:

- 패키지 설치
- alias config 추가
- tsconfig path mapping 도입

### 5.2 Type

수정 허용:

- local type annotation 보완
- prop 이름/shape 정렬
- optional field defaulting

수정 금지:

- public schema 의미 변경
- 광범위한 generic refactor

### 5.3 Lint

수정 허용:

- unused import 제거
- local rename
- safe formatting

수정 금지:

- lint를 피하기 위한 logic 삭제

### 5.4 Runtime

수정 허용:

- null guard
- state initializer
- fallback render
- effect dependency correction

수정 금지:

- API 호출 제거
- business flow 변경

### 5.5 Visual

수정 허용:

- spacing/token/className 조정
- wrapper hierarchy 복원
- critical region 재삽입

수정 금지:

- semantic component 삭제
- major layout redesign

---

## 6. Manual Review Escalation

아래 중 하나라도 만족하면 auto-fix는 종료한다.

1. rule match 없음
2. 같은 family의 critical failure가 2개 이상 충돌
3. config/dependency/schema 수정 필요
4. 변경 파일 3개 초과 예상
5. 변경 라인 120 초과 예상
6. rollback verification 실패
7. visual fix가 runtime regression을 유발

---

## 7. Required Artifacts

각 auto-fix 시도는 최소 아래를 남겨야 한다.

- `rule_id`
- matched `taxonomy_ids`
- `target_files`
- `allowed_operations`
- `forbidden_operations`
- `prompt_bullets`
- `rerun_stages`
- `why_not_other_rules`

---

## 8. 테스트 요구사항

### Unit

- `test_auto_fix_rule_selection.py`
- `test_auto_fix_rule_guardrails.py`
- `test_auto_fix_tie_break.py`
- `test_auto_fix_manual_review_escalation.py`

### Integration

- `test_auto_fix_build_import_rule.py`
- `test_auto_fix_runtime_null_rule.py`
- `test_auto_fix_visual_spacing_rule.py`
- `test_auto_fix_rule_rotation.py`

### E2E

- `E2E-02 runtime failure -> auto-fix -> pass`
- `E2E-04 retry budget exhausted -> manual review`

---

## 9. 설계 결론

이 문서의 목적은 auto-fix를 "AI가 알아서 대충 고치는 단계" 에서
**제한된 규칙 엔진 + bounded retries** 로 내리는 것이다.

이 규칙이 구현되면 남은 불확실성은 모델 품질이 아니라
fixture coverage와 rule precision으로 축소된다.
