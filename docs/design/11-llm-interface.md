# LLM Provider 결정 및 어댑터 인터페이스

## ADR-020 — Primary LLM Provider: Anthropic Claude

### 결정

- **Primary:** `claude-3-5-sonnet-20241022` (Anthropic)
- **Fallback:** `gpt-4o-2024-11-20` (OpenAI)
- **경량:** `claude-3-haiku-20240307` (비용 민감 단순 작업)

### 근거

| 기준 | Anthropic Claude | OpenAI GPT-4o |
|------|-----------------|---------------|
| Vision (이미지→JSON) | ✅ 우수 | ✅ 우수 |
| 긴 코드 생성 | ✅ 200K context | ✅ 128K context |
| 한국어 품질 | ✅ 우수 | ✅ 우수 |
| JSON 출력 강제 | ✅ `tool_use` 방식 | ✅ `response_format` |
| 가격/성능 | ✅ Sonnet 가성비 | 비슷 |
| SDK Python | ✅ `anthropic>=0.40` | ✅ `openai>=1.40` |

### 환경변수

```bash
DDK_LLM_PROVIDER=anthropic          # anthropic | openai (default: anthropic)
DDK_ANTHROPIC_API_KEY=sk-ant-...
DDK_OPENAI_API_KEY=sk-...           # fallback용
DDK_LLM_DEFAULT_MODEL=claude-3-5-sonnet-20241022
DDK_LLM_CHEAP_MODEL=claude-3-haiku-20240307
DDK_LLM_TEMPERATURE=0.0             # default: 0.0 (deterministic 우선)
DDK_LLM_MAX_TOKENS=4096             # per-call cap
DDK_LLM_COST_CAP_USD=2.0           # per-case cost cap
```

---

## 모델 라우팅 정책

| LangGraph 노드 | 모델 | 이유 |
|----------------|------|------|
| `intent_extract` | `claude-3-5-sonnet` | vision + JSON 출력, 정확도 우선 |
| `repo_scan` | `claude-3-haiku` | 단순 패턴 분석, 비용 절감 |
| `generate` | `claude-3-5-sonnet` | 긴 코드 생성, 품질 우선 |
| `normalize` | `claude-3-haiku` | diff 적용, 단순 규칙 |
| `auto_fix` attempt 1 | `claude-3-5-sonnet` | 창의적 수정 필요 |
| `auto_fix` attempt 2 | `claude-3-5-sonnet` | 동일 |
| `auto_fix` attempt 3 | `claude-3-5-sonnet` | 동일 |
| `design` (design studio) | `claude-3-5-sonnet` | 문서 생성 품질 우선 |

---

## LLM Adapter Interface Contract

```python
# src/ddk/adapters/llm/base.py

from __future__ import annotations
from typing import Protocol, Any
from dataclasses import dataclass
from enum import Enum


class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass
class ImageContent:
    """이미지 첨부 (base64 인코딩)"""
    data: str           # base64 encoded
    media_type: str     # "image/png" | "image/jpeg" | "image/webp"


@dataclass
class Message:
    role: MessageRole
    content: str
    images: list[ImageContent] | None = None  # vision 지원


@dataclass
class LLMResponse:
    content: str
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    cost_usd: float | None
    raw: dict[str, Any]  # provider-specific raw response


@dataclass
class LLMCallConfig:
    model: str
    temperature: float = 0.0
    max_tokens: int = 4096
    seed: int | None = None
    schema_version: str = "1.0"


class LLMAdapter(Protocol):
    """모든 LLM provider adapter가 구현해야 하는 Protocol."""

    async def complete(
        self,
        messages: list[Message],
        config: LLMCallConfig,
    ) -> LLMResponse:
        """텍스트 completion."""
        ...

    async def complete_structured(
        self,
        messages: list[Message],
        config: LLMCallConfig,
        output_schema: type,  # Pydantic model class
    ) -> LLMResponse:
        """Pydantic 모델로 구조화된 출력 강제.
        Anthropic: tool_use 방식
        OpenAI: response_format + json_schema 방식
        """
        ...
```

---

## Anthropic Adapter 구현 계약

```python
# src/ddk/adapters/llm/anthropic.py

import anthropic
import base64
from pathlib import Path

class AnthropicAdapter:
    def __init__(self, api_key: str, default_model: str):
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._default_model = default_model

    async def complete_structured(
        self,
        messages: list[Message],
        config: LLMCallConfig,
        output_schema: type,
    ) -> LLMResponse:
        # tool_use 방식으로 JSON 출력 강제
        # schema는 output_schema.model_json_schema()로 변환
        tools = [{
            "name": "structured_output",
            "description": "Output structured data",
            "input_schema": output_schema.model_json_schema(),
        }]
        response = await self._client.messages.create(
            model=config.model,
            max_tokens=config.max_tokens,
            temperature=config.temperature,
            messages=self._convert_messages(messages),
            tools=tools,
            tool_choice={"type": "tool", "name": "structured_output"},
        )
        # tool_use content block 파싱
        ...

    @staticmethod
    def _encode_image(image_path: Path) -> ImageContent:
        data = base64.standard_b64encode(image_path.read_bytes()).decode()
        suffix_to_media = {".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp"}
        media_type = suffix_to_media.get(image_path.suffix.lower(), "image/png")
        return ImageContent(data=data, media_type=media_type)
```

---

## OpenAI Adapter 구현 계약

```python
# src/ddk/adapters/llm/openai.py

import openai

class OpenAIAdapter:
    def __init__(self, api_key: str, default_model: str):
        self._client = openai.AsyncOpenAI(api_key=api_key)
        self._default_model = default_model

    async def complete_structured(
        self,
        messages: list[Message],
        config: LLMCallConfig,
        output_schema: type,
    ) -> LLMResponse:
        # response_format + json_schema 방식
        response = await self._client.beta.chat.completions.parse(
            model=config.model,
            messages=self._convert_messages(messages),
            response_format=output_schema,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
        )
        ...
```

---

## LLMCallRecorder

모든 LLM 호출은 `LLMCallRecorder`를 통해 자동 기록된다.

```python
# src/ddk/adapters/llm/recorder.py

import hashlib
import json
from datetime import datetime, timezone
from ddk.models.llm import LLMCallRecord


class LLMCallRecorder:
    """LLM 호출 wrapper — artifact 자동 저장."""

    def __init__(self, adapter: LLMAdapter, workspace_dir: Path):
        self._adapter = adapter
        self._workspace_dir = workspace_dir

    def _compute_context_pack_hash(self, messages: list[Message]) -> str:
        content = json.dumps([
            {"role": m.role, "content": m.content}
            for m in messages
        ], sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    async def complete_structured(
        self,
        node_name: str,
        messages: list[Message],
        config: LLMCallConfig,
        output_schema: type,
    ) -> tuple[LLMResponse, LLMCallRecord]:
        start = datetime.now(timezone.utc)
        response = await self._adapter.complete_structured(messages, config, output_schema)
        record = LLMCallRecord(
            call_id=f"{node_name}-{start.strftime('%Y%m%d%H%M%S%f')}",
            node_name=node_name,
            model=response.model,
            provider=response.provider,
            temperature=config.temperature,
            seed=config.seed,
            schema_version=config.schema_version,
            context_pack_hash=self._compute_context_pack_hash(messages),
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            cost_usd=response.cost_usd,
            duration_seconds=(datetime.now(timezone.utc) - start).total_seconds(),
            called_at=start,
        )
        # workspace에 저장
        self._save_record(record)
        return response, record
```

---

## 비용 추적 및 Cap 정책

```python
# src/ddk/adapters/llm/cost_tracker.py

COST_PER_1K_INPUT_TOKENS = {
    "claude-3-5-sonnet-20241022": 0.003,
    "claude-3-haiku-20240307": 0.00025,
    "gpt-4o-2024-11-20": 0.0025,
}
COST_PER_1K_OUTPUT_TOKENS = {
    "claude-3-5-sonnet-20241022": 0.015,
    "claude-3-haiku-20240307": 0.00125,
    "gpt-4o-2024-11-20": 0.01,
}

class CostTracker:
    def __init__(self, cap_usd: float):
        self._cap_usd = cap_usd
        self._total_usd = 0.0

    def record(self, model: str, input_tokens: int, output_tokens: int) -> float:
        cost = (
            COST_PER_1K_INPUT_TOKENS.get(model, 0.003) * input_tokens / 1000
            + COST_PER_1K_OUTPUT_TOKENS.get(model, 0.015) * output_tokens / 1000
        )
        self._total_usd += cost
        if self._total_usd > self._cap_usd:
            raise CostCapExceededError(
                f"케이스 비용 상한 초과: ${self._total_usd:.4f} > ${self._cap_usd}"
            )
        return cost

    @property
    def total_usd(self) -> float:
        return self._total_usd
```

---

## LLM 호출 실패 복구 정책 (Failure Recovery Policy)

### 실패 분류

| 실패 유형 | HTTP Status / Error | 재시도 가능 | 예시 |
| --- | --- | --- | --- |
| `RATE_LIMIT` | 429 | ✅ backoff 후 재시도 | API rate limit exceeded |
| `SERVER_ERROR` | 500, 502, 503 | ✅ backoff 후 재시도 | Provider internal error |
| `TIMEOUT` | timeout / 408 | ✅ 1회 재시도 | Response timeout |
| `AUTH_ERROR` | 401, 403 | ❌ 즉시 중단 | Invalid API key |
| `INVALID_REQUEST` | 400 | ❌ 즉시 중단 | Malformed request, context too long |
| `CONTENT_FILTER` | 400 (safety) | ❌ 즉시 중단 + escalation | Content policy violation |
| `NETWORK_ERROR` | ConnectionError | ✅ backoff 후 재시도 | DNS failure, connection reset |

### 재시도 정책

```python
# src/ddk/adapters/llm/retry.py

from dataclasses import dataclass, field

@dataclass(frozen=True)
class LLMRetryPolicy:
    """LLM 호출 재시도 정책. 모든 LLM 호출에 적용."""
    max_retries: int = 3
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True
    retryable_status_codes: frozenset[int] = field(
        default_factory=lambda: frozenset({429, 500, 502, 503, 408})
    )

    def delay_for_attempt(self, attempt: int) -> float:
        """Exponential backoff with optional jitter."""
        import random
        delay = min(
            self.base_delay_seconds * (self.exponential_base ** attempt),
            self.max_delay_seconds,
        )
        if self.jitter:
            delay *= 0.5 + random.random()  # 50-150% jitter
        return delay
```

### Provider Fallback 전략

```python
# src/ddk/adapters/llm/fallback.py

class LLMFallbackChain:
    """Primary provider 실패 시 fallback provider로 전환."""

    def __init__(
        self,
        primary: LLMAdapter,
        fallback: LLMAdapter | None,
        retry_policy: LLMRetryPolicy = LLMRetryPolicy(),
    ):
        self._primary = primary
        self._fallback = fallback
        self._retry_policy = retry_policy

    async def complete_structured(
        self,
        messages: list[Message],
        config: LLMCallConfig,
        output_schema: type,
    ) -> LLMResponse:
        try:
            return await self._call_with_retry(self._primary, messages, config, output_schema)
        except LLMProviderExhaustedError:
            if self._fallback is None:
                raise
            return await self._call_with_retry(self._fallback, messages, config, output_schema)

    async def _call_with_retry(
        self,
        adapter: LLMAdapter,
        messages: list[Message],
        config: LLMCallConfig,
        output_schema: type,
    ) -> LLMResponse:
        last_error: Exception | None = None
        for attempt in range(self._retry_policy.max_retries + 1):
            try:
                return await adapter.complete_structured(messages, config, output_schema)
            except LLMRetryableError as e:
                last_error = e
                if attempt < self._retry_policy.max_retries:
                    delay = self._retry_policy.delay_for_attempt(attempt)
                    await asyncio.sleep(delay)
                continue
            except LLMNonRetryableError:
                raise
        raise LLMProviderExhaustedError(
            f"All {self._retry_policy.max_retries + 1} attempts failed",
            last_error=last_error,
        )
```

### 에러 계층 구조

```python
# src/ddk/adapters/llm/errors.py

class LLMError(Exception):
    """LLM 호출 에러 베이스 클래스."""

class LLMRetryableError(LLMError):
    """재시도 가능한 에러 (rate limit, server error, timeout)."""
    status_code: int | None = None

class LLMNonRetryableError(LLMError):
    """재시도 불가 에러 (auth, invalid request, content filter)."""
    status_code: int | None = None

class LLMProviderExhaustedError(LLMError):
    """재시도 예산 소진 후 발생."""
    last_error: Exception | None = None

class LLMCostCapExceededError(LLMError):
    """비용 상한 초과."""

class LLMContentFilterError(LLMNonRetryableError):
    """콘텐츠 안전 정책 위반. human escalation 필요."""
```

### LLM 폴백 소진 시 케이스 상태 전이

`LLMProviderExhaustedError` 발생 시 시스템은 다음 절차를 따른다:

| 단계 | 동작 | 결과 |
|------|------|------|
| 1 | LangGraph 노드에서 `LLMProviderExhaustedError` 포착 | 예외 전파 중단 |
| 2 | `state["terminal_state"] = "blocked"` 설정 | 그래프 종료 |
| 3 | `state["blocked_reason"] = "llm_provider_exhausted"` 기록 | 원인 추적 |
| 4 | `RollbackController.restore_pre_run_checkpoint()` 호출 | 원본 보호 |
| 5 | CLI exit code `30` (BLOCKED) 반환 | 사용자 알림 |
| 6 | `EvidencePack`에 마지막 LLM 에러 로그 포함 | 사후 분석 |

이 전이는 `19-langgraph-builder.md`의 모든 LLM 호출 노드(`intent_extract`, `plan`, `generate`, `auto_fix`)에 공통 적용된다.

```python
# 노드 공통 LLM 호출 래퍼
async def safe_llm_call(state: GraphState, adapter: LLMAdapter, ...) -> dict:
    try:
        return await adapter.complete_structured(...)
    except LLMProviderExhaustedError as e:
        return {
            "terminal_state": "blocked",
            "blocked_reason": "llm_provider_exhausted",
            "error_detail": str(e),
        }
    except LLMContentFilterError as e:
        return {
            "terminal_state": "blocked",
            "blocked_reason": "content_filter",
            "error_detail": str(e),
        }
```

### 적용 규칙

1. **모든 LLM 호출**은 `LLMFallbackChain`을 통해 수행한다.
2. `LLMRetryableError`만 재시도한다. 나머지는 즉시 전파한다.
3. `LLMContentFilterError`는 case를 `blocked` 상태로 전환하고 human review를 요청한다.
4. `LLMCostCapExceededError`는 case를 `cost-exceeded` 상태로 전환한다.
5. Fallback provider 전환 시 동일 `LLMCallConfig`를 사용하되, model은 fallback 기본 모델로 교체한다.
6. 모든 실패는 `LLMCallRecord`에 `error_type`, `error_message`, `attempt_number`를 기록한다.

### 테스트 요구사항

- `test_retry_policy_exponential_backoff.py` — delay 계산 검증
- `test_fallback_chain_primary_success.py` — primary 성공 시 fallback 미호출
- `test_fallback_chain_primary_exhausted.py` — primary 소진 시 fallback 전환
- `test_non_retryable_error_propagation.py` — auth/content filter 즉시 전파
- `test_cost_cap_stops_execution.py` — 비용 초과 시 즉시 중단

---

## 이미지 인코딩 방식

- **형식:** base64 인코딩, data URL 없이 순수 base64 string
- **지원 형식:** PNG (권장), JPEG, WebP
- **크기 제한:** 5MB per image (Anthropic 제한), 자동 리사이즈 옵션 (`--resize-image`)
- **최대 이미지 수:** case당 5개

```python
# 이미지 전처리
def preprocess_image(path: Path, max_size_mb: float = 4.0) -> ImageContent:
    from PIL import Image
    import io
    img = Image.open(path)
    # 크기 초과 시 비율 유지하며 리사이즈
    buffer = io.BytesIO()
    img.save(buffer, format="PNG", optimize=True)
    if buffer.tell() > max_size_mb * 1024 * 1024:
        scale = (max_size_mb * 1024 * 1024 / buffer.tell()) ** 0.5
        new_size = (int(img.width * scale), int(img.height * scale))
        img = img.resize(new_size, Image.LANCZOS)
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
    data = base64.standard_b64encode(buffer.getvalue()).decode()
    return ImageContent(data=data, media_type="image/png")
```

---

## 추가 의존성 (pyproject.toml)

```toml
[project.dependencies]
anthropic = ">=0.40.0"
openai = ">=1.40.0"
mcp = ">=1.0.0"
pillow = ">=10.0.0"   # 이미지 전처리
```
