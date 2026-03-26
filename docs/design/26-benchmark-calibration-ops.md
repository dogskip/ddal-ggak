# Benchmark & Calibration Operations

> baseline, threshold, superiority claim을 운영 가능한 상태(state machine)로 정의한다.
> 이 문서가 없으면 `17-benchmark-baseline.md` 와 `07-verification-release.md` 의 gate는 실전에서 너무 쉽게 흔들린다.

---

## 1. 목적

이 문서는 3가지를 고정한다.

1. baseline artifact의 상태
2. visual threshold profile의 상태
3. superiority claim이 허용되는 조건

---

## 2. Artifact Lifecycle States

### 2.1 Baseline Artifact 상태

| State | 의미 | 허용 용도 | 금지 용도 |
|---|---|---|---|
| `placeholder` | 실측 전 가정값 | 문서 예시, 로컬 smoke | merge/release/superiority claim |
| `provisional` | 1회 이상 실측했지만 유지성 미검증 | internal regression check | external superiority claim |
| `calibrated` | 실측 + stability 검증 완료 | release gate, superiority claim | - |
| `stale` | prompt/provider/fixture 변경으로 신뢰 상실 | 참고용 열람 | gate 입력 |

### 2.2 Threshold Profile 상태

| State | 의미 | 허용 용도 |
|---|---|---|
| `assumption` | 초기 가정값 | local smoke, early prototype |
| `provisional` | labeled fixture로 1차 조정됨 | PR/merge internal regression |
| `calibrated` | false pass/false fail 검증 완료 | comparative release |
| `stale` | browser/provider/prompt 변화로 재검증 필요 | 참고용만 |

---

## 3. Benchmark Run Envelope

### 3.1 실행 단위

- full internal run = `5 benchmark cases × 2 repetitions = 10 case executions`
- full comparative run = `ddk 10 + gsd 10 = 20 case executions`

### 3.2 운영 cap

기본 team policy:

- `max_case_executions = 20`
- `max_browser_sessions = 20`
- `max_llm_calls = 120`
- `max_auto_fix_attempts = 20`
- `benchmark_cost_cap_usd = 10.0`

하나라도 초과하면 run 전체를 `invalid-infra-run` 으로 처리한다.

### 3.3 Abort 조건

- 동일 infrastructure failure 2회 연속 반복
- Playwright/browser boot failure가 2개 case 이상 발생
- baseline artifact state가 `placeholder` 인데 comparative run을 시도
- configured cost cap 초과

---

## 4. Threshold Calibration Promotion

### 4.1 `assumption -> provisional`

아래를 만족해야 한다.

- labeled golden fixtures `>= 20`
- acceptable / unacceptable 샘플에 대해 2인 human review
- critical false pass `= 0`
- overall false fail `<= 10%`

### 4.2 `provisional -> calibrated`

아래를 만족해야 한다.

- 서로 다른 3회의 benchmark run에서 threshold 결과 안정적
- composite drift `<= ±0.3`
- SSIM drift `<= ±0.02`
- critical region gate 결과 100% 동일

### 4.3 `calibrated -> stale`

아래 중 하나라도 발생하면 stale 처리한다.

- prompt `major version` 변경
- provider 또는 exact model revision 변경
- Playwright/browser major version 변경
- benchmark fixture 변경
- score formula 변경

---

## 5. Baseline Re-run Triggers

| Trigger | 범위 | 필요한 조치 |
|---|---|---|
| prompt patch version | small | targeted smoke rerun |
| prompt minor version | medium | internal benchmark rerun |
| prompt major version | large | full comparative rerun + baseline stale |
| provider model revision change | medium | internal benchmark rerun |
| provider family change | large | full comparative rerun + superiority claim 중지 |
| fixture 변경 | large | full comparative rerun |
| threshold profile 변경 | medium | benchmark rerun + comparison delta 기록 |

---

## 6. Superiority Claim Gate

### 6.1 허용 조건

`딸깍이 GSD를 능가한다` 는 문구는 아래가 모두 참일 때만 허용된다.

1. `gsd-baseline.json.measurement_status == "calibrated"`
2. `threshold_profile_status == "calibrated"`
3. 최신 comparative run 존재
4. comparison report에 `composite delta > 0`
5. critical release gates 모두 green

### 6.2 금지 조건

아래 중 하나라도 참이면 superiority claim 금지:

- baseline state = `placeholder`
- baseline state = `stale`
- threshold profile state = `assumption`
- comparative run이 prompt/provider 변경 이전 결과
- internal target만 만족하고 external baseline이 없는 상태

---

## 7. Placeholder Expiry Policy

- `placeholder` baseline은 **release gate 입력으로 절대 사용 불가**
- CI는 `measurement_status=placeholder` 를 감지하면 `ddk certify --baseline` 을 실패시켜야 한다
- docs example로는 유지 가능하되, artifact metadata에 반드시 `not-for-gating=true` 를 남긴다

---

## 8. Required Metadata

모든 benchmark artifact는 아래를 포함해야 한다.

- `measurement_status`
- `prompt_manifest_version`
- `provider_model_id`
- `threshold_profile_version`
- `fixture_set_version`
- `runner_config_hash`

---

## 9. 테스트 요구사항

### Unit

- `test_benchmark_state_machine.py`
- `test_threshold_profile_policy.py`
- `test_superiority_claim_gate.py`

### Integration

- `test_benchmark_runner_abort_conditions.py`
- `test_placeholder_baseline_blocked.py`
- `test_threshold_stale_after_provider_change.py`

---

## 10. 설계 결론

비교 벤치마크는 숫자 몇 개를 적는 문서가 아니라 **운영 상태 머신** 이어야 한다.

이 문서의 핵심은 "실측 전 가정값" 과 "release를 통과할 수 있는 신뢰된 값" 을
같은 수준으로 취급하지 못하게 만드는 데 있다.
