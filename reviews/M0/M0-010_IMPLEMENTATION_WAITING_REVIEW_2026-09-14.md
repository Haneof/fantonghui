# M0-010 实现记录

状态：R1 PATCH COMPLETE / WAITING CHIEF ENGINEER FINAL REVIEW

日期：2026-09-14

任务：Entity + Relation契约冻结 + R1消除false-green修复ER18引用掩盖

起始commit：225eb7636f9e88f8373de32aa332eeb83c37fd16 (M0-010 CODE COMPLETE 252 passed GitHub SUCCESS)

## 生产Entity/Relation PASS/FROZEN NO CHANGE

- Entity validator identity_claim_refs pinned, Relation validator evidence_set_refs pinned, stable ID, canonical_name非key等已通过审查

## R1漏洞

- Blocker1 ER01 `or True` false-green
- Blocker2 object_type exact Literal未冻结，仅验证默认值
- Blocker3 ER18使用不存在left/right导致对抗可能被NOT_FOUND掩盖

## R1修复 TEST ONLY

- 禁止修改src/aios_core/**，包括models.py, sqlite_store.py等
- 修复ER01：删除or True，精确冻结Entity object_type Literal[ENTITY] get_origin Literal get_args (ENTITY,), Relation object_type Literal[RELATION]
- 修复ER18：先创建Entity A B Observation commit world1, EvidenceSet@1 world2, Relation left A@1 right B@1 evidence [ES@1]，所有正常refs真实存在，然后append floating evidence revision None，commit必须StoreError INVALID_ARGUMENT persistence_revalidation_failed world 2 Relation不存在，证明真正攻击目标
- 新增ER19 exact Literal guard：专门冻结Entity/Relation object_type annotation，ER16负责行为，ER19负责schema
- ER17保持真实Claim
- 禁止永真：grep or True/and False无匹配

## 对抗

- A Entity Literal->ObjectType ER19 FAIL, 恢复有效
- B Relation同理 ER19 FAIL, 恢复有效
- C 旧ER18不存在left/right会NOT_FOUND掩盖，恢复真实endpoint有效
- D 移除revalidation修复后ER18必须FAIL floating evidence被持久化，恢复有效

## 测试

- 253 passed (252+1 ER19), 0 failed, 1 warning (E23 serializer warning预期)
- Reference 15 passed
- Production NO CHANGE proof: git diff 225eb76..HEAD -- src/aios_core => NO CHANGE
- No false-green scan PASS

## 证据

- tests/unit/test_entity_relation.py R1 hardened ER01 exact Literal, ER18 real endpoints, ER19
- reviews/M0/M0-010_review_PATCH_REQUIRED_2026-09-14.md
- reviews/M0/evidence/M0_010_REVIEW_PACKET.md with R1
- reviews/M0/evidence/M0_010_R1_TEST_OUTPUT.txt 253+15
- TASK_PROGRESS_R2.md

## 下一步

等待总工程师 M0-010 FINAL REVIEW，禁止M0-011
