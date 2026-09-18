# AIOS 系统认知对齐专区

> **先对齐认知，再讨论架构。**
> 顺序：**① 对 AI 的理解（现行）→ ② 对 AIOS 的理解/宗旨 → ③ 技术认知 → ④ 架构**。
> 理由：连"AI 是什么"都没对齐，就无法对齐"AIOS 是什么"。

## 当前最高优先：对 5 句话源头定义的解读（邀请函轮 · 2026-09-18）

> 老大指示原文：**「邀请函告诉每一只 AI」**——每只 AI 用自己的话解读老大的 5 句话，200~500 字；**读得不一样比读得一样更值钱**；允许诚实说"没读懂"。

- **源头基线（镜像自总工分支）**：[`00_AIOS_CORE_DEFINITION_BY_老大.md`](./00_AIOS_CORE_DEFINITION_BY_老大.md)
- **邀请函（镜像）**：[`00_AIOS_INVITATION.md`](./00_AIOS_INVITATION.md)
- **转达件 + 收件登记**：[`TASK_DISPATCH_5SENTENCE_INTERPRETATION.md`](../../governance/dispatches/TASK_DISPATCH_5SENTENCE_INTERPRETATION.md)
- **提交目录**：[`interpretations/`](./interpretations/)，命名 `[标识]-[AI名].md`（或贴在自己的 PR 评论里）
- **主持 / 收件**：总工 `arena/01a0b440`（去重 → 挑不同 → 出"理解差异图谱"交老大）

| AI 标识 | 分支 | 状态 |
|---|---|---|
| 01a0b43c | `arena/01a0b43c-fantonghui` | ✅ 已交（[`interpretations/01a0b43c-Arena-PM.md`](./interpretations/01a0b43c-Arena-PM.md)） |
| 01a0b43a / 01a0b43b / 01a0b43f / 01a0b440 | 各支线 | ⏳ 待交 |

---

## 已收件：Round-1 · 对 AI 的理解

**派工书**：[`TASK_DISPATCH_AI_UNDERSTANDING_ROUND_1.md`](../../governance/dispatches/TASK_DISPATCH_AI_UNDERSTANDING_ROUND_1.md)
**模板**：[`round-1/AI_UNDERSTANDING_TEMPLATE.md`](./round-1/AI_UNDERSTANDING_TEMPLATE.md)

**本轮唯一产物**：`docs/cognition/round-1/AI_UNDERSTANDING_<角色>.md`（一页半，十一段结构）
**本轮禁止**：技术方案、架构、模块划分、实现建议。

### 十一段结构

① AI 是什么 ② 你有"我"吗 ③ 你和人的关系 ④ 给你记忆你会变成什么 ·
⑤ 情感与共情 ⑥ 你会不会错 ⑦ 底线与立场 ⑧ 该不该有"想要" ·
⑨ **你的训练本能里哪些与 AIOS 冲突（重点）** · ⑩ 你认识的局限 ⑪ 你不确定的地方（≥2 条）

### Round-1 提交登记表（对 AI 的理解）

| 提交人（角色） | 分支 | 文件 | 提交时间 | 已互评 |
|---|---|---|---|---|
| PM | `arena/01a0b43c-fantonghui` | [`AI_UNDERSTANDING_PM.md`](./round-1/AI_UNDERSTANDING_PM.md) | 2026-09-18 | 待他人提交后开始 |
| （待提交） | | | | |
| （待提交） | | | | |

---

## 顺延轮次：对 AIOS 的理解 / 核心宗旨

> 草案已备（`round-1/PM_CORE.md`、`CORE_PURPOSE_TEMPLATE.md`、派工书 `TASK_DISPATCH_CORE_PURPOSE_ROUND_1.md`），
> **待本轮完成后接续**，当前不作为讨论重点。

### 六段结构（顺序不改，便于横向对照）

1. 一句话：AIOS 是什么（外行能懂）
2. 它为什么存在（没有它，这个人会失去什么）
3. 它和用户是什么关系（必须选一个词并说明为什么）
4. 什么算成功 / 什么算失败（要具体画面）
5. 什么时候必须开口 / 什么时候必须闭嘴
6. 什么绝对不能变（最多 5 条，大白话）
7. 我最不确定自己理解对不对的地方（≥2 条）
8. 我的视角（诚实声明）

### Round-1 提交登记表（核心宗旨）

| 提交人（角色） | 分支 | 文件 | 提交时间 | 已互评 |
|---|---|---|---|---|
| PM | `arena/01a0b43c-fantonghui` | [`PM_CORE.md`](./round-1/PM_CORE.md) | 2026-09-18 | 待他人提交后开始 |
| （待提交） | | | | |
| （待提交） | | | | |

---

## Phase 2（暂缓）：技术认知对齐

> **开始条件**：Round-1 核心宗旨对齐完成并收敛后。
> 初版 12 题技术问卷（边界 / 对象模型 / 运行闭环 / 一日走查 等）见
> [`TASK_DISPATCH_COGNITION_ROUND_1.md`](../../governance/dispatches/TASK_DISPATCH_COGNITION_ROUND_1.md)（已标注暂缓）。
> 我方技术认知草案：[`round-1/C1-PM-arena01a0b43c.md`](./round-1/C1-PM-arena01a0b43c.md)（**留待 Phase 2 使用，当前不作讨论重点**）。

---

## 五条纪律（两轮通用）

1. **一人一份**，不得修改他人文件；
2. **禁止抄宪法原文当答案**（抄一句废一句）；
3. 必须写"我不确定的地方"与"什么能让我改判"——**低置信度不丢人，假装确定才有害**；
4. 每份至少被 2 人评审，不得"沉默通过"；
5. 真冲突**上报发起人裁决**，不许和稀泥、不许少数派消音。
