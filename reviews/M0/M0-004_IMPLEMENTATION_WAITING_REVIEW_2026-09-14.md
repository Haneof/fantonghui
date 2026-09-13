# M0-004 实现记录

状态：

WAITING CHIEF ENGINEER REVIEW

日期：2026-09-14

任务：

唯一时间轴、三类时间语义、跨时区规范化与 Knowledge Cutoff 冻结

起始commit：

f705e38

## 实现了什么

1. 归档 M0-003 FINAL PASS: reviews/M0/M0-003_final_PASS_2026-09-14.md, 更新 TASK_PROGRESS

2. 修改 src/aios_core/contracts/time.py 为总工冻结版本:
   - TimePrecision, utc_now, require_aware, require_timezone_name (ZoneInfo验证), as_utc, canonical_utc_iso (fixed-shape UTC microsec +00:00)
   - TemporalExtent: point/range/open-start/open-end/unknown, 验证 aware, timezone_name IANA, unknown组合, end<start真实instant拒绝
   - KnowledgeWindow: aware cutoff, world_revision ge0

3. 检查 src/aios_core/contracts/base.py 已有 occurred/learned_at/recorded_at, recorded_at>=learned_at, 无 learned_at>=occurred约束, 符合要求, 未重写

4. 修改 src/aios_core/contracts/models.py Task:
   - 增加 require_timezone_name 验证, 合法 None/Asia/Shanghai/America/New_York, 非法 Mars/Base1/""

5. 修改 src/aios_core/storage/sqlite_store.py 时间规范化:
   - import canonical_utc_iso
   - 写 object_revisions: canonical_utc_iso(learned_at), canonical_utc_iso(recorded_at)
   - knowledge_cutoff 过滤: canonical_utc_iso(knowledge_cutoff) 覆盖 get_payload/list_payloads/_list_payloads_historical, 自动拒绝 naive
   - now_dt = utc_now(), now = canonical_utc_iso(now_dt) 用于 world_commits
   - payload_json 仍 model_dump_json(), 索引与payload分离
   - 未修改 schema/事务/world_revision/revision规则/M0-002 context/idempotency/reference validation

6. 新建 tests/unit/test_time.py 35 tests:
   - T01-T10 TemporalExtent各种状态
   - T11-T15 三类时间 (昨天发生今天知道, 今天知道明天发生, naive拒绝, recorded<learned拒绝)
   - T16-T18 KnowledgeWindow
   - T19-T21 UTC canonicalization (相同instant不同时区结果相同, +00:00固定microsec, naive拒绝)
   - T22-T26 Task跨时区
   - T27-T28 Future knowledge leakage跨时区 (04:00 vs 06:00 cutoff 05:00)
   - T29-T30 naive cutoff拒绝
   - T31-T34 timezone_name验证
   - 额外 learned_at vs occurred 回归

7. 更新 TASK_PROGRESS_R2.md, docs/DEV_LOG.md, README.md (已在M0-002加入错误协议说明，本轮无需大改)

## 哪些没有实现

- 未增加 Unix timestamp/local/device/GPS timestamp字段 (以后可为Observation内容)
- 未开发 recurrence engine, DST调度器
- 未实现完整搜索索引、预算、权限、Dependency engine
- 未修改 M0-005 WorldObject基类 (除已验证三类时间)
- 未开发migration系统，pre-M0-004 DB可重建，正式索引格式从M0-004冻结

## 为什么没有越界

- 只做M0-004时间语义冻结 + SQLite索引时间规范化 + Task timezone_name契约
- 未进入 M0-005
- 遵守总工亲自代码要求，未重新设计时间模型，按冻结代码实现

## 测试

- 正式 138 passed (103 + 35)
- Reference 15 passed
- 对抗验证 A-F 有效

## 审查证据

- reviews/M0/evidence/M0_004_REVIEW_PACKET.md
- reviews/M0/evidence/M0_004_TEST_OUTPUT.txt

## 下一步

等待总工程师 M0-004 CODE REVIEW，签发 FINAL PASS 后才允许进入 M0-005。
