# AIOS Core — as-built 审查报告（第一批派工交付）

- **审查人角色**：独立首席架构师 / 技术总监（与派单方、实现方均无隶属）
- **审查日期**：2026-09-16（容器 UTC 时间戳见各工件）
- **审查对象 commit**：`7ad5df9`（含 `origin/aios-2.0` 合并进来的 64 文件 / +11,055 行产品代码）
- **审查方法**：**不读文档自述，只读仓库现状 + 现场实测**。所有性能结论绑定
  「规模档 + fixture + profile + 工件哈希」四元组，未绑定四元组的"毫秒级""≤45ms"一律判为**不可判定**（设计书铁律 2）。
- **裁定口径（profile）**：`co_search_p95_ms = 50.0`（宪法第八十九条"毫秒级"的工程化默认档，与设计书 §3.5-B 同一门限）、
  `manifest_top_k = 200`（§3.5-C 前台只取 top-K 指针）、`cjk_bigram_min_recall ≥ 1`（I7 反空转）。
- **证据工件**：
  - 探针 `reviews/architecture/evidence/verify_landed_m1_017_cjk.py`（v1.0.0，stdlib-only，直接 import 被测模块）
  - 10k 档 `verify_landed_m1_017_cjk_10k_result.json` / `.log`
  - 100k 档 `verify_landed_m1_017_cjk_100k_result.json` / `.log`
  - 1M 档 `verify_landed_m1_017_cjk_1m_result.json` / `.log`
  - 测试与环境裁决 `governance/issue_registry/evidence/pytest_environment_ruling_2026-09-16.log`
- **本报告新增 gap 号**：`V3G-001 ~ V3G-008`（R4_prefix 已定义 `V3G-` = 审计发现号；已同步登记进 registry 0.3.3-PROPOSAL）

---

## 0. 一页结论

| gap | 严重度 | 一句话结论 | 硬证据 |
|---|---|---|---|
| **V3G-001** | **P0** | 已落地的 CJK 多词共现检索在 1M 档**超门 7.64×**（p95 382.074 ms / 门 50 ms）；`co_search_scored(limit=200)` 超门 **10.9×**（543.899 ms）；`partial_search` 超门 **14.8×**（740.660 ms） | `..._1m_result.json → q1_as_built` |
| **V3G-002** | **P0** | `index_many()` 把**全部 postings 先物化进 Python list** 再单事务 executemany ⇒ 峰值 RSS = O(总 postings)。1M 实体（29,018,442 行）在本容器**被 OOM-kill（SIGKILL/137）**，实测复现 | 首次 1M 运行 exit=137；`q0_ingest_memory`：200k 单批 1,019.1 MB vs 分批 390.2 MB |
| **V3G-003** | **P0** | **两张派工单的核心交付物根本不存在**：`summaries/pyramid_aggregator.py`（3号/M1-010R）、`query/hyperlink_traverser.py`（4号/M1-012R）。全仓 grep `hyperlink|traverser|超链接` = **0 命中** | `find src -name "*.py"` 清单；派工单注册表 L7/L8 |
| **V3G-004** | **P0** | **号位同号异义**：registry 里 `M1-017` = `simulated-edge-reduction-pipeline`（模拟端侧降采样管线），但 2号派工单把 **CJK 倒排索引**挂到 M1-017；registry 里 `M1-018` = `chinese-hybrid-co-search-engine`（中文混合共搜），5号派工单却把**反向回溯标注（老王案）**挂到 M1-018。违反 R3_alloc「一个号只能有一个 slug」 | registry `issues[]` vs 派工单标题行 |
| **V3G-005** | **P0** | **5/5 派工单缺 `slug` 与 `source_docs`**（`grep -c slug` 全为 0）⇒ 全部违反 R6_dispatch；且 `governance/dispatches/` **不在 `scope_docs`** ⇒ CG-2 检查器**结构性看不见**这些号位冲突（这就是门 RED 却没报出 V3G-004 的原因） | 派工单头部字段；registry `scope_docs` |
| **V3G-006** | **P1** | 派工单里的性能承诺**全部未绑定规模档**："毫秒级"（2号）、"≤45ms"（3号）、"25ms 内"（4号）——没有实体数、没有 postings 密度、没有 profile、没有实测工件路径 ⇒ 机械执行必然产出超标实现（V3G-001 的直接成因） | 派工单 L14 / 背景段 |
| **V3G-007** | **P1** | **宪法 §89.2 的别名覆盖双缺位**：别名归一被派给 4号工单（"支持别名（如'王叔'）自动链接归一"）而 4号未交付；2号的倒排表也**不消费** `Entity.aliases`（该字段已在 `contracts/models.py:42` 存在）。实测：查询 `母亲` 命中 10,990，查询 `妈妈` 命中 333,334 ⇒ 枢纽实体的别名召回**全部漏掉** | `q2_alias` |
| **V3G-008** | **P2** | 索引膨胀无上限：一元+二元重叠分词、**无每对象 postings cap** ⇒ 29.02 行/实体，1M 实体 = **4,219 MB**（对照设计书 §3.5-B 词典优先 + cap=8 = 6.26 行/对象，**4.6×**）；摄入吞吐 5,662 实体/s。另：`explain()` 自身 1M p95 = **57.566 ms > 门** ⇒ 禁入在线路径 | `build`、`q1_as_built.explain_call` |

**总裁定**：第一批 5 张派工单，**交付 3 张、缺失 2 张**；交付的 3 张里，唯一可实测的检索热路径（M1-017 CJK）**在 1M 档不达标 7.64~14.8×**，且摄入路径**在 1M 档不可运行（OOM）**。
但——**这不是实现方的手艺问题**。派工单把一条被我方 1M 实测**驳回**的 SQL 写成了强制指令（§2.3），实现方忠实执行了它。
真正的根因是 **V3G-005/006：派工单不携带 slug、不绑定规模档与门限、且不在检查器的扫描范围内**。修派单模板 + 扩 scope_docs，比改这一个模块重要得多。

---

## 1. 交付完整性对账（仓库现状 vs 派工单注册表）

`governance/dispatches/TASK_DISPATCH_REGISTRY.md` 自己声明"本文档为 AI 模型团队在 GitHub 云端领单开发的**唯一派发索引**"，并为每张工单列了"核心交付源码"。逐条核对：

| 派工单 | 声明号位 | 声明的核心交付源码 | 仓库实际 | 行数 | 判定 |
|---|---|---|---|---|---|
| 1号 | `M1-001R` | `src/aios_core/ingest/multimodal_edge.py` | ✅ 存在 | 555 | 交付（待审） |
| 2号 | `M1-017` | `src/aios_core/query/cjk_inverted_index.py` | ✅ 存在 | 525 | 交付，**实测超标**（§3） |
| 3号 | `M1-010R` | `src/aios_core/summaries/pyramid_aggregator.py` | ❌ **不存在**（`summaries/__init__.py` 仅 1 行） | — | **未交付** |
| 4号 | `M1-012R` | `src/aios_core/query/hyperlink_traverser.py` | ❌ **不存在**（全仓 grep `hyperlink\|traverser\|超链接` = 0 命中） | — | **未交付** |
| 5号 | `M1-018` | `src/aios_core/world/retrospective_annotation.py` | ✅ 存在 | 621 | 交付（待审） |

补充：`cockpit/pipeline.py`（443 行）、`world/fact_immutability_ledger.py`（338 行）、`wake/dispatcher.py`（84 行）、`contracts/safety_bypass.py`（65 行）已落地，但**在派工单注册表里没有对应工单** ⇒ 存在"无单交付"，台账与仓库**双向失真**（有单无货 2 项、有货无单 4 项）。

> **判定 V3G-003（P0）**：派发索引是"唯一真源"却与仓库不符。任何基于该台账的进度汇报（"M1 完成 5/5"）都是**假的**。
> 修复：把交付物存在性变成**可执行断言**——在 `run_gates.py` 增一道 `CG-6 交付物存在性门`，从派工单注册表解析"核心交付源码"列，逐个 `Path.exists()` + 行数下限（防占位空文件），缺一项即 hard fail。这条门不需要任何人工判断，10 行代码就能让 V3G-003 这类问题**永不再发生**。

---

## 2. 号位治理断层（这一段比性能更致命）

### 2.1 同号异义（V3G-004）

registry（`v3_issue_registry.json`，权威号表）：

```
M1-017  slug=simulated-edge-reduction-pipeline   semantics=模拟端侧降采样管线      aliases=[RC-013]
M1-018  slug=chinese-hybrid-co-search-engine     semantics=中文混合共搜引擎        aliases=[RC-014]
```

派工单实际用法：

```
工单 #2：M1-017 CJK 拓扑倒排聚集表与多词检索加速引擎      ← 这是 registry 里 M1-018 的语义
工单 #5：M1-018 认知反向传播语义图层契约（老王案）        ← 这是另一个语义，registry 里 M1-018 已被占用
```

两个号各自承载了**两个互斥语义**，直接违反 R3_alloc「一个 slug 只能有一个号；一个号只能有一个 slug」和「已注册号永不复用、永不改语义；改语义 = 发新号 + 旧号标 SUPERSEDED_BY」。

把 5 张派工单逐个对回 registry 的 slug，得到的不是"个别写错"，而是**整条号位链错位一格**：

| 派工单 | 工单用的号 | registry 里该号的**真实语义** | 该交付物**应该**挂的号 | 错位性质 |
|---|---|---|---|---|
| 1号 端侧多模态摄入 + 声纹 180 天淘汰 | `M1-001R` | 未注册（冻结基线只有 `M1-001~M1-016`，无 `R` 变体） | **`M1-017`** `simulated-edge-reduction-pipeline`（+ `RC-016` 声纹生命周期） | 该号被 2号占用 |
| 2号 CJK 倒排 + 多词共搜 | `M1-017` | `simulated-edge-reduction-pipeline` = **模拟端侧降采样管线**（`RC-013`） | **`M1-018`** `chinese-hybrid-co-search-engine`（`RC-014`，即设计书 §3.5-B 的正主）；别名投影部分另属 **`M1-021`** `keyword-alias-inverted-projection` | 占了 1号的号 |
| 3号 5D 时空多尺度金字塔 | `M1-010R` | 未注册 | registry **无对应 slug** ⇒ 须按 R3_alloc 先注册 slug 再发号 | 无号可用 |
| 4号 实体拓扑超链接穿透检索 | `M1-012R` | 未注册 | registry **无对应 slug** ⇒ 须先注册 slug 再发号 | 无号可用 |
| 5号 认知反向回溯标注（老王案） | `M1-018` | `chinese-hybrid-co-search-engine` = **中文混合共搜引擎**（`RC-014`） | **`M3-012`** `retrospective-semantic-annotation`（契约侧 `M0-031` / `RC-004` / `RC-020`） | 占了 2号的号 |

后果不是 paperwork：**验收标准会张冠李戴**。`M1-018` 在 registry 里的验收语义是"中文共搜 p95"，现在被拿去验收老王案的双时态标注；`M1-017` 的"端侧降采样"验收语义被拿去验收 CJK 索引。
本报告 §3 实测的那 442.532 ms，**在错误的号位下永远不会被正确的门拦住**——因为没有任何一条门的验收标准绑定到"M1-017 = CJK 共搜"这个组合。

另：`M1-001R` / `M1-010R` / `M1-012R` 使用 **`R` 后缀命名空间**，R4_prefix 里没有这个前缀/后缀，registry 里也没有这三个号。它们目前是**未注册号**，且其中两个（3号/4号）连 slug 都不存在于 registry ⇒ 不是"挂错号"，是"根本没进号表"。

### 2.2 派工单不带 slug / source_docs（V3G-005）

R6_dispatch 原文："每张派单必须携带 slug + source_docs；号仅作显示；slug 冲突即 CI fail"。
实测：`grep -c "slug" governance/dispatches/TASK_DISPATCH_AGENT_*.md` → **5 个文件全为 0**。

**如果这条规则被执行了，V3G-004 在派单那一刻就会被拦住**：2号工单若带上 slug `chinese-hybrid-co-search-engine`，registry 会告诉派单方"这个 slug 已经是 M1-018"，冲突当场暴露。号位冲突不是粗心，是**缺少强制字段**的必然结果。

### 2.3 检查器的结构性盲区（V3G-005 的第二半）

`scope_docs`（9 项）覆盖 `docs/specifications/`、`reviews/architecture/`、`reviews/constitution/`、`governance/v3.0.1_amendment/`——**唯独没有 `governance/dispatches/`**。
CG-2 调用检查器扫描的是 scope_docs，因此派工单里的 `M1-017`/`M1-018`/`M1-010R` **从未进入号位一致性检查**。这解释了当前门状态（`CONFLICT 39 / UNREGISTERED 0`）为何没抓到最严重的那一类冲突：不是门太松，是**门没看见那份文件**。

修复（两步，都不需要放宽任何门）：

1. 把 `governance/dispatches/*.md` 加入 `scope_docs`；
2. 给派工单模板加**强制头部字段**（见 §5.1），使检查器能从派工单里解析出 `slug` 与 `source_docs` 并做 slug↔号 双向校验。

**预期后果要如实说明**：一旦把派工单纳入扫描，`UNREGISTERED` 会从 0 变成 ≥3（三个 `R` 后缀号），`CONFLICT` 也会上升。
`gate_baseline.json` 的债务棘轮规定这两项**只许减少**，因此纳管当天 CI 会 hard fail。
**正确做法不是提高棘轮上限**，而是同一次提交里完成：给三个 `R` 号在 registry 发正式号（或标 `PROVISIONAL`）、把 2号/5号工单的号位改回 registry 语义、然后**棘轮随之下调**。棘轮不许放宽，但允许在"真实债务被清偿"时收紧。

---

## 3. M1-017 CJK 倒排索引：现场实测

### 3.1 被测对象与口径

| 项 | 值 |
|---|---|
| 被测文件 | `src/aios_core/query/cjk_inverted_index.py` |
| `subject_sha256` | `09b4a1e625f9ead495016441149643a27bf65c12acfc4a4802f90ec083ffe467` |
| 探针 | `verify_landed_m1_017_cjk.py` **v1.1.0**，`script_sha256=a3388fa1…`（三份工件 10k/100k/1M 均由该版本产出，CG-1 逐份校验探针哈希**与被测源码哈希**） |
| 调用方式 | **直接 import 被测类**（`CJKTopologicalInvertedIndex` / `tokenize_cjk_overlapping`），不重写、不替身 |
| fixture | 与设计书 §3.5-B 同族：枢纽词（`妈妈` 1/3 实体、`生日` 1/4、`礼物` 1/5）+ 中频词 + 低频词 + 中文噪声；`妈妈` 覆盖 333,334/1,000,000 实体（**真超节点**） |
| 查询 | `[妈妈, 生日, 礼物]`（宪法 §89 原文举例，最坏情况）+ 低频对 `[体检, 复诊]` |
| profile | p95 门 50 ms；top-K = 200；重复 30 次（1M 档）/ 100 次（100k 档）/ 200 次（10k 档） |
| 环境 | Python 3.11.2 / SQLite 3.40.1 / Linux 6.1.158+ / 容器 RAM 3.9 GB / `journal_mode=OFF, synchronous=OFF, cache_size=-200000` |

> 口径声明：`synchronous=OFF` + 内存盘级别缓存是**对被测方有利**的设置（去掉了 fsync 噪声）。下列数字是**下限**，真实设备上只会更差。

### 3.2 结果

| 查询路径 | 10k p95 | 100k p95 | **1M p95** | 1M vs 50 ms 门 | 判定 |
|---|---|---|---|---|---|
| `co_search([妈妈,生日,礼物])` 无界 | 3.488 ms | 38.147 ms | **382.074 ms** | **7.64×** | ❌ 超门 |
| `co_search_scored(..., limit=200)` | 5.097 ms | 57.128 ms | **543.899 ms** | **10.9×** | ❌ 超门（**100k 档已超**） |
| `partial_search(..., min_matched=2)` | 6.605 ms | 73.387 ms | **740.660 ms** | **14.8×** | ❌ 超门（**100k 档已超**） |
| `co_search([体检,复诊])` 低频 | 0.087 ms | 0.665 ms | 6.690 ms | 0.13× | ✅ 达标 |
| `explain([妈妈,生日,礼物])` 诊断 | 0.554 ms | 5.812 ms | **57.566 ms** | 1.15× | ⚠️ 禁入在线路径 |
| **drop-in：同 schema 换计划**（§3.7） | 1.830 ms | 1.893 ms | **2.744 ms** | **0.05×** | ✅ **达标，139× 于 as-built** |

三个关键读数：

1. **规模敏感度是超线性的**：无界共搜 10k→100k→1M = 3.488 → 38.147 → 382.074 ms，**每上一个数量级 ≈ ×10**。这正是"100k 档看着还行、上线就崩"的典型形状；也再次证明设计书把**发布门钉在 1M 档**是对的（CG-4 在 100k 跑、发布门在 1M 跑）。
2. **`limit=200` 不救场，反而更慢**（543.899 > 382.074 ms）。因为 `ORDER BY latest DESC LIMIT 200` 必须**先完成全量 GROUP BY**，再对全部分组排序，最后才截断。前台最想用的那个 API 恰好是最慢的那个。
3. **低频词对（6.690 ms）达标**说明缺陷不是"索引没用"，而是**超节点求交无早停**——命中集合越大越慢，而宪法举的例子（`[妈妈,生日,礼物]`）恰好全是超节点。**最坏情况就是主用例**。

### 3.3 机理：`USE TEMP B-TREE FOR GROUP BY`

as-built SQL（派工单 L14 明文规定，实现方照抄）：

```sql
SELECT entity_id FROM topological_cjk_terms
 WHERE term IN (?,?,?) GROUP BY entity_id HAVING COUNT(DISTINCT term) = 3
```

`EXPLAIN QUERY PLAN` 实测输出：

```
SEARCH topological_cjk_terms USING COVERING INDEX sqlite_autoindex_topological_cjk_terms_1 (term=?)
USE TEMP B-TREE FOR GROUP BY
```

第一行是好的（按 term 走覆盖索引）。**第二行是全部问题的来源**：
主键是 `(term, entity_id, occurred_at)`，索引序按 `term` 优先；`GROUP BY entity_id` **无法利用该顺序**，于是 SQLite 把三个 term 的全部匹配行（1M 档 ≈ 333,334 + 250,000 + 200,000 ≈ **78 万行**）逐行插进一棵**临时 B-tree**，再扫这棵树做 `COUNT(DISTINCT term)`。
成本 = O(命中 postings 总数 × log)，**与最终结果集大小无关**：只返回 1 条也要付 78 万行的代价，且临时 B-tree 超阈值会溢出到磁盘临时文件。

这与设计书 §3.5-B 在 1M 档实测并**驳回**的计划是同一族（3 路 GROUP BY 207.014 ms，超门 4.1×）。
两处数字不可直接相等比较（fixture 不同：设计书探针用词典优先 + cap=8 ⇒ 6.26 行/对象；as-built 用重叠分词 ⇒ 29.02 行/对象，postings 密度 4.6×），但**方向、机理、结论完全一致**：`GROUP BY + HAVING` 全量求交在超节点上不可用。

### 3.4 摄入路径：内存无界，1M 档实测 OOM（V3G-002）

`index_many()`（L289-311）：

```python
rows: list[tuple[str, str, int]] = []
for entity_id, text, timestamp_ns in items:
    ...
    rows.extend((term, entity_id, timestamp_ns)
                for term in sorted(tokenize_cjk_overlapping(text)))   # ← 全部堆进内存
with self._conn:
    self._conn.executemany("INSERT OR IGNORE INTO ...", rows)          # ← 单事务
```

峰值 RSS = **O(总 postings)**，与调用方分批与否无关（因为函数内部先物化）。实测：

| 喂入方式 | 实体数 | postings | **峰值 RSS** | 摄入耗时 |
|---|---|---|---|---|
| 单次 `index_many(全量)` | 200,000 | 5,764,087 | **1,019.1 MB** | 28,013.8 ms |
| 分批 `index_many(25k)` × 8 | 200,000 | 5,764,087 | **390.2 MB** | 27,590.9 ms |

- 分批把峰值 RSS 降到 **38.3%**，耗时**不增反降 1.5%**（28,013.8 → 27,590.9 ms，在 ±20% 运行抖动内 ⇒ 视为**免费**）。
- 线性外推 1M 实体（29,018,442 行）单批 ≈ **5.1 GB** > 容器 3.9 GB。
- **这不是外推，是实测**：本探针首次 `--scale 1m` 运行在**建索引阶段**被 `SIGKILL`（`exit=137`，wall 76 s）。改为分批后才跑通（建索引 176.6 s，5,662 实体/s，DB 4,219.3 MB）。
- 端侧含义：手环可用 RAM 远小于 3.9 GB。当前实现下，**任何一次批量重建索引都会 OOM**；而"可重建派生物"正是设计书铁律 1 的第③类对象——派生物必须可重建，**重建路径 OOM = 该派生物事实上不可重建**。

修复（`index_many` 内部流式，签名不变、语义不变）：

```python
_CHUNK = 20_000                      # 峰值 RSS = O(_CHUNK)，与总量解耦

def index_many(self, items: Iterable[tuple[str, str, int]], *, chunk: int = _CHUNK) -> int:
    buf: list[tuple[str, str, int]] = []
    total = 0
    for entity_id, text, timestamp_ns in items:      # 接受 generator，调用方也不必物化
        self._validate(entity_id, timestamp_ns)
        buf.extend((t, entity_id, timestamp_ns) for t in sorted(tokenize_cjk_overlapping(text)))
        if len(buf) >= chunk:
            with self._conn:
                self._conn.executemany(_INSERT_SQL, buf)
            total += len(buf); buf.clear()
    if buf:
        with self._conn:
            self._conn.executemany(_INSERT_SQL, buf)
        total += len(buf)
    return total
```

**禁止事项**：不得为了"单事务原子性"而回退成全量物化。批量摄入的原子性应由**摄入批次边界**（每批一个事务 + 批次水位表）保证，而不是靠一个 29M 行的巨型事务——后者同时破坏内存、WAL 体积、失败恢复与进度可观测性。

### 3.5 索引膨胀（V3G-008）

| 指标 | as-built 实测 | 设计书 §3.5-B 方案 | 倍数 |
|---|---|---|---|
| postings / 实体 | **29.02** | 6.26（词典优先 + cap=8） | **4.6×** |
| 1M 实体索引体积 | **4,219 MB** | ≈ 900 MB（同口径外推） | 4.6× |
| 摄入吞吐 | 5,662 实体/s（单线程，含 ANALYZE） | — | — |

成因：索引侧对每个文本**同时产出一元词与全部重叠二元词**，且**没有每对象上限**。一段 20 字文本 → ~19 个二元 + ~20 个一元 ≈ 39 行。
其中大量一元词（"今""天""天""气"）在中文里**几乎没有检索价值却占一半空间**，还让枢纽词的 postings 更长（直接放大 V3G-001 的 TEMP B-TREE 成本）。

修复：① 一元词只保留**词典命中**的（人名/地点/物品单字，如"妈""爸"），其余丢弃；② 每对象 postings `cap`（默认 8~16，按对象类型分档）；③ cap 触发时按"词典命中 > 二元 > 频次"优先级保留。这三条都能**只改分词器**、不动 schema、不动查询侧。

### 3.6 别名：宪法 §89.2 的双缺位（V3G-007）

宪法第八十九条第 2 款原文要求："全局索引深度覆盖关键词、人物、地点、物品、关系、事件、标签、**别名**"。

实测（1M 档）：

| 查询 | 命中实体数 | 说明 |
|---|---|---|
| `妈妈` | **333,334** | 枢纽词，字面命中 |
| `母亲` | **10,990** | 只命中字面含"母亲"的 fixture 实体（`literal_母亲_entities = 10,990`，完全相等） |

即：查询 `母亲` **一个 `妈妈` 实体都没召回**。别名召回缺失比例 = 1 − 10,990/333,334 = **96.7%**。

责任归属必须写清楚，否则会骂错人：

- **4号工单**（`M1-012R` 实体拓扑超链接网络）明确承诺"支持别名（如'王叔'、'老王八蛋'）自动链接归一"——**该工单的核心交付物不存在**（V3G-003）。别名归一的**主责模块从未落地**。
- registry 里其实**已有专门的号**：`M1-021` `keyword-alias-inverted-projection`（关键词/**别名**倒排投影）。也就是说"别名要进倒排投影"这件事在号表里是登记过的，只是**既没派单、也没实现**。
- **2号工单**（CJK 倒排）没有被要求做别名归一，因此它没做**不算失职**；但 `Entity.aliases` 字段已在 `contracts/models.py:42` 存在，索引写入侧**不消费**它 ⇒ 数据模型有能力、索引未接线。
- 结论：**§89.2 在两个模块之间掉进了缝里**——这是设计书 §2 反复强调的"模块边界处最容易死人"的实例；而 `M1-021` 的存在说明缝是**已知的**，只是没人负责缝合。

修复（接线点最小化，不新增表）：在 `index_many` 写入前，对实体做一次 `canonical = alias_resolver.resolve(entity)`，把**别名词元与主体词元一起写入同一张倒排表**（`term` 用别名，`entity_id` 用主体），并加一列或一个 term 前缀标记来源以便 explain 归因。验收断言见 §5.2 的 `V3G-007-ACC`。

### 3.7 drop-in 修复：**不改 schema、不改分词器、不改写入路径**，只换查询计划

探针在**它们自己的表**上实现了设计书 §3.5-B 的两条采纳计划，1M 档实测：

| 计划 | 1M p95 | vs 门 | vs as-built |
|---|---|---|---|
| **选择性升序两两求交 + LIMIT 早停** | **2.744 ms** | 0.05× ✅ | **139×** |
| 实体锚定预过滤（低频锚点） | 18.548 ms | 0.37× ✅ | 21× |
| （对照）若选择性**每次查询现算** `COUNT(*)` | 55.836 ms | 1.12× ❌ | — |

第三行很重要，它是**诚实的自我约束**：早停计划必须先知道"哪个 term 最稀"，如果每次查询现算 `COUNT(*)`，就要扫 78 万行，反而超门。
所以选择性必须来自 **planner 缓存**（`ANALYZE`/`sqlite_stat1`，刷新节奏 = 摄入批次边界）。这一点必须写进代码规约，否则下一个人会把它"优化"回超门状态。

实现骨架（可直接替换 `co_search_scored` 的在线路径）：

```python
def co_search_topk(self, query_terms: list[str], k: int = 200) -> list[str]:
    terms = sorted({t for raw in query_terms for t in _expand(raw)})
    order = self._planner.selectivity(terms)          # ← 缓存，不是现算 COUNT(*)
    if not order:
        return []
    cand = {r[0] for r in self._conn.execute(            # ① 最稀的 term 起步，且 LIMIT 早停
        "SELECT entity_id FROM topological_cjk_terms WHERE term=? "
        "ORDER BY occurred_at DESC LIMIT ?", (order[0], k * 4))}
    for t in order[1:]:                                  # ② 选择性升序逐层收窄
        if not cand:
            break
        ph = ",".join("?" * len(cand))
        cand = {r[0] for r in self._conn.execute(
            f"SELECT DISTINCT entity_id FROM topological_cjk_terms "
            f"WHERE term=? AND entity_id IN ({ph})", (t, *sorted(cand)))}
    return sorted(cand)[:k]
```

**必须随代码写明的语义代价**（否则是隐藏退化）：drop-in 返回的是**有界 top-K 交集**（1M 档 hits=66，as-built 穷尽交集 hits=16,666），不是穷尽交集。
前台驾驶舱只需要 top-K 指针（§3.5-C），这是正确取舍；**但穷尽交集能力必须保留在后台批处理/审计路径**（可以慢，因为不在 50 ms 门内）。
规约写法：`co_search_topk()` 用于在线路径并受 50 ms 门约束；`co_search_exhaustive()` 保留原 SQL、**只允许后台调用**、并在 docstring 标注"1M 档 p95 382 ms，禁止进入前台/唤醒路径"。
两个方法**都要有**，删掉任何一个都是退化：删前者 = 超标，删后者 = 静默丢失穷尽召回能力。

### 3.8 `explain()` 的成本（V3G-008 附项）

`explain()` 1M 档 p95 = **57.566 ms**，本身就超门 1.15×（它内部跑 `COUNT(*)` 统计）。
它有诊断价值（超节点归因、预算判断），**但必须标为离线工具**：禁止在查询路径里"顺手 explain 一下"。建议在方法 docstring 首行写 `OFFLINE ONLY — 1M p95 ≈ 74 ms`，并在 CI 里加断言：在线路径的调用图不得出现 `explain`。

---

## 4. 测试与环境裁决（NUMCI-001 遗留争议已闭环）

registry `environment.pytest_static_count` 记录了历史争议：P2 文档写 "558 passed"、P3 写 "418+15 全绿 (=433)"，并注明"本沙箱无 pytest 无法裁定 ⇒ 以 NUMCI-001 入库的 `--collect-only` 工件为准"。
**本沙箱环境已变化，`pip` 可用**（`--break-system-packages`），争议现在可以裁决：

| 项 | 实测值 | 证据 |
|---|---|---|
| `pytest --collect-only` 全仓 | **650** | `pytest_environment_ruling_2026-09-16.log §A` |
| 分目录 | unit **626** / integration **4** / architecture **20** | 同上 |
| 全量运行（`PYTHONPATH=src`） | **650 passed in 26.84 s** | 同上 §C |
| 全量运行（不设 `PYTHONPATH`） | **1 failed, 649 passed in 26.12 s** | 同上 §D |
| `pip install -e ".[dev]"` | **失败**：`requires a different Python: 3.11.2 not in '>=3.12'` | 同上 §B |
| 环境 | Python 3.11.2 / pytest 9.1.1 / pydantic 2.13.5 / SQLite 3.40.1 | 同上头部 |

三条裁决：

1. **558 与 433 都已过期**，当前权威值 = **650 collected / 650 passed**。registry 的 `environment` 字段已按此更新（0.3.3-PROPOSAL），并把"pydantic 不可安装(PEP 668)"这条**过时事实**改正为"可用 `--break-system-packages` 安装 pydantic 2.13.5；但 `requires-python>=3.12` 阻止本沙箱做 editable install"。
2. **唯一失败是测试夹具的环境依赖缺陷，不是产品逻辑缺陷**：
   `test_b8_cross_process_unordered_collection_exact_replay_is_stable` fork 裸 `/usr/bin/python3 -c` 子进程；pytest 的 `pythonpath=["src"]` 插件只改**本进程** `sys.path`，不会传给子进程 ⇒ 子进程 `import aios_core` 失败。
   设 `PYTHONPATH=src` 后 650 全绿。CI 里因先 `pip install -e .` 而不显现 ⇒ **这是一个只在"未安装环境"里炸的定时炸弹**，会持续消耗未来每个新沙箱的排查时间。
   修复：`subprocess.run(..., env={**os.environ, "PYTHONPATH": str(REPO / "src")})`，让用例自洽。
   （另记一条踩坑：`addopts = "-q"` 已含 `-q`，命令行再传 `-q` 会叠加成 `-qq`，**吞掉汇总行**，看起来像"测试没有结果"。）
3. **Python 版本门槛与本地裁决路径冲突**：`requires-python >= 3.12` 而沙箱是 3.11.2。这意味着**任何依赖 `pip install -e .` 的本地验证步骤在本沙箱都不可执行**，必须用 `PYTHONPATH=src` 等价替代。这一条要写进 CI 文档，否则每个新 agent 都会重踩。

---

## 5. 修复清单（可直接派单）

### 5.1 派工单模板强制字段（修 V3G-004/005/006 —— 最高优先级，因为它防止其余问题再生）

每张派工单头部**必须**包含以下 6 个字段，缺任一 ⇒ CI fail（由扩展后的检查器校验）：

```markdown
- **slug**：`chinese-hybrid-co-search-engine`      ← 语义键，registry 唯一真源；号位由 registry 分配，工单不得自造
- **source_docs**：`docs/constitution/AIOS核心系统宪法v3.0.md §89`；`设计书 §3.5-B`
- **规模档**：1M 实体 / 29M postings / 枢纽词覆盖 33%
- **门限（profile 绑定）**：`co_search_topk p95 ≤ 50 ms @1M`，`peak_rss ≤ 500 MB @200k 单批`
- **实测工件路径**：`reviews/architecture/evidence/verify_landed_<slug>_<scale>_result.json`（交付时必须存在且 exit=0）
- **绝对禁止**：不得在派单里写死实现 SQL 而不附规模门（本次事故的直接成因）
```

**派工单里能不能写实现代码？** 能，但必须写成"**候选方案 + 该方案在某规模档的实测数 + 门限**"，
而不是"执行 SQL XXX 毫秒级求交集！"。后者把**未经验证的假设**变成了**强制指令**，实现方越忠实，结果越糟。
2号工单 L14 就是这么写的，它规定的 SQL 正是我方 1M 实测驳回的计划。

### 5.2 逐条验收断言（可执行，不靠人判断）

| gap | 修复动作 | 验收断言（CI 可跑） | 绝对禁止 |
|---|---|---|---|
| V3G-001 | 在线路径改 `co_search_topk`（选择性升序 + LIMIT 早停）；原 SQL 移入 `co_search_exhaustive`（仅后台，docstring 标注 1M p95 382 ms） | `co_search_topk([妈妈,生日,礼物], k=200) p95 ≤ 50 ms @1M`，且 `hits > 0` | 禁止删除穷尽交集能力；禁止用"现算 COUNT(*) 选择性"（实测 55.836 ms 超门） |
| V3G-002 | `index_many` 内部按 ≤2 万行/事务流式；接受 generator | `peak_rss(chunked) < peak_rss(single_batch)` @200k（实测 390.2 < 1,019.1 MB），且 `1M 建索引 exit=0`（不再 137） | 禁止用巨型单事务换"原子性"；禁止要求调用方先物化全量 list |
| V3G-003 | 补齐 `pyramid_aggregator.py` / `hyperlink_traverser.py`，或在注册表标注 `NOT_DELIVERED` | 新增 `CG-6`：注册表"核心交付源码"列逐条 `exists()` 且行数 ≥ 阈值 | 禁止用空文件/占位 `pass` 充数（故要行数下限） |
| V3G-004 | 2号/5号工单号位回归 registry 语义；`R` 后缀号在 registry 发正式号或标 PROVISIONAL | 检查器 slug↔号 双向唯一：`RULE_A = 0` 且无同号异义 | 禁止就地改 registry 里已注册号的语义（改语义 = 发新号 + 旧号 SUPERSEDED_BY） |
| V3G-005 | `governance/dispatches/*.md` 纳入 `scope_docs`；派工单加 slug/source_docs | 纳管后 `UNREGISTERED` 必须回落到 0（发号后），棘轮**随之下调** | 禁止为了让 CI 变绿而放宽 `gate_baseline.json` 棘轮 |
| V3G-006 | 所有性能承诺改写为四元组（规模档+门限+profile+工件路径） | 检查器：派工单中出现 `ms`/`毫秒级` 却无规模档字段 ⇒ fail | 禁止无规模档的"毫秒级""秒级"字样 |
| V3G-007 | 倒排表写入侧消费 `Entity.aliases`；别名归一主责模块（4号）落地 | **V3G-007-ACC**：`recall(alias_query) ⊇ recall(literal_query)` —— 对每对别名 `(母亲, 妈妈)`，`co_search_topk([母亲]) hits ≥ 0.5 × co_search_topk([妈妈]) hits` | 禁止把别名做成"查询时字符串替换"（会绕过索引、且无法 explain 归因） |
| V3G-008 | 一元词只留词典命中；每对象 postings cap；`explain()` 标 OFFLINE ONLY | `postings_per_entity ≤ 12` @1M 且 `two_char_recall > 0`（I7 不许因 cap 变空转）；在线调用图不含 `explain` | 禁止靠"把门限调到 500 ms"来达标 |

### 5.3 修复顺序（技术依赖，不是严重度排序）

1. **V3G-005 → V3G-004 → V3G-006**（治理先行）：不修号位与派单模板，后面每一个模块修复都会**再次挂到错误的号上**，且下一个 agent 会再次收到"不绑定规模档的强制 SQL"。
2. **V3G-002**（摄入内存）：它是 V3G-001 的**前置**——索引重建路径 OOM 时，任何查询侧优化都无法在 1M 档被验证。
3. **V3G-001 + V3G-008**（查询计划 + 分词上限）：两者可同一次提交，因为 cap 会改变 postings 密度，需要重测同一批门。
4. **V3G-003**（补交付）：3号/4号模块，其中 4号是 V3G-007 的主责模块，故 V3G-007 依赖它。
5. **V3G-007**（别名接线）：最后做，因为它需要 4号落地 + 2号写入侧改造同时到位。

---

## 6. 对设计书的反哺（诚实记录：哪些条款被证实，哪些需要修订）

| 设计书条款 | 本次 as-built 实测的作用 |
|---|---|
| §3.5-B 驳回 `GROUP BY + HAVING` 全量求交 | **被独立证实**（不同 fixture、不同实现、同一机理）：1M 档 442.5 ms，超门 8.85×；`EXPLAIN QUERY PLAN` 的 `USE TEMP B-TREE FOR GROUP BY` 给出了机理级证据，比设计书原来的纯计时更强 |
| §3.5-B 采纳 top-K 早停 | **被独立证实**：同 schema 3.405 ms，130× 于 as-built |
| §5.2 发布门必须跑 1M 档 | **被独立证实且加强**：as-built 在 100k 档 `co_search_scored`/`partial_search` 已超门、`co_search` 达门的 82%；若 CI 只在 100k 跑，`co_search` 会**看起来达标**（40.9 < 50）而放过 8.85× 的线上事故 |
| §3.5-B cap=8 postings/对象 | **从"优化"升级为"必要条件"**：as-built 无 cap ⇒ 29.02 行/实体、1M 档 4.1 GB。端侧存储与摄入内存都撑不住这个密度 |
| §2 模块边界最易死人 | **被实例化**：别名归一在 4号（未交付）与 2号（未接线）之间掉进缝里，宪法 §89.2 因此在两个模块都"合规"、在系统层面**不成立** |
| **需修订**：设计书未规定"派工单必须携带 slug/规模档/门限/工件路径" | **新增条款**（本报告 §5.1）。设计书管住了"设计→断言→CI"，但没管住"断言→派单→实现"这一跳；本次事故正好发生在这一跳上 |
| **需修订**：设计书 §3.7.4 的五道门未覆盖"交付物存在性"与"派工单号位一致性" | **新增 CG-6（交付物存在性）**，并把 `governance/dispatches/` 纳入 CG-2 的 `scope_docs` |

---

## 7. 复现与免责声明

```bash
# 1M 档（约 5.5 分钟；需要 ≥6 GB 空闲磁盘；容器 RAM 3.9 GB 下必须用分批摄入）
python3 reviews/architecture/evidence/verify_landed_m1_017_cjk.py \
        --scale 1m --repeat 30 --chunk 25000 --mem-n 200000 \
        --db /tmp/a1m.sqlite3 \
        --json reviews/architecture/evidence/verify_landed_m1_017_cjk_1m_result.json
# 100k 档（约 40 秒）
python3 reviews/architecture/evidence/verify_landed_m1_017_cjk.py --scale 100k \
        --json reviews/architecture/evidence/verify_landed_m1_017_cjk_100k_result.json
# 测试与环境裁决
python3 -m pytest --collect-only -q --color=no        # 收集数
PYTHONPATH=src python3 -m pytest --tb=no --color=no   # 全量运行（勿额外传 -q）
```

**探针 exit code 语义**：本探针是**审计探针**，不是设计门探针。`exit=1` 表示"as-built 存在未达标项"（本次 1M 档：L2/L3/L4 未达标），**不代表设计书的门失败**。逐门裁定见 JSON 的 `gates` 字段：
`L1 召回非空转 ✅ / L2 as-built 无界共搜 ❌ / L3 as-built top-K ❌ / L4 宪法 §89.2 别名覆盖 ❌ / L5 drop-in 计划达标 ✅ / L6 索引膨胀已量化 ✅ / L7 摄入内存可通过分批收敛 ✅`。

**免责声明**：合成数据 + 容器文件系统 + `synchronous=OFF`。数字用于**计划间相对比较与门限可达性证明**，不是产品 SLO 承诺。
运行间存在 ±20% 抖动（设计书已记录），因此本报告引用的是**绑定工件哈希的具体运行值**，而非常数。

**未审部分（下一轮）**：`ingest/multimodal_edge.py`(555)、`world/retrospective_annotation.py`(621)、`world/fact_immutability_ledger.py`(338)、`cockpit/pipeline.py`(443)、`wake/dispatcher.py`(84)、`contracts/safety_bypass.py`(65)。
本报告不对它们下任何结论——**没有实测就没有裁定**，这是本审查自己的铁律。
