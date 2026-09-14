# AIOS Core M0 审计 R2 · 宪法符合性与缺陷清单（M0-001 … M0-019）

| 项 | 内容 |
|---|---|
| 审计编号 | AUDIT-M0-R2（取代 `AIOS_Core_M0审计与返工清单_R1.md`，见 §0） |
| 审计对象 | `aios_core_r2_reference/src/aios_core/**`（contracts / services / storage）+ `tests/` |
| 审查范围 | 母表 M0-001 … M0-019 已交付代码，逐单对照《AIOS宪法2.0》与工程目的 |
| 依据 | 《AIOS宪法2.0》R2（46 条）·《AIOS Core 详细开发任务拆分 R2（总工程师版）》R2 |
| 复现命令 | `cd aios_core_r2_reference && python audit_m0_probes.py`（退出码 = GAP 数） |
| 实测结论 | **17 项检查：16 GAP / 1 PASS**（退出码 = GAP 数 = 16）；被测仓库自带 15 个 pytest 用例全绿 |
| 审计产出物 | `aios_core_r2_reference/audit_m0_probes.py`（只读探针，不改动被测代码） |

---

## 0. 对 R1 的口径更正（先认错）

| R1 的说法 | 更正 |
|---|---|
| 「M0-001 未开工，四运行单元骨架缺失 → 缺陷」 | **撤回**。母表 §13 记录：001–019 由总工程师以「可执行参考实现」交付，工程根目录结构是自觉选择；宪法第四十四条也明确「现在只开发 AIOS Core，不开发上层产品」。骨架何时落地是**排期裁定问题**，不是实现缺陷 → 降级为 NAC-4 |
| 未区分「新发现」与「已知限制」 | **更正**。§13 已明文承认四项：证据依赖的复杂循环检测、迁移框架、完整 API、Dependency 反向索引。本审计中 **B1 依赖反查**、**A6 的引用可绕过部分**、**A1 的循环检测部分**落在已承认范围内，标注为【已承认】而非新缺陷 |

R1 的三项硬阻塞（A1 证据可见性、A3 失败留痕、A5 自证绕过）**仍然成立**，本文把它们重新按宪法风险排序。

---

## 1. 逐单宪法符合性判定

判定标记：✅ 符合 ｜ ⚠️ 部分符合 ｜ ❌ 不符合（存在可利用缺陷）。探针编号见 §2，全部可复跑。

| 单 | 宪法条款 | 实现位置 | 判定与依据 |
|---|---|---|---|
| M0-001 工程骨架 | 第四十四条（只开发 Core）、第三十九条 | `aios_core_r2_reference/src/aios_core/{contracts,services,storage}` | ⚠️ 契约层齐备且可回放（§13）；但 `ai_worker / console / simulator / evaluator` 四包与 `aios.data.root` 双挂载尚不存在 → 属排期裁定（NAC-4），不计为缺陷 |
| M0-002 错误码 | 第十三条（可诊断）、第四十五条 | `contracts/enums.py`（ErrorCode 10 个）、`sqlite_store.py:21`（StoreError） | ⚠️ 10 个错误码齐；但 `StoreError` 无 `context` 字段；`INCOMPLETE_DATA / STALE_INDEX / BUDGET_EXHAUSTED / PERMISSION_DENIED / OUTCOME_UNKNOWN / IDEMPOTENCY_CONFLICT` 六项全库无抛出路径（10 个里只有 4 个在用：INVALID_ARGUMENT、NOT_FOUND、VERSION_CONFLICT、DEPENDENCY_INVALID）；contracts 层校验失败抛裸 `ValueError` → 调用者无法分支处理（B2） |
| M0-003 ID 与 ref | 第十五条、第八条 | `contracts/ids.py:7`（_PREFIXES，20 类）、`refs.py:12` | ⚠️ ID 由 `ids.py:7` 的 uuid4 生成、前缀映射覆盖 20 类 ✅，但**仓库内没有唯一性/不复用测试**（15 个用例里无此项）；❌ `object_id: str` 无 pattern，**ID 前缀与 `object_type` 互不校验**：`ent_` 开头的 ID 被登记为 `observation`（A11） |
| M0-004 时间模型 | **第二条**（唯一时间轴；记录时间/事件时间不能混淆） | `contracts/time.py`、`contracts/base.py:23-24`、`sqlite_store.py:278`（写入）与 `:349/:383/:432`（比较） | ❌ tz-naive 被拒 ✅、三类时间字段齐 ✅；但**时区不被归一**：`learned_at` 以带 `+08:00` 的本地串入库存为 TEXT，可见性用 SQL **字典序**比较 → 同一事实按 UTC 记录可见、按东八区记录不可见（A2）。这直接违反第二条「世界不能靠猜测」，并使 M0-020 H 的「0 泄露」只在时区巧合下成立 |
| M0-005 Revision | 第十三条（不覆盖历史）、第一条 | `base.py:21`（revision ge=1）、`sqlite_store.py:226-235`（单调性校验） | ✅ revision 必须 = latest+1、不覆盖、只追加（`tests/test_store.py:94` 跳号被拒 + 探针复核）；⚠️ `status` 及 session/outcome/experience 状态全为裸 `str`（B3），"受控迁移"目前只靠调用方自觉 |
| M0-006 版本化引用 | 第八条（向下追溯、自证）、M0-006 H | `refs.py:9-22`、`sqlite_store.py:169`（_collect_refs）、`:229-233`（自证） | ❌ **引用只有 `object_id + revision`**（`refs.py:12-14`），既无 `object_type` 也无「引用产生时的世界版本」→ M0-006 G 要求的「携带类型与来源世界版本」未实现，因此无法验证「该版本在当时确实可见」；✅ ref 不可变（frozen）；另有两点漏洞：`revision=None`（最新）可指向自身实现自证（A5，R1 的 NAC-1）；`dict[str,Any]` 字段里的字典形式引用不被 `_collect_refs` 识别，引用存在性与自证**双双绕过**（A6） |
| M0-007 Observation | 第五条、第四十三条、第十七条 | `contracts/models.py:28`（Observation）、`tests/test_contracts.py:28` | ✅ raw_data_hash/normalize_method/data_quality/时间三件套齐（比任务书 G 更严）；⚠️ `value: Any` 无约束 → 结论可夹带进原始记录；测试用 `source_refs=[]` 即"无来源也可登记"，与 G 的 `source_ref` 必填口径不一致（待裁定） |
| M0-008 Claim | **第十二条**（置信针对具体主张）、第七条 | `contracts/models.py:87`（Claim）、`tests/test_contracts.py:45` | ✅ 本轮唯一"完全达成宪法意图"的一单：`claim_type × knowledge_state` 正交，"用户说喜欢咖啡 ≠ 咖啡对他有益"有测试；⚠️ `inferred_preference` 仍被归 `preference` 且置信 0.7，与 M0-008 G 的 `inference` 口径不同（需一致性核对） |
| M0-009 EvidenceSet | 第六条、**第四十六条**（真值隔离） | `contracts/models.py:126`（EvidenceSet）、`sqlite_store.py:76`（唯一落库表 object_revisions） | ❌ 一等对象（selector/成员/coverage/stale）✅、"区间证据一周后仍指原区间"✅；但**成员自身 `learned_at` 不受 selector 时间窗约束** → 未来信息进入证据（A1，P0）。【已承认】循环检测属 §13 待补项，不重复计 |
| M0-010 Entity/Relation/Summary | 第十五、十八、十九条 | `contracts/models.py:38/46/163` | ⚠️ 证据式身份、aliases、supersedes、`support_refs` 齐 ✅；❌ `source_world_revision: int = Field(ge=0)` 是唯一约束 → 世界版本只到 1 时可提交指向 999 的 Summary（A8），"总结可展开重建"落空 |
| M0-011 Dimension 三层 | **第二十一条**（生命周期） | `contracts/models.py:56/67/75`、`enums.py`（DimensionLifecycle） | ❌ 枚举 7 态齐 ✅；但 `state_machines.py` 只有 `TASK_TRANSITIONS` 与 `EVENT_TRANSITIONS`，**维度生命周期无转换矩阵**：`RETIRED→ACTIVE` 可直写（A7）。宪法第二十一条明确要求受控转换 → **需求覆盖缺口**（母表 M0-021 也只冻结了 Task/Event） |
| M0-012 EventAnchor | 第五条、第十三条 | `contracts/models.py:148` | ⚠️ 锚点只存引用、不复制事件内容 ✅；❌ `status=MERGED` 而 `merged_into_ref=None` 可提交（A9）→ 第十三条"后来为何修正"的链条在契约层可被写成断头 |
| M0-013 Goal | 第三十一、三十二条 | `contracts/models.py:175` | ⚠️ Goal 与 Task 分离 ✅、active_task_refs 必填 ✅；但"用户否认推断目标"只能靠新 revision + `supersedes_refs`，而该语义只有 Event 有一致性校验（与 A9 同源，见 NAC-3） |
| M0-014 Task/Wake/Session/Action/Outcome | 第三十二、三十三条 | `contracts/models.py:197/226/247/256/266` | ❌ 字段符合度最高，但：`deadline` 已过期且早于 `next_wake_at` 不报错；`RUNNING→EXPIRED` 被状态机拒（过期任务只能 FAILED/CANCELLED，A10）；`task_state` 用枚举 ✅，但 `new_execution_id()`（`ids.py:44`）全库零调用 → M0-014 D 的 execution_id 幂等未接线（B2） |
| M0-015 Dependency | 第十四条、第十三条 | `contracts/models.py:190` | ❌ **存储侧没有任何依赖表/索引**（全库仅 `sqlite_store.py:241` 提到 evidence/self-cite 文案），成员与依赖关系都埋在 `payload_json` 里；无按 ref 反查 API（【已承认】§13）、`reason` 自由文本、边可指向不存在的 revision；叠加 A6（引用藏在字典里不被扫描）→ **第十四条"必须存在认知依赖关系"在契约层无法保证完整** |
| M0-016 幂等与审计 | 第十三条、第四十五条 | `contracts/operations.py`、`sqlite_store.py:111`（idempotency_records）、`:205`（重放分支） | ❌ 载荷一致的重放 ✅；失败操作零留痕，`operations.error_code/error_message` 无写入路径（A3）；同幂等键不同载荷被**静默当作重放并返回 ok**、载荷不落库也不报错（A4），`IDEMPOTENCY_CONFLICT` 成死码 |
| M0-017 schema | 架构唯一写入层 | `sqlite_store.py:60-111`（5 表）、`:49-50`（PRAGMA） | ⚠️ 表结构符合母表 F，WAL 与外键均在 Core 自己连接上打开（`:49`）✅；无 `schema_version` 列（【已承认】迁移框架）；❌ 外键是**每连接 opt-in**：SQLite 默认 `fk=0`，任何不经 Core 的连接都不受约束 → 直写 `object_revisions` 可造出指向不存在世界版本的孤儿对象（A12）；且 `payload_json` 无任何 CHECK，可为空字典 |
| M0-018 World Revision | 第二条（唯一时间轴） | `sqlite_store.py:121`（current）、`:191`（commit 内 `BEGIN IMMEDIATE` + 乐观锁） | ✅ 本轮最强项，实测通过：并发双写恰好一个成功、另一个 `VERSION_CONFLICT`，失败方**无半成品残留**（C1，探针现场执行）；⚠️ 但仓库内没有该测试（M0-018 H 要求"用多线程或双进程"），且 A12 显示可绕过 revision 直接插入 |
| M0-019 引用验证 | 第八条、第三部分可验证链 | `sqlite_store.py:169`（_collect_refs）、`:191`（`validate_references=True` 默认开）、`contracts/base.py:16`（extra=forbid） | ❌ 校验存在 ✅、"拒绝指向不存在 revision"有测试 ✅；但 A5（latest 自证）、A6（字典形式引用绕过 `_collect_refs`）使"M0-019 H：测试集无未发现断裂引用"**不成立**；`validate_references=False` 是随时可关的公开逃生舱 |

**统计**：001–019 中 ✅ 1（M0-008）／⚠️ 7／❌ 11。最成问题的两条主线：**引用契约（006/019）与生命周期（005/011/014）在写入路径上没有强制**。M0-020、M0-021 已随参考实现交付（§13 第 11、12 点），M0-022 Gate 未建 —— 顺便提示：**进度口径"做到 019"与代码已含 020/021 不一致**，请核对记录。

---

### 1.1 测试覆盖实况（15 个用例，3 个文件，全部通过）

`tests/test_contracts.py`（5）· `tests/test_state_machines.py`（4）· `tests/test_store.py`（6）。
其中三处与验收条款直接相关：① `test_learned_at_cutoff_hides_future_known_revision`（`test_store.py:85`）
**只断言 cutoff 时读到旧 revision，未断言列表可见性被隐藏**，与 M0-020 H「无时间快照与 cutoff 快照差异为 0」不对应；
② **无跨时区用例**（M0-004 H 第 2 条要求）→ A2 因此未被现有测试发现；
③ **无并发写用例**（M0-018 H 要求多线程/双进程）→ 该能力目前只在本次探针中验证过（C1），**必须补进仓库测试**。

## 2. 缺陷清单（按宪法风险排序，全部有探针复现）

### P0 · 动摇"数据分身模拟"实验有效性

| # | 缺陷 | 复现 | 违反 | 建议 |
|---|---|---|---|---|
| A1 | 证据集合把 cutoff 之后才获知的信息收进证据 → 未来信息进入 Simulated Self 的输入 | `gap_a1`（成员 learned_at=2026-10-01，selector 窗口截止 09-14，提交成功） | M0-009 H、宪法第四十六条真值隔离 | store 侧按 `knowledge_window + cutoff` 校验每个成员；违规返回 `EVIDENCE_SET_STALE` 或新错误码 |
| A2 | 时区不归一 + 字典序比较 → 同一事实在一种时区下"已存在"、另一种下"不存在"。写入用 `obj.learned_at.isoformat()`（`sqlite_store.py:278`）保留原偏移；比较走 TEXT 字典序，**三个读路径同时受影响**：`get_payload`(:349)、`list_payloads`(:383)、第三处历史读(:432)；`base.py:23` 只要求 tz-aware，不要求 UTC | `gap_a2`（同一时刻：UTC 记录可见 / +08:00 记录 `NOT_FOUND`） | 宪法第二条、M0-020 H | 写入与查询统一 `astimezone(UTC).isoformat()`（或存 epoch 整数）；补 M0-004 H 的跨时区测试 |
| A12 | "唯一 Core 写入层"无数据库侧强制：`PRAGMA foreign_keys=ON` 是**每连接**生效（`sqlite_store.py:49`），Core 之外的连接默认 `fk=0` → 可造指向不存在世界版本的孤儿对象；`payload_json` 无 CHECK，空字典也能落库并被 `get_payload` 读出 | `gap_a12`（fk=0 写入成功；同一 SQL 在 fk=1 被拒） | 架构约束、M0-017 I | 建库时即设 `PRAGMA foreign_keys=ON` 并加 BEFORE INSERT/UPDATE 触发器禁止绕过；Simulator 挂载只读 |

### P1 · 破坏"可追溯 / 可修正"这两条宪法主线

| # | 缺陷 | 复现 | 违反 |
|---|---|---|---|
| A5 | `revision=None`（最新版本）即可满足"必须有来源"，自证绕过（`sqlite_store.py:238-242` 以 `ref.revision == obj.revision` 判自引用） | `gap_a5` | M0-006 H、第八条 |
| A13 | **生命周期校验未接在写入路径**：`validate_task_transition(COMPLETED, RUNNING)` 明确禁止，同一转换经 `commit()` 却落库成功（store 内调用次数 = 0） | `gap_a13_state_machine_not_wired` | 第二十一条、M0-005/011/014 |
| A14 | **引用不带类型与来源世界版本**：`ObjectRef` 只有 `object_id + revision`（`refs.py:12-14`）→ 无法验证「被引版本当时可见」，断链时也报不出类型（静态核对；`tests/test_contracts.py:78` 只测了 ref 可存） | 无（结构缺失） | M0-006 G/H、第八条 |
| A6 | 字典形式引用不被 `_collect_refs`（`sqlite_store.py:169`）识别 → 引用存在性与自证双双绕过；`get_payload` 直接 `json.loads` 返回（`:360`），不做 `model_validate` | `gap_a6` | M0-019 H、第八条 |
| A9 | `MERGED` 状态与 `merged_into_ref` 可不一致 → 修正链断头 | `gap_a9` | 第十三条 |
| A7 | Dimension / Goal / Summary 连转换矩阵都没有：`state_machines.py` 只有 `_TASK_TRANSITIONS`(:6) 与 `_EVENT_TRANSITIONS`(:30) | `gap_a7` | 第二十一条、M0-011 |
| A8 | `Summary.source_world_revision`(`models.py:168`) 与 `Session.snapshot_world_revision`(`:250`) 只校验 `ge=0`，不校验存在 → 悬空快照 | `gap_a8` | 第十八、十九条 |
| A3 | 失败操作零留痕：`operations.error_code/error_message` 列存在（`sqlite_store.py:106-107`）但全库无写入路径 | `gap_a3` | M0-016 H、第四十五条 |

### P2 · 工程正确性与可用性

| # | 缺陷 | 说明 |
|---|---|---|
| A4 | 同幂等键不同载荷被静默当重放，`_get_idempotent_result` 只读 `result_json` 就返回成功，**完全不比较本次载荷**（`sqlite_store.py:205`） |
| A10 | `RUNNING→EXPIRED` 被拒；`deadline` 早于 `next_wake_at` 且已过期不报错 |
| A11 | ID 前缀与 `object_type` 互不校验 → 任何"按前缀路由 / 按前缀建索引"的假设不成立 |
| B2 | 死码：`new_execution_id`（`ids.py:44`）零调用；`ErrorCode` 10 个中 6 个从不抛出；`StoreError(code, message)` 无 `context`（`sqlite_store.py:21-25`）；contracts 校验失败抛裸 `ValueError` 而非带码错误 |
| B3 | `WorldObject.status: str = "active"`（`base.py:27`）+ `session_state`(`models.py:253`) / `outcome_state`(`:269`) / `experience_state`(`:284`) / `data_shape`(`:60`) 全为裸 `str`（`task_state`、`lifecycle` 用枚举 ✅）|
| B1 | 无按引用反查 API（【已承认】§13），且 schema 里**没有依赖边表**（5 表为 world_meta / world_commits / object_revisions / operations / idempotency_records），反查只能全表扫 `payload_json`；M0-015 H 与 M0-022 场景依赖它 |
| — | 性能：批量读走 `list_payloads`(`:362`) 的 Python 侧组装、无分页参数；测试最大规模 2 条对象 → M0-022 的 500 次回放与 M0-020 批量场景无性能保证 |

---

## 3. 需要总工裁定（审计不得自行改冻结项）

| 编号 | 事项 | 影响 |
|---|---|---|
| NAC-1 | 「自证」是否允许指向自身最新版本（`revision=None`）；若不允许，需明确 latest 的解析时机 | A5、M0-006 H |
| NAC-2 | 幂等冲突如何检测：载荷当前不落库，必须先决定是否纳入载荷摘要（哈希）入唯一键 | A4、`IDEMPOTENCY_CONFLICT` |
| NAC-3 | 「修订即新 revision + supersedes 引用」的一致性校验现在只有 Event 有，是否推广为全对象类型的通用契约 | A9、M0-013 |
| NAC-4 | `ai_worker / console / evaluator` 骨架与 `aios.data.root` 双挂载的落地时点（宪法第四十四条 vs 母表 M0-001 H） | M0-001、真值隔离 |
| NAC-5 | 生命周期状态机的覆盖范围：是否把 Dimension / Goal / Summary 也纳入 M0-021 的冻结清单 | A7 |

---

## 4. 建议修复顺序（一步一个可关闭 PR）

1. **A2 时间归一**（改动最小、影响面最大，直接决定所有时间窗口实验有效性）+ 补 M0-004 跨时区测试。
2. **A1 + A5 + A6 引用与证据闭包**（store 侧校验成员 cutoff；latest 自证规则；禁止 `dict[str,Any]` 承载引用形状，或强制走 `SourceRef/ObjectRef` 类型）。
3. **A12 写入层强制**（建库期 PRAGMA + 触发器禁止旁路写 + 文档化"写路径"）。
4. **A3 + A4 审计与幂等**（失败路径必须写 operation 行并返回带 `context` 的 `StoreError`）。
5. **A7 + A9 + A10 + A11 + B3 契约收紧**（状态改 `StrEnum`；扩展 `TRANSITIONS`；ID 前缀与类型互校；时间字段自洽校验）。
6. **B1 依赖反查 + M0-022 Gate**（≥50 断言场景 + 4 个 fixture + schema snapshot + 并发写测试入库）。

---

## 5. 复核方式与审计边界

```bash
cd aios_core_r2_reference
/tmp/aiosenv/bin/python audit_m0_probes.py          # 人读对账表（17 项），退出码 = GAP 数
/tmp/aiosenv/bin/python audit_m0_probes.py --strict # 机器可读 JSON（16 GAP → 非零退出）
/tmp/aiosenv/bin/python -m pytest -q                # 被测仓库自带 15 用例，全绿
```

本审计**未修改** `aios_core_r2_reference` 的任何 `src/` 或 `tests/` 代码（避免把未经裁定的修复混进审计 PR）；只新增 `audit_m0_probes.py` 与本文件。
**审计自身限制**：① 只读式黑盒 + 源码静态核对，未做 SQL 注入 / 磁盘满 / 进程强杀等故障注入；② 探针不覆盖性能（仅指认"无索引 + Python 扫描"）；③ 未运行 Simulator / Evaluator —— 它们尚不存在（见 NAC-4）。

## 修订记录

| 版本 | 变更 |
|---|---|
| R1 | 以"要不要从 M0-001 重新开工"为框架；5 项已确认不匹配 + 2 项 NAC + 返工清单 |
| R2 | 按总工口径改为**逐单 001–019 宪法符合性**；撤回"M0-001 未开工 = 缺陷"；新增 A6–A12 七项；区分【已承认】项；补 NAC-3/4/5 |
