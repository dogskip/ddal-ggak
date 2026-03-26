# Security / Privacy 거버넌스

> **Purpose:** 데이터 분류, 보존, 삭제, 접근 통제 정책을 정의  
> **Authority:** Tier 0 — 이 문서는 identity/strategy/governance 수준의 전략 문서로, 하위 Tier와 충돌 시 이 문서가 우선한다.  
> **Status:** proposed  
> **Inputs:** 02-prd.md, 15-sandbox-design.md  
> **Outputs:** 06-tech-spec.md, 21-ci-workflow.md  
> **Supersedes:** 없음 (신규)  
> **Stale Trigger:** 데이터 분류 체계 변경, 규제 환경 변경 시  

## 목적

본 문서는 `딸깍`이 다루는 prompt, screenshot, repo, secrets, artifacts, benchmark data의 보안/프라이버시 정책을 정의한다.

## 데이터 분류

| 자산 | 예시 | 분류 | 기본 정책 |
| --- | --- | --- | --- |
| User Idea / Prompt | 기능 아이디어, 요구사항 | Internal / Confidential | 로그 최소화, 필요 범위만 LLM 전송 |
| Screenshot / Mockup | UI 이미지, reference | Internal / Confidential | 목적 외 보존 금지, share 범위 제한 |
| Repository Contents | source code, config | Confidential / Restricted | context pack 최소화, forbidden path 차단 |
| Secrets | `.env`, API keys, tokens | Restricted | LLM 전송 금지, log redaction 필수 |
| Generated Artifacts | reports, screenshots, diff, traces | Internal / Confidential | retention 정책 적용 |
| Benchmark Data | scorecards, baseline | Internal | freshness metadata와 접근 통제 |

## 핵심 정책

1. **Secret Non-Disclosure**
   - secrets, private keys, auth tokens는 LLM/provider로 전송하지 않는다.

2. **Context Minimization**
   - repo 전체를 보내지 않고 context pack 정책에 따라 최소 범위만 전송한다.

3. **Redaction by Default**
   - logs, evidence pack, failure report에서 secrets와 민감경로를 기본 마스킹한다.

4. **Sandbox-only Execution**
   - generated code execution은 sandbox/worktree 안에서만 수행한다.

5. **Provider Traceability**
   - 어떤 provider/model/prompt version이 사용됐는지 artifact로 남긴다.

## 보존(Retention) 정책

- 일반 case artifact: 기본 보존, 정책에 따라 삭제 가능
- benchmark artifact: freshness 판단용 메타데이터와 함께 장기 보존
- secrets: artifact 보존 금지
- screenshot/reference: 목적 달성 후 최소 보존 원칙 적용

## 접근 통제(Access Control)

- architect / verifier / release authority만 full evidence pack 열람 가능
- secrets 관련 정보는 security reviewer 승인 없이는 열람 불가
- benchmark baseline 수정은 proof owner 승인 필요

## Provider 사용 정책

- third-party provider 사용 시 prompt/code 전송 범위를 명확히 한다.
- BYOK(Bring Your Own Key) 모드를 우선 지원한다.
- enterprise/on-prem 요구가 있으면 hosted claim과 분리해 다룬다.

## Release-blocking Security Conditions

아래 중 하나라도 발생하면 blocked.

- unredacted secret in logs detected
- forbidden path read/write detected
- sandbox bypass detected
- unsupported provider / retention policy violation
- evidence pack에 restricted data가 평문으로 남음

## 관련 문서

- sandbox 정책: `15-sandbox-design.md`
- reproducibility / provider metadata: `18-reproducibility.md`
- release blocking conditions: `07-verification-release.md`
- operator / review authority: `32-human-operator-model.md`

## 결론

`딸깍`의 security/privacy는 runtime sandbox만의 문제가 아니다.
prompt, screenshot, repo, artifact 전체 수명주기를 다루는 거버넌스 문제다.
