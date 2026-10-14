# Phase 07 Validation

status: verified_with_explicit_residual_risk

검증 시각: 2026-10-14 (Asia/Seoul), macOS arm64, Python 3.12, Node.js 설치됨, 헤드리스 Chromium(Playwright)

## 자동 회귀

- `pytest tests -m "not playwright"`: `1611 passed, 7 deselected`, 문장 범위 포함 `93%`
  (`6142` 문장 중 `414` 미실행). 의존성 올림 뒤에도 같은 결과.
- `DDK_E2E=1 pytest tests -m playwright`: `7 passed, 1611 deselected`. 실제 `npm ci`, 빌드, Chromium,
  스크린샷 비교를 거치는 종단 테스트 2건(`tests/e2e/test_demo.py`, `tests/e2e/test_visual_loop.py`)과
  브라우저 통합 테스트를 포함한다.
- `pyright`(엄격, `src`): 오류 `0`.
- `ruff check src tests scripts`: `All checks passed!`. `ruff format --check`: `300 files already formatted`.

## 배포 가능성

- `uv build`: sdist 와 wheel 생성 성공.
- `python scripts/check_wheel.py <wheel>`: `ok` (데모 프로젝트와 `package-lock.json`, 슬래시 명령,
  `__main__.py` 포함. `node_modules`, `__pycache__`, `.ddk` 없음).
- 방금 만든 wheel 을 깨끗한 가상환경(올린 의존성 포함)에 설치하고 빈 폴더에서 `ddk demo` 를 끝까지 실행:
  21.8초, 첫 시안 SSIM 0.89(6.3% 크게 다름) → 자동 수정 1회(R-10) → SSIM 1.00, 판정 `ready`(점수 0.96).
- `uv lock --check`: `Resolved 106 packages`.

## 의존성 감사

- `pip-audit --ignore-vuln CVE-2026-4539` 을 처음 실행하자 6개 패키지에서 알려진 취약점 41건이 나왔다:
  cryptography 49.0.0, gitpython 3.1.57, langgraph-sdk 0.4.2, pip 26.1.2, pyjwt 2.13.0, urllib3 2.7.0.
- `uv lock --upgrade-package` 로 cryptography 50.0.2, gitpython 3.2.0, langgraph-sdk 0.4.7,
  pip 26.2.1, pyjwt 2.15.1, urllib3 2.8.0 으로 올렸고 `pyproject.toml` 의 GitPython 하한을 `3.1.60` 으로 높였다.
- 같은 감사를 다시 실행: `No known vulnerabilities found` (지역 패키지 `ddalggak` 만 PyPI 에 없어서 제외).
- 올린 뒤 위의 자동 회귀 전체를 다시 실행해 통과를 확인했다.

## 잔여 위험

- 실제 Anthropic 응답으로 `ddk run` 을 실행해 본 적이 없다. 데모는 녹화된 응답을 재생하고, 모델 요청 형식의
  실제 동작과 비용은 확인하지 못했다.
- GitHub Actions 위에서 `package`, `e2e`, `release` 작업을 실행하지 못했다. 같은 명령을 로컬에서 실행했고 YAML
  구문만 확인했다. `release.yml` 은 PyPI 신뢰 게시자와 `pypi` 환경을 설정하기 전에는 동작하지 않는다.
- 수정 회차마다 git 점검점이 만들어지지만, 실패했을 때 자동으로 되돌리는 동작은 없다(사용자가 `ddk rollback`
  실행). 샌드박스는 임시 복사본이며 git worktree 도 OS 수준 격리도 아니다.
- 시각 판정은 회색조 블록 SSIM 이라 밝기가 같은 색 변화는 통과할 수 있고, 기준값 0.92 는 보정하지 않았다.
  미리보기 서버는 Vite, Next.js, Astro 만 지원한다.
- MCP 서버는 Design Studio(`design_new`, `preflight`, `ddk_version`)만 제공하고 이미지에서 코드까지의
  절차는 노출하지 않는다.
- macOS(arm64)에서만 실행했다. Windows 와 Linux 는 확인하지 못했다.
- Phase 06 에서 이월한 위험(EvidencePack 의 완전한 재생, 비교 benchmark 보정, 행동 증거 `P-0`)은 그대로다.
- `LICENSE` 의 저작권자(`bjchoi`)는 가정이다.
- 이 검증은 Phase 07 완료 증거이지 제품 전체의 인증이 아니며, 스타 수는 코드가 아니라 배포(노출)에 달려 있다.
