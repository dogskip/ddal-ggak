# Phase 07 Plan — 스스로 검증하는 루프

## 목표

디자인 이미지에서 만든 코드를 빌드하고, 실제 브라우저로 디자인과 비교하고, 어긋나면 고쳐서 증거와 함께
판정하는 전체 절차를 키 없이도 눈앞에서 돌려 보이게 하고(`ddk demo`), 실제 저장소에서도 같은 절차가 끝까지
동작하게 한다. 사용자가 처음 만나는 설치·문서·배포 파일까지 갖춘다.

## 전역 제약

- 커밋, 푸시, 게시를 하지 않는다. 공개용 초안은 문서로만 둔다.
- 브라우저는 헤드리스로만 연다.
- 기존 공개 계약(`ddk run/status/certify/rollback`, MCP 도구 3종)을 깨지 않는다.
- 행동 변경은 실패하는 테스트를 먼저 작성한다.
- 확인하지 못한 것은 확인했다고 적지 않고 잔여 위험으로 기록한다.

## Task 1 — 실제 브라우저 비교

- [x] 헤드리스 Chromium 어댑터: 스크린샷, 콘솔 오류, 실패한 요청 수집 (`adapters/chromium_browser.py`)
- [x] 시각 판정: 회색조 8×8 블록 SSIM ≥ 0.92 그리고 크게 다른 면적 ≤ 3% (`--ssim-threshold`, `--max-mismatch`)
- [x] 미리보기 서버는 Vite, Next.js, Astro. 그 밖의 프레임워크와 브라우저·증거 부재는 `blocked`
      (`--no-visual` 로 면제)

## Task 2 — 자동 수정

- [x] 규칙 R-01, R-06(결정적), R-09(파일별 모델 호출), R-10(시각, 코드 진단이 사라진 뒤에만)
- [x] 중단 조건: 회차 예산(`DDK_MAX_RETRY_ATTEMPTS`, 기본 3), 같은 실패 서명 반복, 변경 없음
- [x] 회차마다 git 점검점 `refs/ddk/fix/<case>/attempt-N` (되돌리기는 사용자가 `ddk rollback` 으로 실행)

## Task 3 — 샌드박스

- [x] 임시 복사본: `.git`, `.ddk`, 비밀 경로, 캐시, 안전하지 않은 심볼릭 링크 제외
- [x] 허용 명령 목록과 허용 환경 변수 목록, HOME 과 npm 캐시는 `.ddk-home` 안
- [x] 브라우저는 루프백만 허용, 의존성 설치는 `--ignore-scripts` (`--install`)

## Task 4 — 첫 실행

- [x] `ddk demo`: 녹화된 모델 응답을 재생하고 npm ci, 빌드, tsc, eslint, Chromium, 비교는 실제로 실행
- [x] 브라우저 탐지는 실제 실행으로 확인(`probe`), `ddk doctor --install-browser`, 데모의 내려받기 제안
- [x] `ddk run` 은 브라우저가 없으면 작업 폴더를 만들기 전에 실패

## Task 5 — 증거 보고서와 명령 구조

- [x] 판정 근거를 한 장으로 보여 주는 HTML 보고서와 `ddk report --open`
- [x] `src/ddk/cli.py` 를 `src/ddk/cli/` 패키지로 나누고 `python -m ddk` 지원
- [x] 영어/한국어 안내: 한국어 원문과 `ENGLISH` 대응표, 언어는 `DDK_LANG` 다음 로캘로 결정

## Task 6 — 문서

- [x] README 영어/한국어, 사용자 안내서 영어/한국어, 빠른 시작, CHANGELOG, 자동 수정 규칙서 §10,
      CONTRIBUTING, SECURITY
- [x] README 그림 4종을 실제 데모 실행에서 다시 만드는 `scripts/make_readme_assets.py`
- [x] 공개 준비서 `docs/launch/README.md` (채널별 초안과 점검표, 게시는 하지 않음)

## Task 7 — 배포 파일

- [x] CI: lint·type(`scripts/` 포함), test, package(휠 설치 후 CLI 시작), e2e(실제 npm·Chromium),
      security-audit
- [x] `release.yml`: 태그와 `pyproject.toml` 버전 일치 확인, 휠 검사 `scripts/check_wheel.py`,
      PyPI 신뢰 게시. PyPI 설정 전에는 동작하지 않음
- [x] 휠에 데모 프로젝트(`package-lock.json` 포함)와 슬래시 명령이 들어 있고 `node_modules` 는 없다

## 완료 조건

- 키 없이 `ddk demo` 가 첫 시안 불일치 → 수정 → `ready` 까지 보인다.
- 실제 브라우저를 사용하는 종단 테스트가 통과한다.
- 전체 자동 회귀, 엄격 타입 검사, 린트, 패키지 빌드, 의존성 감사가 통과한다.
- 실행하지 못한 검증(실제 Anthropic 응답, GitHub Actions 위의 새 작업)은 완료로 가장하지 않고 잔여 위험으로 적는다.
