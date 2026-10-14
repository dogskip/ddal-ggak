# 재현성(Reproducibility) 정책

> 딸깍의 LLM 호출 결과를 재현 가능하게 만드는 정책.
> 이 정책 없이는 benchmark gate가 매번 다른 결과를 낸다.

---

## 1. 재현성 문제 정의

### 왜 재현이 어려운가

딸깍의 파이프라인은 1단계(intent extraction)부터 확률적이다:
- `temperature=0`이어도 같은 이미지를 같은 프롬프트로 넣어도 LLM 응답이 미세하게 다를 수 있다.
- Claude 5 계열은 `temperature`·`top_p`·`top_k`를 받지 않는다. 어댑터가 이 값을 보내지 않으므로
  결정론은 설정이 아니라 녹화본(`RecordingLLMAdapter`/`ReplayLLMAdapter`)으로 확보한다.
- Anthropic/OpenAI API는 모델 버전이 조용히 업데이트되기도 한다.
- `seed` 파라미터가 있어도 100% 결정론적 보장은 없다.

### 재현성 목표

1. **벤치마크 재현성**: 같은 BM 케이스를 같은 날 두 번 실행했을 때 composite 점수 ±0.5 이내
2. **버그 재현성**: 실패한 케이스를 artifact만으로 재실행 가능
3. **감사 가능성**: 언제, 어떤 모델, 어떤 프롬프트 버전으로 실행했는지 추적 가능

---

## 2. 재현성 제어 파라미터

### LLM 호출 설정

```python
# src/ddk/adapters/llm/base.py

class LLMCallConfig(DDKBaseModel):
    model: str
    temperature: float = 0.0      # 결정론적 출력 최대화
    seed: int | None = None       # None = 비결정론
    max_tokens: int = 4096
    schema_version: str           # 프롬프트 버전
    top_p: float | None = None    # temperature=0이면 불필요
```

### 재현 모드

```python
# .ddk/config.json에 설정

{
  "reproducibility": {
    "mode": "best_effort",  # "best_effort" | "strict" | "disabled"
    "default_seed": null,   # null = random, 정수 = fixed
    "benchmark_seed": 42,   # 벤치마크 실행 시 고정 seed
    "record_all_calls": true
  }
}
```

| 모드 | 동작 | 사용 시점 |
|------|------|---------|
| `best_effort` | temperature=0, provider-seed 있으면 사용 | 기본값 |
| `strict` | seed=benchmark_seed, 모델 버전 고정 | 벤치마크 실행 |
| `disabled` | 제약 없음 | 실험적 실행 |

---

## 3. 재현을 위한 Artifact 저장

모든 LLM 호출은 `LLMCallRecord`에 다음 정보를 저장한다:

```python
class LLMCallRecord(DDKBaseModel):
    call_id: str
    node_name: str
    model: str                     # "claude-sonnet-5-5" (정확한 모델 ID 포함)
    provider: str                  # "anthropic" | "openai"
    temperature: float             # 실제 사용된 값
    seed: int | None               # 실제 사용된 seed
    context_pack_hash: str         # 입력 컨텍스트의 SHA256
    # ...
```

`context_pack_hash`는 다음을 포함한 해시:
- system prompt 내용
- user message 내용
- image 내용(있을 경우)
- schema_version

즉, **같은 hash == 완전히 같은 입력**이다.

### Context Pack 직렬화 + 해시

```python
import hashlib, json

def compute_context_pack_hash(
    system_prompt: str,
    messages: list[dict],
    schema_version: str,
) -> str:
    payload = json.dumps({
        "system": system_prompt,
        "messages": messages,
        "schema_version": schema_version,
    }, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]
```

---

## 4. Replay 기능

```
ddk replay --case-id C-001 --node intent_extract
```

동작:
1. `.ddk/cases/C-001/llm-calls/` 에서 해당 노드의 `LLMCallRecord` 읽기
2. `context_pack_hash`로 원래 입력 복원 (가능 시)
3. 같은 `model`, `temperature`, `seed`로 LLM 재호출
4. 결과를 새 artifact로 저장 (`replay-{timestamp}`)

**한계**: LLM API가 모델을 업데이트했다면 같은 seed로도 다른 결과가 나올 수 있다. 이것은 설계로 완전히 막을 수 없으며, `LLMCallRecord.model`에 정확한 버전이 저장되어 있을 때 문제를 진단할 수 있다.

---

## 5. 벤치마크 재현성 보장 절차

```bash
# 동일 환경에서 두 번 실행했을 때 결과 비교

# 실행 1
ddk run --case-id BM-001 --seed 42

# 실행 2 (같은 날 같은 환경)
ddk run --case-id BM-001-v2 --seed 42

# 비교
python scripts/compare_runs.py BM-001 BM-001-v2
# 기대: composite 점수 차이 < 0.5
```

### 허용 편차 기준

| 항목 | 허용 편차 | 초과 시 조치 |
|------|---------|------------|
| composite score | ± 0.5 | model 버전 변경 확인 |
| SSIM | ± 0.03 | Playwright 렌더링 환경 확인 |
| build/type/lint pass/fail | 100% 일치 | 결정론적 게이트이므로 반드시 동일 |

---

## 6. Artifact 보존 정책

`.ddk/cases/{case_id}/` 하위 모든 artifact는 삭제하지 않는다:
- `ddk clean --case-id C-001`으로만 명시적 삭제 가능
- 기본 보존 기간: 30일 (설정 변경 가능)
- 벤치마크 케이스 (BM-*)는 영구 보존 (gitignore에서 제외)

```
.gitignore 예시:
.ddk/cases/C-*/          # 일반 케이스는 git에서 제외
!.ddk/cases/BM-*/         # 벤치마크 케이스는 포함
benchmarks/gsd-baseline.json  # 실측 baseline은 포함
benchmarks/ddk-results.json   # 딸깍 실측 결과도 포함
```

---

## 7. Provider / Prompt Compatibility Policy

재현성은 "같은 seed" 하나로 끝나지 않는다.
아래 compatibility class를 기준으로 replay 의미를 구분한다.

| Class | 조건 | 의미 | benchmark 상태 |
|---|---|---|---|
| `strict` | same provider + same provider_model_id + same prompt_version | 사실상 동일 입력/동일 실행 | 유지 |
| `weak` | same provider family, 하지만 exact model revision 또는 prompt minor 다름 | 진단용 비교만 가능 | provisional 재측정 필요 |
| `non-equivalent` | provider 변경 또는 prompt major 변경 | replay-equivalent 아님 | stale, full rerun 필요 |

### 7.1 LLMCallRecord 필수 메타데이터

모든 LLM 호출은 최소 아래를 기록한다.

- `provider_model_id`
- `prompt_version`
- `replay_compatibility`

### 7.2 운영 규칙

- `strict` replay만 benchmark reproducibility 증거로 사용 가능
- `weak` replay는 debugging reference로만 사용
- `non-equivalent` 상태에서는 이전 benchmark artifact를 comparative gate에 재사용할 수 없다

> prompt version change governance: `16-prompt-design.md`
> baseline/threshold state machine: `26-benchmark-calibration-ops.md`
