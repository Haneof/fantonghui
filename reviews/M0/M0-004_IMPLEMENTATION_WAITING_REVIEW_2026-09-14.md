# M0-004 实现记录

状态：

R2 PATCH COMPLETE / WAITING CHIEF ENGINEER FINAL REVIEW

日期：2026-09-14

任务：

唯一时间轴、三类时间语义、跨时区规范化与 Knowledge Cutoff 冻结 + R1 DST fold + R2 Wake UTC

起始commit：

98a7c92a8dd757bba79312a139630351a30e6809 (M0-004基线), eaf921c5f95cf057b2a5b45d450fba52d2973478 (R1)

## 已通过部分 (R1 PASS)

- TemporalExtent start/end 按UTC instant (as_utc)
- WorldObject learned/recorded 按UTC instant (as_utc)
- DST D01-D04 fold=0/1
- fixed microseconds 000000 + 123456
- SQLite canonical UTC保持不变
- 正式142 passed, reference 15 passed

## R2 修复 - 最后一个已知缺口

- 文件范围极窄: 仅 models.py + tests/unit/test_time.py + reviews/TASK_PROGRESS
- 禁止修改 time.py, base.py, sqlite_store.py, ids.py, ErrorCode, schema等
- Wake.validate_wake_times 原 `last_hit_at < first_hit_at` 直接墙钟比较，与唯一UTC instant不一致
- 修复: import as_utc, 改为 `as_utc(last_hit_at) < as_utc(first_hit_at)`，只改比较方式，保留require_aware、字段、默认值、WakeSource、WakeState、hit_count等
- 未设计Wake功能，未进入M0-014

## 新增测试

- D05: first 01:30 fold0 05:30 UTC, last 01:15 fold1 06:15 UTC, 本地01:15<01:30但真实06:15>05:30必须创建成功
- D06: first 01:30 fold1 06:30 UTC, last 01:45 fold0 05:45 UTC, 本地01:45>01:30但真实05:45<06:30必须拒绝
- naive Wake: first_hit_at naive reject, last_hit_at naive reject
- 使用正式Wake class, WakeSource.TASK_DUE, 最小合法参数

## 检查

- 剩余时间排序扫描: 搜索所有 datetime/*_at/start/end承担先后顺序的 < > 比较，已修复 TemporalExtent/WorldObject/Wake，SQLite canonical正确，`self.x < self.y`在contracts中无剩余，报告 NO_REMAINING_DIRECT_INSTANT_ORDERING_ISSUES_FOUND

## 测试

- 正式 146 passed (142+4)
- Reference 15 passed
- 对抗: 改回旧比较 D05/D06至少一个失败，攻击有效

## SHA

- time.py Before/After: 0a243b697f077e5cfd2dd7d364f5257b1ad6def3d91524b87e92f3713cbf531b 相同
- sqlite_store.py: NO CHANGE
- base.py: R1保持

## 证据

- reviews/M0/M0-004_review_PATCH_REQUIRED_2026-09-14.md (R1)
- reviews/M0/evidence/M0_004_REVIEW_PACKET.md (含R1/R2)
- reviews/M0/evidence/M0_004_R1_TEST_OUTPUT.txt 142+15
- reviews/M0/evidence/M0_004_R2_TEST_OUTPUT.txt 146+15
- reviews/M0/evidence/M0_004_TEST_OUTPUT.txt 基线

## 下一步

等待总工程师 M0-004 FINAL REVIEW，签发 FINAL PASS 后才允许进入 M0-005。
