# M0-007 实现记录

状态：R1 PATCH COMPLETE / WAITING CHIEF ENGINEER FINAL REVIEW

日期：2026-09-14

任务：Observation（基础观测）契约正式冻结 + R1消除false-green

起始commit：670c0094d03121e3621f9a34a9df5c12c594f254 (M0-007 CODE COMPLETE 193 passed GitHub SUCCESS)

## 生产Observation PASS/FROZEN NO CHANGE

当前 src/aios_core/contracts/models.py 符合任务书，无需修改，已通过总工审查

## R1漏洞

- helper直接datetime比较：`if recorded < learned: recorded = learned` 引入直接aware比较，M0-004已冻结应as_utc，且silent repair
- helper静默修复非法fixture：非法时间被修正，测试无法暴露
- O05 `or True`永真断言：`assert "confidence" not in payload or ... or True` false-green，无法检测confidence

## R1修复 TEST ONLY

- 禁止修改src/aios_core/**，包括models.py, base.py, time.py, sqlite_store.py
- 修复make_observation helper：
  删除`if recorded < learned: recorded = learned`
  改为`recorded = (recorded_at if recorded_at is not None else learned)`
  直接交给Observation WorldObject validator
- 修复O05：删除永真，改为严格`assert "confidence" not in payload`
- 新增O13：learned 10:00 UTC recorded 09:59 UTC must ValidationError，证明helper不掩盖非法时间
- 其余O01-O12保持不削弱

## 对抗验证

- A: 临时恢复or True永真，证明无法检测confidence，恢复严格，有效
- B: 临时恢复silent repair，O13失败，恢复正式，有效
- 未提交攻击代码

## 测试

- 194 passed (193+1 O13), 0 failed
- Reference 15 passed
- Production NO CHANGE: git diff 670c009..HEAD -- src/aios_core => NO CHANGE

## 证据

- tests/unit/test_observation.py R1 hardened
- reviews/M0/M0-007_review_PATCH_REQUIRED_2026-09-14.md
- reviews/M0/evidence/M0_007_REVIEW_PACKET.md with R1
- reviews/M0/evidence/M0_007_R1_TEST_OUTPUT.txt 194+15
- TASK_PROGRESS_R2.md

## 下一步

等待总工程师 M0-007 FINAL REVIEW，禁止M0-008
