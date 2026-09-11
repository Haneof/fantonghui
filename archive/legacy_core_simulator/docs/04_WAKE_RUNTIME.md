# AIOS Wake Runtime V0.1 —— 解决“不能让大模型过滤每条消息”

## 1. 直接答案

解决了。

核心不是把 0.5B 小模型换成另一个小模型，而是取消“每条信息都问一个 LLM 要不要唤醒”的架构。

## 2. 正确流水线

```text
原始信号
  ↓
DSP / Sensor / 专用模型
  ↓
Semantic Events
  ↓
Event Runtime
  ↓
World State
  ↓
Event Fusion / Temporal Pattern
  ↓
World Change
  ↓
Relevance
  ↓
Attention
  ↓
Wake Runtime
  ↓
AI
```

## 3. 每层到底做什么

### Level 0：Signal
只判断机器能廉价判断的信号：人声、运动、振动、心率变化、GPS变化、通知到达等。

### Level 1：Semanticization
专用模型把输入变成语义：ASR、说话人、视觉描述、活动识别等。

### Level 2：World Update
把事件写入当前世界，更新人物、位置、活动、环境、关系和状态。

### Level 3：Event Fusion
不看单点，按时间、空间、人物、对象、关系进行聚合。

例如：
`HR 110` 本身不触发；
`110->120->130->145 + 无活动 + 持续3分钟` 才产生高价值 World Change。

### Level 4：Relevance
判断是否与用户相关。

### Level 5：Attention
衡量是否值得消耗认知预算。

### Level 6：Wake
决定是否唤醒 AI，以及给多少资源。

## 4. Wake 类型

```text
NO_WAKE          继续记录，不运行认知
MICRO_WAKE       本地轻处理，继续观察
AI_WAKE          唤醒 AI，进入 World
EMERGENCY_WAKE   Safety 路径，绕过普通等待
```

## 5. 关键机制：Active Watch

AI 被唤醒后，可以给 AIOS 下“观察任务”：

```text
Watch {
  target: person_017
  situation: negotiation
  window: 30min
  watch_for:
    - price_change
    - rejection
    - user_silence
    - meeting_end
  wake_threshold: high
}
```

之后系统只在 Watch 条件发生重要变化时再次唤醒 AI。

因此不是：

`一小时1000条事件 -> 大模型1000次判断`

而是：

`一小时1000条事件 -> 世界运行时持续融合 -> 有几次关键变化 -> AI 被叫醒几次`

## 6. 高频场景模板的位置

模板保留，但只是优化器，不是世界模型。

例如付款、驾驶、跌倒、通话等可以用专门规则快速形成高质量 World Change。

未知场景不能因为“没有模板”而丢弃。

未知或异常的新组合反而可以提高 Attention，让 AI 来看。

## 7. 第一版必须实现的算法

优先使用确定性算法，不上小 LLM：

- 滑动时间窗口
- 去重
- 阈值变化
- 趋势检测
- 异常偏离基线
- 时间/空间聚类
- Entity 关联
- 事件重要性历史权重
- 用户当前 MODE
- 安全硬规则
- Active Watch 匹配

## 8. 一个可执行示例

### 输入

30分钟产生 500 个事件。

### 处理

```text
500 Event
 ↓
去重/过滤 -> 280
 ↓
时间空间聚合 -> 60 clusters
 ↓
状态变化 -> 15 changes
 ↓
相关性 -> 6 candidates
 ↓
Attention -> 2 wake candidates
 ↓
AI -> 1次真正介入
```

数字只是示意；真正指标等 Simulator 跑起来以后再测。

## 9. 唤醒成本函数

第一版可用简单评分：

```text
wake_score =
  safety_weight
+ relevance_weight
+ state_change_weight
+ goal_weight
+ deviation_weight
+ active_watch_weight
- interruption_cost
- confidence_penalty
```

达到阈值才 Wake。

Safety 走独立硬规则，不受普通阈值限制。

## 10. 验收条件

必须证明：

1. 10,000 条模拟事件可以在本地完成预处理。
2. AI 调用比例统一按照 §11 定义的 expensive_model_call_count / semantic_event_count 计算；§11 为唯一验收口径。
3. 同一个事件连续重复不会产生重复唤醒。
4. 趋势事件可以穿透单点噪声。
5. 未知场景不会因为无模板而自动丢弃。
6. AI Wake 后可以创建 Active Watch。

## 11. Lease 与统计口径（V0.1-r1）

Lease 唯一管理进程位于 `core/attention/lease`。Attention 负责正常请求，Safety 可发起 Emergency 请求，Lease Manager 统一签发/抢占/回收。

首版预算：
- `MICRO_WAKE`: 2s / 256 output tokens / 1 local-model call / 0 expensive-model calls
- `AI_WAKE`: 30s / 2048 output tokens / 2 expensive-model calls
- `EMERGENCY_WAKE`: 60s / 4096 output tokens / 3 expensive-model calls

`token_budget` 在 V0.1 只计 output tokens;total tokens 与 input tokens 只做 telemetry 统计,不作为 Lease 主限额。保留 `context_budget` 扩展点,本 Sprint 不实施。

统计必须同时输出：
- `semantic_event_count`
- `expensive_model_call_count`
- `ai_wake_session_count`
- `micro_wake_count`
- `emergency_wake_count`

过滤验收的核心比例为：`expensive_model_call_count / semantic_event_count <= 1%`。
