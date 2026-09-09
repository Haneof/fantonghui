# AIOS · 基于宪法的腕上 AI 操作系统

> 宪法 V1.2 ｜ M0-M3 全部验收通过 ｜ M2.5/M3.5 深化阶段完成（千题基准 + 门控 v2 定案）

AIOS 是一个"戴在手腕上的 AI 操作系统"：以事件总线为内核，以人生树（多层记忆）为文件系统，以宪法为最高行为准则，本地小模型做数据整理与格式规整，云端大模型做认知与主动关怀。

## 目录结构

```
aios/
├── 00_宪法/          # AIOS 宪法 V1.2（最高行为准则，所有开发的第一依据）
├── 01_os/            # 操作系统本体
│   ├── code/         # 全部可运行代码（16 进程架构）
│   │   ├── bus/          # aios_busd 队列化事件总线（SQLite WAL 先落盘后转发）
│   │   ├── aiosd/        # 主控守护进程（看门狗 + 服务编排）
│   │   ├── services/     # 15 个服务：hublinkd/memoryd/modelrouterd/perceptiond/
│   │   │                 #   privacyd/safetyd/stated/attentiond/cognitiond/
│   │   │                 #   decisiond/interactd/evolutiond/entityd/modemgrd/abilityd
│   │   ├── aios_sdk/     # 服务接入 SDK（TCP 帧协议）
│   │   ├── simulator/    # 数据注入模拟器
│   │   ├── tests/        # 千题基准执行器/判分器/门控规则引擎/验收测试
│   │   └── run/          # 运行时目录（不入库：db/密钥/日志）
│   ├── schemas/      # 事件/介入/租约/存储 契约
│   ├── tasks/        # 任务书、契约、验收记录、基准结论
│   └── ROADMAP.md
├── 02_hardware/      # 硬件域（M4 远期，当前不做）
├── 03_ui/ 04_apps/   # 预留
└── README.md
reports/              # 阶段报告（HTML）：宪法终审 / 架构蓝图 / M2.5-M3.5 深化 / 门控 v2 设计
```

## 快速启动（Windows）

```powershell
cd 01_os/code
powershell -ExecutionPolicy Bypass -File start_aios.ps1   # 启动总线+15服务
powershell -File status_aios.ps1                          # 健康检查（bus + 15/15 up）
powershell -File stop_aios.ps1                            # 停止
```

Linux（WSL2/Ubuntu）：

```bash
cd /opt/aios && python3 aiosd/aiosd.py    # bus + 15 服务受管
```

## 核心结论（数据实证，2026-09-09）

- **千题基准（1000 题 × 7 类认知任务）**：大模型 90.6% vs 本地 2B 31.1% / 1.5B 33.5% —— 差距是代差级
- **门控 v2（对比机制）**：规则引擎在同一套 636 题上 **100%**，碾压一切模型方案 —— 本地只做数据整理+阈值触发，触发后大模型带证据包介入
- **基础设施**：31,399 条数据 829 条/秒吞吐；kill -9 全栈压杀后事件零丢失；递归摘要金字塔六跳全通

## 安全说明

`code/run/api_keys.json`（云端模型密钥）已在 `.gitignore` 中排除，永不入库。
