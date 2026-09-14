# M0-010 PATCH REQUIRED (TEST ONLY)

日期：2026-09-14

任务：Entity + Relation契约冻结

起始HEAD：225eb7636f9e88f8373de32aa332eeb83c37fd16

GitHub Actions：SUCCESS Python 3.12.14 252 passed Reference 15 passed

生产代码：PASS / FROZEN, NO CHANGE

Entity/Relation生产契约已通过审查：identity_claim_refs pinned, evidence_set_refs pinned, stable ID, canonical_name非key, unknown P001->妈妈, 同名小王不合并, Relation独立对象, left/right按ID, colleague->former_colleague, world revision replay, valid_time exact, durable mutation ER17/18 protected by M0-009 revalidation

## Blocker 1：ER01 `or True`

- tests/unit/test_entity_relation.py存在：
```
assert "object_type" in e_hints or True
```
- 这是false-green，永真，无论object_type是否存在都通过
- 必须删除，禁止任何or True/and False类逃逸

## Blocker 2：object_type exact Literal未冻结

- 当前ER01只验证默认值==ENTITY/RELATION，不足以证明annotation仍是Literal
- 因为object_type: ObjectType = ENTITY也会默认得到ENTITY但已破坏Literal冻结
- 必须精确冻结：
```
entity_object_type_ann = e_hints["object_type"]
assert get_origin(...) is Literal
assert get_args(...) == (ObjectType.ENTITY,)
```
- Relation同理 Literal[RELATION]
- 行为测试ER16负责错误object_type实例化被拒绝，schema测试ER19负责annotation不能退化

## Blocker 3：ER18使用不存在left/right导致对抗可能被NOT_FOUND掩盖

- 当前ER18 left/right使用new_object_id(ObjectType.ENTITY)但没有commit对应Entity
- 这样移除durable revalidation以后，测试仍可能因为left/right NOT_FOUND而失败，掩盖真正攻击目标floating evidence_set_ref
- 必须修复：先创建Entity A, Entity B均rev1和Observation一起或分别commit world1: Entity A, Entity B, Observation, 然后world2: EvidenceSet@1, Relation构造left=EntityA@1 right=EntityB@1 evidence=[EvidenceSet@1], 此时所有正常refs真实存在，然后原地append floating evidence revision None, commit必须StoreError INVALID_ARGUMENT reason persistence_revalidation_failed world revision保持2 Relation不存在
- 临时移除persistence revalidation运行ER18正确结果必须是ER18 FAIL，因为带floating EvidenceSet ref的Relation被旧Store错误commit成功，不能因为left/right missing出现NOT_FOUND，如果移除revalidation后仍raise NOT_FOUND/VERSION_CONFLICT则设计仍无效

## R1 TEST ONLY

- 禁止修改src/aios_core/**，包括models.py, sqlite_store.py, refs.py等
- 仅修复test_entity_relation.py ER01 false-green, 精确冻结Entity/Relation object_type Literal, 修复ER18真实Entity endpoints, 新增ER19 exact Literal guard
- M0-011 HOLD

## 修复后预期

- 253 passed (252+1 ER19)
- Reference 15 passed
- Production NO CHANGE proof: git diff 225eb76..HEAD -- src/aios_core => NO CHANGE
- grep -n "or True"无匹配, and False无匹配

## 状态

PATCH REQUIRED -> R1 PATCH COMPLETE后等待FINAL REVIEW
