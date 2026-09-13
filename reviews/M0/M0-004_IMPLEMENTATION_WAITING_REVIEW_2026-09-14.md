# M0-004 实现记录

状态：

R1 PATCH COMPLETE / WAITING CHIEF ENGINEER REVIEW

日期：2026-09-14

任务：

唯一时间轴、三类时间语义、跨时区规范化与 Knowledge Cutoff 冻结 + R1 DST fold修复

起始commit：

98a7c92a8dd757bba79312a139630351a30e6809

## 已通过部分 (总工确认)

- time.py整体结构符合M0-004
- timezone-aware datetime契约
- KnowledgeWindow
- Task IANA timezone验证
- SQLite learned_at/recorded_at索引已canonical UTC
- 所有knowledge_cutoff路径已canonical UTC
- 旧ISO offset字符串TEXT排序问题已反例证明
- rev1 04:00Z / rev2 06:00Z / cutoff 05:00Z正确返回rev1
- future_secret未提前泄露
- knowledge visibility依据learned_at而非occurred
- 正式138 passed, reference 15 passed (M0-004基线)

## R1 修复

1. TemporalExtent instant比较改为 as_utc(end) < as_utc(start)，按唯一UTC instant排序，修复DST fold下直接墙钟比较问题
2. WorldObject recorded_at/learned_at比较改为 as_utc(recorded_at) < as_utc(learned_at)，保留 recorded_at >= learned_at 语义，比较方式改为UTC
3. 未修改sqlite_store.py canonical逻辑 (NO CHANGE)
4. 新增 DST fold测试 D01-D04，真正使用 fold=0/1
   - D01: start fold=1 06:30 UTC end fold=0 05:45 UTC 本地01:45>01:30但真实05:45<06:30必须拒绝
   - D02: start fold=0 05:30 UTC end fold=1 06:15 UTC 墙钟01:15<01:30但真实06:15>05:30必须允许
   - D03: learned fold=0 05:30 recorded fold=1 06:15 本地01:15<01:30但真实06:15>05:30合法
   - D04: learned fold=1 06:30 recorded fold=0 05:45 本地01:45>01:30但真实05:45<06:30拒绝
5. 补强 canonical microseconds测试: 严格 assert == "2026-09-14T04:00:00.000000+00:00" 和 "2026-09-14T04:00:00.123456+00:00"
6. 检查其他直接时间比较: Wake.last_hit_at < first_hit_at 存在同类风险，未在本次允许范围，列为未解决问题

## 测试

- 正式 142 passed (138 + 4)
- Reference 15 passed
- 对抗 A/B/C 有效

## 审查证据

- reviews/M0/M0-004_review_PATCH_REQUIRED_2026-09-14.md
- reviews/M0/evidence/M0_004_REVIEW_PACKET.md (含R1)
- reviews/M0/evidence/M0_004_R1_TEST_OUTPUT.txt
- reviews/M0/evidence/M0_004_TEST_OUTPUT.txt (基线)

## SHA256

- time.py R1: 0a243b697f077e5cfd2dd7d364f5257b1ad6def3d91524b87e92f3713cbf531b (原 814210c7a0cf529f39fcfc5dca542ff3b203f05b6723ec4481484b7948620c59)
- base.py R1: b3a6d333736e0990995662e1f7096520d800c4621c9d3d68750392ca1d238d82
- sqlite_store.py: NO CHANGE

## 下一步

等待总工程师 M0-004 FINAL REVIEW，签发 FINAL PASS 后才允许进入 M0-005。
