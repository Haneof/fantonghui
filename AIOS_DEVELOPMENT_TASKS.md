# AIOS Development Task Ledger

> 状态：ACTIVE
> 唯一开发分支：`aios`
> 唯一 OS 主线：`aios/01_os/`
> 唯一有效宪法：`docs/AIOS_Constitution_V1.4-r1.md`
>
> **硬规则：任何代码、Schema、Runtime Contract、架构文档或测试发生修改后，必须同步更新本任务表。任务表记录真实工程状态，不记录计划性假完成。**

## 0. 永久工程规则

1. 只在 `aios` 分支开发。
2. 不恢复已删除的旧 `core/`、旧 Constitution、旧 Runtime 或旧 Schema/Test 作为当前设计。
3. `aios/01_os/` 是唯一 OS 产品实现主线。
4. Observation 是事实入口；Global Timeline 是唯一时间基准。
5. Dimension 是 Timeline 上的动态观察视角/时间曲线，不是静态字段、标签或快照 JSON。
6. User/World Dimensions 与 AI Dimensions 共用唯一 Global Timeline，并行演化。
7. AI Instance 接入后必须首先完成 Identity Bootstrap；这是唯一固定认知入口。
8. Identity 之后不得规定固定 Dimension 阅读顺序；AI 自主选择探索路径。
9. Runtime 提供能力、边界、权限、上下文容量和连续性，不替 AI 写死思维路线。
10. Observation / Evidence / Cognition / Hypothesis / Prediction / Outcome 必须可区分、可追溯、可修正。
11. Simulator 的 Expected Intent 对被测 AI 隐藏。
12. 没有测试/运行证据和 Commit，不得标记任务完成。

## 1. 总体开发路线

```text
P0 架构清场 / 单一真相
 → P1 Observation + Global Timeline
 → P2 Dimension Runtime / Dimension Curve
 → P3 Evidence + Confidence + Provenance
 → P4 Trigger Runtime
 → P5 AI Cognitive Runtime / Identity First
 → P6 Autonomous Context Construction
 → P7 Cognitive Delta + Persistent AI Dimensions
 → P8 Session Handoff + Continuation
 → P9 Help / Action / Silence + Outcome
 → P10 Cognitive Simulator + Trace + Evaluator
 → P11 Cognitive Mechanism Optimization + Regression
 → P12 MODE / Safety / Interaction / Capability
 → P13 PC Simulator → Phone → Wearable
```

## 2. 任务表

| ID | 任务 | 状态 | 验收 |
|---|---|---|---|
| P0-T1 | 删除旧 `core/` 第二套 Runtime | ✅ | `core/` 不存在 |
| P0-T2 | 删除旧 Constitution 与旧架构入口 | ✅ | V1.2/V1.3/V1.4-r0 不再作为当前文件 |
| P0-T3 | 建立唯一任务账本 | ✅ | 本文件 |
| P0-T4 | 删除旧 NEXT_TASK/STATUS/DEVLOG | ✅ | 无旧状态入口 |
| P0-T5 | 删除根目录重复 adapters/schemas/tests | ✅ | 主线只保留 `aios/01_os/` |
| P0-T6 | 删除 archive 中旧 Constitution | ✅ | 不再保留旧宪法副本 |
| P1-T1 | Observation Contract 冻结 | ⬜ | schema + tests |
| P1-T2 | Global Timeline Runtime | ⬜ | 稳定落轴、时间查询 |
| P1-T3 | Timeline Evidence Reference | ⬜ | 事实可回溯来源 |
| P2-T1 | Dimension Registry | ⬜ | 动态创建/停用/查询 |
| P2-T2 | Dimension Point Contract | ⬜ | point 绑定 timeline + evidence |
| P2-T3 | Dimension Curve Runtime | ⬜ | 时间纵向读取/更新/比较 |
| P2-T4 | Cross-Dimension Query | ⬜ | 横向/纵向/跨关系查询 |
| P3-T1 | Evidence Runtime | ⬜ | Source/Evidence/Provenance |
| P3-T2 | Confidence Model | ⬜ | source/evidence/claim 分离 |
| P3-T3 | Outcome Verification | ⬜ | prediction → outcome → confidence |
| P4-T1 | Trigger Contract | ⬜ | 只唤醒、不做复杂判断 |
| P4-T2 | Trigger Runtime | ⬜ | 唤醒 AI Session |
| P5-T1 | AI Session Contract | ⬜ | Session 生命周期 |
| P5-T2 | Identity Bootstrap | ⬜ | 接入第一步强制身份建立 |
| P5-T3 | Cognitive Runtime Shell | ⬜ | wake → identity → cognition → persist |
| P6-T1 | Context Access API | ⬜ | Timeline/Dimension/Evidence 查询 |
| P6-T2 | Autonomous Context Construction | ⬜ | 无固定 Dimension 顺序 |
| P6-T3 | Context Budget / Overflow | ⬜ | 自动 continuation/handoff |
| P7-T1 | Cognitive Delta | ⬜ | 只记录真实认知变化 |
| P7-T2 | AI Dimensions Persistence | ⬜ | AI 理解/关系/策略持续演化 |
| P7-T3 | Open Questions | ⬜ | 未解决问题跨 Session 延续 |
| P8-T1 | Session Handoff | ⬜ | 下一 AI 无需从零重读 |
| P8-T2 | Continuation | ⬜ | Context 满载后连续认知不丢失 |
| P9-T1 | Help/Decision/Action/Silence | ⬜ | 帮助不是普通聊天回复 |
| P9-T2 | Outcome Runtime | ⬜ | 结果回写 Timeline |
| P9-T3 | AI Self Update | ⬜ | 从结果更新认知/策略 |
| P10-T1 | Scenario Format | ⬜ | world data + hidden intent |
| P10-T2 | Structured Cognitive Trace | ⬜ | 可审计实际认知路径，不泄露 CoT |
| P10-T3 | Evaluator | ⬜ | intent/relevance/helpfulness 等评分 |
| P10-T4 | Failure Diagnosis | ⬜ | observation/context/interpretation/mechanism/decision/continuity |
| P11-T1 | Cognitive Mechanism Registry | ⬜ | 机制版本化/实验化 |
| P11-T2 | Optimization Loop | ⬜ | scenario → trace → diagnosis → update → rerun |
| P11-T3 | Regression Suite | ⬜ | 新优化不得破坏旧场景 |
| P12-T1 | MODE Runtime | ⬜ | mode 参与认知但不替代认知 |
| P12-T2 | Personal Safety OS | ⬜ | accident/fall/vitals/nonresponse escalation |
| P12-T3 | Interaction Runtime | ⬜ | vibration/text/voice/bone conduction |
| P12-T4 | Capability / Permission | ⬜ | action 权限和安全边界 |
| P13-T1 | PC Core Simulator Demo | ⬜ | 完整主链路 PC 可运行 |
| P13-T2 | Phone Adapter | ⬜ | 手机成为现实数据源 |
| P13-T3 | Wearable Adapter | ⬜ | 手环作为 AIOS Body 接入 |

## 3. 当前执行任务

**P1-T1：Observation Contract 冻结。**

必须：
- 明确 Observation 与 Event 的关系。
- Observation 只保存事实/来源，不保存 AI 推断。
- 保留后续 Evidence / Provenance 所需信息。
- 为 Global Timeline、Dimension Point 提供稳定输入。

完成顺序：

```text
检查现有 Schema / Runtime
 → 实现
 → 测试
 → 更新本任务表
 → Commit 到 aios
 → 验证 Git 实际结果
```

## 4. 变更记录

### 2026-09-12 · P0 清场
- 删除旧 `core/` 第二套 Runtime。
- 删除 V1.2/V1.3/V1.4-r0 Constitution。
- 删除旧架构入口、旧 NEXT_TASK/STATUS/DEVLOG。
- Commit：`b9424035057c48a3a331e99bbc9527e1659da655`
- 结果：PASS

### 2026-09-12 · P0 文档治理
- `docs/README.md`、`docs/00_START_HERE.md`、`AIOS_PROJECT_EXECUTION_MASTER_V1.0.md` 对齐 V1.4-r1。
- Commit：`12b666ba090b0daf08413c0880409e48b574c750`、`50c1cd2a5d157a7b938be8252d06f36b6db1258e`、`91d48b8b3bafbbf415f40064ed0779a65516a3e7`
- 结果：PASS

### 2026-09-12 · P0 任务账本
- 建立 `AIOS_DEVELOPMENT_TASKS.md`，定义 P0–P13 路线和验收规则。
- Commit：`319412926df4e8fca436343ad3b3323b32100c35`

### 2026-09-12 · P0 根目录重复资产清理
- 删除根 `adapters/`、`schemas/`、`tests/`；其中根 schemas 明确包含旧 cognition/decision/memory/growth/relationship 模型。
- Commit：`e765426ca68352b9b51d0a976b59f30ea0720680`
- 结果：PASS

### 2026-09-12 · P0 最终旧宪法清理
- 删除 `archive/AIOS_Constitution_V1.2.md`，确保仓库当前文件树不再保留旧 Constitution 副本。
- Commit：`ea5d9e8b65052e3a8f3092574a6d0b867216041c`
- 结果：PASS

## 5. Agent 强制执行规则

```text
读取 AIOS_DEVELOPMENT_TASKS.md
 ↓
读取 docs/AIOS_Constitution_V1.4-r1.md
 ↓
读取当前任务相关 Contract / Schema
 ↓
检查实际代码
 ↓
只实现当前任务
 ↓
测试 / 验收
 ↓
更新 AIOS_DEVELOPMENT_TASKS.md
 ↓
Commit 到 aios
 ↓
重新检查实际 Git 状态
```

Agent 不得根据聊天历史猜任务，不得从 Git 历史恢复已删除架构，不得把计划当完成，不得跳过任务表更新。
