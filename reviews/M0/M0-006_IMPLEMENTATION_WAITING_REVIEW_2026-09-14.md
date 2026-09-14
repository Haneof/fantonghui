# M0-006 实现记录

状态：

R2 PATCH COMPLETE / WAITING CHIEF ENGINEER FINAL REVIEW

日期：2026-09-14

任务：

ObjectRef / SourceRef 版本化引用、历史钉住与引用知识可见性冻结 + R1强化 + R2 Dependency exact

起始commit：

ac83582c4746f84768197da1b460b95b39129a8a (M0-006基线 179 passed)
7c0355f1148e715e86b3be7a1d37558d26b1f218 (M0-006-R1 181 passed, Python 3.12 CI SUCCESS)

## 已通过并冻结的生产实现 (PASS/FROZEN)

- refs.py, sqlite_store.py 生产代码PASS/FROZEN
- ObjectRef revision=N pinned, revision=None floating, SourceRef版本语义, extra forbid, frozen, exact revision不存在不得fallback, pending同事务引用, generic knowledge boundary使用learned_at, DB canonical UTC, pending as_utc, future-hidden与missing统一NOT_FOUND, M0-005/M0-004不变量保持
- R09 future leakage PASS (canary FUTURE_SECRET_8848), R16/R17 DST PASS

## R1 已修复 (TEST ONLY)

- critical field annotation: list[ObjectRef]严格检查
- future leak canary补强: FUTURE_SECRET_8848严格不可逃逸
- DST R16/R17 pending visibility
- 生产代码 NO CHANGE

## R2 唯一剩余漏洞

- Dependency.dependent_ref / dependency_ref 生产契约当前是 ObjectRef，但测试helper错误允许 ObjectRef|None也通过
- 因此 M0-006-R2 = TEST ONLY

## R2 修复 (TEST ONLY)

- 禁止修改 src/aios_core/**，包括 models.py, refs.py, sqlite_store.py, base.py, time.py
- 修正 Dependency exact type test: 删除宽松Optional逻辑，改为 assert_exact_object_ref 检查 annotation is ObjectRef
- 正式冻结: Dependency.dependent_ref: ObjectRef, dependency_ref: ObjectRef，不能是 Optional/list/str/Any
- list[ObjectRef]测试保持原样: Claim, EventAnchor, EvidenceSet 全部 list[ObjectRef]

## 对抗验证 R2

- 临时将生产 models.py Dependency.dependent_ref改成 ObjectRef|None，运行critical ref test必须FAIL，恢复
- 再临时将 dependency_ref改成Optional，测试也必须FAIL，恢复
- 实际验证: 当前 is ObjectRef True, Optional is ObjectRef False -> FAIL，攻击有效
- 不得提交攻击代码

## 测试

- 正式 181 passed, 0 failed (数量保持)
- Reference 15 passed
- Production NO CHANGE证明: git diff 7c0355f..HEAD -- src/aios_core => NO CHANGE

## 证据

- reviews/M0/M0-006_review_PATCH_REQUIRED_2026-09-14.md (R1)
- reviews/M0/evidence/M0_006_REVIEW_PACKET.md (含R1/R2)
- reviews/M0/evidence/M0_006_R1_TEST_OUTPUT.txt 181+15
- reviews/M0/evidence/M0_006_R2_TEST_OUTPUT.txt 181+15
- tests/unit/test_refs.py (R2 exact)

## 下一步

等待总工程师 M0-006 FINAL REVIEW，签发 FINAL PASS 后才允许进入 M0-007。
