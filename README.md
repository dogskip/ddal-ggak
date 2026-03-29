# 딸깍 (ddalggak / ddk)

> **스크린샷 + 프롬프트 → 검증된 코드** — self-correcting AI delivery pipeline

`ddk`는 레퍼런스 이미지와 자연어 프롬프트를 받아 repo에 맞는 코드를 생성하고,
sandbox에서 build → typecheck → lint → visual diff 검증 후 자동 수정, 최종 인증까지
**10-node LangGraph 파이프라인**으로 처리하는 CLI 도구입니다.

```
[스크린샷 / 이미지]
       +
[자연어 프롬프트]  ──▶  ddk run  ──▶  [검증된 코드 + EvidencePack + ReleaseDecision]
       +
[대상 repo 경로]
```

---

## 요구 사항

| 항목 | 최소 버전 |
|------|-----------|
| Python | 3.12 |
| uv | 최신 |
| git | 2.x |
| Anthropic API key | — |

---

## 설치

```bash
# uv (권장)
uv tool install ddalggak

# pip
pip install ddalggak
```

### 개발용

```bash
git clone https://github.com/bjchoi/ddalggak
cd ddalggak
uv sync
uv run ddk version
```

---

## 빠른 시작

```bash
# 1. 워크스페이스 초기화
ddk init

# 2. 환경 점검
ddk doctor
ddk preflight          # API 키 · Python · anthropic SDK 확인

# 3. 파이프라인 실행
ddk run \
  --image  path/to/reference.png \
  --prompt "로그인 폼 컴포넌트 만들어줘" \
  --repo   /path/to/my-repo

# 4. 결과 확인
ddk status  <case-id>
ddk certify <case-id>
```

---

## 설정

`.env.example`을 복사해 `.env`로 만들고 값을 채웁니다.

```bash
cp .env.example .env
```

| 환경 변수 | 필수 | 설명 | 기본값 |
|-----------|:----:|------|--------|
| `DDK_ANTHROPIC_API_KEY` | ✅ | Anthropic API 키 (`ANTHROPIC_API_KEY`도 인식) | — |
| `DDK_LLM_PROVIDER` | | `anthropic` \| `openai` \| `fake` | `anthropic` |
| `DDK_LLM_MODEL` | | 메인 Claude 모델 | `claude-3-5-sonnet-20241022` |
| `DDK_LIGHT_MODEL` | | 경량 Claude 모델 | `claude-3-haiku-20240307` |
| `DDK_COST_CAP_USD` | | 실행당 최대 비용 (USD) | `2.0` |
| `DDK_SANDBOX_MODE` | | 샌드박스 방식 | `worktree` |
| `DDK_PLAYWRIGHT_BROWSER` | | 스크린샷 브라우저 | `chromium` |
| `DDK_SSIM_THRESHOLD` | | 시각적 유사도 임계값 | `0.92` |
| `DDK_MAX_RETRY_ATTEMPTS` | | 자동 수정 최대 횟수 | `3` |
| `DDK_LOG_LEVEL` | | 로그 레벨 | `INFO` |

> **Tip:** `ANTHROPIC_API_KEY` (DDK_ 없이)도 fallback으로 인식됩니다.

---

## CLI 명령

| 명령 | 설명 |
|------|------|
| `ddk version` | 설치된 버전 출력 |
| `ddk init [path]` | `.ddk/` 워크스페이스 초기화 |
| `ddk doctor` | 환경 전체 진단 (Python / uv / API key / Node / git) |
| `ddk preflight` | 실행 전 필수 항목 점검 |
| `ddk run` | 파이프라인 전체 실행 |
| `ddk status <id>` | 케이스 상태 조회 |
| `ddk certify <id>` | 스코어카드 / 증거 팩 조회 |
| `ddk rollback <id>` | git 체크포인트 롤백 |
| `ddk design new <idea>` | 아이디어 → 10개 설계 문서 자동 생성 |
| `ddk serve` | MCP stdio 서버 실행 |
| `ddk install` | AI 도구 (Claude Desktop / Cursor) 등록 |

---

## 파이프라인 10-Node 구조

```
intake
  └─▶ intent_extract
        └─▶ design_system
              └─▶ plan
                    └─▶ repo_scan
                          └─▶ generate
                                └─▶ normalize
                                      └─▶ validate
                                            └─▶ autofix (retry loop)
                                                  └─▶ certify
```

각 노드 실패 시 `FailureClassifier`가 오류를 분류(FT-BUILD / FT-TYPE / FT-LINT / FT-RUNTIME / FT-VISUAL / FT-ASYNC)하고
`RollbackController`가 git 체크포인트로 복구합니다.

---

## 문서

- [사용자 가이드](docs/USER-GUIDE.md) — 설치, 설정, 전체 워크플로우 상세
- [빠른 시작](docs/QUICK-START.md) — GSD 비교 및 핵심 기능 요약
- [CHANGELOG](CHANGELOG.md) — 버전별 변경 사항

---

## 라이선스

MIT
