# 검증 가능한 화면 변경: 3심 독립 최종 검토

검토일: 2026-10-14. 담당: 독립 3심 검토자. 최종 판단: **문서확정가능**. 초기 판단은 보강필요였으며 높음 4건·중간 3건을 수정한 전체 묶음을 독립적으로 재검토했다. §1~6은 초기 검토와 당시 반례·해시를 보존한 기록이며, 최종 대상·직접 실행·판단은 §7에 기록한다. 이 판단은 구현 완료·출시 승인·표준 인증·경쟁 우위의 판정이 아니다.

## 1. 초기 검토 범위와 독립 실행

검토 범위는 VCR-01~20, 기존 코드의 책임 재사용, 최소 구성, 원본·실행·비밀·판정의 경계, 상태·회차·시간·비용, 저장 필드의 유형·null·관계·보존, 실제 효과를 주장하는 조건이다. 기존 사용자 기능의 실행 사실과 미래 계약을 구분했다. 목표 설계 §1·15와 검증 설계 §3~5의 구분은 타당하다.

검토자는 아래 명령을 직접 실행했다. 파일을 수정하지 않는 메모리 변형을 사용했고 `PYTHONDONTWRITEBYTECODE=1`을 지정했다.

```text
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python docs/design/reviews/check_verified_change_design.py --output /dev/null
```

실제 결과: 종료 코드 0, 정의 21개·필드 202개, 정상 예시 10개·거부 예시 44개 모두 일치(54/54), 요구 추적 20개, 수용 시험 30개, 내부 참조 26개, 실패 0개. 구현 증거와 제품 효과 증거는 각각 0이다. 이 검사 결과를 그대로 받아들이지 않고 기존 정상 예시의 자료·비용·회차·반영·동작 값을 독립적으로 변형해 아래 반례를 확인했다.

모든 정의에서 `additionalProperties=false`, 정의된 필드 전부 명시 필수, 필드의 default 없음도 직접 대조했다. 저장 필드표 202개의 타입·null 표시 불일치는 0개다. 다만 제약 표시와 표 형식에는 R3-01의 문제가 있다. 근거: `verified-change/contract.schema.json`, `35-verified-change-storage.md:137`.

기준 기록의 소스 154개를 현재 파일 바이트에서 재계산해 SHA256 불일치 0개를 확인했다. 이전 평가의 458개 파일에 대해서도 존재 여부·mode·내용 해시 변경이 0개임을 직접 확인했다. 이전 제품 시험을 재실행하거나 새 제품 기능을 실행한 결과는 아니다. 근거: `2026-10-14-baseline.json`, `2026-10-14-preservation.json`, 이전 평가의 `before.json`.

## 2. 독립 판단

기존 변경을 모델 없이 검사하고, 고정된 기준 아래 선택 수정을 하며, 검사와 원본 반영을 구분하는 방향은 VCR-02~06·08·14·15에 직접 대응한다. 기존 `RuntimeValidator`·`ReleaseGate`·자료 저장 책임을 공통 계약으로 재사용하는 선택은 별도 판정 엔진을 늘리는 선택보다 목표에 적합하다. 근거: 목표 설계 §2~6, 분석 §3~4; `src/ddk/services/runtime_validator.py:164`, `src/ddk/services/release_gate.py:21`, `src/ddk/services/case_artifact_store.py:18`.

새 DB·서버·작업 대기열을 추가하지 않는 결정은 현재 단일 사용자와 사례별 직접 조회 범위에서 설명 가능하다. 다만 파일 방식도 동시 요청·내구성·관계 검증을 직접 책임져야 하며 R3-07처럼 누락된 직렬화가 생기면 DB가 없다는 사실만으로 단순하다고 평가할 수 없다. 근거: 저장 설계 §1~4·6, 분석 §5, [SQLite의 적합 범위](https://www.sqlite.org/whentouse.html).

기준·후보에 동일 환경을 사용하고 앱과 독립 검사 작업을 분리하는 방향, 관리된 반영에서 자기 변경만 복구하는 방향은 원본 보존과 정확한 판정에 대응한다. 실제 OS·브라우저·파일 공간에서 작동하는지는 아직 미확인이다. 근거: 목표 설계 §5~10, 저장 설계 §2·6, VCT-04·09·12·21·22·25~27.

관련 기능과 저장 필드는 충분히 구체적인 초안이지만, 아래 경계와 관계가 남아 있으므로 현재 묶음을 확정할 수 없다. 새 제품 방향 자체를 부적합으로 판정한 것은 아니다.

## 3. 초기 지적과 최소 보강

### R3-01 필드표의 열 파손과 nullable 제약 누락

- 심각도: 중간. 관련 요구: VCR-13·14·17.
- 위치: `35-verified-change-storage.md:194,207,264,283,379,386`; nullable 필드의 표 전반; `check_verified_change_design.py:389`의 필드명 대조.
- 실제 확인: 정규식의 escape되지 않은 `|` 때문에 Check.definition_path, InputFile.path, FileChange.path, Artifact.path, ApplyEntry.path, ApplyEntry.staged_path 여섯 행에 열 구분자가 8개다. 기대값은 6개다. 별도 대조에서 nullable의 비null 분기에 있는 minimum/maximum·길이·pattern·format 등 60개 제약 표시가 누락됐다. 타입과 null 표시 자체의 불일치는 0개다.
- 반례: Run.latest_round는 표에 범위가 없지만 schema는 0~10으로 제한한다. ModelCall.completed_at은 UTC 형식과 `Z$`가 표에서 누락된다. 구현자가 표만 사용하면 같은 계약의 서로 다른 구현이 생길 수 있다.
- 최소 수정: 생성 시 anyOf의 비null 분기에서 타입·제약을 추출하고 표 본문에 포함되는 `|`를 escape한다. 검사기는 필드명·순서뿐 아니라 타입·null·명시 필수 여부·제약·실제 열 수를 대조한다. 별도 수기 정본을 추가하지 않는다.
- 수용 시험: 필드표 202개 전체 대조, 열 파손 0개·제약 누락 0개. 한 타입·null·최댓값·pattern·열 구분자를 각각 잘못 바꾼 메모리 변형을 검사기가 거부해야 한다.
- 공식 근거: [GFM 표 규칙](https://github.github.com/gfm/#tables-extension-)은 표 안의 pipe를 escape하도록 정의한다. [JSON Schema Validation](https://json-schema.org/draft/2020-12/json-schema-validation)의 분기별 값 제약은 nullable이라는 이유로 없어지지 않는다.

### R3-02 보장 수준 입력과 호스트 실행 권한의 구분 부족

- 심각도: 높음. 관련 요구: VCR-08·09·14·17.
- 위치: `34-verified-change-design.md:122,134–136,190`; `35-verified-change-storage.md:228`; `src/ddk/models/operator.py:20`, `src/ddk/services/operator_authority.py:50`.
- 반례: 저장소가 제공한 case 또는 모델의 MCP 호출 인자에 assurance_required=trusted-local이 있다고 해서 사용자 권한으로 프로젝트 script를 실행할 수 있어서는 안 된다. 현재 문서는 사용자 승인을 요구하지만 승인 주체와 입력값의 경계를 명시하지 않아 구현이 이를 같은 값으로 취급할 수 있다.
- 최소 수정: Case.assurance_required는 필요한 결과 수준이며 실행 권한을 부여하지 않는다고 명시한다. 첫 MCP는 isolated 실행만 허용한다. trusted-local은 원본·후보·실행 명령·상한을 확인한 명시적 CLI 선택에만 허용하고 저장소·case·모델 응답으로 권한을 추가하지 않는다. 기존 Operator는 release/claim 범위의 process-local 승인 모델이므로 실행 권한으로 재사용하지 않는다. 별도 계정·인증 서버를 추가할 필요는 없다.
- 수용 시험: 동일 case를 CLI의 명시적 선택 없이 실행하거나 MCP에서 전달하면 호스트 script 실행 0회. case의 수준을 변경하거나 Operator의 release 승인을 제공해도 권한이 생기지 않아야 한다. 기존 사용자 권한 아래 명시적으로 선택한 CLI 경로만 별도 보장 표시로 진행해야 한다.
- 공식 근거: [MCP Tools 보안 규칙](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)은 도구 입력 검증과 접근 제어를 요구하고 민감 동작에 대한 사용자 확인을 권고한다. 규약 자체가 이번 실행 권한을 부여하지는 않는다.

### R3-03 상대 URL 판정이 외부 origin을 허용할 수 있음

- 심각도: 높음. 관련 요구: VCR-08·09·13·20.
- 위치: `35-verified-change-storage.md:96`; `check_verified_change_design.py:300–314`; Flow.entry_path와 FlowStep.value의 schema.
- 실제 확인: 정상 Flow의 entry_path를 `/\\example.org/x`로 바꾼 자료가 schema와 의미 검사에서 오류 없이 수용됐다. Node URL을 실제 실행한 결과는 `origin=http://example.org`, `href=http://example.org/x`였다. 따라서 문자열의 첫 `/` 확인만으로 소유 앱의 상대 URL을 강제할 수 없다.
- 최소 수정: 역슬래시와 ASCII 제어문자를 입력에서 거부하고, 실제 브라우저와 같은 URL 해석 결과가 소유 앱의 scheme·host·port와 같은지 실행 직전에 확인한다. redirect·popup·하위 요청도 승인된 앱과 고정 자료의 범위를 넘지 않도록 제한한다. 사후 URL 표시만으로 외부 연결 차단을 대신하지 않는다.
- 수용 시험: 역슬래시·줄바꿈이 섞인 상대 경로, `//host`, 다른 scheme·port, 외부 redirect·popup을 거부하며 외부 요청 0회를 확인한다. `/dashboard?filter=a#result` 같은 정상 경로는 유지한다.
- 재현 명령: `node -e 'const u=new URL(String.fromCharCode(47,92)+"example.org/x", "http://owned-app:3000"); process.stdout.write(JSON.stringify({origin:u.origin,href:u.href}));'`.
- 공식 근거: [WHATWG URL](https://url.spec.whatwg.org/#relative-slash-state)은 HTTP 계열에서 역슬래시를 상대 URL 해석에 포함한다. 이번 확인은 URL 해석과 문서 검사이며 실제 브라우저 보안 실행이 아니다.

### R3-04 동작별 미사용 필드와 빈 입력의 계약 불일치

- 심각도: 중간. 관련 요구: VCR-02·13·14.
- 위치: `35-verified-change-storage.md:98–107`; `check_verified_change_design.py:309–337`; FlowStep.value의 minLength=1.
- 실제 확인: expect-visible에 value와 count를 추가한 자료가 문서의 null 규칙과 달리 수용됐다. 반대로 fill의 value를 빈 문자열로 지정한 자료는 schema에서 거부됐다.
- 반례: 검색 필터를 비우는 일반 동작을 fill로 표현하지 못하고 불필요한 단축키 조합에 의존하게 된다. 사용하지 않는 값이 수용되면 서로 다른 연결 도구가 다른 값을 해석할 수도 있다.
- 최소 수정: action별 필요·금지 필드를 의미 검사에서 강제한다. fill은 빈 문자열을 허용하고, press처럼 의미 있는 비어 있지 않은 값이 필요한 동작은 해당 규칙으로 제한한다. 동작 종류를 늘리거나 임의 JavaScript를 허용할 필요는 없다.
- 수용 시험: 빈 값으로 필터를 지우는 정상 Flow를 수용한다. click/expect-visible의 value·count, expect-count의 value, goto/expect-url의 selector·count, snapshot의 불필요한 입력 값을 거부한다.
- 공식 근거: [Playwright locator.fill](https://playwright.dev/docs/api/class-locator#locator-fill)은 빈 문자열로 입력을 지우는 동작을 명시한다.

### R3-05 완료 판정에 필요한 자료와 회차 완료의 관계 누락

- 심각도: 높음. 관련 요구: VCR-03~06·13·17.
- 위치: `35-verified-change-storage.md:67,83–85`; `check_verified_change_design.py:197–247`.
- 실제 확인: ready-run의 모든 결과에서 artifact_ids를 비운 변형과, latest 회차의 finished_at을 null로 바꾼 변형이 모두 오류 없이 수용됐다. 고정 case·결과 상태·무결성 boolean은 유지했다.
- 반례: trusted-observer라는 이름만 있고 참조할 관찰 자료가 없어도 ready로 표시된다. 회차가 종료되지 않았는데 run만 완료로 표시하는 모순도 같은 의미 검사를 통과한다.
- 최소 수정: 성공 판정에 사용하는 필수 독립 관찰 결과에는 실제 존재하는 자료 ID를 요구한다. 모든 결과·모델 호출의 회차가 존재해야 하고 기준 회차는 0이어야 한다. latest 회차는 완료 상태와 종료 시각을 갖추고 run과 모순되지 않아야 한다. 실제 파일의 존재·해시와 종료 확인은 구현 수용 시험에서 별도로 강제한다.
- 수용 시험: 무자료 ready, 미종료 latest 회차 ready, 존재하지 않는 후보 회차 결과를 각각 거부한다. 정상 예시와 선택 사항에 대한 manual-review는 유지한다. 재시도 기록을 지우는 방식으로 이 조건을 맞추지 않는다.

### R3-06 비용·회차·반영 상태의 일부 모순을 의미 검사가 수용함

- 심각도: 중간. 관련 요구: VCR-11~13·17.
- 위치: `35-verified-change-storage.md:69–71,79,84,87,113–123`; `check_verified_change_design.py:164–176,266–297`.
- 실제 확인: 독립적으로 변형한 ① settled의 input_tokens=null ② output_tokens=null ③ 계산 비용이 최대 예약보다 큼 ④ model call.round_no=8이나 rounds는 0만 존재 ⑤ price_artifact_id가 log 종류 자료를 참조 ⑥ applied인데 파일 항목은 prepared ⑦ 같은 반영 경로 항목 두 개가 모두 오류 없이 수용됐다. 회차의 음수 시간·run 종료 뒤 시각도 수용됐다.
- 최소 수정: settled에 필요한 usage·정산·가격 종류·예약 상한과 호출 회차의 관계를 정한다. 예약 상한 계산 실패는 성공으로 숨기지 않는다. Apply.entries.path 고유성과 전체 상태·파일 상태·사후 확인 시각의 대응을 강제한다. prepared/applying의 진행 중 상태와 종료 상태는 구분하고 복구 중단의 실제 자료를 삭제하지 않는다.
- 수용 시험: 위 변형을 각각 분리한 거부 예시에 포함하고 정상 예약·정산·준비·반영·복구 예시를 유지한다. 현재 구현의 상태 변경 성공으로 계산하지 않는다.
- 판단 제외: unknown/reserved가 있다는 사실만으로 ready를 무조건 거부하라고 요구하지 않는다. 예약 전액 유지와 추가 요청 차단을 명시한 현재 비용 계약과 실제 완료 자료를 함께 판단해야 한다. 불명 비용을 실제 비용 0으로 표시해서는 안 된다.

### R3-07 동일 사례의 미정 비용 확인과 새 예약 사이의 경합

- 심각도: 높음. 관련 요구: VCR-10·11·13·14.
- 위치: `35-verified-change-storage.md:63–71,125`; `34-verified-change-design.md:164,172`. 정의된 저장 잠금은 현재 원본 반영의 apply.lock이다.
- 반례: 같은 사례에 서로 다른 run_id의 repair 요청 두 개가 동시에 들어오면 두 요청이 모두 미정 비용 없음 확인을 마친 뒤 각자 예약과 HTTP 요청을 시작할 수 있다. UUID 배타 생성은 같은 ID의 중복만 막는다. 한 요청이 usage 불명으로 중단되는 순간 다른 요청의 추가 호출을 차단한다는 계약에는 별도 직렬화 책임이 필요하다. 이는 설계상의 동시 실행 반례이며 새 제품의 실제 경합을 실행한 결과는 아니다.
- 최소 수정: 같은 case의 모델 요청 승인·기존 미정 확인·예약 보존·제공자 시도·정산을 한 소유 잠금 아래 직렬화한다. 기존 Lock의 소유 확인 계약을 재사용하고 비용 잠금 경로·획득·해제·중단 처리를 저장 설계에 명시한다. 미정 예약이 있으면 잠금 제거만으로 호출을 재개하지 않는다. 검사 전용·조회·내보내기는 이 비용 잠금과 분리해 유지한다. 새 DB·작업 대기열은 필요하지 않다.
- 수용 시험: 서로 다른 run_id의 동일 case 동시 repair, 예약 직후 중단, 정산 직전 취소, PID 재사용과 손상 잠금에서 예약 손실·동시 무제한 요청·자동 재개가 없는지 VCT-11·23·27에 추가한다.
- 시간 보강: 같은 run의 전체·단계·정리 기한은 `time.monotonic_ns()`의 차이로 집행하고 UTC는 표시·기록으로 구분한다. 시각 보정이나 재시작으로 기한을 다시 시작하지 않는 조건을 VCT-10에 포함한다. [Python time](https://docs.python.org/3.12/library/time.html#time.monotonic)은 이 시계가 시스템 시각 변경에 영향을 받지 않으며 두 값의 차이만 유효하다고 설명한다. 중단된 요청의 자동 재개는 이미 제외된 계약을 유지한다.

## 4. 공식 자료의 독립 재확인

다음 공식 자료를 2026-10-14에 직접 조회했다. 근거가 설명하는 기능을 실제 조합 성공·표준 인증·제품 우위로 확대하지 않았다.

| 자료 | 확인한 범위 | 이번 판단 |
|---|---|---|
| [Playwright Docker](https://playwright.dev/python/docs/docker) | 기본 root 실행의 보호 제한, 별도 사용자와 seccomp, 일반 이미지의 미신뢰 사이트 사용 제한 | 목표 §7의 사용자·보호 설정·자동 완화 금지는 적합한 조건이며 실제 조합 시험이 필요 |
| [Docker networks](https://docs.docker.com/engine/network/#container-networks) | 다른 작업의 네트워크 공유와 제한 옵션 | 앱 none과 검사 작업의 연결은 가능한 설계 후보이며 실제 차단 확인 전 지원 주장 불가 |
| [MCP Tools](https://modelcontextprotocol.io/specification/2025-11-25/server/tools) | 접근 제어·입력 검증·사용자 확인·지원 판의 결과 | R3-02의 입력과 실행 권한 구분이 필요하며 SDK 판만으로 상호운용을 증명하지 않음 |
| [JSON Schema Validation](https://json-schema.org/draft/2020-12/json-schema-validation) | 필드·유형·값·format의 범위 | 유형 검증과 참조·상태·실제 파일 검증을 구분한 결정 유지; R3-01·05·06 보강 필요 |
| [GFM 표 규칙](https://github.github.com/gfm/#tables-extension-) | 표 본문의 pipe escape | R3-01의 표시 형식 보강 필요 |
| [WHATWG URL](https://url.spec.whatwg.org/#relative-slash-state) | HTTP 계열의 역슬래시 해석 | R3-03의 문자열 검사만으로 origin을 제한할 수 없음 |
| [Playwright fill](https://playwright.dev/docs/api/class-locator#locator-fill) | 빈 문자열로 입력 제거 | R3-04의 일반 동작 지원 보강 필요 |
| [Python time](https://docs.python.org/3.12/library/time.html#time.monotonic) | 시각 보정과 무관한 경과 시간 | R3-07의 실행 기한을 기록 시각과 구분 |

## 5. 초기 검토 대상 SHA256

아래는 독립 반례를 실행하고 본 기록을 작성하기 전 동결한 대상이다. 후속 수정 묶음은 별도 해시로 재검토한다. 기존 2심의 초기 버전과 혼합하지 않는다.

| 파일 | SHA256 |
|---|---|
| `34-verified-change-design.md` | `9ca59e36fb8032a49c3250d5686c5a0a2d42949bf5bddc1dc9d06a6521ce58da` |
| `35-verified-change-storage.md` | `10d1a096fabb4694737fde245af951e7c16479bd600f7311db97185d6dc91cc0` |
| `36-verified-change-verification.md` | `da1f11f8a75caa7565747bd31f258f778296e69e3f4d485aab12b89a306a6f0e` |
| `verified-change/GLOSSARY.md` | `f0a644e162b963bdeb714acb40600167bb72d4f91a89cee1bc1ef99bbffa5725` |
| `verified-change/contract.schema.json` | `5dc80f87716599427dc185cb9570d049458008df0e901f3608bac1a933e5e141` |
| `verified-change/contract-examples.json` | `67ed7670f53d013ad21617c5b8f35d3ce54bd8ed9e9cc8203f256dba3ffc498f` |
| `reviews/check_verified_change_design.py` | `683fb6a0f97892d120a4c6dbf843976e8543a33736677835ff74b953de62b0b8` |
| `reviews/2026-10-14-analysis.md` | `074f666da61bbce0a5e6ce6e43dfc409a7cdff0d243c006afab7b3835af159f1` |
| `reviews/2026-10-14-official-sources.md` | `d645ec03a711933181f7131881eee4b81e0b58ae440d9f949f2c4704878e4bb1` |
| `reviews/2026-10-14-second-review.md` | `1030d7d7c9a640ca2588eb3e04b2b701447e97c52755f9b26260720aca529ff6` |
| `reviews/2026-10-14-three-review.md` | `28de6050172e51bbee1e0ed710d9bf15e04eb940fdf5a9fc69ac47820997dfb7` |
| `reviews/2026-10-14-document-validation.json` | `335076750cd1cd5bdd46dc0d631af54194d523fe3fb7722d4f1d80f336b16ee1` |
| `reviews/2026-10-14-validation-before-fix.json` | `041c4d454cec5418571725baac1cbee64f7ca727ac3fa944741af58c88eccf21` |
| `reviews/2026-10-14-baseline.json` | `f6e4e4622232ae819503032dace5c91c9973ffc111d013fd7968e3bc4a2c86aa` |
| `reviews/2026-10-14-preservation.json` | `13fa340e001e5b0a46b067382f6ebaee73d27cf5c8bb6f6a4de71ee35bfe8815` |

## 6. 미검증 범위와 초기 판단

이번 검토에서 실제 제품 구현·유료 모델·격리 작업·headless 브라우저·원본 반영·전원 중단·경쟁 제품 비교·외부 사용자의 반복 사용을 실행하지 않았다. 화면을 실행해야 판단할 사항을 문서 검사 통과로 대신하지 않았다. D0~D4와 VCT의 실제 실행 조건은 유지한다. 현재의 타입 오류·브라우저 시험 실패 역시 이전 평가의 한계와 구현 단계의 해결 조건으로 유지한다.

초기 판단은 **보강필요**였다. 당시 높음 4건(R3-02·03·05·07), 중간 3건(R3-01·04·06)의 미해결 지적이 있었다. 변경 방향과 최소 구성은 목표에 적합하지만 초기 묶음은 문서 확정 조건을 충족하지 못했다. 수정된 문서·schema·예시·검사기와 새로운 전체 해시를 직접 재검토한 최종 결과는 아래와 같다. 절대적 안전·100점·표준 인증·경쟁 우위·실사용 효과는 이번 문서에서 확정하지 않는다.

## 7. 수정 묶음의 최종 독립 재검토

### 7.1 지적별 해소와 실행 범위

목표·저장·검증·용어·schema·예시·문서 검사기·분석·1~3심 기록·실패 전후 자료·기존 파일 보존 목록을 다시 확인했다. 기존 파일의 사실과 미래 계약의 권위는 유지했다. 새 DB·서버·조율 도구·사용자 인증 체계는 추가되지 않았다. Run.duration_ms와 기존 Lock을 사용하는 사례별 비용 잠금은 시간 상한과 중복 호출의 구체 실패에 대응하는 최소 보강으로 판단한다. 근거: 목표 §4·7·8, 저장 §2~4·6·8, VCT-09~13·23·27.

| 지적 | 최종 계약·검사 대응 | 독립 재확인과 남은 실행 조건 |
|---|---|---|
| R3-01 | nullable의 비null 분기 제약·pipe escape·모든 표 값과 열 수 대조 | 203필드의 타입/null/제약/열수 차이 0; 잘못된 표 5변형 모두 거부 |
| R3-02 | 보장 요구는 실행 권한이 아님; 첫 MCP isolated만 실행; trusted-local은 명시적 CLI 선택; Operator 승인 재사용 금지 | 문서 경계 해소; 실제 호스트 실행 0회와 승인 처리 확인은 VCT-09의 미실행 조건 |
| R3-03 | 역슬래시·제어문자·외부 상대 URL 거부; 실제 URL 해석·origin 확인; redirect·추가 페이지·하위 요청·Service Worker 경계 | 외부 entry 변형 거부 직접 확인; 실제 외부 요청 차단은 VCT-09·20의 미실행 조건 |
| R3-04 | fill/expect-text 빈 값 허용; press 빈 값과 action별 미사용 값 거부 | 빈 입력 2개 수용, 미사용 value/count와 빈 press의 거부 직접 확인 |
| R3-05 | 실제 자료 ID·고아 회차 거부·latest 종료·후보 대응 | 무자료 ready·미종료 latest·고아 결과 회차 거부 직접 확인; 실제 파일·관찰의 진실성은 VCT-06·13·21의 조건 |
| R3-06 | settled usage·price 종류·회차·예약 상한; 실제 초과는 blocked+조치로 보존; 반영 경로 고유·종료 상태 대응 | 각 usage 누락·가격 종류·호출 회차·중복 경로·반영 상태 반례 거부; 실제 초과 관측의 정상 보존 수용 |
| R3-07 | 사례별 비용 Lock으로 승인부터 정산까지 직렬화; 미정 예약 유지; 단조 시간으로 상한 집행·UTC는 표시용 | 문서 조건 해소; 시간 초과·duration 누락 거부, UTC 보정 예시 수용; 실제 동시 실행·잠금·중단은 VCT-10·11·23·27의 미실행 조건 |

R3-06의 초기 관찰 중 UTC 시각의 역전·실행 시각 범위 차이는 새 계약에서 실행 시간의 위반을 직접 뜻하지 않는다. UTC를 표시용으로 구분하고 단조 시간으로 측정한 Run.duration_ms를 사용하므로, 시스템 시각 보정 자체를 오류로 판정하지 않는 현재 설계가 더 정확하다. 회차의 존재·종료·참조·최종 후보의 관계는 별도로 강제한다. 이 해소를 위해 새 시계 서비스나 회차 시간 테이블을 요구하지 않았다.

미정 비용은 예약 전액 보존·추가 모델 요청 차단의 근거다. 필수 검사·정리·자료가 완료된 결과의 판정과 원본 반영 권한은 별도 계약이다. 저장 §3의 최종 문장은 추가 모델 요청 없이 검사·조회·내보내기를 사용할 수 있고 반영은 별도 반영 계약을 따른다고 명확히 했다. ready·실행 종료·자료 무결성·원본 조건을 완화하지 않으므로 이 명확화는 새로운 반영 권한이나 제한을 추가하지 않는다. active run·정리 미완료·복구 unknown·참조 자료의 삭제 제한은 유지한다.

### 7.2 직접 실행한 최종 확인

문서 검사 명령을 최신 저장 문서 판에서도 직접 실행했다. 종료 코드 0, 정의 21개·필드 203개, 정상 15개·거부 64개 모두 일치(79/79), VCR 20개·VCT 30개·내부 참조 30개, 실패 0개였다. `ruff check docs/design/reviews/check_verified_change_design.py`도 직접 실행해 종료 0과 `All checks passed!`를 확인했다. 전체 제품 시험·타입 검사·브라우저 시험을 재실행한 결과는 아니다.

초기 반례와 보존한 2심 반례를 정상 예시에서 메모리로 다시 구성했다. 33개 변형의 기대 불일치는 0개였다. 이 수는 동일 위험을 재검토한 문서 예시 수이며 독립적인 제품 과제나 사용자 수가 아니다.

| 독립 변형 범위 | 실제 결과 |
|---|---|
| 자료 ID 전부 제거·미종료 latest·고아 결과 회차 | missing_observation_artifact / missing_baseline_artifact / latest_round_incomplete / orphan_result_round |
| settled 입력·출력 usage 각각 누락·예약 초과 ready·고아 호출 회차·잘못된 가격 종류 | settlement_missing / settlement_above_reservation / orphan_call_round / missing_price_artifact |
| applied의 prepared 항목·중복 반영 경로 | applied_entry_state / duplicate_apply_path |
| 역슬래시·tab·newline·`//` 외부 entry | schema 거부 |
| 미사용 value·count·snapshot value·goto count·빈 press | unused_step_value / unused_step_count / empty_press |
| 빈 fill·빈 expect-text | 정상 수용 |
| 완료 duration 누락·duration 상한 초과 | schema 거부 / run_deadline |
| UTC가 보정된 정상 duration·실제 예약 초과 blocked 기록 | 정상 수용 |
| 2심의 무결성 오류 manual-review·원 실행 없는 repair·비독립 기준 관찰·blocked 반영·criteria 역할·before 해시·잘못된 create·기준 파일의 변경 범위 포함 | 원래 의도한 오류로 각각 거부 |

필드표 대조는 검사기의 field_rows를 호출하지 않는 별도 코드로 수행했다. JSON Schema의 비null 분기와 원문 표의 열을 직접 비교해 203개 필드의 타입·null·제약·열수 불일치가 모두 0개였다. 모든 정의의 추가 필드 금지와 필드 명시 필수도 재확인했다. 이어서 Path.read_text의 저장 문서 입력만 메모리에서 교체해 전체 검사기를 실행했다. 타입·null·최댓값·pattern·pipe escape를 각각 잘못 변경한 5개 변형은 모두 종료 코드 1로 거부됐다. 원본 문서와 검사기를 변경하지 않았다.

수정 전 자료인 `2026-10-14-third-validation-before-fix.json`도 직접 확인했다. 당시 추가 반례 22개를 포함한 전체 76개 중 57개만 일치했고, 잘못 수용한 거부 예시 17개와 잘못 거부한 정상 빈 입력 2개가 기록돼 있다. 최종 79개는 이에 단조 시간·duration 관련 예시 3개를 더한 것이다. 보존된 실패와 최종 결과를 같은 실행으로 혼합하지 않았다.

저장소의 `2026-10-14-workspace-before.json`을 기준으로 기존 458개 파일의 존재·mode·내용 해시를 다시 계산했으며 변경은 0개였다. 기준 manifest의 SHA256는 `5a5966d3f8ec719993d7f6c76c1697e5c4888617f4bc02548ad44b11fbe10a50`이다. 기준 소스 154개의 SHA256 불일치도 0개였다. 임시 자료에만 의존하지 않고 저장소 안의 보존 자료로 재현할 수 있다.

신규 공식 자료인 Playwright의 요청 제어·네트워크 문서도 직접 확인했다. Service Worker 요청과 WebSocket 등의 범위가 다르므로 route 하나로 모든 외부 연결을 차단했다고 판단하지 않는 저장 §5의 제한은 적절하다. [BrowserContext.route](https://playwright.dev/python/docs/api/class-browsercontext#browser-context-route), [네트워크 검사](https://playwright.dev/python/docs/network). 실제 차단의 실행 자료는 이번에 생성하지 않았다.

### 7.3 최종 검토 대상 SHA256

아래는 최종 핵심 계약과 증거의 정확한 바이트 해시다. 본 검토 파일은 자기 해시를 포함할 수 없으므로 최종 증거 목록에서 별도로 기록한다. root의 심사 요약 최종 상태·증거 목록 갱신은 검토된 핵심 계약의 변경과 구분한다.

| 파일 | SHA256 |
|---|---|
| `34-verified-change-design.md` | `555500f9f733832ed031183c47ecb4f91ad148f4f1d80f5c4435ed1746dec2c6` |
| `35-verified-change-storage.md` | `6fac23179727d6a63a47a0488066b0310d9ed522e540248a399df5ac369c1730` |
| `36-verified-change-verification.md` | `c21ba527e91c54f74ff1799c4838f316b6b535e5a967c7a324b7e88319ef6724` |
| `verified-change/GLOSSARY.md` | `f0a644e162b963bdeb714acb40600167bb72d4f91a89cee1bc1ef99bbffa5725` |
| `verified-change/contract.schema.json` | `d63ad780df2fbcfa638a1afa83dc0a7fe1bb11fe3eb3e310fed9fd6eae179e1f` |
| `verified-change/contract-examples.json` | `3c1543e3ba85436b62f0d4f08b9334c4faf6eaddeca6408c38e7a43fef7fa202` |
| `reviews/check_verified_change_design.py` | `e370c389351e1fd164e81c965d02264c99ec3938f314c411c6a1c87d5b0d4115` |
| `reviews/2026-10-14-analysis.md` | `074f666da61bbce0a5e6ce6e43dfc409a7cdff0d243c006afab7b3835af159f1` |
| `reviews/2026-10-14-official-sources.md` | `d645ec03a711933181f7131881eee4b81e0b58ae440d9f949f2c4704878e4bb1` |
| `reviews/2026-10-14-second-review.md` | `1030d7d7c9a640ca2588eb3e04b2b701447e97c52755f9b26260720aca529ff6` |
| `reviews/2026-10-14-three-review.md` | `dfedf17f9e60a709d76a6277f7a720adee6b8fb8e6ef650bf77dab32bc2d0de5` |
| `reviews/2026-10-14-document-validation.json` | `949e3025a65607277d7a0efd094a08ee3bb0bf496a118c4158d01519e38d37e5` |
| `reviews/2026-10-14-third-validation-before-fix.json` | `93cbe7a7dc6fc72874b43b13135add53ccceeb9cb51cf62bf7ff84808fa9090e` |
| `reviews/2026-10-14-validation-before-fix.json` | `041c4d454cec5418571725baac1cbee64f7ca727ac3fa944741af58c88eccf21` |
| `reviews/2026-10-14-baseline.json` | `f6e4e4622232ae819503032dace5c91c9973ffc111d013fd7968e3bc4a2c86aa` |
| `reviews/2026-10-14-preservation.json` | `1bc891e432391efde83fb528f7b4a61e26cc6f3ab5a981cda392b612b256aa66` |
| `reviews/2026-10-14-workspace-before.json` | `5a5966d3f8ec719993d7f6c76c1697e5c4888617f4bc02548ad44b11fbe10a50` |

### 7.4 최종 판단과 미검증 범위

**문서확정가능.** 초기 높음 4건·중간 3건은 문서 계약·필드·의미 검사·거부 예시에서 해소됐으며 이번 범위에서 미해결 중대 지적은 없다. 요구와 구체 실패 위험에 대응하는 기능·저장·권한·복구·비용·검사 책임이 연결돼 있고, 앞선 광범위한 기능 확대보다 제한된 실제 작업을 확인하는 목표에 더 적합한 설계로 판단한다. 이는 문서 수준의 적합성과 구현 준비에 대한 판단이다.

이 설계를 구현한 제품이 경쟁 도구보다 정확하거나 편리하거나 작업 시간을 줄였다는 결과는 없다. OS 격리·브라우저·모델·파일 반영·전원 중단·실제 동시 요청·개인정보·반복 사용·생산성의 실행 증거는 아직 0이다. 현재 제품의 타입 오류와 브라우저 시험 실패도 해결했다고 판단하지 않았다. D0~D4와 VCT의 실제 실행 조건을 충족하고, 독립 비교와 반복 사용 자료를 확보해야 다음 제품 주장을 할 수 있다. 절대적 안전·100점·표준 인증·업계 우위·스타 수는 확정하지 않는다.
