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

---

## R1 PATCH 2026-09-14 DST fold UTC instant修复

### 阻塞问题
- TemporalExtent 原使用 self.end < self.start 直接比较 aware datetime，在相同ZoneInfo下DST回拨重复小时不能代表真实UTC instant顺序
- WorldObject 原使用 self.recorded_at < self.learned_at 同样问题
- 例如 America/New_York DST回拨 2026-11-01 01:30 fold=0 = 05:30 UTC, 01:30 fold=1 = 06:30 UTC，本地墙钟相同但真实instant不同

### 修复
- TemporalExtent: 改为 as_utc(self.end, "end") < as_utc(self.start, "start")
- WorldObject: import as_utc, 改为 as_utc(recorded_at) < as_utc(learned_at)
- 保留语义 recorded_at >= learned_at，只是比较方式改为唯一UTC instant
- 未新增 learned_at >= occurred 约束
- sqlite_store.py NO CHANGE，已通过审查的 canonical UTC 实现保留

### 新增测试 D01-D04
- D01: start 01:30 fold=1 (06:30 UTC) end 01:45 fold=0 (05:45 UTC) 本地墙钟 01:45 > 01:30 但真实 05:45 < 06:30 必须拒绝，验证 as_utc(end) < as_utc(start)
- D02: start 01:30 fold=0 (05:30 UTC) end 01:15 fold=1 (06:15 UTC) 墙钟 01:15 < 01:30 但真实 06:15 > 05:30 必须允许，防 false reject
- D03: WorldObject learned fold=0 05:30 UTC recorded fold=1 06:15 UTC 本地 recorded 01:15 < learned 01:30 但真实 recorded > learned 必须合法
- D04: learned fold=1 06:30 UTC recorded fold=0 05:45 UTC 本地 recorded 01:45 > learned 01:30 但真实 recorded < learned 必须拒绝
- 全部真正使用 fold=0/1，不是仅换UTC offset模拟

### canonical microseconds补强
- 原 T20 宽松 assert ".000000" in canon or ".000" in canon
- 现严格 assert canonical == "2026-09-14T04:00:00.000000+00:00"
- 新增带microsecond 123456 测试 assert == "2026-09-14T04:00:00.123456+00:00"
- 防止未来悄悄改成milliseconds

### 其他直接时间比较检查
- 搜索 src/aios_core 中 learned_at/recorded_at/start/end 直接 < > 比较
- 已修复: TemporalExtent (as_utc), WorldObject (as_utc)
- 未修复但存在同类风险: Wake.validate_wake_times last_hit_at < first_hit_at 直接比较，未在本次任务允许范围内修改，报告为未解决问题等待裁决
- SQLite learned_at<=? 为 canonical UTC 字符串比较，正确

### 对抗验证 R1
- A TemporalExtent改回 self.end < self.start => D01 false accept 失败，攻击有效
- B WorldObject改回 recorded_at < learned_at => D04 false accept 失败，攻击有效
- C canonical改成 milliseconds => fixed microseconds测试失败，攻击有效

### 全量测试 R1
- 正式 142 passed (138 + 4 DST)
- Reference 15 passed
- Python 3.11.2

### SHA256 R1
- time.py: 0a243b697f077e5cfd2dd7d364f5257b1ad6def3d91524b87e92f3713cbf531b
- base.py: b3a6d333736e0990995662e1f7096520d800c4621c9d3d68750392ca1d238d82
- sqlite_store.py: NO CHANGE


---

## R2 PATCH 2026-09-14 Wake UTC instant修复 - M0-004最终缺口

### 背景
- R1已经通过: TemporalExtent start/end 按UTC instant, WorldObject learned/recorded 按UTC instant, DST D01-D04, fixed microseconds, SQLite canonical UTC, 142 passed
- 扫描发现 Wake.validate_wake_times 仍存在直接比较 `if self.last_hit_at < self.first_hit_at`，与唯一UTC instant语义不一致
- Wake schema属于后续M0-014完整冻结范围，本轮不设计Wake功能，只修复现有validator服从M0-004 UTC instant语义

### 修复
- 文件仅允许: src/aios_core/contracts/models.py
- import 增加 as_utc: `from .time import KnowledgeWindow, TemporalExtent, as_utc, require_aware, require_timezone_name`
- Wake validator 改为:
```
if as_utc(self.last_hit_at, "last_hit_at") < as_utc(self.first_hit_at, "first_hit_at"):
    raise ValueError("last_hit_at must not be before first_hit_at")
```
- 保留 require_aware, 保留字段、默认值、WakeSource、WakeState、hit_count、priority、dedupe_key、evidence_refs
- time.py SHA 保持 0a243b697f077e5cfd2dd7d364f5257b1ad6def3d91524b87e92f3713cbf531b 不变
- sqlite_store.py NO CHANGE

### 新增测试 D05/D06 + naive
- D05 Wake DST false-reject: first 01:30 fold=0 =05:30 UTC, last 01:15 fold=1 =06:15 UTC, 本地01:15<01:30但真实06:15>05:30必须创建成功，显式 assert as_utc(last) > as_utc(first)
- D06 Wake DST false-accept: first 01:30 fold=1 =06:30 UTC, last 01:45 fold=0 =05:45 UTC, 本地01:45>01:30但真实05:45<06:30必须拒绝，assert as_utc(last) < as_utc(first) + pytest.raises
- 额外 naive: Wake naive first_hit_at reject, naive last_hit_at reject，保留 require_aware
- 使用正式 Wake class, WakeSource.TASK_DUE 最小合法参数，不创建FakeWake，不修改enum

### 对抗验证 R2
- 临时改回 last_hit_at < first_hit_at: D05旧比较 last<first True => 错误拒绝，D06旧比较 False => 错误允许，至少一个失败，攻击有效，恢复后PASS

### 剩余时间排序扫描
- 搜索 src/aios_core 中所有 datetime / *_at / start / end 承担真实先后顺序的 < > <= >= 比较
- 已修复: TemporalExtent (as_utc), WorldObject (as_utc), Wake (as_utc)
- SQLite learned_at<=? 为 canonical UTC 字符串比较，正确
- 搜索 `self\..* < self\.` 在 contracts 中无剩余直接比较
- 结论: NO_REMAINING_DIRECT_INSTANT_ORDERING_ISSUES_FOUND

### 全量测试 R2
- 正式 146 passed (142 + 4: D05/D06 + 2 naive)
- Reference 15 passed
- Python 3.11.2

### SHA256 R2
- time.py Before: 0a243b697f077e5cfd2dd7d364f5257b1ad6def3d91524b87e92f3713cbf531b
- time.py After: 0a243b697f077e5cfd2dd7d364f5257b1ad6def3d91524b87e92f3713cbf531b 相同
- base.py: b3a6d333736e0990995662e1f7096520d800c4621c9d3d68750392ca1d238d82 保持R1
- models.py: 新增 as_utc import + Wake UTC比较
- sqlite_store.py: NO CHANGE

