# VERDICT: BLOCKER FOUND

## Exact candidate 与审计范围

- Repository：`Haneof/fantonghui`。
- 本轮唯一 candidate：**`b6588bdaaa36d9dace4f9959dda0a89a370e1674`**。
- Candidate branch：`arena/integrator-typedref-replay-20260914`；PR #5 仍 OPEN / draft / 未合并。
- Production：`arena/01a09bc6-fantonghui`，仍为 `8dd96ab767c6d359728da2d64a49e47642c93b31`。
- **没有修改 candidate、production 或 PR #5 实现；没有 merge，没有启动 M1。** 在外部 detached worktree 只读执行，结束时 candidate 工作树干净，src/tests 逐文件与 Git 对象比较无差异。证据见 `evidence/source-verification.json`。
- 会话受固定分支限制，审计提交只推到 `arena/01a09fa9-fantonghui`。该分支以旧被拒候选524为底，仅新增本轮审计文件，**不是把 b658 的实现合入该分支**。
- 人员独立性限制：本会话曾参与更早修复，不能计作未参与开发的第三方独立签字。本轮测试为重新建立的只读 adversarial suite，未修改被测实现。

## 新冻结证据，不是原100项

旧 `524f4d99...` 的原100项 artifact 已确认不可恢复。本套件**不是原件，不声称复跑了原100项，也不是为了凑100项而重建的脚本**。

新文件：`test_adversarial_b658.py`。

**执行前 SHA-256：**

```text
180dc1bac647e6cee6688dd4475dab8a063cc9fa9545acdc0e907036e9bea97d
```

证据顺序：

1. `2026-09-14T14:46:55.774672+00:00`：完成文件，计算 SHA-256，写入 `FREEZE.json`；未收集、未执行。
2. `194638c1306f65865626e27b76ad36fde53f8e60`：将冻结测试、FREEZE、runner 提交并推送 GitHub，commit 时间 `14:49:00Z`。
3. `14:55:25Z` 开始首轮执行：先检查 SHA，再 `pytest --collect-only`，再运行新套件、正式套件、Reference。
4. 收集和执行后再次检查 SHA，完全一致。
5. `818f19b841fe7287111c1675c0c435955314ba84`：首轮完整日志已提交并推送，随后才进行兼容版本复跑和结果解释。
6. Pydantic 2.10.6 复跑同一个文件，仍为相同 SHA，未修改 expected outcome、参数、skip 或 xfail。

**完整收集数是394，不是100。** 两个版本的 `collect-only.log` 均包含完整 node IDs；两个版本均无 collection error、skip、xfail 或 warning 汇总。

补充 `observe_findings.py` 仅记录具体返回与 canonical-validation 对照，不计入394项，也不替代契约断言。该脚本亦在执行前单独计算 SHA，执行后校验未变；原始输出保存在 `evidence/observations.json`。

## 环境与精确执行结果

| 环境 | 新套件收集 | 新 red-team suite | 正式 suite | Reference |
|---|---:|---|---|---|
| **CPython 3.12.14 / Pydantic 2.13.5 / pytest 8.4.2** | **394** | **17 failed / 377 passed**，7.36s | **526 passed**，7.89s | **15 passed**，0.25s |
| **CPython 3.12.14 / Pydantic 2.10.6 / pytest 8.4.2** | **394** | **17 failed / 377 passed**，7.62s | **1 failed / 525 passed**，8.49s | **15 passed**，0.32s |

每轮完整输出、命令、退出码、前后测试 SHA、版本、pip freeze 均在 `evidence/pydantic-<version>/`。

CPython 由官方 `python/cpython` 的 `v3.12.14` 源码构建，GCC 12.2.0，SQLite 3.40.1，glibc 2.36；整数转换默认上限4300位。由于环境下载与系统开发包限制，该本地构建缺少可选 `_ssl` 模块；测试 wheels 由已有下载环境取得，再离线安装至3.12虚拟环境。这里不是完整网络/SSL运行时认证；所有394项、526项及Reference实际在该3.12.14解释器下运行，不拿3.11结果代替3.12证据。

### Pydantic 2.10.6 已知 schema snapshot 差异

candidate 唯一正式失败为：

```text
tests/unit/contracts/test_m0_schema_snapshot.py::test_m0_schema_snapshot_matches_frozen_contract
```

另对原始 **524f4d99...** 的正式套件在同一 CPython 3.12.14 / Pydantic 2.10.6 下重新执行：**1 failed / 485 passed**，唯一失败也是该 schema snapshot。完整输出：`evidence/baseline524-pydantic210-formal.log`。

**不把此差异算成 X1–X4 修复回归，不据此单独新增 blocker，也未修改 frozen snapshot。** 它是已知的跨工具链 schema hash 重现性限制。

## CI 核验与证据持久化

重新通过 GitHub API 核验 run **34853601694**、job **104007394770**：head SHA 为精确 b658，conclusion 为 success。元数据保存在 `evidence/candidate-ci.json`。

本轮没有把既有 CI success 当成通过结论；本地重新执行得到526+15通过，同时新394项出现17项失败。

尝试新增专用审计 Actions workflow 时，GitHub 拒绝 push，原因是当前连接没有 `workflows` 写权限；该 workflow **未发布**，也未留在最终审计提交中。随后采用用户允许的“GitHub 分支持久化”途径。这里没有声称新394项已有远程Actions运行，也没有伪造 artifact。

固定审计分支现有默认 CI 若显示绿色，其含义仍取决于原 workflow；**不能将其解读成新394项全绿**。本套冻结执行结果是附带的完整本地3.12日志。

## 覆盖与历史约束重新反证

`evidence/test-groups.json` 提供逐函数的两个版本相同计数。

| 领域 | 本轮结果与边界 |
|---|---|
| X1 modern typed/opaque 双向身份 | **24 passed**：16项双向分离/重启/stale exact replay，8项 marker spoof；ObjectRef、SourceRef × metadata/value/arguments/selector.filters |
| legacy 身份 | **17 passed / 6 failed**：pure JSON exact、incoming typed fail-closed 通过；反向 typed→opaque 未关闭，见 X5 |
| X2 序列化/协议 | **80 passed**：surrogate、无效bytes、unsupported object、巨大整数、NaN/±Infinity、list/dict cycle、1500层嵌套 ×4位置×fresh/retry |
| X3 nested extras | **8 passed**：多层 extra='allow'、model_copy改变extra、无损持久化、altered retry冲突 |
| dirty unknown fields | **8 passed / 8 failed**：普通rogue正确拒绝；下划线未知字段静默消失，见 X6 |
| X4 ref revision | **96 passed**：字符串1规范化、None合法引用、malformed/negative/zero/fraction/list拒绝；两个ref类型、四位置、fresh/retry |
| dirty OperationRequest routing | **34 passed**：28项非法revision/id/key，6项可规范化标量；含key bytes/list/None/empty/blank/surrogate，未泄漏SQLite binder异常 |
| B1 plain changed data | **4 passed**；legacy/dirty未知字段仍造成false replay，故整体不能关闭 |
| B4 / cutoff | **40 passed**：missing/current pinned self/floating self/cutoff ×两个ref×五种容器；不将safe unsupported ref-set rejection误算为绕过 |
| B6 规范化 | 字符串revision、bytes/string、tuple/list、共享非循环别名均通过；无序容器持久化正常形式重放 **3 failed**，见 X7 |
| B10 canonical dispatch | **13 passed**：extra-allow外层、dirty discriminator、base impersonation；下划线dirty未知字段见 X6 |
| B11 Mapping keys | **48 passed**：6类非字符串key×4位置×fresh/retry，均受控且零写入 |
| restart / hash seeds | 另有**1 passed**，执行3个子进程，seed 37/179/991，set-of-frozenset exact replay，完整数据库行不变 |

这不是宣称每种 Python 对象、每种历史数据库和所有M0行为已穷尽。

## 新 findings

以下使用 REDTEAM-X5、X6、X7，避免冒充旧X1–X4或占用Chief的全局B编号。17个失败用例归于三个问题，不称为17个独立blocker。全部源码位置绑定 b658。

### REDTEAM-X5 — legacy typed→opaque 仍 false replay

**Severity：HIGH / M0 blocker。6个冻结用例失败。**

**Invariant：**B1 的 materially different request 必须冲突；本轮明确要求 legacy 无法重建 typed semantics 时 fail closed，且不得在任一方向 typed/opaque false replay。

**复现：**旧成功请求在 Any 中携带真实 ObjectRef/SourceRef；旧 idempotency row 无 `_request_fingerprint`；重启后用相同 key、旧 expected_world_revision，将该引用换成相同形状的 opaque dict。

**Actual：**metadata、value、arguments，两个ref类型全部返回 `idempotent_replay=True`，没有 IDEMPOTENCY_CONFLICT。

这不只是人工删字段的fixture结果：补充观察程序实际调用**旧524实现创建数据库**，再让b658打开；旧 typed `ObjectRef(anchor@1)` 的请求，改为opaque dict重试仍返回成功。旧opaque→opaque对照也成功。`observations.json` 保留实际返回和状态摘要。

**Expected：**对不能证明语义等价的历史行返回 IDEMPOTENCY_CONFLICT；普通、不含歧义引用形状的pure JSON exact replay继续工作。

**Root cause：**`storage/idempotency.py:613–620` 仅检查**incoming**请求中是否还有typed ref；incoming已经换成dict时，进入旧有损JSON fingerprint。`storage/sqlite_store.py:250–275` 的legacy fallback无法知道旧提交的原始类型，于是匹配并重放。

**Atomicity：**6项false replay均未改变world revision或四张表；问题是错误认定同一请求并返回旧成功，不是重复插入。

**Minimum repair boundary：**处理的是历史信息不足，而非多做一次incoming遍历。需要明确的legacy歧义识别/迁移/版本化策略，不能把丢失的类型凭空恢复。特别是“所有ref-shaped opaque历史请求必须可重放”与“旧typed→opaque必须拒绝”，在旧数据完全同形且没有额外证据时不能同时保证。应由Chief冻结如何处理歧义行；不能以仅拒绝incoming typed宣称双向关闭。无歧义pure JSON可继续兼容。

### REDTEAM-X6 — `_` 前缀未知dirty字段仍被静默删除

**Severity：HIGH / M0 canonical-boundary blocker。8个冻结用例失败。**

**Invariant：**B10的canonical schema才是权威；X3修复要求dirty model-copy字段不得在验证前静默消失，X4要求ref leaf也重新验证。四种模型均为extra='forbid'。

**最小复现：**

```python
dirty = clean.model_copy(update={'_rogue': 'payload'})
store.commit([dirty], request)
```

针对 Observation、OperationRequest、nested ObjectRef、nested SourceRef 分别执行fresh/retry。

**Actual：**fresh四项都接受并完整提交；同key添加该字段的四项altered retry都返回旧成功。

**独立对照：**四个模型的 `__private_attributes__` 均为空；`_rogue` 真正在 `vars(dirty)` 中，不是声明过的PrivateAttr。将同一完整字段快照交给各自canonical `model_validate(dict(vars(dirty)))`，四项均返回 `ValidationError / extra_forbidden`。普通 `rogue` 字段则在本套8项对照中被store正确拒绝。

**Expected：**fresh返回INVALID_ARGUMENT，existing-key返回IDEMPOTENCY_CONFLICT，并保持零写入。不能通过名字以 `_` 开头就替canonical schema过滤掉提交字段。

**Root cause：**`storage/idempotency.py:47–62` 的 `_model_items` 在59行无条件跳过 `key.startswith('_')`；unknown dirty值在canonical revalidation前消失，outer model及ref leaf都看不到它。

**Atomicity：**四个fresh请求从world revision 1变2，并写入四张表；这是**本应拒绝的请求被完整提交**，不是事务写一半。四个false replay保持完整状态不变。冻结测试的finally检查捕获了前者，未被“没有抛异常”掩盖。

**Minimum repair boundary：**区分真实声明的private/internal模型状态与调用者通过model_copy注入的未知字段。不可用整个下划线命名空间作为跳过canonical验证的后门；也不应把合法PrivateAttr误当成durable输入。保持accepted extras、ref语义与递归key规范。

### REDTEAM-X7 — 新semantic identity额外区分无序容器与其durable正常形式

**Severity：MEDIUM / B6 normalization blocker。3个冻结用例失败。**

**Invariant：**`reviews/M0/M0_gate_B6_B7_B5_R4_resolution_2026-09-14.md` §2.1 明确：identity使用与实际持久化相同的规范化表示；已经成功且可规范化的同一请求，不能仅因Python内部表示不同而在restart后冲突。typed refs具有明确的额外引用验证语义；本反例**没有typed ref**。

**复现：**value/metadata/arguments写入 `{'unordered': frozenset({'alpha','beta'})}`，读取store实际持久化的JSON值，再以该正常形式、原operation/key/expected revision重试。

**Actual：**第一次正常提交，durable值为 `{'unordered': ['alpha','beta']}`；正常形式重试返回 IDEMPOTENCY_CONFLICT / `request_fingerprint_mismatch`。

实际fingerprints：

```text
frozenset request: 3c952577263c1c13b22129b6192483e61a1f19cc142ebbce42689e03d215dd8d
durable-form retry: 4797cee3f3353b1e5a8f17a5c9fa1bd5a818da7bcbb08c0a299515ce98b9ad79
```

**Expected：**相同无引用durable正常形式应exact replay。这里不是拿任意Python `==` 当协议等价，也不是把重新排序的list当同一请求，而是直接用store自己的排序持久化输出。

**Root cause：**`storage/idempotency.py:433–465` 将set/frozenset编码为 `$set`，list/tuple编码为 `$sequence`；durable JSON则都存为数组。typed-ref修复把其他容器种类也提升为身份语义，超出了已冻结的正常形式兼容约束。

**Controls：**原始set-of-frozenset跨进程seed稳定性通过；bytes/string、tuple/list正常形式通过。故不是普通restart或hashseed排序失败。

**Atomicity：**3项失败重试均完整状态不变，没有写入。

**Minimum repair boundary：**在保留真实ref类型标记及marker-spoof分离的同时，使无引用容器的durable normalization与identity一致。若Chief确实打算将“unordered容器种类”新增为冻结的请求语义，需显式修订B6兼容边界并说明老请求迁移，不能只以当前实现不同为其正确性依据。

## Atomicity 汇总

所有新套件的预期拒绝通过同一个 `reject()` helper：以finally比较 `world_revision` 加以下四张表的**完整行、完整列值**，不是仅比较count：

- world_commits
- object_revisions
- operations
- idempotency_records

预期replay通过 `replay()` helper做相同完整比较。legacy/corruption fixture的人工变动在“调用前快照”之前完成，未混入被测调用的写入。

17项失败的实际分类：

- **10项错误成功重放**：X5六项 + X6四项，状态不变。
- **4项错误fresh接受**：X6四项，world revision和四表发生完整提交，零写入期望失败。
- **3项错误冲突**：X7三项，状态不变。

本轮没有观察到受控抛错后残留半笔事务。不能据此声称所有失败“零写入通过”：X6 fresh必须明确保留红色证据。

## Residual risks 与 Chief recommendation

1. 本轮不是人员独立签字；应由未参与修复的reviewer按冻结SHA独立复跑。
2. 本轮新测试在本地3.12.14执行，而非新增remote Actions；本地构建的SSL可选模块限制已披露。CI权限限制没有被隐瞒，也没有用旧CI绿色替代新结果。
3. legacy typed/opaque原始信息不可恢复的兼容政策必须由Chief明确裁决；不能承诺既全兼容歧义行又精确恢复不存在的信息。
4. X7涉及B6正常形式与新增container-kind语义的边界，报告给出明确冻结依据及实际counterexample；若要改变契约，应显式裁决，不得修改本轮冻结测试来制造绿灯。
5. 不将Pydantic 2.10.6预存在的schema-hash差异混入这三个finding。
6. 既有B2/B3/B5/B7/B8/B9的formal回归绿灯仍是有限证据；本轮不声称覆盖全部存储故障、任意恶意Python对象、全部历史schema迁移或M1行为。

**Recommendation to Chief：REJECT CANDIDATE / REPAIR REQUIRED。**

394项新冻结证据在两个Pydantic版本下均为17失败。建议先修复/裁决X5–X7，再在明确的新exact candidate上原样复跑本文件，并由独立人员重审。测试原件及本轮红色日志保留不变。

**不宣布 M0 FINAL PASS，不merge，不启动M1。**

## 如何复跑与验证

在可读取仓库Git对象的位置，建立只读candidate副本/工作树。测试和candidate源码必须分离；使用本目录runner可强制检查candidate HEAD、冻结SHA，并执行完整四步：

```bash
python3.12 -m venv /path/to/venv
/path/to/venv/bin/python -m pip install pydantic==2.13.5 pytest==8.4.2
PYTHONDONTWRITEBYTECODE=1 /path/to/venv/bin/python /path/to/audit/run_frozen.py /path/to/exact-b658-worktree
```

执行前可在本证据目录中运行：

```bash
sha256sum -c SHA256SUMS
```

为保留归档原件，建议先复制证据目录到新的运行输出位置，避免runner覆盖已有日志。原始冻结文件和日志以Git commit/ZIP中的字节为准。

主要交付：本报告、冻结测试、FREEZE.json、runner、两轮collect-only/完整pytest logs、版本信息、完整SHA256SUMS、真实旧实现legacy观察输出和GitHub元数据。ZIP是本轮b658的新证据包，绝不使用旧524原artifact的名字冒充旧件。
