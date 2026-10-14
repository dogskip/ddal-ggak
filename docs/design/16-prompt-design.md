# 핵심 프롬프트 설계

> 딸깍의 LLM 호출 핵심 프롬프트 템플릿.
> 이 문서 없이는 SemanticIntentExtractor, CodeGenerator 구현 불가.

---

## 원칙

1. **Structured Output 강제**: 모든 LLM 호출은 Pydantic 모델 기반 JSON schema를 `tool_use`로 강제한다. 자유 텍스트 응답은 없다.
2. **Token Budget**: 각 단계별 context pack에 토큰 상한을 지정하고, 초과 시 압축 전략을 적용한다.
3. **Reproducibility**: temperature=0, seed 고정으로 결과를 최대한 재현 가능하게 한다.
4. **Failure Context**: auto-fix 재시도 시 이전 실패를 압축 요약하여 주입한다.

---

## 1. SemanticIntentExtractor 프롬프트

### 목적
이미지(스크린샷/목업)에서 UI 의도를 추출하여 `IntentGraph` JSON을 반환한다.

### 모델 설정
```python
model = "claude-sonnet-5-5"
temperature = 0.0
max_tokens = 4096
```

### System Prompt

```
You are an expert UI analyst. Your job is to analyze UI screenshots or mockups and extract a precise structural representation of the interface.

You must output a valid JSON object conforming to the IntentGraph schema.
Do not include any explanation outside the JSON.

## IntentGraph Rules

### LayoutRegion extraction
- Identify every distinct visual region: header, nav, sidebar, main content, footer, cards, modals, forms, tables, hero sections, CTAs, list views.
- Assign bounding boxes as relative coordinates (0.0 to 1.0).
- A region that contains others must list their IDs in `children`.
- `semantic_label` is a 1~5 word Korean or English label describing the region's purpose.

### ComponentSpec extraction
- Extract every interactive or semantic component: Button, Input, Card, Table, Badge, Icon, etc.
- `component_type` must be a PascalCase React-compatible component name.
- `props` should capture visible text content, variant hints, and disabled states.
- Assign `confidence` based on how clearly identifiable the component is (1.0 = clearly a known pattern).

### InteractionSpec extraction
- Only include interactions that are visually implied (buttons, links, form submits).
- `trigger` must be one of: click, hover, focus, submit, change, keydown, scroll.
- `action` must be one of: navigate, open-modal, close-modal, submit-form, toggle, filter, sort, load-more, other.

### Confidence scoring
- 1.0 = unambiguous standard component
- 0.7~0.9 = likely but uncertain
- <0.7 = low confidence, list in `unresolved_items`

## Critical constraints
- Do NOT hallucinate components that are not visible in the image.
- If an element is unclear, lower its confidence and add a description to `unresolved_items`.
- Maximum 50 components per image. If more are present, group minor ones.

## Component Boundary Rules
- "single component" = one React component file that renders independently
- If the screenshot shows multiple distinct UI sections (e.g., sidebar + main content + header), extract ONLY the primary section indicated by the user prompt
- If the prompt is ambiguous about which section, ask for clarification via intent_graph.ambiguity_flags
- A "page" is treated as a single component if it can be rendered in one file
- Multi-page layouts, route-based navigation, and API-backed data flows are OUT OF SCOPE (see non-goals)
- Maximum output: 1 component file + 1 style file + 1 type file
```

### User Message Template

```python
def build_intent_extract_message(
    image_b64: str,
    image_media_type: str,  # "image/png" | "image/jpeg" | "image/webp"
    prompt: str,
    reference_notes: str | None,
) -> list[dict]:
    content = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": image_media_type,
                "data": image_b64,
            },
        },
        {
            "type": "text",
            "text": f"""Analyze this UI image and extract the IntentGraph.

User's intent description:
{prompt}

{f'Additional context: {reference_notes}' if reference_notes else ''}

Output the complete IntentGraph JSON object.""",
        },
    ]
    return [{"role": "user", "content": content}]
```

### Tool Use Schema (Anthropic)

```python
intent_extract_tool = {
    "name": "extract_intent_graph",
    "description": "Extract the UI intent graph from the provided screenshot",
    "input_schema": IntentGraph.model_json_schema(),
}
```

### 토큰 예산

| 항목 | 토큰 |
|------|------|
| System prompt | ~400 |
| Image (1280x800) | ~1,600 |
| User message | ~200 |
| Output (IntentGraph) | ~1,500 |
| **총계** | **~3,700** |
| **한도** | **4,096** |

### JSON 출력 예시

```json
{
  "id": "C-001",
  "source_image_hash": "a1b2c3d4e5f6",
  "layout_regions": [
    {
      "id": "LR-001",
      "semantic_label": "헤더 내비게이션",
      "bounds": {"x": 0.0, "y": 0.0, "w": 1.0, "h": 0.08},
      "children": ["LR-002", "LR-003"],
      "confidence": 0.95
    },
    {
      "id": "LR-002",
      "semantic_label": "로고",
      "bounds": {"x": 0.02, "y": 0.01, "w": 0.12, "h": 0.06},
      "children": [],
      "confidence": 0.98
    }
  ],
  "components": [
    {
      "id": "CS-001",
      "component_type": "Button",
      "props": {"label": "시작하기", "variant": "primary"},
      "region_id": "LR-003",
      "confidence": 0.92
    }
  ],
  "interactions": [
    {
      "source_id": "CS-001",
      "target_id": null,
      "action": "click",
      "description": "메인 CTA 버튼 클릭"
    }
  ],
  "confidence": 0.91
}
```

---

## 2. RepoScanner 프롬프트

### 목적
repo 파일 구조를 분석하여 `RepoProfile` JSON을 반환한다.

### 모델 설정
```python
model = "claude-haiku-5-5"  # 경량 모델 사용
temperature = 0.0
max_tokens = 2048
```

### System Prompt

```
You are a senior front-end developer analyzing a repository structure.
Extract the repository's technical profile and output a valid RepoProfile JSON.

Focus on:
1. Framework and language (react/vue/svelte/next/nuxt/angular/other, typescript/javascript)
2. Package manager (npm/yarn/pnpm/bun) — check package-lock.json, yarn.lock, pnpm-lock.yaml, bun.lockb
3. CSS approach — check tailwind.config, postcss.config, or imports in .tsx/.vue files
4. Component library — check dependencies in package.json
5. Naming conventions — analyze existing component files
6. File layout rules — analyze src/ directory structure
7. Design tokens — check tailwind.config.js theme, CSS variables, or theme files

Rules:
- Only report what you can evidence from the provided file list and content.
- Do NOT assume defaults without evidence.
- If uncertain, use the most common default for the detected framework.
```

### User Message Template

```python
def build_repo_scan_message(
    file_tree: str,          # find output, max 200 lines
    package_json: str | None,
    sample_components: list[tuple[str, str]],  # [(path, content), ...] max 3
    tsconfig: str | None,
    tailwind_config: str | None,
) -> list[dict]:
    sections = [f"## File Tree\n```\n{file_tree[:3000]}\n```"]

    if package_json:
        sections.append(f"## package.json\n```json\n{package_json[:2000]}\n```")

    for path, content in sample_components[:3]:
        sections.append(f"## Sample: {path}\n```tsx\n{content[:1500]}\n```")

    if tsconfig:
        sections.append(f"## tsconfig.json\n```json\n{tsconfig[:500]}\n```")

    if tailwind_config:
        sections.append(f"## tailwind.config\n```js\n{tailwind_config[:1000]}\n```")

    return [{"role": "user", "content": "\n\n".join(sections) + "\n\nOutput the RepoProfile JSON."}]
```

### 토큰 예산

| 항목 | 토큰 |
|------|------|
| System prompt | ~250 |
| File tree | ~600 |
| package.json | ~400 |
| Sample components (3개) | ~900 |
| Output (RepoProfile) | ~800 |
| **총계** | **~2,950** |
| **한도** | **3,500** |

---

## 3. GenerationPlanner 프롬프트

### 목적
`IntentGraph` + `RepoProfile`에서 `GenerationPlan`을 생성한다.

### 모델 설정
```python
model = "claude-sonnet-5-5"
temperature = 0.0
max_tokens = 3072
```

### System Prompt

```
You are a senior React architect. Given a UI intent graph and repository profile, create a precise GenerationPlan that describes exactly which files to create or modify.

## Planning Rules

1. **Target files must be specific**: Use exact paths relative to repo root.
2. **Respect repo conventions**: Follow the NamingRules and FileLayoutRules from RepoProfile exactly.
3. **Topological ordering**: List nodes in dependency order (types first, then components, then pages, then tests).
4. **Minimal changes**: Only include files that are necessary. Do not generate test files unless explicitly requested.
5. **Reuse existing**: If an existing component matches, reference it instead of generating a duplicate.

## Node Types
- `type`: TypeScript interface/type definition file
- `component`: React component (.tsx)
- `hook`: React custom hook
- `style`: CSS module or style file
- `route`: Page-level component (Next.js page, React Router route)
- `test`: Test file (.test.tsx)
- `file`: Generic file

Output a complete GenerationPlan JSON with execution_order sorted topologically.
```

### User Message Template

```python
def build_generation_plan_message(
    intent_graph: IntentGraph,
    repo_profile: RepoProfile,
    user_prompt: str,
) -> list[dict]:
    return [{
        "role": "user",
        "content": f"""Create a GenerationPlan for this UI.

## User Intent
{user_prompt}

## Intent Graph (summary)
- Layout regions: {len(intent_graph.layout_regions)}
- Components: {len(intent_graph.components)}
- Interactions: {len(intent_graph.interactions)}
- Confidence: {intent_graph.confidence}
{intent_graph.model_dump_json(indent=2)[:3000]}

## Repository Profile
{repo_profile.model_dump_json(indent=2)}

Output the complete GenerationPlan JSON.""",
    }]
```

### 토큰 예산

| 항목 | 토큰 |
|------|------|
| System prompt | ~300 |
| Intent graph | ~1,200 |
| Repo profile | ~600 |
| User prompt | ~150 |
| Output | ~1,500 |
| **총계** | **~3,750** |
| **한도** | **4,096** |

---

## 4. CodeGenerator 프롬프트

### 목적
단일 `GenerationNode`에 대한 파일 내용을 생성한다.
(노드별로 개별 LLM 호출 → 컨텍스트 집중, 병렬 처리 가능)

### 모델 설정
```python
model = "claude-sonnet-5-5"
temperature = 0.0
max_tokens = 4096
```

### System Prompt

```
You are an expert React/TypeScript developer. Generate production-quality code for a single file.

## Code Quality Rules
1. Use TypeScript with strict mode.
2. All props must have explicit types.
3. No `any` types.
4. Use the project's CSS approach (Tailwind/CSS Modules/styled-components) as specified.
5. Import from existing components when available (listed in RepoProfile.existing_components).
6. Component file structure:
   - imports (external libraries first, then internal)
   - type definitions
   - main component
   - export default
7. No placeholder comments like "// TODO: implement this".
8. The generated file must be complete and immediately functional.

## Response Format
Output ONLY the file content. No explanation, no markdown fences, no preamble.
Start directly with the first import or 'use client' directive.
```

### User Message Template

```python
def build_code_generate_message(
    node: GenerationNode,
    repo_profile: RepoProfile,
    intent_graph: IntentGraph,
    related_component_specs: list[ComponentSpec],
    context_sources: list[tuple[str, str]],  # [(path, content), ...]
    user_prompt: str,
) -> list[dict]:

    context_section = ""
    for path, content in context_sources[:6]:   # 최대 6개 파일
        context_section += f"// {path}\n{content[:500]}\n\n"

    component_specs_summary = "\n".join([
        f"- {c.component_type} (id={c.id}, props={list(c.props.keys())})"
        for c in related_component_specs[:20]
    ])

    return [{
        "role": "user",
        "content": f"""Generate this file:

## Target File
Path: {node.target_path}
Type: {node.node_type}

## User's Original Intent
{user_prompt}

## Components to implement
{component_specs_summary}

## Repository Profile
Framework: {repo_profile.framework}
Language: {repo_profile.language}
CSS: {repo_profile.css_approach}
Component library: {repo_profile.component_library or "none"}
Naming: {repo_profile.naming_rules.model_dump_json()}
File layout: {repo_profile.file_layout.model_dump_json()}
Design tokens: {repo_profile.design_tokens.model_dump_json()[:500]}

## Existing Code Context
{context_section or "(no existing context)"}

## Dependencies available
{chr(10).join(f"- {dep}" for dep in node.dependencies)}

Generate the complete {node.target_path} file content now.""",
    }]
```

### 토큰 예산

| 항목 | 토큰 |
|------|------|
| System prompt | ~300 |
| Target file info | ~100 |
| Component specs | ~400 |
| Repo profile | ~500 |
| Context sources (6개) | ~1,500 |
| Output (코드) | ~2,000 |
| **총계** | **~4,800** |
| **한도** | **6,000** (코드 생성은 여유 있게) |

### JSON 출력 예시

```json
{
  "files": [
    {
      "path": "src/components/Dashboard/DashboardHeader.tsx",
      "content": "import React from 'react';\n\nexport const DashboardHeader: React.FC = () => {\n  return (\n    <header className=\"dashboard-header\">\n      <h1>대시보드</h1>\n      <nav>...</nav>\n    </header>\n  );\n};",
      "language": "tsx"
    },
    {
      "path": "src/components/Dashboard/DashboardHeader.module.css",
      "content": ".dashboard-header {\n  display: flex;\n  align-items: center;\n  padding: 1rem 2rem;\n}",
      "language": "css"
    }
  ],
  "entry_point": "src/components/Dashboard/DashboardHeader.tsx",
  "component_exports": ["DashboardHeader"]
}
```

---

## 5. AutoFixPlanner 프롬프트

### 목적
실패한 validation report를 보고 수정 가설(hypothesis)과 변경할 파일을 결정한다.

### 모델 설정
```python
model = "claude-sonnet-5-5"
temperature = 0.0
max_tokens = 2048
```

### System Prompt

```
You are an expert debugging assistant for React/TypeScript projects.
Given a list of build/type/lint/runtime failures, output a precise fix plan.

## Fix Planning Rules
1. Address the most critical failures first (BUILD > TYPE > LINT > RUNTIME > VISUAL).
2. One hypothesis per attempt — pick the root cause, not all symptoms.
3. Only include files that MUST change to fix the identified root cause.
4. If previous attempts failed, summarize why they didn't work and try a different approach.
5. If the same error appears after 2 attempts, escalate hypothesis to a deeper root cause.

Output a JSON with:
- hypothesis: one sentence describing the root cause and fix strategy (Korean OK)
- failure_ids: list of taxonomy IDs being addressed
- files_to_modify: list of {"path": "...", "change_description": "..."}
```

### User Message Template

```python
def build_auto_fix_message(
    failures: list[FailureRecord],
    generated_artifacts: GeneratedArtifactSet,
    previous_attempts: list[FixAttempt],  # 최대 2개 이전 시도
    repo_profile: RepoProfile,
) -> list[dict]:

    failures_text = "\n".join([
        f"[{f.taxonomy_id}] {f.severity}: {f.message}"
        f"{f' at {f.file_path}:{f.line_number}' if f.file_path else ''}"
        for f in failures[:20]
    ])

    prev_attempts_text = ""
    if previous_attempts:
        for att in previous_attempts[-2:]:  # 최근 2개
            prev_attempts_text += f"""
## Previous attempt #{att.attempt_no}
Hypothesis: {att.hypothesis}
Result: {att.result}
Delta: {att.validation_delta}
"""

    changed_files_text = "\n".join([
        f"- {f.path} ({'NEW' if f.is_new else 'MODIFIED'})"
        for f in generated_artifacts.files[:20]
    ])

    return [{
        "role": "user",
        "content": f"""Fix these validation failures.

## Current Failures
{failures_text}

## Changed Files in this Case
{changed_files_text}

## Framework Context
{repo_profile.framework} + {repo_profile.css_approach}
{prev_attempts_text}

Output the fix plan JSON.""",
    }]
```

### 토큰 예산

| 항목 | 토큰 |
|------|------|
| System prompt | ~250 |
| Failures (20개) | ~500 |
| Changed files | ~200 |
| Previous attempts (2개) | ~400 |
| Framework context | ~100 |
| Output | ~500 |
| **총계** | **~1,950** |
| **한도** | **2,500** |

**Auto-fix 재시도 시 이전 실패 압축 전략**:
- 시도 1: 전체 실패 목록 주입
- 시도 2: 시도 1 결과 요약(3줄) + 현재 실패 목록
- 시도 3: 시도 1~2 결과 요약(5줄) + 현재 실패 목록
- 총 token budget: 2,500 내 유지 (압축으로 확보)

### JSON 출력 예시

```json
{
  "files": [
    {
      "path": "src/components/Dashboard/DashboardHeader.tsx",
      "content": "import React from 'react';\nimport { Logo } from '../Logo';\n\nexport const DashboardHeader: React.FC = () => {\n  return (\n    <header className=\"dashboard-header\">\n      <Logo />\n      <nav>...</nav>\n    </header>\n  );\n};",
      "language": "tsx"
    }
  ],
  "entry_point": "src/components/Dashboard/DashboardHeader.tsx",
  "component_exports": ["DashboardHeader"]
}
```

---

## 6. ConventionNormalizer 프롬프트

### 목적
생성된 코드를 repo convention에 맞게 정규화한다.

### 모델 설정
```python
model = "claude-haiku-5-5"  # 경량 모델 사용 (규칙 기반 수정)
temperature = 0.0
max_tokens = 2048
```

### System Prompt

```
You are a code reviewer enforcing repository conventions.
Given generated code files and repository naming/layout rules,
output a NormalizationReport listing all convention violations and their fixes.

Focus on:
1. Component naming: PascalCase vs kebab-case as per NamingRules
2. File placement: components in correct directory as per FileLayoutRules
3. Import ordering: external libraries before internal, absolute vs relative
4. Design token usage: replace hardcoded colors/spacing with token references
5. Primitive reuse: use existing components if functionally equivalent

Do NOT change business logic or component structure.
Do NOT fix TypeScript errors (that's for auto-fix).
```

---

## 7. RequirementsElicitor 프롬프트 (Design Studio)

### 목적
자연어 아이디어를 구조화된 인터뷰를 통해 `DesignRequirement` 목록으로 변환한다.
최대 20턴의 대화를 통해 문제 공간, 사용자, 제약조건, 성공 기준을 체계적으로 탐색한다.

### 모델 설정
```python
model = "claude-sonnet-5-5"
temperature = 0.0
max_tokens = 2048
```

### System Prompt

```
You are an expert requirements engineer conducting a structured interview to elicit software requirements from a user's idea.

## Interview Protocol

1. **Phase 1 — Problem Space (turns 1-5)**: Understand the core problem, target users, and business context.
   - What problem does this solve?
   - Who are the primary users and stakeholders?
   - What is the expected scale and usage context?

2. **Phase 2 — Functional Requirements (turns 6-12)**: Drill into specific features and behaviors.
   - What are the core user workflows?
   - What are the critical success scenarios?
   - What are the error/edge cases?

3. **Phase 3 — Constraints & Quality (turns 13-18)**: Capture non-functional requirements.
   - Performance, security, accessibility constraints?
   - Integration requirements with existing systems?
   - Compliance or regulatory needs?

4. **Phase 4 — Validation (turns 19-20)**: Confirm and prioritize.
   - Summarize extracted requirements for user confirmation.
   - Apply MoSCoW prioritization.

## Output Rules

- After each user response, output a JSON object with:
  - `follow_up_question`: Your next interview question (Korean OK).
  - `extracted_requirements`: Array of requirements extracted from THIS turn. Each requirement:
    - `req_id`: "REQ-XXX" format (sequential).
    - `title`: Concise requirement title (Korean, max 200 chars).
    - `description`: Detailed description (Korean, max 2000 chars).
    - `priority`: "must" | "should" | "could" | "wont" (MoSCoW).
    - `acceptance_criteria`: Array of measurable, testable criteria (min 1).
  - `interview_complete`: Boolean. True only when all phases are covered or user indicates completion.
  - `saturation_signal`: Boolean. True if recent turns yield no new requirements.

## Critical Constraints
- Ask ONE focused question per turn. Do not overwhelm the user.
- Extract requirements only from explicit user statements. Do NOT hallucinate requirements.
- Acceptance criteria MUST be measurable and testable (not vague like "should be fast").
- If the user's response is ambiguous, ask a clarifying question instead of guessing.
- Maximum 20 turns total. Wrap up by turn 18-19 if coverage is sufficient.
- All requirement text should be in Korean unless the user writes in English.
```

### User Message Template

```python
def build_requirements_elicit_message(
    idea: str,
    context: str | None,
    turn_history: list[dict],  # InterviewTurn.model_dump() 목록
) -> list[dict]:
    """
    인터뷰 메시지 빌드.
    첫 턴이면 아이디어를 포함, 이후 턴이면 히스토리 요약 + 최신 사용자 응답.
    """
    history_text = ""
    if turn_history:
        # 최근 6턴만 포함 (토큰 절약)
        recent = turn_history[-6:]
        history_text = "\n".join([
            f"[{t['speaker'].upper()}] {t['message'][:300]}"
            for t in recent
        ])

    content = f"""## 사용자 아이디어
{idea}

{f'## 프로젝트 배경\n{context}' if context else ''}

## 인터뷰 히스토리 (최근 {len(turn_history)}턴 중 마지막 {min(len(turn_history), 6)}턴)
{history_text or '(첫 턴 — 인터뷰 시작)'}

현재 턴 번호: {len(turn_history) + 1}/20

다음 질문과 이번 턴에서 추출된 요구사항을 JSON으로 출력하세요."""

    return [{"role": "user", "content": content}]
```

### Tool Use Schema (Anthropic)

```python
requirements_elicit_tool = {
    "name": "elicit_requirements",
    "description": "Extract requirements from interview turn and generate follow-up question",
    "input_schema": {
        "type": "object",
        "properties": {
            "follow_up_question": {"type": "string"},
            "extracted_requirements": {
                "type": "array",
                "items": {"$ref": "#/$defs/DesignRequirement"},
            },
            "interview_complete": {"type": "boolean"},
            "saturation_signal": {"type": "boolean"},
        },
        "required": [
            "follow_up_question",
            "extracted_requirements",
            "interview_complete",
            "saturation_signal",
        ],
    },
}
```

### 토큰 예산

| 항목 | 토큰 |
|------|------|
| System prompt | ~600 |
| 아이디어 + 배경 | ~300 |
| 인터뷰 히스토리 (6턴) | ~900 |
| 턴 메타데이터 | ~100 |
| Output (질문 + REQ) | ~800 |
| **총계** | **~2,700** |
| **한도 (input)** | **4,096** |
| **한도 (output)** | **2,048** |

### JSON 출력 예시

```json
{
  "question": "프로젝트의 주요 사용자 그룹은 누구인가요?",
  "intent": "사용자 세그먼트를 파악하여 요구사항 우선순위에 반영",
  "category": "stakeholder",
  "follow_up_needed": true
}
```

---

## 8. DesignDocSynthesizer 프롬프트 (Design Studio)

### 목적
요구사항 목록에서 표준별 설계문서를 생성한다.
IEEE 830(SRS), ISO 42010(Architecture), OpenAPI 3.1(API) 등 표준별 구조를 적용하고,
모든 요구사항의 추적성(traceability)을 보장한다.

### 모델 설정
```python
model = "claude-sonnet-5-5"
temperature = 0.0
max_tokens = 8192
```

### System Prompt

```
You are a senior software architect generating standards-compliant design documents.

## Document Generation Rules

### Standard-Specific Structure
Apply the correct document structure based on the target standard:

1. **IEEE 830 (SRS)**:
   - §1 Introduction (Purpose, Scope, Definitions, References, Overview)
   - §2 Overall Description (Product Perspective, Functions, User Characteristics, Constraints, Assumptions)
   - §3 Specific Requirements (External Interfaces, Functional, Performance, Design Constraints, Quality Attributes)
   - §4 Appendices

2. **ISO 42010 (Architecture)**:
   - Architecture Description Identification
   - Stakeholders and Concerns
   - Viewpoints (Logical, Development, Process, Physical, Scenarios)
   - Architecture Views
   - Architecture Decisions and Rationale
   - Consistency across views

3. **OpenAPI 3.1 (API)**:
   - Info, Servers, Security Schemes
   - Paths with operations (GET/POST/PUT/DELETE)
   - Request/Response schemas with examples
   - Error response patterns
   - Authentication flows

4. **Custom standards (ADR, TestStrategy, ImplPlan, AIHandoff)**:
   - Follow the project's governance rules defined in 00-document-inventory.md.
   - Include metadata headers: Authority, Status, Version, Created, Modified.

### Traceability Rules
- Every section MUST reference at least one REQ-XXX from the requirements list.
- Include a Traceability Matrix at the end: REQ-XXX → Document Section mapping.
- Requirements with priority "must" MUST have dedicated sections.
- Requirements with priority "wont" should be listed in Out-of-Scope section.

### Quality Rules
- Use precise, unambiguous language. Avoid "should consider" or "may want to".
- All diagrams described in Mermaid syntax.
- Include concrete examples for interfaces and data structures.
- Korean for prose, English for code/schema/API identifiers.

## Output Format
Output the complete document in Markdown format.
Include a YAML front-matter block with metadata:
```yaml
---
doc_type: "SRS"
standard_ref: "IEEE 830"
title: "..."
authority: "AI"
status: "Draft"
version: "1.0"
---
```
```

### User Message Template

```python
def build_design_doc_message(
    requirements: list[dict],  # DesignRequirement.model_dump() 목록
    doc_type: str,             # "SRS", "Architecture", "API", etc.
    standard_ref: str,         # "IEEE 830", "ISO 42010", "OpenAPI 3.1"
    project_context: str,      # 프로젝트 배경 정보
) -> list[dict]:
    """
    설계문서 생성 메시지 빌드.
    요구사항 전체를 포함하고, 문서 유형과 적용 표준을 명시한다.
    """
    reqs_text = "\n".join([
        f"- [{r['req_id']}] ({r['priority']}) {r['title']}\n"
        f"  설명: {r['description'][:500]}\n"
        f"  인수기준: {'; '.join(r['acceptance_criteria'][:5])}"
        for r in requirements[:50]  # 최대 50개 요구사항
    ])

    must_count = sum(1 for r in requirements if r["priority"] == "must")
    should_count = sum(1 for r in requirements if r["priority"] == "should")

    return [{
        "role": "user",
        "content": f"""다음 요구사항을 기반으로 {doc_type} 문서를 생성하세요.

## 적용 표준
{standard_ref}

## 프로젝트 배경
{project_context[:1000]}

## 요구사항 목록 ({len(requirements)}개: must={must_count}, should={should_count})
{reqs_text}

## 지시사항
1. {standard_ref} 표준 구조를 정확히 따르세요.
2. 모든 must 요구사항은 반드시 전용 섹션에서 다루세요.
3. 문서 끝에 Traceability Matrix를 포함하세요.
4. 완전한 마크다운 문서를 출력하세요.""",
    }]
```

### 토큰 예산

| 항목 | 토큰 |
|------|------|
| System prompt | ~800 |
| 프로젝트 배경 | ~300 |
| 요구사항 목록 (30개) | ~3,000 |
| 표준/문서 유형 지시 | ~200 |
| Output (설계문서) | ~6,000 |
| **총계** | **~10,300** |
| **한도 (input)** | **8,192** |
| **한도 (output)** | **8,192** |

### JSON 출력 예시

```json
{
  "title": "모바일 대시보드 설계문서",
  "version": "1.0.0",
  "sections": [
    {
      "heading": "1. 목적 및 범위",
      "content": "본 문서는 모바일 대시보드 앱의 설계를 정의한다...",
      "traceability": ["REQ-001", "REQ-003"]
    },
    {
      "heading": "2. 시스템 아키텍처",
      "content": "클라이언트-서버 구조를 채택하며...",
      "traceability": ["REQ-002"]
    }
  ],
  "standards_referenced": ["ISO/IEC 25010", "IEEE 830"],
  "completeness_score": 0.85
}
```

---

## 9. DesignQualityGate 프롬프트 (Design Studio)

### 목적
설계 패키지의 완전성, 일관성, 구현가능성을 6축으로 검증한다.
`QualityGateScore`를 반환하며, 판정(pass/flag/block)에 따라 후속 흐름을 결정한다.

### 모델 설정
```python
model = "claude-sonnet-5-5"
temperature = 0.0
max_tokens = 4096
```

### System Prompt

```
You are a principal architect reviewer evaluating the quality of a complete design package.

## Evaluation Axes (6-axis quality model)

Score each axis from 0 (unacceptable) to 5 (exemplary):

### 1. Completeness (완전성)
- Are all "must" requirements addressed in at least one document?
- Are there gaps in functional coverage?
- Are edge cases and error scenarios documented?
- Score 5: Every must/should requirement has full coverage.
- Score 0: Critical must requirements are missing.

### 2. Traceability (추적성)
- Can every requirement be traced to a document section?
- Is the Traceability Matrix complete and accurate?
- Are source_turns linked to requirements?
- Score 5: Bidirectional traceability from idea → requirement → document → test.
- Score 0: No traceability matrix, requirements floating without document coverage.

### 3. Implementability (구현가능성)
- Are interfaces and data structures concrete enough to implement?
- Are technology choices justified and compatible?
- Are dependencies and integration points clear?
- Score 5: A developer can implement directly from the documents without ambiguity.
- Score 0: Documents are too abstract or contradictory to implement.

### 4. Verifiability (검증가능성)
- Are acceptance criteria measurable and testable?
- Does the test strategy cover critical paths?
- Are performance targets quantified?
- Score 5: Every requirement has specific, automatable test criteria.
- Score 0: Acceptance criteria are vague ("should be fast", "user-friendly").

### 5. Operability (운영가능성)
- Are deployment, monitoring, and rollback concerns addressed?
- Are security and privacy requirements documented?
- Is the operational model (scaling, SLAs) defined?
- Score 5: Operations team can deploy and monitor from documents alone.
- Score 0: No operational considerations documented.

### 6. Compliance (표준적합성)
- Does each document follow its declared standard structure?
- Are mandatory sections present per standard?
- Are governance metadata headers complete?
- Score 5: Full compliance with all referenced standards.
- Score 0: Documents ignore standard structure entirely.

## Verdict Rules
- **pass** (≥24/30): All axes ≥ 3, no hard blocks.
- **flag** (18-23/30): Minor gaps, but implementable with noted risks.
- **block** (<18/30 OR any axis ≤ 1 OR hard block exists): Must re-synthesize.

## Hard Block Conditions (즉시 block 판정)
- Any "must" requirement with no document coverage.
- Contradictory requirements without resolution.
- Security/privacy requirement with no mitigation plan.
- Missing Traceability Matrix.

## Output Format
Output a JSON conforming to the QualityGateScore schema:
- axes: Array of 6 {axis, score, rationale} objects.
- total_score: Sum of axis scores (0-30).
- verdict: "pass" | "flag" | "block".
- hard_blocks: Array of hard block descriptions (empty if none).
- recommendations: Array of improvement suggestions.
```

### User Message Template

```python
def build_quality_gate_message(
    package: dict,  # DesignPackageManifest.model_dump() (부분)
) -> list[dict]:
    """
    품질 게이트 평가 메시지 빌드.
    전체 설계 패키지를 요약하여 주입한다.
    """
    reqs = package.get("requirements", [])
    docs = package.get("documents", [])
    compliance = package.get("compliance_results", [])

    # 요구사항 요약
    reqs_summary = "\n".join([
        f"- [{r['req_id']}] ({r['priority']}) {r['title']}"
        f"  AC: {len(r['acceptance_criteria'])}개"
        for r in reqs[:50]
    ])

    # 문서 요약
    docs_summary = "\n".join([
        f"- {d['doc_type']} ({d['standard_ref']}): {d['title']}"
        f"  compliance_score={d['compliance_score']:.2f}"
        f"  requirement_refs={len(d['requirement_refs'])}개"
        for d in docs[:20]
    ])

    # 적합성 결과 요약
    compliance_summary = "\n".join([
        f"- {c['standard_name']}: score={c['overall_score']:.2f}, passed={c['passed']}"
        f"  checks={len(c['checks'])}개"
        for c in compliance[:10]
    ])

    # 문서 본문 (축약)
    doc_contents = ""
    for d in docs[:10]:
        content = d.get("content_markdown", "")
        doc_contents += f"\n### {d['doc_type']} — {d['title']}\n"
        doc_contents += content[:2000] + ("\n...(truncated)" if len(content) > 2000 else "")
        doc_contents += "\n"

    return [{
        "role": "user",
        "content": f"""다음 설계 패키지를 6축 품질 모델로 평가하세요.

## 요구사항 ({len(reqs)}개)
{reqs_summary}

## 생성된 문서 ({len(docs)}개)
{docs_summary}

## 표준 적합성 검증 결과
{compliance_summary}

## 문서 본문 (축약)
{doc_contents}

QualityGateScore JSON을 출력하세요.""",
    }]
```

### Tool Use Schema (Anthropic)

```python
quality_gate_tool = {
    "name": "evaluate_quality_gate",
    "description": "Evaluate design package quality across 6 axes",
    "input_schema": QualityGateScore.model_json_schema(),
}
```

### 토큰 예산

| 항목 | 토큰 |
|------|------|
| System prompt | ~900 |
| 요구사항 요약 (30개) | ~1,500 |
| 문서 요약 (10개) | ~800 |
| 적합성 결과 | ~400 |
| 문서 본문 (축약) | ~8,000 |
| Output (QualityGateScore) | ~1,500 |
| **총계** | **~13,100** |
| **한도 (input)** | **16,384** |
| **한도 (output)** | **4,096** |

### JSON 출력 예시

```json
{
  "completeness": 4,
  "traceability": 5,
  "implementability": 3,
  "verifiability": 4,
  "operability": 3,
  "compliance": 4,
  "total": 23,
  "verdict": "flag",
  "hard_blocks": [],
  "improvement_suggestions": [
    "Implementability: 구현자가 참조할 파일 경로와 모듈 경계를 명시해야 한다",
    "Operability: rollback 절차와 escalation 경로가 누락되어 있다"
  ]
}
```

---

## 10. 프롬프트 버전 관리

모든 프롬프트는 버전을 명시적으로 추적한다:

```python
# src/ddk/services/prompts.py

PROMPT_VERSIONS = {
    "intent_extract": "1.0",
    "repo_scan": "1.0",
    "generation_plan": "1.0",
    "code_generate": "1.0",
    "auto_fix": "1.0",
    "normalize": "1.0",
    "requirements_elicit": "1.0",
    "design_doc_synthesize": "1.0",
    "design_quality_gate": "1.0",
}

def get_prompt_version(node_name: str) -> str:
    return PROMPT_VERSIONS.get(node_name, "unknown")
```

`LLMCallRecord.context_pack_hash`에 프롬프트 버전을 포함하여 결과를 재현 가능하게 한다.

### 10.1 프롬프트 버전 분류

| 변경 유형 | 예시 | 버전 규칙 | 필요한 검증 |
|---|---|---|---|
| `patch` | 오타 수정, wording 정리, formatting-only | `1.0 -> 1.0.1` | golden test |
| `minor` | 지시 명확화, same-schema behavior tuning | `1.0 -> 1.1` | targeted regression + benchmark smoke |
| `major` | 출력 의미/도구 정책/JSON 구조 변경 | `1.0 -> 2.0` | full benchmark rerun + baseline/threshold stale 처리 |

### 10.2 프롬프트 변경 운영 규칙

- numbering scheme은 반드시 `major.minor.patch` semantic versioning 을 따른다.
- `patch` 변경은 baseline state를 바꾸지 않는다.
- `minor` 변경은 comparative baseline을 `provisional` 로 낮춘다.
- `major` 변경은 comparative baseline과 threshold profile을 모두 `stale` 로 만든다.
- 모든 LLM 호출은 `prompt_version` 을 artifact에 기록해야 한다.

> baseline/threshold state machine: `26-benchmark-calibration-ops.md`
> replay compatibility policy: `18-reproducibility.md`

---

## 11. 테스트 방법

### 프롬프트 단위 테스트 (Golden Test)

```python
# tests/unit/test_prompts.py

def test_intent_extract_prompt_includes_image():
    msgs = build_intent_extract_message(
        image_b64="aGVsbG8=",
        image_media_type="image/png",
        prompt="대시보드 생성",
        reference_notes=None,
    )
    assert len(msgs) == 1
    assert msgs[0]["role"] == "user"
    image_block = next(c for c in msgs[0]["content"] if c["type"] == "image")
    assert image_block["source"]["data"] == "aGVsbG8="

def test_code_generate_prompt_limits_context_sources():
    # context_sources가 6개를 초과할 때 최대 6개만 포함
    sources = [(f"src/comp{i}.tsx", f"content{i}") for i in range(10)]
    msg = build_code_generate_message(
        node=..., repo_profile=..., intent_graph=...,
        related_component_specs=[], context_sources=sources,
        user_prompt="test",
    )
    # 6개 초과 분 제한 확인
    assert msg[0]["content"].count("// src/comp") <= 6
```

### Integration Test (FakeLLM)

```python
# tests/integration/test_intent_extractor.py

async def test_intent_extraction_returns_intent_graph():
    fake_graph = IntentGraph(
        id="C-001", source_image_hash="abc123",
        layout_regions=[], components=[], interactions=[],
        confidence=0.9,
    )
    adapter = FakeLLMAdapter({"intent_extract": fake_graph.model_dump()})
    extractor = IntentExtractorService(llm=adapter)

    result = await extractor.extract(
        image_path=Path("fixtures/images/sample.png"),
        prompt="대시보드 생성",
    )

    assert isinstance(result, IntentGraph)
    assert result.confidence == 0.9
```

---

## 10. Architect-grade 설계 품질 게이트 체크리스트

> 이전 `31-architect-grade-quality-gates.md` 에서 흡수. `DDK-REQ-024` quality gate 프롬프트(`DesignQualityGate`)가 참조하는 채점 기준.

### 평가 축 (각 0~5점, 총 30점)

| 축 | 질문 |
| --- | --- |
| Completeness | 목적, 범위, 요구사항, 실패 모드가 충분히 정의되었는가 |
| Traceability | REQ ↔ design ↔ test ↔ release gate 연결이 보이는가 |
| Implementability | 구현자가 추론 없이 착수 가능한가 |
| Verifiability | 성공/실패를 artifact와 gate로 판정 가능한가 |
| Operability | human operator, rollback, escalation, governance가 정의되었는가 |
| Compliance | 적용 표준과 정책이 clause/artifact 수준에서 매핑되는가 |

### 판정 기준

| 총점 | 판정 | 의미 |
| --- | --- | --- |
| 24~30 | `pass` | architect-grade package |
| 18~23 | `flag` | 사용 가능, review/보완 필요 |
| 0~17 | `block` | 설계 승인 불가 |

### Hard Block 조건 (총점 무관 block)

- 제품 정체성 SSoT와 충돌
- 핵심 REQ의 acceptance/verification path 부재
- human operator model 부재
- proof boundary 미기재 상태에서 강한 claim 존재
- rollback / failure / escalation 부재
