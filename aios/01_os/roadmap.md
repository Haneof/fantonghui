# AIOS 01_os · V1.4 开发路线图

> 当前有效架构：AIOS Constitution V1.4-r0。
> 当前目标：先把 Observation → Trigger → AI Session → Inference Event → Help → Outcome 这条 OS 主链跑通。

## M0 · 骨架与契约

- [ ] Observation Contract
- [ ] Global Timeline
- [ ] Dimension Registry
- [ ] Trigger Contract
- [ ] AI Session Contract
- [ ] Inference Event Contract
- [ ] Outcome / Self Update Contract
- [ ] Interaction Contract

**验收：** 所有对象都能挂到同一时间轴；Observation 与 Inference Event 分离；Trigger 不产生语义结论。

## M1 · Observation + Timeline

- [ ] 多模态 Mock Observation
- [ ] 时间统一与 provenance
- [ ] 原始证据保存/回放
- [ ] Dimension Point
- [ ] 曲线方向、斜率、持续时间、波动、持久偏离

**验收：** 同一批输入可稳定回放；原始证据不被推断覆盖。

## M2 · Trigger Runtime

- [ ] threshold
- [ ] curve change
- [ ] keyword/entity hit
- [ ] inactivity
- [ ] schedule
- [ ] user trigger
- [ ] safety trigger
- [ ] Trigger audit

**验收：** Trigger 只负责机械唤醒，不做“是不是谈判/焦虑”等语义判断。

## M3 · AI Runtime

- [ ] AI Session
- [ ] 按任务选择读取范围
- [ ] Identity / Unknown ID
- [ ] Inference Event
- [ ] Cognition
- [ ] Help-First / Intent-First
- [ ] AI Self Update

**验收：** AI 能从触发窗口进入用户世界，引用证据并生成可追溯的事件/认知。

## M4 · Capability + Safety

- [ ] Capability Registry
- [ ] Permission / Confirmation
- [ ] Safety Runtime
- [ ] Action
- [ ] Outcome

**验收：** 高风险动作不能绕过权限；安全事件可越过普通干预预算。

## M5 · 3D / UI

- [ ] 3D Body
- [ ] UI State
- [ ] Gesture Event
- [ ] Haptic / Voice / Display abstraction
- [ ] Mock OS State 驱动

**验收：** UI 不拥有 AI、Memory、Timeline、Trigger；真实 Runtime 接入时不需要重写 UI 核心。

## M6 · Phone Adapter

- [ ] 通知
- [ ] 日历
- [ ] 位置
- [ ] 用户授权的聊天/通讯数据
- [ ] App 观测
- [ ] 相册描述

## M7 · Wearable Adapter

- [ ] IMU
- [ ] Mic
- [ ] Camera
- [ ] 生理传感器
- [ ] Display
- [ ] Haptic

## 重要约束

1. 新代码只进入 `aios/01_os/`。
2. `core/` 视为历史验证资产，不再继续扩张。
3. 本地小模型不得承担复杂语义判断；本地只做机械检测、清洗、格式处理和资源控制。
4. 三棵树不再作为底层物理存储架构。
5. 所有 App 共享同一个 AI、同一条 Global Timeline，不建立第二套大脑。
