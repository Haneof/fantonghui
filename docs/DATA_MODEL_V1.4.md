# AIOS Data Model V1.4

## 核心原则

AIOS 不再把“人生记忆树”作为独立底层系统。

统一模型是：

```text
Global Timeline
      +
Dynamic Dimensions
      +
Relationship / Entity Links
      +
AI Cognition / Self Update
```

## 数据关系

```text
Observation
   │
   ├── Dimension Point
   ├── Trigger
   └── AI Evidence
          ↓
     Inference Event
          ↓
   Cognition / Task / Action
          ↓
       Outcome
          ↓
    AI Self Update
```

## 事实与推断

Observation 是证据，不因为系统方便就变成事实。

AI 的推断必须明确状态，例如：

```text
CONFIRMED
INFERRED
UNCERTAIN
CONFLICT
```

推断可以改变；原始 Observation 不因为推断改变而被重写。

## Identity

未知说话人、人物、地点等先绑定 Unknown ID：

```text
unknown_001
unknown_002
```

后续 AI 确认后建立映射。原始记录保留，时间轴重新投影，但不篡改原始证据。

## Trend

趋势不是一个静态数字，而是时间序列属性：

```text
delta
slope
duration
volatility
persistence
direction
```

系统不允许只凭单个数值推断复杂语义事件。

## Privacy

所有数据对象必须能够携带隐私等级和 provenance。任何摘要、推断或行动都必须能回溯到允许读取的证据范围。
