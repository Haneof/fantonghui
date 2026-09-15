BLOCKER FOUND

# auditor-e · TRACK=E · M0 Gate 独立红队审计

| 项 | 值 |
|---|---|
| AUDITOR_ID | `auditor-e` |
| TRACK | `E`（Cross-cutting Integration / Unknown-Unknowns，主攻 B10+） |
| 审计日期 | 2026-09-14 |
| exact semantic candidate | `659157b849a0dbaad241c3e316dcd98eb7c72df7` |
| observed production HEAD | `5acef4a4f43895a0762462e1f30e4f923da979a0`（`arena/01a09bc6-fantonghui`） |
| governance HEAD | `44f57611a1305574df9e7e72cddb2ad1d0f7d796` |
| 是否改过生产代码 | 否。`git status` 生产分支未被本审计写入；所有探针在 `/tmp` 临时工作区运行 |
| 结论 | 2 个 BLOCKER（B10、B11）+ 3 个 RULING REQUIRED（B12、B13、B14）+ 1 个观察项（B15）；15 项共同必查全部通过 |

---

## 1. candidate → HEAD 比较结果（要求的第一步）

```
git diff --stat 659157b 5acef4a
 reviews/M0/M0_gate_B8_B9_followup_2026-09-14.md | 99 +++++++++++++++++++++++++
 1 file changed, 99 insertions(+)
```

**ahead-only、纯文档**：候选之后只有 2 个 commit（`d180091` review、`5acef4a` review），无 `src/`、无 `tests/`、无 schema 变更 → 候选仍是当前生产语义 HEAD，本轮审计对候选的结论直接适用于 HEAD。

## 2. CI 独立核验（不采信描述）

| 声明 | 我的核验方式 | 结果 |
|---|---|---|
| run `34831608087` / job `103935994524` 绿 | `gh run view` + `gh api` job 元数据 | `conclusion=success`，`headSha=d180091c…`（= 声称的 source-equivalent archive HEAD）✅ |
| formal 420 passed / 1 known warning | 本地候选全量跑：`PYTHONPATH=src pytest` | **`420 passed, 1 warning in 3.44s`** ✅；该 warning 来自 `test_e23_time_range_mutation`（`tests/unit/test_evidence_set.py:931` 故意把 `EvidenceSelector.time_range` 赋成 str，模型无 `validate_assignment` → pydantic 序列化告警），与「known adversarial warning」一致 |
| Reference 15 passed | `PYTHONPATH=aios_core_r2_reference/src pytest aios_core_r2_reference/tests` | **15 passed** ✅ |
| B8/B9 修复前为红（run `34831346707`，418/2 failed） | 检出 `83a23302ff3c88a409db988059c03e5ec27a7ace` 跑同一测试文件 | **恰好 2 failed**：`test_b8_cross_process_unordered_collection_exact_replay_is_stable`、`test_b9_non_busy_operational_error_with_busy_word_is_not_retryable_lock` ✅ 红→绿链条自证成立 |
| 本地环境差异 | 我这边是 CPython **3.11.2** + pytest 8.4.2；CI 是 3.12.14 + pytest 8.4.2 | 结论未见差异；但见 §6「Gate 证据可移植性」 |

## 3. 新增对抗探针

`governance/agent_reports/m0-parallel-audits/auditor-e-probes.py`（28 项，含 §4 全部最小复现）。运行方式：

```bash
git worktree add --detach /tmp/audit/cand 659157b849a0dbaad241c3e316dcd98eb7c72df7
python3 -m venv /tmp/av && /tmp/av/bin/python -m pip install "pydantic>=2.10,<3" "pytest>=8,<9"
AIOS_SRC=/tmp/audit/cand/src PYTHONPATH=/tmp/audit/cand/src /tmp/av/bin/python /tmp/audit/probes/e_probe.py
# 退出码 = 已确认缺陷数（当前 6）
```

每个用例独立临时库目录（避免世界版本串味）。**未修改任何生产代码或测试**。

---

## 4. BLOCKER

### B10 — 公共写入层不校验「声明类型 ↔ payload 结构」，可写入违反冻结契约的 durable 行

**级别**：BLOCKER（当前 M0 范围内、纯公共 API 可复现、破坏已冻结的「唯一 Core 写入层保证 durable 表示满足冻结契约」不变量，并直接造成 Gate false-green）

**根因**：`normalize_world_object_for_persistence`（`src/aios_core/storage/idempotency.py:80-84`）用 **`type(obj)`** 而非 `obj.object_type` 对应的冻结模型再校验：

```python
snapshot = obj.model_dump(mode="python", round_trip=True)
return cast(TWorldObject, type(obj).model_validate(snapshot))   # ← 类型由调用方决定
```

`commit()`（`sqlite_store.py:447-463`）随后按这个自我校验结果写库，`payload_json` 亦以 `obj.model_dump(...)` 生成（`sqlite_store.py:558`）。二者都信任调用方给出的 Python 类型，没有任何一步把 payload 对着 `object_type` 指向的**冻结契约**校验。

**两条最小复现（都只用公共 API）**

1. 基类伪造 `object_type`：
```python
from aios_core.contracts.base import WorldObject
from aios_core.contracts import ObjectType, Observation
store.commit([WorldObject(object_id="fake_obs", subject_id="u1", learned_at=T0,
                          recorded_at=T0+timedelta(seconds=1), created_by="caller",
                          object_type=ObjectType.OBSERVATION)], operation)          # ← 成功，world +1
Observation.model_validate(store.get_payload("fake_obs"))                            # ← ValidationError：缺 source_kind / modality
```
2. 子类夹带 extra 键（模型未 `final`，`extra="forbid"` 只约束该模型自身）：
```python
class WidenedObservation(Observation): auditor_note: str = "extra"
store.commit([WidenedObservation(...)], operation)          # ← 成功
Observation.model_validate(store.get_payload("wide"))       # ← "Extra inputs are not permitted"
```

**影响契约/文件**：M0-001（契约层是唯一真相）、M0-005（revision 与 payload 结构）、M0-017 D（「所有对象先结构/引用/版本校验再 insert」）、M0-019（引用与结构验证）、M0-022（冻结快照）。文件：`src/aios_core/storage/idempotency.py:80-84`、`src/aios_core/storage/sqlite_store.py:447-463,558`。

**为什么 420 个测试全绿仍漏掉**：
- 全部测试都用**具体模型实例**提交，从不用基类或子类 → `type(obj)` 恰好等于冻结类型，交叉校验的缺口不被触及；
- M0-022 的 schema snapshot 只导出/哈希**各模型自身的 JSON Schema**（`tests/unit/contracts/test_m0_schema_snapshot.py`，实测无任何行为断言）→ 「入库对象是不是那个类」是快照的结构性盲区；
- 架构扫描只禁 Worker 直连 SQLite（`tests/architecture/test_worker_static_policy.py`），不禁「经 Core 写入不自证 payload」。

**最小修复边界**（不改 schema、不做迁移、不动冻结矩阵）：
在 `commit()` 的持久化边界加一步「按声明类型再校验」，与现有 B7 revalidation 同位：
```python
MODEL = MODEL_BY_TYPE[obj.object_type]            # 契约层显式映射，勿运行时推导
MODEL.model_validate(canonical_json_value(obj))   # 不接受子类 extra：round-trip 必须是该模型的合法输入
```
并要求 `type(obj) is MODEL_BY_TYPE[obj.object_type]`（或以 `model_config` 允许子类但显式丢弃未声明字段——**二者必须择一，属契约决定**）。失败统一 `StoreError(ErrorCode.INVALID_ARGUMENT, reason="declared_type_payload_mismatch")`。补 2 个测试即上面两条复现。

### B11 — durable 读取路径把内部异常直接抛给调用方，违反 M0-002 H「禁止只有 traceback」

**级别**：BLOCKER（协议边界缺口；且与 B10 串联后**无需改库即可自我砖化**）

M0-002 H 要求「所有协议级失败都有 code + message + context；禁止只有 traceback 或 HTTP 500」。四个站点在真实失败下抛裸异常：

| # | 位置 | 触发 | 实测 |
|---|---|---|---|
| 1 | `sqlite_store.py:362` `Dependency.model_validate(...)`（`_validate_dependency_graph`） | durable 里存在一行 `object_type='dependency'` 而 payload 不合契约——**B10 的基类伪造即可写入** | `commit()` 抛裸 `ValidationError`；此后**该库所有 Dependency 写入永久失败**，错误中无任何 `CoreErrorCode` 可分支（探针 `e_spoofed_dependency_bricks_later_commit`） |
| 2 | `sqlite_store.py:238` `CommitResult.model_validate(result_json)` | 携带 pre-B6 形状 `result_json` 的库（`object_refs` 缺失） | 裸 `ValidationError: object_refs Field required`（探针复现 (ii)） |
| 3 | `idempotency.py:155-157` `RuntimeError("idempotency record references missing operation")` | 审计行与幂等记录不一致（人工/导入/未来清理） | 裸 `RuntimeError`（探针复现 (i)） |
| 4 | `idempotency.py:46-50` + pydantic 序列化 | `arguments`/`Any` 字段里放一个业务对象（`dict[str, Any]` 全部接受） | 裸 `PydanticSerializationError: Unable to serialize unknown type` |

第 1 条最严重：**它使 B10 从「可写坏行」升级为「一次坏行即砖掉整条写入路径」**，且失败不可分类 → Worker/重试引擎只能崩退出或把永久性损坏当可重试错误反复重放（正是 Track E 关心的「error classification + future retry behavior」交互）。

**影响契约**：M0-002（错误码契约）、M0-016（审计与幂等）、M0-017（H：异常模拟后数据库必须一致且可诊断）、M0-015。

**为什么没被抓到**：现有测试只在**内存对象层**构造非法输入（走 pydantic 构造期，抛错符合预期），从不构造「durable 行本身不合契约」的场景；B5 的错误边界只覆盖了 `sqlite3` 异常，没有覆盖「Core 自己再校验 durable payload」这条路径。

**最小修复边界**：不改分类语义（B9 的 result-code 判定保持），只在三处 durable 读取点包裹并转译：
- `_validate_dependency_graph` 的 `model_validate` 失败 → `StoreError(STORAGE_FAILURE, reason="durable_dependency_row_invalid", context={object_id, revision})`（明确「不要自动跳过坏行继续放行」，否则 B3 环检测被静默削弱）；
- `CommitResult.model_validate` / `stored_request_fingerprint` 的 `RuntimeError` → `STORAGE_FAILURE / durable_record_inconsistent`；
- `canonical_json_value` 的不可序列化 → 在 `commit()` 早期转 `INVALID_ARGUMENT`（与 §5 B15 一并裁定）。
外加 3 个回归测试。**不得**顺手加 migration 框架（那是 M1 已承认范围）。

---

## 5. RULING REQUIRED

### B12 — 重放身份是否包含 `operation_id`？（权威文本互相矛盾）

同一 `idempotency_key`、内容完全相同的等价请求，仅 `operation_id`（一次尝试的 id）不同 → `IDEMPOTENCY_CONFLICT / request_fingerprint_mismatch`，而该写入其实已生效（world=1）。崩溃丢回执后换 attempt id 重试，**必然**收到冲突，而不是原回执。

- M0-016 A：「所有世界修改带 operation_id/…/idempotency_key，并**能够安全重试**」；H：「重试无重复副作用，审计可查」；
- B6 裁决（`CURRENT_STATE.md`）：「幂等身份 = 与持久化表示相同的归一化结果」——而 `operations.operation_id` 是主键，故身份**必然**含它；
- 另外现文案 `idempotency key was already used for a different request` 在此场景为**假**（同一请求，不同尝试）。

需要 chief-01 裁定：(a) 身份含 attempt id → 则 M0-016 A 的「安全重试」应显式限定为「同 attempt id 重试」，并把文案改为 `attempt_id_mismatch`；或 (b) 身份不含 attempt id（只覆盖语义字段）→ B6 裁决需要限定「持久化表示」的范围。**我不建议**在不裁定的情况下改代码。

### B13 — 生命周期矩阵只活在 helper，持久化层不强制

`validate_task_transition(COMPLETED, RUNNING)` 明确非法，但 `commit()` 不调用任何状态机（`grep -n state_machines src/aios_core/storage/` → 0 命中），非法迁移直接落库（Dimension 等更无矩阵）。

- M0-021 H：「非法转换明确报错；合法转换完整覆盖」——按 helper 口径**已满足**；
- M0-017 D：「所有对象先结构/引用/版本校验再 insert」——是否把状态迁移算作「结构校验」，文本未言明。

请裁定：M0 是否要求**持久化边界**强制冻结矩阵。若答案为否，请在母表 M0-021/M0-005 明确写「M0 不强制写入层迁移校验，由 M2 服务层负责」，以免 Gate 把 helper 级证据当行为证据。

### B14 — `set` 与有序 `list` 在归一后不可分辨（B8 归一的直接后果）

`{"seq": {"a","b"}}`（无序语义）与 `{"seq": ["a","b"]}`（有序语义）归一为同一 canonical JSON → 同一指纹。实测第二个请求收到 `idempotent_replay=True` 的成功回执，而 Core 从未按「有序请求」处理它。因 durable 字节完全相同，**不丢数据**；顺序不同（`["b","a"]`）会正确判为不同请求并冲突（已验证 ✅）。
需要裁定 M0 立场：接受「Core 的 Any 字段不承载集合有序性语义」并写进契约注释，或为有序性引入显式包装类型（改 schema → 属 `NEEDS_ARCH_CHANGE`，不可顺手做）。

### B15 — 非 JSON 标量被静默有损转换（观察项）

`arguments={"c": 1+2j}` → 落库为 `{"c": "1+2j"}`（string），无错误、无诊断。指纹在转换后计算，故重放自洽；但「提交值 ≠ durable 真值」。若 M0 认为 Any 字段应严格 JSON-only，需在 `commit()` 早期报 `INVALID_ARGUMENT`（与 B11 第 4 站同处）。

---

## 6. 15 项共同必查的实测结果（全部通过）

| # | 必查项 | 探针 | 结果 |
|---|---|---|---|
| 1 | stale exact replay 先于 expected-world rejection | `e_replay_precedes_version_conflict` | ✅ 返回原回执 `world_revision=1`，未吞成 VERSION_CONFLICT |
| 2 | 同 key 不同请求必须冲突 | `e_same_key_different_request` | ✅ `IDEMPOTENCY_CONFLICT/request_fingerprint_mismatch` |
| 3 | 跨进程 / 不同 `PYTHONHASHSEED` 重放稳定 | `e_cross_process_replay_stability` | ✅ 4 seed（1/7/12345/random）全部 `replay=True`；改集合成员 → 正确冲突 |
| 4 | 失败赋值后的脏 `OperationRequest` 不得入审计 | `e_dirty_operation_not_persisted` | ✅ `operation_name=""` 拒改后，durable 行仍为干净快照 |
| 5 | busy 分类必须按 SQLite result code | `e_real_busy_is_version_conflict` | ✅ 真实持锁写入 → `VERSION_CONFLICT/storage_busy`，`sqlite_errorcode=5`，世界版本未动 |
| 6 | 非锁故障即使文本含 busy/locked 仍为 `STORAGE_FAILURE` | `e_text_trap_is_storage_failure` | ✅ 用 `raise_abort('database is locked')` 触发文本陷阱 → `STORAGE_FAILURE/sqlite_operational_error`（B9 修复有效） |
| 7 | 失败事务原子回滚四类记录 | `e_late_failure_atomicity` | ✅ 在 `idempotency_records` AFTER INSERT 注入失败 → world=1，`world_commits/object_revisions/operations/idempotency_records` 均无残留 |
| 8 | floating/current 自引用必须拒 | `e_self_reference_rules` | ✅ `DEPENDENCY_INVALID` |
| 9 | `X@2 → X@1` 历史 pinned 自链必须仍合法 | 同上 | ✅ 正常提交 |
| 10 | EvidenceSet typed refs 服从自身 frozen cutoff | `e_evidence_frozen_cutoff` | ✅ cutoff 之后的成员被拒 `NOT_FOUND/reference_not_visible_or_missing`（R4 落地） |
| 11 | 同事务合法互引不得误杀 | `e_same_tx_mutual_refs` | ✅ Claim↔EvidenceSet 同事务通过 |
| 12 | Dependency 拒环、Relation 有环不得误杀 | `e_dependency_vs_relation_cycle` | ✅ Dependency 环 `DEPENDENCY_INVALID`；Relation 环允许 |
| 13 | world_revision 与 knowledge_cutoff 组合 | `e_dual_lens` | ✅ 三向组合均正确收敛（含列表侧） |
| 14 | Task/Event 冻结矩阵未漂移 | `e_matrix_no_drift` | ✅ `git diff f38fdd2..candidate` 对 `state_machines.py`/`enums.py` 为 0 文件 |
| 15 | schema snapshot 只作结构证据 | `e_schema_snapshot_scope` | ✅ 快照测试仅结构 hash，未冒充行为证明；但其**结构性盲区已被 B10 利用**（见 §4） |

**Gate 证据可移植性（附带发现）**：`test_b8_cross_process_unordered_collection_exact_replay_is_stable` 用 `sys.executable -c "import aios_core…"` 起子进程但不传 `PYTHONPATH`，只靠 CI 的 `pip install -e ".[dev]"` 才能 import；在干净检出上直接 `python -m pytest` 会因 `ModuleNotFoundError` 而**假红**（我第一次复现就撞上）。建议给该测试显式注入 `env={"PYTHONPATH": str(Path("src").resolve())}`，或改用 `importorskip` + 安装态断言，使独立复核者得到与 CI 相同的结果。（这是测试可移植性缺陷，不是生产语义缺陷。）

---

## 7. 残留风险与后续 Gate 归属

| 项 | 归属 | 说明 |
|---|---|---|
| EvidenceSet 全量 world 快照 / selector 物化 | **M1-006** | 候选只做 typed-ref 在自身 frozen cutoff 的可见性，未声称物化能力，符合 R4 边界 |
| Dependency 反向索引与纠错传播 | **M3** | `collect_impacted_dependents` 是内存 helper，注释已声明非持久索引；不构成 M0 blocker |
| Session snapshot+cutoff 绑定、`recorded_at` 伪防 | **M1/M2** | 主裁定（`recorded_at` = 受控记录时间，物理时间 = `world_commits.committed_at`）与实现一致；M1 摄入侧尚未存在 |
| 迁移框架 / 旧库兼容 | **M1** | B11 的第 2、3 站根因在此；M0 未发布可不做 migration，但**必须**把「坏行」变成协议错误（B11 修复），否则携带临时库的演示路径不可诊断 |
| hostile Python sandbox | 已明确 defer | `trusted reviewed-code Worker` 口径与 `tests/architecture/*` 静态策略一致，未见过度声明复发 |
| opaque dict 伪引用不进引用校验 | M0 边界内可接受 | M0-019 H 只约束 typed refs；实现一致（探针 `e_validate_reference_bypass_via_replay` 记为 INFO），但应在 M1 的 payload 契约里显式化 |
| `operations.error_code/error_message` 只有 `committed` 路径 | **M1**（M0-016 待补） | 列存在但无写入路径；M0-016 G 未要求失败留痕测试，故不判为违反；建议在 M1 摄入失败留痕时一并关闭 |

## 8. 是否建议重开此前的 FINAL PASS

- **建议重开**：`M0-002`（错误协议边界仍有裸异常出口）、`M0-005`、`M0-017`（durable 结构校验未覆盖「声明类型 ↔ payload」）、`M0-022`（Gate 证据：快照结构性盲区 + B8 测试可移植性）。
- **不建议重开**：`M0-015`（其在有界 M0 范围内仍成立：环检测、同事务互引、Relation 不误杀，均实测通过）、`M0-009`/`M0-019` 的 R4 修复（第 10 项实测通过）、`M0-016` 的 B6/B8 重放语义（第 1/2/3 项实测通过；B12 属需裁定的语义选择，不是回归）。

## 9. 边界声明

- 本报告**不宣布** M0 FINAL PASS、不宣布 M1 START、不授权并行核心开发：最终 Gate 权仅属 `chief-01`。
- 本审计未修改生产分支任何文件；未更新 `governance/agent_reports/architect-01/LATEST.md`；未覆盖任何其他 auditor 报告（`m0-parallel-audits/` 此前在库中不存在）。
- `ARCHITECTURE PASS` 在本轨不成立；B10 与 B11 修复并各自补测试后，我可在同一天内对新候选复审并给出 E 轨结论。
