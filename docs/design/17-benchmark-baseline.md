# Benchmark Baseline 측정 명세

> GSD vs 딸깍 비교 gate의 기준값 정의 및 측정 harness 설계.
> 이 문서 없이는 `ddk certify`의 benchmark gate가 공허하다.

---

## 핵심 원칙

1. **측정 우선**: "GSD보다 좋다"는 주장은 실측값이 있을 때만 유효하다.
2. **같은 harness**: 딸깍과 GSD를 동일한 테스트 픽스처 + 동일한 채점 방식으로 측정한다.
3. **P0 릴리즈 블로커**: baseline artifact `benchmarks/gsd-baseline.json`이 없으면 `ddk certify --baseline`이 블록된다.

---

## 1. Scorecard 항목 정의

```json
// benchmarks/scorecard-schema.json
{
  "precision": {
    "description": "생성된 UI가 참조 이미지와 얼마나 일치하는가",
    "formula": "(ssim * 0.4 + layout_match * 0.4 + component_match * 0.2) * 10",
    "range": "0.0 ~ 10.0",
    "inputs": {
      "ssim": "VisualRegressionReport.ssim",
      "layout_match": "critical_region_overlap",
      "component_match": "intent_graph.confidence"
    }
  },
  "maintainability": {
    "description": "생성된 코드가 기존 repo convention에 얼마나 맞는가",
    "formula": "(10 - normalization_report.drift_score_after) / 10 * 10",
    "range": "0.0 ~ 10.0",
    "inputs": {
      "drift_score_after": "NormalizationReport.drift_score_after (0~10)"
    }
  },
  "automation": {
    "description": "사람 개입 없이 자동으로 완료된 비율",
    "formula": "certified_auto_cases / total_cases * 10",
    "range": "0.0 ~ 10.0",
    "inputs": {
      "certified_auto": "ReleaseDecision.status == 'certified-ready' without human touch",
      "total_cases": "전체 벤치마크 케이스 수"
    },
    "note": "fix 시도 3회 이내 자동 통과 = 자동 완료"
  },
  "scalability": {
    "description": "복잡도 증가에 따른 성능 저하 저항성",
    "formula": "(simple_score - complex_score) * -1 + 5",
    "range": "0.0 ~ 10.0",
    "note": "complex = 3개 이상 레이아웃 영역, API binding 포함",
    "v1_note": "P0에서는 reference only (단순 케이스만 측정)"
  },
  "composite": {
    "formula": "(precision * 3 + maintainability * 2 + automation * 3 + scalability * 2) / 10"
  }
}
```

---

## 2. Benchmark Test Suite

### 픽스처 구성 (P0)

```
benchmarks/
├── cases/
│   ├── BM-001-simple-card/
│   │   ├── input.png           # 단순 카드 컴포넌트 목업
│   │   ├── prompt.txt          # "카드 컴포넌트 생성"
│   │   ├── visual-reference.png
│   │   └── expected-files.json # 생성되어야 할 파일 목록
│   ├── BM-002-login-form/
│   │   ├── input.png
│   │   ├── prompt.txt
│   │   ├── visual-reference.png
│   │   └── expected-files.json
│   ├── BM-003-data-table/
│   │   ├── input.png
│   │   ├── prompt.txt
│   │   ├── visual-reference.png
│   │   └── expected-files.json
│   ├── BM-004-dashboard-layout/  # complex case
│   │   ├── input.png
│   │   ├── prompt.txt
│   │   ├── visual-reference.png
│   │   └── expected-files.json
│   └── BM-005-modal-flow/
│       ├── input.png
│       ├── prompt.txt
│       ├── visual-reference.png
│       └── expected-files.json
│
├── target-repos/
│   └── react-vite-ts/          # 표준 테스트 repo (fixtures/repos/와 동일)
│
├── gsd-baseline.json           # GSD 측정 결과 (실측 후 저장)
├── ddk-results.json            # 딸깍 측정 결과 (자동 생성)
└── comparison-report.json      # 비교 보고서 (자동 생성)
```

### benchmark runner

```python
# scripts/run_benchmark.py

"""
사용법:
  python scripts/run_benchmark.py --tool ddk --cases all
  python scripts/run_benchmark.py --tool gsd --cases all
  python scripts/run_benchmark.py --compare
"""

import asyncio
import json
from pathlib import Path

BENCHMARK_CASES = ["BM-001", "BM-002", "BM-003", "BM-004", "BM-005"]

async def run_ddk_benchmark():
    results = {}
    for case_id in BENCHMARK_CASES:
        case_dir = Path(f"benchmarks/cases/{case_id}-*")
        # ddk run으로 케이스 실행
        # scorecard 수집
        # results[case_id] = scorecard.model_dump()
    return results

def compute_aggregate(results: dict) -> dict:
    """5개 케이스의 평균 scorecard 계산"""
    metrics = ["precision", "maintainability", "automation", "scalability", "composite"]
    aggregate = {}
    for m in metrics:
        vals = [r[m] for r in results.values() if r.get(m) is not None]
        aggregate[m] = sum(vals) / len(vals) if vals else None
    return aggregate

def compare_baselines(ddk: dict, gsd: dict) -> dict:
    """GSD vs 딸깍 비교 리포트 생성"""
    metrics = ["precision", "maintainability", "automation", "scalability", "composite"]
    comparison = {}
    for m in metrics:
        ddk_val = ddk.get(m)
        gsd_val = gsd.get(m)
        if ddk_val is not None and gsd_val is not None:
            comparison[m] = {
                "ddk": ddk_val,
                "gsd": gsd_val,
                "delta": ddk_val - gsd_val,
                "winner": "ddk" if ddk_val > gsd_val else "gsd" if gsd_val > ddk_val else "tie"
            }
    return comparison
```

---

## 3. GSD Baseline 측정 방법

### GSD 측정 불가 항목

GSD는 딸깍과 다른 카테고리 제품이므로, 일부 항목은 GSD에 해당하지 않는다:

| 항목 | GSD 측정 가능? | 대안 |
|------|--------------|------|
| precision (visual match) | ❌ GSD는 이미지 입력 없음 | GSD 코드 생성 품질로 대체 평가 |
| maintainability (convention drift) | ✅ ESLint/TSC 에러 수 | 적용 |
| automation (auto-complete rate) | ✅ 성공률 기준 | 적용 |
| scalability | △ 참고용 | 참고용 |

### 비교 기준 재정의

GSD와 딸깍은 완전히 다른 문제를 풀기 때문에, 비교 게이트를 다음과 같이 재정의한다:

```
딸깍 우위 조건:
1. precision >= 7.5  (이미지 → 코드 정확도, GSD에 없는 능력)
2. maintainability >= 7.0  (convention 준수)
3. automation >= 7.0  (자동 완료율, BM-001~003 기준)
4. 5개 BM 케이스 중 4개 이상 certified-ready
5. composite >= 7.5
```

이것은 "GSD와 같은 것을 더 잘 한다"가 아니라 "GSD가 못하는 것을 잘 한다"는 우위 기준이다.

---

## 4. 초기 추정값 (P0 릴리즈 전 가정)

> **이 값은 가정이다.** P0 구현 완료 후 실측으로 교체 필요.
> `benchmarks/gsd-baseline.json`에 실측 전까지 아래 값을 placeholder로 저장.

```json
// benchmarks/gsd-baseline.json (실측 전 placeholder)
{
  "schema_version": "1.0",
  "tool": "gsd",
  "measurement_status": "placeholder",
  "note": "실측 전 가정값. P0 구현 후 run_benchmark.py --tool gsd로 교체",
  "cases": {},
  "aggregate": {
    "precision": null,
    "maintainability": null,
    "automation": null,
    "scalability": null,
    "composite": null
  },
  "measured_at": null
}
```

딸깍 자체 목표값 (P0 달성 기준):

```json
// benchmarks/ddk-p0-targets.json
{
  "targets": {
    "precision": 7.5,
    "maintainability": 7.0,
    "automation": 6.5,
    "scalability": 5.0,
    "composite": 7.0
  },
  "certification_rate": 0.8,
  "note": "BM-001~005 중 4개 이상 certified-ready"
}
```

---

## 5. P0 릴리즈 전 필수 작업

1. `fixtures/repos/react-vite-ts/` 표준 테스트 repo 구성
2. `benchmarks/cases/BM-001~005/` 입력 이미지 및 prompt 확정
3. `scripts/run_benchmark.py` 구현 및 동작 검증
4. P0 코어 루프 구현 후 딸깍 5개 케이스 실행
5. `benchmarks/ddk-results.json` 실측값 저장
6. 목표값과 비교 후 certify gate 활성화

---

## 6. Baseline Artifact State

`gsd-baseline.json` 과 `ddk-results.json` 은 아래 상태를 가진다.

| State | 의미 | gate 사용 가능 여부 |
|---|---|---|
| `placeholder` | 문서용 가정값 | 불가 |
| `provisional` | 1회 이상 실측 | internal only |
| `calibrated` | 실측 + 안정성 검증 완료 | 가능 |
| `stale` | prompt/provider/fixture 변화로 무효화 | 불가 |

`measurement_status=placeholder` 는 bootstrap 예시로만 허용되며,
release 또는 superiority claim의 입력으로는 절대 허용되지 않는다.

---

## 7. Benchmark Run Envelope

운영 cap (team policy):

- full internal run = `5 cases × 2 repetitions = 10 executions`
- full comparative run = `20 executions`
- `max_browser_sessions = 20`
- `max_llm_calls = 120`
- `max_auto_fix_attempts = 20`
- `benchmark_cost_cap_usd = 10.0`

다음 중 하나라도 만족하면 run 전체를 `invalid-infra-run` 으로 처리한다.

- 동일 infra failure 2회 연속
- browser boot failure 2개 case 이상
- configured cost cap 초과

---

## 8. Re-run Triggers

아래 변경이 있으면 baseline을 다시 측정해야 한다.

- prompt `minor` or `major` version change
- provider exact model revision change
- provider family change
- benchmark fixture 변경
- threshold profile 변경
- score formula 변경

provider family change 또는 prompt major change는 baseline state를 즉시 `stale` 로 만든다.

---

## 9. Comparative Claim Policy

`딸깍이 GSD를 능가한다` 는 비교 문구는 아래가 모두 참일 때만 허용된다.

1. `gsd-baseline.json.measurement_status == "calibrated"`
2. `threshold_profile_status == "calibrated"`
3. 최신 comparative run 존재
4. comparison report에서 `composite delta > 0`

그 외에는 internal target 달성만 말할 수 있으며, superiority claim은 금지한다.

> 상세 운영 규칙: `26-benchmark-calibration-ops.md`
