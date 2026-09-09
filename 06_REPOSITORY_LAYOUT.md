# AIOS Core Repository Layout V0.1

第一版先做 PC Simulator，不追求“像完整 OS”，追求核心闭环可运行。

```text

aios-core/

├─ docs/

│  ├─ constitution-reference.md

│  ├─ architecture.md

│  ├─ runtime-contracts.md

│  ├─ wake-runtime.md

│  └─ acceptance-tests.md

│

├─ core/

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

│  │  └─ wake

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

│  ├─ world_state.json

│  ├─ cognition.json

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

## 第一版真实实现建议

为了让一个非程序员也能让编码 AI 推进，第一版可以用 Python 做 Simulator。

后续硬件化再逐步迁移：

- 常驻低功耗部分 -> RTOS / MCU / Sensor Hub

- AIOS 主运行时 -> Linux / C++ / Rust 等

- UI/设备适配 -> Android / Linux / Embedded

不要把 Python Simulator 当最终设备 OS；它只是验证底座逻辑的“数字孪生沙盒”。
