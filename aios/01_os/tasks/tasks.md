# AIOS OS 当前任务看板（V1.4）

> 当前有效架构：V1.4-r0。
> 旧 M0-M3 服务拆分和三棵树任务不再作为新开发依据。

## P0 — 架构迁移（当前最高优先级）

| ID | 任务 | 状态 |
|---|---|---|
| P0-01 | Observation Contract 落地 | ⬜ |
| P0-02 | Global Timeline 落地 | ⬜ |
| P0-03 | Dimension Registry + Curve Runtime | ⬜ |
| P0-04 | Trigger Runtime 纯机械化 | ⬜ |
| P0-05 | AI Session Contract | ⬜ |
| P0-06 | Inference Event + provenance | ⬜ |
| P0-07 | Outcome / AI Self Update | ⬜ |
| P0-08 | UI Interaction Contract | ⬜ |

## P1 — 旧代码处理

| ID | 任务 | 状态 |
|---|---|---|
| P1-01 | 盘点 `core/` 依赖 | ⬜ |
| P1-02 | 可复用算法迁移到 `aios/01_os/` | ⬜ |
| P1-03 | 旧 Runtime 标记兼容/冻结 | ⬜ |
| P1-04 | 删除没有引用的旧代码 | ⬜ |
| P1-05 | 旧测试迁移为 V1.4 测试 | ⬜ |

## P2 — Simulator

- [ ] Observation 多模态输入
- [ ] Timeline 回放
- [ ] Dimension 曲线
- [ ] Trigger
- [ ] AI Session Mock
- [ ] Inference Event
- [ ] Help / Silence
- [ ] Action / Outcome

## P3 — 3D / UI

- [ ] 3D Body
- [ ] UI State
- [ ] Gesture Event
- [ ] Haptic / Voice / Display
- [ ] Mock Runtime 驱动

## P4 — Phone Adapter

- [ ] 通知
- [ ] 日历
- [ ] 位置
- [ ] 授权聊天/通讯数据
- [ ] App 观测
- [ ] 相册描述

## P5 — Wearable Adapter

- [ ] IMU
- [ ] Mic
- [ ] Camera
- [ ] 生理传感器
- [ ] Display
- [ ] Haptic

## 开发纪律

1. 新代码只进入 `aios/01_os/`。
2. 每项任务先定义 Contract，再写代码。
3. Agent 的“完成报告”不等于验收；必须有文件事实、测试和原始运行结果。
4. 不允许为了让旧测试通过而恢复已经被 V1.4 废止的架构。
