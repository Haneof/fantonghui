# AIOS 现状架构测绘报告（AS-IS）

> **文件编号**：ARCH-AS-IS-001
> **测绘日期**：2026-09-18
> **性质**：NON-NORMATIVE · 事实测绘，不含主张、不改任何文件
> **方法**：从 `src/` 实际代码与现行法统文本机械扫描得出，非从设计文档转抄

---

## 0. 为什么先做这张图

目标架构不能凭空画。在决定"应该长什么样"之前，必须先看见"现在长什么样"。
本报告只陈述可复现的事实，每条结论都附扫描口径，供复核。

---

## 1. 判词摘要

| 编号 | 事实 | 性质 |
|---|---|---|
| F-1 | 宪法第 108 条自称"至少 14 个组件"，模块边界表**只定义了 8 个**（C02/C03/C05/C06/C07/C08/C09/C10） | 架构缺口 |
| F-2 | **C01、C04、C11、C12、C13、C14 在宪法中无任何定义**；其中 C01 是全系统唯一数据入口、C13 是唯一模型出口 | 架构缺口（要害） |
| F-3 | ADJ-010（ACTIVE）裁定"以 R4 §2.1 的 **C01~C16 全表**为唯一账本"，但该文件 §2.1 实际标题为 **C01–C15**，表中**无 C16** | 生效裁决指向不存在的基准 |
| F-4 | ADJ-010 指向的 R4 设计书状态为 **CANDIDATE（未签核）** | ACTIVE 依赖 CANDIDATE |
| F-5 | 代码 26 个包按功能名组织，与 C01~C16 编号**无机械对应**；ADJ-010 要求的"映射哈希不一致即 CI 红"当前不可执行 | 法统与代码脱钩 |
| F-6 | `tasks/`、`actions/`、`workspace/` 三个包为 **1 行占位空壳**，但 Task 是宪法第 60 条"一等公民" | 宪法与实现落差 |
| F-7 | Task 调度行为实际散落在 `scheduler/conditional_engine.py` 与 `tools/lightweight_condition_evaluator.py` | 职责错位 |
| F-8 | `ingest → bench`：生产代码依赖测试基准包 | 依赖方向违规 |

---

## 2. 代码实际拓扑（扫描 `src/`）

### 2.1 顶层入口

| 入口 | 文件 | 说明 |
|---|---|---|
| `ai_worker` | `cognitive_executor.py` / `cockpit_executor.py` | 认知执行主路径；registry §6 裁定前者为新主路径，后者为 Legacy |
| `console` | `app_manifest.py` / `wearable_ui/` | 交互端口 |
| `evaluator` | `audit_evaluator_entry.py` | 评估入口 |
| `simulator` | `life_simulator_entry.py` | 仿真入口 |

### 2.2 `aios_core` 包规模（按代码行降序）

| 包 | 文件 | 行数 | 推定职责 |
|---|---:|---:|---|
| simulation | 9 | 5903 | 仿真与虚拟人生 |
| bench | 10 | 5299 | 基准与压测 |
| tools | 10 | 3608 | 工具集（含条件求值器） |
| cognition | 14 | 3177 | 认知、维度引擎 |
| query | 7 | 3037 | 检索与召回 |
| world | 4 | 2941 | 世界读写面 |
| storage | 3 | 2029 | 存储与版本 |
| ingest | 4 | 1971 | 接入与清洗 |
| runtime | 9 | 1781 | 运行时 |
| wake | 5 | 1677 | 唤醒 |
| contracts | 11 | 1665 | 契约对象（72 个 class） |
| perception | 3 | 1431 | 感知 |
| scheduler | 1 | 1421 | 调度（含条件引擎） |
| summaries | 3 | 1046 | 多尺度总结 |
| cockpit | 3 | 925 | 驾驶舱装配 |
| dimensions | 2 | 873 | 维度注册 |
| operations | 2 | 850 | 操作经验 |
| wearable | 3 | 206 | 穿戴 |
| communication | 3 | 191 | 沟通经验 |
| curves | 2 | 181 | 维度曲线 |
| narrative | 2 | 171 | 叙事分段 |
| dependency | 2 | 142 | 依赖图 |
| services | 2 | 138 | 状态机 |
| **workspace** | 1 | **1** | **空壳占位** |
| **tasks** | 1 | **1** | **空壳占位** |
| **actions** | 1 | **1** | **空壳占位** |

> 注：`simulation` + `bench` 合计 11202 行，占比最大的两个包均为**验证设施**而非产品本体。

### 2.3 包间依赖与核心度

被依赖次数（越高越处于底层）：

```
contracts  22   ← 绝对核心，所有包共用
storage     9
query       8
errors      6
world       4
tools       4
cockpit     3   scheduler 3   cognition 3   services 3
dimensions  2   ingest    2
```

**依赖方向异常**：

- `ingest → bench`：产品代码依赖测试基准包（F-8）
- `perception → cognition`、`scheduler → cockpit`：上下层交叉，需在 TO-BE 中裁定方向

---

## 3. 22 个一等对象：契约 vs 行为

**契约层完备**：宪法第 71 条的 22 个对象，全部在 `contracts/models.py` 有定义（`Entity` 额外出现在 `cognition/dimension_engine.py`）。

**行为层缺口**：

| 对象 | 契约 | 行为归属 | 问题 |
|---|---|---|---|
| Task | ✅ models.py | `scheduler/` + `tools/` | `tasks/` 包为空壳（F-6/F-7） |
| Action / Outcome | ✅ models.py | 无独立包 | `actions/` 为空壳 |
| 工作台接口 | — | `cockpit/` + `ai_worker/` | `workspace/` 为空壳 |

> 结论：**对象定义清楚，对象的"生命周期由谁负责"不清楚**。这是缺架构层的直接症状——契约可以逐个冻结，但职责归属必须由架构统一裁定。

---

## 4. 模块编号体系的三套并存账本

| 账本 | 来源 | 状态 | 覆盖范围 |
|---|---|---|---|
| 宪法第 108 条边界表 | `AIOS核心系统宪法v3.0.md` | ACTIVE | **仅 8 个**：C02/03/05/06/07/08/09/10 |
| R4 设计书 §2.1 | `AIOS_Core_工程重构与任务拆分设计书_R4_首席架构师版.md` | **CANDIDATE** | C01–C15（**无 C16**） |
| ADJ-010 裁决 | `v3.0.1_规范裁决集` | ACTIVE | 宣称 **C01~C16**，指向上一行 |
| 实际代码 | `src/aios_core/` | 运行中 | 26 个功能名包，**无 C 编号** |

**冲突链**：ACTIVE 的 ADJ-010 → 指向 CANDIDATE 的 R4 → 引用了 R4 里不存在的 C16 → 而代码用的是第四套命名。

这是"东一个宪法西一个宪法"在模块层面的精确形态。

---

## 5. 系统边界：当前未被完整定义

宪法第四条确立最高目标为"帮助用户"，但**"帮助"如何离开系统**从未被完整枚举：

- 第 98 条之一定义了手环 FSM（震动/骨传导/屏幕）
- 第 85 条定义了 1 秒首字延迟
- registry §6 第 5 条定义了 P0 首个硬件安全动作

以上均为**局部输出面**。全系统的输入源清单、输出面清单、明确不做的事，**没有任何单一文件完整定义**。

> 输出面不定，架构无法收敛——因为无法判断一个模块是否必要。

---

## 6. 本报告不做的事

1. 不提出目标架构（那是 TO-BE 的任务）
2. 不修改任何现有文件
3. 不裁决上述冲突——冲突的裁决权属于治理平面与项目所有者

---

## 附：复现口径

| 事实 | 复现命令 |
|---|---|
| F-1/F-2 | `sed -n '/\*\*Core 模块边界划分\*\*/,/架构概念映射表/p' docs/constitution/AIOS核心系统宪法v3.0.md \| grep -c "^\| C"` |
| F-3 | `sed -n '59,62p' AIOS_Core_工程重构与任务拆分设计书_R4_首席架构师版.md` |
| F-6 | `cat src/aios_core/{tasks,actions,workspace}/*.py` |
| F-8 | 扫描 `from aios_core.X` 跨包引用 |
| §2.2 | 按包统计 `*.py` 行数 |
| §3 | 对 22 个对象名执行 `grep -rl "class <Name>\b" src/` |
