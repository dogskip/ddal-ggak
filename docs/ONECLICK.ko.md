# 한 번의 명령으로 변경 검증

[English](ONECLICK.md) · [검증 계약](VERIFIED-CHANGES.ko.md) · [SQLite 필드](CATALOG.md)

`ddk up`은 현재 Git 변경을 캡처하고 고정된 기준으로 검사합니다. 필요하면 승인된 예산 안에서
수정·재검사하고 검토 자료와 반영 계획을 생성합니다. 실제 반영에는 `--apply`가 필요합니다.
요청 문장만으로 인수 기준을 추측하지 않습니다. 독립된 목표 검사와 보존 검사가 없으면
프로젝트 명령이나 모델을 실행하기 전에 `acceptance_checks_required`로 중단합니다.

## 해시 계산 없이 첫 case 준비

`ddk doctor --dry-run --json`은 Python·Git·Docker·설치된 이미지·Chromium·폰트·제공자 상태를
조회합니다. 의존성을 설치하거나 모델을 호출하지 않습니다. `warning`은 선택 제공자 부재나 현재
Git 변경 등을 뜻할 수 있습니다. 필수 조건이 없으면 `blocked`이며 조치도 함께 표시합니다.
`ddk doctor`, `--dry-run`, `--json`은 같은 판정과 검사 목록을 사용합니다. 잘못된 환경 설정도
값을 공개하지 않고 차단합니다. `--install-browser`만 설치를 요청하며 `--dry-run`과 함께
지정하면 설치하지 않습니다. 차단된 점검은 종료 값 2를 반환합니다.

검토한 동작을 `.ddk/verify.toml`, `ddk.toml`, `pyproject.toml`의 `[tool.ddk.verify]` 중 하나에
정의합니다. 앞에 있는 파일을 우선합니다. 다음은 제목을 After로 변경하고 기존 이동을 보존하는
정적 페이지 예제입니다. Git 기준에는 제목과 `/next.html` 링크가 있어야 합니다.

```toml
preview_argv = ["python3", "-m", "http.server", "{port}", "--bind", "127.0.0.1"]
scope_paths = ["index.html"]

[[checks]]
check_id = "heading"
role = "target"
steps = [{action="expect-text", selector="h1", value="After"}]

[[checks]]
check_id = "navigation"
role = "preserve"
steps = [{action="click", selector="a"}, {action="expect-text", selector="h1", value="Next"}]
```

```bash
ddk up "제목 변경과 기존 이동 보존" --dry-run --json
ddk up "제목 변경과 기존 이동 보존" --trusted-local --json
```

`--trusted-local`은 별도 사본에서 프로젝트 명령을 호스트 권한으로 실행하는 승인입니다.
자동 준비는 실제 호스트 환경을 이 보장 수준으로 기록하며 `isolated`로 높이지 않습니다.
별도로 준비한 기존 격리 case는 계속 사용할 수 있습니다. 소스·기준·실행 정의·실제 Chromium
SHA-256·폰트·의존성 고정 파일·설치 이미지·OS·Python을 자동 기록합니다.
`ddk init --request "..."`와 `ddk change init`은 검사를 실행하지 않고 같은 case를 생성합니다.

`--from-design design-package/`는 `manifest.json`의 요구와 선택적인 `verification.json`을 가져옵니다.
검사에 대응한 `check_ids`는 보존합니다. 대응이 없는 요구는 검토 대상으로 기록하며 통과시키지 않습니다.
`--git-base HEAD~1`로 기준을 선택할 수 있습니다. `ddk change verify --git-base REF`와 기존 물리
디렉터리 입력도 지원합니다. Git 추출은 작업 중인 파일·현재 분기를 변경하지 않습니다.
심볼릭 링크·하드링크·하위 저장소·모호한 파일 상태는 거부합니다. 비밀 정보와 실행 자료는 기존
경로 규칙으로 제외합니다. 파일 삭제는 연결한 요구의 `allow_delete=true`와 허용 경로가 필요합니다.

## 인수 기준 초안과 승인

```bash
ddk init --discover --json
ddk init --discover --url 'python3 -m http.server {port} --bind 127.0.0.1' --confirm-execution --json
# 초안을 검토하고 목표 검사·보존 검사·허용 경로·실행 명령을 정의합니다.
ddk init --approve-draft --json
ddk up "제목 변경과 기존 이동 보존" --trusted-local --json
```

위의 탐색 명령은 둘 중 하나를 선택합니다. 기존 초안은 덮어쓰지 않습니다.
`package.json`·`pyproject.toml`과 Playwright 설정 파일 이름으로 검사 명령을 제안합니다.
설정 JavaScript나 제안한 시험 명령은 실행하지 않습니다. 명시한 화면 관측에는 기존 Headless
관측 서비스를 사용하며, 실행 명령에는 별도의 실행 승인이 필요합니다. `--dry-run`은 파일 생성과
화면 관측을 수행하지 않습니다. MCP의 명령 관측에는 `init,probe,trusted-local` 소유자 권한이 필요합니다.
준비 결과만 반환하는 `--dry-run`은 `status=blocked`여도 종료 값 0일 수 있으므로 상태와 조치를
함께 확인해야 합니다. Run 판정을 생성하지 않으며 반영 승인이나 현재 소스 검사를 대신하지 않습니다.

생성한 `.ddk/verify.draft.toml`은 `draft=true`이며 목표 검사와 허용 경로를 추정하지 않습니다.
현재 결함이 요청의 정답으로 고정되지 않도록 독립된 필수 목표·보존 검사를 추가해야 합니다.
승인은 정본 생성과 같은 단계·검사·명령 형식을 검증한 뒤 `.ddk/verify.toml`을 새로 발행합니다.
기존 승인 파일과 초안은 보존합니다. 설계에서 가져온 설정도 `draft=true`이면 생성할 수 없습니다.
기준 승인은 호스트 실행이나 모델 비용 승인을 대신하지 않습니다. 설정 파일의 존재·우선순위·해시는
`criteria/bootstrap.json`에 고정하며 이후 변경은 재검사 사유입니다.

## 수정과 반영

```bash
ddk up --case CASE_UUID --repair --confirm-provider --trusted-local --json
ddk up --case CASE_UUID --apply --trusted-local \
  --confirm-local-storage --confirm-quiescence --json
```

먼저 모델 없이 검사하고 수정 제안이 필요할 때 제공자를 생성합니다. 반복 수정은 동일한 시간·출력·
호출·비용 한도를 공유합니다. 기본 Anthropic 가격은 확인 날짜부터 30일이 지나면 `--price`가 필요합니다.
다른 제공자는 case에 연결된 가격 정의가 필요합니다. `--provider`는 `anthropic`, `openai-compatible`,
`claude-cli`, `codex-cli`를 지원하며 호환 API는 `--endpoint`도 지정합니다. CLI 연결은 개인 설정과
실행 도구를 제외하고 빈 임시 디렉터리에서 응답을 요청합니다. 현재 CLI 응답만으로 요금을 확정할 수
없으므로 ready를 부여하지 않습니다. 사용량·추가 요금이 불명확한 API 응답도 같은 원칙을 적용합니다.
구독이나 로컬 주소를 무료의 근거로 사용하지 않습니다. 제한 옵션이 없는 CLI 버전은 실행에 실패합니다.
`ddk change repair`와 MCP의 `ddk_repair`도 같은 제공자·가격 선택을 사용합니다. 별도 수정 명령도
기본 Anthropic 가격이 유효하면 `--price`를 생략할 수 있습니다. 다른 제공자의 가격을 추정하거나
지원하지 않는 제공자·주소 조합을 자동 대체하지 않습니다. 재조회에는 제공자를 생성하지 않습니다.

전체 파일 교체와 정확한 Search/Replace를 모두 지원합니다.

```json
{"patches":[{"path":"index.html","hunks":[{"search":"Broken","replace":"Continue"}]}]}
```

검색 문자열은 현재 파일에 정확히 한 번 있어야 합니다. 빈 문자열·동일한 교체·중복 경로·잘못된
UTF-8·크기 초과·허용 범위 밖 변경은 중단 사유입니다. 과거 실패 요약과 접근성·화면 비교 자료는
마스킹 후 수정 문맥에 포함합니다. 색인은 참고 자료이며 통과 판정의 근거를 대신하지 않습니다.
같은 요청 안에서 동일한 후보가 반복되면 중단합니다.

수정 문맥은 고정된 요구·해시 부분과 회차별 진단 부분으로 구성합니다. 실패 구간·동일 단계의
접근성 차이·화면 비교 수치를 우선 추출하며 원본은 해시와 함께 보관합니다. 제한된 요약만으로
모든 진단을 보존한다고 주장하지 않습니다. 필요하면 다음 명령으로 원본 진단을 조회합니다.

```bash
ddk change evidence --run-id RUN_UUID --artifact-id ARTIFACT_ID --offset 0 --limit 4096 --json
```

전체 파일을 검증하고 UTF-8 전체를 마스킹한 뒤 지정 바이트 범위를 반환합니다. 결과에 연결한
진단·접근성 자료만 허용하며 소스·모델 입력·수정 제안·가격 자료는 제외합니다. 동일 오류가 처음
반복되면 다른 수정 방식을 요구하고 다음 반복에는 `repair_stalled`로 중단합니다. 실패 건수가
같아도 오류가 바뀌면 중단 근거로 사용하지 않습니다. 이전 사례의 해결 경험도 정본 증거로 재검증한
참고 자료입니다. 입력 앞부분의 동일성을 비용 절감 증거로 확대하지 않으며 미정 요금은 차단합니다.

반영 계획은 처음 후보와 최종 후보의 차이입니다. Git 기준으로 복원한 파일과 새 파일의 추가 수정도
포함합니다. 파일·권한·해시를 대조하고 기존 파일을 백업하며 생성·수정·삭제를 기록합니다.
외부 변경을 발견하면 보존하고 충돌이나 복구 상태를 표시합니다. 로컬 저장소 사용과 다른 작업 중지에
대한 확인이 필요하며 기존 반영·복구 서비스를 사용합니다.
검증 후 원본 변경이나 반영 충돌이 발생하면 전체 실행은 `blocked`, 종료 값은 1입니다.
이미 완료한 검증 기록의 `ready`는 보존하되 이를 전체 실행 성공으로 표시하지 않습니다.

## 시험 보고와 Policy

`report_adapter`는 `ddk-json`, `pytest-json`, `junit-xml`, `vitest-json`, `jest-json`, `playwright-json`을
지원합니다. 명령의 `{report}`는 소유한 임시 보고 경로로 교체합니다. 예를 들어
`python3 -m pytest --junitxml={report}`를 사용할 수 있습니다. 자리표시자가 없으면 표준 출력이 보고
원문이어야 합니다. 실행 실패를 정상 보고로 덮어쓰지 않습니다. 보고 누락·모순·해석 실패·실행 0건은
통과하지 않습니다. 기본은 건너뜀도 차단하며, `allow_skipped=true`에서만 허용합니다.
이 경우에도 실행한 시험이 한 개 이상 있어야 합니다. Playwright의 불안정 결과는 실패로 처리합니다.
실제 시험 도구와 의존성은 미리 준비해야 하며 형식 지원을 모든 제품 버전의 실행 증거로 확대하지 않습니다.

Policy는 `forbidden_paths`, `forbid_secret_patterns`, `forbid_regex`, `max_changed_files`,
`max_changed_lines`를 지원합니다. 경로 비교는 대소문자를 구분합니다. 정규식은 그룹·후방 참조·
여러 수량자를 거부합니다. 진단은 검출 값을 제외한 경로·줄 번호·사유만 보관합니다. 변경 줄 수는
삭제 줄과 추가 줄의 합입니다. 호스트·격리 평가기는 동일한 별도 소유 프로세스를 사용하고 개별 검사와
실행 전체의 기한을 적용합니다. 이 검사는 기계적 규칙 검사이며 보안 심사나 요청 의미 전체의 증명은 아닙니다.

## 실제 화면과 접근성 확인

```bash
ddk probe --url http://127.0.0.1:3000 --viewport 1280x800 --out .ddk/probes/latest --json
ddk probe --url 'python3 -m http.server {port} --bind 127.0.0.1' --confirm-execution --json
```

PNG·접근성 자료·DOM·콘솔·페이지·통신 오류·선택 영역의 좌표·정리 영수증을 생성합니다.
다른 출처와 WebSocket을 차단하며 Chromium은 화면을 표시하지 않고 자체 격리를 유지합니다.
통신 요청이 없는 추가 화면도 위반으로 기록합니다. 선택 영역이 없어서 실패한 경우 현재
화면의 PNG·접근성·DOM 자료를 별도 2초 한도 안에서 수집하며 실패 판정은 유지합니다.
화면 저장 전후에 진행 중인 통신의 완료를 제한 시간 안에서 확인하므로 늦은 HTTP 실패도 차단합니다.
시각·언어·시간대·화면 크기를 고정합니다. 고정 검사에는 `expect-ax-tree`, `expect-ax-role`,
`expect-no-console-error`가 추가됐습니다. 화면 저장과 실패 정리 시 접근성 자료를 함께 보관합니다.

`--reference path.png`는 이미지 차이를 생성합니다. 기준 등록은
`--case CASE_UUID --check CHECK_ID --update-reference references/page.png`로 요청합니다.
`--update-baseline`은 같은 옵션입니다. 정상 관측·환경·시각·화면 크기·이미지 해시가 일치해야 합니다.
원래 기준을 변경하지 않고 **새로운 후속 case**를 생성합니다. 선택 영역을 캡처했다면 같은 영역을
검사하도록 기록합니다. 실패한 검사가 자기 기준을 자동 교체할 수 없습니다.

## 현재 자료 검사와 오프라인 증거 재검사

```bash
ddk change gate --repo . --json
ddk change replay --repo . --run-id RUN_UUID --json
ddk install --all --with-hooks
```

`gate`는 SQLite 판정을 사용하지 않고 정본·필수 증거·비용 계산을 검증한 뒤 전체 소스와 설정을
대조합니다. 새 미완료 실행이 있으면 과거 통과로 대체하지 않습니다. 최신 시작 시각이 겹치면 자동
선택을 차단합니다. 바이트·경로 목록·권한·설정이 달라지면 `reopened`, 종료 값 1입니다.
일치한 `passed`만 0입니다. 설정 고정 자료가 없는 과거 사례는 차단합니다. 검사 도중 파일·실행·
설정이 바뀌어도 차단합니다. 반환 이후 임의 편집까지 잠그는 기능은 아닙니다.

선택 설치는 프로젝트에만 적용합니다. 기존 설정은 보존하고 다른 Git 검사나 `core.hooksPath`가
있으면 거부합니다. Claude `Stop` 실패는 종료 값 2로 전달합니다. Git `pre-push`는 표준 입력의
실제 커밋을 모두 대조합니다. 입력 한도는 2MiB·64건입니다. 작업 사본이 통과해도 다른 커밋을
전송할 수 없습니다. 분기 삭제는 별도 검토 대상으로 차단합니다. 정규화 소스와 로컬 기준을 확인하며
이전 커밋 전체나 원격 저장소 정책을 검사하는 것은 아닙니다. 소유자의 검사 우회는 막지 못하므로
서버의 분기 보호는 별도로 적용해야 합니다. 기본 설치에는 이 검사를 추가하지 않습니다.

`replay`는 프로젝트나 모델을 실행하지 않고 봉인한 파일·계약·해시·사용량·가격 계산을 재검사합니다.
과거 기록을 수정하지 않으며 증거가 온전할 때만 원래 판정을 반환합니다. 종료 값 0은 증거 재검사
성공을 뜻하므로 원래 `blocked`인 기록도 포함합니다. `replay_decision`을 함께 확인해야 합니다.
실제 화면 실행을 반복하거나 새 기준으로 과거 소프트웨어를 통과시키는 명령이 아닙니다.

## SQLite와 MCP

정본 경로는 `.ddk/verified-change/1/`의 기존 `cases/<id>/case.json`, `runs/<id>/run.json`,
`applies/<id>/apply.json`입니다. SQLite·FTS5는 정본 기록 후 갱신하는 재생성 가능한 색인입니다.
`ddk change reindex`는 JSON과 증거를 검증한 후 별도 파일을 만들어 원자적으로 교체합니다.
동일성은 정규화 행과 조회 결과의 동일성을 뜻합니다. SQLite 파일·WAL의 바이트 동일성을 뜻하지 않습니다.
색인 오류는 정본 저장을 취소하지 않으며 재구축 안내를 표시합니다. 실패 이력 조회 오류도 참고 문맥만
생략합니다. 전체 16개 논리 테이블과 필드는 [색인 안내](CATALOG.md)에 있습니다.

`ddk serve`는 `ddk_doctor`, `ddk_init`, `ddk_verify`, `ddk_repair`, `ddk_status`, `ddk_probe`,
`ddk_apply`, `ddk_query_ledger`, `ddk_gate_status`, `ddk_replay`, `ddk_read_evidence`와 기존 설계·준비·버전 도구를 제공합니다. 추가 필드·잘못된 형식·
2MiB 초과 stdio 입력은 거부합니다. 검사 도구는 격리 실행을 유지합니다. 쓰기·제공자·화면 관측은
서버 소유자가 지정한 `DDK_MCP_REPOSITORY`와 `DDK_MCP_CAPABILITIES` 및 요청의 `approved=true`가
함께 필요합니다. 권한 이름은 `init,repair,probe,apply,trusted-local`이며 기본은 허용 권한 없음입니다.
호스트 실행은 `trusted-local` 권한이 추가로 필요합니다. 호환 API는 소유자가 지정한
`DDK_MCP_PROVIDER_ENDPOINT`와 요청 주소도 같아야 합니다. 요청자가 API 키의 전송 대상을
다른 주소로 변경할 수 없습니다. 원장 조회는 SQL에서 안전한 열만 선택하며
임의 SQL·소스·요청 원문·진단 원문을 공개하지 않습니다.

`ddk_read_evidence`는 진단의 공개 범위를 제한하기 위해 `repair` 소유자 권한과 `approved=true`가
필요합니다. 현재 자료 검사·증거 재검사는 CLI와 같은 서비스를 사용하고 제한된 정보만 반환합니다.

ready는 해당 실행의 고정된 필수 검사와 무변조·정리·비용 조건을 만족했다는 뜻입니다.
앱의 무결함·유료 모델 효과·독립 사용자 채택·제품 우위·GitHub 별 수를 보장하지 않습니다.
[후속 계획](../ROADMAP.ko.md)은 다음 검증 우선순위를 구분합니다.
