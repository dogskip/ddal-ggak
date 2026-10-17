# 같은 조건의 비교 절차

이 기능은 입력을 준비하고 제출된 비교 기록을 검증합니다. 모델 호출·비용 승인·외부 공개는
수행하지 않으며 `calibrated`는 false로 유지합니다. 기존 [재현 시험](REPRODUCTION.md)은
별도의 인수 기준 검사입니다.

## 고정한 비교 사례

[정본 목록](../src/ddk/assets/benchmarks/paired-corpus.json)은 실제 소스 3곳을 고정합니다.
작고 재현 가능한 기능을 선택해 의도적으로 결함을 추가한 사례입니다. 원래 저장소에서 발견한
결함이나 전체 프로젝트를 대표하는 표본으로 해석하지 않습니다.

| 소스 | 고정 커밋 | 과제 |
| --- | --- | --- |
| [Click 8.3.0](https://github.com/pallets/click/tree/00fadb8904387158ce6e9aa1573be770446895c1) | `00fadb8904387158ce6e9aa1573be770446895c1` | 짧은 파일명 복원, 전체 경로와 잘못된 바이트 처리 보존 |
| [clsx 2.1.1](https://github.com/lukeed/clsx/tree/925494cf31bcd97d3337aacd34e659e80cae7fe2) | `925494cf31bcd97d3337aacd34e659e80cae7fe2` | 참인 객체 항목 선택 복원, 중첩 배열과 거짓 값 제외 보존 |
| [Hyperapp 2.0.22](https://github.com/hyperapp/hyperapp/tree/876d3f44d0ae601de181714c583a07d83d3472c9) | `876d3f44d0ae601de181714c583a07d83d3472c9` | 동작 등록 복원, 초기 표시와 초기화 보존 |

과제마다 세 회차(1729·2718·3141)와 두 조건을 사용합니다. 같은 회차의 초기 소스는 동일하며
총 18건입니다. 회차 번호만으로 모델의 난수 제어가 지원된다고 판단하지 않습니다.
실제 추출 설정과 미지원 조건을 기록합니다.

## 준비와 승인

고정한 공개 태그의 사본을 별도 폴더에 준비합니다. 준비 명령은 기존 Git 조회·복사 기능을
사용해 커밋·파일 해시·유일한 변경 위치를 확인하고, 독립된 `bench-source` 저장소를 만듭니다.
초기 소스·요청 해시를 보관하며 전체 허용 소스와 시험용 프로그램도 해시로 고정합니다.
의존성 설치나 모델 호출은 수행하지 않습니다.

```sh
uv run python scripts/paired_benchmark.py prepare \
  --source click=/tmp/ddk-upstreams/click \
  --source clsx=/tmp/ddk-upstreams/clsx \
  --source hyperapp=/tmp/ddk-upstreams/hyperapp \
  --out /tmp/ddk-paired
```

대상 폴더는 새 경로여야 하며 실패한 시도의 자료도 유지합니다. `preparation.json`의 상태는
기준 승인 필요입니다. 모델 실행 전에 목표·보존 검사, Case 해시, 실행 도구·모델 판,
토큰·시간 상한과 총비용을 사용자가 승인해야 합니다.

준비 결과에는 `draft: true`인 JSON 초안 3개와 각각의 해시가 포함됩니다. 변경 범위는
기존 과제의 소스 파일 하나입니다. 두 조건에 같은 시험용 프로그램을 포함하며 Click은
실제 Python 함수 결과를, clsx는 후보 모듈 결과를, Hyperapp은 실제 화면 동작을 확인합니다.
목표·보존 조건의 브라우저 검사는 기존 Case 규약을 유지합니다. 시험용 프로그램의 변경은
허용 범위에 포함하지 않습니다.

검토한 초안의 SHA-256을 각각 지정해야 `seal`이 Case를 생성합니다.

```sh
uv run python scripts/paired_benchmark.py seal \
  --preparation /tmp/ddk-paired/preparation.json \
  --approved-draft click-short-name=REVIEWED_CLICK_DRAFT_SHA256 \
  --approved-draft clsx-object-flags=REVIEWED_CLSX_DRAFT_SHA256 \
  --approved-draft hyperapp-events=REVIEWED_HYPERAPP_DRAFT_SHA256 \
  --out /tmp/ddk-paired/sealed-cases.json
```

대문자 값은 예시용 표시입니다. 초안을 수정했다면 수정본을 검토한 해시가 필요합니다.
생성 전에 18개 폴더의 초기 소스·요청·시험용 프로그램·중복 여부와 고정한 전체 소스를
검사합니다. 링크·경로 이탈·기존 출력은 거부합니다. 과제마다 Case 하나를 생성해 DDK
조건의 세 폴더에 같은 기록을 등록합니다. 일반 조건에는 DDK 기록을 생성하지 않습니다.
결과에 Case ID·해시·경로를 포함하며 비교 조건의 `case_sha256`에 사용합니다. 후반부에서
실패하면 부분 기록을 유지하므로 새 준비 자료에서 재시도해야 합니다.
준비와 Case 생성은 사용자 권한 실행·제공자 전송·비용 지출을 승인하지 않습니다.
Case 생성은 설치된 브라우저를 확인하지만 후보 코드는 실행하지 않습니다.

DDK 조건은 `ddk up --case-id CASE_ID --repo CANDIDATE --json`으로 같은 Case를 선택하며,
별도 실행 승인 아래에서만 `--trusted-local`을 추가합니다. 초기 Git 커밋을 기준으로 유지하고
모델 수정 후 새 Case를 생성하지 않습니다. 기준과 시험 결과는
[브라우저 Case 설명](BROWSER-CASES.md)에 정리합니다.

## 같은 조건의 실행

도구·모델 판, 추출 설정, 기본 지시, 요청, 초기 소스, 환경, 토큰·시간·비용 상한을 맞춥니다.
DDK 검사와 피드백 사용만 다르게 하며 일반 시험 도구는 동일하게 허용합니다. DDK 커밋과
별도 검사 프로그램의 SHA를 고정합니다. 정본 지침 3개의 차이를 추가 변수로 도입하지 않습니다.

회차별로 실행 순서를 교차하고 매번 새 대화와 독립 작업 폴더를 사용합니다. 대화 ID를 보관하고
두 조건 사이에 수정 조언이나 결과를 전달하지 않습니다. 관찰·사용량·대화 자료는 후보 폴더
밖에 보관합니다. 실패·시간 초과·취소·blocked·상한 소진을 모두 포함하며 재시도로 기존 관찰을
덮어쓰지 않습니다.

유료 호출 전에 도구의 실제 비용 제한을 확인해야 합니다. 기록 검증 기능은 외부 도구의 지출을
직접 제한하지 않습니다. 미정 비용은 null이며 로컬 모델도 명시적인 무료 근거가 필요합니다.
장비 비용과 사람의 작업 시간은 모델 API 비용에 포함하지 않습니다.

## 별도 관찰

고정 검사 프로그램은 후보의 시험 파일 밖에서 실제 소스를 실행합니다. Python·Node 실행은
출력·시간 상한, 소유한 작업의 종료 확인, 제한한 환경변수를 사용합니다. Hyperapp은 새 headless
Chromium에서 보호 설정을 적용하고 외부 요청을 거부합니다. Python·Node 프로젝트 실행은
명시적 `trusted-local`이며 사용자 권한을 사용합니다. OS 격리는 제공하지 않으므로 승인한
신뢰 소스와 변경에만 사용합니다.

```sh
uv run python scripts/paired_benchmark.py oracle \
  --task hyperapp-events --repo /tmp/ddk-paired/hyperapp-events/1729/ddk \
  --seed 1729 --arm ddk --trusted-local --out /tmp/hyperapp-observation.json
```

세 시험의 실행·실패 수, 실제 후보 해시, 시간, 검사 프로그램 SHA를 보관합니다. 목표·보존·추가
동작을 확인하며 판정 미달은 1로 종료합니다. 실행 실패나 시험 0개는 통과가 아닙니다.
관찰 중 소스 변경을 거부하며 실제 종료 값을 JSON 결과와 별도로 보관합니다.

DDK 조건은 완료된 정본 Run과 일치하는 후보·Case 해시, 증거, Run SHA가 필요합니다.
저장된 ready와 별도 검사의 실패는 다른 관찰이며 두 결과가 충돌하면 잘못된 수용으로 집계합니다.

## 기록 규약

`ddk.services.paired_benchmark`의 엄격한 자료형이 규약을 정의합니다.
`ddk-paired-receipts/1`은 목록 해시, 신고한 출처, 공통 조건과 18건을 포함합니다.
도구 기록은 같은 조건·실행 값과 고유 대화 ID, 자료 해시를 연결합니다. 모든 참조는 상대 경로와
SHA-256을 사용하며 폴더 이탈이나 링크 경유를 허용하지 않습니다.

공통 조건은 도구·모델·DDK 판, 환경·추출·권한 해시, 승인된 Case 해시 3개, 토큰·시간·비용 상한을
포함합니다. 각 건은 소스·요청 해시, 호출·비용·시간, 도구의 완료 주장, 별도 관찰과 DDK Run을
보관합니다. 해시 대조만으로 실제 계정·모델·지출이나 비교 조건의 준수를 인증하지 않습니다.
대화 자료의 독립 검토가 필요합니다.

```sh
ddk bench --json
ddk bench --receipts /tmp/ddk-paired/receipts.json --json
```

자료가 없으면 미측정으로 1을 반환합니다. 누락·비용 미정·시험 생략·시험 0개·상한 초과는
불완전 상태로 유지하며, 무결성·규약·조건 불일치는 5로 종료합니다. 정상적으로 관찰한 실패는
전체 비교에 포함합니다. JSON의 통과 표시가 실제 비정상 종료를 무효화하지 않습니다.

## 해석

두 조건의 판정·별도 검사 통과·실패·잘못된 수용·거부, 시간과 기록 비용을 제공합니다.
시험용 기록의 실측 건수는 0입니다. 출처 문구를 실측으로 바꾸어도 신고 건수만 바뀌며
`measured_records=0`, `measurement_review=not-reviewed`, `calibrated=false`를 유지합니다.
독립 검토를 교정 값으로 반영하는 기능은 아직 없습니다. 검토와 승인된 실측 전에
`gsd-baseline.json`을 변경하거나 비교 우위를 주장하지 않습니다.

최초 로컬 확인에서는 독립 작업 사본 18개를 만들고 원본·결함·직접 복원 상태 9건을 모델 호출
없이 구분했습니다. 이는 준비·검사 프로그램의 확인이며 모델 수리 성공률이나 제품 우위가 아닙니다.
