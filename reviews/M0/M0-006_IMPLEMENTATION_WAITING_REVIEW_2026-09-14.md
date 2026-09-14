# M0-006 实现记录

状态：

R1 PATCH COMPLETE / WAITING CHIEF ENGINEER REVIEW

日期：2026-09-14

任务：

ObjectRef / SourceRef 版本化引用、历史钉住与引用知识可见性冻结 + R1强化测试

起始commit：

ac83582c4746f84768197da1b460b95b39129a8a (M0-006基线 179 passed, Python 3.12 CI SUCCESS)

## 已通过并冻结的生产实现 (PASS/FROZEN)

- refs.py, sqlite_store.py 已通过审查
- ObjectRef revision=N pinned, revision=None floating, SourceRef版本语义, extra forbid, frozen, exact revision不存在不得fallback, pending同事务引用, generic knowledge boundary使用referencing learned_at, DB knowledge visibility使用canonical UTC, pending visibility使用as_utc, future-hidden与missing统一NOT_FOUND, M0-005/M0-004不变量保持
- GitHub Actions SUCCESS Python 3.12 179 passed

## R1 阻塞仅为测试冻结不足

- 阻塞A: critical model ref test仅检查字段名存在，未验证annotation确实是ObjectRef
- 阻塞B: R09 future leakage断言存在OR逃逸，可能泄露时仍false-green
- 阻塞C: pending visibility新增datetime排序路径，但无DST fold integration test
- 因此 M0-006 PATCH REQUIRED (TEST ONLY), M0-007 HOLD

## R1 修复 (TEST ONLY)

- 生产代码 NO CHANGE
- 修复 critical model ref field test: 使用 get_type_hints/get_origin/get_args，验证 list[ObjectRef] 和 ObjectRef，若未来改为 str/list[str]/dict/Any测试必须失败
  - Claim.support_evidence_set_refs, counter_evidence_set_refs
  - EventAnchor.primary_claim_refs, evidence_set_refs
  - EvidenceSet.member_refs/support_refs/counter_refs/context_refs
  - Dependency.dependent_ref, dependency_ref
- 修复 R09 future leakage: 删除OR逃逸，使用明确canary FUTURE_SECRET_8848，验证 code, context referenced_object_id, referenced_revision, reason=reference_not_visible_or_missing，且 serialized_error中不得包含 FUTURE_SECRET_8848/"11:00"/"learned_at"/"payload"
- 新增 R16 pending DST false-accept: A 01:45 fold0 05:45 UTC引用B 01:30 fold1 06:30 UTC，墙钟01:30<=01:45但真实06:30>05:45，必须NOT_FOUND，world仍0
- 新增 R17 pending DST false-reject: B 01:30 fold0 05:30 UTC, A 01:15 fold1 06:15 UTC，墙钟01:30>01:15但真实05:30<06:15，必须成功 world==1

## 对抗验证

- A 删除ObjectRef类型断言模拟list[str] => 强化后类型检查失败，证明冻结有效
- B 错误context加入payload canary => R09失败
- C 生产逻辑改回直接aware比较 => R16/R17至少失败
- 禁止提交攻击代码，生产代码未修改

## 测试

- 正式 181 passed (179+2), 0 failed
- Reference 15 passed
- Python 3.11.2本地，GitHub Actions Python 3.12预期181

## 生产代码不变证明

- git diff ac83582..HEAD -- refs.py sqlite_store.py base.py models.py time.py ids.py enums.py operations.py => NO CHANGE

## 证据

- reviews/M0/M0-006_review_PATCH_REQUIRED_2026-09-14.md
- reviews/M0/evidence/M0_006_REVIEW_PACKET.md (含R1)
- reviews/M0/evidence/M0_006_R1_TEST_OUTPUT.txt 181+15
- tests/unit/test_refs.py (R16/R17 + 强化)

## 下一步

等待总工程师 M0-006 FINAL REVIEW，签发 FINAL PASS 后才允许进入 M0-007。
