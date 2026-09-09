# AIOS Runtime Contracts V0.1

## 1. Event Runtime

输入：Semantic Event

输出：规范化 Event、Event Cluster、World Update Request

负责：

- 去重

- 时间排序

- 时间窗口聚合

- 空间关联

- Entity 关联

- 事件生命周期

不负责：AI 判断、用户建议、最终唤醒决定。

## 2. World Runtime

输入：Event / Entity / State Update

输出：World State、World Change

负责维护“现在世界是什么样”。

## 3. State Runtime

输入：World 更新

输出：当前状态快照、状态变化 Delta

重点：不要只保存值，要保存变化。

示例：

`HR=72 -> HR=130` 是 State Change；单独的 `HR=130` 信息量较低。

## 4. Memory Runtime

输入：经过语义化并通过存储策略的事件/经验

输出：时间轴、多级摘要、多维索引

事实进入 Memory Tree；不得把 AI 推断直接写成事实。

## 5. Identity Runtime

输入：Voice/Name/Context/Contact/Relationship 等证据

输出：Entity Identity Resolution + confidence

允许 UNKNOWN 和多候选，不允许无证据强绑定。

## 6. Relevance Runtime

问题：这个变化与用户是否有关？

主要因素：

- 与用户本人关系

- 与当前目标关系

- 与当前 MODE 关系

- 与重要人物关系

- 与未来计划关系

- 与历史模式关系

- 风险

输出：relevance score + reason

## 7. Attention Runtime

问题：这个世界变化值不值得消耗认知资源？

输入：World Change + Relevance + MODE + Safety + history + active watches

输出：attention score + lease request

注意：它不是 LLM 分类器。

## 8. Wake Runtime

输入：Attention candidate

输出：NO_WAKE / MICRO_WAKE / AI_WAKE / EMERGENCY_WAKE

Wake 是资源调度，而不是语义理解。

## 9. AI Runtime

被唤醒后：

1. 恢复 AI identity

2. 载入 Cognitive World

3. 读取当前 World

4. 读取相关 Memory

5. 读取 Growth

6. Think

7. Judge

8. Plan

9. Request Capability

10. Reflect

模型不拥有上述持久状态。

## 10. Capability Runtime

AI 不能直接访问硬件/应用。

统一走：

`AI -> Capability -> Permission -> Safety -> Adapter -> External World`

## 11. Interaction Runtime

负责消息队列、振动语义、抬腕、触摸、语音、骨传导等交互协议。

AI 负责内容；Interaction Runtime 负责通信机制。

## 12. Evolution Runtime

保存：

- judgment

- action

- feedback

- outcome

- error

- lesson

- strategy update

策略变化必须可回滚。
