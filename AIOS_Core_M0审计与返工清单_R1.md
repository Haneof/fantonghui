# AIOS Core M0 审计与返工清单（R1）

> **审计编号**：AUDIT-M0-R1
> **日期**：2026-09-14
> **审查人**：Arena Agent（以审查员角色执行，非实现方）
> **被测对象**：`aios_core_r2_reference/` @ 主线 `aios-2.0` commit `5597966`（Python 1250 行 / 15 个测试）
> **对账基准**：《AIOS_Core_详细开发任务拆分_R2_总工程师版.md》M0-001…M0-022 的 G（必须编写的测试）/ H（验收标准）/ I（明确禁止）+ 《AIOS宪法2.0》R1/R2 冻结项
> **复核方式**：`cd aios_core_r2_reference && python audit_m0_probes.py`（退出码＝已确认缺口数；`--strict` 可用于 CI 门禁）

---

## 0. 结论

| 层次 | 判定 | 说明 |
|---|---|---|
| 目标 → 方案 | **基本匹配**，含 2 处规格漏洞 | 第一阶段三目标（持续运行 / 主动发现帮助机会 / 能够纠错）在 M2/M3/M4 与 C01–C14 中均有落点；M0-016、M0-019 的规格文本本身存在可绕过口子（见 §3） |
| 方案 → 实现 | **形状匹配、实质不匹配** | 21/22 单的契约对象与存储原语已存在；但按母表 0.2「完成定义」七条衡量，**0/22 单可以合法关闭** |
| 实现 → 目标 | **未开始** | README §1 所列第一阶段六件套（共同世界运行时 / 认知工作台 / 任务与唤醒调度 / 会话执行器 / 纠错与成长 / 虚拟世界评估系统）当前均无代码，只有其脚下的契约层 |

**一句话**：`contracts/` 层质量高（frozen 模型、`extra="forbid"`、ObjectRef 与 SourceRef 类型不可互换、三类时间语义齐全、状态机有测试）；真正的问题集中在**存储层不变量存在可复现破口**、**工程骨架（M0-001）不存在**、**M0-022 Gate 的测试量 15/50 且四个 fixture 全无**。

---

## 1. 已确认的与规格不匹配项（均可复现）

下表全部由 `audit_m0_probes.py` 复现，非推断。

### A 级：动摇 M0 Gate 的不变量破口

| 编号 | 规格出处与原文 | 实测结果 | 影响 |
|---|---|---|---|
| **A1** | M0-009 H「任何高层 Claim/Event 能解释依据是什么」＋ R2-04 区间证据冻结 | `learned_at = NOW+5d` 的 Observation 可写入 `knowledge_cutoff = NOW` 的 EvidenceSet，`commit` 成功 | **未来信息可进入证据**。虚拟世界测试规范要求的真值隔离在此失效，M4/M5 的 A/B 结论将来会被质疑 |
| **A2** | M0-020 H「隐藏未来数据 **0 泄露**」＋ M0-004 G 明确要求「跨时区 Task」测试 | `learned_at` 以 `+08:00` 入库，用 UTC cutoff 查询返回 `NOT_FOUND`；库中存的是 ISO 字符串，比较走**字典序** | 跨时区场景下"该读到的读不到"，且写入顺序、`ORDER BY recorded_at` 全部不可靠 |
| **A3** | M0-016 H「重试无重复副作用，**审计可查**」 | `VERSION_CONFLICT` 后 `operations` 表仅 1 行；`error_code / error_message` 两列**全代码库无写入路径** | 失败操作零留痕。PM 周看板第 4 问（断裂引用 / 重复 Action / 未来信息泄露）无从回答 |
| **A4** | M0-016 C「先查 idempotency_key，再校验 expected_world_revision」 | 同键不同载荷：第二次提交被当作重放（`idempotent_replay=True`），对象**未落库且不报错**；`IDEMPOTENCY_CONFLICT` 定义后从未抛出 | 静默丢写。比崩溃危险：调用方认为提交成功 |
| **A5** | M0-019 G「自引用 Claim/Evidence 当前版本拒绝」 | 引用自身且 `revision = None`（latest）可绕过；实现只拦 `ref.revision == obj.revision` | 自我引证成立 → 「主张用自己作证」这一条防线是空的 |

### B 级：整单缺件

| 编号 | 规格出处 | 实测结果 |
|---|---|---|
| **B1** | M0-015 H「能够从底层对象反查受影响对象」 | `SQLiteWorldStore` 公共 API 仅 `[commit, current_world_revision, get_payload, list_payloads, operation_record]`，**无任何按引用反查接口**；A↔B 同事务互引提交成功，「构造循环证据应拒绝或标红」未实现 |
| **B2** | M0-002 H「所有协议级失败都有 code + message + context」 | `ErrorCode` 10 个码中 **6 个从未被抛出**（`INCOMPLETE_DATA / STALE_INDEX / BUDGET_EXHAUSTED / PERMISSION_DENIED / OUTCOME_UNKNOWN / IDEMPOTENCY_CONFLICT`）；`StoreError.__init__(self, code, message)` **无 context 字段**；contracts/services 全部抛裸 `ValueError` |
| **B3** | M0-005 H「任何修改不覆盖旧 revision」＋ 状态可追溯 | `WorldObject.status` 是裸 `str`，实测可写入任意值；`Action.outcome_state`、`Session.session_state`、`OperationExperience.experience_state` 同样为裸字符串 |
| **B4** | M0-001 H「全仓可安装；依赖方向检查通过；README 能说明四个运行单元」 | 仓库根**无** `pyproject.toml/setup.py`；`ai_worker / console / simulator / evaluator` 目录不存在；「禁止 AI Worker 获得 sqlite connection」无 import-lint、无 truth-path 隔离测试。母表 §14 把 M0-001 列为**第 1 批第 1 项** |

### C 级：实测通过（不要误改）

| 编号 | 结论 |
|---|---|
| **C1** | 并发双写：`{0:'ok', 1:'VERSION_CONFLICT'}`，`world_revision == 1` ✅ 乐观并发正确。但 M0-017 G / M0-018 G 要求的**这条测试在仓库里不存在**，属"实现对了、证据没有" |
| **C2** | append-only revision（跳号写 rev4 被拒）、历史 `get_payload(revision=1)`、`commit` 原子回滚、同事务互引、悬空 ref → `NOT_FOUND`、100k ID 零碰撞 ✅ 全部符合规格 |

---

## 2. M0 二十二单逐单对账

口径：**结构**＝契约/接口是否到位；**DoD**＝母表 0.2 七条（代码合并 / 文档一致 / 单测 / 跨模块集成测试 / 可运行证据 / 已知限制记录 / 不违反 R2 冻结项）。

| 单号 | 标题 | 结构 | DoD | 关键证据 / 缺口 |
|---|---|---|---|---|
| M0-001 | 仓库骨架、包边界与依赖方向 | ✗ | 0/7 | B4：整单未开工 |
| M0-002 | 统一错误码与协议级异常 | △ | 1/7 | B2：6 个死码、无 context、非存储层无 code |
| M0-003 | 稳定对象 ID | ✓ | 4/7 | 实测 100k 唯一；「rename 不改 ID」「不泄露真值」无测试 |
| M0-004 | 唯一时间轴与三类时间语义 | △ | 3/7 | A2 跨时区破口；G 要求的「跨时区 Task」测试缺失 |
| M0-005 | WorldObject 公共字段与 Revision | △ | 4/7 | append-only ✓；B3 状态裸串 |
| M0-006 | ObjectRef / SourceRef 版本化引用 | ✓ | 3/7 | 类型互斥（传 ObjectRef 给 `source_refs` 被 pydantic 拒）；G 四项测试仅一项被我补测 |
| M0-007 | Observation 契约 | △ | 2/7 | `value: Any` 实测可写 `{'event_type':'breakup'}`，「底层不做语义判断」无防护无测试 |
| M0-008 | Claim 语义模型 | ✓ | 3/7 | ClaimType 11 × KnowledgeState 6 分离达成 R2-02；「话语置信度不得抬高预测置信度」仅靠约定 |
| M0-009 | EvidenceSet 一等对象 | ✗ | 1/7 | A1；`EvidenceCoverage` 可全 `None` 静默 |
| M0-010 | Entity + Relation | △ | 2/7 | 结构对；G 四场景全缺；「字符串搜索不自动合并实体」因无 merge API 而被动满足 |
| M0-011 | Dimension 三层契约 | ✓ | 4/7 | `input_refs` 最小 1、`data_shape` 不被强制为 curve、证据只以引用存在 ✅ |
| M0-012 | EventAnchor 契约与生命周期 | ✓ | 5/7 | 状态机 4/4 测试通过；`status=MERGED` 而 `merged_into_ref=None` 仍可提交（缺一致性校验） |
| M0-013 | Goal 一等对象 | ✓ | 3/7 | `GoalSourceType` 五源分离 ✅；「用户否认后 Task 复核」属 M3 |
| M0-014 | Task/Wake/Session/Action/Outcome | △ | 3/7 | `new_execution_id()` 定义后**全库零调用**；状态字段裸串（B3） |
| M0-015 | Dependency 契约 | ✗ | 0/7 | B1：反查 API 与循环引用检测均缺 |
| M0-016 | OperationRequest、审计与幂等 | △ | 3/7 | A3 + A4 |
| M0-017 | SQLite 追加式世界存储 schema | △ | 2/7 | `world_meta` 仅 `world_revision` 一键，**无 schema_version / 迁移脚本**；G 七项测试覆盖约 3 项；断电一致性无测试 |
| M0-018 | 全局 World Revision 与原子提交 | ✓ | 4/7 | C1 ✅；「失败中途不写半个世界」代码正确但无测试 |
| M0-019 | 引用存在性与同事务验证 | △ | 2/7 | A5；`validate_references=False` 是公开绕过入口，与「同事务强制」存在张力 |
| M0-020 | 历史世界读取与 Knowledge Cutoff | △ | 3/7 | 同偏移下正确 ✅；A2；历史读取走 Python 全表兜底（规模隐患） |
| M0-021 | Task / Event 状态机冻结 | ✓ | 6/7 | **唯一接近可关闭的一单**（G 四场景全部有测试且通过） |
| M0-022 | M0 契约总测试与冻结快照 | ✗ | 0/7 | 要求「最少 50 个断言场景」+ 运动会/未知人物/未来预测/Goal-Task 四 fixture：现全仓 **15 个测试函数、0 个 fixture、0 个 schema snapshot** |

---

## 3. NEEDS_ARCH_CHANGE（按 R2 规定不得由编码人员顺手修改）

依据《…_R2.md:927》「任何 `NEEDS_ARCH_CHANGE` 不得由编码人员自己顺手修改 schema 后继续开发」，以下两条**只提议题，不动代码**：

1. **NAC-1 自我引证定义不完整**（对应 A5）
   规格把禁止条件写成「自己的当前 revision」，`revision=None`（latest 语义）天然落在禁止范围之外。
   **建议改为**：对象不得以 `object_id` 等于自身的引用（**含 latest 与任意 revision**）作为自身证据或来源；如需允许"新版本引用旧版本"，必须显式写成 `revision < 自身 revision` 并加测试。
2. **NAC-2 幂等判定未纳入载荷指纹**（对应 A4）
   规格只写「重放返回原结果」，未规定重放前必须比对请求内容，导致同键不同载荷静默丢写。
   **建议增加**：`OperationRequest.arguments_digest`（或 `payload_sha256`）参与幂等判定；键相同而摘要不同 → `IDEMPOTENCY_CONFLICT` 并写入审计表。

---

## 4. 建议的返工顺序（每步都可独立关闭）

| 步 | 内容 | 关闭判据（对应 DoD） |
|---|---|---|
| **1** | A1 + A5：EvidenceSet 成员可见性约束、自证含 latest 拦截 | 每条先写失败测试再实现；`audit_m0_probes.py` 对应项转 PASS；测试搬入 `tests/` |
| **2** | A2：`learned_at / recorded_at` 统一按 UTC 存储与比较，cutoff 走绝对时刻 | 补 M0-004 G 的「跨时区 Task」+ cutoff 两侧测试；`ORDER BY` 改按规范化时间 |
| **3** | A3 + A4 + B2：失败操作写 `operations(status='failed', error_code, error_message, context)`；`StoreError` 加 `context`；contracts/services 异常映射到 ErrorCode；10 个码全部有抛出路径 | M0-002 H、M0-016 H 达成；错误码逐个构造测试 |
| **4** | B4：M0-001 工程骨架 —— 仓库根 `pyproject.toml` + `src/aios_core|ai_worker|console|evaluator` 四分区 + 依赖方向测试（禁止 `ai_worker` 出现 `import sqlite3` 与私有连接；禁止读取 evaluator truth path） | M0-001 H 四条全绿；此项**负责人级别＝总工程师定义、编码代理执行**，可由编码代理承担 |
| **5** | B1：`store.dependents(object_id)` 反查 + 循环引用检测（拒绝或标红） | M0-015 H 可达；集成测试覆盖 Claim→EvidenceSet→Observation 链 |
| **6** | B3 + 状态一致性：生命周期状态改受控枚举（含 `Action/Session/OperationExperience`）；EventAnchor 状态与 `merged_into_ref/split_child_refs` 一致性校验 | M0-005 H、M0-012 缺口闭合 |
| **7** | M0-022 Gate：把探针逐条转成 `tests/`，补四个场景 fixture 与 schema snapshot，`--strict` 进 CI | 「M0 完成」在此之前不应对外宣称 |

---

## 5. 审查边界声明

- 本次审查**未修改** `src/aios_core/**` 与 `tests/**` 的任何一行；新增文件仅本审计文档与 `audit_m0_probes.py`。
- 探针为只读行为检验，运行于临时目录中的独立数据库，不接触任何真实数据。
- 环境事实：仓库无 CI 配置，`pyproject` 声明 `requires-python>=3.12` 但无锁文件、无 lint/type-check 配置；`aios_core_r2_reference_test_output.txt` 仅有一行 `...............  [100%]`，**不含命令、Python 版本与依赖版本**，按 DoD 第 5 条「可运行证据」目前不可复核（本审计是在临时 venv 装 `pydantic 2.13.5 / pytest 8` 后才跑通 15 个测试）。
- 建议随本清单补一条约定：`aios_core_r2_reference_test_output.txt` 改为记录 `python -V` + `pip freeze | grep pydantic` + 完整 `pytest -q` 输出，否则"基线测试验证记录"无法被第三方复现。
