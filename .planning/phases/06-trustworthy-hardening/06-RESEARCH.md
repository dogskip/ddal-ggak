# Phase 06 Research — Trustworthy Hardening

**조사일:** 2026-07-27  
**범위:** 현재 dirty worktree를 포함한 `ddalggak`, 최신 공식 GitHub 원본, 공개 표준 자료  
**판정 방식:** 1심 소스 정적 검토 → 2심 외부 원본 교차검증 → 3심 실행 반증/회귀 검증

## 현행 기준선

- Git: `main`, `origin/main`보다 2커밋 앞섬. 사용자 변경이 존재하므로 기존 변경을 보존한다.
- 회귀: `uv run --extra dev pytest -q -m 'not playwright'` → 907 passed, 2 deselected.
- 커버리지: 90%.
- Ruff: 통과.
- Pyright: 신규 assurance 모델의 매개변수 없는 `list` 때문에 9건 실패.
- 문서: `.planning/STATE.md`는 Phase 5 완료라고 하지만 Phase 5 디렉터리가 없고,
  `REQUIREMENTS.md`에는 구현 완료 항목이 Pending으로 남아 있다.

## 최신 외부 원본

| 시스템 | 기준 커밋 | 직접 확인한 원본 |
|---|---|---|
| GSD Core | `c07734216ff223649e43c14d448511c75f74695a` (`next`) | `docs/explanation/context-engineering.md` blob `d5852652933d2db564be913c697cf5f3fcafdfdf`; `src/verification.cts` blob `4d89b51ce8ae785a611eda5860ac14a139538f1d`; `src/capability-trust.cts` blob `fddb28faa7e8a68ff1580e1f34ab18b845566dd7` |
| Tura | `09b7913a693e82c6ebd4ffea0081ab063dd03316` | `docs/core/task-status.md` blob `baa5726a168fd4d72ab945c9c3cb6c7904b12ff2`; `docs/core/command-run.md` blob `4911dd25bea9c76fbc7574fa9b52c264f687fddb`; `docs/core/context-management.md` blob `10f7e6f77f8635066a333a7c7c1200a94cc04f1c` |
| Superpowers | `3dcbd5c4b48e02263fbf4a3c01e3fe4f81d584d9` | `skills/brainstorming/SKILL.md` blob `789c3a1990b9ab3896c4d8b0b708525ac83fe5ce`; `skills/test-driven-development/SKILL.md` blob `4320d8879a639d0536c2239bb80c9d7257ad8947`; `skills/verification-before-completion/SKILL.md` blob `7d45333cc4a49c57a80df6c1fe2fa777a207afbc` |
| Platty | `1c8d845e7769c43c32e79670c10ab3fc46544159` | `guide/en/how-platty-works.md` blob `f0f96f17140d8974a732ed8d77127f4bfb138fcd`; `platty-sdd-spec/SKILL.md` blob `5e88405addd3c0a9cd2444ded54da66c5ea692fe`; `platty-sync/SKILL.md` blob `016984ee0dc43385aa8dd84c762d526a68affb66` |

`gsd-build/get-shit-done`은 2026-06-26 보관 처리됐으며 현재 개발 원본은
`open-gsd/gsd-core`이다. Platty의 분석 엔진은 proprietary이므로 공개 저장소에서 검증 가능한
범위는 가이드와 에이전트 계약뿐이다. 제품 성능 주장은 검증 사실로 취급하지 않는다.

## 공식 표준·런타임 근거

- Anthropic 모델 폐기 문서상 기존 Sonnet 3.5/Haiku 3 기본값은 이미 폐기됐다.
  Sonnet 5는 non-default sampling parameter를 거부하므로 `temperature=0.0` 계약을 유지하는
  현재 파이프라인에는 Sonnet 4.6 + Haiku 4.5 조합을 채택한다.
- 품질 모델 표기는 `ISO/IEC 25010:2023`, 아키텍처 기술은
  `ISO/IEC/IEEE 42010:2022`로 갱신한다. 조항 텍스트의 내부 해석은 인증이 아니다.
- 보안 기준은 NIST SSDF 1.1(최종), OWASP ASVS 5.0.0, OWASP LLMSVS 2.0,
  공급망 provenance는 SLSA 1.2를 후속 검증 기준으로 사용한다. 현재 구현이 이 표준들을
  준수한다고 주장하지 않는다.

## 3심 반증 결과

임시 디렉터리에서 실제 서비스를 호출했다.

1. 빈 코드 파일과 빈 테스트 파일만 매핑해도 `superset=True`, maturity `P-2`.
2. 빈 문서 파일만 매핑해도 표준 조항 `satisfied`.
3. `GeneratedFile(path="../escaped.txt")`가 sandbox 밖에 파일을 생성.

따라서 현재 `proof/audit`는 증명기가 아니라 파일 존재 매퍼이고, 생성 경로는 보안 경계를
위반한다. 이 상태에서 상위호환·표준충족 주장을 허용하면 안 된다.

## 채택 결정

| 출처 | 채택 | 보류/기각 이유 |
|---|---|---|
| GSD Core | 검증 신선도, 명시적 상태, trust와 artifact parity 분리 | 전체 범용 워크플로 복제는 제품 경계를 흐리고 중복 |
| Tura | 구조화 상태, bounded context, 실행 전 경계 확인 | 범용 macro command runner와 세션 DB는 one-shot delivery pipeline에 과설계 |
| Superpowers | Red-Green-Refactor, 완료 직전 fresh verification, YAGNI | skill runtime 자체를 제품에 내장하면 책임 중복 |
| Platty | source commit/fingerprint, evidence boundary, unresolved 상태 보존 | proprietary static graph 엔진을 동등 구현했다고 주장할 근거 없음 |

## 구현 우선순위

1. 모든 생성·증거 경로를 repo/sandbox 내부 상대경로로 강제하고 symlink 탈출을 차단한다.
2. 은퇴한 Claude 기본 모델을 현재 지원 모델로 교체하고 설정값이 모든 LLM 서비스에 실제 전파되게 한다.
3. 파일 존재 상태를 `mapped`로 낮추고, 행동 검증 보고서 없이는 `proved/superset`을 금지한다.
4. 표준 결과를 `satisfied`가 아니라 `mapped`로 표현하고 인증/준수 오인을 막는다.
5. Pyright·회귀·패키지·보안 감사를 새로 실행하고 `.planning` 상태를 실제 결과와 맞춘다.
