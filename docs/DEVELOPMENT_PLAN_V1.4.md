# AIOS Development Plan V1.4

## 当前原则

先把 OS 主链跑通，再接真实手机、3D UI 和穿戴硬件。

## Phase 1 — OS 骨架

1. Observation Contract
2. Global Timeline
3. Dimension Registry / Curve Runtime
4. Trigger Runtime
5. AI Session Contract
6. Inference Event
7. Outcome / Self Update

## Phase 2 — Simulator

用 Mock Observation 模拟：

- 语音转写
- GPS
- 环境描述
- 身体指标
- 社交/支付/App 数据
- 汽车数据

验证：Observation → Trigger → AI Session → Event → Help → Outcome。

## Phase 3 — 3D / UI

3D Body 是交互身体，不承担认知逻辑。

UI 必须通过 Interaction Contract 接入：

```text
OS State → UI
User Gesture → OS Event
```

先用 Mock OS State 驱动 UI，后续只替换数据源，不重做 UI。

## Phase 4 — Phone Adapter

手机作为第一批现实世界数据器官：

- 通知
- 日历
- 通讯
- App 数据
- 位置
- 相册描述
- 用户授权的数据源

## Phase 5 — Wearable Adapter

逐步接入：

- IMU
- Mic
- Camera
- Haptic
- Display
- physiological sensors

## Phase 6 — AI Runtime

接入云端模型，验证：

- 上下文读取
- 用户世界理解
- 关系解析
- Help-First
- Intent-First
- 安全策略
- AI Self Update

## 禁止事项

- 不继续扩张 `core/`。
- 不恢复三棵树作为底层存储架构。
- 不让本地小模型承担复杂语义过滤。
- 不让 UI 自己实现 AI。
- 不在没有 Runtime Contract 的情况下新增设备专用逻辑。
