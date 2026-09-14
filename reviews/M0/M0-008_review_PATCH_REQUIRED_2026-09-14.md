# M0-008 PATCH REQUIRED (TEST ONLY)

日期：2026-09-14

任务：Claim语义模型正式冻结

起始HEAD：bd250568af29170dac9a05d23011ebfc81a6a37b

GitHub Actions：SUCCESS Python 3.12.14 210 passed Reference 15 passed

生产代码：PASS / FROZEN, NO CHANGE

## 生产审查

- Claim schema符合任务书：claimant_id str, claim_type ClaimType, content str, valid_time TemporalExtent, asserted_at datetime aware, knowledge_state KnowledgeState, confidence float 0-1, support/counter list[ObjectRef], unknown_items list[str], plus WorldObject公共字段, object_type Literal CLAIM
- ClaimType至少11个，KnowledgeState独立，FACT!=truth, confidence独立，无LLM等
- 生产契约PASS/FROZEN

## Blocker 1：claimant/subject存在 or True

- tests/unit/test_claim.py最后一个测试存在：
```
assert claim.claimant_id != claim.subject_id or True
```
- 这是无效断言，永真，无法检测subject被规范化成claimant_id的bug
- 必须严格：
```
assert claim.claimant_id == "user-1"
assert claim.subject_id == "mother-subject"
assert claim.claimant_id != claim.subject_id
```
- 禁止or True或任何永真条件，冻结claimant和subject是两个独立概念，系统不得静默把subject改成claimant

## Blocker 2：核心semantic annotation未精确冻结

- 仅靠行为断言`claim.claim_type == ClaimType.FACT`不足以永久证明生产annotation仍然是ClaimType
- ClaimType和KnowledgeState都属于StrEnum，仅行为测试无法防止退化成str/Any/object
- 必须新增C17使用get_type_hints精确冻结：
  claimant_id is str
  claim_type is ClaimType
  content is str
  valid_time is TemporalExtent
  asserted_at is datetime
  knowledge_state is KnowledgeState
  confidence is float
  unknown_items origin list args (str,)
  support refs origin list args (ObjectRef,)
  counter refs origin list args (ObjectRef,)
- 这是Claim长期可解释性基础，冻结行为语义+schema类型语义

## Cleanup：C05直接datetime comparison改为as_utc

- 当前`assert claim.valid_time.start > claim.asserted_at`直接比较
- M0-004已冻结时间先转唯一UTC instant再比较
- 改成：
```
assert as_utc(valid_time.start, "valid_time.start") > as_utc(asserted_at, "asserted_at")
```
- 本轮不新增DST业务测试，只是让M0-008测试不违反时间纪律

## R1为TEST ONLY

- 禁止修改src/aios_core/**，特别是models.py, enums.py, base.py, time.py, refs.py, storage
- 仅修复test_claim.py C16 strict, 新增C17 exact, 修复C05 as_utc, 清理or True
- M0-009 HOLD

## 修复后预期

- 211 passed (210+1 C17)
- Reference 15 passed
- Production NO CHANGE proof: git diff bd25056..HEAD -- src/aios_core => NO CHANGE
- grep -n "or True" tests/unit/test_claim.py无匹配

## 状态

PATCH REQUIRED -> R1 PATCH COMPLETE后等待FINAL REVIEW
