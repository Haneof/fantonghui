# AIOS Core Repository Layout V0.1-r1

第一版先做 PC Simulator，不追求“像完整 OS”，追求核心闭环可运行。

## 文档规范位置

所有项目规范文档统一放在 `docs/`，文档编号保留，不再使用根目录与 `docs/` 两套规范路径。

```text

aios-core/

├─ docs/

│  ├─ 00_START_HERE.md

│  ├─ 01_CORE_ARCHITECTURE.md

│  ├─ 02_RUNTIME_CONTRACTS.md

│  ├─ 03_WORLD_EVENT_SCHEMA.md

│  ├─ 04_WAKE_RUNTIME.md

│  ├─ 05_AI_RUNTIME.md

│  ├─ 06_REPOSITORY_LAYOUT.md

│  ├─ 07_DEVELOPMENT_PLAN.md

│  ├─ 08_ACCEPTANCE_TESTS.md

│  ├─ 09_FIRST_SPRINT_TASKS.md

│  ├─ AIOS_Constitution_V1.2-r1.md

│  └─ AIOS_PROJECT_MASTER_PROMPT_V1.0.md

│

├─ core/

│  ├─ perception/

│  │  └─ perception_runtime

│  ├─ world/

│  │  ├─ world_runtime

│  │  ├─ state_runtime

│  │  └─ entity_runtime

│  ├─ event/

│  │  ├─ event_runtime

│  │  ├─ fusion

│  │  └─ patterns

│  ├─ memory/

│  │  └─ memory_runtime

│  ├─ identity/

│  │  └─ identity_runtime

│  ├─ attention/

│  │  ├─ relevance

│  │  ├─ attention

│  │  ├─ wake

│  │  └─ lease

│  ├─ ai/

│  │  ├─ ai_runtime

│  │  ├─ model_router

│  │  └─ cognitive_world

│  ├─ capability/

│  │  └─ capability_runtime

│  ├─ policy/

│  │  ├─ permission

│  │  └─ safety

│  ├─ interaction/

│  │  └─ interaction_runtime

│  └─ evolution/

│     └─ evolution_runtime

│

├─ adapters/

│  ├─ simulator/

│  ├─ phone/

│  └─ wearable/

│

├─ schemas/

│  ├─ event.json

│  ├─ entity.json

│  ├─ relationship.json

│  ├─ world_state.json

│  ├─ memory.json

│  ├─ world_change.json

│  ├─ cognition.json

│  ├─ decision.json

│  └─ growth.json

│

├─ tests/

│  ├─ unit/

│  ├─ integration/

│  └─ scenario/

│

└─ tools/

   └─ simulator/

```

## 规范文件与仓库路径规则

规范文档的 canonical 路径只有 `docs/`。Agent 不得在仓库根目录复制另一份规范文件。

## 第一版真实实现建议

为了让一个非程序员也能让编码 AI 推进，第一版可以用 Python 做 Simulator。

后续硬件化再逐步迁移：

- 常驻低功耗部分 -> RTOS / MCU / Sensor Hub

- AIOS 主运行时 -> Linux / C++ / Rust 等

- UI/设备适配 -> Android / Linux / Embedded

不要把 Python Simulator 当最终设备 OS；它只是验证底座逻辑的“数字孪生沙盒”。
