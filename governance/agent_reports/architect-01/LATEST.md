BLOCKER FOUND

# architect-01 — M0 Gate 正式独立复审

agent_id: architect-01  
role: Principal Architect / Architecture Red Team  
task: M0 GATE FOLLOW-UP PATCH INDEPENDENT RE-REVIEW  
status: BLOCKER FOUND  
working_branch: governance/aios-control-plane  
base_commit: 95cec4142bdd9a87011bbad197e05ec1d27aeb57  
head_commit: 268d403836b107a1969a9a5d8b85e4955baec9bf（被审生产 candidate，不是报告提交）  
production_files_changed: NONE  
test_result: exact candidate 本地 formal 405 passed / 1 known warning；独立探针 31 passed / 2 deliberate mutation warnings  
reference_result: 独立设置 Reference PYTHONPATH 后 15 passed  
ci_status: candidate run 34823226166 / job 103909332923 SUCCESS，经 GitHub 原始日志核验  
requested_chief_action: 保持 M0 Gate 未通过；处理 B6/B7、B5 未闭合项和 R4 裁决后再复审。  
报告更新提交可由本文件 Git 历史定位；不把它与生产 candidate 混为一谈。

## 1. Verdict 与边界

本轮发现可复现的基础错误，不能给 ARCHITECTURE PASS：

- **B6（新，High / BLOCKER）**：B1 fingerprint 在重试时读取未规范化输入，却从首次提交的规范化结果重建原请求；同一已成功输入可以在重启后被错误判为 IDEMPOTENCY_CONFLICT。
- **B7（新，High / BLOCKER）**：OperationRequest 的 after-validator 赋值失败不回滚字段，store 又不重新验证 operation，因而冻结契约禁止的空白 reason 可成功写入 durable audit。
- **B5 未完全关闭**：连接建立在异常包装的 try 外，可泄漏 raw OperationalError；内部 SQL/schema 故障被宽泛归为 INVALID_ARGUMENT，错误恢复类别需要正式裁决。

B1 的普通 JSON 精确请求比较已修复，B3/B4 原始漏洞已关闭；这不抵消 B6/B7。B2 trusted-reviewed-code 和 R3 双透镜后续绑定裁决有任务书依据，本轮接受其明确范围。修正上一轮把同进程非沙箱能力直接定为 M0 blocker 的过强判断，不要求 M0 引入 hostile-code sandbox。

EvidenceSet 的成员/窗口不一致已实测，但其 M0/M1 enforcement 分界有两种有文本依据的解释，列为 **R4 — RULING REQUIRED**，不静默降为普通 residual，也不假装已证明必须在 M0 实现完整 Evidence service。

最终 M0 FINAL PASS 权限属于 chief-01。本报告没有修改生产实现，没有自行修补后批准，没有进入 M1。

## 2. 实际证据与基线

直接 git fetch GitHub 仓库 `Haneof/fantonghui`，在 detached worktree 检查 `268d403836b107a1969a9a5d8b85e4955baec9bf`。本轮治理 HEAD 观察值为 `afcd92459a9ed3941811152c45e7b7c4d8acf4c5`。

| 项目 | 独立核验结果 |
|---|---|
| 原 candidate | 95cec4142bdd9a87011bbad197e05ec1d27aeb57，是本轮 candidate 祖先 |
| 本轮 candidate | 268d403836b107a1969a9a5d8b85e4955baec9bf |
| production archive | 83577317e96224f9cdb271a8a835a4e48f3aa78c；相对 candidate 仅 TASK_PROGRESS_R2.md 变化 |
| B1/B3 | 8ab574c6b33b2238b468c812992a92ba56ab3f71 在祖先链中；fingerprint 文件先由 6d519bd1398b21f9a59b18df2905d306effb6a8a 引入 |
| B2 | e06bc80e43ea26be2be726232158cb2719092f11 在祖先链中，新增静态政策测试 |
| B4/B5 | a99326c5034118b3a497e3be0d53ac9466445467 在祖先链中 |
| 268d403 diff | 只修改 tests/unit/test_world_revision_atomicity.py 的异常预期及说明；没有改变生产语义 |
| 原 candidate 到本轮 production diff | 仅 storage/idempotency.py 和 storage/sqlite_store.py；contracts/query/dependency helpers/state machines/schema 均无 diff |
| 第一轮报告 | c6b0191797ab3ef06b4ee031003431a0d9527d48，仅作为待验证输入 |
| 另一红队 | 42f19a3f39a1e4ac375ac315d6dcf8f487725830 的报告，读取其 B4/B5/R3、residual 与定级分歧 |

本轮读取/定位的治理文件：AGENTS.md、CONTROL_PANEL、CURRENT_STATE、ACTIVE_ASSIGNMENTS、REQUEST、REREVIEW_REQUEST、PRINCIPAL_ARCHITECT_RED_TEAM、AGENT_REPORT_PROTOCOL，以及本对话前轮已读取的 ROLE_REGISTRY / MODEL_ROUTING_POLICY / MULTI_AGENT_POLICY。当前授权明确允许独立复审并替换本报告。

本轮重新核对的权威章节：宪法/R1/R2 的隔离、时间、证据与冻结条款；R2 §5.2/5.3；权威 taskbook §0.3、M0-001/002/006/009/015/016/017/018/019/020/021/022、M1-006，以及 Session/M2 绑定条款。没有把前轮“全部源码已读”的广泛声明当成本轮证明；本轮重点是 patch 全文、未变模块对照和完整回归。

重点源码/测试：storage/idempotency.py、sqlite_store.py；contracts/base.py、models.py、operations.py、errors.py；query/history.py、dependency/graph.py、services/state_machines.py；tests/unit/test_m0_gate_blockers.py、test_m0_gate_followup.py、test_operations.py、test_world_revision_atomicity.py、test_history_m020.py、M0-019 / EvidenceSet / Dependency / state-machine tests；tests/architecture/test_boundaries.py、test_worker_static_policy.py；snapshot test 和四个 fixture。

Chief reviews 已从真实生产树读取：

- reviews/M0/M0_gate_blocker_resolution_2026-09-14.md
- reviews/M0/M0_gate_followup_B4_B5_R3_2026-09-14.md
- M0-009/016/017/020/021 的冻结 review（前轮读取与本轮涉及章节复核）

## 3. CI、失败归因与本地运行

| 证据 | 结果 |
|---|---|
| run 34823226166 / job 103909332923 | checkout 268d403...；CPython 3.12.14、Pydantic 2.13.5、pytest 8.4.2；405 passed / 1 warning；Reference 15 passed；SUCCESS |
| run 34822952167 / job 103908457587 | checkout 6adacd45c0ed6392017742365d9c9850b75ee0c4；404 passed / 1 failed / 1 warning；Reference skipped |
| exact candidate 本地 | CPython 3.12.14 / pytest 8.4.2；formal 405 passed / 1 warning；Reference 使用自身 src PYTHONPATH 后 15 passed |
| 独立探针 | 31 passed / 2 deliberate warnings；其中若干测试是“断言漏洞仍存在”，绝不代表 31 个 invariant 全部成立 |

失败 run 的唯一失败是 `test_w02_failed_mid_insert_rolls_back_the_entire_world_transaction`：触发器确实抛 `sqlite3.IntegrityError: forced M0-018 mid-transaction failure`，新的 `_connection` 将其包装为 StoreError，而旧测试只捕获 raw IntegrityError。268d403 保留了五表 rollback/no-gap 断言，只改预期异常类型及 code/reason。**“旧测试期待过时”这一窄解释成立；“所有 B5 错误分类已经正确”不由此成立。** 失败 run 本身未走到异常上下文后的 rollback 断言，不能单靠它证明原子性；本轮通过完整绿色测试与额外故障探针验证了该点。

测试命令：

```sh
python -m pytest tests -o addopts='' -q
PYTHONPATH=aios_core_r2_reference/src python -m pytest aios_core_r2_reference/tests -o addopts='' -q
PYTHONPATH="$PWD/src" python -m pytest /path/to/redteam_reaudit.py -q -s
```

附录提供独立探针全文。探针初版因 `contracts.__all__` 导致 wildcard import 缺少名称而失败；改成显式 import 后再运行。该初版失败是审计 harness 错误，未计作生产问题。

## 4. B1 复审：普通路径关闭，B6 仍阻止整体关闭

逐字段独立改变 operation_id、session_id、operation_name、arguments、expected_world_revision、reason：均 IDEMPOTENCY_CONFLICT，且比较 world_meta/world_commits/object_revisions/operations/idempotency_records 五表，状态逐项不变。

改变对象 ID/集合/revision/payload：均拒绝。arguments 字典键顺序与 objects 输入顺序改变：仍可 replay。正常 exact retry 在旧 expected revision 检查前 replay，重开 store 后相同。两个同步起跑的 same-key/different-request writer：一个成功，另一个 IDEMPOTENCY_CONFLICT，世界只推进一次。

从原 95cec41 store 实现创建的旧格式数据库（相同当前模型，模型文件未变）在新 store 上正常 replay，并拒绝 altered payload；未运行 ALTER/migration。重建正常 durable JSON 请求时，operation row 加该 world revision 的所有对象确实足够，因为一次 world commit 对应唯一 operation。

但“重建等价于原始请求”只在序列化输入与持久化输出相同的前提下成立。此隐藏前提被 B6 推翻。

### B6 — pre-validation fingerprint 与 post-validation durable payload 不一致

分类：**BLOCKER / High**。受影响 candidate：268d403...；引入比较路径的 patch：8ab574c...，fingerprint 文件 6d519bd...。受影响冻结契约：M0-016 safe retry、M0-009 persistence normalization；需重开/保持 M0-016 reopened，不必改世界对象字段。

最小复现：

1. 创建合法 Observation o@1 并提交。
2. 创建合法 EvidenceSet es，随后执行 `es.coverage.observed_count = "1"`。EvidenceCoverage 未开启 validate_assignment，此操作不报错。
3. `store.commit([es], request)` 成功；durable revalidation 将字符串 `"1"` 规范化为整数 `1`，存储 payload 为整数。原来的 es 实例未被修改，仍含字符串。
4. 重启 store，再次 `commit([es], 同一 request)`，返回 IDEMPOTENCY_CONFLICT。

机制：idempotency `_object_entries()` 使用传入 obj.model_dump_json()；原请求 fingerprint 从 durable object_revisions 重建，该 payload 来自 `type(obj).model_validate(obj.model_dump(...))` 的新实例。第一次没有 key 时不计算/存储 incoming identity，也没有检验规范化前后是否一致。因而同一被接受请求对应两个 fingerprint。

现有测试为什么没抓住：B1 tests 都使用规范化后的普通 Observation；M0-009 mutation tests 只检查非法值被拒绝，没有检查“可被 coercion 接受的 mutation”成功后重试。serializer warning 不使第一次提交失败，不能当作拒绝证据。

M1–M8 风险：崩溃/网络丢回执后调用方无法恢复同一已成功操作，可能转用新 key 或进入错误恢复路径。当前实现并未重复写入，但破坏 safe exact retry 的基础承诺。

最小修复边界：Chief 选择一致的 identity 规则。推荐将可接受输入规范化与 durable request identity 固定为同一表示；如果必须严格保留当前 replay→expected→full validation 顺序，可在首次写入拒绝会改变 durable serialization 的未规范化输入，或持久化原请求 identity 并制定显式兼容策略。不能只在发生 conflict 后把所有 mismatch 吞掉。新增 coercible nested mutation、重启 replay、同 payload 不同内存表示测试。任何验证顺序改变必须明确复审，不能为了 B6 破坏 stale replay。

### B7 — OperationRequest 赋值校验失败后仍可落库

分类：**BLOCKER / High（durable audit contract）**。受影响 commit：M0-016 cdbd7ff1d42ba292a2e0ca9972f0c9eccd4666c3 至本轮 candidate 均保留此路径；本轮新增发现，不是 B1/B3 patch 新引入。文件：contracts/operations.py、storage/sqlite_store.py、tests/unit/test_operations.py。

最小复现：

```python
r = op()
try:
    r.reason = " "
except ValidationError:
    pass
assert r.reason == " "
store.commit([obs()], r)  # 成功
assert store.operation_record(r.operation_id)["reason"] == " "
```

Pydantic after-validator 在赋值后抛错，并不恢复旧字段。store 只重验 WorldObject，不重验 OperationRequest；空白 reason 满足 SQLite NOT NULL，成功写进 operations 和 world_commits。相同机制可影响使用 after-validator 检查的空白身份字段。

现有 `test_o04_validate_assignment_keeps_frozen_operation_identity_valid` 只断言赋值抛错，不检查异常后对象状态或持久化拒绝。因此测试名/结论强于证据。

违反 M0-016 的非空白 identity/reason 契约，破坏 M1–M8 操作审计可信性。最小修复：对 operation 做一致的不可变快照及必要的边界重验证，或在字段写入前校验/冻结请求；保留精确 replay 优先规则，测试失败赋值后 commit、嵌套 arguments mutation、成功审计行 round-trip。保持 M0-016 reopened；不是要改变错误枚举。

## 5. B2、B3、B4

### B2 — CLOSED NOW（当前威胁模型声明）；M1 wiring 仍强制 Gate

taskbook M0-001 §C 明确允许 import-lint 或测试扫描，§D 明确模块化单体，§F 无业务 API、只冻结模块依赖。§0.3 不要求微服务。M0-017 §I 禁止 Worker 获得 connection，解释为 reviewed production wiring 禁止注入 capability 与上述文字一致；它没有要求在 M0 执行不可信 Python。

README §6 原本已明确“代码架构政策检查，不是操作系统级安全沙箱”；本轮新增 test_worker_static_policy 与 Chief review 明确同一范围。旧 M0-017 review 的“因此没有暴露”只能作为历史窄主张，不能再当 sandbox proof；新裁决已明确取代更强措辞。本轮检索没有发现新增文档继续宣称恶意 Python 技术上绝对无法绕过。

静态 scanner 确实检查 __import__('sqlite3')、importlib.import_module('aios_core.storage') 及常见 importlib 别名。旧 test_boundaries scanner 本身仍只检测静态 import，新测试补充该缺口；不能混淆两者。任意计算字符串、辅助模块、依赖注入等不是其可完备证明范围。Worker 当前只有 docstring，未发现生产注入路径；这只证明当前无 wiring，不证明未来安全。

M1 启用 Worker I/O 前检查 DB path/Connection/store/raw-read capability 的所有构造、参数、闭包和返回值路径；不把 HistoricalWorldQuery 的可选 cutoff 直接暴露为安全 AI query。执行 untrusted Python 前必须重新做真实隔离 Gate。

### B3 — CLOSED NOW（标准 Dependency 模型的当前 exact-version graph）

实测 same-tx 两边/三边环、跨提交两边/三边环全部 DEPENDENCY_INVALID，五表不变。Dependency d@2 替换 d@1 时，图按 latest durable + pending replacement 计算，旧 edge 不错误残留；新闭环仍拒绝。并发反向边使用同一 expected snapshot 时一个成功、另一个 VERSION_CONFLICT；输家刷新 expected 后补环则 DEPENDENCY_INVALID。

exact-version distinction 实测 a@1→b@1→a@2 可提交，这是 exact graph 中的非环，不应按 stable ID 误杀。普通 Relation 环与 generic Holder 之间 mutual refs 仍合法。全套 Dependency/Relation tests 通过。

判环位于 BEGIN IMMEDIATE 内、writes 前，仅针对 isinstance(Dependency) 的 pending 模型和 durable Dependency rows；未加入 M3 reverse index/自动修正。当前图判环不能等同“所有历史版本和所有高层 provenance 自证都已解决”；M1 构造标准模型/生成依赖边，M3 独立依据和跨 revision 增信规则仍必须 Gate。未来不能允许用非标准 WorldObject 子类伪装 Dependency 绕过这一 dispatch；当前 production wiring 未提供该入口。

### B4 — CLOSED NOW

现有 Claim ObjectRef、SourceRef tests 通过；新增 generic typed Holder floating self 测试拒绝并逐表比较零 mutation。统一 recursive collector 的 guard 在 lookup/pending fallback 前拒绝 same object_id 的 None/current revision。历史 X@2→X@1 成功；已有 cutoff tests 验证历史目标仍需可见。两个不同 stable IDs 的 same-tx mutual refs 成功，不把整个世界图变成 DAG。

## 6. B5 — 部分修复，不能整体关闭

已关闭：operation_id 已提交后换 key → IDEMPOTENCY_CONFLICT；真实 BEGIN IMMEDIATE 锁重叠 → VERSION_CONFLICT / storage_busy；mid-insert trigger abort 完全 rollback；解除锁/删除故障 trigger 后同请求正常提交、不消耗 revision。

额外进程故障：独立子进程在第一个 object INSERT 实际完成、transaction 尚未 commit 时 os._exit(77)。重开数据库五表与故障前相同；同请求可在 world revision 1 成功。该测试是 crash-before-commit，不声称覆盖 fsync、电源丢失或所有 commit syscall 边界。

### B5-a — raw connect failure（未关闭，BLOCKER / Medium）

`SQLiteWorldStore(tmp_path / 'missing' / 'x')`（父目录不存在）抛出 raw sqlite3.OperationalError。`sqlite3.connect(...)` 在 `_connection` 的 try 之前，不受新 mapping 覆盖；每次读写都重新连接，因此已创建 store 的底层路径变得不可用也有同类风险。修复范围：a99326c... 的 `_connection` 连接生命周期，含安全 close/初始化错误。无需改变数据库 schema。现有 lock test 只让 BEGIN IMMEDIATE 失败，未攻击 connect。

### B5-b — 非 lock 故障被归为 INVALID_ARGUMENT（RULING REQUIRED）

在 disposable DB 中移除 operations 表以模拟 schema 损坏/不匹配，然后提交完全合法请求：返回 StoreError(INVALID_ARGUMENT, reason=sqlite_operational_error)，cause 为 no such table。此请求参数无错；刷新或改请求无法修复内部 schema。该 fault injection 不声称正常用户能通过公开 API 删除表，而是攻击明确要求的基础设施故障分类。

source `_connection` 将所有 IntegrityError 和非 lock OperationalError 一概映射 INVALID_ARGUMENT；sqlite3.DatabaseError 的其他子类也未统一处理。锁判定基于错误文本中的 locked/busy 子串，而非 SQLite result code，不能作为完备分类。

冲突来源：M0-002 §A 要求可机器分支、避免错误恢复；B5 当前 patch 却把内部实现故障归到输入错误。冻结 ErrorCode 没有明确 INTERNAL/STORAGE_FAILURE 类别。

方案 A：正式扩充协议，区分 storage unavailable/internal/corruption 与 invalid request，保留诊断 cause；优点恢复语义明确，代价需重开 M0-002/schema snapshot。

方案 B：维持 ErrorCode 集合，但正式定义非输入故障的 envelope/context 和停止/重试规则，并要求所有 consumer 按该契约分支；代价是 code 单独不再足够，不能仍称 INVALID_ARGUMENT 为纯输入错。

推荐 A，至少不得把 no-table/read-only/disk/I/O 故障默认为可通过修改请求修复。chief 必须选择；未实现的 M2 retry engine 不使当前错误分类自动正确。B5-a 可独立修复，B5-b 裁决需先于 frozen protocol 关闭。

## 7. R3 与 R4

### R3 — ACCEPTABLE M0 RESIDUAL — M1 GATE / M2 GATE

精确 P6 前提“recorded_at 比 learned_at 更早”不能经正常模型+store 写入：base.validate_times 要求 recorded_at >= learned_at；本轮实测模型拒绝，不能偷偷绕验证构造后声称正常 API 漏洞。

真正可行的等价攻击：现在 commit 一个 learned_at=明天、recorded_at=后天的对象（committed_at 是物理提交时间）。只传 world revision 会返回它；只传今天 cutoff 则隐藏它。另在 world 2 新增 learned_at=今天的回填对象，cutoff-only 会看到，但 world 1 + cutoff 不可见。双透镜严格交集成立。

taskbook M0-020 §D 明确“后续 query 服务包装”，M0-020 review 接受独立透镜。没有找到要求删除 M0 内部单透镜 API 的原文，因此接受 Chief scope。M1 public historical AI view 必须双绑定，M2 每次 Session read 必须沿用固定 world+knowledge boundary，refresh 必须显式。当前 HistoricalWorldQuery 可省略 cutoff，不能直接把这个 facade 当作已满足上述 public Gate。

### R4 — EvidenceSet 成员/冻结窗口一致性：RULING REQUIRED

实测：o@1 learned_at=10:00；es learned_at=10:00、knowledge_window.cutoff=09:00、world_revision=1、member_refs=[o@1]。commit(es) 成功；但用 es 自己的双透镜读取 o@1 会 NOT_FOUND。不是普通 query 双透镜实现出错，而是 durable EvidenceSet 自称的窗口与成员矛盾。

source 只检查 es.cutoff<=es.learned_at；store refs 全用 es.learned_at，而不是 es.cutoff。member/support/counter/context 均经同一宽窗口处理。现有 E13 只比较 cutoff 与 EvidenceSet 本身 learned_at，没比较成员。

冲突来源：R2 §5.3 要保存“当时的信息截止时间”和“成员版本或可重建成员集合”；M0-006 §D 要存储引用在 cutoff 内可见；另一方面 M0-009 review 明确 world_revision 只是 round-trip、M1-006 才负责真实赋值；M1-006 §C/D 明确 selector 按 cutoff 材料化并冻结 world/cutoff。

方案 A：M0 durable boundary 对 EvidenceSet 成员使用 frozen cutoff，另裁决 same-tx world_revision（不能简单禁止所有当前 pending refs）；修复现存自相矛盾 snapshot，需重开 M0-009/019。

方案 B：M0 仅保存待服务验证的结构，M1-006 负责成员时间/世界范围/角色一致性，所有消费者在该 Gate 前不得信任或展开此为有效 proof；允许后移但必须明确标识未验证状态与禁止使用规则，不能继续泛称 durable EvidenceSet 已具可复核快照保证。

推荐 A 对 learned cutoff 先做最小约束，并正式裁决 same-tx world semantics；若 Chief 选择 B，需书面缩窄当前 guarantee、冻结 M1-006 验证入口。本轮不单方面选择一种解释“消掉”冲突。此问题前轮已作为 residual 出现，故不冒称全新 B 编号。

## 8. M0 全局 regression

| 领域 | 结论与限制 |
|---|---|
| M0-009 顺序 | 当前仍 replay/conflict → reused operation_id check → expected world → WorldObject revalidation → revision/type → reference → Dependency graph → writes。B6 暴露前后表示不一致，B7 暴露 operation 未重验；没有把它们误报为所有对象重验失效 |
| M0-018 | 一事务一 world、object +1、mid-insert rollback、无 gap、stale writer/race、crash-before-commit 均通过 |
| M0-019 | missing ref、same-tx、mutual non-proof、floating/current self、历史 pinned self 回归通过 |
| M0-020 | exact object/world/cutoff 交集通过；mutable subject 在选择最新可见 revision 后过滤，无旧 subject resurrection；public binding 留待 R3 Gate |
| M0-021 | 完整矩阵及 revision helpers 通过。generic store 可绕 helper 的事实仍在，按 taskbook/冻结 non-goals，由 M1 Event 和 M2 Task service 强制调用；未声称 storage 已强制 domain transition |
| Claim/Entity/Relation/Goal/active contracts | 全套回归通过，production contract 文件未改；不声称测试证明语义真值、Goal 达成或外部动作效果 |
| Structural snapshot | 候选文件与原 candidate 未变，测试通过。独立在内存将 _reference_exists 改为永远 True 后 snapshot 完全相同，实证 behavioral false-green；未改任何 production 文件 |

四个 mandatory fixture 均绿，解释边界如下：sports-day 证明 Event revisions 可读，不证明多模态证据推理或持久边界强制 transition；unknown-person 证明 nullable name/alias 保存，不证明身份消解；future-prediction 证明指定类型 round-trip，不证明语义防升格；Goal/Task 证明 Task 完成不自动改 Goal，不证明 assess_progress 正确。它们满足 M0 的具名 fixture 要求，不能用作 M1/M2 服务的替代 Gate。

## 9. 十项 residual 分类（全部列出）

| 项目 | 分类 | 必须执行的后续边界 |
|---|---|---|
| 1 EvidenceSet member learned_at vs cutoff | RULING REQUIRED | R4；world_revision/same-tx 与角色/coverage 一并明确。不能自动接受前轮 residual 标签 |
| 2 ObjectRef/SourceRef endpoint type | ACCEPTABLE M0 RESIDUAL — M1 GATE | 本轮实测 Claim.support_evidence_set_refs 指向 Observation 可提交；M1 各 typed service 验证端点类型和标准模型 registry，禁止非标准子类冒充正式类型 |
| 3 plain dict pseudo-ref | ACCEPTABLE M0 RESIDUAL — M1 GATE | 本轮实测 metadata 内 missing dict ref 可存；opaque data 不自称 ref，但 consumer 一旦解释成引用必须转正式类型并重验，禁止旁路 provenance |
| 4 recorded_at ownership | RULING REQUIRED | committed_at 是实际物理 clock，recorded_at 目前由调用方提供且必须>=learned。预载未来资料与“实际写入时间”字面冲突须定所有权；建议保留物理 committed_at、明确模拟时间/导入时间，M1 ingestion 不允许任意伪造知识时间 |
| 5 open-string status | ACCEPTABLE M0 RESIDUAL — M2 GATE | Outcome UNKNOWN/Session 状态、Task/Action 恢复词汇须在 runtime 启用前冻结；M1 Evidence/Goal service 先约束其状态/判定，不能把 Task complete 当 Goal achieved |
| 6 schema behavioral false-green | ACCEPTABLE M0 RESIDUAL — M1 GATE | 当前仅称 structural snapshot；未来每个 invariant 有直接 adversarial test 和 code review；不要求纯 JSON Schema 承担行为证明 |
| 7 reverse index/correction propagation | ACCEPTABLE M0 RESIDUAL — M3 GATE | durable exact graph 判环只解决当前显式 edges；M1 正确生成依赖，M3 独立依据、跨 revision 自证、stale/rebuild 与修正传播都必须验证 |
| 8 CI dependency drift | ACCEPTABLE M0 RESIDUAL — M1 GATE | 当前依赖范围 pydantic>=2.10,<3 / pytest>=8,<9，ubuntu-latest/action tags 非锁定。该次 3.12.14/2.13.5/8.4.2 已核验，不能推广到未来；M1 建可重放锁定/版本升级回归政策 |
| 9 Worker raw-read future capability | ACCEPTABLE M0 RESIDUAL — M1 GATE | B2/R3 production wiring review 必须在任何 Worker world I/O 前完成；static scanner 不是 capability proof |
| 10 Session snapshot+cutoff | ACCEPTABLE M0 RESIDUAL — M2 GATE | 固定双透镜贯穿每次读取及恢复，显式 refresh；跨 world 写入不得自动扩大 Session 可见范围 |

recorded_at 裁决的 competing options：A 按物理入库由 store 赋值，则未来 learned 预置须改变模拟 ingestion/时间 invariant；B 明确它是调用方/虚拟时间轴的记录时刻，以 world_commits.committed_at 单独表示物理提交，需更新术语和生产入口约束。推荐 B 保留模拟器能力，但必须正式说明，不能把两者混用。关联 M0-004/005/020，尚未因本轮修改任何字段。

## 10. 给 chief-01 的明确下一步

1. M0 不签 FINAL PASS，M1/并行施工继续暂停。
2. 保持 M0-016 reopened，修 B6 fingerprint normalization 和 B7 operation persistence validation，分别增加独立回归，保持 exact stale replay 优先。
3. 完成 B5-a 连接生命周期异常边界；对 B5-b 非输入存储故障分类正式裁决，需要时重开 M0-002，不以“无 raw exception”替代语义判断。
4. 对 R4 EvidenceSet 窗口及 recorded_at 所有权发正式 ruling，写清 M0 当前保证与 M1 consumer 前置 Gate。
5. B2/B3/B4 可记录为本轮已验证的窄关闭项，不能藉此关闭整个 M0。
6. 取得新 exact candidate 全量与 Reference CI，保留失败 run，邀请下一次独立复审。不要只更新 snapshot/改异常测试使其变绿。

## 11. 审计限制与可复现附件

没有修改生产源码、现有测试或冻结文档。独立探针只在临时 DB/子进程中执行；持久化的交付只有此报告。没有实测设备断电、磁盘物理损坏、所有 SQLite Error subclass、超大图压力或任意不可信 Python。故障注入/当前 graph 测试不代表这些情况已获证明。

以下脚本应保存为独立 `redteam_reaudit.py`，从 exact candidate 根目录以 PYTHONPATH=src 运行。`test_old_database_replay` 的旧源码路径需指向另一个 exact 95cec41 checkout；其它测试不需要旧 worktree。31 tests 包含对已确认缺陷的正向断言，未来转生产回归时应改为期待修复后的不变量。


```python
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import sqlite3
import json
import pytest
from pydantic import ValidationError
from aios_core.contracts.models import Observation, Dependency, EvidenceSet
from aios_core.contracts.refs import ObjectRef
from aios_core.contracts.enums import ObjectType, ErrorCode
from aios_core.contracts.time import KnowledgeWindow
from aios_core.contracts.operations import OperationRequest
from aios_core.contracts.base import WorldObject
from aios_core.contracts.models import EvidenceCoverage
from aios_core.storage import SQLiteWorldStore, StoreError

T=datetime(2026,9,14,10,tzinfo=timezone.utc)
def common(i, **kw):
    return dict(object_id=i,subject_id='s',learned_at=T,recorded_at=T,created_by='audit',**kw)
def obs(i='o',**kw):
    return Observation(**common(i),source_kind='test',modality='text',value=kw.pop('value','v'),**kw)
def op(n=0,k='k',**kw):
    d=dict(operation_id=k,session_id='s',operation_name='commit',arguments={'a':1,'b':2},expected_world_revision=n,reason='audit',idempotency_key=k);d.update(kw);return OperationRequest(**d)
def dep(i,a,b,rev=1):
    return Dependency(**common(i,revision=rev),dependent_ref=ObjectRef(object_id=a,revision=1),dependency_ref=ObjectRef(object_id=b,revision=1),dependency_type='proof')
def state(s):
    with sqlite3.connect(s.db_path) as c:
        return [c.execute('SELECT * FROM '+t).fetchall() for t in ('world_meta','world_commits','object_revisions','operations','idempotency_records')]
def reject(s,objects,request,code):
    before=state(s)
    with pytest.raises(StoreError) as e:s.commit(objects,request)
    assert e.value.code==code
    assert state(s)==before
    return e.value

@pytest.mark.parametrize('field,value',[('operation_id','other'),('session_id','other'),('operation_name','other'),('arguments',{'a':2}),('expected_world_revision',99),('reason','other')])
def test_identity(tmp_path,field,value):
    s=SQLiteWorldStore(tmp_path/'x');o=obs();r=op();s.commit([o],r)
    reject(s,[o],r.model_copy(update={field:value}),ErrorCode.IDEMPOTENCY_CONFLICT)
@pytest.mark.parametrize('change',['id','revision','value','set'])
def test_object_identity(tmp_path,change):
    s=SQLiteWorldStore(tmp_path/'x');o=obs();r=op();s.commit([o],r)
    altered={'id':[obs('p')],'revision':[o.model_copy(update={'revision':2})],'value':[obs(value='changed')],'set':[o,obs('p')]}[change]
    reject(s,altered,r,ErrorCode.IDEMPOTENCY_CONFLICT)
def test_order_restart(tmp_path):
    s=SQLiteWorldStore(tmp_path/'x');a,b=obs('a'),obs('b');r=op();s.commit([a,b],r);s=SQLiteWorldStore(tmp_path/'x');before=state(s)
    assert s.commit([b,a],r.model_copy(update={'arguments':{'b':2,'a':1}})).idempotent_replay
    assert state(s)==before
def test_samekey_race(tmp_path):
    a=SQLiteWorldStore(tmp_path/'x');b=SQLiteWorldStore(tmp_path/'x');bar=Barrier(2)
    def run(pair):
        s,i=pair;bar.wait()
        try:s.commit([obs(i)],op(operation_id=i));return 'ok'
        except StoreError as e:return e.code.value
    with ThreadPoolExecutor(2) as ex:results=list(ex.map(run,[(a,'a'),(b,'b')]))
    assert sorted(results)==['IDEMPOTENCY_CONFLICT','ok'];assert a.current_world_revision()==1
@pytest.mark.parametrize('length',[2,3])
@pytest.mark.parametrize('split',[False,True])
def test_cycles(tmp_path,length,split):
    s=SQLiteWorldStore(tmp_path/'x');ids=['a','b','c'][:length];s.commit([obs(i) for i in ids],op())
    ds=[dep('d'+str(n),i,ids[(n+1)%length]) for n,i in enumerate(ids)]
    if split:s.commit(ds[:-1],op(1,'first'));ds=ds[-1:]
    reject(s,ds,op(s.current_world_revision(),'cycle'),ErrorCode.DEPENDENCY_INVALID)
def test_edge_revision_and_race(tmp_path):
    s=SQLiteWorldStore(tmp_path/'x');s.commit([obs('a'),obs('b'),obs('c')],op());s.commit([dep('d','a','b')],op(1,'edge'))
    s.commit([dep('d','a','c',2),dep('e','b','a')],op(2,'replace'))
    reject(s,[dep('f','c','a')],op(3,'cycle'),ErrorCode.DEPENDENCY_INVALID)
def test_competing_edges(tmp_path):
    s=SQLiteWorldStore(tmp_path/'x');s.commit([obs('a'),obs('b')],op());stores=[SQLiteWorldStore(tmp_path/'x') for _ in range(2)];bar=Barrier(2)
    edges=[dep('d','a','b'),dep('e','b','a')]
    def run(i):
        bar.wait()
        try:stores[i].commit([edges[i]],op(1,str(i)));return 'ok'
        except StoreError as e:return e.code.value
    with ThreadPoolExecutor(2) as ex:res=list(ex.map(run,range(2)))
    assert sorted(res)==['VERSION_CONFLICT','ok']
    loser=res.index('VERSION_CONFLICT');reject(s,[edges[loser]],op(2,'retry'),ErrorCode.DEPENDENCY_INVALID)
class Holder(WorldObject):
    link:ObjectRef
def test_holder_self_mutual_history(tmp_path):
    s=SQLiteWorldStore(tmp_path/'x')
    def holder(i,ref,revision=1):return Holder(**common(i,revision=revision),object_type=ObjectType.OBSERVATION,link=ref)
    reject(s,[holder('a',ObjectRef(object_id='a'))],op(),ErrorCode.DEPENDENCY_INVALID)
    s.commit([holder('a',ObjectRef(object_id='b')),holder('b',ObjectRef(object_id='a'))],op())
    s.commit([holder('a',ObjectRef(object_id='a',revision=1),2)],op(1,'history'))
def test_failure_after_insert_and_recovery(tmp_path):
    s=SQLiteWorldStore(tmp_path/'x')
    with sqlite3.connect(s.db_path) as c:c.execute("CREATE TRIGGER fail BEFORE INSERT ON object_revisions WHEN NEW.object_id='b' BEGIN SELECT RAISE(ABORT,'audit failure'); END")
    reject(s,[obs('a'),obs('b')],op(),ErrorCode.INVALID_ARGUMENT)
    with sqlite3.connect(s.db_path) as c:c.execute('DROP TRIGGER fail')
    assert s.commit([obs('a'),obs('b')],op()).world_revision==1
    assert SQLiteWorldStore(s.db_path).commit([obs('a'),obs('b')],op()).idempotent_replay
def test_busy_recovery(tmp_path):
    s=SQLiteWorldStore(tmp_path/'x');s.SQLITE_BUSY_TIMEOUT_MS=10
    with sqlite3.connect(s.db_path) as c:
        c.execute('BEGIN IMMEDIATE');e=reject(s,[obs()],op(),ErrorCode.VERSION_CONFLICT);assert e.context['reason']=='storage_busy';c.rollback()
    assert s.commit([obs()],op()).world_revision==1
def test_evidence_cutoff_counterexample(tmp_path):
    s=SQLiteWorldStore(tmp_path/'x');o=obs();s.commit([o],op())
    es=EvidenceSet(**common('es'),purpose='past snapshot',knowledge_window=KnowledgeWindow(knowledge_cutoff=T-timedelta(hours=1),world_revision=1),member_refs=[ObjectRef(object_id='o',revision=1)],selection_method='explicit')
    s.commit([es],op(1,'es'))
    with pytest.raises(StoreError):s.get_payload('o',revision=1,as_of_world_revision=1,knowledge_cutoff=es.knowledge_window.knowledge_cutoff)
    print('R4: persisted EvidenceSet includes member learned AFTER its frozen cutoff')
def test_fingerprint_normalization_counterexample(tmp_path):
    s=SQLiteWorldStore(tmp_path/'x');s.commit([obs()],op())
    es=EvidenceSet(**common('es'),purpose='proof',knowledge_window=KnowledgeWindow(knowledge_cutoff=T),member_refs=[ObjectRef(object_id='o',revision=1)],selection_method='explicit')
    es.coverage.observed_count='1'
    r=op(1,'es');s.commit([es],r)
    assert s.get_payload('es')['coverage']['observed_count']==1
    reject(SQLiteWorldStore(s.db_path),[es],r,ErrorCode.IDEMPOTENCY_CONFLICT)
    print('B6: identical accepted input fails replay after persistence coerces nested value')
def test_sqlite_nonlock_counterexamples(tmp_path):
    with pytest.raises(sqlite3.OperationalError):SQLiteWorldStore(tmp_path/'missing'/'x')
    s=SQLiteWorldStore(tmp_path/'x')
    with sqlite3.connect(s.db_path) as c:c.execute('DROP TABLE operations')
    with pytest.raises(StoreError) as e:s.commit([obs()],op())
    assert e.value.code==ErrorCode.INVALID_ARGUMENT
    print('B5: connect failure RAW OperationalError; missing internal table classified INVALID_ARGUMENT')
def test_double_lens(tmp_path):
    s=SQLiteWorldStore(tmp_path/'x');future=obs().model_copy(update={'learned_at':T+timedelta(days=1),'recorded_at':T+timedelta(days=2)})
    s.commit([future],op());assert s.get_payload('o',as_of_world_revision=1)
    with pytest.raises(StoreError):s.get_payload('o',as_of_world_revision=1,knowledge_cutoff=T)
    s.commit([obs('late')],op(1,'late'));assert s.get_payload('late',knowledge_cutoff=T)
    with pytest.raises(StoreError):s.get_payload('late',as_of_world_revision=1,knowledge_cutoff=T)
    with pytest.raises(ValidationError):Observation.model_validate(future.model_dump()|{'recorded_at':T})

def test_exact_revision_graph_is_not_stable_id_dag(tmp_path):
    s=SQLiteWorldStore(tmp_path/'x');a=obs('a');b=obs('b');s.commit([a,b],op())
    s.commit([a.model_copy(update={'revision':2})],op(1,'rev2'))
    d=dep('d','a','b');e=dep('e','b','a');e.dependency_ref=ObjectRef(object_id='a',revision=2)
    s.commit([d,e],op(2,'exact'))
    # a@1 -> b@1 -> a@2 is not a cycle on exact versions.
    assert s.current_world_revision()==3
def test_old_database_replay(tmp_path):
    import importlib.util
    spec=importlib.util.spec_from_file_location('old_store','/workspace/scratch/82c41c0036ab/candidate/src/aios_core/storage/sqlite_store.py')
    old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
    r=op();o=obs();old.SQLiteWorldStore(tmp_path/'x').commit([o],r)
    s=SQLiteWorldStore(tmp_path/'x');assert s.commit([o],r).idempotent_replay
    reject(s,[obs(value='altered')],r,ErrorCode.IDEMPOTENCY_CONFLICT)
def test_process_crash_after_object_insert(tmp_path):
    import multiprocessing
    import os
    from contextlib import contextmanager
    s=SQLiteWorldStore(tmp_path/'x');before=state(s)
    def child():
        class CrashStore(SQLiteWorldStore):
            @contextmanager
            def _connection(self):
                with super()._connection() as conn:
                    class Proxy:
                        def __getattr__(self,n):return getattr(conn,n)
                        def execute(self,sql,*args):
                            result=conn.execute(sql,*args)
                            if 'INSERT INTO object_revisions(' in sql:os._exit(77)
                            return result
                    yield Proxy()
        CrashStore(s.db_path).commit([obs('a'),obs('b')],op())
    p=multiprocessing.get_context('fork').Process(target=child);p.start();p.join(10)
    assert p.exitcode==77;assert state(s)==before
    assert s.commit([obs('a'),obs('b')],op()).world_revision==1
def test_operation_mutation_protocol(tmp_path):
    s=SQLiteWorldStore(tmp_path/'x');r=op()
    with pytest.raises(ValidationError):r.reason=' '
    # Pydantic after-validator failure does not roll back assignment.
    assert r.reason==' '
    s.commit([obs()],r)
    assert s.operation_record('k')['reason']==' '
    print('B7: OperationRequest failed assignment still persists: reason blank')
def test_structural_snapshot_false_green(monkeypatch):
    import runpy
    m=runpy.run_path('tests/unit/contracts/test_m0_schema_snapshot.py');build=m['build_current_snapshot'];before=build()
    monkeypatch.setattr(SQLiteWorldStore,'_reference_exists',lambda *a,**kw:True)
    assert build()==before
def test_endpoint_and_opaque_dict(tmp_path):
    from aios_core.contracts.models import Claim
    from aios_core.contracts.enums import ClaimType, KnowledgeState
    s=SQLiteWorldStore(tmp_path/'x');s.commit([obs()],op())
    c=Claim(**common('c'),claimant_id='ai',claim_type=ClaimType.HYPOTHESIS,content='x',asserted_at=T,knowledge_state=KnowledgeState.HYPOTHESIS,confidence=.2,support_evidence_set_refs=[ObjectRef(object_id='o',revision=1)],metadata={'fake_ref':{'object_id':'missing','revision':1}})
    s.commit([c],op(1,'claim'))
    assert s.get_payload('c')['support_evidence_set_refs'][0]['object_id']=='o'

```
