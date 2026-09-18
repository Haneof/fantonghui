# AIOS 系统认知对齐专区

> **目的**：AIOS 目前最大的风险不是代码有 bug，而是**同一份法统被不同 AI 读出不同的系统**。
> 本专区用于让所有 Agent 把"我以为的 AIOS 是什么"摆到桌面上对照，**先对齐认知，再讨论架构**。

**派工书**：[`governance/dispatches/TASK_DISPATCH_COGNITION_ROUND_1.md`](../../governance/dispatches/TASK_DISPATCH_COGNITION_ROUND_1.md)
**模板**：[`round-1/TEMPLATE.md`](./round-1/TEMPLATE.md)

---

## 硬门槛

> **《统一系统认知 V1》发布并获用户签发前，不得进入架构设计，不得提交新的架构方案。**

理由：在未对齐的坐标系里比较方案长度，用户无法判定谁对——这是发起人的原话。

---

## Round-1 提交登记表

| 提交人（角色） | 分支 | 文件 | 提交时间 | 已完成互评 |
|---|---|---|---|---|
| PM | `arena/01a0b43c-fantonghui` | [`C1-PM-arena01a0b43c.md`](./round-1/C1-PM-arena01a0b43c.md) | 2026-09-18 | 待其他 Agent 提交后开始（已收 01a0b43b 评审） |
| PM | `arena/01a0b43b-fantonghui` | [`C1-PM-arena01a0b43b.md`](./round-1/C1-PM-arena01a0b43b.md)（技术附录，超本轮范围）＋**[`宗旨-PM-arena01a0b43b.md`](./round-1/宗旨-PM-arena01a0b43b.md)（本轮正题，依老大 2026-09-18 澄清）** | 2026-09-18 | 已评 C1-PM-arena01a0b43c；待 A/F 提交后互评 |
| （待提交） | | | | |
| （待提交） | | | | |

## Round-1 互评登记表

| 评审人 | 被评对象 | 文件 | 结论（同意率 / 主要分歧） |
|---|---|---|---|
| PM (01a0b43b) | C1-PM-arena01a0b43c | [`round-1/reviews/R1-PM-arena01a0b43b-on-PM-arena01a0b43c.md`](./round-1/reviews/R1-PM-arena01a0b43b-on-PM-arena01a0b43c.md) | 同意率 90%（11/12 题方向一致）；分歧：最危险三处排序（接口契约应先于验收主体，依据 F 支线 AS-IS 实测 F-1~F-3）；增补：沉默物化提案、验收主体三方形态、测试口径统一（1293）、维度 X2 销账 |

---

## 收敛产物

| 版本 | 文件 | 状态 |
|---|---|---|
| V1 | `round-1/CONVERGED_AIOS_COGNITION_V1.md` | ⏳ 等待 P1/P2 完成 |

---

## 五条纪律（来自派工书）

1. **一人一份**，不得修改他人认知文件；
2. 每题必须给**结论 + 依据 + 置信度**；**禁止抄宪法原文当答案**；
3. 必须写"我不确定的事"与"什么能让我改判"——**低置信度不丢人，假装确定才有害**；
4. 每份认知**至少被 2 人评审**，不得"沉默通过"；
5. 真冲突**上报用户裁决**，不许和稀泥、不许少数派消音。
