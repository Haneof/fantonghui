# M0-009 实现记录

状态：R1 PATCH COMPLETE / WAITING CHIEF ENGINEER FINAL REVIEW

日期：2026-09-14

任务：EvidenceSet契约冻结 + R1 durable boundary revalidation

起始commit：1deef8c94ff105efc453ee461a19297ffa542a1b (M0-009 CODE COMPLETE 230 passed GitHub SUCCESS)

## 生产修改 R1

- models.py NO CHANGE (M0-009新增validator逻辑PASS：empty reject, pinned refs, selector dimension pinned, cutoff <= learned_at)
- 唯一允许：src/aios_core/storage/sqlite_store.py
- 增加generic persistence revalidation：
  - import ValidationError
  - 在commit中：BEGIN IMMEDIATE, idempotency replay, expected_world_revision check, 然后对object_list重新model_dump(mode python round_trip True) + model_validate(snapshot), 若ValidationError => StoreError INVALID_ARGUMENT context object_id, object_type, revision, reason persistence_revalidation_failed from exc
  - generic：不认识EvidenceSet，不hardcode
  - 错误泄露：code INVALID_ARGUMENT, context至少4字段，禁止完整payload
  - 原子性：revalidation在任何INSERT之前，失败rollback，world revision不增加，无成功idempotency record
  - idempotency顺序：replay优先，VERSION_CONFLICT优先

## 测试加固

- E01 exact：selector union exact set {EvidenceSelector, None}, filters exact dict[str,Any], aggregation exact str|None, coverage exact int|None etc
- E09 exact fixed interval：expected_start 2026-09-01, expected_end 2026-09-14 23:59, expected_cutoff 2026-09-14 23:59, 一周后读取用TemporalExtent.model_validate和KnowledgeWindow.model_validate严格as_utc equality, world_revision 1, member_refs [], 新Observation不在旧
- E13 strict error：检查"knowledge_window.knowledge_cutoff must not be after learned_at"在错误信息中

## 新增E20-E23

- E20 member_refs原地mutation：Observation target rev1 world 1, 合法EvidenceSet member [target@1], 原地append floating None, commit INVALID_ARGUMENT persistence_revalidation_failed, world 1, EvidenceSet不存在, 移除revalidation时旧实现会接受floating
- E21 selector.dimension_refs嵌套mutation：DimensionDefinition rev1 commit, selector [dim@1] + EvidenceSet, 原地append floating, commit INVALID_ARGUMENT
- E22 coverage mutation：Observation A commit, coverage 0.7 + EvidenceSet, 原地coverage_ratio 1.5, commit INVALID_ARGUMENT, 证明完整对象图验证
- E23 time_range mutation：合法selector time_range固定, 原地污染为"now-14d", commit INVALID_ARGUMENT不得持久化动态

## 保护

- M0-006 ObjectRef语义不改变，revision None仍FLOATING，M0-009仅EvidenceSet业务施加更严格，Store revalidation generic不把全系统revision mandatory
- M0-005 revision +1等保持
- idempotency顺序保持
- 不提前做M1-006/M3-002，不新增模型调用

## 对抗

A移除revalidation E20 FAIL, B E21 FAIL, C E22 FAIL, D E23 FAIL, E filters只检查第一个参数严格test失败, F旧EvidenceSet漂移E09失败，恢复有效

## 测试

- 234 passed (230+4), 0 failed, 1 warning (expected serializer warning for time_range string)
- Reference 15 passed
- Production diff：models.py NO CHANGE, sqlite_store.py CHANGED generic revalidation, 其他NO CHANGE

## 证据

- src/aios_core/storage/sqlite_store.py revalidation
- tests/unit/test_evidence_set.py 23 tests E01-E23 hardened
- reviews/M0/M0-009_review_PATCH_REQUIRED_2026-09-14.md
- reviews/M0/evidence/M0_009_REVIEW_PACKET.md with R1
- reviews/M0/evidence/M0_009_R1_TEST_OUTPUT.txt 234+15
- TASK_PROGRESS_R2.md

## 下一步

等待总工程师 M0-009 FINAL REVIEW，禁止M0-010
