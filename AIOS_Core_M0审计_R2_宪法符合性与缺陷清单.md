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
| 未区分「新发现」与「已知限制」 | **更正**。§13 已明文承认四项：证据依赖的复杂循环检测、迁移框架、完整 API、Dependency 反向索引。本审计中 **`M0-015-B1` 依赖反查**、**`M0-019-B2` 的引用可绕过部分**、**`M0-009-B1` 的循环检测部分**落在已承认范围内，标注为【已承认】而非新缺陷 |

R1 的三项硬阻塞（`M0-009-B1` 证据可见性、`M0-016-B1` 失败留痕、`M0-019-B1` 自证绕过）**仍然成立**。

**编号体系一并纠正**：R1 用了 A1…A5／B1…B3／C1 这种审计自造编号，脱离项目进度体系、无法直接派工。
R2 全部改为 `M0-0NN-B<k>`（NN=主责工单号，B=Bug），文档、探针输出、退出码语义三处同步；跨单影响放在「违反」列做交叉引用。

---

## 1. 逐单宪法符合性判定

判定标记：✅ 符合 ｜ ⚠️ 部分符合 ｜ ❌ 不符合（存在可利用缺陷）。
每行末尾的 `M0-0NN-B<k>` 即该单的缺陷编号，完整描述与复现证据在 §2 —— **编号本身就是工单号，可直接照此派工**。

| 单 | 宪法条款 | 实现位置 | 判定与依据 |
|---|---|---|---|
| M0-001 工程骨架 | 第四十四条（只开发 Core）、第三十九条 | `aios_core_r2_reference/src/aios_core/{contracts,services,storage}` | ⚠️ 契约层齐备且可回放（§13）；但 `ai_worker / console / simulator / evaluator` 四包与 `aios.data.root` 双挂载尚不存在 → 属排期裁定（NAC-4），不计为缺陷 |
| M0-002 错误码 | 第十三条（可诊断）、第四十五条 | `contracts/enums.py`（ErrorCode 10 个）、`sqlite_store.py:21`（StoreError） | ⚠️ 10 个错误码齐；但 `StoreError` 无 `context` 字段；`INCOMPLETE_DATA / STALE_INDEX / BUDGET_EXHAUSTED / PERMISSION_DENIED / OUTCOME_UNKNOWN / IDEMPOTENCY_CONFLICT` 六项全库无抛出路径（10 个里只有 4 个在用：INVALID_ARGUMENT、NOT_FOUND、VERSION_CONFLICT、DEPENDENCY_INVALID）；contracts 层校验失败抛裸 `ValueError` → 调用者无法分支处理（`M0-002-B1`） |
| M0-003 ID 与 ref | 第十五条、第八条 | `contracts/ids.py:7`（_PREFIXES，20 类）、`refs.py:12` | ⚠️ ID 由 `ids.py:7` 的 uuid4 生成、前缀映射覆盖 20 类 ✅，但**仓库内没有唯一性/不复用测试**（15 个用例里无此项）；❌ `object_id: str` 无 pattern，**ID 前缀与 `object_type` 互不校验**：`ent_` 开头的 ID 被登记为 `observation`（`M0-003-B1`） |
| M0-004 时间模型 | **第二条**（唯一时间轴；记录时间/事件时间不能混淆） | `contracts/time.py`、`contracts/base.py:23-24`、`sqlite_store.py:278`（写入）与 `:349/:383/:432`（比较） | ❌ tz-naive 被拒 ✅、三类时间字段齐 ✅；但**时区不被归一**：`learned_at` 以带 `+08:00` 的本地串入库存为 TEXT，可见性用 SQL **字典序**比较 → 同一事实按 UTC 记录可见、按东八区记录不可见（`M0-004-B1`）。这直接违反第二条「世界不能靠猜测」，并使 M0-020 H 的「0 泄露」只在时区巧合下成立 |
| M0-005 Revision | 第十三条（不覆盖历史）、第一条 | `base.py:21`（revision ge=1）、`sqlite_store.py:226-235`（单调性校验） | ✅ revision 必须 = latest+1、不覆盖、只追加（`tests/test_store.py:94` 跳号被拒 + 探针复核）；⚠️ `status` 及 session/outcome/experience 状态全为裸 `str`（`M0-005-B1`），"受控迁移"目前只靠调用方自觉 |
| M0-006 版本化引用 | 第八条（向下追溯、自证）、M0-006 H | `refs.py:9-22`、`sqlite_store.py:169`（_collect_refs）、`:229-233`（自证） | ❌ **引用只有 `object_id + revision`**（`refs.py:12-14`），既无 `object_type` 也无「引用产生时的世界版本」→ M0-006 G 要求的「携带类型与来源世界版本」未实现，因此无法验证「该版本在当时确实可见」；✅ ref 不可变（frozen）；另有两点漏洞；**引用本身不含类型与来源世界版本 → `M0-006-B1`**：`revision=None`（最新）可指向自身实现自证（`M0-019-B1`，R1 的 NAC-1）；`dict[str,Any]` 字段里的字典形式引用不被 `_collect_refs` 识别，引用存在性与自证**双双绕过**（`M0-019-B2`） |
| M0-007 Observation | 第五条、第四十三条、第十七条 | `contracts/models.py:28`（Observation）、`tests/test_contracts.py:28` | ✅ raw_data_hash/normalize_method/data_quality/时间三件套齐（比任务书 G 更严）；⚠️ `value: Any` 无约束 → 结论可夹带进原始记录；`source_refs` 默认可空 → 无来源的观察也能登记 → `M0-007-B1`；测试用 `source_refs=[]` 与 G 的 `source_ref` 必填口径不一致（待裁定） |
| M0-008 Claim | **第十二条**（置信针对具体主张）、第七条 | `contracts/models.py:87`（Claim）、`tests/test_contracts.py:45` | ✅ 本轮唯一"完全达成宪法意图"的一单：`claim_type × knowledge_state` 正交，"用户说喜欢咖啡 ≠ 咖啡对他有益"有测试；⚠️ `inferred_preference` 仍被归 `preference` 且置信 0.7，与 M0-008 G 的 `inference` 口径不同（需一致性核对） |
| M0-009 EvidenceSet | 第六条、**第四十六条**（真值隔离） | `contracts/models.py:126`（EvidenceSet）、`sqlite_store.py:76`（唯一落库表 object_revisions） | ❌ 一等对象（selector/成员/coverage/stale）✅、"区间证据一周后仍指原区间"✅；但**成员自身 `learned_at` 不受 selector 时间窗约束** → 未来信息进入证据（`M0-009-B1`，P0）。【已承认】循环检测属 §13 待补项，不重复计 |
| M0-010 Entity/Relation/Summary | 第十五、十八、十九条 | `contracts/models.py:38/46/163` | ⚠️ 证据式身份、aliases、supersedes、`support_refs` 齐 ✅；❌ `source_world_revision: int = Field(ge=0)` 是唯一约束 → 世界版本只到 1 时可提交指向 999 的 Summary（`M0-010-B1`），"总结可展开重建"落空 |
| M0-011 Dimension 三层 | **第二十一条**（生命周期） | `contracts/models.py:56/67/75`、`enums.py`（DimensionLifecycle） | ❌ 枚举 7 态齐 ✅；但 `state_machines.py` 只有 `TASK_TRANSITIONS` 与 `EVENT_TRANSITIONS`，**维度生命周期无转换矩阵**：`RETIRED→ACTIVE` 可直写（`M0-011-B1`）。宪法第二十一条明确要求受控转换 → **需求覆盖缺口**（母表 M0-021 也只冻结了 Task/Event） |
| M0-012 EventAnchor | 第五条、第十三条 | `contracts/models.py:148` | ⚠️ 锚点只存引用、不复制事件内容 ✅；❌ `status=MERGED` 而 `merged_into_ref=None` 可提交（`M0-012-B1`）→ 第十三条"后来为何修正"的链条在契约层可被写成断头 |
| M0-013 Goal | 第三十一、三十二条 | `contracts/models.py:175` | ⚠️ Goal 与 Task 分离 ✅、active_task_refs 必填 ✅；但"用户否认推断目标"只能靠新 revision + `supersedes_refs`，而该语义只有 Event 有一致性校验（`M0-013-B1`）（与 `M0-012-B1` 同源，见 NAC-3） → 单列为 `M0-013-B1` |
| M0-014 Task/Wake/Session/Action/Outcome | 第三十二、三十三条 | `contracts/models.py:197/226/247/256/266` | ❌ 字段符合度最高，但：`deadline` 已过期且早于 `next_wake_at` 不报错；`RUNNING→EXPIRED` 被状态机拒（过期任务只能 FAILED/CANCELLED，`M0-014-B1`）；`task_state` 用枚举 ✅，但 `new_execution_id()`（`ids.py:44`）全库零调用 → M0-014 D 的 execution_id 幂等未接线（`M0-002-B1`） |
| M0-015 Dependency | 第十四条、第十三条 | `contracts/models.py:190` | ❌ **存储侧没有任何依赖表/索引**（全库仅 `sqlite_store.py:241` 提到 evidence/self-cite 文案），成员与依赖关系都埋在 `payload_json` 里；无按 ref 反查 API（`M0-015-B1`）（【已承认】§13）、`reason` 自由文本、边可指向不存在的 revision；叠加 `M0-019-B2`（引用藏在字典里不被扫描）→ **第十四条"必须存在认知依赖关系"在契约层无法保证完整** |
| M0-016 幂等与审计 | 第十三条、第四十五条 | `contracts/operations.py`、`sqlite_store.py:111`（idempotency_records）、`:205`（重放分支） | ❌ 载荷一致的重放 ✅；失败操作零留痕，`operations.error_code/error_message` 无写入路径（`M0-016-B1`）；同幂等键不同载荷被**静默当作重放并返回 ok**、载荷不落库也不报错（`M0-016-B2`），`IDEMPOTENCY_CONFLICT` 成死码 |
| M0-017 schema | 架构唯一写入层 | `sqlite_store.py:60-111`（5 表）、`:49-50`（PRAGMA） | ⚠️ 表结构符合母表 F，WAL 与外键均在 Core 自己连接上打开（`:49`）✅；无 `schema_version` 列（【已承认】迁移框架）；❌ 外键是**每连接 opt-in**：SQLite 默认 `fk=0`，任何不经 Core 的连接都不受约束 → `M0-017-B1`；批量读无分页 → `M0-017-B2` → 直写 `object_revisions` 可造出指向不存在世界版本的孤儿对象（`M0-017-B1`）；且 `payload_json` 无任何 CHECK，可为空字典 |
| M0-018 World Revision | 第二条（唯一时间轴） | `sqlite_store.py:121`（current）、`:191`（commit 内 `BEGIN IMMEDIATE` + 乐观锁） | ✅ 本轮最强项，实测通过：并发双写恰好一个成功、另一个 `VERSION_CONFLICT`，失败方**无半成品残留**（`M0-018-B1`，探针现场执行）；⚠️ 但仓库内没有该测试（M0-018 H 要求"用多线程或双进程"），且 `M0-017-B1` 显示可绕过 revision 直接插入 |
| M0-019 引用验证 | 第八条、第三部分可验证链 | `sqlite_store.py:169`（_collect_refs）、`:191`（`validate_references=True` 默认开）、`contracts/base.py:16`（extra=forbid） | ❌ 校验存在 ✅、"拒绝指向不存在 revision"有测试 ✅；但 `M0-019-B1`（latest 自证）、`M0-019-B2`（字典形式引用绕过 `_collect_refs`）使"M0-019 H：测试集无未发现断裂引用"**不成立**；`validate_references=False` 是随时可关的公开逃生舱 |

**统计**：001–019 中 ✅ 1（M0-008）／⚠️ 7／❌ 11。最成问题的两条主线：**引用契约（006/019）与生命周期（005/011/014）在写入路径上没有强制**。M0-020、M0-021 已随参考实现交付（§13 第 11、12 点），M0-022 Gate 未建 —— 顺便提示：**进度口径"做到 019"与代码已含 020/021 不一致**，请核对记录。

---

### 1.1 测试覆盖实况（15 个用例，3 个文件，全部通过）

`tests/test_contracts.py`（5）· `tests/test_state_machines.py`（4）· `tests/test_store.py`（6）。
其中三处与验收条款直接相关：① `test_learned_at_cutoff_hides_future_known_revision`（`test_store.py:85`）
**只断言 cutoff 时读到旧 revision，未断言列表可见性被隐藏**，与 M0-020 H「无时间快照与 cutoff 快照差异为 0」不对应；
② **无跨时区用例**（M0-004 H 第 2 条要求）→ `M0-004-B1` 因此未被现有测试发现；
③ **无并发写用例**（M0-018 H 要求多线程/双进程）→ 该能力目前只在本次探针中验证过（`M0-018-B1`），**必须补进仓库测试**。

## 2. 缺陷登记（编号 = 主责工单-B\*，按工单顺序）

**编号规则**：`M0-0NN-B<k>`，B 表示 Bug，前缀即主责工单 → 每条可直接据此开修复单、按 §15 模板填字段，不再使用审计自造编号。
「证据」列 `check_*` 在 `audit_m0_probes.py` 可复跑；标 **静态核对** 的是 schema/代码直接可读出的结构缺失（无运行探针）。
级别 P0 动摇实验有效性 ／ P1 破坏可追溯与可修正 ／ P2 工程正确性。
`M0-020-B1`／`M0-021-B1` 的**缺陷代码在 001–019 范围内**（cutoff 读路径、`commit()` 未接状态机），但按母表它们分别归属 020/021 两单，故按其主责单编号，便于直接派工。

| 缺陷编号 | 主责工单 | 级别 | 缺陷 | 违反 | 证据 |
|---|---|---|---|---|---|
| `M0-002-B1` | M0-002 错误码 | P2 | 10 个错误码中 6 个从不抛出；`StoreError(code, message)`(`sqlite_store.py:21-25`) 无 `context`；contracts 校验失败抛裸 `ValueError` | 第十三、四十五条 | `check_m0_002_b1` |
| `M0-003-B1` | M0-003 ID | P2 | ID 前缀与 `object_type` 互不校验：`ent_` 开头的 ID 被登记为 `observation` → 按前缀路由/建索引的假设都不成立 | 第十五条 | `check_m0_003_b1` |
| `M0-004-B1` | M0-004 时间 | **P0** | `learned_at` 入库保留原时区偏移（`sqlite_store.py:278`）存 TEXT，可见性按字典序比较（`:349`、`:383`、`:432` 三个读路径）；`base.py:23` 只要求 tz-aware，不要求 UTC → 同一事实按 UTC 记录可见、按 +08:00 记录 `NOT_FOUND` | **第二条**、M0-020 H | `check_m0_004_b1` |
| `M0-005-B1` | M0-005 Revision | P1 | `WorldObject.status: str = "active"`（`base.py:27`）与 `session_state`/`outcome_state`/`experience_state`/`data_shape` 均为裸 `str`，任意值可写入（`task_state`、`lifecycle` 用枚举 ✅） | 第十三条 | `check_m0_005_b1` |
| `M0-006-B1` | M0-006 引用 | P1 | `ObjectRef` 只有 `object_id + revision`（`refs.py:12-14`），**无类型、无来源世界版本** → M0-006 G 未实现；无法验证「被引版本当时可见」，断链时也报不出类型 | 第八条、M0-006 G | 静态核对 |
| `M0-007-B1` | M0-007 Observation | P2 | `value: Any` 无约束 → 结论可夹带进原始记录；`source_refs` 默认可空 → 无来源的观察也能登记 | 第五、四十三条 | 静态核对 |
| `M0-009-B1` | M0-009 EvidenceSet | **P0** | 成员自身 `learned_at` 不受 selector `knowledge_window` 约束 → cutoff 之后才获知的信息进入证据，Simulated Self 看到未来 | 第六条、**第四十六条**、R2-04 | `check_m0_009_b1` |
| `M0-010-B1` | M0-010 Entity/Relation/Summary | P1 | `Summary.source_world_revision`(`models.py:168`) 与 `Session.snapshot_world_revision`(`:250`) 只校验 `ge=0` → 世界只到 1 时可提交指向 999 / 12345 的悬空快照，「总结可展开重建」落空 | 第十八、十九条 | `check_m0_010_b1` |
| `M0-011-B1` | M0-011 Dimension | P1 | 维度生命周期 7 态**无转换矩阵**：`state_machines.py` 只有 `_TASK_TRANSITIONS`(:6) 与 `_EVENT_TRANSITIONS`(:30) → `RETIRED→ACTIVE`、`CANDIDATE→RETIRED` 可任意写 | **第二十一条** | `check_m0_011_b1` |
| `M0-012-B1` | M0-012 EventAnchor | P1 | `status=MERGED` 而 `merged_into_ref=None` 可提交 → 「后来为何修正」的链条在契约层可被写成断头 | 第十三条 | `check_m0_012_b1` |
| `M0-013-B1` | M0-013 Goal | P1 | 与 `M0-012-B1` 同源：Goal 修订（用户否认推断目标）只有 `supersedes_refs` 字段，无「状态 ↔ 引用」一致性校验 | 第十三、三十一条 | 静态核对（复用 M0-012 探针写法） |
| `M0-014-B1` | M0-014 Task/Wake/Session | P2 | `RUNNING→EXPIRED` 被矩阵拒（过期任务只能 FAILED/CANCELLED）；`deadline` 已过期且早于 `next_wake_at` 不报错；`new_execution_id()`(`ids.py:44`) 零调用 → D 项 execution_id 幂等未接线 | 第三十二、三十三条 | `check_m0_014_b1` |
| `M0-015-B1` | M0-015 Dependency | P2 |【§13 已承认】无按引用反查 API；且 **schema 里没有依赖边表**（5 表：world_meta / world_commits / object_revisions / operations / idempotency_records，`:60-111`），关系全埋在 `payload_json` → 反查只能全表扫 | 第十四条 | `check_m0_015_b1` |
| `M0-016-B1` | M0-016 幂等与审计 | P1 | 失败操作零留痕：`operations.error_code/error_message` 列存在（`:106-107`）但全库无写入路径 → 无法回答「AI 当时怎么得到答案」 | 第十三条、**第四十五条** | `check_m0_016_b1` |
| `M0-016-B2` | M0-016 幂等与审计 | P2 | 同幂等键不同载荷被静默当重放：`_get_idempotent_result`(`:205`) 只读 `result_json` 就返回成功，**完全不比较本次载荷**；`IDEMPOTENCY_CONFLICT` 成死码 | M0-016 G/H | `check_m0_016_b2` |
| `M0-017-B1` | M0-017 schema | **P0** | `PRAGMA foreign_keys=ON` 是**每连接** opt-in(`:49`)：非 Core 连接默认 `fk=0` → 可直写 `object_revisions` 造出指向不存在世界版本（4242）的孤儿对象；`payload_json` 无 CHECK，空字典也落库并被 `get_payload` 读出 → 「所有写入通过唯一 Core 写入层」只靠调用方自觉 | 架构唯一写入层、M0-017 I | `check_m0_017_b1` |
| `M0-017-B2` | M0-017 schema | P2 | 批量读走 `list_payloads`(`:362`) 的 Python 侧组装、无分页参数；测试最大规模 2 条对象 → M0-022 的 500 次回放与 M0-020 批量场景无性能保证 | M0-022、完成定义第 5 条 | 静态核对 |
| `M0-018-B1` | M0-018 World Revision | ⚠️ 行为 PASS | 并发双写恰好一个成功、失败方无半成品残留 `{0: ok, 1: VERSION_CONFLICT}` ✅ —— 但**仓库内没有这个测试**（M0-018 H 要求多线程/双进程），修复时勿把行为改坏 | 完成定义第 3、5 条 | `check_m0_018_b1`（唯一非 GAP 项） |
| `M0-019-B1` | M0-019 引用验证 | P1 | 自证检查只在 `ref.revision == obj.revision` 命中（`:238-242`）→ 写 `revision=None`（latest）即可绕开「必须有来源且不得自证」 | 第八条、M0-006 H | `check_m0_019_b1` |
| `M0-019-B2` | M0-019 引用验证 | P1 | `metadata` / `data_quality` / `maintenance_policy` / `completion_condition` / `payload` / `checkpoint` 等 `dict[str,Any]` 里的**字典形式引用**不被 `_collect_refs`(`:169`) 识别 → 引用存在性与自证双双绕过；`get_payload` 直接 `json.loads` 返回(`:360`)，不做 `model_validate` | 第八条、M0-019 H | `check_m0_019_b2` |
| `M0-020-B1` | M0-020 可见性 | P1 | `test_learned_at_cutoff_hides_future_known_revision`(`tests/test_store.py:85`) 只断言 cutoff 时读到旧 revision，**未断言未来项被隐藏、未断言列表可见性** → 与 H「无时间快照与 cutoff 快照差异为 0」不对应；且全库**无跨时区用例**，所以 `M0-004-B1` 不会被现有测试抓到 | M0-020 H、M0-004 H | 静态核对 |
| `M0-021-B1` | M0-021 状态机 | P1 | 状态机校验器**从未被 `commit()` 调用**：`validate_task_transition(COMPLETED, RUNNING)` 明确禁止，同一转换经 store 却落库成功 → 「受控迁移」在写入路径上未接线 | **第二十一条** | `check_m0_021_b1`（归属见 NAC-5） |

**合计 22 条**（另 1 条待核对口径：`M0-008` 行内注明的 `inferred_preference` 归类问题，不记为 Bug）：
P0 3 条（`M0-004-B1`、`M0-009-B1`、`M0-017-B1`）· P1 11 条 · P2 6 条 · 行为合格但测试缺失 1 条。
其中 `M0-015-B1` 与 `M0-009-B1`／`M0-017-B1` 的相关部分属 §13 **已承认**的待补项，不计为新发现。

## 3. 需要总工裁定（审计不得自行改冻结项）

| 编号 | 事项 | 影响 |
|---|---|---|
| NAC-1 | 「自证」是否允许指向自身最新版本（`revision=None`）；若不允许，需明确 latest 的解析时机 | `M0-019-B1`、M0-006 H |
| NAC-2 | 幂等冲突如何检测：载荷当前不落库，必须先决定是否纳入载荷摘要（哈希）入唯一键 | `M0-016-B2`、`IDEMPOTENCY_CONFLICT` |
| NAC-3 | 「修订即新 revision + supersedes 引用」的一致性校验现在只有 Event 有，是否推广为全对象类型的通用契约 | `M0-012-B1`、M0-013 |
| NAC-4 | `ai_worker / console / evaluator` 骨架与 `aios.data.root` 双挂载的落地时点（宪法第四十四条 vs 母表 M0-001 H） | M0-001、真值隔离 |
| NAC-5 | 生命周期状态机的覆盖范围：是否把 Dimension / Goal / Summary 也纳入 M0-021 的冻结清单 | `M0-011-B1` |

---

## 4. 建议修复顺序（一步一个可关闭 PR）

1. **`M0-004-B1` 时间归一**（改动最小、影响面最大，直接决定所有时间窗口实验有效性）+ 补 M0-004 跨时区测试。
2. **`M0-009-B1` + `M0-019-B1` + `M0-019-B2` 引用与证据闭包**（store 侧校验成员 cutoff；latest 自证规则；禁止 `dict[str,Any]` 承载引用形状，或强制走 `SourceRef/ObjectRef` 类型）。
3. **`M0-017-B1` 写入层强制**（建库期 PRAGMA + 触发器禁止旁路写 + 文档化"写路径"）。
4. **`M0-016-B1` + `M0-016-B2` 审计与幂等**（失败路径必须写 operation 行并返回带 `context` 的 `StoreError`）。
5. **`M0-011-B1` + `M0-012-B1` + `M0-014-B1` + `M0-003-B1` + `M0-005-B1` 契约收紧**（状态改 `StrEnum`；扩展 `TRANSITIONS`；ID 前缀与类型互校；时间字段自洽校验）。
6. **`M0-015-B1` 依赖反查 + M0-022 Gate**（≥50 断言场景 + 4 个 fixture + schema snapshot + 并发写测试入库）。

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
| R2 | 按总工口径改为**逐单 001–019 宪法符合性**；**编号体系改为 `M0-0NN-B<k>`（挂主责工单），废除 R1 自造的 A*/B*/C1**；撤回"M0-001 未开工 = 缺陷"；新增 `M0-019-B2`–`M0-006-B1` 共 14 项探针（17 项检查）；区分【已承认】项；补 NAC-3/4/5；全文 37 处 file:line 锚点脚本核验 |
