# AIOS Repository Layout V0.2 —— 目录即架构（V0.1-r1 快照见 `archive/docs_v0.1_snapshot/`）

> 本版按宪法 V1.4-r0 §12.4 与本仓实际形态重写。**核心裁定：目录结构就是架构声明——放错目录 = 架构错误。**
> V0.1 提出的 `aios-core/core/{world,event,...}` 布局**作废**（曾登记为 STATUS 冲突 1，2026-09-11 结案）。

## 1. 三条目录铁律

1. **规范文档只有一套**：全部放 `docs/`，编号 00-09 保留，不在根目录再放副本（根目录那套 V0.1 副本已归档）。
2. **实现只有一条线**：所有代码在 `aios/01_os/code/`。任何新 Runtime 只能有一个 Owner，**不得**在别处复制实现（§12.4）。
3. **归档区只读**：`archive/**` 不得写入新代码、不得被 import。它是取证区（旧线 192 项测试与 V1.2 文档快照在里面，仍可独立复现）。

## 2. 实际布局（与五层架构的映射）

```
fantonghui/
├─ STATUS.md                  唯一状态源（V1.4 迁移看板 14 项 + 结案记录）
├─ NEXT_TASK.md               施工单（当前任务 A-E，含 F/G/H）
├─ DEVLOG.md                  执行日志（原始输出、失败项、未完成项）
├─ schemas/                   Canonical 03 的逐字节参照物（非实现，勿 import）
├─ docs/                      12 份规范 + V1.4 三份宪法 + 一致性索引
│  ├─ 00..09                  WHAT/HOW（02/04 的 VOID 条款见下）
│  ├─ AIOS_Constitution_V1.4-r0.md   ← 最高权威（2026-09-11 批准生效）
│  ├─ AIOS_Constitution_V1.3-r0.md / V1.2-r1.md   历史版本，保留不改
│  └─ README_V14_CONFORMANCE.md      00-09 条款级 VOID/KEEP/REVISE 索引
│
├─ aios/
│  ├─ 01_os/                  ★ 系统本体（= L0-L4 全部落这里）
│  │  ├─ code/
│  │  │  ├─ aiosd/            L0 进程监督（init 角色）
│  │  │  ├─ bus/              L0 系统总线
│  │  │  ├─ aios_sdk/         L4 App 接入面（须补 call()）
│  │  │  ├─ services/         L1-L3 十五个服务 + README_V1.4_BOUNDARY.md（逐服务边界标注）
│  │  │  ├─ api_pool/         云端大模型通道（唯一合法的语义算力出口）
│  │  │  ├─ simulator/        L1 数据源之一（模拟器，非产品）
│  │  │  ├─ tests/            验收裁判 + FROZEN.md（§4.4/§12.8 冻结件标注）
│  │  │  ├─ bench/            验收夹具（如 teaching_fit_v0.jsonl）
│  │  │  ├─ aios_console.py   只读 Dev 面板（§8 风险二的裁决产物，非产品 UI）
│  │  │  ├─ services.json     服务注册表（未来 app 注册表的雏形）
│  │  │  └─ run/              运行态（gitignore；基准证据例外保留跟踪）
│  │  ├─ schemas/             主线在用的三件套（运行时读这里）
│  │  ├─ docs/                实现层设计文档（10_AIOS_SYSCALLS_V0.md 等）
│  │  ├─ tasks/               plans/ 任务书 · logs/ 工作日志 · contracts*.md 冻结契约
│  │  └─ roadmap.md           里程碑
│  ├─ 02_hardware/            L1 设备适配（手环/手机/传感器）——空壳，按计划靠后
│  ├─ 03_ui/                  L4 UI（shell/display/voice/interaction/settings）——空壳，契约先行
│  └─ 04_apps/                L4 应用（education/social/work/health/entertainment）——空壳
│
└─ archive/                   只读取证区（legacy_core_simulator/ · superseded_docs/ · reports_v1.2/ · docs_v0.1_snapshot/）
```

## 3. 新增代码的落位判定（照此表放，不放就退回）

| 要做的事 | 落位 | 不得落在 |
|---|---|---|
| Observation Store / Global Timeline | `code/services/`（复用 hublinkd 持久队列）或新 `observedd.py` | 根目录、`02_hardware`、App 内 |
| 维度曲线与注册表 | 新 `code/services/dimensiond.py` + 契约进 `01_os/docs/` | `04_apps/education`（App 不许自建画像） |
| 六类 Trigger | `code/services/attentiond.py` 重写（§4.3） | 新建第二个触发服务 |
| 设置面 | `code/services/settingsd.py` + 呈现层进 `03_ui/settings`（后者冻结） | 各服务私有的 `*.json` 配置 |
| 教育 App | 将来 `04_apps/education/`，且只调 Syscall 表 22 条 | 任何 `code/services/` 下的"教育逻辑" |
| 验收测试 | `code/tests/test_sX_tY.py` | 散在 `run/` 或文档里的"手工确认" |
| 基准夹具 | `code/bench/` | `run/`（运行态目录，随时被覆盖） |

## 4. 忽略与体积规则

- `run/` 下运行态**不入库**（`aios/.gitignore` 已钉：`**/run/*.json` + bench1k 派生物），但**基准证据**（`questions.json`、`results*.jsonl`、`benchmark_*.json`、`gate_rules_result.json`）保持跟踪——它们是可复现结论的唯一凭据。
- 数据集与模型权重不入库（31,399 条/90 天脚本可再生；`.gguf` 走外部存储）。
- `*.db`/`*.log`/`__pycache__`/`var/` 一律不入库。

## 5. 与旧文档的关系

`docs/02` 与 `docs/04` 中"Relevance Runtime / Attention+Lease 三运行时并列 / Wake 四级 / 感知层输出 Semantic Event"已被 V1.4 判 **VOID**（逐条见 `README_V14_CONFORMANCE.md`）；`aios/01_os/docs/OS总体架构设计_V0.1.md` 四项设计被 §4.4 冻结，文件顶部已挂横幅。改目录或改布局前，先改本文件，再改代码。
