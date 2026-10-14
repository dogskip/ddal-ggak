# 문서 인벤토리

## 목적

`docs/design` 문서군의 범위와 권위, 현재 구현과의 관계를 기록한다. 문서는 설계 의도이며,
실행 가능한 코드·테스트·보고서보다 높은 증거로 취급하지 않는다.

## 현재 저장소 판정

| 항목 | 현재 사실 | 권위 |
|---|---|---|
| 제품 | Python CLI/MCP와 10-node LangGraph 파이프라인이 구현됨 | `src/ddk`, `pyproject.toml` |
| 자동 검증 | pytest, Ruff, Pyright, package build 계약을 사용 | 실행 시점의 명령 결과 |
| 제품 정체성 | GSD 계보를 지향하는 Design-to-Delivery 도구 | `27-identity-positioning.md` |
| capability 비교 | 파일 존재는 `mapped`; 행동 검증 없이는 `proved` 아님 | `benchmarks/capability-matrix.json`, `ddk proof` |
| 표준 | clause-to-artifact 내부 매핑이며 인증·준수 판정이 아님 | `benchmarks/standards-catalog.json`, `ddk audit` |

## 권위 순서

1. 현재 실행 결과와 생성된 검증 보고서
2. 코드, 테스트, 잠금 파일, CI 설정
3. 머신 판독 SSoT (`benchmarks/*.json`, `.planning/REQUIREMENTS.md`)
4. 제품 정체성·거버넌스 문서 (`27`, `28`, `32`, `33`)
5. 나머지 설계·운영 문서와 예시

상위 항목과 문서가 충돌하면 상위 항목을 따르고 문서를 갱신한다.

## 문서군

| 범위 | 역할 |
|---|---|
| `00` | 인벤토리와 권위 |
| `02~09` | PRD, NFR, 시스템 설계, ADR, 검증, 인계 |
| `10~26` | 어댑터, 모델, CLI, 샌드박스, 프롬프트, 재현성, 운영 계약 |
| `27~28` | 제품 정체성과 capability/claim 경계 |
| `32~33` | 운영자 권한과 보안·개인정보 거버넌스 |
| `FINAL-AUDIT-REPORT.md` | 특정 시점 감사 스냅샷; 현재 사실의 SSoT가 아님 |

## 신선도 규칙

- 모델 ID, 외부 저장소 커밋, 표준 버전, 의존성 버전은 변경 가능 정보이므로 검증일을 남긴다.
- `ddk proof`와 `ddk audit` 결과를 문서에 손으로 고정하지 않는다.
- `proved`, `superset`, `superiority`, `compliant`, `certified`는 해당 실행 증거와 gate가
  없으면 사용하지 않는다.
- 소스 변경 뒤에는 테스트·정적 분석·패키지 빌드를 새로 실행한다.

## 현재 증명 경계

구현·테스트 파일이 존재한다는 사실은 capability 및 표준 항목의 연결 관계를 보여줄 뿐이다.
실제 사용자 시나리오에서의 행동 증명, 교정된 비교 benchmark, 독립 인증을 대신하지 않는다.
따라서 현재 문서군은 설계·구현·검증 계약을 제공하지만 GSD 상위호환이나 국제표준 준수를
자동으로 확정하지 않는다.
