# AIOS Runtime Contracts V1.4

## 1. Observation Contract

任何外部输入先变成 Observation。

最小字段：

```text
observation_id
timestamp
source
modality
payload
speaker_id
provenance
privacy_level
```

Observation 不得携带未经 AI 判断的复杂语义结论。

## 2. Dimension Contract

```text
dimension_id
owner
source
subject
value_type
unit
privacy_level
provenance_policy
lifecycle
```

曲线节点至少保存：

```text
timestamp
raw_value
normalized_value
unit
confidence
source
observation_refs
previous_value
delta
direction
slope
duration
volatility
```

原始值不能因为归一化而丢失。

## 3. Trigger Contract

Trigger 必须说明：

```text
trigger_id
timestamp
trigger_type
rule_id
source_refs
window
mechanical_reason
```

Trigger 的输出是 **Wake Request**，不是语义事件。

允许的 Trigger：

- threshold
- curve_change
- keyword/entity hit
- inactivity
- schedule
- user
- safety

## 4. AI Session Contract

AI Session 至少记录：

```text
session_id
trigger_id
start_time
end_time
read_scope
input_refs
model/provider
output_refs
```

AI 可以按任务读取：当前窗口、某条曲线、人物、实体、关键词、事件锚点、历史区间、全局时间轴或 AI 自身历史判断。

## 5. Inference Event Contract

AI 生成的事件必须能够回指证据：

```text
event_id
time_window
supporting_observations
trigger_id
epistemic_status
confidence
generated_by
```

推断事件永远不能覆盖 Observation。

## 6. Action Contract

高风险 Action 必须携带：

```text
action_id
intent
risk_level
authorization
confirmation_required
input_refs
execution_result
```

涉及支付、对外发送、现实世界控制等动作必须遵守权限与确认策略。

## 7. Outcome Contract

每个重要 Action 都应该产生 Outcome，并回写 Global Timeline：

```text
outcome_id
action_id
timestamp
result
success
failure_reason
evidence_refs
```

Outcome 是 AI 后续 Self Update 的证据，不是日志垃圾桶。

## 8. UI Interaction Contract

UI 只能消费 OS 状态并产生用户操作事件：

```text
UI → UserInteraction
OS → UIState
```

UI 不得直接调用模型、修改 Timeline、写 Memory 或建立自己的 Trigger Runtime。
