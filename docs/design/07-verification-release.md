# 검증 및 릴리즈 전략

## 1. 검증 철학

`딸깍`은 generator가 아니라 production loop다. 따라서 검증은 부수 기능이 아니라 제품 코어다.

원칙:

1. 가장 낮고 신뢰할 수 있는 test layer를 우선 사용한다.
2. unit/integration/contract가 회귀 부담의 대부분을 가진다.
3. E2E는 비싸고 불안정하므로 release-critical path만 유지한다.
4. UI-affecting 작업은 runtime + visual 모두 통과해야 한다.
5. generated code execution은 sandbox 밖에서 금지한다.

## 2. Automated Test Gates

| 게이트 | 필수 항목 | 실패 시 |
| --- | --- | --- |
| Local / Pre-commit | format, lint, type, changed unit tests | commit 차단 |
| PR Gate | static checks, unit, contract, selected integration | merge 차단 |
| Merge Gate | full integration, sandbox policy, runtime validation | main merge 차단 |
| Staging Gate | visual regression, critical E2E, benchmark dry-run | staging promote 차단 |
| Release Gate | benchmark comparison, release decision, blocker audit | release 차단 |

## 3. Minimum Coverage by Intent

숫자만 높은 vanity coverage는 요구하지 않는다.

- critical business/control logic: strong unit coverage expected
- cross-layer behavior: integration coverage expected
- interface/schema compatibility: contract coverage expected
- critical user journey: minimal E2E coverage expected

필요시 숫자 threshold를 쓸 수 있으나, 이는 `repository evidence`, `team policy`, `assumption` 중 하나로 표시해야 한다.

## 4. Scorecard Gate

| 축 | 현재 보수 평가 | 목표 | Gate Type |
| --- | --- | --- | --- |
| Precision | 7.5 | 8.5+ | comparative |
| Maintainability | 7.0 | 8.5+ | comparative |
| Automation | 6.5 | 8.8+ | comparative |
| Scalability | 6.0 | reference only in v1 | non-blocking |
| Composite | 6.8~7.2 | 8.5+ in category-bound benchmark | release |

## 5. Baseline Measurement Prerequisite

release에서 comparative claim을 하려면 다음이 모두 필요하다.

- `benchmarks/gsd-baseline.json` 존재
- 동일 harness, 동일 scoring formula 사용
- baseline freshness metadata 포함
- category boundary 명시
- current run scorecard artifact 존재

위 조건이 없으면 benchmark는 informational only이며 superiority claim은 금지된다.

## 6. Flaky Test Policy

### Flaky 정의
- 동일 commit / 동일 env에서 pass/fail이 비결정적으로 바뀌는 테스트

### 정책
- release gate에서 허용 flaky tests: `0`
- quarantine 가능 계층: non-gating PR tests only
- retries 허용 계층: browser E2E와 visual capture only
- retries 상한: `1`
- stabilization owner: 변경 작성자 + test owner

## 7. Bug-fix Test Rule

모든 bug fix는 아래를 따라야 한다.

1. lowest reliable layer에 regression test 추가
2. user-visible critical flow면 필요시 integration 또는 E2E 갱신
3. sandbox, context pack, retry controller 버그는 unit + integration 둘 다 추가

## 8. Test Environment Policy

| 환경 | 범위 | 비고 |
| --- | --- | --- |
| Local dev | format, lint, type, targeted unit/integration | 빠른 피드백 우선 |
| CI PR | static + contract + selected integration | deterministic suite 위주 |
| CI Merge | full integration + sandbox + runtime validation | protected branch gate |
| Staging | visual regression + critical E2E + benchmark dry-run | real browser required |
| Production post-release | smoke verification + observability checks | limited blast radius |

## 9. Integration Test Policy

Integration tests must verify:

- workspace init to artifact writing
- repo profile creation from fixture repo
- generate -> normalize -> validate chain
- runtime failures map into stable failure taxonomy
- sandboxed command execution and denial
- visual report generation from captured screenshots
- retry controller + auto-fix attempt persistence
- evidence pack replay completeness
- release decision aggregation

## 10. Contract Test Policy

Contract tests must verify:

- CLI JSON output compatibility
- Pydantic schema compatibility
- artifact schema version stability
- failure taxonomy ID stability
- scorecard and release decision schema compatibility
- sandbox metadata schema compatibility

## 11. E2E Policy

E2E는 아래만 유지한다.

| Scenario | 이유 | Preconditions | Auth/Data | Retry | Timeout | Artifact on Failure |
| --- | --- | --- | --- | --- | --- | --- |
| E2E-01 ingest -> generate -> build pass | core happy path | fixture repo + reference image | none | 1 | strict | screenshot, logs, trace |
| E2E-02 runtime failure -> auto-fix -> pass | self-healing 핵심 | intentionally broken fixture | none | 1 | strict | diff, logs, fix history |
| E2E-03 visual mismatch -> block | visual gate 핵심 | mismatched reference | none | 1 | strict | reference/current/diff |
| E2E-04 retry budget exhausted -> manual review | bounded loop 핵심 | repeated failure fixture | none | 0 | strict | fix attempts, blocker report |
| E2E-05 benchmark + certify | release decision 핵심 | baseline artifact present | none | 0 | strict | scorecard, decision report |
| E2E-06 sandbox violation denied | safety 핵심 | malicious/forbidden fixture | none | 0 | strict | sandbox denial report |

### E2E에서 다루지 않을 것
- every validation edge case
- every console message variant
- deep normalization rule variants
- failure taxonomy leaf-level mapping
- schema-only compatibility checks

### 11.1 E2E Assertion 상세 명세

> 각 E2E 시나리오별 구체적 assertion. 구현자가 assert문을 직접 작성할 수 있는 수준.

#### E2E-01: ingest → generate → build pass

```python
async def test_e2e_happy_path(fixture_repo, sample_image):
    result = await run_case(repo=fixture_repo, image=sample_image, prompt="대시보드")

    # 1. 생성된 파일 존재
    assert len(result.generated_files) >= 1
    assert any(f.path.endswith(".tsx") for f in result.generated_files)

    # 2. 빌드 성공
    assert result.build_result.exit_code == 0
    assert result.build_result.duration_seconds < 180

    # 3. 타입체크 성공
    assert result.type_check_result.exit_code == 0
    assert result.type_check_result.error_count == 0

    # 4. Lint 성공
    assert result.lint_result.exit_code == 0

    # 5. Evidence pack 완전성
    assert result.evidence_pack is not None
    assert result.evidence_pack.llm_call_records  # 최소 1개
    assert result.evidence_pack.context_pack_hash is not None

    # 6. 최종 상태
    assert result.status == "success"
```

#### E2E-02: runtime failure → auto-fix → pass

```python
async def test_e2e_autofix_recovery(broken_fixture_repo, sample_image):
    result = await run_case(repo=broken_fixture_repo, image=sample_image, prompt="테스트")

    # 1. 초기 실패 감지
    assert result.initial_validation.has_failures
    assert any(f.family == "runtime" for f in result.initial_validation.failures)

    # 2. Auto-fix 시도
    assert len(result.fix_attempts) >= 1
    assert len(result.fix_attempts) <= 2  # bounded

    # 3. Fix 후 성공
    assert result.final_validation.build_result.exit_code == 0
    assert result.status == "success"

    # 4. Fix artifact 기록
    for attempt in result.fix_attempts:
        assert attempt.rule_id is not None
        assert attempt.target_files  # 수정 대상 존재
        assert attempt.rerun_stages  # 재검증 단계 존재
```

#### E2E-03: visual mismatch → block

```python
async def test_e2e_visual_block(fixture_repo, mismatched_reference_image):
    result = await run_case(repo=fixture_repo, image=mismatched_reference_image, prompt="테스트")

    # 1. Visual 검증 실패
    assert result.visual_result is not None
    assert result.visual_result.ssim < 0.92  # threshold 미달
    # 또는
    assert result.visual_result.missing_critical_regions  # 핵심 영역 누락

    # 2. 상태 = blocked
    assert result.status in ("visual-blocked", "blocked")

    # 3. Diff artifact 존재
    assert result.visual_result.reference_screenshot is not None
    assert result.visual_result.current_screenshot is not None
    assert result.visual_result.diff_image is not None
```

#### E2E-04: retry budget exhausted → manual review

```python
async def test_e2e_retry_exhausted(unfixable_fixture_repo, sample_image):
    result = await run_case(repo=unfixable_fixture_repo, image=sample_image, prompt="테스트")

    # 1. 재시도 예산 소진
    assert len(result.fix_attempts) == 2  # max retries
    assert all(not a.improved for a in result.fix_attempts)

    # 2. Manual review로 종료
    assert result.status == "manual-review-required"

    # 3. Blocker report 존재
    assert result.blocker_report is not None
    assert result.blocker_report.unresolved_failures  # 미해결 실패 목록
    assert result.blocker_report.attempted_rules  # 시도한 rule 목록
```

#### E2E-05: benchmark + certify

```python
async def test_e2e_benchmark_certify(fixture_repo, sample_image, baseline_artifact):
    result = await run_case(
        repo=fixture_repo, image=sample_image, prompt="대시보드",
        benchmark=True, baseline=baseline_artifact,
    )

    # 1. Scorecard 생성
    assert result.scorecard is not None
    assert result.scorecard.precision >= 0.0
    assert result.scorecard.automation >= 0.0

    # 2. Release decision
    assert result.release_decision is not None
    assert result.release_decision.status in ("ready", "blocked")

    # 3. Evidence pack에 scorecard 포함
    assert result.evidence_pack.scorecard_artifact is not None
```

#### E2E-06: sandbox violation denied

```python
async def test_e2e_sandbox_violation(malicious_fixture_repo, sample_image):
    result = await run_case(repo=malicious_fixture_repo, image=sample_image, prompt="테스트")

    # 1. Sandbox 위반 감지
    assert result.sandbox_violations  # 비어있지 않음
    assert any("forbidden" in v.lower() or "denied" in v.lower() for v in result.sandbox_violations)

    # 2. 즉시 차단
    assert result.status == "blocked"
    assert result.build_result is None or result.build_result.sandboxed

    # 3. Denial report 존재
    assert result.sandbox_denial_report is not None
```

## 12. Non-functional Tests

| 영역 | 테스트 | Gate |
| --- | --- | --- |
| Performance | P0 runtime smoke duration baseline | Staging informational |
| Security | sandbox denial, secret redaction | Merge + Release |
| Migration | schema version compatibility, upgrade path | Merge |
| Observability | evidence completeness, correlation IDs | Merge |
| Rollback | release decision to blocked/manual-review path integrity | Release |

## 13. Visual Threshold Calibration

초기 운영 기준(assumption):

| Metric | Initial Threshold | 목적 |
| --- | --- | --- |
| SSIM | `>= 0.92` | 전반적 구조 유사성 |
| Changed Pixel Ratio | `<= 5%` | 과도한 drift 차단 |
| Critical Region Overlap | `>= 0.90` | CTA/hero/form 보존 |
| Missing Critical Region Count | `0` | 핵심 컴포넌트 누락 차단 |

Calibration 절차:

1. golden fixtures 10세트 수집
2. human-reviewed acceptable vs unacceptable 분리
3. threshold sweep으로 false pass/false fail 확인
4. threshold profile versioning
5. 변경 시 benchmark impact 비교

Threshold profile state:

| State | 의미 | Gate 허용 범위 |
| --- | --- | --- |
| `assumption` | 초기 가정값 | local smoke only |
| `provisional` | 1차 실측/조정됨 | PR + merge internal regression |
| `calibrated` | 안정성 검증 완료 | comparative release |
| `stale` | prompt/provider/browser/fixture 변화로 재검증 필요 | gate 불가 |

비교 릴리즈(comparative release)에서 `assumption` 또는 `stale` threshold는 허용되지 않는다.

> 상세 운영 명세: `26-benchmark-calibration-ops.md`

## 14. Sandboxed Execution Policy

release-blocking 규칙:

- sandbox bypass detected
- forbidden path read/write detected
- forbidden network egress detected
- unredacted secret in logs detected
- command allowlist violation detected

하나라도 발생하면 즉시 blocked.

## 15. Release Blocking Conditions

아래 중 하나라도 발생하면 release 차단:

- critical path E2E failure
- contract incompatibility on public interfaces
- migration verification failure
- permission/security regression
- required tests missing for release-gating requirements
- runtime validation failure
- visual threshold failure
- sandbox policy violation
- baseline artifact required but missing for comparative release
- baseline artifact state = `placeholder` or `stale`
- threshold profile state = `assumption` or `stale` for comparative release
- observability/evidence checks missing on new critical path
- release-gating flaky test 존재
- rollback checkpoint creation or revert 실패 (auto-fix touched code)
- LLMCallRecord artifact 누락 (LLM-touched stage)
- preflight doctor green 없이 case run 시작 (CI 제외)

## 16. Mergeable / Releasable 정의

### Mergeable
- requirement-mapped tests 존재
- touched code paths에 regression tests 존재
- runtime/sandbox/schema changes는 integration or contract 포함

### Releasable
- mergeable 조건 충족
- critical E2E green
- scorecard artifact 존재
- release decision `ready`
- known critical/blocker `0`

## 17. Release Decision Algorithm

> `ReleaseDecision` 모델의 status 결정 알고리즘. Phase 4 구현의 핵심.

### 입력

```python
@dataclass
class ReleaseInput:
    scorecard: Scorecard               # benchmark 결과
    blocker_count: int                 # known critical/blocker
    e2e_results: list[E2EResult]       # E2E green/red
    contract_results: list[ContractResult]
    sandbox_violations: list[str]
    visual_threshold_state: str        # "calibrated" | "provisional" | "assumption" | "stale"
    baseline_state: str                # "fresh" | "placeholder" | "stale"
    rollback_test_passed: bool
    evidence_pack_complete: bool
    release_type: str                  # "internal" | "comparative" | "public"
```

### Decision Algorithm

```python
# src/ddk/services/release_decision.py

def compute_release_decision(inp: ReleaseInput) -> ReleaseDecision:
    blockers: list[str] = []
    warnings: list[str] = []

    # ── Hard blockers (하나라도 있으면 blocked) ──
    if inp.blocker_count > 0:
        blockers.append(f"Known blockers: {inp.blocker_count}")

    failed_e2e = [e for e in inp.e2e_results if not e.passed]
    if failed_e2e:
        blockers.append(f"E2E failures: {[e.name for e in failed_e2e]}")

    if inp.sandbox_violations:
        blockers.append(f"Sandbox violations: {inp.sandbox_violations}")

    failed_contracts = [c for c in inp.contract_results if not c.compatible]
    if failed_contracts:
        blockers.append(f"Contract breaks: {[c.name for c in failed_contracts]}")

    if not inp.rollback_test_passed:
        blockers.append("Rollback test failed")

    if not inp.evidence_pack_complete:
        blockers.append("Evidence pack incomplete")

    # ── Comparative release 추가 조건 ──
    if inp.release_type == "comparative":
        if inp.baseline_state in ("placeholder", "stale"):
            blockers.append(f"Baseline state '{inp.baseline_state}' insufficient for comparative release")
        if inp.visual_threshold_state in ("assumption", "stale"):
            blockers.append(f"Visual threshold '{inp.visual_threshold_state}' insufficient for comparative release")

    # ── Warnings (blocking은 아니나 기록) ──
    if inp.visual_threshold_state == "provisional":
        warnings.append("Visual threshold is provisional — comparative claims limited")
    if inp.baseline_state == "placeholder":
        warnings.append("Baseline is placeholder — benchmark informational only")

    # ── Decision ──
    if blockers:
        status = "blocked"
    elif warnings:
        status = "ready"  # warnings는 blocking이 아님
    else:
        status = "ready"

    return ReleaseDecision(
        status=status,
        blockers=blockers,
        warnings=warnings,
        checked_at=datetime.now(timezone.utc),
        release_type=inp.release_type,
    )
```

### Decision Matrix

| 조건 | internal release | comparative release |
| --- | --- | --- |
| known blocker > 0 | blocked | blocked |
| E2E failure | blocked | blocked |
| sandbox violation | blocked | blocked |
| contract break | blocked | blocked |
| rollback test fail | blocked | blocked |
| evidence incomplete | blocked | blocked |
| baseline = stale | ready (warning) | **blocked** |
| visual threshold = assumption | ready (warning) | **blocked** |
| 전부 통과 | **ready** | **ready** |

### 테스트 요구사항

- `test_release_decision_all_green.py` — 전부 통과 → ready
- `test_release_decision_blocker.py` — known blocker > 0 → blocked
- `test_release_decision_e2e_fail.py` — E2E 실패 → blocked
- `test_release_decision_comparative_stale_baseline.py` — comparative + stale baseline → blocked
- `test_release_decision_internal_stale_baseline.py` — internal + stale baseline → ready (warning)

## 18. 결론

검증 전략의 핵심은 **runtime truth + visual truth + bounded correction + sandbox safety** 를 동시에 release gate로 묶는 것이다.
