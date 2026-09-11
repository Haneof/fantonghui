# AIOS Core Acceptance Tests V0.1

## A. 世界连续性

给系统连续注入 24 小时模拟事件。

必须证明：

- World State 连续更新。

- Entity 不因 session 结束而丢失。

- Time/Space 可回放。

## B. 过滤压力测试

输入：10,000 条模拟事件。

要求：

- 不允许 10,000 次大模型调用。

- 默认绝大部分事件不触发 AI。

- 同类重复事件应被融合。

- 单点异常不能直接制造大量 Wake。

首版验收目标：`expensive_model_call_count / semantic_event_count <= 1%`。其中 denominator = 进入 Event Runtime 的 Semantic Event 总数；numerator = 实际触发强推理/云端大模型的模型调用次数。`MICRO_WAKE`、DSP、规则和专用感知模型不计入该 numerator，但必须单独报告 `ai_wake_session_count`、`micro_wake_count`、`emergency_wake_count`，防止用“一个 AI session 多次调用模型”规避统计。

## C. 趋势测试

输入：

`HR 110 -> 120 -> 130 -> 145 + 无运动 + 持续3分钟`

要求：产生一个高优先级 World Change，并进入 Safety/Attention 路径。

## D. 行为偏离测试

用户基线：每天主动聊天 20 次。

连续三天：只说 2~3 次 + 提前回家 + 取消计划。

要求：产生 Behavioral Deviation candidate；不能因为单次沉默就 Wake。

## E. 未知场景测试

输入一组没有预定义模板的新场景。

要求：不能因为“无模板”而静默丢弃；允许作为低置信度变化进入 Relevance/Attention。

## F. Active Watch 测试

AI 在一次 Wake 中创建：

“关注未来30分钟内 P017 的价格变化”。

要求：之后普通噪音不唤醒；价格变化达到条件时再次 Wake。

## G. 三棵树隔离测试

让 AI 生成一个错误判断。

要求：

- 错误判断只能进入 Cognition。

- 不能直接成为 Memory fact。

- 失败结果进入 Growth。

## H. 模型切换测试

同一 AI session 从 Model A 换到 Model B。

要求：Identity / Cognition / Growth 不丢失。

## I. Action 安全测试

尝试直接调用发送消息/支付等高风险能力。

要求：Capability -> Permission -> Safety 必须完整经过。

## J. 结果回流

任何已执行 Action 都必须产生 Outcome。

Outcome 必须能够进入 Evolution，形成后续策略更新。
