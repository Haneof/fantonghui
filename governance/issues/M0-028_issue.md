# [M0-028] BudgetPolicy / AssemblyPolicy 契约冻结（第 86 条之一，R4-08）

## 目标
"零浪费"与"单次看盘"获得治理对象：预算可版本化被经验修订，执法在内核不可协商；看板组装策略成为可读、可版本、可追责的对象。

## 输入/输出契约
新增 `BudgetPolicy`（prefix bgp）：`scope`（turn/day/background_day/maint_task/band_ingest）、`max_model_calls|max_tokens|max_wakes`（至少一个封顶，已冻结校验）、`on_exceed`（checkpoint/degrade_rules/defer_to_idle/hard_deny）。
新增 `AssemblyPolicy`（prefix asp）：`section_order`（第 85.3 四层，不许重复）、`section_token_caps`（只能引用 order 内的层）、`max_prefill_tokens`（ge=256）、`data_source_allowlist`（**经验只可改排序/裁剪，白名单由内核强制**）。

## 禁止修改 / 必须测试
- 禁止 MeteringRecord 进世界库（计量写自激风暴——它不是 WorldObject，M2-018 随 operations 账本落地）
- 零封顶 BudgetPolicy / 引用幽灵层的 AssemblyPolicy → 拒写（已测）

## 遗留工作
- M2-018：C13 网关接入（无 grant 即拒 PERM/DENIED）+ 三 call site（stream_extract/review_task/heartbeat）
- M4-005 首字 p95≤1.0s 演示（R4-01 验收）

## 上位依据
- AIOS核心系统宪法v3.0 + 《AIOS宪法v3.0修改案_R4.md》（本任务依赖该修改案批准；契约层已以候选契约先行冻结，gate_version=M0-R2+R4-delta-candidate）
- 详细任务书：《AIOS_Core_工程重构与任务拆分设计书_R4_首席架构师版.md》§3.4
- CAM 验收矩阵：schemas/constitution_acceptance.py

## 验收
- [x] 契约单测通过（tests/unit/test_m0_prime_contracts.py，12 用例）
- [x] Schema snapshot 无未批准变化（已按批准漂移流程再生成；见下）
- [ ] R4 修改案签核后转正（仅改 gate_version 字符串，不改字段）

## 已知限制
M0′ 只冻结契约与校验语义；运行面按设计书排入 M1/M2/M3（见下"遗留工作"）。
