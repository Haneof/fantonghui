# schemas/ —— Canonical 03 的逐字节参照副本

- 存在理由（唯一）：主线验收 `aios/01_os/code/tests/test_s1_t5.py` 的 **S1 项**要用本目录比对
  `aios/01_os/schemas/` 是否仍是 Canonical 03 的逐字节副本（防"第二套定义"）。本目录是**参照物，不是实现**：
  运行时一律读 `aios/01_os/schemas/`（见 `stated.py:38`），不得 import 这里。
- 本目录只保留 03 在世界边界采纳的三份（STATUS 冲突 2 裁决）；V1.2 时代其余六份
  （memory/cognition/decision/growth/relationship/entity）已随旧线归档至
  `archive/legacy_core_simulator/schemas/`——它们是 Semantic-Event-first 的产物，
  V1.4 的新 schema（Observation/DimensionPoint/TriggerRecord/InferenceEvent/SummaryNode）
  须按宪法第三、五、八章**另起新件**，不得原样搬回（V1.4 §12.2）。
- 校验：`cd aios/01_os/code && python3 tests/test_s1_t5.py --fast` → S1 PASS 即三者逐字节一致。
