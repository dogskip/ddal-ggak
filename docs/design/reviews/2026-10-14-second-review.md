# 검증 가능한 화면 변경: 2심 독립 반론 검토

검토일: 2026-10-14. 담당: 독립 2심 검토자. 최종 판단: **문서확정가능**. 초기 판단은 승인보류였으며 본문·저장·필드·수용 기준·문서 검사기를 수정한 뒤 전체를 재검토했다. 3심 최종 검토가 남아 있으며 이 판단은 구현 완료나 출시 승인으로 해석하지 않는다.

## 1. 검토 대상과 증거 범위

사용자의 목적은 유용성·정확성·경쟁력·원본 보호·편의성·유지보수성·재사용·중복 제거·확장성과 불필요한 구성의 제거다. 분석의 VCR-01~20을 기준으로 선택 이유와 실패 경계를 검토했다. 현재 구현의 미완성은 미래 설계의 결함과 구분했다.

| 대상 | SHA256 |
|---|---|
| `docs/design/34-verified-change-design.md` | `e8916873187464666a6d31f74e22d26a370915a7dda86c405519a1d58727cc24` |
| `docs/design/reviews/2026-10-14-analysis.md` | `73f69691add9ab19e84695a71e5095d13be790505b4e25c7cb025885334b148f` |
| `docs/design/verified-change/contract.schema.json` | `b997e177bcd55d72ff37d0e2f07d8d0fc58fda00ffe0d48e90dd6c84cea7b046` |
| `src/ddk/services/runtime_validator.py` | `39a330f6068f357709f13de7bcd70ef53cd1bc31cc0bf0e8e1bea4791604929f` |
| `src/ddk/adapters/sandbox/tempdir.py` | `e84810c08b62d5c9f5806c1e5d1fdbb6073994abae3ce46cf0e71c1c7d422135` |
| `src/ddk/services/artifact_applier.py` | `7de8428b7831c95a8f6e0dd18957095f58c6bf588537f8e6550cb0e8de3027c7` |
| `src/ddk/services/case_artifact_store.py` | `533dce03250a5efa183dcc21b8eae5ab3619850641af21a739a7e5da415013cc` |
| `src/ddk/services/release_gate.py` | `0cc1fb47629dce2dbc48182b54b5044a8dede0a290666cf40549296dd675aae1` |
| `src/ddk/cli/runtime.py` | `386d4e36751f5376455ad5bdf096f23b7c2a356de67f63686a31fe55b5e2bc3f` |
| `src/ddk/adapters/llm/claude.py` | `79ba57f0241c83c58fb8e1f6b5342ffccd4051dbfe24c82fba55416123fdb0f6` |
| `src/ddk/adapters/chromium_browser.py` | `bebaf5fd84e5ef5b33076f7bdf7316ad360c76f2143c3445a8b78cd5723464c0` |

검토는 문서·소스 정적 대조와 공식 자료 조회다. 유료 모델 호출, 원본 반영, 컨테이너 실행, 실제 경쟁 도구 비교, 보이는 브라우저, 배포·외부 전송은 실행하지 않았다. 아래 수용 시험은 구현 이후 확인할 조건이며 현재 통과 자료가 아니다.

## 2. 수정이 필요한 반례

### R2-01 기준·후보 복사 중 편집의 감지 누락

- 심각도: 높음. 관련 요구: VCR-04·08·12.
- 문서 근거: `34-verified-change-design.md:39–41,86–92`. 현재 사본 생성은 순서대로 파일을 복사하는 `src/ddk/adapters/sandbox/tempdir.py:29–66`이다.
- 반례: 기준을 지정했더라도 복사 중 편집기가 두 연관 파일을 순서대로 갱신하면 사본은 실제로 승인한 적 없는 혼합 상태가 된다. 사본 전체의 해시 계산만으로 승인 상태와의 일치를 증명할 수 없다. 기존 dirty 변경과 새 변경을 구분하는 승인 계약도 파일 목록만으로 완료되지 않는다.
- 최소 수정: 고정 Git 객체에서 기준을 구성하거나 승인한 일반 파일 목록·bytes·mode·존재 여부를 기준으로 사본을 구성한다. 작업 폴더 사본은 복사 전후 목록과 파일 상태가 일치하는지 확인하고 변화가 있으면 `snapshot_changed`로 중단한다. 동시 편집을 멈춘 조건의 안정한 복사이며 다파일 시점 원자성을 보장하지 않는다는 제한을 명시한다. 기준·후보 준비 방식과 미지정 변경 처리를 저장 계약에 연결한다.
- 수용 시험: 복사 도중 두 파일 갱신·새 파일 생성·삭제·mode 변경을 각각 주입해 안정하지 않은 입력이 완료 기준으로 공개되지 않는지 확인한다. 혼합된 기존 수정은 경로별 승인 범위가 없으면 `ambiguous_baseline`이어야 한다.

### R2-02 프로그램 출력과 검사 판정의 권한 구분 부족

- 심각도: 높음. 관련 요구: VCR-05·06·09.
- 문서 근거: `34-verified-change-design.md:90,98,120–122`. 현재 검사는 명령 종료 코드 0에서 통과로 판정한다. `src/ddk/services/runtime_validator.py:355–372`, 현재 `_CHECKS`는 `runtime_validator.py:46`이다.
- 반례: 앱 명령이 실제 시험을 실행하지 않고 통과 수를 나타내는 JSON을 출력하거나, 후보가 import되는 기존 Node 시험의 같은 process에서 결과 작성 기능을 바꿀 수 있다. 기준 파일의 읽기 전용 보호가 결과 판정의 진실성을 자동 보장하지 않는다. 읽기 전용 승인 기준을 앱과 분리해도 checker가 앱의 결과 주장만 신뢰하면 동일한 문제가 유지된다.
- 최소 수정: 앱 출력은 관찰 자료로 취급한다. 딸깍 소유 checker·판정 코드·결과 폴더에는 앱의 쓰기 권한을 제공하지 않는다. 브라우저 동작 판정은 승인된 독립 checker에서 계산한다. 앱 코드를 같은 process로 가져오는 기존 단위 시험은 결과 위조에 대한 강한 보호를 제공하지 않는다고 표시한다. 의도적으로 시험 조건을 감지하는 앱의 모든 기만을 차단한다고 주장하지 않는다.
- 수용 시험: 가짜 통과 JSON·결과 파일 쓰기·검사 모듈 교체·원격 제어 연결을 시도하는 앱으로 판정과 자료가 변하지 않는지 확인한다. 동일 process 시험의 제한이 결과 범위에서 누락되지 않아야 한다.

### R2-03 Chromium 실행 정책의 실현 가능성과 제어 경로 누락

- 심각도: 높음. 관련 요구: VCR-09·10·20.
- 문서 근거: `34-verified-change-design.md:120–124`. 현재 연결은 `src/ddk/adapters/chromium_browser.py:183–190`에서 root이면 `--no-sandbox`를 추가하며 `chromium_sandbox=True`를 지정하지 않는다.
- 반례: 일반 사용자와 Docker 기본 seccomp 조합에서 Chromium 보호 실행이 불가능한 장비가 존재할 수 있다. 구현자가 root·`--no-sandbox`·권한 추가로 대체하면 앱의 화면 내용이 승인 기준·결과를 가진 checker를 공격할 범위가 증가한다. 앱과 checker가 같은 네트워크를 공유하면 앱도 checker의 debugging·제어 port에 접근할 수 있다.
- 최소 수정: 앱은 `--network=none`, checker는 소유 앱 ID의 `--network=container:<id>`로 연결하고 PID·파일 공간·자원은 별도 확인한다. checker의 `headless=True`, `chromium_sandbox=True`, 일반 사용자, 고정하고 검토한 seccomp 정책을 사전 검사한다. `--no-sandbox`, root, privileged, `SYS_ADMIN`, host IPC/network/PID 자동 대체를 금지한다. 제어는 공통 네트워크에 port를 열지 않는 경로로 처리하며 작업 식별·종료 순서를 정의한다. 필요한 공유 메모리는 제한된 작업별 범위로 제공한다.
- 공식 근거: [Playwright Docker](https://playwright.dev/docs/docker)는 별도 사용자와 검토한 seccomp 설정을 설명한다. [Python BrowserType](https://playwright.dev/python/docs/api/class-browsertype#browser-type-launch-option-chromium-sandbox)의 `chromium_sandbox` 기본값은 false다. [Docker none](https://docs.docker.com/engine/network/drivers/none/)은 loopback만 제공하며 [container network](https://docs.docker.com/engine/network/#container-networks)는 다른 작업의 네트워크를 공유하는 방식을 설명한다. 이 조합의 실제 지원은 구현 장비에서 확인해야 한다.
- 수용 시험: 앱에서 인터넷·호스트·Docker socket·기준·결과·checker 제어 port 접근이 차단되고 checker는 앱에만 접속하는지 확인한다. 보호 기능을 활성화한 headless 동작 검사를 통과해야 한다. 정책 확인 실패는 `isolation_unavailable`이어야 하며 자동 완화가 없어야 한다.

### R2-04 SDK 숨은 재시도와 비용 불명 예약의 처리 부족

- 심각도: 높음. 관련 요구: VCR-10·11.
- 문서 근거: `34-verified-change-design.md:152–156`. 현재 `src/ddk/adapters/llm/claude.py:44`는 SDK 재시도 설정을 생략하고 `claude.py:61–74`는 별도 5회 재시도를 제공한다. 비용은 `claude.py:118–125,185–186`에서 호출 전 누적값 확인과 응답 후 계산을 사용한다.
- 반례: SDK와 외부 재시도 책임이 중첩되면 한 번의 논리 호출 아래 여러 실제 HTTP 요청이 발생한다. 응답을 받기 전에 취소되어도 제공자에서 비용이 발생할 수 있다. 불명 예약을 0으로 해제하면 전체 비용 상한보다 많은 추가 요청을 허용할 수 있다. 스트림의 read timeout만으로 전체 기한도 보장되지 않는다.
- 최소 수정: SDK 자동 재시도를 0으로 설정하고 재시도 책임을 한 곳에 집중한다. 실제 HTTP 시도마다 사전 예약·요청 수·전체 기한을 적용한다. usage 불명 예약은 해제하지 않으며 추가 호출을 차단한다. 최초 입력·출력 상한, 가격 근거, 가격에 포함된 usage 항목을 고정한다. 현재 호출을 끊어도 제공자의 이미 수락한 처리나 청구 취소를 보장하지 않는다고 명시한다.
- 공식 근거: [Anthropic Python SDK](https://platform.claude.com/docs/en/api/sdks/python#retries)는 기본 자동 재시도 2회와 `max_retries=0`을 설명하며 timeout에도 기본 재시도가 적용된다고 명시한다.
- 수용 시험: 가짜 HTTP 연결로 429·5xx·timeout·스트림 중단·usage 누락·취소를 주입해 실제 전송 수가 승인 한도를 넘지 않는지 확인한다. 남은 기한이 없는 재시도와 불명 예약 뒤 추가 요청은 없어야 한다. 실비가 예약보다 커지는 경우에는 불완전 가격 판단으로 종료해야 한다.

### R2-05 반영·복구가 bytes 외의 상태를 무시할 가능성

- 심각도: 높음. 관련 요구: VCR-08·12·13.
- 문서 근거: `34-verified-change-design.md:166–174`; `contract.schema.json:1179–1268`. 현재 `src/ddk/services/artifact_applier.py:38–61`는 순차 쓰기이며 `artifact_applier.py:71–72`는 사라진 기존 파일을 새 파일로 판단한다.
- 반례: 파일 bytes가 예정한 새 값과 같아도 외부 사용자가 mode나 경로 유형을 변경했을 수 있다. 해시만 일치한다고 복구하면 새 사용자 변경이 손실될 수 있다. 새 파일 반영 후 복구도 예정 값 확인 없이 삭제하면 외부 변경이 손실된다. 사전 검사 뒤의 외부 편집은 저장소 잠금에 협조하지 않을 수 있다.
- 최소 수정: 반영 전·직전·반영 후·복구에서 존재 여부·일반 파일 유형·bytes 해시·mode를 함께 비교한다. create 복구 삭제는 소유한 새 파일이 예정 상태와 일치할 때만 허용한다. 외부 값은 자동 쓰기 없이 `unknown/conflict`로 유지한다. 새 부모 디렉터리를 정리한다면 소유·비어 있음 확인 없이 재귀 삭제하지 않는다. 배타 생성과 반영 기록의 내구성 및 적용 시점의 한계는 유지한다.
- 수용 시험: 각 파일 교체 전후 종료, rename 전후 내구성 실패, 외부 bytes 편집·chmod·파일 삭제·symlink 교체, create 충돌, 복구 중 종료를 주입한다. 외부 변경은 보존되고 전체 원상 확인 전 `rolled_back`이 없어야 한다. 파일 공간 기능 미확인은 내보내기만 허용해야 한다.

### R2-06 판정 간 중복 조건의 우선순위 부족

- 심각도: 중간. 관련 요구: VCR-06·14.
- 문서 근거: `34-verified-change-design.md:144–150`. 현재 `src/ddk/services/release_gate.py:128–143`는 심각한 실패를 먼저 확인하고 종합 점수와 수정 한도를 사용한다.
- 반례: 수정 한도에 도달한 동시에 필수 동작 실패나 자료 해시 오류가 존재하면 `blocked`와 `manual-review`가 모두 적용된다. CLI·MCP·보고서가 서로 다른 판정을 계산할 수 있다. 선택 요구가 검사 대상에서 제외됐는데 ‘모든 요구 대응’이라고 표시될 가능성도 있다.
- 최소 수정: 불완전 실행의 판정 null → 자료·권한·기준 오류와 필수 검사 실패의 blocked → 통과 자료가 있어도 사람의 의도·범위 결정이 필요한 manual-review → 나머지 ready 순으로 정의한다. 수정 한도 도달은 조치 코드로 보존하되 필수 실패를 검토 필요만으로 축소하지 않는다. 모든 요구에는 통과·실패·선택 미실행·미확인 중 하나를 대응시킨다.
- 수용 시험: 같은 실행에 한도 도달·필수 실패·해시 오류·선택 미실행을 조합하고 모든 입구의 판정·종료 코드·조치가 동일한지 확인한다. 누락된 필수 자료를 종합 점수로 상쇄할 수 없어야 한다.

### R2-07 수정 실행의 상한 소유자와 중복 요청 관계 불명

- 심각도: 높음. 관련 요구: VCR-10·11·13·14.
- 문서 근거: `34-verified-change-design.md:47,75,142,152–154,178–182`; `contract.schema.json:928–1099`.
- 반례: `repair(case, run) -> run`에서 수정 후보 검사마다 새 run을 생성하고 상한을 초기화하면 수정 2회·전체 1,800초·제공자 요청 12회·비용 상한이 전체 수정 요청에 적용되지 않는다. 같은 MCP request ID를 다른 case·후보·상한·작업으로 재사용할 때 ID만 조회하면 다른 요청의 결과를 반환할 수 있다.
- 최소 수정: 한 사용 요청의 상한을 소유하는 실행 단위를 확정한다. 첫 범위에서는 한 repair 실행 안에서 모든 수정 시도·후보 검사·정리를 계산하고 완료 run 한 건을 공개하는 방식이 가장 단순하다. 이전 run을 입력으로 하는 별도 명시적 repair 요청은 새로운 승인 상한을 표시한다. request ID는 작업 종류와 고정 입력·상한의 일치 여부를 함께 확인하며 다른 입력의 같은 ID는 충돌로 처리한다.
- 수용 시험: 반복 수정·검사·429 재시도·연결 종료를 조합해 한 요청 전체가 상한을 넘지 않는지 확인한다. 같은 ID와 같은 입력은 실행을 중복하지 않고, 같은 ID와 다른 case·후보·작업·상한은 오류여야 한다. 중단 이후 status 조회는 재실행하거나 예약을 해제하지 않아야 한다.

### R2-08 필수 요구의 일부 검사만 필수로 설정할 수 있음

- 심각도: 높음. 관련 요구: VCR-02·03·06·13.
- 문서 근거: 저장 초안 `35-verified-change-storage.md:78`의 SC-02는 필수 요구에 최소 하나의 필수 검사만 연결하도록 정의한다. `34-verified-change-design.md:150`은 모든 요구 대응을 ready 조건으로 사용한다.
- 반례: ‘검색과 모바일 표시’를 하나의 필수 요구로 승인하고 검색 검사는 필수, 모바일 표시는 선택으로 연결한다. 검색만 통과해도 나머지 필수 요구가 확인되지 않은 채 ready로 판정될 수 있다. 사용자에게 전체 요구 완료를 표시한다면 잘못된 통과다.
- 최소 수정: 첫 계약은 OR 검사군을 제공하지 않으므로 필수 요구에 연결한 모든 검사를 필수로 제한한다. 선택 검사로 확인할 요소는 명시적 선택 요구로 분리한다. 검사로 표현할 수 없는 필수 의도는 미확인으로 유지하며 완료로 계산하지 않는다.
- 수용 시험: 필수 요구에 필수 검사 하나와 선택 검사 하나를 연결한 case를 관계 검사에서 거부한다. 연결된 필수 검사의 실패·미실행·누락 하나라도 있으면 ready를 금지한다.

### R2-09 실행기의 실제 대상이 로컬인지 불명

- 심각도: 중간. 관련 요구: VCR-08·09·18.
- 문서 근거: `34-verified-change-design.md:122–126`은 Docker 호환 실행기의 보호 정책을 정의하지만 실제 endpoint의 범위를 명시하지 않는다.
- 반례: 사용자의 Docker context 또는 DOCKER_HOST가 원격 daemon을 지정하면 같은 명령이 외부 실행기에 파일을 전달하거나 그 환경의 파일을 사용한다. 로컬 검사로 안내하면 개인정보와 실행 경계가 달라진다.
- 최소 수정: 첫 범위는 승인한 로컬 실행기로 제한하고 실제 적용되는 context·endpoint를 확인한다. 원격 대상이나 로컬 여부 미확인은 자동 실행·파일 전달 없이 `isolation_unavailable`로 종료한다. 원격 실행 서비스를 새로 설계할 필요는 없다. 승인된 Git 기준의 조회는 `.git`의 복사·모델 입력 제외와 구분한다.
- 공식 근거: [Docker contexts](https://docs.docker.com/engine/manage-resources/contexts/)는 로컬·원격 context와 환경 변수·명령 인자가 실행 대상을 변경하는 조건을 설명한다.
- 수용 시험: 원격 context·DOCKER_HOST·상충하는 설정을 주입해 파일 전달과 원격 작업 생성이 없는지 확인한다. 선택된 로컬 대상이 준비 이후 변경되면 실행 전에 중단해야 한다.

### R2-10 미정 비용 조정 기록의 계약 누락

- 심각도: 중간. 관련 요구: VCR-11·13·18.
- 문서 근거: `35-verified-change-storage.md:69`는 수동 확인 또는 제공자 조회로 조정한 별도 기록을 요구한다. 논리 테이블은 `35-verified-change-storage.md:11–21`에 정의되어 있다.
- 반례: 완료 run은 불변인데 미정 비용을 해제할 별도 기록의 키·대상·근거·확인 주체·금액·승인 관계가 없다. 구현자가 원래 run을 변경하거나 형식이 없는 기록으로 상한을 해제할 수 있다. 반대로 미정 예약을 안전하게 보존하면 지원한다고 설명한 조정을 할 수 없다.
- 최소 수정: 첫 버전은 미정 예약 보존과 추가 모델 요청 차단만 지원하고 비용 조정 기능은 별도 계약 이후의 기능으로 제외한다. 이 방법은 신규 테이블·명령·관리 기능을 추가하지 않는다. 조정 기능을 도입한다면 원 call_id·근거 자료·확인 책임·정산값·시각·기존 기록 보존을 별도 계약으로 정의해야 한다.
- 수용 시험: 일반 파일이나 임의 조치 문구로 미정 예약을 해제할 수 없어야 한다. 미정 비용 때문에 차단된 요청은 조회만으로 실행을 재개하거나 원래 run을 수정하지 않아야 한다.

### R2-11 문서 검사기가 핵심 관계의 반례를 수용함

- 심각도: 높음. 관련 요구: VCR-05·06·12·13·17.
- 근거: `check_verified_change_design.py:61–65,105–107,147–149,153–175`; `35-verified-change-storage.md:63,79–89`; `34-verified-change-design.md:154,172–180`. 기준·후보·원본을 변경하지 않고 예시만 메모리에서 변형해 검사했다.
- 반례 실행 시 SHA256: 검사기 `a694cb11f3ab3a8b681d273ac4a55f052dc777dccc9e257f9244662039925dc1`, 예시 `79f0c8a711a6717ba1b91ce2d1e509e449ba2c562fbd38436e7be0972529457b`, schema `5dc80f87716599427dc185cb9570d049458008df0e901f3608bac1a933e5e141`.
- 실제 조회 결과: 기존 긍정 예시의 ① criteria_match=false인 manual-review ② source_run_id=null인 repair ③ 기준 핵심 보존 결과의 project-report ④ blocked run을 참조하는 managed apply ⑤ 검사 정의 입력의 criteria 역할을 source로 변경한 case가 모두 schema와 semantic_errors에서 오류 없이 수용됐다. blocked run의 해시는 해당 변형 바이트로 계산해 단순 해시 오류를 배제했다. 이어서 ⑥ 고정 기준과 무관한 update.before_sha256 ⑦ 기준에 존재하는 파일의 create/null before 분류 ⑧ 변경 허용 범위에 기준 파일 추가도 수용됐다. 변경 묶음의 해시는 변형 내용과 일치하도록 계산했다. 명령은 격리된 기존 Python 환경에서 `PYTHONDONTWRITEBYTECODE=1`로 실행했으며 독립 출력 여덟 건 모두 `accepted: true, errors: []`였다.
- 반례: 문서 검사 통과가 선언한 관계·판정 경계를 모두 검사했다는 근거로 사용될 수 있다. 특히 필수 오류를 검토 필요로 축소하거나 blocked 자료를 원본 반영의 입력으로 승인할 수 있다. 실제 제품의 실행 결함을 발견한 것으로 확대하지 않는다.
- 최소 수정: 기준 역할의 일치, repair 원 실행의 존재·동일 사례, 필수 보존의 독립 기준 관찰, manual-review의 무결성과 보존 통과, 관리된 반영의 ready·완료 자료 조건을 의미 검사에서 강제한다. 기준의 source 존재·해시·mode를 변경의 before 상태와 연결하고 criteria·fixture·reference·environment를 변경 허용 범위에서 제외한다. 위 여덟 변형을 거부 예시에 추가한다. 첫 범위의 managed apply가 ready만 받는 조건을 본문에 명시한다.
- 수용 시험: 여덟 변형이 각각 의미 검사에서 거부되고 기존 정상 예시가 유지되는지 독립 재실행한다. 문서 검사의 다른 미포함 관계는 실행 수용 기준으로 유지하며 구현 완료나 제품 우위로 계산하지 않는다.

## 3. 도입 방향에 대한 독립 판단

범위를 제한한 독립 검사·선택 수정은 현재 `RuntimeValidator`, `ReleaseGate`, 파일 자료의 책임을 재사용하면서 VCR-02~06·14·15의 실제 간격을 줄인다. 모델 없는 검사, 원본 반영과 검사 분리, 고정 기준과 요구별 결과는 범위 확대보다 목표에 직접 대응한다. 따라서 **문서 수준의 목표 적합성이 기존 방향보다 개선될 근거는 있다**. 이는 실제 작업 시간·정확성 우위의 판정이 아니다. 근거: `34-verified-change-design.md:17–27,73–82,188–204`, `2026-10-14-analysis.md:42–79`.

추가 서버·외부 DB·작업 대기열·새 조율 도구를 제외하고 현재 파일 자료를 보강하는 선택은 현재 단일 사용자·사례별 조회 범위에서 설명 가능하다. JSON의 관계·동시 작성·중단 복구 책임을 저장 설계에서 실제로 정의해야 한다. 승인 기준을 다른 process와 파일 공간에 두는 것은 앱의 쓰기 권한을 제한하기 위한 구성이다. 더 강한 분리를 이유 없이 여러 서비스나 모델 합의로 확대할 필요는 없다. 근거: `34-verified-change-design.md:57–82,158–162,208–215`, `2026-10-14-analysis.md:71–87`.

기능의 희귀성·업계 우위·생산성·스타 수는 이번 검토에서 입증하지 않았다. 실제 대안과의 비교는 D4의 조건이다. 지적과 최종 필드·수용 기준의 재검토 결과는 아래에 기록한다.

## 4. 최종 스냅샷 재검토

최종 묶음의 목표·저장·검증·용어·schema·예시·검사기·실패 전후 기록·현재 소스 대조 기록을 재검토했다. 본문 문구 수정과 문서 검사 통과를 구현 시험 통과로 계산하지 않는다.

| 지적 | 최종 문서·검사 대응 | 2심 재확인 |
|---|---|---|
| R2-01 | 목표 §5:88의 복사 전후 전체 상태·편집 제한·snapshot_changed | 문서 조건 해소; VCT-04 실제 실행은 미실행 |
| R2-02 | 목표 §6:100·저장 SC-07의 project-report/trusted-observer·동일 process 제한 | 문서 조건 해소; VCT-21 실제 실행은 미실행 |
| R2-03 | 목표 §7:124–130의 별도 파일/PID·공통 제어 port 금지·보호 브라우저·정책 확인 | 문서 조건 해소; VCT-09·22 실제 실행은 미실행 |
| R2-04 | 목표 §8:164·저장 §3:69–71의 HTTP 시도별 예약·SDK 재시도 0·미정 보존 | 문서 조건 해소; VCT-11 실제 실행은 미실행 |
| R2-05 | 목표 §10:176–184·저장 §6:123–127의 전체 상태·복구·외부 편집 제한 | 문서 조건 해소; VCT-12·25 실제 실행은 미실행 |
| R2-06 | 목표 §8:154–160·저장 SC-05의 필수 오류 우선·manual-review 필수 통과 | 문서 조건 해소; 판정 거부 예시 재실행 |
| R2-07 | 목표 §8:150·§11:190·저장 §3:63–71의 한 요청 소유·회차·중복 ID 충돌 | 문서 조건 해소; VCT-23·24 실제 실행은 미실행 |
| R2-08 | 저장 SC-02·검사기 semantic_errors(case)의 필수 요구 전체 연결 강제 | 해당 거부 예시 직접 재실행 |
| R2-09 | 목표 §7:128과 Environment의 local 조건 | 원격 거부 예시 직접 재실행; 실제 Docker는 미실행 |
| R2-10 | 저장 §3:71의 비용 조정 기능 제외·미정 예약 보존 | 추가 테이블 없이 문서 조건 해소 |
| R2-11 | 저장 SC-03·05·07·08·12와 검사기의 기준 역할·보존 관찰·ready 반영·before 상태 | 원래 방법의 변형 여덟 건 모두 의도한 오류로 거부 |

### 독립 실행 확인

기존 격리된 Python 환경의 검사기를 `PYTHONDONTWRITEBYTECODE=1`, `--output /dev/null`로 직접 실행했다. 결과는 정의 21개·필드 202개·정상 예시 10개·거부 예시 44개 모두 54개 일치, VCR 20개·VCT 30개·로컬 참조 26개, 실패 0이었다. 실행 종료 코드도 0이었다. 구현 증거와 제품 효과 증거는 모두 0이다. 이는 원래 긍정 예시가 유지되고 선언한 문서 제약의 거부 예시가 동작한다는 확인이다.

R2-11의 변형은 원본 파일을 변경하지 않고 메모리에서 다시 구성했다. 요청·변경 해시는 변형 바이트에 맞춰 계산해 무관한 해시 오류를 배제했다. 다음 오류를 각각 직접 확인했다.

| 독립 반례 | 수정 후 실제 오류 |
|---|---|
| 무결성 오류가 있는 manual-review | integrity_not_complete |
| 원 실행이 없는 repair | repair_source_missing |
| 기준 보존 UI의 project-report | untrusted_baseline_observation |
| blocked run의 관리된 반영 | apply_run_not_ready |
| 검사 정의를 프로그램 source로 분류 | criteria_role_mismatch |
| 기준과 무관한 update.before 해시 | before_not_baseline |
| 기준에 존재한 파일의 create 분류 | create_existing_baseline |
| 기준 파일을 변경 허용 범위에 추가 | protected_input_in_scope |

이 여덟 변형은 위 44개 거부 예시에 반영된 동일 위험의 재검토다. 새로운 독립 제품 표본 여덟 개로 계산하지 않는다. root가 보존한 실패 전 기록은 `2026-10-14-validation-before-fix.json`이며 수정 전 여덟 거부 예시가 실제로 실패했음을 확인했다. 최종 검사기 SHA256은 아래 표와 같다.

현재 기준 기록의 source_sha256 154건을 파일 바이트에서 직접 재계산했으며 불일치는 0건이었다. 이전 제품 시험을 다시 실행하지 않았다. 현재 제품의 타입 오류·브라우저 실패, 모델 품질·격리·비용·동시 편집·생산성 효과의 미검증은 구현 단계의 과제로 유지한다. 근거: `2026-10-14-baseline.json`, 검증 설계 §3·4.

### 최종 대상 SHA256

| 파일 | SHA256 |
|---|---|
| `34-verified-change-design.md` | `9ca59e36fb8032a49c3250d5686c5a0a2d42949bf5bddc1dc9d06a6521ce58da` |
| `35-verified-change-storage.md` | `10d1a096fabb4694737fde245af951e7c16479bd600f7311db97185d6dc91cc0` |
| `36-verified-change-verification.md` | `da1f11f8a75caa7565747bd31f258f778296e69e3f4d485aab12b89a306a6f0e` |
| `verified-change/GLOSSARY.md` | `f0a644e162b963bdeb714acb40600167bb72d4f91a89cee1bc1ef99bbffa5725` |
| `verified-change/contract.schema.json` | `5dc80f87716599427dc185cb9570d049458008df0e901f3608bac1a933e5e141` |
| `verified-change/contract-examples.json` | `67ed7670f53d013ad21617c5b8f35d3ce54bd8ed9e9cc8203f256dba3ffc498f` |
| `reviews/check_verified_change_design.py` | `683fb6a0f97892d120a4c6dbf843976e8543a33736677835ff74b953de62b0b8` |
| `reviews/2026-10-14-document-validation.json` | `335076750cd1cd5bdd46dc0d631af54194d523fe3fb7722d4f1d80f336b16ee1` |
| `reviews/2026-10-14-validation-before-fix.json` | `041c4d454cec5418571725baac1cbee64f7ca727ac3fa944741af58c88eccf21` |
| `reviews/2026-10-14-three-review.md` | `28de6050172e51bbee1e0ed710d9bf15e04eb940fdf5a9fc69ac47820997dfb7` |
| `reviews/2026-10-14-baseline.json` | `f6e4e4622232ae819503032dace5c91c9973ffc111d013fd7968e3bc4a2c86aa` |

### 최종 판단

**문서확정가능.** 초기 높음 8건·중간 3건의 지적은 문서 계약 또는 검사 관계에서 해소됐다. 이 검토에서 미해결 중대 지적은 없다. 목표 적합성·현재 책임의 재사용·원본 보호·검사의 진실성·상한 소유·저장·복구의 설명은 초기 방향보다 개선됐다고 판단한다. 3심은 이 스냅샷과 후속 변경을 구분해 확인해야 한다.

실제 OS·브라우저·모델·원본 반영의 신뢰성, 업계 우위, 생산성, 사용자 편의성의 실측은 확정하지 않았다. D0~D4의 실행 조건과 독립 제품 평가가 남아 있다. 누구도 반론할 수 없거나 절대적으로 100점이라는 판정은 하지 않는다.
