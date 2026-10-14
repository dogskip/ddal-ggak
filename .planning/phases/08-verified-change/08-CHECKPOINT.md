# 검증 가능한 변경 구현 확인 기록

2026-10-14 기준의 중간 구현 기록이다. 설계 전체의 완료·출시·제품 우위를 선언하지 않는다. [구현 계획](08-PLAN.md)과 확정 설계 34~36을 기준으로 한다.

## 구현 범위

| 범위 | 구현과 확인 | 남은 조건 |
|---|---|---|
| 공통 보호 | 문맥·복사·수정·반영의 경로 규칙, 인증 파일 제외, 일반 파일·크기·중복·응답 완결성 검사 | 새 호출 입구에서도 같은 규칙을 사용해야 한다 |
| 취소·정리 | 소유한 자식·하위 작업 종료, 출력·정리 시간 제한, 중첩 이벤트 실행 보강 | 새 검사 연결의 통합 확인 |
| 자료 계약 | 고정 case·run·반영 기록, 공통 검증, 내구성 저장, 배타 잠금, 종료 기록 불변 | CLI·MCP 연결 |
| 모델 없는 검사 | 두 번의 원본 목록·내용 확인, 명시적 기준·후보, 요구별 변경 대응, 필수 누락·정리 실패 차단 | 실제 검사 연결이 아직 기본 실행에 연결되지 않음 |
| 브라우저 | 실제 headless 시나리오, 시나리오별 격리, 요청 차단, 고정 RGB 기준, 민감 자료 표시 | Docker 실행과 통합하지 않았음 |
| 격리 | 로컬 endpoint 확인, 앱·검사 분리, 명시 정책 확인, 소유 작업 정리 | 실제 소켓이 없어 격리 실행 미검증 |
| 비용 | 단일 HTTP, 사전 예약, 사례별 직렬화, 미정 비용 보존·추가 호출 차단 | 수정·재검사를 한 요청에 연결하는 절차 |
| 원본 반영 | 명시적 ready·해시·환경 보장·사용자 확인, 사전 기록, 전체 상태 확인, 제한 복구 | 새 CLI 입구 연결, 다른 OS·파일 공간의 실행 증거 |

DB·서버·외부 계정·유료 제공자 호출은 추가하지 않았다. 실제 모델 품질과 외부 사용자의 반복 사용은 미평가다.

## SDD·TDD와 회귀 근거

- 설계 정합성: [document-current.json](evidence/document-current.json). 21개 정의·203개 필드·79개 예시·요구 20개·수용 기준 30개·참조 36개 확인. 구현·제품 효과 증거는 0으로 유지한다.
- 공통 보호: [초기 실패](evidence/boundary-red.txt), [통과 기록](evidence/boundary-green.txt).
- 자료 저장: [초기 실패](evidence/storage-red.txt), [통과 기록](evidence/storage-green.txt), [잠금 복구](evidence/lock-resume-green.txt).
- 원본 포착·검사 조율: [원본 시험](evidence/source-green.txt), [검사 시험](evidence/engine-green.txt), [확인 범위](evidence/engine-verification.json). 주입한 검사 결과는 실제 격리 실행의 증거가 아니다.
- 비용: [초기 실패](evidence/budget-red.txt), [164개 관련 시험](evidence/budget-green.txt). 제공자 요청은 모의 HTTP이며 실제 유료 요청은 0회다.
- 원본 반영: [관리된 반영 초기 실패](evidence/managed-apply-red.txt), [실제 종료 후 복구 초기 실패](evidence/managed-recovery-red.txt), [복구 동기화 초기 실패](evidence/managed-restore-durability-red.txt), [70개 집중 시험](evidence/managed-recovery-green.txt).
- 기존 위험 복구의 회귀: [초기 전체 결과](evidence/full-unit-regression.txt)의 실패 4개는 전체 Git 초기화·미추적 파일 삭제를 기대한 이전 계약이었다. [관련 27개 시험](evidence/legacy-recovery-regression.txt)은 거부 후 실제 파일·Git 상태 보존을 확인한다.
- 전체 일반 시험: [2,025개 통과](evidence/full-unit-regression-final.txt). 브라우저 표시가 있는 시험 18개는 별도 실행 대상이다.
- 기존 실제 데모: [실행 기록](evidence/real-delivery-headless.txt)에서 데모 통과, 화면 반복 시험의 준비 실패를 확인했다. 의존성 폴더를 원본에서 복사하지 않는 정책에 맞춰 일시 사본 설치를 명시한 뒤 [실제 화면 반복 시험](evidence/real-delivery-headless-green.txt)이 통과했다. 기준·허용 오차·필수 검사는 변경하지 않았다.
- 실제 브라우저: [취소 후 미수거 오류의 실패 재현](evidence/verified-browser-async-red.txt)과 [수정 후 32개 단위·실제 시험](evidence/verified-browser-async-green.txt), [정리 자료·SHA](evidence/verified-browser-async-manifest.json). 예외를 무시하지 않고 소유한 실행·단계 작업을 직접 기다린다. 선택자 실패는 failed, 취소는 호출자에게 전파하며 정리 자료를 보존한다.
- 별도 화면 시험 18개는 겹치지 않는 실행의 결과다. 새 실제 headless 11개, 기존 데모·수정 반복 2개, [기존 연결·이미지 5개](evidence/browser-adapter-headless.txt)가 통과했다. 이미지 비교 시험 1개는 브라우저 실행 시험이 아니다.
- 전체 타입 검사: [오류 0개](evidence/full-types.txt). [Ruff](evidence/full-lint.txt), [형식](evidence/full-format.txt), [diff 검사](evidence/full-diff-check.txt) 통과.
- 배포 파일: [구성 검사·설치 후 조회](evidence/checkpoint-package.json). 별도 환경에 설치한 모듈 144개를 현재 소스와 대조하고, 설치한 계약 파일의 실제 해석·격리 설정 파일·저작권 파일·직접 의존성 선언을 확인했다. 다른 의존성 조합 전체의 호환 보증은 아니다.

## 원본 반영의 3심 검토

검토 대상은 `src/ddk/services/artifact_applier.py`와 관련 시험·공통 파일·Store 계약이다. 전체 제품의 3심 완료로 확대하지 않는다. 서로 다른 시험 수는 범위가 겹치므로 합산하지 않는다.

| 심사 | 확인과 지적 | 조치·재확인 |
|---|---|---|
| 1심 구현 검토 | 파일 상태·권한·존재, 단계별 기록, 실제 종료·외부 편집·저장 실패 | 실패 시험 작성 후 최소 수정, 집중 70개 통과 |
| 2심 독립 검토 | 완료 기록 동기화 우회, 복구 부모 동기화 누락, 완료 직후 종료 잠금 미정리 | 반례 재현 후 수정. 지정 SHA의 관련 79개 통과, update/create 실패 재주입에서 unknown·잠금 유지. 필수 잔여 지적 없음 |
| 3심 독립 검토 | 위 경계의 독립 재검증, 완료 기록 공개 전 실패, 복구 동기화 재진입, rolled_back 저장 실패·실제 종료 | 관련 110개 통과. 외부 변경·unknown 보존 포함. 필수 잔여 지적 없음 |

검토 전후 SHA256:

```text
src/ddk/services/artifact_applier.py
436c8cbf85480c37e3e2fc4602f80edb235b917aae013c9f41ce9fa594c275be
tests/unit/services/test_managed_application.py
c294f7435f2de8100c648bcf6ebfc15a861c2c2b7db599276c38677c83baf626
```

## 종료와 복구의 한계

실제 자식 작업을 종료한 시험은 작업 중단의 증거다. 전원 단절·저장 장치 결함·다른 호스트·임의 동시 편집에 대한 보증으로 확대하지 않는다. 저장 확인 실패와 외부 상태는 unknown으로 보존하고 새 원본 반영을 막는다. 파일이 조회된다는 사실만으로 내구성 완료를 판단하지 않는다.

현재 Docker 사전 확인은 [local_socket_unavailable](evidence/isolation-environment.txt)이다. 호스트 실행·보호 해제·실행기 설치로 대체하지 않았다. 기본 검사 연결은 이 조건에서 isolation_unavailable이며 ready를 만들지 않는다. trusted-local 실행 권한을 case·모델·MCP 입력에서 추론하지 않는다.

새 verify/repair/export/apply/recover/status와 stdio MCP, 실제 격리 통합, 한 요청의 수정·재검사 연결은 남은 구현이다. 이 분기는 아직 커밋·푸시하지 않았다. README 비교 그림만 별도 수정 커밋 `ef2a788`으로 GitHub에 반영했다.

소스·시험·문서와 주요 실행 기록의 최종 SHA는 [checkpoint-verification.json](evidence/checkpoint-verification.json)에 보관한다.
