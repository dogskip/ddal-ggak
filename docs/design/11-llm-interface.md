# LLM Provider 결정 및 어댑터 인터페이스

> **Current implementation (2026-10-14):** Anthropic만 실행 지원한다.
> OpenAI adapter와 provider fallback chain은 아래의 확장 설계이며 아직 구현되지 않았다.

## ADR-020 — Primary LLM Provider: Anthropic Claude

### 결정

- **Primary:** `claude-sonnet-5-5` (Anthropic)
- **Fallback:** 미구현 확장점(OpenAI 설정 enum만 예약)
- **경량:** `claude-haiku-5-5` (비용 민감 단순 작업)

Claude 5 계열은 기본값이 아닌 `temperature`·`top_p`·`top_k`를 받지 않고, 일부 모델은
`tool_choice`로 도구 호출을 강제하는 요청도 거절한다. 어댑터가 모델별 규칙을 알고 요청을
조정하므로(아래 "모델별 요청 규칙") 최신 세대를 기본값으로 둔다. 이전 세대
(`claude-sonnet-4-6`, `claude-haiku-4-5-20251001` 등)도 같은 환경변수로 지정할 수 있다.

### 근거

| 기준 | Anthropic Claude | OpenAI GPT-4o |
|------|-----------------|---------------|
| Vision (이미지→JSON) | ✅ 우수 | ✅ 우수 |
| 긴 코드 생성 | ✅ 200K context | ✅ 128K context |
| 한국어 품질 | ✅ 우수 | ✅ 우수 |
| JSON 출력 강제 | ✅ `tool_use` 방식 | ✅ `response_format` |
| 가격/성능 | ✅ Sonnet 가성비 | 비슷 |
| SDK Python | ✅ `anthropic>=0.120` | 미설치/미구현 |

### 환경변수

```bash
DDK_LLM_PROVIDER=anthropic          # 현재 anthropic만 실행 지원
DDK_ANTHROPIC_API_KEY=sk-ant-...
DDK_LLM_MODEL=claude-sonnet-5-5
DDK_LIGHT_MODEL=claude-haiku-5-5
DDK_COST_CAP_USD=2.0                # per-case cost cap
```

---

## 모델 라우팅 정책

| LangGraph 노드 | 모델 | 이유 |
|----------------|------|------|
| `intent_extract` | `claude-sonnet-5-5` | vision + JSON 출력, 정확도 우선 |
| `repo_scan` | `claude-haiku-5-5` | 단순 패턴 분석, 비용 절감 |
| `generate` | `claude-sonnet-5-5` | 긴 코드 생성, 품질 우선 |
| `normalize` | `claude-haiku-5-5` | diff 적용, 단순 규칙 |
| `auto_fix` R-01~R-08 | LLM 없음 | 결정론적 규칙 |
| `auto_fix` R-09 | `claude-haiku-5-5` | 제한된 파일 재생성 |
| `design` (design studio) | `claude-sonnet-5-5` | 문서 생성 품질 우선 |

---

## 모델별 요청 규칙

규칙과 단가는 `src/ddk/adapters/llm/model_traits.py` 한 곳에 있다(공식 문서 2026-10-14 기준).
표에 없는 모델에는 모든 모델이 받는 설정만 보내고, 가장 비싼 단가로 비용을 계산한다.

| 항목 | Claude 5 계열 | 이전 세대 (`sonnet-4-6`, `haiku-4-5` 등) |
|------|---------------|------------------------------------------|
| `temperature` | 보내지 않는다. 기본값이 아닌 값은 400 오류 | `LLMCallConfig.temperature` 전달 (Opus 4.7·4.8은 제외) |
| 구조화 출력 | `fable-5-1`·`opus-5-5`·`sonnet-5-5`는 도구 호출 강제를 거절한다. `tool_choice: auto`에 호출 지시문을 붙이고, 도구 대신 JSON 본문으로 답해도 받아들인다. `haiku-5-5`는 강제 가능 | 도구 호출 강제 |
| `effort` | `LLMCallConfig.effort`가 있으면 `output_config.effort`로 전달 | 지원 모델(`sonnet-4-6`, `opus-4-5` 이상)만 전달, 나머지는 생략 |
| `max_tokens` | 생각(thinking)에 쓴 토큰도 포함되므로 답변 크기에 여유분을 더한다. `low` 2,048 · `medium` 8,192 · `high` 16,384 · `xhigh` 32,768 · `max` 65,536 (상한 128,000) | 요청한 값 그대로 |
| 응답 읽기 | `text` 블록만 이어 붙인다. 생각 블록은 건너뛴다 | 동일 |
| 종료 사유 | `refusal`은 오류. `max_tokens`·`model_context_window_exceeded`는 잘림으로 표시하고, 구조화 출력이 잘리면 오류 | 동일 |
| 호출 방식 | 스트리밍으로 받는다. 긴 답변이 읽기 제한 시간에 걸리지 않는다 | 동일 |
| 단가 | `haiku-5-5`는 프롬프트가 100,000 토큰을 넘으면 입력 0.50 · 출력 2.50 달러(100만 토큰당)로 오른다 | 고정 |

`LLMCallRecord.temperature`는 요청한 값이며 Claude 5 계열에는 전달되지 않는다. 같은 입력의
재생은 `RecordingLLMAdapter`/`ReplayLLMAdapter`의 녹화본으로 보장한다
([18-reproducibility.md](18-reproducibility.md)).

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
    temperature: float = 0.0  # 샘플링 설정을 받지 않는 모델에서는 무시된다
    max_tokens: int = 4096  # 답변 크기. 생각하는 모델에는 여유분이 더해진다
    seed: int | None = None
    schema_version: str = "1.0"
    effort: Literal["low", "medium", "high", "xhigh", "max"] | None = None  # None: 모델 기본값


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
        # tool_use 방식으로 JSON 출력 유도. schema는 output_schema.model_json_schema()
        traits = model_traits(config.model)  # model_traits.py: 모델별 요청 규칙·단가
        request = {
            "model": config.model,
            "max_tokens": output_budget(config.model, config.max_tokens, config.effort),
            "messages": self._convert_messages(messages),
            "tools": [{"name": output_schema.__name__, "input_schema": schema}],
        }
        if traits.sampling:  # Claude 5 계열은 temperature를 받지 않는다
            request["temperature"] = config.temperature
        if traits.effort and config.effort:
            request["output_config"] = {"effort": config.effort}
        if traits.forced_tool:
            request["tool_choice"] = {"type": "tool", "name": output_schema.__name__}
        else:  # 강제를 거절하는 모델: auto + "이 도구를 호출하라"는 지시문을 system에 덧붙인다
            request["tool_choice"] = {"type": "auto"}
        # 스트리밍으로 끝까지 받은 뒤 tool_use 블록을 읽고, 없으면 본문 JSON을 읽고,
        # 둘 다 없거나 중간에 잘렸으면 LLMResponseError
        ...

    @staticmethod
    def _encode_image(image_path: Path) -> ImageContent:
        data = base64.standard_b64encode(image_path.read_bytes()).decode()
        suffix_to_media = {".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp"}
        media_type = suffix_to_media.get(image_path.suffix.lower(), "image/png")
        return ImageContent(data=data, media_type=media_type)
```

---

## OpenAI Adapter 확장 계약 (미구현)

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

# 단가(USD / 100만 토큰, 입력 / 출력)는 model_traits.py의 estimate_cost()가 계산한다.
#   claude-fable-5-1    10 / 50
#   claude-opus-5-5      4 / 20
#   claude-sonnet-5-5    2 / 10
#   claude-haiku-5-5     0.10 / 0.50   (프롬프트 100,000 토큰 초과 시 0.50 / 2.50)
#   claude-sonnet-4-6    3 / 15        claude-haiku-4-5  1 / 5
# 목록에 없는 모델은 가장 비싼 단가(10 / 50)로 계산한다. 상한이 과소 집계되면 안 되기 때문이다.

class CostTracker:
    def __init__(self, cap_usd: float):
        self._cap_usd = cap_usd
        self._total_usd = 0.0

    def record(self, model: str, input_tokens: int, output_tokens: int) -> float:
        cost = estimate_cost(model, input_tokens, output_tokens)
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

### Provider Fallback 전략 (미구현)

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

### 목표 적용 규칙 (현재 미구현)

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
