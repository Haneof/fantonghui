# AIOS Development Task Ledger

> 状态：ACTIVE
> 唯一开发分支：`aios`
> 唯一 OS 主线：`aios/01_os/`
> 唯一有效宪法：`docs/AIOS_Constitution_V1.4-r1.md`
>
> **硬规则：任何代码、Schema、Runtime Contract、架构文档或测试发生修改后，必须同步更新本任务表。任务表记录当前真实工程状态，不记录计划性假完成。**

## 0. 开发总原则

1. 只在 `aios` 分支开发；不得修改其他分支。
2. 不恢复已删除的旧 `core/`、旧 Constitution 或旧架构文档。
3. 不建立第二套 OS Runtime。
4. Observation 是底层事实入口；Global Timeline 是唯一时间基准。
5. Dimension 是基于 Global Timeline 的动态观察视角/时间曲线，不是静态字段、标签表或当前快照 JSON。
6. User/World Dimensions 与 AI Dimensions 共用同一个 Global Timeline，并行演化。
7. Identity First 是唯一规定死的认知入口：AI Instance 接入后必须先建立自身身份。
8. Identity Bootstrap 之后禁止硬编码 Dimension 阅读顺序；由 AI 自主决定探索路径。
9. Runtime 负责提供能力、边界、连续性和资源约束；不替 AI 写死思考路线。
10. 事实、证据、认知、假设、预测、结果必须可区分、可追溯、可修正。
11. Simulator 的 Expected Intent 对被测 AI 隐藏；不得把答案写进生产 Runtime。
12. 每个完成任务必须有自动化测试或明确的可验证证据。

---

# 1. 总体开发路线

```text
P0  架构清场 / 单一真相
 ↓
P1  Observation + Global Timeline
 ↓
P2  Dimension Runtime / Dimension Curve
 ↓
P3  Evidence + Confidence + Provenance
 ↓
P4  Trigger Runtime
 ↓
P5  AI Cognitive Runtime / Identity First
 ↓
P6  Autonomous Context Construction
 ↓
P7  Cognitive Delta + Persistent AI Dimensions
 ↓
P8  Session Handoff + Continuation
 ↓
P9  Help / Action / Silence + Outcome
 ↓
P10 Cognitive Simulator + Trace + Evaluator
 ↓
P11 Cognitive Mechanism Optimization + Regression
 ↓
P12 MODE / Safety / Interaction / Capability
 ↓
P13 PC Simulator → Phone → Wearable integration
```

**原则：先把“AI 如何拥有连续世界”做实，再把“AI 如何像一个懂人的人一样行动”做实，最后才扩展硬件和应用。**

---

# 2. 当前状态

| ID | 阶段 | 任务 | 状态 | 验收目标 |
|---|---|---|---|---|
| P0-T1 | P0 | 删除旧 `core/` 第二套 Runtime | ✅ 完成 | `core/` 不再存在 |
| P0-T2 | P0 | 删除旧 Constitution / 旧架构入口 | ✅ 完成 | V1.2/V1.3/V1.4-r0 不再作为仓库入口 |
| P0-T3 | P0 | 建立唯一开发任务表 | ✅ 完成 | 本文件成为唯一任务状态账本 |
| P0-T4 | P0 | 清理旧 NEXT_TASK / STATUS / DEVLOG 入口 | ✅ 完成 | 不再有旧状态表误导 Agent |
| P0-T5 | P0 | 删除根目录重复旧 adapters/schemas/tests | ✅ 完成 | Runtime/Schema/Test 只保留 `aios/01_os/` 主线版本 |
| P1-T1 | P1 | Observation Contract 冻结 | ⬜ 待开发 | schema + tests |
| P1-T2 | P1 | Global Timeline Runtime | ⬜ 待开发 | Event/Observation 按时间稳定落轴、可查询 |
| P1-T3 | P1 | Timeline Evidence Reference | ⬜ 待开发 | 每个事实可回溯来源 |
| P2-T1 | P2 | Dimension Registry | ⬜ 待开发 | 动态创建/查询/停用 Dimension |
| P2-T2 | P2 | Dimension Point Contract | ⬜ 待开发 | point 必须绑定 timeline + evidence/provenance |
| P2-T3 | P2 | Dimension Curve Runtime | ⬜ 待开发 | 沿时间轴读取、更新、比较、查询曲线 |
| P2-T4 | P2 | Cross-Dimension Query | ⬜ 待开发 | 横向/纵向/跨关系查询 |
| P3-T1 | P3 | Evidence Runtime | ⬜ 待开发 | Source/Evidence/Provenance 可追溯 |
| P3-T2 | P3 | Confidence Model | ⬜ 待开发 | source/evidence/claim confidence 分离 |
| P3-T3 | P3 | Outcome Verification | ⬜ 待开发 | prediction → outcome → confidence update |
| P4-T1 | P4 | Trigger Contract | ⬜ 待开发 | Trigger 只负责唤醒，不负责语义判断 |
| P4-T2 | P4 | Trigger Runtime | ⬜ 待开发 | Event/时间/状态触发 AI Session |
| P5-T1 | P5 | AI Session Contract | ⬜ 待开发 | Session 生命周期可验证 |
| P5-T2 | P5 | Identity Bootstrap | ⬜ 待开发 | AI 接入第一步强制建立身份 |
| P5-T3 | P5 | Cognitive Runtime Shell | ⬜ 待开发 | wake → identity → cognition → persist |
| P6-T1 | P6 | Context Access API | ⬜ 待开发 | AI 可自主查询 Timeline/Dimensions/Evidence |
| P6-T2 | P6 | Autonomous Context Construction | ⬜ 待开发 | 禁止固定 Dimension 阅读顺序 |
| P6-T3 | P6 | Context Budget / Overflow | ⬜ 待开发 | 超限自动 continuation/handoff |
| P7-T1 | P7 | Cognitive Delta | ⬜ 待开发 | 只记录本 Session 真正发生的认知变化 |
| P7-T2 | P7 | AI Dimensions Persistence | ⬜ 待开发 | AI 自身理解/关系/策略等可持续演化 |
| P7-T3 | P7 | Open Questions | ⬜ 待开发 | 未解决认知缺口跨 Session 延续 |
| P8-T1 | P8 | Session Handoff | ⬜ 待开发 | 下一 AI 无需从零重读历史 |
| P8-T2 | P8 | Continuation | ⬜ 待开发 | Context 满载后连续认知不丢失 |
| P9-T1 | P9 | Help / Decision / Action / Silence Contract | ⬜ 待开发 | 帮助不是普通聊天回复 |
| P9-T2 | P9 | Outcome Runtime | ⬜ 待开发 | 行动结果回写 Global Timeline |
| P9-T3 | P9 | AI Self Update | ⬜ 待开发 | 从结果更新 AI 认知/策略 |
| P10-T1 | P10 | Scenario Format | ⬜ 待开发 | 世界数据 + hidden expected intent |
| P10-T2 | P10 | Structured Cognitive Trace | ⬜ 待开发 | 可重建 AI 实际认知路径，不泄露 CoT |
| P10-T3 | P10 | Evaluator | ⬜ 待开发 | intent hit / relevance / helpfulness 等评分 |
| P10-T4 | P10 | Failure Diagnosis | ⬜ 待开发 | observation/context/interpretation/mechanism/decision/continuity 分类 |
| P11-T1 | P11 | Cognitive Mechanism Registry | ⬜ 待开发 | 机制可版本化、可实验 |
| P11-T2 | P11 | Optimization Loop | ⬜ 待开发 | scenario → trace → diagnosis → update → rerun |
| P11-T3 | P11 | Regression Suite | ⬜ 待开发 | 新优化不得破坏旧场景 |
| P12-T1 | P12 | MODE Runtime | ⬜ 待开发 | context mode 参与认知但不替代认知 |
| P12-T2 | P12 | Personal Safety OS | ⬜ 待开发 | accident/fall/vitals/nonresponse escalation |
| P12-T3 | P12 | Interaction Runtime | ⬜ 待开发 | vibration/text/voice/bone conduction semantics |
| P12-T4 | P12 | Capability / Permission | ⬜ 待开发 | action 权限与安全边界 |
| P13-T1 | P13 | PC Core Simulator Demo | ⬜ 待开发 | 完整主链路可在 PC 独立运行 |
| P13-T2 | P13 | Phone Adapter | ⬜ 待开发 | 手机成为主要现实数据源之一 |
| P13-T3 | P13 | Wearable Adapter | ⬜ 待开发 | 手环作为 AIOS Body 接入 |

---

# 3. 当前执行任务

**下一任务：P1-T1 Observation Contract 冻结。**

要求：
- 不重新定义 Event → World 的旧路线。
- 明确 Observation 与 Event 的关系。
- Observation 必须保留 evidence/provenance 所需信息。
- 不把 AI 推断写进 Observation。
- 为后续 Global Timeline 与 Dimension Point 提供稳定输入。

完成后必须：
1. 修改 Schema / Runtime / Tests。
2. 运行对应测试。
3. 更新本文件的状态、实际变更文件、测试结果。
4. 再开始下一个任务。

---

# 4. 每次变更记录

### 2026-09-12 · P0 清场

- **变更**：删除旧 `core/` 第二套 Runtime；删除 V1.2/V1.3/V1.4-r0 Constitution；删除旧架构入口文档与旧 `NEXT_TASK.md` / `STATUS.md` / `DEVLOG.md`。
- **保留**：`docs/AIOS_Constitution_V1.4-r1.md` 作为唯一有效宪法；`aios/01_os/` 作为唯一 OS 实现主线。
- **主要 Commit**：`b9424035057c48a3a331e99bbc9527e1659da655`
- **结果**：PASS

### 2026-09-12 · P0 文档治理对齐

- **变更**：`docs/README.md`、`docs/00_START_HERE.md`、`AIOS_PROJECT_EXECUTION_MASTER_V1.0.md` 全部切换到 V1.4-r1，并统一指向本任务表。
- **结果**：PASS
- **相关 Commit**：`12b666ba090b0daf08413c0880409e48b574c750`、`50c1cd2a5d157a7b938be8252d06f36b6db1258e`、`91d48b8b3bafbbf415f40064ed0779a65516a3e7`

### 2026-09-12 · P0 任务账本建立

- **变更**：建立 `AIOS_DEVELOPMENT_TASKS.md`，定义 P0–P13 开发路线、任务状态、验收规则和变更记录规则。
- **Commit**：`319412926df4e8fca436343ad3b3323b32100c35`
- **结果**：PASS

### 2026-09-12 · P0 根目录重复资产清理

- **变更**：删除根目录旧 `adapters/`、`schemas/`、`tests/`。这些内容与 `aios/01_os/` 中的主线资产重复，其中根 `schemas/` 仍包含旧 `cognition/decision/memory/growth/relationship` 三棵树模型，容易诱导 Agent 回到旧架构。
- **Commit**：`e765426ca68352b9b51d0a976b59f30ea0720680`
- **结果**：PASS（`aios` 已更新）

---

# 5. Agent 执行规则

Agent 接入仓库后必须按以下顺序：

```text
读取 AIOS_DEVELOPMENT_TASKS.md
 ↓
读取 docs/AIOS_Constitution_V1.4-r1.md
 ↓
读取当前任务涉及的 Runtime Contract / Schema
 ↓
检查实际代码
 ↓
实现当前唯一任务
 ↓
测试
 ↓
更新 AIOS_DEVELOPMENT_TASKS.md
 ↓
提交到 aios
```

Agent 不得根据聊天历史猜测当前任务，也不得从 Git 历史恢复已经删除的架构作为现行设计。
