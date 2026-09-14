# M0-008 实现记录

状态：R1 PATCH COMPLETE / WAITING CHIEF ENGINEER FINAL REVIEW

日期：2026-09-14

任务：Claim（主张）语义模型正式冻结 + R1严格冻结类型契约消除false-green

起始commit：bd250568af29170dac9a05d23011ebfc81a6a37b (M0-008 CODE COMPLETE 210 passed GitHub SUCCESS)

## 生产Claim PASS/FROZEN NO CHANGE

当前Claim schema符合任务书，已通过总工审查

## R1漏洞

- Blocker1: claimant/subject测试存在`or True`永真，无法检测subject被规范化成claimant bug
- Blocker2: 核心semantic annotation未精确冻结，仅行为断言不足以证明annotation仍是ClaimType/KnowledgeState
- Cleanup: C05直接datetime comparison改为as_utc per M0-004纪律

## R1修复 TEST ONLY

- 禁止修改src/aios_core/**，特别是models.py, enums.py, base.py, time.py, refs.py, storage
- 修复C16：正式命名test_c16_claimant_vs_subject_independent，严格assert claimant user-1 subject mother-subject !=，禁止or True
- 新增C17：get_type_hints精确冻结claimant_id str, claim_type ClaimType exact, content str, valid_time TemporalExtent, asserted_at datetime, knowledge_state KnowledgeState exact, confidence float, unknown_items list[str], support/counter list[ObjectRef]
- 修复C05：直接比较改为as_utc比较
- 其余C01-C15保持
- 禁止永真：grep or True无匹配

## 对抗验证

- A: subject规范化成claimant C16 FAIL, 恢复有效
- B: claim_type改str C17 FAIL, 恢复有效
- C: knowledge_state改str C17 FAIL, 恢复有效
- D: unknown_items改list[Any] C17 FAIL, 恢复有效
- 未提交攻击代码

## 测试

- 211 passed (210+1), 0 failed
- Reference 15 passed
- Production NO CHANGE: git diff bd25056..HEAD -- src/aios_core => NO CHANGE
- No false-green: or True scan无匹配

## 证据

- tests/unit/test_claim.py R1 hardened C16 strict C17 exact C05 as_utc
- reviews/M0/M0-008_review_PATCH_REQUIRED_2026-09-14.md
- reviews/M0/evidence/M0_008_REVIEW_PACKET.md with R1
- reviews/M0/evidence/M0_008_R1_TEST_OUTPUT.txt 211+15
- TASK_PROGRESS_R2.md

## 下一步

等待总工程师 M0-008 FINAL REVIEW，禁止M0-009
