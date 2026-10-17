# 기존 변경 검사와 안전한 반영

처음 준비와 통합 명령은 [새 사용 안내](ONECLICK.ko.md), SQLite 필드는 [색인 안내](CATALOG.md)를 참고합니다.
[English](VERIFIED-CHANGES.md) · [후속 계획](../ROADMAP.ko.md)

새 명령은 `ddk change` 아래에 있다. 기존 `run`, `status`, `apply`, `demo` 명령과 구분한다. 검사 전용 경로는 모델·API 키·이미지 입력이 필요하지 않다. 화면 기준이 있는 검사만 이미지를 요구한다.

기본 `isolated`는 로컬 Docker의 앱·검사 작업을 분리해 실행한다. 고정한 이미지가 이미 설치돼 있어야 하며 실행기·보호 설정·실제 환경을 확인하지 못하면 `isolation_unavailable`이다. 검사 중 이미지 내려받기·의존성 설치·사용자 환경 실행으로 자동 대체하지 않는다. 명시적으로 선택하는 `trusted-local`은 사용자 권한으로 프로젝트 명령을 실행하며 OS 격리를 제공하지 않는다.

## 준비할 자료

승인된 case 정의, 고정 입력 폴더, 명시적인 기준·후보 폴더, 변경 파일별 요구 ID가 필요하다. `case.json`과 `inputs/`를 함께 보관하면 입력 폴더를 생략할 수 있다. 정의와 필드 제약은 [JSON Schema](../src/ddk/assets/verified-change/contract.schema.json)와 [시험 예제](../tests/fixtures/verified-change/contract-examples.json)를 사용한다.

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

## 격리 환경 준비와 확인

앱 이미지에는 고정한 Node·의존성이, 검사 이미지에는 Python 3.12 이상·Playwright·해당 Chromium·Pillow·jsonschema·fontconfig가 필요하다. 검사 이미지의 고정 예시는 [Dockerfile](../tools/verified-checker/Dockerfile)에 있다. 이미지 준비는 검사와 별도 작업이다. 준비한 이미지의 `docker image inspect` 결과 `Id`에서 `sha256:`을 제외한 값을 Environment의 두 이미지 SHA에 기록한다. 태그나 원격 Docker 주소는 허용하지 않는다.

실행은 원본 대신 소유한 사본을 사용한다. 앱은 `/workspace`만 공유하고 검사 기준·관찰 자료·Docker 소켓을 받지 않는다. 검사 작업은 읽기 전용 `/criteria`와 결과를 보관할 `/results`만 공유하며 앱 파일을 받지 않는다. 두 작업은 외부 연결이 없는 같은 통신 영역에서 루프백으로 통신한다. 화면 제공 명령의 `{port}`는 내부 `4173`으로 치환하며 사용자 장비에 포트를 공개하지 않는다. 화면 검사마다 새 앱·검사 작업과 새 브라우저 문맥을 사용한다. 명령 검사는 앱 작업 안에서만 실행한다.

검사 코드는 사용 중인 ddalggak에서 별도로 복사해 읽기 전용으로 제공한다. 프로젝트의 Python 모듈·시작 파일·시험 출력으로 검사 코드를 교체하지 않는다. 전달한 검사 코드 목록의 SHA와 실제 실행 제한 확인 자료도 결과에 보관한다.

| Environment 값 | 실제 대조 대상 |
|---|---|
| `runtime_name`, `runtime_version`, `endpoint_kind` | `docker`, 로컬 실행기의 ServerVersion, `local` |
| 앱·검사 이미지 SHA | 로컬 이미지 조회 및 생성한 작업의 실제 Image |
| OS·장비·Python·Playwright | 검사 이미지 안에서 조회한 값 |
| Node·패키지 도구 버전 | 앱 이미지 안에서 조회한 값. 버전 앞의 `v`는 Node에 포함하지 않음 |
| `lockfile_sha256` | 사본 최상위의 package-lock.json·pnpm-lock.yaml·yarn.lock·bun.lock·bun.lockb 중 정확히 하나의 전체 SHA |
| 브라우저 버전·실행 파일 SHA | 실제 보호 설정을 적용해 실행한 Chromium과 실행 파일 |
| `font_manifest_sha256` | `fc-list --format '%{file}\\n'`의 고유 파일 경로를 정렬한 `{path,sha256}` 배열의 canonical JSON SHA |
| `policy_sha256` | 자원·공유 경로·통신·권한·로그·seccomp 정책을 포함하는 `verified-isolation/1`의 SHA |

정책 SHA는 `ddk.adapters.verified_isolation.POLICY_SHA256`, 글꼴 목록의 계산은 `ddk.adapters.verified_worker.font_manifest`가 정본이다. 기준을 실행 결과에 맞춰 자동 갱신하지 않는다. 버전·해시 불일치는 통과할 수 없다. 잠금 파일 대조는 고정한 파일과의 일치를 뜻하며 이미지의 의존성을 자동 설치하거나 잠금 파일에서 재구성했다는 증거는 아니다. 앱 이미지는 그 의존성이 준비된 신뢰하는 입력이어야 한다.

작업 생성·정책 확인·환경 대조·명령·화면 준비는 같은 검사 시간 제한을 사용한다. 앱 출력은 생성 직후부터 수집하고 앱·검사 작업이 종료된 뒤 확정한다. UTF-8 출력은 기준·후보에 걸쳐 합산하며 누락·초과·미정 상태에서 후속 검사를 실행하지 않는다. 취소·시간 초과에서도 소유한 작업을 제거하고 실제 부재를 조회한다. 정리·자료 회수·사본 대조를 확인하지 못하면 ready를 제공하지 않는다.

로컬 Docker 실행기와 선택한 검사 이미지는 신뢰하는 실행 기반이다. 앱의 쓰기 가능한 사본에는 별도의 디스크 용량 할당이 없으므로 이 기능을 악성 프로그램에 대한 장비 전체 보호로 해석하지 않는다. 현재 실제 확인 환경은 macOS ARM64와 OrbStack의 Linux 작업, 고정 Node 정적 시험 앱이다. 다른 실행기·장비·Vite·Next.js의 실제 지원은 별도 실행 근거가 필요하다.

`command` 검사는 고정한 `command_argv`를 셸 평가 없이 실행한다. `test`의 현재 수집 형식은 단일 JSON 객체의 정수 `executed_count`, `failed_count`, `skipped_count`다. 시험 0개·해석 불가·누락·건너뜀을 통과로 처리하지 않는다. 시험 프로그램의 보고는 `project-report`이며 독립 브라우저 관찰과 구분한다. 임의 Vitest·Jest 보고 형식이 모두 지원된다고 안내하지 않는다. `policy` 종류의 실제 평가는 아직 미지원이다.

## 명령과 결과

| 명령 | 주요 입력 | 동작 |
|---|---|---|
| `ddk change verify` | `--case-file` 또는 `--case-id`, `--baseline`, `--candidate`, `--run-id`, 필요 시 두 대응 파일 | 고정 기준과 후보 검사. `--case-file`는 정의 가져오기도 수행 |
| `ddk change status` | `--run-id` | 완료·대기 기록과 자료 검증 후 조회. 작업을 재시작하거나 저장소를 생성하지 않음 |
| `ddk change export` | `--run-id`, 새 ZIP 파일인 `--destination` | 검토용 JSON과 허용된 자료 내보내기. 기존 파일을 덮어쓰지 않음 |
| `ddk change apply` | case/run ID, run·변경 SHA, `--confirm-local-storage`, `--confirm-quiescence` | ready 결과만 관리된 반영. 기본 요구 보장은 isolated |
| `ddk change recover` | `--apply-id`, 로컬·동일 호스트·다른 작업 중지 확인 | 소유자가 종료한 반영을 현재 상태와 대조해 복구. 외부 변경은 보존 |

각 명령의 `--repo`는 기록과 원본 반영 대상 저장소다. `--json`은 stdout에 JSON 결과만 제공하며 진행·진단은 stderr에 출력한다. 종료 값은 [정본 표](EXIT-CODES.ko.md)에 따라 ready=0, 판정 미달=1, 사용법 오류=2, 설정 무효=3, 실행 불가=4, 무결성 실패=5, 취소=130이다. `--run-id`를 생략하면 UUID를 생성한다. 동일 요청의 같은 ID는 저장된 상태 조회이며, 다른 입력에 같은 ID를 사용하면 충돌이다.

개인 환경 실행은 `verify --trusted-local`로 별도 선택해야 한다. case도 trusted-local을 요구해야 하며 isolated case의 요구 수준을 낮출 수 없다. 원본·후보·명령·상한을 검토한 사용자의 선택이며, 저장된 case 자체가 실행 권한은 아니다.

기본 ZIP은 민감한 원문·모델 응답·화면 자료·로그를 제외한다. `--include-sensitive`는 해당 자료를 포함할 명시적 선택이며 공개 안전성 보증이 아니다. 보고서에는 판정·보장 수준·검사 결과·변경 해시·조치 코드를 제공한다. 제공자 응답이나 실행 오류 원문은 기본 보고서에 복사하지 않는다.

`apply`는 export와 별개다. ready라도 원본의 존재·일반 파일 여부·내용·권한이 변경되었으면 반영하지 않는다. 불확정 상태는 `unknown`으로 유지하며 강제 덮어쓰기나 Git 전체 초기화를 제공하지 않는다. 실제 정리·저장 확인을 실패했으면 성공으로 표시하지 않는다.

## 동일 요청 예산의 수정·재검사

`ddk change repair`는 완료된 source run에서 새 요청을 시작합니다. 원래 검사에 사용한 기준·후보와
보호 파일 대응을 명시하며, 후보는 저장된 해시와 일치해야 합니다. 원래 승인한 변경 경로·요구 관계만
수정할 수 있습니다. 추가 경로·삭제·권한·시험·의존성 변경은 허용하지 않습니다.

주요 입력은 `--source-run-id`, `--baseline`, `--candidate`, `--provider`, `--input-token-limit`,
`--output-token-limit`, `--confirm-provider`, `--run-id`입니다. 기록 위치는 `--repo`로 지정하며
보호 파일 대응이 있으면 `--project-inputs`를 함께 사용합니다.

```bash
ddk change repair --source-run-id SOURCE_RUN_UUID \
  --baseline ./baseline --candidate ./candidate --repo ./repository \
  --price ./verified-price.json --input-token-limit 32768 --output-token-limit 8192 \
  --confirm-provider --run-id REPAIR_RUN_UUID --json
```

`--confirm-provider`는 승인 경로의 비밀 정보를 제외한 내용과 실패 검사 발췌를 선택한 제공자에
전송하고 비용 발생에 동의하는 선택입니다. 기본 Anthropic은 `ANTHROPIC_API_KEY` 또는
`DDK_ANTHROPIC_API_KEY`가 필요합니다. 다른 제공자와 주소 선택은 [통합 안내](ONECLICK.ko.md)를
따릅니다. trusted-local case는 `--trusted-local`도 명시해야 하며
isolated의 보장 수준을 낮출 수 없습니다. 화면 자료나 임의 저장소 파일은 모델 문맥에 포함하지 않습니다.

`--price`를 생략하면 유효 기간 안의 기본 Anthropic 가격을 case에 연결합니다. 다른 제공자나
기본 가격 만료 시 가격 JSON이 필요합니다. 가격 JSON에는 아래 필드가 모두 필요하며 단가를 추정하지 않습니다.

| 필드 | 의미 |
| --- | --- |
| `provider`, `model` | 선택한 제공자와 명시적인 모델명. Anthropic은 `known_model_names()`로 제한 |
| `input_micro_usd_per_million`, `output_micro_usd_per_million` | 토큰 백만 개당 최대 단가. 금액 단위는 미국 달러의 백만분의 일 |
| `extra_max_micro_usd` | 호출 하나의 검증한 추가 비용 최대값. 같은 금액 단위 사용 |
| `source_url`, `verified_at` | 가격의 HTTPS 근거와 `Z`로 끝나는 확인 시각 |
| `evaluator_sha256` | case가 고정한 검사 기준 해시 |

단가는 [공식 가격](https://platform.claude.com/docs/en/about-claude/pricing)과 대조해야 합니다.
입력 한도는 비용 예약과 UTF-8 문맥 크기의 보수적 제한에 사용하며 정확한 토큰 계산이나 제공자 청구액을
보증하지 않습니다. 관찰한 사용량이 입력·출력·추가 비용 한도를 초과하면 중단합니다. 실제 응답 모델도
가격에 명시한 모델과 일치해야 합니다.

회차 0에서 기준과 후보를 다시 검사하고 이미 통과하면 모델을 호출하지 않습니다. 제안 하나마다 예약을
저장·재조회한 뒤 HTTP 한 번만 수행합니다. SDK 재시도는 0이며 사고용 출력량을 예약보다 확대하지
않습니다. 준비·모델 호출·모든 재검사는 같은 단조 시계의 마감과 누적 출력 한도를 사용합니다. 출력은 실행 출력과 SDK 최종 응답의
UTF-8 자료 크기이며 응답의 추론·부가 자료도 포함합니다. HTTP 전송 형식의 크기를 뜻하지 않습니다.
비용 미정·미지원 과금·후보 반복·상한 소진은 추가 작업을 중단합니다.
[공식 사용량 규칙](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)에 따라 일반
입력과 재사용 입력을 구분하며, 누락된 사용량을 0으로 정산하지 않습니다.

회차별 후보·검사·가격·사용량 자료를 같은 run에 보존하고 이전 증거를 덮어쓰지 않습니다. 반영 대상은
최신 독립 검사 후보입니다. HTTP 중단 시 예약·미정 사용량을 유지하고 해당 case의 추가 유료 작업을
차단합니다. 같은 ID의 재요청은 상태 조회이며 입력이 다르면 충돌입니다. 중단한 모델 작업을 자동으로
재실행하거나 재과금하지 않으며 source 참조 깊이는 32로 제한합니다.
기존 `status`, `export`, `apply`, `recover`를 재사용합니다. recover는 중단된 반영의 복구이며
불확정 제공자 호출의 재실행이나 미정 비용 자동 정산을 제공하지 않습니다.

## MCP

정본 도구 14개는 `ddk_` 접두를 사용합니다. `ddk_design_new`와 `ddk_preflight`를 사용하며
이전 `design_new`, `preflight`는 호환 이름으로 제공합니다.

`ddk serve`는 검증용 도구 여덟 개와 기존 설계·준비·버전 도구를 제공합니다.
`ddk_verify`는 격리 실행을 유지합니다. 추가 수정·반영·화면 관측은 서버 소유자 권한과
각 요청의 승인 및 필요한 호스트 실행 권한이 있어야 합니다. 세부 권한과 기본 거부 조건은
[통합 명령 안내](ONECLICK.ko.md#sqlite와-mcp)에 있습니다. `ddk_status`는 저장된 보장을 그대로 표시합니다.

필수 검사 실패는 정상 도구 결과의 blocked다. 잘못된 입력과 실행 불가는 도구 오류이며, 보존된 실행 ID는 상태 도구로 조회할 수 있다. 첫 구현은 잠긴 SDK 1.30.0 및 실제 협상한 규약 판의 시험 범위만 주장한다. 도구 설명·표시는 승인이나 보안을 대신하지 않는다. [공식 MCP 도구 규약](https://modelcontextprotocol.io/specification/2025-11-25/server/tools).

원문 크기·깊이·중복 키·UTF-8 규칙에 맞지 않는 stdio 요청은 연결을 종료한다. 임의 요청 ID로 성공 응답을 만들지 않으며, 이미 보존한 실행 결과를 삭제하지 않는다.

## 현재 한계

자동 case 준비와 일반 시험 보고 형식, CLI·MCP 수정은 구현했습니다. 실제 제공자 효과와 대표
프로젝트·다른 장비의 호환성은 별도 검증이 필요합니다. 기존 예제의 기록된 응답을 유료 모델의
실제 수정 효과로 해석하지 않습니다. 지정 기준 통과는 앱의 무결함·제품 우위·GitHub 별 수를 뜻하지 않습니다.
