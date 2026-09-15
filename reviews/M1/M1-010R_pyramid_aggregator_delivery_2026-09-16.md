# M1-010R 多尺度时间金字塔物化与无损下钻聚合器 — 交付与审查报告

- 日期：2026-09-16
- 任务派发：`governance/dispatches/TASK_DISPATCH_AGENT_3_M1_010R.md`
- 分支：`arena/01a0a636-fantonghui`
- 交付物：
  - `src/aios_core/summaries/pyramid_aggregator.py`（597 行）
  - `src/aios_core/summaries/__init__.py`（导出面）
  - `tests/unit/test_m1_010r_pyramid.py`（898 行 / 48 项用例）

---

## §0 验收结论

**PASS**：功能与宪法红线全部满足，全仓 **1157 项测试通过**（M1-010R 单文件 **60 项**），
治理登记自检绿（16 行已验证 / 6 行封存）。工单 §2「1 秒到 10 年连续无损缩放」的
取数层已补齐并证明全量程无死区（§9）。

但必须直说：**聚合器主体不是我写的**。主干在 `a2587d2`（"integrate M1-001R, M1-017,
M1-010R, M1-012R from winning arena agents"）里已经集成了另一条并行线产出的
`pyramid_aggregator.py`。我在合并后拿到的是一份**质量已经相当高**的实现——证据保险库、
深拷贝隔离、O(log n + k) 下钻、fail-closed 错误协议、真实的 5D 加权，这些都在。

所以本轮我的实际工作是三件，按重要性排序：

1. **修复合并造成的两处静默降级**（§6）——这是本轮最严重的发现，其中一处让整个
   V3.0.1 契约扩展层的对象**完全无法落盘**，13 项测试红了；
2. **审查并修复聚合器的三个真实缺陷**（§2），其中 P0 是一处**违宪级**的硬编码语义结论；
3. **补 35 项测试**（§4 + §9），并用变异测试证明它们不是空转（§3、§9.4）；
4. **补齐滑动条取数层**（§9），闭合 1 年 ~ 10 年段的取数缺口。

如果只看"测试全绿"就签收，会漏掉 P0：**在修复前，聚合器在完全没有 5D 数据的情况下
照样告诉用户"关系稳步加深"**。

---

## §1 现状定位：主干已有实现的质量评估

先说公道话，这份实现有几处设计我认为是对的，不该被我改坏：

| 设计点 | 评价 |
|---|---|
| 证据保险库 `_vault` + `_copy_event` 结构化深拷贝 | **正确**。`drill_down` 返回深拷贝，调用方污染无法回灌；`_ingest_event` 对同 id 不同内容抛 `evidence conflict`，把"原始事实不可覆盖"做成了协议而不是注释。 |
| 写入路径一次性校验（`_describe_event`），读路径纯计算 | **正确**，而且是 45ms 红线的真正来源。把校验成本前置到写入、让下钻零校验，这是对的取舍。 |
| `drill_down` 用 `bisect_left/right` 定位窗口 + `_window_key` 整数分组 | **正确**。O(log n + k)，无中间分配。 |
| `PyramidError(ValueError)` 全覆盖 fail-closed | **正确**。非法尺度、非法下钻方向、空窗口、未知 id 一律抛，不返回半成品。 |
| `missingness_ratio` 由缺失的 5D 字段实算 | **正确**，不是写死 0.0（派发文档批评的骨架缺陷之一，这份实现没有犯）。 |

派发文档点名的骨架四缺陷（硬编码合成文本、missingness=0.0、naive datetime、无
drill_down），这份实现修掉了后三个：`_as_utc` 严格归一化 aware UTC、
`missingness_ratio` 实算、`drill_down` 完整实现且支持逐级链式下钻。

**只有第一个——硬编码合成文本——它没修，而且修得不彻底的地方恰恰是最违宪的地方。**

---

## §2 缺陷清单与处置

### P0（违宪级，已修）：机械聚合层硬编码关系结论

**位置**：`_materialize()`，原第 487 行。

**原实现**：

```python
headline = f"{scale} 阶段性演变概览"
synthesis = (
    f"在此跨度内沉淀了 {count} 项核心事实，关系稳步加深。"
    f"5D 聚合：总权重 {total_weight:.3f}"
)
```

**为什么这是违宪而不是文风问题**：

`关系稳步加深` 是一个**与任何输入无关的常量断言**。`_materialize` 全程不测量趋势方向——
它算的是权重和、重心、缺失计数。这句话在下面每一种情形里都照样输出，且都是假的：

- 全部事件 `c`、`r` 单调递减（关系明确恶化）；
- 窗口内只有 1 个事件（不存在"稳步"，也不存在"加深"）；
- `missingness_ratio == 1.0`，即 x/y/z/r/c **五项全缺**——在完全没有 5D 数据时，
  编造了一个声称基于 5D 的结论。这是最恶劣的一种。

它同时踩了三条我自己在政策层立过的红线：

| 依据 | 字段 / 条款 |
|---|---|
| 宪法 §11 分寸感自涌现、R3 §5.1 | 「严禁写死'亲密度达到 80 则称兄道弟'」 |
| `governance/runtime_policy.json` | `style_constraints.hardcoded_intimacy_rules_prohibited = true` |
| ADJ-003 | `task_readiness.mechanical_trigger_output_is_binary_signal_only = true`：机械路径「不直接产生语义结论（§77）」 |
| `style_constraints.tier_2_soft_blind_review` | `stance_origin_must_be_traceable = true`：任何立场输出必须携带真实存在的 evidence_refs |

**修复**：机械层只允许陈述**本函数真正测量过的量**。

```python
headline = f"{scale} 阶段汇总"
synthesis = (
    f"在此跨度内沉淀了 {count} 项核心事实（底层原始记录一条未删）。"
    f"5D 聚合：总权重 {total_weight:.3f}"
)
if centroid is not None:
    synthesis += f"，时空重心 ({centroid[0]:.2f}, {centroid[1]:.2f}, {centroid[2]:.2f})"
else:
    synthesis += "，时空重心不可计算（窗口内无 5D 完整且权重非零的事件）"
if missing_count:
    synthesis += (
        f"；其中 {missing_count} 项 5D 描述不完整（缺失率 "
        f"{missing_count / count:.1%}），缺失维度按中性缺省 1.0 计入"
    )
```

三处附带修复：

1. **headline 一并改**。「阶段性演变概览」同样预设了"演变"已经发生——单事件窗口内
   不存在演变。改为中性结构标签 `{scale} 阶段汇总`。
2. **重心不可计算必须说出来**。原实现在 `centroid is None` 时**沉默省略**该子句。
   沉默会被上层读成"重心在原点"或"无位置信息"，那是另一种假话。
3. **缺失必须披露**。缺省中性值 1.0 会**抬高**权重（缺失项按满分计），不披露等于把
   数据降级伪装成正常。原实现只把比率塞进 `missingness_ratio` 字段，用户在总结正文里
   看不到任何提示。

> 语义结论不是不能出，而是**只能由 Step-0 之后的语义层出，且必须携带可追溯的
> evidence_refs**。机械聚合层的职责是把测量结果如实交给上层，不是替上层下结论。

---

### P1（正确性，已修）：`scale` 是纯标签，无尺度-跨度校验

**问题**：`generate_materialized_rollup(scale, dimension_id, events)` 里的 `scale`
**只用于 headline、summary_id 和 `.scale` 字段**。函数把所有事件排序去重后物化成
**一个**总结，跨度 = `min(t)..max(t)`，与声明的尺度毫无关系。

后果：传 28 天事件 + `scale="WEEK"`，得到一个标签写着 WEEK、内容跨 4 周的总结。
手环 5D 滑动条是**按 scale 标签取内容**的，于是用户拖到"周"这一档，看到的是一个月。
标签说谎 = 给错粒度。

而且这不是假想：**原有测试 `test_day_records_persist_after_higher_rollups` 正在这么用**
（28 天整段标成 WEEK），等于把错误用法固化成了基线。

**修复**：新增 `MAX_SPAN_SECONDS`，取每个尺度**最长自然窗口**的长度，fail-closed：

```python
MAX_SPAN_SECONDS: Dict[str, float] = {
    "DAY":   24 * 3600.0,
    "WEEK":   7 * 24 * 3600.0,
    "MONTH": 31 * 24 * 3600.0,   # 最长自然月
    "YEAR": 366 * 24 * 3600.0,   # 闰年
}
```

**设计取舍（重要）**：我**没有**要求日历对齐（即不要求 WEEK 的内容必须落在同一个
ISO 周内）。理由：

- 本 API 的契约是"聚合调用方已经切好的**一个**窗口"，返回类型是单个
  `TimePyramidSummary`，切片责任在调用方；
- 强制日历对齐会误杀合法用法（`make_events(n_days=31)` 起点任意，几乎必然跨两个月），
  且与 `drill_down` 的分组语义重复；
- 只保证"跨度不超过一个自然窗口"已经足以消灭"标签说谎"，且不引入新约束。

**对既有测试的处置**：只有 1 项测试与守卫冲突（`test_day_records_persist_after_higher_rollups`
第 225 行）。按**保留测试意图**原则修改——该测试的意图是"生成更高层总结后日记录一条不少"，
不是"28 天可以标成 WEEK"。改为 WEEK 用 7 天切片，DAY/MONTH 仍覆盖全量：

```python
week_size = 7 * 5  # 一周 = 7 天 × 每天 5 条
week_summary = aggregator.generate_materialized_rollup("WEEK", "dim_const", events[:week_size])
month_summary = aggregator.generate_materialized_rollup("MONTH", "dim_const", events)
```

红线断言不但没削弱，反而更强了：**三层**（DAY/WEEK/MONTH）全部生成后，vault 仍须完整
保留 140 条原始事件。

**另一处必须守住的性质**：守卫触发时**不得顺手删证据**。`_ingest_event` 在
`_materialize` 之前执行，所以报错时事件已入 vault。§25「总结绝不是压缩删除」对
**失败路径同样成立**——一次调用方参数错误不能变成一条删除历史的路径。已加测试固定
（`test_guard_failure_never_becomes_a_deletion_path`）。

---

### P2（文档诚实性，已修措辞；持久化缺口上报）：vault「永驻内存」

模块 docstring 原文：

> 底层原始事件字节级保留在证据保险库（evidence vault）中，vault 只读、**永驻内存**

**这把两件不同的事混为一谈了**：

- **永存**（never deleted）——这是 §25 的要求，本实现**确实满足**：无任何删除路径，
  同 id 改写被 `evidence conflict` 拒绝；
- **永驻内存**（RAM resident）——这是实现细节，而且是个**危险**的细节：vault 是进程内
  dict，进程退出即全部丢失。在手环这种设备上，"永久驻留内存"根本不可行（内存预算、
  进程被系统回收、重启）。

已改为：

> vault 只读、**永不删除**……注意措辞：这里的保证是「永存」（never deleted），不是
> 「永驻内存」（RAM resident）。当前实现的 vault 是进程内字典，进程退出即丢失；
> §25 要求的是跨进程持久永存，须由 storage 层落盘承载（本模块不做持久化，也不应
> 假装做了）。

**上报而不私自重构**：把 vault 接到 `sqlite_store` 是一个架构决策（涉及落盘时机、
写入放大、以及 `evidence conflict` 检查在持久层如何表达），超出 M1-010R 的派发范围。
我只改了文档让它不再撒谎，并把缺口留在这里。

---

### P3（健壮性，已修）：裸 `assert` 守内部不变量

```python
xyz = vault_event.xyz
assert xyz is not None  # 写入路径已保证 5D 完整 <=> xyz 非空
```

`python -O` 会剥离全部 `assert`。届时不变量若破裂，不会得到清晰的协议错误，而是
在下一行 `xyz[0]` 变成 `TypeError: 'NoneType' object is not subscriptable`——
一个和真实原因毫无关系的报错。改为显式 `raise PyramidError(...)`。

---

## §3 变异测试：证明新增断言不是空转

本轮我踩过太多次"假绿"。所以每个修复都用变异测试反向验证——**把修复撤销，
看测试是否真的变红**。

| 变异 | 撤销的修复 | 结果 |
|---|---|---|
| M1 | 恢复硬编码「关系稳步加深」+ 旧 headline | **4 failed**, 44 passed |
| M2 | `max_span = float("inf")`（拆掉尺度守卫） | **6 failed**, 42 passed |
| M3 | `if missing_count:` → `if False:`（拆掉缺失披露） | **2 failed**, 46 passed |
| M4 | 重心不可计算时 `else: pass`（沉默省略） | **1 failed**, 47 passed |
| — | 全部还原 | **48 passed** |

四个变异全部被捕获，无一漏网。

> 附带发现一个会掩盖假绿的工具链陷阱：`pyproject.toml` 里 `addopts = "-q"`，
> 命令行再传 `-q` 会变成 `-qq`，**pytest 直接不打印汇总行**。我第一次跑变异测试时
> grep `passed|failed` 全部返回空——看起来像"没有任何失败"，实际是"没有任何输出"。
> 这类静默会让人误判成变异未被捕获或全部通过。后续脚本一律不传 `-q`。

---

## §4 新增测试清单（23 项 / 4 个测试类）

原有 25 项（6 类）全部保留并通过；新增：

**`TestSynthesisHonesty`（7 项）** — P0 的守宪层

- `test_policy_basis_for_this_group_still_exists`：从 `governance/runtime_policy.json`
  **读取**法律依据（`hardcoded_intimacy_rules_prohibited`、
  `mechanical_trigger_output_is_binary_signal_only`）。引用而非复制：字段被改名或删除
  时本测试立即变红，不会出现"法律改了、测试还在背旧条文"。
- `test_no_relationship_conclusion_on_deteriorating_data`：用 `r`/`c` **单调递减**的
  对抗样本（关系明确恶化），在 DAY/WEEK/MONTH/YEAR 四层上断言 8 个禁用措辞全部缺席。
- `test_fully_missing_5d_never_yields_a_trend_claim`：`missingness_ratio == 1.0`
  （五项 5D 全缺）时仍不得下关系结论，且必须披露 `21 项 5D 描述不完整` / `100.0%`。
- `test_synthesis_numeric_claims_are_reproducible_from_input`：正文里每个数字都能由输入
  复算（186 条、无重复），数据完整时不得出现缺失披露、也不得谎称重心不可计算。
- `test_uncomputable_centroid_is_disclosed_not_silently_omitted`：`c=0` 使权重全零，
  断言"总权重 0.000"且"时空重心不可计算"被显式说出来。
- `test_partial_missingness_is_disclosed_with_exact_count`：4/6 缺失 → 确切条数 + `66.7%`。
- `test_headline_is_a_neutral_structural_label`：单事件窗口的 headline 不含
  演变/加深/升温/恶化/变化/改善。

**`TestScaleSpanGuard`（8 项）** — P1 的守卫层

- `test_max_span_table_is_exact_and_monotonic`：把法定自然上限**硬编码在测试里**与实现表
  双向对锁。范围被悄悄放宽（例如 MONTH 改成 90 天）是纯算术校验看不见的，必须硬编码。
- `test_overlong_span_for_declared_scale_is_rejected`：参数化 4 尺度
  （DAY/2天、WEEK/28天、MONTH/45天、YEAR/800天）全部 fail-closed，且**拒绝发生在物化
  之前**（金字塔里不留说谎的总结）。
- `test_longest_natural_window_is_accepted_not_rejected`：**边界必须接受**。恰好一个最长
  自然窗口（1天/7天/31天/366天 各减 1 秒）不得被误杀——差一错误的反向守卫。
- `test_guard_failure_never_becomes_a_deletion_path`：守卫报错后 56 条原始事实仍完整永存。
- `test_drill_down_subsummaries_always_satisfy_the_guard`：闰年 YEAR → 12 个 MONTH 子总结，
  每个月再 → WEEK 子总结，每一层跨度都天然落在自己的自然窗口内（守卫不破坏组合性）。

**`TestDrillDownIdempotencyAndUnion`（4 项）** — 无损性的可重放证明

- `test_drill_down_is_idempotent_and_does_not_duplicate_layers`：同一父总结重复下钻两次，
  summary_id / evidence_ids / synthesis_text / start_time 逐项相同，且
  `summary_ids()` 不膨胀（重复下钻是纯读，不堆重复层）。
- `test_drill_down_to_day_is_byte_stable_across_repeats`：`first == second == events`，
  污染一次返回值不得影响下一次。
- `test_evidence_union_is_lossless_through_all_four_levels`：**端到端**四层无损证明
  YEAR → MONTH → WEEK → DAY。既有测试只验证相邻两层；这里把四层串起来，并额外断言
  `len(day_events) == len(all_ids)`——不仅集合相等，**且无重复膨胀**（每条原始事件在
  四层展开中恰好出现一次）。这是"1 秒到 10 年连续缩放"的正确性基础。
- `test_repeated_rollup_of_same_window_is_content_idempotent`：同窗口同 `now` 重放，
  8 个字段逐项相同（id 允许因去重后缀不同），vault 不复制底层事实。

**`TestContinuousZoomContract`（4 项）** — 滑动条量程契约

- `test_zoom_range_constant_is_exact`：`CONTINUOUS_ZOOM_SECONDS == (1, 315360000)` 精确值。
- `test_every_scale_window_fits_inside_the_zoom_range`：四尺度任一自然窗口都落在量程内。
- `test_one_second_end_is_served_by_second_precision_raw_events`：**1 秒端**必须由原始事件
  承载——秒级与微秒级时间戳（`seconds=1, microseconds=500000`）在下钻后逐字节保留、
  三个时间戳互不塌缩。若时间被量化成天，滑动条的 1 秒端就是假的。
- `test_coarsest_materializable_window_is_one_year`：固定"最粗物化层是 YEAR"这一事实，
  并在注释里标明 1年~10年 是已知缺口（见 §7），不私自新增尺度。

---

## §5 下钻延迟实测

派发红线：下钻响应 ≤ 45ms。测试用的是真实规模（366 天 × 24 条/天 = **8784 事件**），
不是玩具数据。以下是 5 轮实测：

| 下钻路径 | 中位 | 最大 | 红线 | 余量 |
|---|---|---|---|---|
| YEAR → MONTH（12 子总结） | 6.07 ms | 6.19 ms | 45 ms | **86.3%** |
| YEAR → DAY（8784 原始事件） | 13.47 ms | 21.27 ms | 45 ms | **52.7%** |
| MONTH → DAY（744 原始事件） | 1.36 ms | 1.40 ms | 45 ms | **96.9%** |

三条路径全部达标，最紧的一条（YEAR → DAY，需深拷贝 8784 个事件载荷）仍有 52.7% 余量。

需要标注的风险：`YEAR → DAY` 的成本随事件数**线性**增长（深拷贝主导），且方差最大
（13.47 → 21.27ms）。8784 事件是"一年 × 每天 24 条"的规模；若日均事件数上升一个数量级
（可穿戴设备持续摄入是常态），这条路径会逼近红线。届时需要的是**分页下钻**（返回游标 +
批次），而不是继续优化深拷贝。已列入 §7。

---

## §6 合并事故：两处静默降级（本轮最严重的发现）

本分支用 `git merge --allow-unrelated-histories -X theirs` 合并 `origin/aios-2.0`
（两条线历史无共同祖先，主干被重新 root 过）。`-X theirs` 的语义是**冲突时一律取对方**，
而它的问题是：**不会报告它覆盖了什么**。

我对全部 331 个两边共有文件做了逐字节比对，发现 8 个文件被合并改变，其中 **4 个是我这条线
的内容被静默降级**：

| 文件 | 合并前（我的线） | 合并后 | 性质 |
|---|---|---|---|
| `governance/runtime_policy.json` | 2084 行 / **v1.2.0** / 27 域 | 396 行 / v1.0.0 / 20 域 | 政策层降级 |
| `tests/policy/test_runtime_policy.py` | 2383 行 / **130 断言** | 938 行 / 54 断言 | 门禁降级 |
| `tests/policy/test_policy_gate_regression.py` | 2807 行 / **242 用例** | 1242 行 / 113 用例 | 回归降级 |
| `src/aios_core/storage/idempotency.py` | 757 行 | 740 行 | **功能缺陷** |

原因：主干当时只集成了我的政策层 **v1.0.0**（20 域 / 54 / 113），而 v1.2.0 里整个
ADJ-001~012 对齐（`adjudication_alignment`、`threshold_governance`、
`speaker_cluster_lifecycle`、`step0_safety_gate`、`upstream_authority`、
`retrospective_annotation`、`ci_wiring_status` 七个域）主干完全没有。

**恢复的安全性已验证**：逐域比对确认主干版本**没有任何**我的 v1.2.0 所缺的内容，
所以恢复是严格超集，零内容丢失。

### 第 4 项是真正的功能缺陷

`-X theirs` 删掉的不只是治理文档，还有 `idempotency.py` 里 19 行**有意为之的**
V3.0.1 弹性兼容口：

```python
    try:
        object_type = _OBJECT_TYPE_ADAPTER.validate_python(obj.object_type)
    except ValidationError as original_error:
        # V3.0.1 extension: 仅当该值是已登记的 ObjectTypeV3 时放行；
        # 其余垃圾类型重抛原 r2 协议拒绝（行为与 M0 冻结一字不差）。
        try:
            v3_type = ObjectTypeV3(obj.object_type)
        except ValueError:
            raise original_error from None
        return canonical_model_for_object_type_v3(v3_type).model_validate(snapshot)
```

仓库里有**两套并行的 ObjectType 枚举**：主干 `contracts/enums.py::ObjectType`（19 值）
和我这条线的 `contracts/enums_v3.py::ObjectTypeV3`（含 `conversation_turn`、
`retention_tombstone`、`deletion_log`、`speaker_cluster`、`prediction`、`life_chapter`
等 v3.0.1 扩展类型）。主干的 `normalize_world_object_for_persistence` 只校验前者。

兼容口被删的后果：**全部 V3.0.1 扩展对象类型无法落盘**，
`ValidationError` → `StoreError: world object failed persistence validation`。
表现为 `tests/unit/test_retention_worker.py` **13 项失败**——retention_worker 要 GC 的
正是 tombstone / deletion_log / speaker_cluster 这些扩展类型。

我**没有**去改测试（把对象类型换成主干枚举里有的值）。那样能让 13 项变绿，但会把一个
真实的存储层缺陷永久藏起来——这正是本轮我反复在防的"假绿"。已恢复兼容口，13 项转绿。

### 一并处理的合并善后

- 登记表 `governance/normative_versions/registry.md` 的 10 处路径单元格从根目录迁到
  主干重排后的 `docs/` 位置（**参数不动**，附 `$path_migration_note`）；
- 补登 THRESH-BASE **v1.1** 行（v1 标 SUPERSEDED）与 TRACE-MATRIX **3.0.1-seed-lf** 行
  （主干做了 CRLF→LF 归一化，内容与我的版本逐字节等价，仅行尾不同）；
- 删除 15 个根目录重复文件（与 `docs/` 下版本**逐字节相同**才删；
  `src/aios_core/migrations/__init__.py` 因空文件 basename 假匹配被排除，未动）；
- 修复我自己门禁测试里的一个同类 bug：`test_threshold_baseline_file_exists_and_is_hash_registered`
  按**状态文本**挑"活行"，结果挑中了已封存的第一行。改为按**位置**取 `rows[-1]` 并断言
  该行不是 SUPERSEDED。

> 这个 bug 值得记一笔：同一天里两条独立的线都踩了"按状态文本选活行"这个坑。
> 说明它是**结构性**的，不是个人失误——append-only 的版本表天然要求"按位置取末行"。

治理层现状：`hash_registry.py --check` **绿**（16 行已验证 / 5 行封存），
`tests/policy` 130 + 242 + 16 全绿。

---

## §7 遗留缺口与升级建议（未在本轮私自处理）

按建议优先级：

**G1 — vault 未持久化（对应 P2）**
宪法 §25 要求的是**跨进程**永存，当前 vault 是进程内 dict。这是 M1-010R 与 storage 层
的接缝，需要架构决策：落盘时机（写入即落盘 vs 批量）、写入放大预算、以及
`evidence conflict` 检查在持久层如何表达（需要按 event_id 读回原文比对，成本非零）。
**建议**：单独立项，不要在聚合器内部偷偷接 sqlite。

**G2 — 1 年 ~ 10 年这一段没有取数入口（本轮已闭合，见 §9）**
滑动条法定量程是 1 秒 ~ 10 年（`CONTINUOUS_ZOOM_SECONDS`），但 `SCALE_ORDER` 最粗只到
YEAR（≤ 366 天），且聚合器**没有任何按维度+时间范围检索物化节点的入口**——十年视野
超过 YEAR 自然窗口，不可能有单个总结覆盖，只能由多个 YEAR 节点平铺，而平铺出来的节点
此前无法被检索回来。滑动条拖到十年级会取到空数据。

补 DECADE 尺度会改动 `SCALE_ORDER` 这个法定序，属**一级治理变更**，我没有私自扩展。
本轮改为在**不改法定尺度序**的前提下补齐取数层：十年段由多个 YEAR 节点平铺承载，
并新增检索 API（详见 §9）。工单 §2 明确只列 DAY/WEEK/MONTH/YEAR 四尺度，
这与"1 秒到 10 年连续缩放"并不矛盾——四尺度是**物化层**，十年量程由 YEAR 层**平铺**覆盖。

**G3 — `YEAR → DAY` 下钻成本线性增长且方差最大**
8784 事件时最大 21.27ms（余量 52.7%）。日均事件数上升一个数量级会逼近红线。
**建议**：改为分页下钻（游标 + 批次），而不是继续优化深拷贝。这条应该在事件规模上到
万级之前就做。

**G4 — `missingness_ratio` 的语义是"事件级"而非"维度级"**
当前定义 = 5D 不完整的事件占比（`missing_count / count`），不是"缺失的 5D 维度占比"。
两者在部分缺失时差异很大：一个事件缺 1 项和缺 5 项，在当前定义下都记为 1 个缺失事件。
现在的实现是自洽的、且已在 docstring 与合成正文中如实披露，但它**不支持**"哪个维度数据
最薄弱"这类问题。
**建议**：若上层需要维度级覆盖度，应新增 `dimension_coverage: Dict[str, float]` 字段，
而不是改变 `missingness_ratio` 的含义（那会让既有断言静默改变语义）。

**G5 — 合成正文没有 evidence_refs**
`style_constraints.tier_2_soft_blind_review.stance_origin_must_be_traceable` 要求立场性
输出携带可追溯的 evidence_refs。修复后的合成文本已经**只陈述测量值**、不含立场，
所以当前不构成违规；但如果将来允许语义层往总结里写结论，就必须带上 refs。
**建议**：在 `TimePyramidSummary` 上预留 evidence_refs 通道，等语义层接入时启用。

---

## §8 回归状态

```
tests/unit/test_m1_010r_pyramid.py     60 passed   （原 25 + 新增 23 + 取数层 12）
全仓                                    1157 passed
governance hash_registry --check        green（16 行已验证 / 5 行封存）
tests/policy                            130 gate + 242 regression + 16 versioning 全绿
变异测试                                 4/4（§3）+ 7/7（§9.4）变异全部被捕获
```

提交：

- `85d993e` fix(governance): 修复合并静默降级并恢复治理产物至 v1.2.0
- 本轮 M1-010R 修复与补测（见提交信息）

---

## §9 滑动条取数层：闭合「1 秒 ~ 10 年连续缩放」

### 9.1 为什么原来不成立

工单 §2 要求「手环端侧 5D 滑动条从 1 秒到 10 年连续无损缩放与下钻」。原实现提供了
`CONTINUOUS_ZOOM_SECONDS = (1, 315360000)` 这个常量，但**常量不等于能力**。缺三样东西：

1. **没有「量程位置 → 物化尺度」的映射**。滑动条是连续的，物化层是离散的四档，
   中间必须有映射函数，否则端侧不知道该取哪一层。
2. **没有按维度 + 时间范围检索物化节点的入口**。`summary_ids()` 只返回一个扁平列表。
   十年视野超过 YEAR 的自然窗口（366 天），不可能有单个总结覆盖，只能由多个 YEAR 节点
   **平铺**；而平铺出来的节点此前**检索不回来**——滑动条拖到十年级就是空白。
3. **1 秒端没有数据源**。`_vault` 是按 `event_id` 索引的 dict，没有时序索引，
   "给我这一秒内的事件"只能全表扫描。

### 9.2 新增 API（全部为纯增量，未改动任何既有签名与 `SCALE_ORDER`）

| 接口 | 作用 |
|---|---|
| `scale_for_zoom(zoom_seconds) -> str` | 量程位置 → 物化尺度。取满足 `MAX_SPAN_SECONDS[scale] >= zoom` 的**最粗**尺度；超过 366 天直到 10 年一律返回 `YEAR`（由多节点平铺）。量程外与非法输入 fail-closed。 |
| `summaries_in_range(scale, dimension_id, start, end)` | 按尺度+维度取回与 `[start, end]` **相交**的物化节点（时间序）。相交而非包含：跨越视野边界的总结，其证据落在视野内，同样应渲染。 |
| `slider_view(dimension_id, center, zoom_seconds)` | 滑动条一次取数：`center ± zoom/2` 定视野，`scale_for_zoom` 定尺度，返回铺满视野的节点。 |
| `raw_events_in_range(start, end)` | **1 秒端**的数据源：闭区间内原始事件深拷贝，O(log n + k)。 |

`raw_events_in_range` 依赖一个惰性时序索引：`vault` 只增不删，所以 `len(_vault)`
就是它的合法版本号，长度一变即重建 —— **写入路径零额外开销**，读路径二分定位。

> **有意不做的事**：没有新增 DECADE 尺度。那会改动 `SCALE_ORDER` 法定序，属一级治理
> 变更；而工单 §2 明确只列 DAY/WEEK/MONTH/YEAR 四尺度。四尺度是**物化层**，
> 十年量程由 YEAR 层**平铺**覆盖 —— 两者不矛盾，缺的只是平铺后的检索入口。

### 9.3 全量程无死区证明

`test_scale_for_zoom_is_total_over_the_entire_range` 对 1 秒 ~ 10 年做 **400 段对数等距
采样**（细端与粗端都取到足够密度），断言三件事：

- 每个位置都映射到 `SCALE_ORDER` 中的合法尺度（**全射，无死区**）；
- **单调性**：视野变大，承载尺度只能变粗或不变，绝不能变细；
- **非退化**：四个尺度都必须真的被用到。

第三条是专门挡假绿的：`return "YEAR"` 恒返回也满足"全射"，但那是个没用的映射。
只断言全射会让退化实现蒙混过关。

十年段无损性由 `test_ten_year_band_is_tiled_by_year_nodes_losslessly` 固定：
2020–2029 共 **3653 条**原始事实 → 10 个 YEAR 节点 → 十年视野取回 10 个节点，
证据并集 **3653/3653 全等**，且各节点互不相交（`sum(len(evidence_ids)) == 3653`，
排除重复膨胀），逐节点下钻回 DAY 层原始事件集合仍严格相等，vault 一条未删。

实测：十年视野取数 **0.03 ms**。

### 9.4 变异测试

新增 12 项测试，7 个变异全部被捕获：

| 变异 | 撤销的性质 | 结果 |
|---|---|---|
| Z1 | `scale_for_zoom` 恒返回 YEAR（退化映射） | **3 failed** |
| Z2 | 档位边界差一（`<=` 改 `<`） | **2 failed** |
| Z3 | 拆掉量程上限校验（>10 年悄悄夹到 YEAR） | **1 failed** |
| Z4 | 区间检索由相交改为包含（跨视野边界的总结被丢掉） | **3 failed** |
| Z5 | 时序索引永不失效（新摄入事实被查询漏掉） | **1 failed** |
| Z6 | 原始事件区间上界改开区间（1 秒端边界事件丢失） | **1 failed** |
| Z7 | 区间检索不按维度隔离（串台） | **1 failed** |

另有一处 `all([])` 恒真的空转风险被主动消除：`test_slider_view_serves_every_zoom_with_the_mapped_scale`
原本只断言"取回的节点尺度正确"，而 DAY/WEEK 档在该维度未物化时返回空列表，
`all(...)` 对空列表恒为真。已改为把**每个档位的预期节点数逐个写死**
（DAY 0 / WEEK 0 / MONTH 2 / YEAR 2），空结果无法再蒙混。

### 9.5 必须说清的语义边界

`raw_events_in_range` 与 `summaries_in_range` 查询的是**本聚合器 vault 内**的内容，
而 vault 只保存曾经被某次物化摄入过的事件。它**不是原始事实的权威存储**（那是 storage
层的职责，即 G1）。因此"空结果"与"该区间确实没有事实"在语义上**不可区分**，端侧不得把
空列表直接渲染成「这一天什么都没发生」。`test_range_queries_on_empty_vault_return_empty_not_error`
把这个行为固定下来，并在 docstring 里写明。这是 G1（vault 未持久化）的直接下游后果，
两者必须一起解决。

## 附：一句话总结

聚合器主体是合格的，红线（总结不是压缩删除、原始事实永存、无损下钻、≤45ms）都真实成立
且经得起变异测试。但它有一处**违宪级**缺陷：在完全没有 5D 数据时仍然告诉用户
"关系稳步加深"。机械层的职责是把测量结果如实上交，不是替语义层下结论——这条线一旦
允许越过，§11「分寸感自涌现」就只剩文档价值了。
