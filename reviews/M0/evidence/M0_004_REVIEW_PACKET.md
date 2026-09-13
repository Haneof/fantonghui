# M0-004 审查证据包

## 任务
唯一时间轴、三类时间语义、跨时区规范化与 Knowledge Cutoff 冻结

## 起始commit
f705e38 (M0-003 FINAL PASS, ids.py SHA256 9972e1d4d7e272019da26d8fb466a9391dea868039e43b5fc9cdaf33073a8993)

## time.py最终SHA256
814210c7a0cf529f39fcfc5dca542ff3b203f05b6723ec4481484b7948620c59
路径: src/aios_core/contracts/time.py
与总工冻结代码语义一致

## 三类时间正式定义
- occurred: TemporalExtent, 事情在世界中什么时候发生 (point/range/open/unknown)
- learned_at: datetime aware, AIOS什么时候获得/知道这条资料, 无默认等于occurred, 必须调用者明确提供
- recorded_at: datetime aware, 该revision什么时候真正写入AIOS, default_factory=utc_now, 必须 >= learned_at
- 禁止 learned_at >= occurred 约束，因为未来计划/预测可以先知道后发生 (learned < occurred 合法)
- 例如：用户9月14日说“我9月13日去了医院” => occurred 9/13, learned 9/14, recorded >= learned
- 例如：用户今天说“我明天去医院” => learned < occurred 合法

## TemporalExtent状态组合
- point: start已知, end==start
- bounded range: start已知, end已知, end>=start (真实instant比较，支持不同时区)
- open-start: start=None, end=aware
- open-end: start=aware, end=None
- explicit unknown: unknown=True, start=None, end=None, precision=UNKNOWN
- 非法: unknown=False + start=None+end=None 拒绝
- 非法: unknown=True + 有start/end 拒绝
- 非法: unknown=True + precision!=UNKNOWN 拒绝
- 非法: end真实instant < start 拒绝 (即使local clock看似更晚)

## timezone_name规则
- 表示保留的本地时区规则名称，IANA timezone
- 合法: Asia/Shanghai, America/New_York, Europe/London, UTC, None
- 非法: "China Time", "New York Time", "北京时间", "Mars/Base1", "" 自由文本
- 验证: ZoneInfo(value) 可解析
- 语义: datetime负责唯一instant, timezone_name负责本地显示/周期调度, 二者不要求逐字符相同
- 例如 next_wake_at UTC表示，timezone_name 仍可 America/New_York

## canonical UTC规则
- as_utc(value, field_name): require_aware + astimezone(UTC)
- canonical_utc_iso(value, field_name): as_utc(...).isoformat(timespec="microseconds") => 固定形状 2026-09-14T04:00:00.000000+00:00
- 以 +00:00 结尾, 固定microseconds
- 示例: 12:00 Asia/Shanghai (04:00 UTC) 和 04:00 UTC canonical结果完全相同
- naive datetime拒绝

## SQLite时间索引规则
- object_revisions表 learned_at, recorded_at 为 TEXT
- 原实现直接 isoformat() 保留原始offset，不同offset间字符串顺序 != 真实时间顺序
- 例: 12:00+08 (04:00Z) 文本 "2026-09-14T12:00:00+08:00" > "2026-09-14T05:00:00+00:00" (05:00Z)，但真实 04:00Z < 05:00Z，旧实现错误
- 新实现:
  - 写 object_revisions: canonical_utc_iso(obj.learned_at, "learned_at"), canonical_utc_iso(obj.recorded_at, "recorded_at")
  - knowledge_cutoff 过滤: canonical_utc_iso(knowledge_cutoff, "knowledge_cutoff")
  - 覆盖 get_payload, list_payloads, _list_payloads_historical
  - 自动实现 naive cutoff拒绝 (require_aware)
  - now = utc_now() -> canonical_utc_iso(now_dt, "now") 用于 world_commits committed_at
- payload_json 仍由 model_dump_json() 生成，保留原始offset，索引与payload职责分离
- schema未修改, 事务未修改, world_revision未修改, M0-002错误context未修改, idempotency未修改, reference validation未修改

## 跨时区cutoff案例
- 数据库已有 rev1 learned 12:00+08=04:00 UTC value "known_before_cutoff"
- rev2 learned 02:00-04=06:00 UTC value "future_secret"
- cutoff 05:00 UTC
- 旧实现直接ISO字符串比较: "12:00+08" <= "05:00+00" ? False (错误)
- 新实现 canonical: "04:00.000000+00:00" <= "05:00.000000+00:00" ? True, 返回 rev1, 不泄露 future_secret
- T27, T28 验证通过

## Future knowledge leakage案例
- 对象 occurred 2020年, learned 2026年, cutoff 2025年
- 即使 occurred < cutoff, 但 learned > cutoff, 对象不应可见
- 可见性取决于 learned_at <= cutoff, 不是 occurred <= cutoff
- test_knowledge_cutoff_uses_learned_at_not_occurred 验证: get_payload 抛 NOT_FOUND, list_payloads 返回0
- 非常关键的AIOS规则

## Task跨时区测试
- T22 timezone_name America/New_York + next_wake_at ZoneInfo NY + deadline aware 成功, next_wake_at.astimezone(UTC) 唯一instant
- T23 Asia/Shanghai 成功
- T24 Mars/Base1 失败 (invalid IANA)
- T25 naive next_wake_at 失败
- T26 naive deadline 失败
- 未实现 recurrence engine / DST调度器，仅冻结输入契约

## 对抗验证
- A 删除 TemporalExtent naive验证 -> naive测试失败，攻击有效
- B store改回 knowledge_cutoff.isoformat() -> 跨时区future leakage测试失败 (04:00 vs 05:00 字符串比较错误)，攻击有效
- C learned_at索引改回 obj.learned_at.isoformat() -> 同B，跨时区cutoff测试失败，攻击有效
- D 错误加入 learned_at >= occurred 约束 -> 今天知道明天事件测试失败，攻击有效
- E 删除 Task timezone_name 验证 -> invalid IANA测试失败，攻击有效
- F 数据库cutoff按 occurred 判断 -> learned_at-not-occurred测试失败，攻击有效
- 攻击后恢复正式代码

## 正式pytest
- Python 3.11.2 (正式 >=3.12, PYTHON_312_CI_RESULT_UNAVAILABLE, CI_WORKFLOW_PRESENT)
- 138 passed (103原 + 35新增 test_time.py)
- Reference 15 passed
- 当前正式基线 103 -> 138 增加

## Reference pytest
- 15 passed, reference中 time.py 只是早期地基快照，正式代码正确超越reference，不能为保持diff=0拒绝修正

## pre-M0-004 DB说明
- M0-004以前的开发测试DB属于可重建数据，索引时间可能使用原始offset字符串
- 正式时间索引格式从M0-004开始冻结为canonical UTC
- 不开发migration系统，不修改schema版本系统，不增加迁移服务

## Python版本
- 正式 >=3.12, 本地 3.11.2, PYTHON_312_CI_RESULT_UNAVAILABLE

## 未实现事项
- Unix timestamp字段, local timestamp, device timestamp, GPS timestamp (以后可为Observation内容)
- 完整 Task recurrence engine, DST调度器
- 完整搜索索引, 预算系统, 权限系统, Dependency engine, M0-005 WorldObject扩展, M0-004以外
- 本任务只冻结核心世界时间契约

## git status
clean after commit
