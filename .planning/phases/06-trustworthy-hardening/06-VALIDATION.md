# Phase 06 Validation

status: verified_with_explicit_residual_risk

## 1심 — 계약 테스트

- 경로 정규화/containment 및 symlink 탈출
- runtime/case artifact write boundary
- context pack secret/symlink exclusion
- model policy DI propagation
- proof/compliance false-positive denial

## 2심 — 전체 회귀

- `uv run --extra dev pytest -q -m 'not playwright'`
- `uv run --extra dev ruff check .`
- `uv run --extra dev pyright`

## 3심 — 배포/보안

- `uv build`
- `uv run --extra dev pip-audit`
- 임시 디렉터리 path-escape 반증 재실행
- `ddk proof --json`과 `ddk audit --json`의 과장 금지 결과 확인

## 실행 기록

검증 시각: 2026-07-27 (Asia/Seoul)

### 1심 결과 — 계약/반증

- 경로·symlink·write boundary focused suite: `64 passed`, exit `0`.
- 전체 non-Playwright suite + coverage: `936 passed, 2 deselected`, exit `0`.
- statement coverage: `90%` (`3670` statements, `366` missed).
- 이미지 입력에 visual report가 없으면 release blocker
  `missing-visual-evidence`가 생성되는 회귀 계약 포함.

### 2심 결과 — 정적 정합성

- `uv run --extra dev ruff check .`: `All checks passed!`, exit `0`.
- `uv run --extra dev pyright`: `0 errors, 0 warnings, 0 informations`, exit `0`.
- `uv lock --check`: `Resolved 106 packages`, exit `0`.
- current model/config DI와 Anthropic-only provider preflight 계약이 전체 회귀에 포함됨.
- 실제 runtime과 설정 기본값을 `tempdir`로 정렬하고 미구현 sandbox mode를 fail-fast 처리.

### 3심 결과 — 패키지/보안/과장 방지

- `uv build`: sdist와 wheel 생성 성공, exit `0`.
- `uv run --extra dev pip-audit`: 알려진 취약점 `0`; 로컬 패키지 자체만 PyPI 미등록으로
  감사 제외, exit `0`.
- `ddk proof --strict`: exit `1` (의도된 fail-closed). `14/14 mapped`,
  `0/14 behavior-proved`, maturity `P-0`; parity/superset/superiority 모두 거부.
- `ddk audit --strict`: exit `1` (의도된 fail-closed). `13/16 mapped`,
  `1 partial`, `2 gaps`, mapping coverage `81.25%`.
- Playwright marker suite: `1 passed, 1 skipped, 936 deselected`, exit `0`.
  Chromium binary 부재로 실제 browser integration 1건은 실행하지 못함.

## 잔여 위험

- 기본 runtime은 production browser adapter와 dev-server lifecycle을 연결하지 않는다.
- 현재 소스 커밋에 묶인 행동 receipt와 비교 benchmark calibration이 없어 우월성 주장은 금지된다.
- 실 Anthropic API 호출, 비용, rate-limit 동작은 외부 credential 없이 검증하지 않았다.
- EvidencePack은 완전 replay bundle이 아니고 operator ledger는 process-local이다.
- `TempDirSandbox`는 secret-bearing env와 외부 symlink를 차단하지만 OS 수준
  filesystem/network/resource isolation은 제공하지 않는다.
- 따라서 본 검증은 Phase 06 hardening 완료 증거이지 제품 전체의 “100/100” 인증이 아니다.
