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

## Redaction 구현 명세

> 정책 선언만으로는 충분하지 않다. 아래 구현 명세를 따라야 secrets가 로그/artifact에 노출되지 않는다.

### 1. 마스킹 패턴 (Redaction Patterns)

```python
# src/ddk/security/redact.py

import re
from typing import Any

# 마스킹 대상 패턴 (우선순위 순)
REDACT_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("api_key",     re.compile(r"(sk-[a-zA-Z0-9]{20,})")),              # OpenAI
    ("api_key",     re.compile(r"(sk-ant-[a-zA-Z0-9\-]{20,})")),        # Anthropic
    ("api_key",     re.compile(r"(AIza[a-zA-Z0-9\-_]{35})")),           # Google
    ("bearer",      re.compile(r"(Bearer\s+[a-zA-Z0-9\-_.~+/]+=*)")),  # Bearer token
    ("env_secret",  re.compile(r"([A-Z_]{3,}_(?:KEY|TOKEN|SECRET|PASSWORD|PASS)=\S+)")),  # ENV=value
    ("private_key", re.compile(r"(-----BEGIN (?:RSA |EC )?PRIVATE KEY-----.*?-----END)", re.DOTALL)),
    ("jwt",         re.compile(r"(eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,})")),
]

REDACT_PLACEHOLDER = "[REDACTED]"

def redact_string(text: str) -> str:
    """문자열에서 민감 정보를 마스킹."""
    for _, pattern in REDACT_PATTERNS:
        text = pattern.sub(REDACT_PLACEHOLDER, text)
    return text

def redact_dict(obj: Any, depth: int = 0) -> Any:
    """dict/list/str 재귀 순회하며 마스킹. 최대 깊이 10."""
    if depth > 10:
        return obj
    if isinstance(obj, str):
        return redact_string(obj)
    if isinstance(obj, dict):
        return {k: redact_dict(v, depth + 1) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact_dict(item, depth + 1) for item in obj]
    return obj
```

### 2. Pydantic 모델 필드 어노테이션

민감 데이터를 포함하는 Pydantic 모델 필드는 `Field(exclude=True)` 또는 커스텀 직렬화를 사용한다.

```python
# src/ddk/models/config.py (DdalggakConfig 모델 내)

from pydantic import BaseModel, Field, field_serializer

class DdalggakConfig(BaseModel):
    # API 키는 직렬화 시 항상 마스킹
    anthropic_api_key: str | None = Field(default=None, exclude=True)
    openai_api_key: str | None = Field(default=None, exclude=True)
    
    @field_serializer("anthropic_api_key", "openai_api_key")
    def mask_api_key(self, value: str | None) -> str:
        if value is None:
            return None
        return f"{value[:6]}...{value[-4:]}" if len(value) > 10 else REDACT_PLACEHOLDER

class LLMCallRecord(BaseModel):
    # LLM 호출 기록에서 API 키 노출 방지
    provider: str
    model: str
    messages_hash: str      # 실제 메시지 대신 hash만 저장
    # messages: list[dict]  # 직접 저장 금지 — context_pack_hash로 대체
    input_tokens: int
    output_tokens: int
    cost_usd: float
```

### 3. 로그 출력 필터

```python
# src/ddk/logging/setup.py

import logging
import json
from ddk.security.redact import redact_string, redact_dict

class RedactingFormatter(logging.Formatter):
    """로그 출력에서 민감 정보를 자동 마스킹하는 포매터."""

    def format(self, record: logging.LogRecord) -> str:
        # 메시지 마스킹
        record.msg = redact_string(str(record.msg))
        if record.args:
            record.args = redact_dict(record.args)
        return super().format(record)


class StructuredJSONFormatter(logging.Formatter):
    """
    구조화된 JSON 로그 출력 포매터.
    
    출력 예시:
    {"timestamp": "2025-07-22T10:00:00Z", "level": "INFO", "node": "ingest", 
     "case_id": "case-001", "event": "context_pack_built", "file_count": 6}
    """

    REQUIRED_FIELDS = ["timestamp", "level", "node", "case_id", "event"]

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_string(record.getMessage()),
        }
        # 구조화 필드 병합 (record.extra로 전달된 필드)
        if hasattr(record, "extra"):
            log_data.update(redact_dict(record.extra))
        return json.dumps(log_data, ensure_ascii=False)


def setup_logging(level: str = "INFO", json_output: bool = False) -> None:
    """딸깍 로깅 초기화. json_output=True 시 JSON 포맷 사용."""
    handler = logging.StreamHandler()
    if json_output:
        handler.setFormatter(StructuredJSONFormatter())
    else:
        handler.setFormatter(RedactingFormatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        ))
    logging.getLogger("ddk").setLevel(level)
    logging.getLogger("ddk").addHandler(handler)
```

### 4. Evidence Pack Redaction

evidence pack을 저장하기 전에 `redact_dict()`를 통과시켜야 한다.

```python
# src/ddk/services/certify.py (evidence pack 저장 시)

async def save_evidence_pack(evidence: EvidencePack, output_dir: Path) -> None:
    """Evidence pack을 redact 후 저장."""
    from ddk.security.redact import redact_dict
    
    redacted = redact_dict(evidence.model_dump())
    output_path = output_dir / "evidence-pack.json"
    output_path.write_text(
        json.dumps(redacted, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
```

### 5. Auto-fix Failure Context Redaction

`auto_fix_node`가 이전 실패 context를 LLM에 주입할 때 반드시 redact해야 한다.

```python
# src/ddk/nodes/auto_fix.py

from ddk.security.redact import redact_string

async def auto_fix_node(state: GraphState) -> dict:
    ...
    # 실패 context를 LLM에 주입 전 반드시 redact
    failure_summary = redact_string(
        _summarize_failures(state["runtime_validation_report"])
    )
    ...
```

### 6. Forbidden Paths 검사 (15-sandbox-design.md 연동)

sandbox `_build_env()`의 ENV_WHITELIST가 API 키를 실행 환경에서 차단하는 것과 별개로,
context pack 빌더도 `FORBIDDEN_READ_PATHS`를 적용해야 한다.

```python
# 이미 15-sandbox-design.md에 정의된 FORBIDDEN_READ_PATHS
FORBIDDEN_READ_PATHS = [
    "**/.env*",
    "**/*.pem",
    "**/*.key",
    "**/secrets/**",
    "**/.git/config",
    "**/node_modules/**",
]
# context_pack_builder.py에서도 동일하게 적용
```

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
