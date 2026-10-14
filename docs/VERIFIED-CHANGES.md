# 기존 변경 검사와 안전한 반영

새 명령은 `ddk change` 아래에 있다. 기존 `run`, `status`, `apply`, `demo` 명령과 구분한다. 검사 전용 경로는 모델·API 키·이미지 입력이 필요하지 않다. 화면 기준이 있는 검사만 이미지를 요구한다.

현재 실제 실행을 확인한 경로는 명시적으로 승인한 `trusted-local`이다. 프로젝트 명령이 사용자 권한으로 실행되며 OS 격리를 제공하지 않는다. 기본 `isolated`는 자동 대체하지 않는다. 현재 검사 작업 연결이 미구현이므로 Docker 사전 확인이 성공해도 `isolation_unavailable`이다. 이 기능을 격리 실행 지원 완료로 안내하지 않는다.

## 준비할 자료

승인된 case 정의, 고정 입력 폴더, 명시적인 기준·후보 폴더, 변경 파일별 요구 ID가 필요하다. `case.json`과 `inputs/`를 함께 보관하면 입력 폴더를 생략할 수 있다. 정의와 필드 제약은 [자료 계약](design/35-verified-change-storage.md)과 [JSON Schema](design/verified-change/contract.schema.json)를 사용한다.

- 기준은 case가 고정한 프로그램 파일과 보호 파일의 내용·권한에 일치해야 한다.
- 후보는 범위 안의 프로그램 파일 생성·수정만 허용한다. 삭제·이동·권한 변경·시험·기준·의존성 변경은 거부한다.
- 프로젝트의 시험·의존성 잠금 파일 등은 `--project-inputs`의 JSON 파일에 프로젝트 경로와 고정 입력 경로의 대응을 명시한다.
- `--change-requirements`는 변경 경로를 승인한 요구 ID 배열에 대응한다. 도구가 요구 관계나 Git 기준을 추정하지 않는다.

고정 입력에는 Environment와 `criteria/execution.json`이 포함된다. 실행계획도 criteria 입력으로 고정하며, 아래 키 외의 값은 허용하지 않는다.

| 키 | 값과 의미 |
|---|---|
| `format` | `verified-evaluator/1` |
| `environment_path` | 고정 Environment 파일의 상대 경로 |
| `criteria_paths` | 실행계획 자신과 모든 검사 정의가 포함된 기준 파일 목록 |
| `environment_paths` | 환경 파일 목록 |
| `preview_argv` | 화면을 제공할 명령 배열. 전체 인자 하나인 `{port}`만 치환하며 명령 검사만 있으면 빈 배열 가능 |
| `frozen_time` | 시간대가 있는 ISO 8601 고정 시각 |
| `browser_executable` | 명시적 절대 경로 또는 기본 탐색을 사용할 `null` |
| `visual_references` | 경로·화면 크기·환경 객체 SHA·`mask_sha256:null`의 배열. 화면 비교가 없으면 빈 배열 |

입력 목록의 SHA·크기·권한을 실제 파일과 대조한다. case의 환경 SHA는 환경 **파일 목록**의 해시이며, 화면 기준의 환경 SHA는 Environment **객체**의 해시다. 두 값을 바꾸어 사용하지 않는다. 기준·환경 파일 목록을 바꾸면 새 case가 필요하다.

`command` 검사는 고정한 `command_argv`를 셸 평가 없이 실행한다. `test`의 현재 수집 형식은 단일 JSON 객체의 정수 `executed_count`, `failed_count`, `skipped_count`다. 시험 0개·해석 불가·누락·건너뜀을 통과로 처리하지 않는다. 시험 프로그램의 보고는 `project-report`이며 독립 브라우저 관찰과 구분한다. 임의 Vitest·Jest 보고 형식이 모두 지원된다고 안내하지 않는다. `policy` 종류의 실제 평가는 아직 미지원이다.

## 명령과 결과

| 명령 | 주요 입력 | 동작 |
|---|---|---|
| `ddk change verify` | `--case` 또는 `--case-id`, `--baseline`, `--candidate`, `--run-id`, 필요 시 두 대응 파일 | 고정 기준과 후보 검사. `--case`는 정의 가져오기도 수행 |
| `ddk change status` | `--run-id` | 완료·대기 기록과 자료 검증 후 조회. 작업을 재시작하거나 저장소를 생성하지 않음 |
| `ddk change export` | `--run-id`, 새 ZIP 파일인 `--destination` | 검토용 JSON과 허용된 자료 내보내기. 기존 파일을 덮어쓰지 않음 |
| `ddk change apply` | case/run ID, run·변경 SHA, `--confirm-local-storage`, `--confirm-quiescence` | ready 결과만 관리된 반영. 기본 요구 보장은 isolated |
| `ddk change recover` | `--apply-id`, 로컬·동일 호스트·다른 작업 중지 확인 | 소유자가 종료한 반영을 현재 상태와 대조해 복구. 외부 변경은 보존 |

각 명령의 `--repo`는 기록과 원본 반영 대상 저장소다. `--json`은 stdout에 JSON 결과만 제공하며 진행·진단은 stderr에 출력한다. 기본 종료 값은 ready=0, blocked/manual-review=1, 입력·실행 불가=2, 취소=130이다. `--run-id`를 생략하면 UUID를 생성한다. 동일 요청의 같은 ID는 저장된 상태 조회이며, 다른 입력에 같은 ID를 사용하면 충돌이다.

개인 환경 실행은 `verify --trusted-local`로 별도 선택해야 한다. case도 trusted-local을 요구해야 하며 isolated case의 요구 수준을 낮출 수 없다. 원본·후보·명령·상한을 검토한 사용자의 선택이며, 저장된 case 자체가 실행 권한은 아니다.

기본 ZIP은 민감한 원문·모델 응답·화면 자료·로그를 제외한다. `--include-sensitive`는 해당 자료를 포함할 명시적 선택이며 공개 안전성 보증이 아니다. 보고서에는 판정·보장 수준·검사 결과·변경 해시·조치 코드를 제공한다. 제공자 응답이나 실행 오류 원문은 기본 보고서에 복사하지 않는다.

`apply`는 export와 별개다. ready라도 원본의 존재·일반 파일 여부·내용·권한이 변경되었으면 반영하지 않는다. 불확정 상태는 `unknown`으로 유지하며 강제 덮어쓰기나 Git 전체 초기화를 제공하지 않는다. 실제 정리·저장 확인을 실패했으면 성공으로 표시하지 않는다.

## MCP

기존 `ddk serve`의 stdio 서버가 `ddk_verify`, `ddk_status`를 제공한다. CLI와 같은 서비스·계약·저장을 사용한다. 첫 검사 도구는 isolated만 허용하며 trusted-local·반영·복구·설치·내보내기 권한을 공개하지 않는다. `ddk_status`는 실제 저장된 보장 수준을 그대로 표시한다.

필수 검사 실패는 정상 도구 결과의 blocked다. 잘못된 입력과 실행 불가는 도구 오류이며, 보존된 실행 ID는 상태 도구로 조회할 수 있다. 첫 구현은 잠긴 SDK 1.28.1 및 실제 협상한 규약 판의 시험 범위만 주장한다. 도구 설명·표시는 승인이나 보안을 대신하지 않는다. [공식 MCP 도구 규약](https://modelcontextprotocol.io/specification/2025-11-25/server/tools).

원문 크기·깊이·중복 키·UTF-8 규칙에 맞지 않는 stdio 요청은 연결을 종료한다. 임의 요청 ID로 성공 응답을 만들지 않으며, 이미 보존한 실행 결과를 삭제하지 않는다.

## 현재 한계

새 경로의 자동 수정·재검사, 실제 격리 검사 작업, 일반 시험 도구별 보고 수집, 처음 기준을 준비하는 안내 자동화는 미완료다. 기존 `ddk demo`의 기록된 모델 응답과 새 모델 없는 검사는 각각의 근거를 사용한다. Node 정적 시험 앱의 실제 동작 확인을 실제 Vite·Next.js 저장소 전체의 지원 증거로 확대하지 않는다. 검사 통과는 지정한 기준의 결과이며 앱 전체의 무결함·제품 우위·GitHub 별 수를 뜻하지 않는다.
