# 검증 가능한 화면 변경: 저장과 필드

상태: 미구현 목표 계약. 범위: [목표 설계](34-verified-change-design.md)의 파일 자료·실행·복구.

## 1. DB 선택과 논리 테이블

**첫 구현은 실제 DB·ORM·서버를 추가하지 않는다.** 현재 JSON 저장을 보강한다. 사례별 자료를 보존하는 데 외부 조회·협업 요구가 없고, 현재 코드와 저장 위치를 재사용할 수 있기 때문이다. 파일 관리가 복잡한 조회·관계 검증·단일 작성자 대기·복구에서 불리하다는 측정 결과가 있으면 SQLite를 다시 비교한다. ‘DB가 없으므로 단순하다’는 판단을 하지 않는다. [SQLite의 적합 범위](https://www.sqlite.org/whentouse.html), [설계 전 대안](reviews/2026-10-14-analysis.md).

다음은 파일 구조의 **논리 테이블**이며 실제 SQL 테이블이 아니다. 배열의 포함 관계가 부모 키를 제공한다. 관계의 ID·고유성·참조는 별도 의미 검사로 강제한다. 대상 앱의 DB와 사업 데이터를 정의하거나 변경하지 않는다.

| 논리 테이블 | 정본·물리 저장 | 키·관계 | 조회 방식 |
|---|---|---|---|
| cases | `cases/<case_id>/case.json` / Case | case_id 고유; 이전 case는 supersedes_case_id | ID로 직접 경로 조회 |
| requirements | Case.requirements | (case_id, requirement_id) 고유 | 사례 안의 ID 대응 |
| checks | Case.checks | (case_id, check_id) 고유 | 요구의 check_ids와 연결 |
| runs | `runs/<run_id>/run.json` / Run | run_id 고유; case_id 참조 | ID 직접 조회; 자동 최신 선택 없음 |
| check_results | Run.results | (run_id, round_no, phase, check_id) 고유 | 검사·후보 회차별 비교 |
| file_changes | Run.changes | (run_id, path) 고유; 최종 후보·requirement_ids 참조 | 반영할 경로로 조회 |
| artifacts | Run.artifacts | (run_id, artifact_id) 고유; 실제 일반 파일 참조 | ID→경로·해시 |
| model_calls | Run.model_calls | call_id 고유; 요청 순번·회차 참조 | 비용·호출 상한 집계 |
| apply_transactions | `applies/<apply_id>/apply.json` / Apply | apply_id 고유; case_id/run_id와 run_sha256 참조 | 복구 ID 직접 조회 |

별도 영구 인덱스는 만들지 않는다. 목록·집계는 조회 결과이며 정본이 아니다. 나중에 캐시를 추가하더라도 삭제 후 정본에서 재생성할 수 있어야 한다. SQLite를 도입하면 실제 컬럼·외래키·제약·전환을 별도 결정하며 이 논리 표를 현재 DB로 소개하지 않는다.

## 2. 저장 위치와 공개 순서

```text
<repo>/.ddk/verified-change/1/
  cases/<case_id>/case.json
  cases/<case_id>/inputs/<owned-relative-path>
  runs/<run_id>/.pending/run.json
  runs/<run_id>/artifacts/<owned-relative-path>
  runs/<run_id>/run.json
  applies/<apply_id>/apply.json
  applies/<apply_id>/before/<owned-relative-path>
  applies/<apply_id>/staged/<owned-relative-path>
  locks/apply.lock
  locks/model/<case_id>.lock
```

기존 `.ddk/cases/C-NNN`과 전역 schema-version 파일은 변경하지 않는다. 새 namespace의 첫 판은 `verified-change/1`이다. `.ddk` 자체가 symlink·외부 공유 경로이면 안전한 저장 위치를 명시하거나 중단한다. 파일 기본 권한은 개인 사용자만 접근 가능한 디렉터리 0700·자료 0600이며 프로그램 권한은 별도 보존한다.

사례 입력은 승인된 일반 파일을 먼저 보관하고 검증한 뒤 `case.json`을 마지막에 공개한다. 동일 case_id에 다른 내용을 저장하지 않는다. case.json의 정확한 바이트 해시를 run.case_sha256에 기록한다. schema 검증 이전에 중복 JSON 키·NaN·Infinity·잘못된 UTF-8·외부 참조를 거부한다. format 검사를 명시적으로 활성화한다. [JSON Schema 2020-12](https://json-schema.org/draft/2020-12/json-schema-validation).

입력·후보·환경·검사 묶음 해시는 역할별로 정렬한 `(path, sha256, mode, size_bytes)` 목록을 고정 UTF-8 JSON 바이트로 저장한 뒤 계산한다. 상대 경로를 UTF-8 바이트 순서로 정렬하고 키 순서·구분·개행을 한 구현에서 고정한다. 저장한 정확한 바이트를 기준으로 하며 RFC 8785 준수를 주장하지 않는다. 외부 이름·대소문자·Unicode 충돌은 입력에서 거부한다. [RFC 8785](https://www.rfc-editor.org/rfc/rfc8785).

진행 상태는 `.pending/run.json`에 원자적으로 교체한다. **모델 요청 전 예약과 반영 전 기록은 해당 작업보다 먼저 내구성을 확인한다.** 기록이 실패하면 다음 동작을 하지 않는다. 조회는 pending을 완료 결과와 구분한다. 중단된 요청의 예약을 없애지 않는다.

실행 산출물은 소유한 경로에 먼저 저장·동기화·해시 확인한다. 마지막으로 완료 manifest를 `run.json`에 공개한다. 완료 manifest가 없거나 참조 해시가 다르면 완료 결과로 조회하지 않는다. pending을 정리하는 일은 성공 조건이 아니며 남은 기록이 실제 상태와 충돌하면 중단 기록으로 유지한다. 완료 자료를 다시 수정하지 않는다.

### 파일 교체와 내구성

1. 대상과 같은 파일 공간의 안전한 임시 파일을 배타 생성한다.
2. 전체 바이트를 작성하고 flush·파일 fsync를 한다.
3. 내용을 검증하고 이름을 교체한다. 지원 환경에서는 해당 디렉터리도 동기화한다.
4. 파일 존재·일반 유형·mode·해시를 다시 확인한다.

단일 파일 교체와 다파일 반영은 다르다. Windows·macOS·Linux의 실제 지원 동작을 검사하며 지원하지 않는 디렉터리 동기화를 통과로 숨기지 않는다. 전원 중단·디스크 손상·원격 동기화까지 절대 보장을 주장하지 않는다. 내구성이 확인되지 않는 환경에서는 원본 반영을 막고 자료의 보장 제한을 표시한다. [Python 3.12](https://docs.python.org/3.12/library/os.html#os.replace), [fsync의 디렉터리 제한](https://man7.org/linux/man-pages/man2/fsync.2.html).

Environment는 locale·timezone·실행기·브라우저·의존성·글꼴·fixture·정책의 고정 정보를 담은 일반 JSON 파일이며 Case.inputs의 environment 역할로 보관한다. 기준과 후보의 비교에서 시간·임시 작업 ID·포트처럼 실행마다 달라지는 식별 정보는 환경 해시에 넣지 않고 소유 작업 기록으로 구분한다. isolated의 이미지·브라우저·정책 확인이 없으면 해당 보장 수준을 부여하지 않는다.

## 3. 요청·회차·비용의 소유자

run_id는 한 요청의 안정된 UUID이며 CLI·MCP 재요청 식별자로도 사용한다. 전체 저장 namespace에서 배타 생성하여 같은 ID의 다른 case·작업·후보·상한을 거부한다. `request_sha256`은 승인된 요청 바이트의 case 해시·작업·후보·명령·상한·실행 방식을 포함한다. 이 해시는 사용자의 실행 권한을 대신하지 않는다. 같은 ID·같은 해시는 상태 조회만 제공하고 작업을 다시 시작하지 않는다. 다른 해시는 `request_conflict`다.

`verify`는 수정·모델 호출 없이 회차 0을 검사한다. `repair`는 같은 사례의 완료 manifest와 고정 후보를 가진 source_run_id를 참조하는 새 요청이며 한 run 안에서 회차 0과 수정 회차 1·2를 한다. 자동 수정·재검사·제공자 재시도 때문에 새 run을 만들지 않는다. 전체 시간·횟수·비용 상한은 그 요청 하나가 소유한다. 사용자가 새 repair를 명시적으로 선택해야 새로운 요청이 된다.

기준 검사는 round_no=0·phase=baseline에 기록한다. 후보는 phase=candidate와 각 회차에 기록한다. 최종 판정은 `latest_round`의 후보와 기준·정책 검사만 사용하며 이전 회차의 성공으로 마지막 실패를 덮지 않는다. 이전 실패·후보 해시는 `rounds`와 자료에 유지한다. Run.changes는 최종 후보의 변경이며 예전 회차의 변경 묶음은 별도 자료로 보관한다.

결과와 모델 호출이 참조한 round_no는 rounds에 존재해야 한다. ModelCall.round_no는 수정할 입력 후보의 회차를 가리킨다. 그 호출로 만든 다음 후보는 별도 회차에 기록한다. ready/manual-review의 최신 회차는 finished_at이 존재하고 후보·변경 해시가 최종 결과와 일치해야 한다. 회차의 UTC 값은 표시용이며 시간 상한은 Run.duration_ms로 확인한다.

HTTP 시도마다 call_id와 실제 attempt_no를 생성하고 SDK 재시도는 0으로 설정한다. 가격·최대 입력·출력·부가 비용을 확인하지 못하면 예약을 생성하지 않고 `price_unavailable`로 중단한다. 가격 자료는 해당 호출의 immutable artifact다. 계산한 비용은 청구서 확정 금액이 아니다.

예약은 pending 기록에 먼저 보존한다. `settled`만 실제 usage로 계산한 값을 사용하며 `reserved/unknown`은 예약 전체를 유지한다. 비용 계산의 상한은 정산 합계+미정 예약 합계다. 취소·연결 종료·새 run으로 미정 예약을 제거하지 않는다. 같은 사례에 미정 요청이 남으면 추가 모델 요청을 막고 예약과 원래 실행을 보존한다. 첫 판은 비용 조정·제공자 비용 조회 기능을 제공하지 않는다. 미정 사례도 추가 모델 호출 없이 검사·조회·내보내기를 사용할 수 있고, 원본 반영은 별도 반영 계약을 따른다. 중단한 모델 요청은 자동 재개하지 않는다. 조정 기능이 필요하면 근거·권한·원본 보존을 포함하는 별도 계약을 검토한다. 미정 사례를 새 case로 바꾸어 자동 재시도하는 동작은 금지한다.

서로 다른 run_id도 같은 사례의 모델 요청에는 `locks/model/<case_id>.lock`을 사용한다. 기존 Lock 필드를 재사용하고 소유 run과 경로의 case 관계를 확인한다. 요청 허용 확인·모든 pending/완료 기록의 미정 예약 조회·새 예약 저장과 내구성 확인·제공자 시도·정산 저장까지 한 소유자가 잠금을 유지한다. 예약 직후 중단되면 해당 예약과 잠금을 보존하고 새 모델 요청을 차단한다. 미정 기록을 내구성 있게 보존하고 정상 종료한 소유자가 잠금을 해제하더라도 다음 소유자는 그 기록 때문에 추가 호출을 거부한다. PID만으로 잠금을 탈취하지 않는다. 검사·상태 조회는 비용 잠금 없이 허용한다. 잠금 대기도 실행 시간 상한에 포함하며 원본 반영 잠금과 동시에 획득하지 않는다.

settled는 입력·출력 usage, 계산 비용, 완료 시각과 kind=price 자료가 모두 있을 때만 사용한다. 실제 계산 비용이 예약을 초과하면 값을 보존하되 ready/manual-review는 금지하고 `blocked`와 cost_reservation_exceeded 조치를 기록한다. unknown/reserved의 계산 값으로 예약을 축소하지 않는다. 미정 비용은 예약 전액을 유지하는 조건에서 검사 판정과 구분하며, 그것만으로 필수 검사를 실패로 바꾸지 않는다.

## 4. 관계·의미 제약

JSON Schema는 유형·필드·열거값의 정본이다. 아래 규칙은 schema만으로 확인할 수 없으므로 저장 시와 조회 시 별도로 검증한다.

| ID | 반드시 지킬 조건 |
|---|---|
| SC-01 | 요구 ID·검사 ID·자료 ID·경로가 각 부모 범위에서 고유하며 모든 참조가 존재한다 |
| SC-02 | 필수 요구의 check_ids는 비어 있지 않고 연결한 모든 검사가 필수다; 첫 판은 OR 검사군을 제공하지 않는다; 모든 사용자 요구의 연결 범위가 표시된다 |
| SC-03 | 검사 정의 경로·해시는 Case.inputs의 criteria 역할과 일치하며 기준·fixture·reference·environment 경로는 변경 허용 범위에서 제외한다 |
| SC-04 | `preserve`의 기준 결과가 필수 후보보다 먼저 존재·통과하며 `target`의 기준 실패는 보존 실패로 계산하지 않는다 |
| SC-05 | `ready`와 `manual-review`는 종료·시간·필수 결과·관찰 주체·무결성·정리·후보·환경 관계를 모두 만족한다; 필수 항목의 skipped/unavailable/flaky는 통과가 아니다 |
| SC-06 | 각 회차의 결과 키가 고유하고 모든 결과·모델 호출의 회차가 존재한다; 기준 결과의 회차는 0이며 최신 회차의 완료·후보·변경 해시가 최종 결과와 대응한다 |
| SC-07 | 필수 화면·정책 결과와 핵심 보존 동작은 trusted-observer의 실제 자료 ID를 포함한다; 빈 artifact_ids·고아 참조·project-report만으로 이 범위의 ready/manual-review를 판단하지 않는다 |
| SC-08 | create는 고정 기준에 없는 경로이며 이전 해시·mode가 null, update는 Case.inputs의 source 역할의 해시·mode와 일치한다; after mode는 기존 권한을 보존한다 |
| SC-09 | model call 순번·회차·가격 자료 종류가 유효하고 settled에는 usage가 존재한다; 예약 초과·전체 한도 초과를 통과로 표시하지 않으며 unknown/reserved의 계산 비용으로 예약을 축소하지 않는다; 같은 사례의 요청 승인·미정 확인·예약·시도·정산은 하나의 비용 잠금으로 직렬화한다 |
| SC-10 | 검사·자료·후보 실제 파일은 일반 파일·경로 경계·크기·해시가 일치한다; symlink·외부 참조를 조회하지 않는다 |
| SC-11 | 종료 run과 고정 case의 바이트를 변경하지 않으며 run_id와 request_sha256의 재사용 계약을 지킨다 |
| SC-12 | apply는 ready인 완료 run 바이트·변경 해시·대상 전체 상태·소유 잠금·원본 사본·준비 파일을 확인한 뒤만 쓰기를 시작한다 |
| SC-13 | 동일 apply_id는 같은 요청의 기존 상태 조회다; 다른 요청을 같은 ID로 반영하지 않는다 |
| SC-14 | 공개 승인 없는 sensitive artifact는 공개 내보내기에 포함하지 않는다; trace·원시 응답은 기본 제외한다 |

## 5. 화면 동작 정의

Flow는 별도 고정 JSON 파일이며 Check.definition_path/sha256으로 참조한다. 한 Flow의 steps는 같은 context에서 실행한다. entry_path와 goto/expect-url 값은 하나의 `/`로 시작하는 소유 앱의 상대 URL이다. 원문에 역슬래시·ASCII 제어문자 U+0000~001F·U+007F가 있거나 `//`로 시작하면 거부한다. 실제 브라우저와 같은 URL 해석 후 scheme·host·port가 소유 앱의 origin과 일치하는지도 확인한다. `/\\example.org/x`처럼 외부 origin으로 해석될 수 있는 문자열을 상대 경로로 허용하지 않는다. [WHATWG URL](https://url.spec.whatwg.org/#relative-slash-state).

이 정책은 최초 이동·HTTP redirect·추가 페이지·하위 요청·WebSocket에도 적용한다. 별도 기준이 없는 첫 판에서는 Service Worker를 차단하고 외부 주소·승인하지 않은 scheme을 거부한다. BrowserContext.route 하나로 모든 redirect와 외부 연결을 차단했다고 주장하지 않으며, 격리 실행의 네트워크 차단과 실제 요청·최종 origin 관찰을 함께 확인한다. 우회가 발견되면 blocked다. [Playwright의 요청 제어 범위](https://playwright.dev/python/docs/api/class-browsercontext#browser-context-route), [네트워크 검사](https://playwright.dev/python/docs/network).

| action | 필요 필드 | 금지·의미 |
|---|---|---|
| goto | value=상대 URL | selector·count·reference 값은 null; 외부 URL 금지 |
| click·expect-visible | selector | value·count·reference 값은 null |
| fill·expect-text | selector·value | 빈 문자열 허용; count·reference 값은 null |
| press | selector·value | 빈 문자열 금지; count·reference 값은 null |
| expect-count | selector·count | value·reference 값은 null |
| expect-url | value=상대 URL | selector·count·reference 값은 null |
| snapshot | reference_path·rgb_tolerance·max_mismatch_ppm | value·count는 null; 고정된 이미지 기대와 비교; selector가 있으면 지정 영역만 비교 |

다른 action의 이미지 관련 값은 null이다. step_id는 Flow 안에서 고유하다. 각 action의 미사용 필드는 null을 강제하며 의미 없는 값을 무시하지 않는다. snapshot의 이미지가 Case.inputs에서 reference로 고정되지 않았거나 크기·mask·환경 조건이 없으면 비교하지 않고 unavailable이다. 현재 판에는 자동 mask와 기준 갱신을 제공하지 않는다. 전체 화면 또는 승인된 영역에서 RGB 각 성분 차이 한도를 넘는 픽셀 비율을 백만분율로 비교한다. 같은 밝기의 색 변경도 검사하며 SSIM은 보조 자료다. 비교식을 변경하면 새 계약 판과 새 case가 필요하다. DOM·사용 동작은 별도 검사이며 이미지 비교로 대체하지 않는다.

fixture_sha256은 사례의 fixture 역할 입력 묶음 해시다. 모든 시나리오의 데이터 초기화 결과와 고정 조건을 기록한다. 원래 외부 서버와 실제 데이터 저장까지 검증했다고 확대하지 않는다. 자동 생성한 임의 JavaScript를 Flow 단계로 실행하지 않는다.

## 6. 원본 반영 상태·잠금·복구

| 상태 | 허용되는 다음 상태 | 의미 |
|---|---|---|
| prepared | applying·conflict | 전체 사전 검사·사본·준비 파일·기록 내구성 확인 |
| applying | applied·rolling_back·unknown | 대상 파일을 반영 중 |
| applied | 없음 | 전체 사후 상태 확인과 기록 완료 |
| rolling_back | rolled_back·unknown | 예상한 자신의 새 상태만 복구 |
| rolled_back | 없음 | 이전 전체 존재·유형·mode·해시 확인 |
| conflict | 없음 | 쓰기 전 충돌; 원본 유지 |
| unknown | 없음 | 자동 쓰기·재반영·자료 삭제 금지; 사용자 확인 필요 |

상태 전이 기록은 파일 쓰기보다 먼저 보존한다. applying 중 첫 쓰기 전에 prepared의 내구성을 확인한다. 복구는 무조건적인 원본 사본 복사가 아니다. 각 파일의 현재 상태가 after와 같을 때만 before로 복구하며, before와 같으면 유지한다. create 복구의 삭제는 자신의 새 파일 상태가 전부 같을 때만 허용한다. 다른 내용·mode·파일 유형·존재 여부는 외부 변경으로 보고 unknown으로 중단한다.

entries.path는 반영 안에서 고유하고 run의 변경 경로와 정확히 일치한다. applied는 모든 entry=written과 postcheck_at이 필요하다. rolled_back은 모든 entry=restored와 전체 복구 확인 시각이 필요하며, 이전 상태를 그대로 유지한 경로도 확인 후 restored로 기록한다. prepared/conflict에는 written·restored entry가 있을 수 없다. 부분 진행 상태는 applying/rolling_back/unknown에만 보존한다.

반영 잠금은 배타 생성하는 apply.lock이며 owner ID·nonce·PID·process 시작 식별·생성 시각을 보관한다. PID 존재 여부만으로 잠금을 제거하지 않는다. 정상 종료는 자신의 nonce와 파일 상태가 맞을 때만 해제한다. 비어 있거나 손상된 잠금, 시작 정보가 없는 잠금, 다른 호스트 잠금은 자동 제거하지 않는다. 복구가 미확정이면 잠금 또는 동등한 쓰기 금지 상태를 유지한다.

잠금은 딸깍 작성자끼리의 계약이며 외부 편집기의 쓰기를 막지 않는다. 원본 반영에는 사용자 협조로 동시 쓰기를 중지한 조건이 필요하다. 네트워크 파일 공간·동기화 도구·다른 호스트의 자동 작성이 가능하거나 내구성을 확인하지 못하면 내보내기만 제공한다. 다파일 반영의 외부 관찰상 원자성은 보장하지 않는다.

## 7. 보존·삭제·전환

일반 완료 사례는 사용자가 선택해 삭제하며 자동 기한 삭제는 첫 범위에 없다. 기본 자료 상한을 초과하면 새 작업을 막고 대상·크기를 제시한다. active run·미정 비용·prepared/applying/rolling_back/unknown 반영·복구 원본은 삭제할 수 없다. 삭제는 소유 ID·일반 경로·참조 관계를 다시 확인한 경우만 실행한다.

공개 내보내기는 필요한 변경과 요약만 기본 포함한다. 원본 내용·가격 외 모델 응답·trace·로그·화면은 민감 여부와 명시적 승인에 따라 제외한다. 삭제는 다른 도구의 동기화 사본이나 외부 제공자의 기록 삭제를 보장하지 않는다.

알 수 없는 schema 판은 변경 없이 거부한다. 이전 workspace 자료는 별도 조회 경로를 유지하고 새 결과로 자동 변환하지 않는다. 명시적 변환은 원본 사본·원본 해시·새 schema 검증·조회 비교를 포함하며 현재 제품 검증 수준을 승격하지 않는다. 실패하면 원본과 새 자료를 유지하고 성공으로 표시하지 않는다.

## 8. 컬럼의 타입·null·기본값

아래 필드표는 JSON Schema에서 생성한 명세다. 모든 필드는 명시적으로 존재해야 하며 default로 누락을 보완하지 않는다. null 허용 여부는 표에 표시한다. SQL을 도입한다면 string/UUID/hash/time은 TEXT, integer/boolean은 INTEGER, object/array는 정규화하거나 JSON으로 표현할 후보이나 실제 DB 설계는 별도 결정이다.

키·관계·고유성은 §1·§4, 상태 전이는 §6, 물리 자료는 §2가 담당한다. 추가 선언값만 나열하고 관계 검사를 생략하는 구현은 이 계약을 충족하지 않는다.

<!-- generated-field-tables -->

### Viewport

화면 크기

| 컬럼 | 타입 | null | 기본값 | 의미·제약 |
|---|---|---|---|---|
| `width` | integer | 불가 | 없음; 명시 필수 | 화면 너비; minimum=1; maximum=8192 |
| `height` | integer | 불가 | 없음; 명시 필수 | 화면 높이; minimum=1; maximum=8192 |

### Limits

승인된 실행 상한

| 컬럼 | 타입 | null | 기본값 | 의미·제약 |
|---|---|---|---|---|
| `step_timeout_ms` | integer | 불가 | 없음; 명시 필수 | 단계 최대 시간; minimum=1; maximum=3600000 |
| `run_timeout_ms` | integer | 불가 | 없음; 명시 필수 | 실행 전체 최대 시간; minimum=1; maximum=86400000 |
| `cleanup_timeout_ms` | integer | 불가 | 없음; 명시 필수 | 정리 최대 시간; minimum=1; maximum=60000 |
| `max_fix_attempts` | integer | 불가 | 없음; 명시 필수 | 최대 수정 횟수; minimum=0; maximum=10 |
| `max_provider_requests` | integer | 불가 | 없음; 명시 필수 | 제공자 요청 총 상한; minimum=0; maximum=100 |
| `budget_micro_usd` | integer | 불가 | 없음; 명시 필수 | 예약 포함 비용 상한; minimum=0; maximum=9007199254740991 |
| `max_file_bytes` | integer | 불가 | 없음; 명시 필수 | 일반 파일 상한; minimum=1; maximum=9007199254740991 |
| `max_output_bytes` | integer | 불가 | 없음; 명시 필수 | 실행 출력 상한; minimum=1; maximum=9007199254740991 |
| `max_artifact_bytes` | integer | 불가 | 없음; 명시 필수 | 자료 총 상한; minimum=1; maximum=9007199254740991 |
| `max_changed_files` | integer | 불가 | 없음; 명시 필수 | 변경 파일 수 상한; minimum=1; maximum=1000 |
| `cpu_millis_per_worker` | integer | 불가 | 없음; 명시 필수 | 작업 하나의 CPU 상한; 1000은 CPU 하나; minimum=1; maximum=64000 |
| `memory_bytes_per_worker` | integer | 불가 | 없음; 명시 필수 | 작업 하나의 메모리 상한; minimum=1; maximum=9007199254740991 |
| `max_processes_per_worker` | integer | 불가 | 없음; 명시 필수 | 작업 하나의 최대 프로세스 수; minimum=1; maximum=100000 |
| `browser_shm_bytes` | integer | 불가 | 없음; 명시 필수 | 검사 작업의 공유 메모리 상한; minimum=1; maximum=9007199254740991 |

### Requirement

요구 테이블; 사례 안의 ID 고유

| 컬럼 | 타입 | null | 기본값 | 의미·제약 |
|---|---|---|---|---|
| `requirement_id` | string | 불가 | 없음; 명시 필수 | 사례 안의 요구 ID; minLength=1; maxLength=128 |
| `description` | string | 불가 | 없음; 명시 필수 | 수용할 결과; minLength=1; maxLength=2000 |
| `required` | boolean | 불가 | 없음; 명시 필수 | 필수 요구 |
| `check_ids` | array<string> | 불가 | 없음; 명시 필수 | 연결한 검사 ID; minItems=1; maxItems=1000 |

### Check

검사 정의 테이블; 검사 기준 파일은 고정

| 컬럼 | 타입 | null | 기본값 | 의미·제약 |
|---|---|---|---|---|
| `check_id` | string | 불가 | 없음; 명시 필수 | 사례 안의 검사 ID; minLength=1; maxLength=128 |
| `role` | enum preserve, target, policy | 불가 | 없음; 명시 필수 | 검사의 역할 |
| `required` | boolean | 불가 | 없음; 명시 필수 | 필수 검사 |
| `kind` | enum command, test, browser, visual, policy | 불가 | 없음; 명시 필수 | 검사 종류 |
| `definition_path` | string | 불가 | 없음; 명시 필수 | 기준 디렉터리 안의 상대 경로; 실제 경계는 별도 검사; minLength=1; maxLength=1024; pattern=^(?!/)(?!.*\\)(?!.*(?:^\|/)\.\.(?:/\|$))(?!.*\u0000).+$ |
| `definition_sha256` | string | 불가 | 없음; 명시 필수 | 전체 SHA256; pattern=^[0-9a-f]{64}$ |
| `command_argv` | array<string> | 불가 | 없음; 명시 필수 | 셸 평가 없는 명령 배열; minItems=0; maxItems=100 |
| `viewport` | Viewport | 허용 | 없음; 명시 필수 |  |
| `timeout_ms` | integer | 불가 | 없음; 명시 필수 | 검사 최대 시간; minimum=1; maximum=3600000 |

### InputFile

고정한 입력 파일 목록

| 컬럼 | 타입 | null | 기본값 | 의미·제약 |
|---|---|---|---|---|
| `path` | string | 불가 | 없음; 명시 필수 | 기준 디렉터리 안의 상대 경로; 실제 경계는 별도 검사; minLength=1; maxLength=1024; pattern=^(?!/)(?!.*\\)(?!.*(?:^\|/)\.\.(?:/\|$))(?!.*\u0000).+$ |
| `sha256` | string | 불가 | 없음; 명시 필수 | 전체 SHA256; pattern=^[0-9a-f]{64}$ |
| `mode` | integer | 불가 | 없음; 명시 필수 | 파일 권한; minimum=0; maximum=511 |
| `size_bytes` | integer | 불가 | 없음; 명시 필수 | 파일 크기; minimum=0; maximum=9007199254740991 |
| `role` | enum source, criteria, fixture, reference, environment | 불가 | 없음; 명시 필수 | 입력의 역할 |

### Case

고정한 사례 정의; 파일 해시는 실행에서 참조

| 컬럼 | 타입 | null | 기본값 | 의미·제약 |
|---|---|---|---|---|
| `record_type` | const case | 불가 | 없음; 명시 필수 |  |
| `schema_version` | const verified-change/1 | 불가 | 없음; 명시 필수 |  |
| `case_id` | string | 불가 | 없음; 명시 필수 | UUID v4 식별자; pattern=^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$; format=uuid |
| `legacy_alias` | string | 허용 | 없음; 명시 필수 | 기존 사례 별칭; minLength=1; maxLength=128 |
| `supersedes_case_id` | string | 허용 | 없음; 명시 필수 | UUID v4 식별자; pattern=^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$; format=uuid |
| `created_at` | string | 불가 | 없음; 명시 필수 | UTC 시각; pattern=Z$; format=date-time |
| `request` | string | 불가 | 없음; 명시 필수 | 요청 원문; minLength=1; maxLength=8192 |
| `scope_paths` | array<string> | 불가 | 없음; 명시 필수 | 허용된 프로그램 변경 경로; minItems=1; maxItems=1000 |
| `assurance_required` | enum isolated, trusted-local | 불가 | 없음; 명시 필수 | 승인된 최소 실행 경계 |
| `baseline_tree_sha256` | string | 불가 | 없음; 명시 필수 | 전체 SHA256; pattern=^[0-9a-f]{64}$ |
| `environment_sha256` | string | 불가 | 없음; 명시 필수 | 전체 SHA256; pattern=^[0-9a-f]{64}$ |
| `evaluator_sha256` | string | 불가 | 없음; 명시 필수 | 전체 SHA256; pattern=^[0-9a-f]{64}$ |
| `inputs` | array<InputFile> | 불가 | 없음; 명시 필수 | 고정 입력 목록; minItems=1; maxItems=100000 |
| `requirements` | array<Requirement> | 불가 | 없음; 명시 필수 | 요구 목록; minItems=1; maxItems=100 |
| `checks` | array<Check> | 불가 | 없음; 명시 필수 | 검사 정의 목록; minItems=1; maxItems=1000 |
| `limits` | Limits | 불가 | 없음; 명시 필수 |  |

### CheckResult

검사 결과 테이블; run 안의 phase/check 고유

| 컬럼 | 타입 | null | 기본값 | 의미·제약 |
|---|---|---|---|---|
| `check_id` | string | 불가 | 없음; 명시 필수 | 사례의 검사 ID; minLength=1; maxLength=128 |
| `phase` | enum baseline, candidate | 불가 | 없음; 명시 필수 | 검사 대상 |
| `status` | enum passed, failed, skipped, unavailable, flaky | 불가 | 없음; 명시 필수 | 검사 결과 |
| `exit_code` | integer | 허용 | 없음; 명시 필수 | 명령 종료 값; minimum=-2147483648; maximum=2147483647 |
| `executed_count` | integer | 허용 | 없음; 명시 필수 | 실행한 시험 수; minimum=0; maximum=9007199254740991 |
| `failed_count` | integer | 허용 | 없음; 명시 필수 | 실패한 시험 수; minimum=0; maximum=9007199254740991 |
| `skipped_count` | integer | 허용 | 없음; 명시 필수 | 건너뛴 시험 수; minimum=0; maximum=9007199254740991 |
| `retry_count` | integer | 불가 | 없음; 명시 필수 | 검사 재시도 수; minimum=0; maximum=10 |
| `duration_ms` | integer | 불가 | 없음; 명시 필수 | 검사 시간; minimum=0; maximum=9007199254740991 |
| `reason_code` | string | 허용 | 없음; 명시 필수 | 실패 또는 미확인 코드; minLength=1; maxLength=128 |
| `artifact_ids` | array<string> | 불가 | 없음; 명시 필수 | 자료 ID; minItems=0; maxItems=1000 |
| `evidence_origin` | enum trusted-observer, project-report | 불가 | 없음; 명시 필수 | 판정 자료의 관찰 주체; 프로그램 자체 보고와 구분 |
| `round_no` | integer | 불가 | 없음; 명시 필수 | 기준은 0, 후보는 해당 수정 회차; minimum=0; maximum=10 |

### FileChange

변경 테이블; 생성은 이전 값 없음, 갱신은 이전 값 필수

| 컬럼 | 타입 | null | 기본값 | 의미·제약 |
|---|---|---|---|---|
| `path` | string | 불가 | 없음; 명시 필수 | 기준 디렉터리 안의 상대 경로; 실제 경계는 별도 검사; minLength=1; maxLength=1024; pattern=^(?!/)(?!.*\\)(?!.*(?:^\|/)\.\.(?:/\|$))(?!.*\u0000).+$ |
| `action` | enum create, update | 불가 | 없음; 명시 필수 | 변경 종류 |
| `before_sha256` | string | 허용 | 없음; 명시 필수 | 전체 SHA256; pattern=^[0-9a-f]{64}$ |
| `after_sha256` | string | 불가 | 없음; 명시 필수 | 전체 SHA256; pattern=^[0-9a-f]{64}$ |
| `before_mode` | integer | 허용 | 없음; 명시 필수 | 이전 권한; minimum=0; maximum=511 |
| `after_mode` | integer | 불가 | 없음; 명시 필수 | 새 권한; minimum=0; maximum=511 |
| `after_artifact_id` | string | 불가 | 없음; 명시 필수 | 새 파일 자료 ID; minLength=1; maxLength=128 |
| `requirement_ids` | array<string> | 불가 | 없음; 명시 필수 | 변경의 요구 ID; minItems=1; maxItems=1000 |

### Artifact

자료 테이블; 공개 승인 없는 민감 자료는 외부 제공 금지

| 컬럼 | 타입 | null | 기본값 | 의미·제약 |
|---|---|---|---|---|
| `artifact_id` | string | 불가 | 없음; 명시 필수 | run 안의 자료 ID; minLength=1; maxLength=128 |
| `kind` | enum log, trace, screenshot, diff, source, patch, price, data | 불가 | 없음; 명시 필수 | 자료 종류 |
| `path` | string | 불가 | 없음; 명시 필수 | 기준 디렉터리 안의 상대 경로; 실제 경계는 별도 검사; minLength=1; maxLength=1024; pattern=^(?!/)(?!.*\\)(?!.*(?:^\|/)\.\.(?:/\|$))(?!.*\u0000).+$ |
| `sha256` | string | 불가 | 없음; 명시 필수 | 전체 SHA256; pattern=^[0-9a-f]{64}$ |
| `size_bytes` | integer | 불가 | 없음; 명시 필수 | 자료 크기; minimum=0; maximum=9007199254740991 |
| `sensitive` | boolean | 불가 | 없음; 명시 필수 | 민감 자료 여부 |
| `public_export_allowed` | boolean | 불가 | 없음; 명시 필수 | 공개 내보내기 승인 여부 |

### ModelCall

모델 요청 테이블; 모든 제공자 재시도 포함

| 컬럼 | 타입 | null | 기본값 | 의미·제약 |
|---|---|---|---|---|
| `call_id` | string | 불가 | 없음; 명시 필수 | UUID v4 식별자; pattern=^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$; format=uuid |
| `attempt_no` | integer | 불가 | 없음; 명시 필수 | 제공자 실제 요청 순번; minimum=1; maximum=100 |
| `provider` | string | 불가 | 없음; 명시 필수 | 제공자 이름; minLength=1; maxLength=128 |
| `model` | string | 불가 | 없음; 명시 필수 | 실제 모델 이름; minLength=1; maxLength=256 |
| `price_artifact_id` | string | 불가 | 없음; 명시 필수 | 가격 자료 ID; minLength=1; maxLength=128 |
| `state` | enum reserved, settled, unknown | 불가 | 없음; 명시 필수 | 비용 확인 상태 |
| `reserved_micro_usd` | integer | 불가 | 없음; 명시 필수 | 요청 전 최대 비용 예약; minimum=0; maximum=9007199254740991 |
| `calculated_micro_usd` | integer | 허용 | 없음; 명시 필수 | usage와 가격 자료로 계산한 비용; 청구서 금액 아님; minimum=0; maximum=9007199254740991 |
| `input_tokens` | integer | 허용 | 없음; 명시 필수 | 제공자가 보고한 입력 수; minimum=0; maximum=9007199254740991 |
| `output_tokens` | integer | 허용 | 없음; 명시 필수 | 제공자가 보고한 출력 수; minimum=0; maximum=9007199254740991 |
| `created_at` | string | 불가 | 없음; 명시 필수 | UTC 시각; pattern=Z$; format=date-time |
| `completed_at` | string | 허용 | 없음; 명시 필수 | UTC 시각; pattern=Z$; format=date-time |
| `round_no` | integer | 불가 | 없음; 명시 필수 | 수정할 입력 후보의 회차; 생성할 다음 후보의 회차가 아님; minimum=0; maximum=10 |

### Integrity

판정 전 무결성 확인

| 컬럼 | 타입 | null | 기본값 | 의미·제약 |
|---|---|---|---|---|
| `case_match` | boolean | 불가 | 없음; 명시 필수 | 사례 해시 일치 |
| `criteria_match` | boolean | 불가 | 없음; 명시 필수 | 검사 기준 일치 |
| `environment_match` | boolean | 불가 | 없음; 명시 필수 | 환경 조건 일치 |
| `candidate_match` | boolean | 불가 | 없음; 명시 필수 | 후보 해시 일치 |
| `artifacts_complete` | boolean | 불가 | 없음; 명시 필수 | 참조 자료 완전 |
| `cleanup_complete` | boolean | 불가 | 없음; 명시 필수 | 정리 완료 |

### Action

결과 조치

| 컬럼 | 타입 | null | 기본값 | 의미·제약 |
|---|---|---|---|---|
| `code` | string | 불가 | 없음; 명시 필수 | 오류 또는 조치 코드; minLength=1; maxLength=128 |
| `target` | string | 허용 | 없음; 명시 필수 | 대상 경로 또는 검사 ID; minLength=1; maxLength=1024 |
| `message` | string | 불가 | 없음; 명시 필수 | 사용자가 필요한 판단; minLength=1; maxLength=2000 |
| `retryable` | boolean | 불가 | 없음; 명시 필수 | 조건을 해결한 뒤 재시도 가능 |

### Run

실행 테이블; 완료 manifest 공개 전에는 조회 자료일 뿐 완료 근거가 아님

| 컬럼 | 타입 | null | 기본값 | 의미·제약 |
|---|---|---|---|---|
| `record_type` | const run | 불가 | 없음; 명시 필수 |  |
| `schema_version` | const verified-change/1 | 불가 | 없음; 명시 필수 |  |
| `run_id` | string | 불가 | 없음; 명시 필수 | UUID v4 식별자; pattern=^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$; format=uuid |
| `case_id` | string | 불가 | 없음; 명시 필수 | UUID v4 식별자; pattern=^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$; format=uuid |
| `case_sha256` | string | 불가 | 없음; 명시 필수 | 전체 SHA256; pattern=^[0-9a-f]{64}$ |
| `started_at` | string | 불가 | 없음; 명시 필수 | UTC 시각; pattern=Z$; format=date-time |
| `finished_at` | string | 허용 | 없음; 명시 필수 | UTC 시각; pattern=Z$; format=date-time |
| `status` | enum prepared, running, completed, cancelled, failed | 불가 | 없음; 명시 필수 | 실행 상태 |
| `decision` | enum ready, blocked, manual-review | 허용 | 없음; 명시 필수 | 결과 판정 |
| `assurance` | enum isolated, trusted-local | 허용 | 없음; 명시 필수 | 실제로 확인한 실행 경계 |
| `candidate_tree_sha256` | string | 허용 | 없음; 명시 필수 | 전체 SHA256; pattern=^[0-9a-f]{64}$ |
| `environment_sha256` | string | 허용 | 없음; 명시 필수 | 전체 SHA256; pattern=^[0-9a-f]{64}$ |
| `evaluator_sha256` | string | 불가 | 없음; 명시 필수 | 전체 SHA256; pattern=^[0-9a-f]{64}$ |
| `integrity` | Integrity | 불가 | 없음; 명시 필수 |  |
| `results` | array<CheckResult> | 불가 | 없음; 명시 필수 | 검사 결과; minItems=0; maxItems=2000 |
| `changes` | array<FileChange> | 불가 | 없음; 명시 필수 | 파일 변경; minItems=0; maxItems=1000 |
| `artifacts` | array<Artifact> | 불가 | 없음; 명시 필수 | 자료 목록; minItems=0; maxItems=10000 |
| `model_calls` | array<ModelCall> | 불가 | 없음; 명시 필수 | 제공자 요청 목록; minItems=0; maxItems=100 |
| `actions` | array<Action> | 불가 | 없음; 명시 필수 | 필요한 조치; minItems=0; maxItems=1000 |
| `request_sha256` | string | 불가 | 없음; 명시 필수 | case·작업·후보·상한을 고정한 요청 바이트의 해시; pattern=^[0-9a-f]{64}$ |
| `operation` | enum verify, repair, generation | 불가 | 없음; 명시 필수 | 요청한 작업 |
| `source_run_id` | string | 허용 | 없음; 명시 필수 | 수정의 원래 실행 ID; pattern=^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$; format=uuid |
| `latest_round` | integer | 허용 | 없음; 명시 필수 | 마지막 후보 회차; minimum=0; maximum=10 |
| `rounds` | array<CandidateRound> | 불가 | 없음; 명시 필수 | 요청 안의 후보 회차; maxItems=11 |
| `duration_ms` | integer | 허용 | 없음; 명시 필수 | 준비부터 정리 종료까지 단조 시간 차이로 측정한 실행 시간; minimum=0; maximum=9007199254740991 |

### ApplyEntry

반영 파일 기록; 해시 재조회로 실제 상태를 확인

| 컬럼 | 타입 | null | 기본값 | 의미·제약 |
|---|---|---|---|---|
| `path` | string | 불가 | 없음; 명시 필수 | 기준 디렉터리 안의 상대 경로; 실제 경계는 별도 검사; minLength=1; maxLength=1024; pattern=^(?!/)(?!.*\\)(?!.*(?:^\|/)\.\.(?:/\|$))(?!.*\u0000).+$ |
| `before_sha256` | string | 허용 | 없음; 명시 필수 | 전체 SHA256; pattern=^[0-9a-f]{64}$ |
| `after_sha256` | string | 불가 | 없음; 명시 필수 | 전체 SHA256; pattern=^[0-9a-f]{64}$ |
| `before_mode` | integer | 허용 | 없음; 명시 필수 | 이전 권한; minimum=0; maximum=511 |
| `after_mode` | integer | 불가 | 없음; 명시 필수 | 새 권한; minimum=0; maximum=511 |
| `backup_path` | string | 허용 | 없음; 명시 필수 | 기준 디렉터리 안의 상대 경로; 실제 경계는 별도 검사; minLength=1; maxLength=1024; pattern=^(?!/)(?!.*\\)(?!.*(?:^\|/)\.\.(?:/\|$))(?!.*\u0000).+$ |
| `staged_path` | string | 불가 | 없음; 명시 필수 | 기준 디렉터리 안의 상대 경로; 실제 경계는 별도 검사; minLength=1; maxLength=1024; pattern=^(?!/)(?!.*\\)(?!.*(?:^\|/)\.\.(?:/\|$))(?!.*\u0000).+$ |
| `state` | enum prepared, written, restored, conflict | 불가 | 없음; 명시 필수 | 파일 반영 상태 |

### Apply

반영 테이블; 파일 기록 보존 후 원본 쓰기

| 컬럼 | 타입 | null | 기본값 | 의미·제약 |
|---|---|---|---|---|
| `record_type` | const apply | 불가 | 없음; 명시 필수 |  |
| `schema_version` | const verified-change/1 | 불가 | 없음; 명시 필수 |  |
| `apply_id` | string | 불가 | 없음; 명시 필수 | UUID v4 식별자; pattern=^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$; format=uuid |
| `case_id` | string | 불가 | 없음; 명시 필수 | UUID v4 식별자; pattern=^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$; format=uuid |
| `run_id` | string | 불가 | 없음; 명시 필수 | UUID v4 식별자; pattern=^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$; format=uuid |
| `run_sha256` | string | 불가 | 없음; 명시 필수 | 전체 SHA256; pattern=^[0-9a-f]{64}$ |
| `changes_sha256` | string | 불가 | 없음; 명시 필수 | 전체 SHA256; pattern=^[0-9a-f]{64}$ |
| `created_at` | string | 불가 | 없음; 명시 필수 | UTC 시각; pattern=Z$; format=date-time |
| `updated_at` | string | 불가 | 없음; 명시 필수 | UTC 시각; pattern=Z$; format=date-time |
| `state` | enum prepared, applying, applied, rolling_back, rolled_back, conflict, unknown | 불가 | 없음; 명시 필수 | 반영 상태 |
| `entries` | array<ApplyEntry> | 불가 | 없음; 명시 필수 | 대상 파일 목록; minItems=1; maxItems=1000 |
| `quiescence_confirmed_at` | string | 불가 | 없음; 명시 필수 | UTC 시각; pattern=Z$; format=date-time |
| `postcheck_at` | string | 허용 | 없음; 명시 필수 | UTC 시각; pattern=Z$; format=date-time |
| `actions` | array<Action> | 불가 | 없음; 명시 필수 | 복구와 충돌 조치; minItems=0; maxItems=1000 |

### Selector

승인된 선택자

| 컬럼 | 타입 | null | 기본값 | 의미·제약 |
|---|---|---|---|---|
| `strategy` | enum role, label, test-id, css | 불가 | 없음; 명시 필수 | 선택자 종류 |
| `value` | string | 불가 | 없음; 명시 필수 | 역할 또는 선택 값; minLength=1; maxLength=1024 |
| `name` | string | 허용 | 없음; 명시 필수 | 접근 가능한 이름; minLength=1; maxLength=1024 |

### FlowStep

화면 동작 정의; action별 관계 제약은 저장 문서에 정의

| 컬럼 | 타입 | null | 기본값 | 의미·제약 |
|---|---|---|---|---|
| `step_id` | string | 불가 | 없음; 명시 필수 | 시나리오 안의 순번 ID; minLength=1; maxLength=128 |
| `action` | enum goto, click, fill, press, expect-visible, expect-text, expect-count, expect-url, snapshot | 불가 | 없음; 명시 필수 | 허용된 화면 동작 |
| `selector` | Selector | 허용 | 없음; 명시 필수 |  |
| `value` | string | 허용 | 없음; 명시 필수 | 입력 또는 기대 값; minLength=0; maxLength=2048 |
| `count` | integer | 허용 | 없음; 명시 필수 | 기대 항목 수; minimum=0; maximum=100000 |
| `reference_path` | string | 허용 | 없음; 명시 필수 | 기준 디렉터리 안의 상대 경로; 실제 경계는 별도 검사; minLength=1; maxLength=1024; pattern=^(?!/)(?!.*\\)(?!.*(?:^\|/)\.\.(?:/\|$))(?!.*\u0000).+$ |
| `rgb_tolerance` | integer | 허용 | 없음; 명시 필수 | RGB 각 성분 차이 한도; minimum=0; maximum=255 |
| `max_mismatch_ppm` | integer | 허용 | 없음; 명시 필수 | 허용 다른 픽셀 비율의 백만분율; minimum=0; maximum=1000000 |
| `timeout_ms` | integer | 불가 | 없음; 명시 필수 | 동작 최대 시간; minimum=1; maximum=300000 |

### Flow

별도 일반 파일로 고정하는 화면 동작 기준

| 컬럼 | 타입 | null | 기본값 | 의미·제약 |
|---|---|---|---|---|
| `record_type` | const flow | 불가 | 없음; 명시 필수 |  |
| `schema_version` | const verified-change/1 | 불가 | 없음; 명시 필수 |  |
| `flow_id` | string | 불가 | 없음; 명시 필수 | 사용 시나리오 ID; minLength=1; maxLength=128 |
| `check_id` | string | 불가 | 없음; 명시 필수 | 연결한 검사 ID; minLength=1; maxLength=128 |
| `entry_path` | string | 불가 | 없음; 명시 필수 | 소유한 앱의 상대 URL 경로; 외부 origin은 금지; maxLength=2048; pattern=^/(?!/)[^\\\u0000-\u001f\u007f]*$ |
| `fixture_sha256` | string | 불가 | 없음; 명시 필수 | 전체 SHA256; pattern=^[0-9a-f]{64}$ |
| `steps` | array<FlowStep> | 불가 | 없음; 명시 필수 | 같은 context에서 실행할 동작; minItems=1; maxItems=100 |

### CandidateRound

후보 회차 기록; 자동 수정은 같은 run 안의 다음 회차

| 컬럼 | 타입 | null | 기본값 | 의미·제약 |
|---|---|---|---|---|
| `round_no` | integer | 불가 | 없음; 명시 필수 | 후보 회차; minimum=0; maximum=10 |
| `candidate_tree_sha256` | string | 불가 | 없음; 명시 필수 | 해당 후보의 파일 묶음 해시; pattern=^[0-9a-f]{64}$ |
| `changes_sha256` | string | 불가 | 없음; 명시 필수 | 해당 회차의 변경 묶음 해시; pattern=^[0-9a-f]{64}$ |
| `started_at` | string | 불가 | 없음; 명시 필수 | 회차 시작 UTC 시각; pattern=Z$; format=date-time |
| `finished_at` | string | 허용 | 없음; 명시 필수 | 회차 종료 UTC 시각; pattern=Z$; format=date-time |

### Environment

고정한 비교 환경; 기준과 후보에서 같은 값 사용

| 컬럼 | 타입 | null | 기본값 | 의미·제약 |
|---|---|---|---|---|
| `os_name` | string | 불가 | 없음; 명시 필수 | 실행 OS; minLength=1; maxLength=256 |
| `os_version` | string | 불가 | 없음; 명시 필수 | OS 판; minLength=1; maxLength=256 |
| `architecture` | string | 불가 | 없음; 명시 필수 | 실행 장비 종류; minLength=1; maxLength=256 |
| `runtime_name` | string | 불가 | 없음; 명시 필수 | 실행기 이름; minLength=1; maxLength=256 |
| `runtime_version` | string | 불가 | 없음; 명시 필수 | 실행기 판; minLength=1; maxLength=256 |
| `python_version` | string | 불가 | 없음; 명시 필수 | 검사 Python 판; minLength=1; maxLength=256 |
| `node_version` | string | 불가 | 없음; 명시 필수 | 프로그램 Node 판; minLength=1; maxLength=256 |
| `package_manager` | string | 불가 | 없음; 명시 필수 | 대상 앱의 패키지 도구; minLength=1; maxLength=256 |
| `package_manager_version` | string | 불가 | 없음; 명시 필수 | 패키지 도구 판; minLength=1; maxLength=256 |
| `playwright_version` | string | 불가 | 없음; 명시 필수 | Playwright 판; minLength=1; maxLength=256 |
| `browser_version` | string | 불가 | 없음; 명시 필수 | 브라우저 판; minLength=1; maxLength=256 |
| `locale` | string | 불가 | 없음; 명시 필수 | 화면 언어 조건; minLength=1; maxLength=256 |
| `timezone` | string | 불가 | 없음; 명시 필수 | 화면 시간대 조건; minLength=1; maxLength=256 |
| `record_type` | const environment | 불가 | 없음; 명시 필수 |  |
| `schema_version` | const verified-change/1 | 불가 | 없음; 명시 필수 |  |
| `assurance` | enum isolated, trusted-local | 불가 | 없음; 명시 필수 | 확인한 실행 경계 |
| `app_image_sha256` | string | 허용 | 없음; 명시 필수 | 앱 작업의 고정 이미지; pattern=^[0-9a-f]{64}$ |
| `checker_image_sha256` | string | 허용 | 없음; 명시 필수 | 검사 작업의 고정 이미지; pattern=^[0-9a-f]{64}$ |
| `lockfile_sha256` | string | 불가 | 없음; 명시 필수 | 의존성 잠금 파일 해시; pattern=^[0-9a-f]{64}$ |
| `browser_binary_sha256` | string | 불가 | 없음; 명시 필수 | 브라우저 실행 파일 해시; pattern=^[0-9a-f]{64}$ |
| `fixture_sha256` | string | 불가 | 없음; 명시 필수 | fixture 입력 묶음 해시; pattern=^[0-9a-f]{64}$ |
| `font_manifest_sha256` | string | 불가 | 없음; 명시 필수 | 글꼴 목록 해시; pattern=^[0-9a-f]{64}$ |
| `policy_sha256` | string | 불가 | 없음; 명시 필수 | 실행 제한과 적용 정책 해시; pattern=^[0-9a-f]{64}$ |
| `endpoint_kind` | enum local, remote | 불가 | 없음; 명시 필수 | 확인한 실행기 접속 범위; 첫 판은 local만 실행 |

### Lock

원본 반영과 사례별 모델 요청에 재사용하는 단일 작성자 기록

| 컬럼 | 타입 | null | 기본값 | 의미·제약 |
|---|---|---|---|---|
| `record_type` | const lock | 불가 | 없음; 명시 필수 |  |
| `schema_version` | const verified-change/1 | 불가 | 없음; 명시 필수 |  |
| `owner_run_id` | string | 불가 | 없음; 명시 필수 | 잠금 소유 실행; pattern=^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$; format=uuid |
| `nonce` | string | 불가 | 없음; 명시 필수 | 획득할 때 생성한 소유 확인 값; pattern=^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$; format=uuid |
| `pid` | integer | 불가 | 없음; 명시 필수 | 소유 process ID; 단독 해제 근거로 사용하지 않음; minimum=1 |
| `process_start_token` | string | 불가 | 없음; 명시 필수 | 시작한 process의 재사용 구분 값; minLength=1; maxLength=256 |
| `created_at` | string | 불가 | 없음; 명시 필수 | 획득 UTC 시각; pattern=Z$; format=date-time |
