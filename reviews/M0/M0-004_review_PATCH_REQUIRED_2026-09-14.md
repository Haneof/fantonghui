# M0-004 总工程师代码审查

日期：2026-09-14

状态：

PATCH REQUIRED

审查HEAD：

98a7c92a8dd757bba79312a139630351a30e6809

## 已通过部分

总工程师确认：

- time.py整体结构符合M0-004
- timezone-aware datetime契约成立
- KnowledgeWindow成立
- Task IANA timezone验证成立
- SQLite learned_at / recorded_at索引已canonical UTC
- 所有knowledge_cutoff查询路径已canonical UTC
- 旧ISO offset字符串TEXT排序问题已被真实反例证明
- rev1 04:00Z / rev2 06:00Z / cutoff 05:00Z正确返回rev1
- 数据库已有future_secret时未提前泄露
- knowledge visibility依据learned_at而非occurred
- 正式测试138 passed
- reference 15 passed

## 阻塞问题：DST fold instant ordering

当前 TemporalExtent 使用：

self.end < self.start

当前 WorldObject 使用：

self.recorded_at < self.learned_at

Python aware datetime 在相同ZoneInfo对象下遇到DST回拨重复小时，

不能依赖这种直接墙钟比较表达唯一UTC instant。

例如 America/New_York DST回拨：

01:30 fold=0
=
05:30 UTC

01:30 fold=1
=
06:30 UTC

两者本地墙钟相同，

但真实instant不同。

AIOS唯一时间轴必须按UTC instant比较。

因此：

TemporalExtent start/end排序

以及：

WorldObject learned_at/recorded_at排序

必须显式转换为UTC后比较。

## 裁决

M0-004：

PATCH REQUIRED

执行：

M0-004-R1

M0-005：

HOLD
