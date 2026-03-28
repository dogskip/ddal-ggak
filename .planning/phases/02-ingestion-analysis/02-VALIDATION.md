---
phase: 02
slug: ingestion-analysis
status: approved
nyquist_compliant: true
wave_0_complete: false
created: 2025-07-28
---

# Phase 02 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio (asyncio_mode = "auto") |
| **Config file** | `pyproject.toml [tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/unit/services/ -x -q` |
| **Full suite command** | `uv run pytest tests/ -x -q` |
| **Integration command** | `uv run pytest tests/integration/ -m integration -x -q` |
| **Estimated runtime** | ~2 seconds (unit), ~10 seconds (full) |
| **Baseline** | 207 tests pass — all Phase 2 additions must maintain this |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/unit/services/ -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -x -q`
- **Phase gate (D-08 완료 후):** `uv run pytest tests/ -x -q` + `uv run pytest tests/integration/test_ingestion_pipeline.py -x` 모두 green
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~2 seconds (unit quick run)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 02-W0-01 | Wave 0 | 0 | D-05 | infra | `uv run pytest tests/unit/services/ -x -q` | ❌ W0 | ⬜ pending |
| 02-W0-02 | Wave 0 | 0 | D-06 | infra | `uv run pytest tests/ -x -q` | ❌ W0 | ⬜ pending |
| 02-W0-03 | Wave 0 | 0 | INGEST-04 | infra | `uv run pytest tests/unit/services/test_semantic_intent_extractor.py -x` | ❌ W0 | ⬜ pending |
| 02-W0-04 | Wave 0 | 0 | INGEST-05 | infra | n/a | ❌ W0 | ⬜ pending |
| 02-01-01 | 01 | 1 | INGEST-02 | unit | `uv run pytest tests/unit/services/test_intake_processor.py -x` | ❌ W0 | ⬜ pending |
| 02-01-02 | 01 | 1 | INGEST-02 | unit | same | ❌ W0 | ⬜ pending |
| 02-01-03 | 01 | 2 | INGEST-03 | unit | `uv run pytest tests/unit/services/test_repo_convention_scanner.py -x` | ❌ W0 | ⬜ pending |
| 02-01-04 | 01 | 2 | INGEST-03 | unit | same | ❌ W0 | ⬜ pending |
| 02-01-05 | 01 | 2 | INGEST-03 | unit | same | ❌ W0 | ⬜ pending |
| 02-01-06 | 01 | 2 | INGEST-03 | unit (FakeLLM) | same | ❌ W0 | ⬜ pending |
| 02-01-07 | 01 | 3 | INGEST-04 | unit (FakeLLM) | `uv run pytest tests/unit/services/test_semantic_intent_extractor.py -x` | ❌ W0 | ⬜ pending |
| 02-01-08 | 01 | 3 | INGEST-04 | unit | same | ❌ W0 | ⬜ pending |
| 02-01-09 | 01 | 4 | INGEST-05 | unit (FakeLLM) | `uv run pytest tests/unit/services/test_design_system_inferencer.py -x` | ❌ W0 | ⬜ pending |
| 02-01-10 | 01 | 4 | INGEST-05 | unit | same | ❌ W0 | ⬜ pending |
| 02-01-11 | 01 | 5 | INGEST-06 | unit (FakeLLM) | `uv run pytest tests/unit/services/test_generation_planner.py -x` | ❌ W0 | ⬜ pending |
| 02-01-12 | 01 | 5 | INGEST-06 | unit | same | ❌ W0 | ⬜ pending |
| 02-01-13 | 01 | 6 | CODEGEN-03 | unit | `uv run pytest tests/unit/services/test_context_pack_builder.py -x` | ❌ W0 | ⬜ pending |
| 02-01-14 | 01 | 6 | CODEGEN-03 | unit | same | ❌ W0 | ⬜ pending |
| 02-01-15 | 01 | 6 | CODEGEN-03 | unit | same | ❌ W0 | ⬜ pending |
| 02-01-16 | 01 | 6 | CODEGEN-03 | unit | same | ❌ W0 | ⬜ pending |
| 02-01-17 | 01 | 6 | CODEGEN-03 | unit | same | ❌ W0 | ⬜ pending |
| 02-02-01 | 02 | 7 | D-08 | integration | `uv run pytest tests/integration/test_ingestion_pipeline.py -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Wave 0 creates test stubs and infrastructure before implementation begins.

- [ ] `src/ddk/services/__init__.py` — 서비스 레이어 패키지 생성
- [ ] `tests/unit/services/__init__.py` — 서비스 단위 테스트 패키지 생성
- [ ] `src/ddk/models/design_system.py` — `DesignSystem`, `InferredDesignToken` Pydantic 모델
- [ ] `src/ddk/models/context_pack.py` — `ContextPack`, `ContextChunk` Pydantic 모델
- [ ] `@pytest.mark.integration` 마커 설정 — `pyproject.toml` markers 추가 + `conftest.py` ANTHROPIC_API_KEY skip guard
- [ ] `Message` 이미지 지원 확장 — `src/ddk/adapters/llm/base.py` `images: list[str] = []` 필드 추가
- [ ] `ClaudeAdapter` 이미지 전송 지원 — `src/ddk/adapters/llm/claude.py` base64 이미지 블록 처리
- [ ] `tests/fixtures/repos/react-vite-ts/` — 최소 package.json, tsconfig.json fixture 디렉토리
- [ ] `tests/unit/services/test_intake_processor.py` — stub
- [ ] `tests/unit/services/test_repo_convention_scanner.py` — stub
- [ ] `tests/unit/services/test_semantic_intent_extractor.py` — stub
- [ ] `tests/unit/services/test_design_system_inferencer.py` — stub
- [ ] `tests/unit/services/test_generation_planner.py` — stub
- [ ] `tests/unit/services/test_context_pack_builder.py` — stub
- [ ] `tests/integration/test_ingestion_pipeline.py` — stub (E2E 5-노드 그래프)

---

## Key Acceptance Criteria per Service

| Service | Acceptance Criteria |
|---------|---------------------|
| `IntakeProcessor` | CaseInput 반환; 이미지 미존재 시 `FileNotFoundError`; 이미지 5개 초과 시 `ValidationError` |
| `RepoConventionScanner` | React 프로젝트에서 `framework="react"` 반환; `package.json` 없으면 `framework="other"`; LLM 호출은 정적 불충분 시에만 |
| `SemanticIntentExtractor` | FakeLLM 응답에서 `IntentGraph` 파싱; `confidence >= 0.0`; `source_image_hash` 16자리 hex |
| `DesignSystemInferencer` | `DesignSystem` 반환; 이후 `repo_profile.design_tokens` 풍부화; FakeLLM으로 단위 테스트 통과 |
| `GenerationPlanner` | 동일 입력 → 동일 `GenerationPlan`; topological order 준수 |
| `ContextPackBuilder` | `total_lines <= 300`; `len(chunks) <= 6`; 동일 입력 → 동일 `context_pack_hash`; P1 없으면 `insufficient_context=True` |

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| 실제 Claude API → IntentGraph | INGEST-04 | ANTHROPIC_API_KEY 필요 | `uv run pytest tests/integration/ -m integration -k intent_extract` |
| 실제 Claude API → RepoProfile LLM 보완 | INGEST-03 | ANTHROPIC_API_KEY 필요 | `uv run pytest tests/integration/ -m integration -k repo_scan` |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s (unit quick run ~2s)
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
