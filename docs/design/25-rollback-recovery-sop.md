# Rollback & Recovery SOP

> rollback이 실패했을 때도 시스템이 조용히 망가지지 않도록 하는 운영 절차.
> 이 문서가 없으면 `15-sandbox-design.md` 의 rollback 설계는 happy path에만 강하다.

---

## 1. 목적

rollback의 성공 기준은 단순히 `git reset --hard` 를 한 번 실행하는 것이 아니다.

성공은 다음을 모두 만족해야 한다.

1. repo 상태가 pre-run snapshot과 일치
2. sandbox/worktree가 깨끗함
3. orphan file이 없음
4. artifact에 무엇이 복구되었는지 남음

하나라도 실패하면 fix loop를 계속하면 안 된다.

---

## 2. Pre-run Invariants

fix loop 시작 전 반드시 저장해야 할 것:

- `pre_run_ref`
- `pre_run_git_status` (`git status --porcelain`)
- `pre_run_untracked_files`
- `worktree_path`
- `case_id`

이 5개 중 하나라도 없으면 rollback은 `RB-001 checkpoint-metadata-missing` 으로 간주한다.

---

## 3. Rollback State Machine

```text
rollback_requested
  -> checkpoint_loaded
  -> restore_attempted
  -> verify_status
      -> clean_match        -> rollback_succeeded
      -> dirty_mismatch     -> cleanup_attempted
          -> clean_match    -> rollback_succeeded
          -> still_dirty    -> manual_review_required
```

---

## 4. Failure Matrix

| Code | 상황 | 자동 조치 | 사람 조치 | 결과 |
|---|---|---|---|---|
| `RB-001` | checkpoint metadata 없음 | 즉시 중단 | `.ddk/cases/{case_id}/` 확인 | manual review |
| `RB-002` | `restore_checkpoint(ref)` 실패 | worktree 재생성 시도 | 실패 시 repo 보호 후 종료 | manual review |
| `RB-003` | `stash pop` conflict | conflict 파일 목록 artifact 저장 | 수동 merge 또는 stash 유지 | manual review |
| `RB-004` | untracked/orphan file 잔존 | sandbox/worktree 한정 `git clean -fd` | primary repo면 수동 확인 | manual review if remains |
| `RB-005` | primary repo status mismatch | 추가 자동복구 금지 | 사람 검토 전까지 block | blocked |
| `RB-006` | worktree cleanup 실패 | worktree 디렉토리 제거 후 재생성 | 실패 시 수동 삭제 | manual review |

---

## 5. 자동 복구 순서

### 5.1 Sandbox / Worktree rollback

1. `restore_checkpoint(ref)`
2. `git status --porcelain` 비교
3. dirty면 sandbox/worktree 내부에서만 `git clean -fd`
4. 다시 status 비교
5. 여전히 dirty면 worktree 제거 후 저장된 ref로 재생성
6. 그래도 실패면 `manual-review-required`

### 5.2 Primary repo rollback

primary repo는 더 보수적으로 다룬다.

1. pre-run snapshot 로드
2. stash restore 시도
3. `git status --porcelain` 비교
4. mismatch면 추가 destructive action 금지
5. `RollbackReport` 작성 후 `manual-review-required`

primary repo에서의 자동 `git clean -fd` 는 기본 금지다.

---

## 6. Post-rollback Verification

rollback 완료 후 반드시 확인할 것:

- `git rev-parse HEAD` 가 expected ref와 일치하는가
- `git status --porcelain` 가 pre-run snapshot과 일치하는가
- 새로 생긴 tracked/untracked file이 없는가
- `.ddk/cases/{case_id}/artifacts/` 외부에 residual file이 없는가
- fix loop가 종료 상태로 기록되었는가

### 6.1 성공 판정

아래가 모두 `true` 여야 rollback success다.

```json
{
  "head_match": true,
  "status_match": true,
  "residual_files": 0,
  "worktree_recreated_if_needed": true
}
```

---

## 7. RollbackReport Artifact

```json
{
  "case_id": "C-001",
  "requested_ref": "abc1234",
  "result": "manual-review-required",
  "failure_code": "RB-003",
  "automated_steps": [
    "restore_checkpoint",
    "status_compare",
    "stash_pop"
  ],
  "verification": {
    "head_match": false,
    "status_match": false,
    "residual_files": 2
  },
  "human_actions": [
    "Resolve stash conflict in src/App.tsx",
    "Re-run ddk rollback --case-id C-001 --verify-only"
  ]
}
```

---

## 8. Human Operator SOP

### 8.1 manual-review-required 발생 시

1. `RollbackReport` 확인
2. conflict/residual file 경로 확인
3. pre-run snapshot과 현재 `git status --porcelain` diff 비교
4. 사람이 직접 복구 후 `ddk rollback --verify-only` 실행
5. success가 아니면 해당 case를 폐기하고 새 case로 재시작

### 8.2 금지 사항

- 상태가 불일치하는 repo에서 fix loop 재개 금지
- rollback 실패 후 benchmark 실행 금지
- residual file 존재 상태에서 certify 금지

---

## 9. 테스트 요구사항

### Unit

- `test_rollback_report_schema.py`
- `test_rollback_state_machine.py`
- `test_rollback_postconditions.py`

### Integration

- `test_rollback_restore_checkpoint.py`
- `test_rollback_stash_conflict_path.py`
- `test_rollback_orphan_file_cleanup.py`
- `test_rollback_verify_only.py`

### Release Gate

- rollback verification mismatch가 있으면 release blocked

---

## 10. 설계 결론

rollback은 convenience feature가 아니라 **신뢰성 경계(reliability boundary)** 다.

실패한 rollback 뒤에 계속 진행하는 순간, 이후의 모든 validation artifact는 신뢰를 잃는다.
따라서 rollback failure는 fix failure보다 더 보수적으로 다뤄야 한다.
