# Context Pack Determinism & Edge-case Operations

> `ContextPackBuilder` 를 구현 가능한 수준으로 고정하는 운영 명세.
> 이 문서가 없으면 `04-system-design.md` 의 6 files / 300 lines 규칙은 edge case에서 구현자 재량이 너무 커진다.

---

## 1. 목적

`context pack` 은 LLM 호출의 입력 품질을 결정한다.

따라서 목표는 단순하다:

1. **동일 입력이면 동일 pack**
2. **budget 초과 시 예측 가능한 축소**
3. **중요 컨텍스트 손실 시 조용히 진행하지 않고 명시적 downgrade**

---

## 2. 불변 조건 (Invariants)

- 최대 파일 수: `6`
- 최대 총 라인 수: `300`
- 각 target file은 최소 `P1` 또는 `P2` 컨텍스트 1개 이상 확보
- tie-break는 항상 deterministic
- hash는 선택된 chunk manifest를 포함
- `insufficient_context=true` 인 pack으로는 `generate` 를 계속하지 않는다

---

## 3. Candidate Ranking

### 3.1 우선순위 계층

| Priority | 의미 |
|---|---|
| `P1` | IntentGraph가 직접 참조한 파일 |
| `P2` | target file과 같은 feature/디렉토리의 sibling |
| `P3` | repo canonical example |
| `P4` | design token/theme source |
| `P5` | shared types/utilities |

### 3.2 정렬 키

후보 파일은 아래 tuple로 오름차순 정렬한다.

```python
sort_key = (
    priority_rank,         # P1=1 ... P5=5
    relation_rank,         # exact symbol match=1, same dir sibling=2, shared support=3
    line_bucket,           # ceil(total_lines / 50)
    normalized_path,       # lexical
)
```

`normalized_path` 까지 포함해야 같은 score에서 비결정론이 없다.

---

## 파일 타입별 Priority 매핑 테이블

context pack 빌더는 아래 우선순위 규칙에 따라 파일을 선택한다.
budget(300 lines) 초과 시 낮은 priority 파일부터 제외한다.
동일 priority 내에서는 파일 경로의 lexicographic 순서로 정렬한다.

| Priority | 파일 패턴 | 이유 |
|----------|-----------|------|
| P1 (최고) | `src/App.tsx`, `src/App.jsx`, `src/main.tsx`, `src/main.jsx` | 진입점 — 컴포넌트 트리 루트 |
| P1 | `src/index.tsx`, `src/index.jsx` | 또 다른 진입점 패턴 |
| P1 | `package.json` | 의존성/스크립트 — 빌드 도구 파악 필수 |
| P2 (높음) | `tsconfig.json`, `tsconfig.*.json` | TypeScript 설정 — import 경로 해석 |
| P2 | `vite.config.ts`, `vite.config.js` | 빌드 설정 — alias/plugin 파악 |
| P2 | 실패한 파일 (runtime/type/lint 오류가 발생한 파일) | auto_fix 대상 — 반드시 포함 |
| P3 (중간) | `src/**/*.tsx`, `src/**/*.jsx` (import된 컴포넌트) | 직접 import된 컴포넌트 |
| P3 | `src/**/*.ts`, `src/**/*.js` (import된 유틸) | 직접 import된 유틸 |
| P3 | `src/types/*.ts`, `src/types.ts` | 타입 정의 |
| P4 (낮음) | `src/**/*.css`, `src/**/*.module.css` | 스타일 — 타입 오류와 무관 |
| P4 | `src/**/*.scss`, `src/**/*.sass` | 스타일 전처리기 |
| P4 | `*.config.js`, `*.config.ts` (기타) | 기타 설정 파일 |
| P5 (최저) | `README.md`, `*.md` | 문서 — 코드 생성에 참조용 |
| P5 | `public/**` | 정적 자산 — 코드 생성에 거의 불필요 |

### 특수 규칙

1. **실패 파일 강제 포함**: P2 우선순위에 있는 "실패한 파일"은 budget 부족 시에도 P1 파일 다음으로 반드시 포함한다.
2. **동적 우선순위 승격**: auto_fix 재시도 시 이전 시도에서 수정된 파일은 P1으로 임시 승격한다.
3. **최대 파일 수**: P 우선순위와 무관하게 최대 6개 파일만 포함 (budget 내라도 초과 불가).
4. **`node_modules` 제외**: 어떤 priority도 `node_modules/**` 파일을 포함하지 않는다.
5. **binary 파일 제외**: `.png`, `.jpg`, `.gif`, `.woff`, `.ttf` 등 바이너리 파일은 제외한다.

---

## 4. Chunking Rules

### 4.1 기본 chunk 순서

각 파일은 아래 순서대로 chunk를 만든다.

1. import block
2. referenced symbol definition window (`±20 lines`)
3. exported type/interface definitions
4. file synopsis block

### 4.2 Oversize File 처리

#### Case A. 단일 P1 파일이 300줄 초과

전체 파일을 넣지 않는다. 대신:

- import block
- referenced symbol windows
- top-level exported types used by the target
- `synopsis`:
  - path
  - exported symbols
  - component/file purpose 1~2줄

이렇게 줄였는데도 `120 lines` 를 넘으면 `synopsis + 1 symbol window` 만 유지한다.

#### Case B. target file이 4개 이상

`GenerationPlan` 을 먼저 split 한다.

- 한 generation node는 최대 `3 target_files`
- 그 이상이면 `plan` 단계에서 node 분할
- `ContextPackBuilder` 가 이를 보정하지 않는다

#### Case C. P1/P2 없음

- `insufficient_context=true`
- `missing_context_for=[target_file,...]`
- pipeline route: `manual-review-required`

---

## 5. Budget Allocation

### 5.1 Multi-target budget

target file이 여러 개인 경우 budget을 균등하게 쓰지 않는다.

- target별 local budget: `최대 2 files / 90 lines`
- shared/global budget: `최대 2 files / 120 lines`

즉 전체는 다음 구조를 가진다.

```
target A local
target B local
target C local
shared examples/tokens/types
```

### 5.2 Drop 순서

300줄 초과 시 다음 순서로 축소한다.

1. `P5` 전체 제거
2. `P4` synopsis-only로 축소
3. `P3` symbolic chunk만 유지
4. `P2` sibling file 중 line_bucket 큰 파일 제거
5. `P1` 은 제거하지 않고 synopsis-only로 축소

`P1` 이 전부 사라지는 상황은 허용하지 않는다.

---

## 6. Manifest & Hash

### 6.1 ContextPackManifest

```json
{
  "node_name": "generate",
  "target_files": ["src/App.tsx"],
  "chunks": [
    {
      "path": "src/components/Button.tsx",
      "priority": "P2",
      "start_line": 1,
      "end_line": 38,
      "content_sha256": "..."
    }
  ],
  "insufficient_context": false
}
```

### 6.2 Hash 입력

`context_pack_hash` 는 아래를 canonical JSON으로 직렬화해 계산한다.

- node_name
- target_files
- prompt_version
- chunk manifest (`path`, `priority`, `start_line`, `end_line`, `content_sha256`)

실제 code text를 직접 넣지 않고 `content_sha256` 를 넣어도 된다.
중요한 것은 동일 manifest면 동일 hash여야 한다는 점이다.

### 6.3 Collision fallback

SHA 충돌은 실질적으로 무시 가능하지만, 구현 계약은 아래와 같다.

- hash 동일
- 하지만 manifest 비교 결과 다름

이면 최종 hash는 아래로 재계산한다.

`sha256(base_hash + manifest_sha256)[:16]`

---

## 7. Edge-case Matrix

| Edge Case ID | 상황 | 처리 |
|---|---|---|
| `CP-001` | single P1 file > 300 lines | symbol window + synopsis only |
| `CP-002` | target_files > 3 | `plan` 단계에서 node split |
| `CP-003` | P1/P2 후보 없음 | insufficient_context → manual review |
| `CP-004` | 모든 후보가 매우 큼 | P1 유지, 나머지 synopsis-only |
| `CP-005` | 동일 rank 후보 다수 | lexical path tie-break |
| `CP-006` | chunk 후에도 300 lines 초과 | P5→P4→P3→P2 순 축소 |
| `CP-007` | hash 같지만 manifest 다름 | salted hash fallback |

---

## 8. Pipeline Contract

`generate` 노드는 아래 상태값을 반드시 읽는다.

- `context_pack_hash`
- `context_pack_manifest_ref`
- `insufficient_context`

라우팅 규칙:

- `insufficient_context=false` → generate 진행
- `insufficient_context=true` → `manual-review-required`

즉 정보가 부족한데도 "그냥 생성해 보기"는 금지다.

---

## 9. 테스트 요구사항

### Unit

- `test_context_pack_priority_order.py`
- `test_context_pack_edge_cases.py`
- `test_context_pack_manifest_hash.py`
- `test_context_pack_budget_drop_order.py`

### Integration

- `test_context_pack_with_large_fixture_repo.py`
- `test_context_pack_multi_target_split.py`
- `test_generate_blocked_on_insufficient_context.py`

---

## Code Normalization Rules

> `normalize` 노드가 생성 코드를 target repo conventions에 맞추는 규칙 목록.
> 이 규칙 없이는 04-system-design.md의 normalizer가 구현 불가.

### Normalization 단계

1. **Import Ordering** — target repo의 import convention 감지 후 적용
2. **Path Aliasing** — tsconfig paths/aliases에 맞게 import 경로 변환
3. **Naming Convention** — component/function/variable 명명 규칙 정렬
4. **File Placement** — target repo의 디렉토리 구조에 맞게 파일 위치 조정
5. **Style System** — CSS modules / Tailwind / styled-components 감지 후 변환
6. **Barrel Export** — index.ts re-export 패턴이 있으면 신규 컴포넌트 등록

### 규칙 적용 우선순위

| 우선순위 | 규칙 | 감지 방법 | 실패 시 |
| --- | --- | --- | --- |
| 1 | ESLint/Prettier config | `.eslintrc*`, `.prettierrc*` 파싱 | 기본 규칙 사용 |
| 2 | tsconfig paths | `tsconfig.json` `paths` 필드 | 상대 경로 유지 |
| 3 | Import convention | 기존 파일 5개 샘플링 → 패턴 추출 | 알파벳순 |
| 4 | Naming convention | 기존 컴포넌트 5개 샘플링 → PascalCase/camelCase 확인 | PascalCase |
| 5 | Style system | package.json deps + 기존 파일 확인 | CSS modules |
| 6 | Barrel exports | 기존 index.ts 유무 확인 | 스킵 |

### NormalizationProfile 모델

```python
# src/ddk/models/normalization.py

from pydantic import BaseModel
from enum import Enum

class StyleSystem(str, Enum):
    CSS_MODULES = "css-modules"
    TAILWIND = "tailwind"
    STYLED_COMPONENTS = "styled-components"
    VANILLA_CSS = "vanilla-css"
    UNKNOWN = "unknown"

class NamingConvention(str, Enum):
    PASCAL_CASE = "PascalCase"
    CAMEL_CASE = "camelCase"
    KEBAB_CASE = "kebab-case"

class NormalizationProfile(BaseModel):
    """target repo에서 감지된 코드 컨벤션 프로파일."""
    import_order_tool: str | None = None  # "eslint-plugin-import" | None
    path_aliases: dict[str, str] = {}      # {"@/": "src/"}
    component_naming: NamingConvention = NamingConvention.PASCAL_CASE
    file_naming: NamingConvention = NamingConvention.KEBAB_CASE
    style_system: StyleSystem = StyleSystem.UNKNOWN
    has_barrel_exports: bool = False
    formatter_config_path: str | None = None
    linter_config_path: str | None = None
```

### 테스트 요구사항

- `test_normalization_profile_detection.py` — fixture repo에서 프로파일 감지
- `test_import_rewriting.py` — path alias 적용 확인
- `test_style_system_detection.py` — Tailwind/CSS modules 감지
- `test_barrel_export_registration.py` — 새 컴포넌트 barrel 등록

---

## 10. 설계 결론

이 문서로 `ContextPackBuilder` 의 핵심 판단은 더 이상 "좋은 감각" 의 문제가 아니다.

남는 것은 fixture coverage뿐이며, 같은 입력에서 다른 pack이 나오는 문제는
설계상 허용되지 않는다.
