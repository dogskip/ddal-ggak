# 사용 설명서

내 프로젝트에서 딸깍을 실행하고, 보고 내용을 읽고, 잘못 나온 결과를 다루는 방법입니다. 전체 소개와 설정 표는
[README](../README.ko.md)에 있고, 이 문서에는 세부 내용이 있습니다. English: [USER-GUIDE.md](USER-GUIDE.md).

## 1. 설치

Python 3.12 이상, [uv](https://docs.astral.sh/uv/)(또는 pipx, pip), npm 이 들어 있는 Node.js 20.19 이상
또는 22.12 이상, 그리고 Chrome·Edge·Chromium 중 하나가 필요합니다. 실제로 중요한 Node.js 버전은 내
프로젝트가 요구하는 버전이며, 위 버전은 데모의 Vite 7 이 요구하는 것입니다.

```bash
uv tool install git+https://github.com/dogskip/ddal-ggak    # PATH 에 `ddk` 가 생깁니다
ddk --help
```

설치하지 않고 실행하려면 `uvx --from git+https://github.com/dogskip/ddal-ggak ddk <명령>` 을 사용합니다.

## 2. 환경 점검

```bash
ddk doctor
```

한 줄이 검사 하나입니다. Python, uv, API 키, Node.js, git, 헤드리스 Chromium 을 확인합니다. 필수 검사가
실패하면 종료 코드 1 이고, 경고는 선택 항목입니다. 브라우저 줄에 경고가 나오면 `ddk doctor --install-browser`
(Playwright 의 헤드리스 Chromium 을 한 번만, 약 100MB 내려받습니다)를 실행하거나 Chrome 을 설치하세요.
브라우저는 `DDK_CHROMIUM_PATH`, Playwright 의 Chromium, 설치된 Chrome·Chromium·Edge 순으로 찾습니다.
최소 구성의 Linux 이미지에서는 Chromium 에 시스템 라이브러리도 필요하며, Playwright 의
`install-deps chromium` 이 설치해 줍니다.

## 3. 데모 실행

```bash
ddk demo                  # 파일을 보관하려면: ddk demo --workdir ./demo-out
```

데모는 작은 Vite + React + TypeScript 프로젝트를 임시 폴더에 복사하고 `npm ci` 로 설치한 뒤, 내장
와이어프레임으로 전체 절차를 실행합니다. API 대신 미리 녹화한 모델 응답을 재생하므로 키가 필요 없습니다.
첫 시안은 일부러 조금 어긋나 있습니다. 화면 비교가 그것을 잡아내고, 수정 뒤에 `ready` 로 끝납니다. 마지막
줄들이 열어 볼 파일을 알려 주며, 증거 보고서가 맨 앞입니다.

## 4. 내 디자인으로 실행

### 저장소 준비

- `package.json` 이 있고 의존성이 설치되어 있어야 합니다(`npm install`, 또는 pnpm·yarn·bun 의 같은 명령).
  아니면 `--install` 을 붙이세요. 그러면 임시 복사본에서 생명주기 스크립트를 실행하지 않고 설치합니다.
- 검사할 대상이 있어야 합니다. `build` 스크립트, TypeScript 설정, ESLint 설정입니다. 셋 다 없으면
  검증할 것이 없어서 판정은 `blocked` 입니다.
- 화면 비교에는 Vite, Next.js, Astro 가 필요합니다. 빌드한 앱을 띄워야 볼 수 있기 때문입니다. 그 밖의
  구성은 `--no-visual` 이 필요합니다.
- 내 작업은 먼저 커밋하거나 stash 하세요. `ddk run` 은 내 파일을 건드리지 않지만(추가되는 것은 7장 참고),
  `ddk apply` 는 파일에 기록합니다.

### 실행

```bash
export ANTHROPIC_API_KEY=sk-ant-...
ddk run design.png
ddk run hero.png pricing.png -p "Next.js app router, Tailwind, 기존 Button 유지"
```

이미지는 PNG, JPEG, WebP, GIF 를 지원하며, 모델에 보내기 전에 긴 변을 1568px 이하로 줄입니다. 이미지가
여럿이면 코드를 작성하고 디자인 시스템을 추론할 때는 모두 모델에 보여 주지만, 디자인 분석과 화면 비교에는
**첫 번째** 이미지만 사용합니다. `-p` 가 없으면 이미지를 그대로 구현하되 저장소의 규칙을 따르라고
요청합니다.

진행 상황은 단계마다 한 줄씩 출력됩니다. 입력 확인, 저장소 분석, 디자인 분석, 디자인 시스템 추론, 생성 계획,
코드 생성, 관례 정리, 검증(빌드, 타입, 린트, SSIM 이 붙은 화면), 자동 수정 시도, 판정 순서입니다. 모델을 호출하기
전에 API 키 누락, 읽을 수 없는 이미지, 시작할 수 없는 브라우저가 있으면 실행이 멈추므로(종료 코드 1), 실패할
것이 뻔한 실행에는 비용이 들지 않습니다.

실행이 끝나면 패널(case ID, 판정, 점수, 보고서 경로)과 종료 코드가 나옵니다. 판정이 `ready` 이면 **0**,
다른 판정이거나 시작하지 못했으면 **1**, 설정이 잘못됐으면 **2** 입니다. `--json` 은 같은 내용을 표준 출력에
JSON 으로 출력하며(진행 상황은 표준 오류로 나갑니다), 스크립트와 에이전트는 이것을 읽으면 됩니다.
`release_decision`, `terminal_state`, `scorecard_overall`, 그리고 보고서 경로인 `report` 가 들어 있습니다.

### 결과 읽기

```bash
ddk report --open      # HTML 한 장: 판정, 비교 회차, 수정, 검사, 점수
ddk status             # case 상태, 판정, 자동 수정 횟수 (가장 최근 case. --case-id C-002 로 지정)
ddk certify            # 점수표와 증거 묶음이 붙은 판정
```

보고서에서는 판정 카드를 먼저 보고, 그다음 스크린샷 회차를 보세요. *디자인*, *결과 화면*, 빨간색 *차이*가
나옵니다. 겹쳐 보기의 막대를 끌면 결과와 디자인을 번갈아 비교할 수 있습니다. *검사* 표는 빌드, 타입 검사,
린트, 화면 비교와 각각의 소요 시간을 보여 주며, 건너뛴 단계는 이유가 적혀 있습니다. *점수표*는 네 가지
하위 점수(정밀도, 유지보수성, 자동화, 확장성)의 평균입니다. 고정된 공식이 검사 결과, 수정 이력, 관례
정리에서 계산하며, 모델에게 점수를 매기게 하지 않습니다.

| 판정 | 뜻 | 할 일 |
| --- | --- | --- |
| `ready` | 차단 사유가 없고 점수가 0.85 이상 | 보고서를 읽고 `ddk apply` |
| `manual-review` | 자동 수정이 포기했거나 점수가 0.85 미만 | 보고서를 열고, 직접 적용하거나 프롬프트를 고쳐 다시 실행 |
| `blocked` | 검사가 실패했거나, 화면을 비교하지 못했거나, 검증된 것이 없거나, 환경이 검사를 실행하지 못함 | 보고서가 차단 사유를 나열합니다. 원인을 해결하고 다시 실행 |

### 적용

```bash
ddk apply --dry-run    # 파일별 표: 새 파일 / 수정 / 변경 없음 / 충돌 / 거부
ddk apply              # 파일 적용
```

`ddk apply`는 `ready`가 아닌 case를 거부합니다. 실행 시작 시점의 버전이 그대로 있거나 아직 없는
파일만 반영합니다. 충돌이나 안전하지 않은 경로가 하나라도 있으면 중단합니다. 교체 파일의 사본은
`.ddk/cases/<id>/artifacts/replaced/`에 보관합니다. 양쪽 변경을 검토해 충돌을 해결하세요.
`--force`와 `--allow-blocked`는 호환 옵션으로만 유지하며 종료 값 2로 중단합니다.

`ddk rollback`도 종료 값 2로 중단합니다. 저장소 전체 초기화는 제공하지 않습니다.
기존 변경 case는 별도의 [기존 변경 검사 절차](VERIFIED-CHANGES.ko.md)를 사용합니다.
`change export`로 검토 자료를 생성하고, `change apply`로 반영 기록을 보관하며,
`change recover`로 중단된 반영을 현재 파일과 대조해 복구합니다. 기존 이미지 실행의 반영이나
완료된 반영을 취소하는 기능은 아닙니다. 기존 반영을 정리할 때는 자신의 Git 변경과 사본을 보존하세요.

## 5. 실행 조절

| 하고 싶은 것 | 방법 |
| --- | --- |
| 다른 지시 | `-p "..."` |
| 더 엄격하거나 느슨한 일치 | `--ssim-threshold 0.95`, `--max-mismatch 0.01` (또는 `DDK_*` 변수) |
| 수정 반복 횟수 조절 | `DDK_MAX_RETRY_ATTEMPTS` (1~10, 기본 3) |
| 더 저렴한 실행 | `DDK_LLM_MODEL` / `DDK_LIGHT_MODEL`, 상한은 `DDK_COST_CAP_USD` |
| 화면 비교 건너뛰기 | `--no-visual` (보고서에 면제로 기록됩니다) |
| 다른 case ID 나 저장소 | `--case-id C-007`, `--repo ../other-app` |

비용: 모든 모델 호출은 토큰 수와 가격이 case 폴더(`llm-calls.json`, 합계는 보고서)에 기록됩니다.
`DDK_COST_CAP_USD`(기본 2.0)에 도달하면 새 호출을 시작하지 않으며, 진행 중이던 호출은 한도를 넘겨서 끝날
수 있습니다.

## 6. 무엇을 검사하는가

`ddk` 는 프로젝트 자신의 파일만 읽고, 명령을 추측하지 않습니다.

- **빌드**: `package.json` 의 `build` 스크립트.
- **타입 검사**: `typecheck`, `type-check`, `check-types`, `tsc` 스크립트. 없으면 `tsconfig.json` 이 있고
  TypeScript 가 의존성일 때 `tsc --noEmit` 을 실행합니다(solution 방식의 `references` 를 따라갑니다).
- **린트**: `lint` 스크립트. 없으면 ESLint 설정이 있고 ESLint 가 의존성일 때 ESLint 를 실행합니다.
- **화면 비교**: 프로젝트 자신의 `vite preview`, `next start`, `astro preview` 를 루프백 주소에서 실행하고,
  첫 번째 디자인 이미지와 같은 크기의 헤드리스 Chromium 에서 전체 페이지 스크린샷을 찍습니다.

패키지 관리자는 잠금 파일을 따릅니다(pnpm, yarn, bun, 아니면 npm). 프로젝트에 없는 단계는 이유와 함께
*건너뜀* 으로 기록하고, 모든 단계를 건너뛰었다면 검증된 것이 없으므로 판정은 `blocked` 입니다. 페이지를
불러오는 동안 나타난 콘솔 오류와 실패한 요청은 실패로 계산합니다.

브라우저는 루프백 주소로만 접속할 수 있습니다. 원격 글꼴, 이미지, API 는 차단되므로, 이것들이 필요한
페이지는 빠진 채로 그려지고 비교도 그 모습을 기준으로 합니다.

## 7. 디스크에 남는 증거

```
.ddk/                           `ddk run` 이 추가하는 유일한 폴더. 스스로 제외하므로 git 은 건너뜁니다
  cases/C-001/
    artifacts/
      generated/                모델이 작성한 파일 (`ddk apply` 가 복사하는 것)
      inputs/                   내 디자인 이미지
      visual/round-1/…          비교 회차마다의 스크린샷, 차이 이미지, 수치
      replaced/                 `ddk apply` 가 교체한 파일
    reports/
      report.html               증거 보고서
      release-decision.json     판정과 차단 사유
      scorecard.json            네 가지 하위 점수와 등급
      evidence-pack.json        소요 시간, 비용, 종료 상태
      fix-attempts.json         수정 시도별 규칙, 파일, 결과
      runtime-validation-report.json   검사마다 명령, 종료 코드, 소요 시간
      llm-calls.json            모델 호출마다 토큰, 비용, 모델
      …                         계획, 디자인 분석, 저장소 프로필, 상태
```

`ddk report` 는 이 파일들만으로 HTML 을 다시 생성하며, `report.html` 은 그림까지 한 파일에 들어 있고 웹에서
아무것도 가져오지 않으므로 그대로 동료에게 보내도 됩니다.

`.ddk/` 말고도, 실행은 수정 회차마다 git ref 하나(`refs/ddk/fix/<case>/attempt-N`)를 만들어 그때 체크아웃된
커밋을 가리킵니다. 이 참조는 과거 점검 기록이며 전체 초기화 권한이 아닙니다. `ddk rollback`은
중단됩니다. 이력이 없는 저장소에는 생성하지 않습니다.

## 8. 문제가 생겼을 때

| 보이는 것 | 원인과 대처 |
| --- | --- |
| `No Anthropic API key found` | `ANTHROPIC_API_KEY` 또는 `DDK_ANTHROPIC_API_KEY` 를 지정하거나 `.env` 에 넣으세요 |
| `No Chromium found; run: ddk doctor --install-browser…` | 그 명령을 실행하거나, Chrome 을 설치하거나, `DDK_CHROMIUM_PATH` 를 지정하세요. `--no-visual` 은 화면 비교를 건너뜁니다 |
| `dependencies are not installed; run \`<설치 명령>\` or pass --install` | 저장소에서 먼저 설치하거나 `--install` 을 붙이세요 |
| `no preview command for this project (supported: vite, next, astro)` | 비교할 화면을 띄울 수 없습니다. `--no-visual` 을 사용하세요 |
| `vite is declared but not installed in node_modules` | 의존성을 설치하세요 |
| `No build, type-check or lint step applied…, so nothing was verified` | 빌드 스크립트, `tsconfig.json`, ESLint 설정 중 하나를 추가하세요 |
| 맞게 보이는 페이지에서 화면 비교가 계속 실패 | 보고서를 여세요. 애니메이션, 무작위·실시간 데이터, 원격 글꼴, 다른 뷰포트는 실행마다 달라집니다. 디자인 파일을 고치거나 `--max-mismatch` 를 완화하세요 |
| 수정 반복 뒤 `manual-review` | 같은 실패가 되돌아왔거나 횟수를 다 썼습니다. 보고서에 마지막 진단이 있으니 쓸 만한 부분을 직접 적용하세요 |
| 비용 한도 도달 | `DDK_COST_CAP_USD` 를 올리거나 더 저렴한 `DDK_LLM_MODEL` 을 사용하세요 |
| 출력 언어가 다름 | `DDK_LANG=en` 또는 `DDK_LANG=ko` |

그 밖에 이상하면 `DDK_LOG_LEVEL=DEBUG ddk run …` 이 자세한 내용을 출력합니다.

## 9. Design Studio

별도의 기능입니다. 아이디어를 설계 문서 열 개(SRS, PRD, 구조, API, 데이터베이스, 보안, 결정 기록, 테스트,
계획, AI 보조 도구용 인계 문서)로 바꿉니다.

```bash
ddk design new "AI 코드 리뷰 도구"                    # 먼저 몇 가지를 물어봅니다
ddk design new "AI 코드 리뷰 도구" -y -o ./docs       # 질문 없이, 폴더 지정
```

이 기능에도 API 키가 필요합니다. 자세한 내용은 [DESIGN-STUDIO.md](DESIGN-STUDIO.md)를 참고하세요.

## 10. 에이전트와 MCP

```bash
ddk install --detect       # 찾아낸 AI 코딩 도구 목록
ddk install --claude       # 또는 --cursor, --codex, --gemini, --opencode, --copilot, --kiro, --all
```

`/ddk:design`과 MCP 서버 `ddk serve`를 등록합니다. 도구는 `design_new`, `preflight`,
`ddk_version`, `ddk_verify`, `ddk_status`입니다. 기존 변경 검사는 고정 입력과 격리 실행을 요구하며,
MCP는 반영·복구·trusted-local 실행을 공개하지 않습니다.
[기존 변경 사용 설명서](VERIFIED-CHANGES.ko.md)를 참고하세요.

이미지 생성은 CLI에서 실행합니다. 셸 도구가 있다면 `ddk run <이미지> --json`을 호출하고
`release_decision`과 `report`를 조회합니다. 예정 기능과 완료 조건은 [후속 계획](../ROADMAP.ko.md)에
있습니다.
