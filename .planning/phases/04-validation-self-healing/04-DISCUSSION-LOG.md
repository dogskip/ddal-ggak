# Phase 4 Discussion Log

## Gray Area 1: Auto-fix 규칙 전략

**질문**: 9개 수리 규칙을 결정론적 패치 vs LLM 재생성 중 어떻게 구현?

**결정**: 하이브리드 (hybrid)

- R-01~R-08: 결정론적 패치 (string/regex 치환)
- R-09 (FT-BUILD-002, FT-RUNTIME-001): LLM 재생성
- FakeLLM key `"autofix"` 추가

---

## Gray Area 2: Playwright 통합 깊이

**질문**: Phase 4 테스트에서 실제 Playwright 사용? vs FakePlaywrightAdapter로 충분?

**결정**: 실제 Playwright 포함 (real_playwright)

- Phase 4 통합 테스트에서 실제 dev server 기동 + Playwright 브라우저 실행
- 단위 테스트는 FakePlaywrightAdapter 유지
- `pytest.mark.playwright` 마커로 CI skip 가능하게 구성

---

## Gray Area 3: Graph 루프 아키텍처

**질문**: validate-fix 루프를 어떻게 구현? 5가지 옵션 제시

**결정**: LangGraph 조건부 엣지 루프 (conditional_edge)

- `add_conditional_edges("validate", route_after_validate, {...})`
- pass → END, fix_available → autofix → validate, exhausted → END
- oscillation 감지: failure_set_hash 반복 시 즉시 manual-review 탈출
