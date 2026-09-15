# R4 政策层 × v3.0.1 裁决集（ADJ-001~012）对齐报告
#
# （三轮：§0~§7 第一轮 · §8 第二轮 THRESH-BASE 落地 · §9 第三轮 两条 v1.1.0 合并）

> **日期**：2026-09-15
> **对齐双方**：
> - `governance/runtime_policy.json` v1.0.0（本会话产出，上位文档为 `AIOS_Core_任务规划与开发任务拆分重构方案_R4.md`）
> - `governance/v3.0.1_规范裁决集_ADJ-001-012.md`（并行会话产出，已按宪法第 115 条二级程序签发）
> **裁决规则**：裁决集明文「凡 v3.0 原文与本裁决集冲突处，以本裁决集为准」。政策层是裁决集的下位法，**凡冲突处改政策层，不改裁决集**。
> **产出**：`governance/runtime_policy.json` v1.1.0 + `tests/policy/`（118 条判决断言 / 206 个违宪变异回归）
> **结论摘要**：12 条裁决，**3 条我错了、6 条 ADJ 更锐利、2 条方向一致我做了编码、1 条编号对撞已上交**。没有一条是「我对 ADJ 错」。

---

> **读者指引**：本报告分两轮。§0~§7 是第一轮（ADJ-001~012 逐条对齐）；
> **§8 是同日第二轮** —— THRESH-BASE（`governance/thresholds/baseline_v1.json`）落地之后，
> 我在一小时内又漂移了两次，并撞上规范版本注册表的一个规则组合死结。
> §7 的结论原文保留未改。
> **§9 是同日第三轮** —— 推送受阻期间另一条工作线也重写了政策层并自称 v1.1.0，
> 两条线在同一天各自独立撞上同一个注册表死结、给出两种解法；本节记录合并、
> 采纳对方解法的理由、以及我踩出的那条会让**宪基静默失去哈希保护**的边界缺陷。

## 0. 先说结论里最难听的部分

我在 v1.0.0 里写了一整段 `id_namespace_registry`，专门用来防止编号漂移。
**然后在同一周里，我自己成了它的第二个案例。**

仓库里现在有两份 R4 重构方案：

| | 文件 | 模块表 | 注册状态 |
|---|---|---|---|
| **PLAN-R4** | `AIOS_Core_任务规划与开发任务拆分重构方案_R4_独立首席架构师版.md` | **C01~C16** | 已登记于 `governance/normative_versions/registry.md`，PROPOSED→随 G0 签发转 CURRENT |
| **R4（我的）** | `AIOS_Core_任务规划与开发任务拆分重构方案_R4.md` | **C01~C18** | **未登记** |

而 `ADJ-010 §1` 裁定：「以 v3.0.1 起，AC 模块映射唯一本为**【R4 重构方案 §2.1】的 C01~C16 全表**（含新增 C15 上下文装配层、C16 交互端口）」——**引用的是 PLAN-R4，不是我这份。**

四个编号直接对撞：

| ID | PLAN-R4（已落库） | 我的 R4（未落库） |
|---|---|---|
| **C15** | 上下文装配层 | 仿真、评估与纵向守卫 |
| **C16** | 交互端口（NotificationReceipt / 穿戴 FSM） | 端侧摄入适配（边缘轻量化） |
| **C17** | 不存在 | 资源治理与预算执行 |
| **C18** | 不存在 | 政策与合规守卫 |

**既成事实的证据**：`governance/traceability_matrix.csv` 第 6 行
`C02-no_forced_interrupt,第五条,...,C16,NotificationReceipt,M2-022;M2-023,...`
—— `module` 列是 C16、`world_objects` 是 NotificationReceipt，**矩阵已按 PLAN-R4 语义落库**。我的 C16（端侧摄入）与它直接冲突。

按 `registry.md` 规则④「任何本表未收录的 README/博客/口头决议，一律不构成工程基准」，**我这份 R4 目前不是工程基准**。按 `ADJ-010 §3`「模块/里程碑新增、合并或改义必须进行一级治理变更；映射者哈希不一致即 CI 红」，我无权自裁。

### 我的处置（已写入政策层，可判红）

1. **不自封权威**：`id_namespace_registry.namespaces["C01..C16"].status = CONTESTED_SEE_module_namespace_collision`；我提出的 `C17..C18` / `M0.1` / `M-CI` / `CP1..CP4` 一律标记 `PROPOSAL_NOT_BASELINE`。
2. **提交合并提案，等一级治理变更裁决**：保留 PLAN-R4 的 C15/C16（已落库，迁移成本既成事实），**我的四个职能改编号为 C17~C20**：

| 我的职能 | 改编号为 |
|---|---|
| 仿真、评估与纵向守卫 | **C17** |
| 端侧摄入适配（边缘轻量化） | **C18** |
| 资源治理与预算执行 | **C19** |
| 政策与合规守卫 | **C20** |

   原则：**已落库到追溯矩阵的编号有既成事实的迁移成本优势，未落库的一方改名，社会成本最低。** 这是 ADJ-011「键绝不回收复用」精神的延伸 —— 冲突时让未被引用的一方让位。
3. **合并重叠的门**：我的 `M0.1`（阻塞性契约补丁门）并入 ADJ-010 的 `M0'`；我的 `CP1`（检索规模硬门）并入 ADJ-010 的 `M1.X`。两者语义高度重叠，并存只会制造第二套里程碑编号。
4. **保留但不丢弃**：C19/C20（资源治理与政策合规守卫）是 PLAN-R4 缺失的真实职能 —— **本次对齐的全部工作量都花在了 C20 的职责范围内**，它不该因编号冲突而消失。

> **自我评估**：我在 v1.0.0 里写命名冲突检测器时，脑子里想的是「旧文档那帮人」。
> 真正的教训是：**命名冲突检测器不能只对着旧文档跑，它必须对着所有新文档跑，包括它自己的作者写的那一份。**
> 政策层 v1.1.0 已把这条变成断言：`test_contested_namespaces_are_marked_as_proposals_not_baselines`。

---

## 1. 三处我错了（不是「不够好」，是错）

### 1.1 ADJ-001 §2 —— 我的 `order_strictly_enforced` 混淆了两个正交约束

**我 v1.0.0 写的**：
```json
"mental_startup": {
  "resolution": "checklist_not_pipeline",
  "order_strictly_enforced": false
}
```

**ADJ-001 §2 裁定的**：
> 第 84.2 条的「照镜子→校准羁绊→定姿态→审视世界与触发源」实现为单份 Cockpit Manifest 内部
> `step1_self → step2_rapport → step3_stance → step4_world` 的**段落排版顺序**。
> 四步序是**布局规格（layout）**，不是**网络调用规格（network）**。
> 严禁将四步序实装为四次以上串行推理往返；`≥2 次往返才能完成首次响应` 视为违宪。

**我错在哪**：宪法 C3 矛盾（§84之2「顺序绝对不可颠倒」 vs §110之14「不被固定认知流水线限制」 vs §86之3「绝对不得强制固定阅读顺序」）的正确解法，是把「顺序」劈成两个不同的东西：

| | 该严格吗 | 宪法依据 |
|---|---|---|
| **排版序**（同一份 Manifest 里的段落先后） | **必须严格**，且有静态校验 | §84之2 |
| **调用序**（是否发四次模型请求） | **必须不严格**，且严禁 ≥2 次往返 | §110之14 / §86之3 |

我用**一个布尔值**承载了**两个正交约束**，结果是两个都没约束。更糟的是：

> **我的回归用例 CASE-55 主动惩罚了正确的取值。** 它把 `order_strictly_enforced = True` 当成违宪变异，而 ADJ-001 之后「排版序严格」恰恰是合法的、必需的。
> **一个测试在守卫一个 bug。** 这比没有测试更坏 —— 它会让正确的修复判红。

**v1.1.0 的修正**：
```json
"resolution": "layout_not_pipeline",
"layout_order_strictly_enforced": true,
"layout_order_static_check_must_be_green": true,
"call_order_strictly_enforced": false,
"four_step_as_multiple_serial_calls_prohibited": true,
"first_response_round_trips_max": 1
```

`resolution` 也从 `checklist_not_pipeline` 改成 `layout_not_pipeline`。**这不是措辞**：「清单」暗示四步是四个可独立勾选的动作，仍可被实装成四次调用；「排版」明确它们是同一份 Manifest 里的四个段落，**物理上不可能**变成四次调用。

新增的 `first_response_round_trips_max = 1` 是 ADJ 给我的最好礼物：**它比我原来任何一条约束都更硬，也更容易自动校验 —— 数网络往返次数即可，不需要理解语义。** 它同时保住 §84（四步都在）与 §85之1（1 秒首字）。

**顺带发现 ADJ-001 §3 是整套裁决里最漂亮的一处解法**。§78（Wake Reason 第一）、§80之2（方便度第一）、§84之2（四步序第一）三条各自宣称某个动作是「第一」，字面上互斥。ADJ 指出它们作用于三个不同子系统：

| 条款 | 「第一」的种类 | 决定什么 | 子系统 |
|---|---|---|---|
| §78 | `task_pointer` | 看与办什么 | 调度类 |
| §80之2 | `delivery_gate` | 此刻能否出声 | 信道类 |
| §84之2 | `personality_startup` | 以什么心境看 | 装配置版类 |

**矛盾不是靠选一个赢家解决的，是靠发现它们根本不在同一个维度上解决的。** 我把这个结构原样编码进了 `mental_startup.three_firsts_are_different_subsystems`，并加断言要求三者必须落在三个不同子系统 —— 塌缩到同一个，C3 矛盾就原地复活。

### 1.2 ADJ-011 —— 我的全部 `constitution_ref` 是不合规格式

**ADJ-011 §2**：
> 现有的第一百一十条/条号/章号保留为「友好别名」，但任何正式 Issue、代码注释、测试名、审计报告一律须引用**稳定键**。……**「条号」本身即为不能再承载语义的印刷物。**

**我 v1.0.0 写的**：全部是裸条号 —— `§86(条件驱动零浪费)`、`§93之1`、`§84之2`。按 ADJ-011，一份新建的正式文件用裸条号，属不合规。

ADJ-011 的立法理由我完全认同，而且它举的病例我在断层审计里也抓到过：**【工作台规格 L305】引用「宪法第三十四条」，而 v3.0 的第三十四条讲的是「Observation 不直接唤醒」（稳定键 `C10-obs_no_wake`），与工作台规格想引的十三步循环毫无关系** —— 那是 v2.0 的条号残留。条号会漂移，稳定键不会。

**v1.1.0 的修正**：为每个域补入 `constitution_stable_keys`，映射自 `governance/traceability_matrix.csv` 的 120 个已注册键；裸条号保留为人类可读别名。

并且我把它变成了**跨文件引用完整性检查**：
```python
def test_every_cited_stable_key_is_actually_registered() -> None:
    cited = _collect_stable_key_refs(POLICY)          # 递归收集全部 constitution_stable_keys
    unregistered = sorted({k for k in cited if k not in STABLE_KEYS})   # STABLE_KEYS 来自 CSV
    assert not unregistered
```
**稳定键制度若允许引用不存在的键，它就退化成了另一套会漂移的编号 —— 而漂移正是它要消灭的东西。** 实测：政策层引用的全部稳定键 100% 命中矩阵。

### 1.3 ADJ-012 —— 我自拟的 `ARCH-01~10` 被 `P01~P10` 取代

断层审计 G01~G08 的核心事故：`A01~A10` 在两份文档里 **10/10 同号不同义**。`M2-011 §H` 写着「R1-10/W12/**A06** 通过」，用的是《架构规划》义（重复投递不重复行动），而宪法 A06 = **世界搜索可用**。**世界搜索从未被验证过，却在 gate 上显示 PASS。**

我 v1.0.0 的解法：把架构规划那一套改名 `ARCH-01..10`。
ADJ-012 的解法：把它整体重命名为 **`P01~P10`（Prototype Acceptance）**，原 A0x→P0x 一一对应、语义不变。

**意图完全相同，名字不同，ADJ 是法律。** 我标记 `ARCH-01..10` 为 `SUPERSEDED_BY_ADJ_012` 并指向 `P01..P10`。

**关键处置：不悄悄删掉。** 被取代的命名必须显式标记并指向替代者 —— 否则读过 v1.0.0 的人会继续用 `ARCH-01~10`，漂移会以「两个都对」的形式延续。断言：`test_my_superseded_naming_is_marked_not_silently_dropped`。

---

## 2. 六处 ADJ 更锐利（方向对，但我的版本弱一档）

### 2.1 ADJ-004 §3 —— 从「策略偏好」升级到「能力边界」（本次对齐最重要的一处）

**我 v1.0.0 写的**：
```json
"janitor_tiering": {"llm_share": 0.05, "llm_role": "tie_break_only"}
```

**ADJ-004 §3 裁定的**：
> 第二阶段=物理粉碎（加密擦除接口），**仅机械保留 Worker 可调用**；
> **LLM 对第二阶段无直接调用权限**，LLM 提供的删除意图一律先在候选池排队，
> 经机械审计（引用锁/类别/legal hold）后由机械 Worker 执行。

**差别是决定性的**：

| | 我 v1.0.0 | ADJ-004 |
|---|---|---|
| 形态 | `llm_role = "tie_break_only"` | `llm_direct_call_permission = false` |
| 性质 | **策略偏好** | **能力边界** |
| 能否被绕过 | 改一行配置就行 | 不能 —— LLM 根本没有这个调用权限 |

对一个把「删除」交给语言模型判断的系统，这个区别就是**「偶尔删错」与「结构上不可能删错」**的区别。策略偏好可以被绕过，能力边界不能。

ADJ-004 还补了两处我完全缺失的东西：

**① 永存对象清单（引用锁）**：Claim / EventAnchor / EvidenceSet / Summary / LifeChapter / Prediction / Goal / Task / Wake / Session / Action / Outcome 十二类对象的版本链**永存**；被它们引用的 Observation 与原话切片**永存**；**DeletionLog 本身永存**。
最后一条尤其关键 —— 否则删除记录可被删除，**一个能抹掉自己抹除痕迹的系统无法被审计**。

**② 出土兼容性（ADJ-004 §4）**：
> 任何代码路径查询已粉碎数据的 canonical ID **必须返回 Tombstone** 而非「不存在」或断链。

这条我 v1.0.0 完全没有，而它是最后一道防线。差别是决定性的：

| 返回 | 上层认知的解读 |
|---|---|
| `not_found` | 「这件事**从未发生过**」→ 历史虚无 |
| `Tombstone` | 「这件事**发生过**，但其原始载体已依法销毁」→ 历史诚实 |

**③ 可吊销对象的三条件**（缺一不可）：① 降采样特征块 + 异常片段 + 协商后的语义化结论已以可审计形态（transform lineage）落库；② 未被任何永存对象引用；③ 不在 legal hold 下。

条件 ① 保证「删掉原始数据」之后语义化结论仍可审计追溯 —— 这是 §33之5（轻量化）与 §27（证据链绝对不可逆断裂）能同时成立的唯一方式。

**我的 `resolution` 名也改了**：v1.0.0 叫 `tiered_retention_with_quarantine`（分档留存+隔离冷却），ADJ 的结构更准确 —— 核心不是「分档」，而是**「引用锁决定谁可吊销」+「两阶段决定怎么吊销」**，已改为 `two_phase_tombstone_with_reference_lock`。

### 2.2 ADJ-007 §1 —— 计时边界不同，不是数字不同

**我 v1.0.0 写的**：`fast_lane_first_token_ms: {p50: 600, p95: 1000}`，六段串行预算含 `vad_tail_silence` 与 `asr_finalize`。

**ADJ-007 §1 裁定的**：
> 「1 秒首字」立法定为**暖路径 SLO 而非绝对承诺**：以 **ASR final / 用户文本入队**为计时起点，
> 目标 p50 ≤ 1.0s、p95 ≤ 1.5s（notify 车道）；冷连接/冷模型/深调查车道显式标注「不在此承诺内」；
> 超出时必须有用户可感知降级（先震动、先摘要）。
> 计时说明：**不含** ASR 本身的终稿形成，**不含**后置 TTS 完整成句（那是 TTFAudio 指标）。

**这不是「ADJ 宽松、我严格」的问题，是两个不同的指标。** 重新按 ADJ 边界计算我的六段预算：

| 阶段 | where | 属于法定边界？ | min~max (ms) |
|---|---|---|---|
| vad_tail_silence | device | **否**（在 ASR final 之前） | 150~250 |
| asr_finalize | device | **否** | 80~200 |
| manifest_assembly | service | 是 | 15~40 |
| co_search_net_add | service | 是 | 0~60 |
| network_rtt | network | 是 | 60~200 |
| cloud_prefill_ttft | cloud | 是 | 120~250 |
| **法定边界内合计** | | | **195~550** |
| **体感边界内合计** | | | **425~1000** |

法定 p95 = 1500，实测最坏 550ms → **余量 2.7×**。体感 p95 = 1000，实测最坏 1000ms → **余量 1.0×，刚好卡住**。

**两个指标都必须保留，理由是对称的**：

- 只留法定值 → **产品会合法地慢**。法定 SLO 是审计下限，不是产品目标。用户体感从开口算起，把 VAD 尾静音与 ASR 终稿的 230~450ms 也算进去后仍要求 p95 ≤ 1000ms，才能倒逼「推测式召回」与「prefix KV-cache」这两个杠杆真的被实现。
- 只留体感值 → **审计不过**。法定 SLO 无人守。

v1.1.0 拆成 `legal_slo_from_asr_final_ms`（authority = ADJ-007 §1，blocker）与 `perceived_slo_from_speech_onset_ms`（authority = 本政策层自设，warning），并**要求体感值必须严于法定值** —— 否则它不构成额外约束，白占一个字段。

**顺带修了一处我自己都没发现的漏洞**：每个阶段必须声明 `inside_legal_slo`，且**设备侧阶段必须在法定边界之外**。这一条纯算术断言抓不到 —— 把 `vad_tail_silence` 标成 inside 之后，法定边界内串行和 800ms 仍 < p95 1500ms，「达标」。但后果是真实的：**团队会去优化一个根本不该被计入法定预算的阶段，而真正的法定余量被虚报。** 已加断言 `test_latency_stage_boundaries_match_their_physical_position`。

### 2.3 ADJ-007 §2 —— 「零误触」的法定判据比我精确得多

**我 v1.0.0 写的**：`zero_mistrigger_claim_is_not_falsifiable = true`，要求测 FAR（误接受率）、窗口内误触发率、送达确认率，并规定噪声语料（袖子摩擦/桌面传导/骑行颠簸/睡眠/厚衣袖/嘈杂地铁）。

**ADJ-007 §2 裁定的**：
> 「零误触」是「防误触机制的下限目标」而非「广告标语」：验收判据 = **`false_playback_without_epoch = 0`**（无通知 epoch 的马达骨传导通路必须断电）。
> **并非「要做到全世界都不会触错」—— 侧键误按、误点碰仍允许发生，只要它们不进入语音播报。**

**ADJ 划清了法定门与质量指标的界线，而我把两者混在一起了。** 我的 FAR 框架比法律更严；**更严不是错，但把它当法定门会让 gate 在合法行为上判红 —— 久而久之团队会学会忽略红灯。** 一个总是误报的门，等于没有门。

v1.1.0：`false_playback_without_epoch = 0` 是 blocker 级法定门；FAR 跨噪声语料降为 warning 级质量指标（仍然要测、要报趋势，但振动误报本身不构成违宪）。

**并且我强化了 I1 不变量**：
```
v1.0.0:  I1 = bone_conduction_enabled == (state == 'triggered')
v1.1.0:  I1 = bone_conduction_enabled == (state == 'triggered') and notification_epoch exists
```
少了 epoch 条件，「无通知 epoch 时通路必须断电」就没有实现载体 —— 而那是 `false_playback_without_epoch = 0` 的**唯一执行点**（在 Step-0 §1(c) 投放信道合法性检查中）。

### 2.4 ADJ-007 §3 —— 1~3 句的例外我有 1 类，ADJ 有 4 类，而且我漏的那类形态不同

| | 例外 | 我 v1.0.0 | ADJ-007 §3 |
|---|---|---|---|
| (a) | 用户明示展开（**措辞模糊也算信号**） | ✗ 漏 | ✓ |
| (b) | 人身安全 / 重大健康风险 / 法律权限 | ✓ 有（`applies_to` 四项） | ✓ |
| (c) | **无障碍需求群体，详尽度为默认反倾** | ✗ 漏 | ✓ |
| (d) | 系统自查发现短答造成事实缺口 → 可突破但必须落 CommExp 记录 | ✗ 漏 | ✓ |

**(c) 是我最该反省的一处，因为它的形态与我写的例外根本不同**：

- 我写的例外是**「例外放行」**：默认短，检测到条件才放宽。
- ADJ 的 (c) 是**「默认反转」**：对视觉门诊者与老年人，**详尽是默认值，短答才需要理由**。

**写成例外的实际后果**：实现者只在检测到明确请求时才放宽，而**老年用户往往不会请求**。一个把「1~3 句」当铁律、只在用户说「展开」时才放宽的系统，对最需要详尽的人群恰恰最不详尽。已编码为 `c_accessibility_default_reversal.verbosity_is_default = true`。

**(a) 也比我想象的宽**：ADJ 明文「措辞模糊也算信号，例如『讲讲你到底怎么想的』」。**这比关键词匹配宽 —— 实现上需要意图分类，不能用黑名单。** 若只匹配「展开/详细说说」，那句最需要长答的话会被 3 句上限掐断。

**ADJ-007 §3 的结论句是我 v1.0.0 完全没有的一条优先级裁定**：
> 「1~3 句」服从于「事实完整」与「安全」，**不服从于「看起来不像机器人」**。

差别在于：**例外清单告诉实现者「这些情况可以长」，优先级告诉实现者「冲突时牺牲哪一个」。** v1.0.0 我写了例外但没写优先级，于是实现者仍可能为了「像个真人」而砍掉必要信息 —— **而且砍得理直气壮，因为政策说了要短。** 已编码为 `priority_order: ["事实完整", "安全", "1~3 句短表达"]` + `anti_robot_appearance_is_not_a_valid_reason_to_truncate = true`。

### 2.5 ADJ-005 / ADJ-006 / ADJ-009 —— 三处我完全没有的构件

**ADJ-005 回溯标注的唯一合法形式**。我只有 P1 原则（索引是日志的纯函数），**但 P1 只约束索引，不约束对象版本链** —— 缺了它，工程师照样可以直接改旧 Summary 的数值行。ADJ 给出 bi-temporal 结构：

```
RetrospectiveAnnotation(anchor_ref: pinned revision,
                        valid_time: 该事实有效的过去区间,
                        learned_at: T_now,
                        payload, evidence_refs)
```

`valid_time` 与 `learned_at` 分离是实质：**二者合一就无法同时呈现「当时映照（当时不知道）」与「今日回看（今日知道）」两个版本** —— 而那是 §93（不可篡改）与 §31之一（反向修正权）能共存的唯一方式。这与 Zep/Graphiti 的 bi-temporal edge 设计同源，但 ADJ 是从宪法条款独立推出的。

验收锚是**字节级哈希变分 = 0** —— 一个可以无歧义判定的硬门，比任何语义审查都可靠。心率值、当时坐姿、原话音频的 revision 一旦变动即违宪。

**ADJ-006 检索的语义防火墙**。我写的检索约束全是召回率与延迟，**没有一条约束检索结果「可以拿来做什么」**：

> world.co_search 的法定输出 = **候选切片指针 + hit_reasons + coverage**。
> 共现交集仅完成「关联候选区定位」，**不构成任何 Claim 的真值推导**。
> **fusion 权重提高的是「候选质量」，不是「真值概率」。融合得分只用于把最相关的 slice 排在前面，不进入 confidence 赋值路径。**

**这直接命中我 M1-012 规约里的一个潜在语义漏洞**：`CoSearchHit.density_score`（共现密度：命中词数 × 邻近度 × 权重）。漏掉 ADJ-006，检索得分就会伪装成认知置信度 —— **AI 会「因为找到了很多相关记录」而相信一个并未被证据核验的结论。** 已编码 `fusion_score_must_not_enter_confidence_path = true`，并加了一条 0 容忍 blocker 不变量 `retrieval.fusion_score_leaked_into_confidence`。

ADJ-006 还要求把「共振密集区」在实现语言中重命名为「**候选密集区**」。**名字不是小事 —— 它会决定工程师敢用它做什么。**

**ADJ-009 声纹簇生命周期**。我 v1.0.0 只有一句「第三方声纹默认不持久化」，**完全没有生命周期** —— 而「声纹退休后历史引用断链」正是 ADJ-009 要堵的风险。ADJ 给出：

- `ACTIVE → RETIRED → TOMBSTONE`，**退休不等于删除**，历史引用保持解析有效；
- 再识别**禁止直接复生旧簇**，需连续性探针（时间连续性 / 设备场景连续性 / 明确确认，三者之一），否则新建簇；
- **身份归 PersonEntity，簇只是证据载体** —— 这样簇可以退休、可以新建，而「这个人是谁」的认知不断裂；
- 特征向量与来源归因**永存**，原始波形**可吊销**（删掉波形但保留「从何时来自哪里进入」，归因能力就还在）。

没有连续性探针的后果很具体：**一个声音相似的陌生人会被合并进旧簇，于是「老张说过的话」里混进了别人说的话** —— 对 §36「文字相同不等于实体相同」在声学域的直接违反。

### 2.6 ADJ-002 —— 我把「出厂默认」写成了「铁律」，还漏了人格层承诺

| | 我 v1.0.0 | ADJ-002 |
|---|---|---|
| 3~5 小时 | `interval_hours: {min:3, max:5}`（**等于铁律**） | 作废为**研发基线出厂默认**，归入二级治理参数（ADJ-008） |
| 心跳 Wake 的性质 | 未定义 | **候选唤醒而非承诺出声**；Step-0 方便度判有最终否决权 |
| 绝对下限 | 只有 `safety_trigger_never_suppressed` | 安全值守通道 **+ 已登记的自承诺类任务（药物、复检）** |

**铁律那一处正好撞上 §80之3 的反馈自适应** —— 铁律无法被学习调整，而宪法要求它必须能。

**漏掉自承诺任务那一处，暴露了我的思路局限**：我按「安全项」的思路在想，所以只写了安全。但**用户自己登记的吃药与复检提醒不是安全项，它是人格层承诺（§19之二/§32）**：AI 答应过的事，不该因为 AI 学到「他最近嫌我烦」就被静默下调。这是承诺与节奏学习之间的优先级裁定，不查人格层条款就想不到。

ADJ-002 §3 还有一条我完全没想到的禁令：**「禁止以『维持心跳』为由绕过反馈冷却」**。它堵住一个自证循环 —— AI 学到用户嫌它烦 → 但为了「维持关系节律」继续出声 → 用户更烦。**每一次绕过在日志里看起来都是合理的。**

验收锚 `固定节奏炸弹数 = 0`（7 天平稳数据下）也是我没有的。**「为了维持关系而打扰关系」是这个产品最讽刺的失败模式。**

---

## 3. 两处方向一致，我把 ADJ 的要求编码为可校验字段

### 3.1 ADJ-008 —— 一次意外但有力的相互印证

**ADJ-008(b)**：触发阈值「在 **`governance/thresholds/`** 中以参数文件形态冻结出厂基线」。

**我的 v1.0.0**：`governance/runtime_policy.json` —— 参数文件形态，冻结在 `governance/`。

**两条完全独立的路径走到了同一个设计模式。** 这是对「法律层」概念最强的一次外部印证：ADJ-008 是在做条款裁决时推出这个需求的，我是在做工程推导时推出这个需求的，两者没有互相看过。

我把 ADJ-008 的四项要求编码为字段，其中 (d) 最值得单列：

> **人身安全参数（摔倒/撞击等人身硬信号）不进入学习型下调通道，只允许经治理流程向更严修改。**

这是一个**方向单调性约束**，可自动校验。它防的失败模式很特殊：**安全阈值的磨钝是渐进的、每一步都「有依据」的，因此快照式测试永远抓不到它** —— 每一天的阈值看起来都合理，只有把 30 天的方向连起来才看得见她一直在变松。**只有方向约束能抓住它。**

`threshold_change_log` 要求「可回放 **且** 可回滚」，这是两个独立要求：**只可回放不可回滚，AI 就能一路把阈值学坏而无人能撤销。**

### 3.2 ADJ-003 —— 机械触发只产出二值信号

> 第 79 条 8 类=**机械检查项**，其产出是「是否值得 Step-0」的二值信号，
> **不直接产生语义结论（第 77 条）也不直接产生对外投放**。

若机械触发能直接产生语义结论，§77「触发器不负责理解人生」就被绕过了 —— **一个心率阈值越线会直接变成「他今天压力很大」这样的认知。** 已编码为 `mechanical_trigger_output_is_binary_signal_only = true`。

ADJ-003 还注册了三个 WakeSource 扩展名。我把自拟的 `LONG_STABLE_HEARTBEAT` 改为法定名 **`RELATIONSHIP_RHYTHM_CANDIDATE`** —— **一个政策层作者亲手制造的编号漂移源，必须自己先消除。**

---

## 4. 一处编号对撞，已上交一级治理变更

见 §0。摘要：`ADJ-010` 引用的「R4 重构方案 §2.1」是 PLAN-R4（C01~C16，已登记、已落库到追溯矩阵），而我这份 R4 是 C01~C18（未登记）。C15/C16 双定义，C17/C18 是 PLAN-R4 缺失的真实职能。

按 `ADJ-010 §3`（模块新增/合并/改义必须走一级治理变更；映射者哈希不一致即 CI 红），**政策层无权自裁**。已登记冲突、给出合并提案（我的四个职能改编号 C17~C20，让未落库的一方让位；我的 M0.1/CP1 并入 ADJ 的 M0'/M1.X），并把自己的全部相关编号标记为 `PROPOSAL_NOT_BASELINE`。

**待治理平面裁决。**

---

## 5. 对齐过程中，判决门抓到的我自己的错

这一节是本次对齐最有价值的副产品。`tests/policy/` 在 v1.1.0 迁移过程中一共判红 **8 次**，每一次都是真问题：

| # | 判红内容 | 性质 |
|---|---|---|
| 1 | `verdict ADJ_SHARPER_ADOPTED 计数不符：声明 5，实际 6` | 我的自评计数是错的（实际 3/6/2/1，我写 3/5/3/1） |
| 2 | `adjudication_alignment` 域未引用任何宪法条款 | 我给自己的对齐段忘了找法源（应为 §115 三级修宪） |
| 3 | `ADJ-010 → id_namespace_registry.namespaces.C01..C16` 字段不存在 | 路径解析器不支持含点的键名，**存在性检查在合法字段上误报** |
| 4 | `以下裁决只有描述性字段，没有任何可判红的执法点: ADJ-003/008/010/011/012` | **真缺口** —— 5 条裁决只被"提及"而未被"执法"，已补 4 条硬门 |
| 5 | 11 个判决断言改名 → 24 个变异 case 的目标失效 | **harness 假绿通道**：`getattr` 抛 AttributeError 被 `except` 当成"已抓住违宪" |
| 6 | `token_budget.over_quota_policy.safety` 是新增键 | 第二类假绿：变异一个已不存在的字段，政策实质未变，判决门"通过" |
| 7 | `safety` 被列为 never_degradable 却不在 over_quota_policy 中 | **`.get(sub) != "halt"` 的危害**：缺失的键与合规的键返回同一个结果，一条守护安全的断言实际什么都没守 |
| 8 | `vad_tail_silence` 标为 inside_legal_slo 后仍"达标"（800ms < 1500ms） | **纯算术断言抓不到边界声明错误** —— 后果是团队去优化一个不该计入法定预算的阶段 |

第 4、5、6、7、8 条不是笔误，是**结构性的假绿通道**。逐条说明它们的处置：

### 5.1 「有裁决、无执法点」—— 最重要的元断言

第 4 条判红暴露的是：**一份政策可以逐条引用 12 项裁决、写得头头是道，而没有任何一条能在 CI 里判红 —— 那它就还是文学。**

**D1 的诊断（宪法是文学不是法律）会在政策层原样复发。** 所以 v1.1.0 新增了一条元断言：

```python
def test_every_adjudication_has_at_least_one_enforcing_invariant_or_gate() -> None:
    """每条 ADJ 都必须至少有一个可判红的执法点
    （一条退化不变量 或 一条工程硬门）。"""
```

它扫描 `degradation_invariants[*].adjudication_ref` 与 `engineering_hard_gates.added_by_adjudication_set[*].authority`，要求 ADJ-001~012 **每一条都至少命中一个**。第一次运行就抓到 5 条裁决只有描述性字段。已补齐 4 条硬门（`mechanical_trigger_produced_semantic_conclusion` / `module_or_milestone_mapping_hash_mismatch` / `stable_key_registry_drift` / `a_p_namespace_ambiguity`），全部取自 ADJ 各自的验收锚原文。

**这条元断言检查的是「裁决集是否真的被执法」，而不只是「裁决集是否被提及」。**

### 5.2 两类 harness 假绿通道

第 5、6 条是同一个病：**回归 harness 自身会产生假绿，而且重构越勤快、绿灯越多。**

- **第一类（改名）**：判决门断言改名后，变异 case 的 `getattr(gate, name)` 抛 `AttributeError`，被 `except Exception` 分支当成「已抓住违宪」。24 个 case 集体变成装饰品。
  → 处置：`_assert_caught` 先校验目标断言真实存在，否则**大声失败**并报「harness 假绿」。由 `CASE-00c` 守卫这条守卫。

- **第二类（幽灵字段）**：变异一个已不存在的字段，只是新增一个判决门从不读取的键，政策实质未变，判决门「通过」，harness 报不出任何异常。**这类假绿比改名更隐蔽：它看起来像守卫很稳。**
  → 处置：`_assert_caught` 比对变异前后的全部键路径，要求**至少改动一个既有字段的值，或删除一个既有键**；纯新增键的 case 必须显式声明 `allow_additive=True`（其存在意义就是「新增这个键本身即违宪」，如 CASE-55 把歧义布尔字段放回来）。由 `CASE-00d` 守卫这条守卫。

**给守卫写守卫，是这个项目已经证明有效的品味**（`tests/architecture/test_scanner_regression.py` 给扫描器本身写了 12 个 case）。我只是把它推进了一层：**这次连"守卫的守卫"都被证明有假绿通道，所以 CASE-00c / CASE-00d 是必须的，不是装饰。**

### 5.3 `.get()` 默认值在守宪测试里的典型危害

第 7 条值得单独记一笔，因为它是一个通用的工程教训。

```python
# v1.0.0 的断言
for sub in tb["never_degradable"]:
    assert tb["over_quota_policy"].get(sub) != "halt"
```

`never_degradable = ["safety", "conversation.fast"]`，但 `over_quota_policy` 里**根本没有 `safety` 这个键**（安全不是被预算的子系统）。`.get("safety")` 返回 `None`，`None != "halt"` 为真 —— **断言通过，而它什么都没检查。**

**缺失的键与合规的键返回了同一个结果。** 一条看起来在守护安全的断言，实际守护的是空气。

v1.1.0 的修法不是给 `.get()` 加默认值，而是**把语义分清楚**：

```python
for sub in tb["never_degradable"]:                     # 被预算的：必须已登记且不为 halt
    assert sub in quota, f"{sub} 被列为 never_degradable，却不在 over_quota_policy 中"
    assert quota[sub] != "halt"

assert tb["non_budgeted_never_degradable"] == ["safety"]  # 不被预算的：在预算体系之外
assert "safety" not in tb["subsystems"]                   # 一旦它有配额，就存在"配额用完"的语义
assert "safety_watch" in POLICY["step0_safety_gate"]["hard_block_still_allows"]
```

**安全不是一个被预算的子系统，它在预算体系之外** —— 由 `step0_safety_gate.hard_block_still_allows`（后台静默巡检 + 安全值守）保护。一旦它有配额，就存在「配额用完」这个状态，而**安全通道不允许有「用完」这个状态**。

**教训**：在守宪测试里，`.get()` 的默认值是一种静默失效。P3 原则（静默失效一律非法）不只适用于产品代码，也适用于测试代码 —— **尤其是测试代码。**

---

## 6. 交付清单与实测结果

| 产物 | v1.0.0 | **v1.1.0** | 变化 |
|---|---|---|---|
| `governance/runtime_policy.json` | 396 行 / 20 域 | **~870 行 / 27 域** | 新增 `step0_safety_gate` / `retrospective_annotation` / `speaker_cluster_lifecycle` / `threshold_governance` / `retrieval_slo.semantic_firewall` / `adjudication_alignment`；重写 `retention_policy` / `mental_startup` / `heartbeat` / `latency_slo` / `style_constraints` |
| `tests/policy/test_runtime_policy.py` | 54 条断言 | **126 条断言** | 全部带 `constitution_stable_keys`；新增跨文件稳定键完整性检查、ADJ 执法点元断言、延迟物理边界断言 |
| `tests/policy/test_policy_gate_regression.py` | 113 个变异 case | **227 个变异 case** | 新增 CASE-112~201 覆盖 ADJ 新增政策面；CASE-202~222 覆盖 THRESH-BASE 跨工件一致性（见 §8）；新增 CASE-00c/00d 守卫 harness 自身 |
| 退化不变量 | 15 条 | **25 条** | 新增 10 条 ADJ 验收锚（round_trips / byte_hash_drift / reference_lock / tombstone_hit / cluster_resurrect / false_playback / safety_truncated / fusion_leak / rhythm_bomb / perceived_latency） |
| 工程硬门 | 6 条 | **6 + 10 条** | §16 六条原样继承；ADJ 追加十条，分区存放（变更门槛不同） |
| 退化注入 case | 6 个 | **12 个** | 覆盖全部新增退化类别 |

**实测（本机 Python 3.11，纯标准库，无 pytest / pydantic / pyyaml）**：

```
$ python3 tests/policy/test_runtime_policy.py
126/126 passed, 0 failed
policy:        governance/runtime_policy.json
trace matrix:  governance/traceability_matrix.csv (120 stable keys)

$ python3 tests/policy/test_policy_gate_regression.py
227/227 caught, 0 missed
(missed = 政策门在该变异下仍然通过 = 守卫失效)
```

**稳定键跨文件完整性**：政策层引用的全部 `constitution_stable_keys` 100% 命中 `traceability_matrix.csv` 的 120 个已注册键，悬空引用 0。

---

## 7. 一句话总结

**12 条裁决，没有一条是「我对 ADJ 错」。**

这不是客套。ADJ 裁决集是在完整读过 v3.0 全文、做了条款级冲突分析之后签发的；我的 v1.0.0 是在断层审计的基础上做的工程推导。**在「条款语义的精确边界」这件事上，前者的信息位置本来就优于后者** —— 它看得见 §78/§80之2/§84之2 三个「第一」的字面互斥，而我是从实现可行性倒推的。

我的优势在别处，而且这次对齐恰好证明了它的价值：

- **可执行的判决门**：ADJ 的验收锚（`first_response_round_trips ≤ 1`、`reference_lock_violation=0`、`observation_byte_hash_drift=0`、`false_playback_without_epoch=0`）全部是 0/1 可判定的，**天生适合变成 CI 红灯**。裁决集提供了判据，政策层提供了执法。
- **实测数字**：2,554,000 tok/月的零基闭合、195~550ms 的法定边界内串行和、L 档 0.24GB/年 —— ADJ 不产出这些，它裁决条款。
- **给判决门写回归测试**：这次对齐过程中判决门判红 8 次，抓到的第一个违宪者始终是我自己。**ADJ-001 那条最高级裁决之所以能落地成 `first_response_round_trips_max = 1`，是因为有一个东西在盯着它。**

**两者合流才是完整的三层结构**：裁决集是宪法 v3.0.1 的条文，政策层是它的执法细则，判决门是它的法庭。缺任何一层，另外两层都会退化回文学。

**唯一的遗留分歧（§0 的 C15/C16 对撞）已上交一级治理变更，政策层无权自裁，也不应自裁。**

---

## 8. 第二轮：THRESH-BASE 落地后，我在一小时内又漂移了两次

> 本节写在 §7 之后，因为它是 §7 写完当天（2026-09-16）发生的事。
> 保留 §7 原文不改 —— 一个「结论写完就被现实打脸」的记录，比一个事后修饰过的结论有价值。

§7 我写「政策层是裁决集的执法细则」。几小时后，另一条工作线把 **M0-031 落地**：
`governance/thresholds/baseline_v1.json` 真的出现了，`registry.md` 里 G0 已签发，
PLAN-R4 / ADJ-v3.0.1 / TRACE-MATRIX 全部转 CURRENT，而**我的两份文件也被登记了** ——
`POLICY-RUNTIME`（v1.0.0，钉了哈希）与 `PLAN-R4-B`。

于是发生了三件事，每一件都值得记下来。

### 8.1 我在同一轮里，第二次犯了 ADJ-011 明令禁止的错

ADJ-011 的判词是「一物两名即漂移源」。我在 §1.2 里刚刚承认自己的裸条号引用不合规、
刚刚给全部 25 个域补上 `constitution_stable_keys`、刚刚写下跨文件完整性断言 ——
然后转头做了这两件事：

| # | 我写的 | 已落地基线写的 | 性质 |
|---|---|---|---|
| 1 | `change_log_fields: [previous_value, new_value, evidence_input_window, learning_hash]` | `change_protocol.required_fields: [param_id, prev_value, next_value, input_window, learner_hash, rationale, applied_at, reversible]` | **四个同义异名 + 四个漏项** |
| 2 | `learn_channel_enum: [STRICTER_ONLY, NONE, BIDIRECTIONAL]` | 实际词表 `{STRICTER_ONLY, DUAL, NONE}` | **我把 DUAL 写成了 BIDIRECTIONAL** |

第一次是「我没读过那份文件」，可以理解。第二次不是 —— 第二次发生在我**已经因为第一次
而写下 `single_source_of_truth` 字段之后**。也就是说：我一边声明「政策层不得重定义基线拥有的契约」，
一边在同一个 JSON 对象里重新枚举了基线拥有的词表。

**所以教训不是「下次仔细点」，而是结构性的**：

> **政策层不得枚举另一个工件拥有的词表。**
> 枚举一旦落到两个文件里就必然漂移，而漂移方向总是「两边都看起来合理」——
> `BIDIRECTIONAL` 和 `DUAL` 谁都不像错的，人工评审抓不到，只有跨文件断言抓得到。

已做的处置：
- 删除本地 `learn_channel_enum`，改为声明 `learn_channel_vocabulary_owner`，词表由判决门从基线派生；
- `change_log_fields` 改为逐字引用基线的 `required_fields`，并加 `change_log_field_names_copied_from` 注明来源；
- `safety_parameter_examples` 从我自造的 `fall_detection` 改为基线里真实存在的 `thr.vital.fall_impact_g` 等 ——
  **自造名字的示例无法被校验**：判决门拿它去基线里找，找不到，而「找不到」与「找错」在 `.get()` 语义下是同一个结果（§5 已踩过这个坑）；
- 新增判决门断言 `test_policy_does_not_redefine_the_baseline_change_log_field_names` 与
  `test_policy_does_not_hardcode_a_vocabulary_the_baseline_owns`；
- **把自己犯过的两次错固化成回归用例 CASE-206 与 CASE-208**。记忆会失效，测试不会。

其中漏掉 `reversible` 最不该。ADJ-008 要求「可回滚」，基线把它实现为
「每条日志保留 `prev_value` 使回滚是常数时间操作」—— 这是一个可机器校验的性质；
而我只写了一句 `change_log_must_be_rollbackable: true` 的文学承诺。
**同一个要求，一边是实现约束，一边是态度表态，而我选了后者。**

### 8.2 规则②③组合出一个死结：注册表原本不允许任何已登记文件演进

`hash_registry.py --check` 判红了，两行漂移 —— 是我自己那两份文件。
红得完全正确：我改了已登记的文件，没有追加版本行。

但当我按规则②去追加版本行时，撞上了死结：

```
规则②  已入库的行禁止改写（追加新版本行代替）
规则③  任何已登记文件的实际哈希与表内不符即红检
check() 把【每一行】的哈希都拿去和【当前】文件内容比对
```

三条合起来：**一份已登记文件只要合法演进，旧版本行就永久漂移、CI 永红；
而改写旧行哈希格又被规则②明令禁止。规则②给出的唯一合法出路，
恰好是规则③判红的唯一形态。** 注册表里不存在任何一条路径允许一份已登记文件演进。

这不是实现瑕疵，是规则的组合缺陷。而且它**只会在第一次有人认真修改一份已登记文件时暴露**
—— 也就是恰好在治理开始起作用的那一刻。在此之前它一直绿，因为它从未被使用过。

处置（窄口径、防滥用、不改写任何哈希格）：状态格显式含机读标记 `HISTORICAL-ROW` 的行，
视为「同一文件已被取代的历史版本」，`check()` 不再拿它与当前文件比对（比对本就无意义），但：

1. **历史哈希逐字留在表内**（ADJ-004 版本链永存；豁免比对 ≠ 删除历史）；
2. **同一路径必须另有一行处于 CURRENT/REGISTERED 作为活继任者**，否则该标记立即判红 ——
   不然它就是一个后门：给任何文件的状态格加上它，该文件就永久退出哈希校验，而表看起来仍然全绿。
   **一个能被滥用的豁免机制，比没有豁免更危险。**
3. 继任者判定按**路径**而非 spec_id（否则「把行改指向别的文件」可以蒙混过关）；
4. `--fill` 拒绝向 `HISTORICAL-ROW` 的哈希格写入任何内容，即使它是占位形态。

已按此走完真实流程：`POLICY-RUNTIME` 1.0.0 与 `PLAN-R4-B` R4 两行标为 SUPERSEDED · HISTORICAL-ROW
（哈希格一字未动），追加 1.1.0 与 R4.1 两条活行，`--fill` 补登，`--check` 18 行全绿。
并新增 `tests/policy/test_hash_registry_versioning.py`（14 条）用合成注册表逐条钉死上述行为 ——
**它守的不是哈希算法（那 trivially 正确），而是豁免权的边界。**

同时把规则③复刻进政策层判决门（`test_registered_documents_do_not_drift_from_their_pinned_hashes`），
理由：这次是治理作业的 `--check` 抓到我，但开发者平时跑的是 `tests/policy/`。
**只在 CI 的治理步骤里可见的纪律，等于对日常开发不可见。**

**还踩中一个作业顺序陷阱**：我先跑了 `--fill` 补登 1.1.0 行，然后又去改政策层内容，
于是该行哈希漂移；再跑 `--fill` 时它按规则②**拒绝改写已钉住的哈希格** —— 完全正确的行为，
但把我卡在「改不动、又不能不绿」的状态里。处置：这两行尚未提交，未入 git 的行不构成历史，
恢复成占位再补登即可（**若已提交，就只能再追加一个版本行，那是规则②要的代价，不该绕过**）。
已把「`--fill` 必须是提交前最后一步」写进工具文档头部。

写这条断言时我自己先犯了一个错：用 `startswith(f"| {spec} |")` 取第一个匹配行，
结果把历史行的哈希拿去和当前文件比，制造了一条永远无法消除的**假红**。
同一 spec_id 现在合法地有多行，必须逐行比对自己的哈希格。已修正，并加
`test_rows_sharing_a_spec_id_are_checked_against_their_own_hash_cell` 钉住。

### 8.3 顺手挖出 `--fill` 的一个可审计性缺陷

调试 8.2 时发现：`fill()` 用 strip 过的 cells 重新拼行
（`"|" + "|".join(row.cells) + "|"`），于是**每一次补登都会把该行的空格排版压扁**：

```
补登前： | POLICY-RUNTIME | `governance/runtime_policy.json` | 1.1.0 | （待回填） | **CURRENT** | ... |
补登后： |POLICY-RUNTIME|`governance/runtime_policy.json`|1.1.0|`f0c7ba99…`|**CURRENT**|...|
```

真实注册表里已经有两行被压扁了（第 25、26 行），与其余 16 行排版不一致。

这**不是美观问题，是可审计性问题**：治理表是靠 diff 评审的。一次只改哈希格的补登，
如果 diff 显示整行被重写，评审者就无法一眼看出动了哪一格 ——
而「看不出动了哪一格」正是篡改最想要的属性。规则②之所以禁止改写已入库的行，
保护的正是这种可读性；一个把整行重排的 `--fill`，在效果上削弱了它本该保护的东西。

已改为保留每格原有的前导/尾随空白做原位替换，被压扁的两行已修复，
并加 `test_fill_preserves_row_padding_so_the_diff_stays_auditable` 钉住（逐格比对，只允许第 4 格变化）。

### 8.4 变异测试再次证明它的价值不在「确认守卫有效」

这批 21 个新 case（CASE-202~222）里，有两条是**先写变异、发现抓不到、再回头改判决门**的：

**CASE-217：把宪法承认的心跳默认区间从 `[3,5]` 放宽到 `[1,24]`。**
我原以为 `test_heartbeat_factory_default_lies_inside_the_constitutional_default_range` 会抓住它。
实测：抓不到。因为 10800s 落在 `[1,24]` 内，基线值也仍然相等，五条断言全过。
**放宽法律区间，在纯算术断言下是隐形的。**
修法与 §5 那次「VAD 边界声明错误」同源：区间本身来自 ADJ-002（承认 §80之1 的 3~5 小时），
属法律内容而非政策参数，必须在判决门里硬编码钉死 —— 与本文件对 `ALL_ADJ` 的处理同理：
**让「放宽法律」必须同时改两个文件才能通过。**

**CASE-215：把 `safety_parameter_examples` 整体替换成我自造过的 `["fall_detection","impact_detection"]`。**
实测：抓不到。因为我的守卫写的是 `if ex.startswith("thr."): assert ex in real_ids` ——
一个**只对预期形状开火**的守卫。变异成不带该前缀的名字，守卫一次都不执行。

> **守卫只对它预期的形状生效，就等于对攻击者选择的形状无效。**

已改为要求全部举例都是真实 `param_id`，去掉形状豁免。这与 §5 记录的
「`.get()` 默认值静默通过」「纯算术抓不到边界声明错误」是同一族缺陷：
**断言写了，但它的触发条件比它声称保护的条件窄。**

### 8.5 一处我不修的缺陷（附理由）

`baseline_v1.json` 第 80 行，`thr.motion.inactivity_alert_hours` 的 evidence 写作
「**ADV**-008 允许双向学习的生活型参数」—— 应为 **ADJ**-008。一个字母的引用错误。

我**没有**改它，理由有三条，且第三条最重要：

1. 该文件已作为 THRESH-BASE 登记哈希、状态 REGISTERED，属已入库规范；改它会造成哈希漂移，需走版本追加流程；
2. 它不是我这条工作线的产物，改别人的规范文件应当由该文件的责任线执行；
3. **ADJ-011 §2 的判词正是「条号本身即为不能再承载语义的印刷物」** —— 一个写错的条号，
   恰好是这条判词最好的例证。把它就地修掉，等于销毁一个证据。

已在政策层的 `$safety_param_note` 与本节记录在案，交由 THRESH-BASE 责任线在下次版本追加时一并处理。

### 8.6 第二轮交付与实测

| 产物 | 变化 |
|---|---|
| `governance/runtime_policy.json` | `threshold_governance` 重写为**消费方**身份：`single_source_of_truth` / `policy_assertions_on_baseline`（9 条，每条点名自己的执法断言）/ 字段名逐字引用基线 / 删除本地枚举 |
| `tests/policy/test_runtime_policy.py` | 118 → **126** 条断言：新增 §19 跨工件一致性 8 条（基线存在性、哈希登记、不得重定义字段名、不得本地枚举词表、逐参数 learn_channel、安全通道方向、心跳默认区间、规则③复刻） |
| `tests/policy/test_policy_gate_regression.py` | 206 → **227** 个变异 case：CASE-202~222 |
| `tests/policy/test_hash_registry_versioning.py` | **新增，14 条**：规则②③死结的处置、防滥用不变量、--fill 纪律、真实注册表集成校验 |
| `tools/governance/hash_registry.py` | 补 `HISTORICAL-ROW` 机制（含继任者强制校验）+ 修 `fill()` 排版压扁缺陷 + 文档记载两处缺陷的成因与边界 |
| `governance/normative_versions/registry.md` | POLICY-RUNTIME 1.0.0 / PLAN-R4-B R4 转 SUPERSEDED · HISTORICAL-ROW（哈希格未动）；追加 1.1.0 / R4.1 活行并补登；修复被压扁的两行排版 |

```
$ python3 tools/governance/hash_registry.py --check
registry hash check green (18 rows verified, 0 placeholders)

$ python3 tests/policy/test_runtime_policy.py
126/126 passed, 0 failed

$ python3 tests/policy/test_policy_gate_regression.py
227/227 caught, 0 missed

$ python3 tests/policy/test_hash_registry_versioning.py
14/14 passed, 0 failed
```

另一条工作线的 `test_thresholds_baseline.py` 与 `test_traceability_matrix.py` 同步复跑，未受影响。

### 8.7 这一轮的判词

§7 我说「抓到的第一个违宪者始终是我自己」。第二轮把这个说法推进了一步：

**我不只是违宪者，我还是那个一边写反漂移断言、一边漂移的人。**
`single_source_of_truth` 这个字段是我在发现第一次漂移后亲手加进去的，
然后我在同一个对象里造了第二个漂移。

这说明**自律字段没有约束力** —— 写下「我不得重定义他人契约」这句话，
对阻止我重定义他人契约毫无作用。真正起作用的只有两样东西：
一条会判红的跨文件断言，和一个把我犯过的错固化下来的变异用例。

这也是政策层与文学的区别，第三次被证实。

---

## 9. 第三轮：两条工作线的 v1.1.0 对撞，以及规则②③死结的两次独立发现

> 本节写在 §8 之后。触发原因是推送失败：令牌过期期间，另一条工作线推了
> `ec69ade`（M1-019 Retention & Tombstone Worker）与 `0e391bf`（M1-023 Alias Dictionary），
> 其中**也重写了 `governance/runtime_policy.json`（+719/-150），也自称 v1.1.0**。

### 9.1 最有价值的一条证据：同一个死结被两条线独立撞上

§8.2 我记录了规则②③的组合死结，并提出了**标记语义**解法
（状态格写 `HISTORICAL-ROW` + 强制要求同路径存在活继任者，否则判红）。

rebase 时发现：**另一条工作线在同一天、互不知情的情况下撞上了同一个死结，
并独立提出了位置语义解法**（追加序即时间序，同一组只有表内最后一行参与比对，
更早的行 archived、哈希封存）。

两个人从不同方向走到同一处，说明这不是我个人的疏忽，而是**规则本身的结构性缺陷**。
这与我上一轮对 ADJ-008(b) 的判断同构（「两条独立路径走到同一处，是对『法律层』概念
最强的外部印证」）—— 只不过这次被印证的是一个 bug。

**采纳位置语义，舍弃我自己的标记语义**，理由三条：

1. 不需要人工填写标记 —— 少一个人为字段就少一种填错的方式；
2. **不存在「豁免权」这个概念，因而不需要防滥用不变量**：最后一行永远被校验，
   没有任何一行能靠自我声明退出比对。我的标记语义必须额外配一条
   「无活继任者即判红」才不留后门，那是机制自带缺陷的补丁；
3. 与规则①「一行 = 一份规范的一个版本」天然一致：版本顺序就是表格顺序。

标记语义唯一的优势是显式可读，该优势已由 archived 的报告文案补足。
**我的方案更啰嗦、需要更多守卫、并且把正确性寄托在人工填对一个标记上 —— 它更差。**

### 9.2 但位置语义有一条必须显式限定的边界，我实测把它踩出来了

采纳之后我立刻跑 `--check`，输出里有一行：

```
.. L14 [CONST-v3.0.1] archived（已被后续版本行取代，哈希封存）
```

**CONST-v3.0.1 是唯一生效宪基。** 它被位置语义判成「已被后续版本行取代」，
静默移出了哈希校验，而 archived 落在 `skipped` 桶里 —— **不判红**。

成因：复合行（路径列含 `+`）取 `+` 之后的路径段，于是
`CONST-v3.0.1`（宪法v3.0.md + 裁决集）与 `ADJ-v3.0.1`（裁决集）指向同一个文件。
按 path 归组，后者就把前者「取代」了。

当时该文件仍有 `ADJ-v3.0.1` 兜底，所以没有真正失守。但：

- **报告是错的** —— 宪基并未被任何东西取代，它和 ADJ 行是两个不同的规范工件；
- **它是脆弱的** —— 一旦 ADJ 行被删除或调序，宪基就无声失去哈希保护，
  而 CI 依然全绿；
- **`skipped` 不判红** —— 一行可以静默地掉出校验范围，这本身就是设计缺陷。

修法：**归组键是 `(spec_id, path)`，不是 `path`。** 规则① 的「一份规范」就是 spec_id；
不同 spec_id 即使指向同一文件，也是不同的规范工件，各自都必须被校验。
已修，并加两条回归（`test_two_specs_sharing_one_file_are_both_checked`、
`test_a_superseded_composite_spec_is_archived_while_the_other_stays_live`）
与一条真实注册表断言（`test_the_constitutional_baseline_is_actually_hash_verified`）——
**宪基若掉出校验，判决门必须判红。**

### 9.3 两种解法共有的一个后门：表尾追加一行占位

顺着 9.2 往下查，发现**我的标记语义和他们的位置语义都有同一个洞**：

某路径的**最后一行**若是未补登的占位（无 64-hex），则该文件当前**不受任何哈希保护** ——
旧行已 archived/标历史而不再比对，新行占位被「待补登」跳过，`--check` 依然 exit 0。
也就是说：**在表格末尾追加一行占位，就能让任意已登记文件静默退出哈希校验。**

这不是理论风险。本轮我自己就制造了这个状态：追加 1.2.0 行写占位、
然后继续改政策层内容 —— 在那段时间里，政策层完全不受哈希保护，而 `--check` 报的是
「占位未登记」而非漂移。

修法：**末行占位判为漂移，不是跳过。** 初次登记时的占位是同一个提交内的瞬态，
CI 校验的是已提交状态；一个被提交下来的占位行，意味着有人提交了半截登记作业，
那就该红。已加 `test_trailing_placeholder_row_is_drift_not_skip` 与
`test_a_placeholder_in_a_non_final_row_does_not_mask_drift`。

### 9.4 合并本身：政策层的叶子键零重叠

先做结构比对，再决定怎么合，而不是直接读 diff：

| 域 | 数量 | 处置 |
|---|---|---|
| 只有我改过 | **17** | 取我的（ADJ-001~012 对齐成果） |
| 只有他们改过 | 1（`generated_at`） | 取他们的 |
| **两边都改过** | **2** | `policy_version`（版本号对撞）+ `retention_policy`（唯一需要真合并的域） |
| 我新增的域 | 7 | 他们完全没有，无冲突 |

`retention_policy` 内部逐叶子键比对：**重叠 0 个**。原因是两边写的是同一件事的不同半面 ——

- **我写的**：什么可以删、按什么条件删、删完留什么
  （永存清单 / 引用锁 / 两阶段 / 出土兼容 / 被遗忘权）；
- **他们写的**：多久之后删
  （`ttl_days_by_retention_class` / `speaker_cluster_retire_days` / `stage1_quarantine_days`）。

所以是干净的并集。**但并集不等于合并完成** —— 有两处需要交叉接线：

**(1) 我的声纹生命周期缺一个数值，他们的 180 天正好补上。**
我在 ADJ-009 对齐时写了 `activity_assessed_by_recent_use_window: true`，
却**没给这个窗口任何数值**。对一个 fail-closed 系统，没有值的窗口等于没有窗口，
实现者只能自己猜。他们的 `speaker_cluster_retire_days.days = 180`（引 ADJ-009 半年退休）
就是这个值。已改为**只放引用、不复制数值**：复制就会有两个 180，
而两个 180 迟早变成 180 和 210。这是 `single_source_of_truth` 纪律的第二次实践
（第一次是 §8.1 的 change_log 字段名）。

**(2) 他们有一个字段是纯粹的重复，而且没人读。**
`stage1_quarantine_days` 与同域 `quarantine_cooldown_days` 语义相同、数值相同（都是 30），
而**全仓库没有任何代码或测试读取它** —— Worker 读的是 `quarantine_cooldown_days`。
按 ADJ-011，这就是「一物两名即漂移源」：两个字段各自演进之后，
「隔离冷却期到底几天」就没有唯一答案。

处置与 §8.5 的 `ADV-008` 笔误同理：**不擅自删除另一条工作线已提交的字段**，
改为用判决门把两者钉死相等（`test_stage1_quarantine_alias_cannot_drift_from_its_canonical_field`），
并在字段内写 `$alias_warning` 说明它冗余、以及为什么还没删。
删除动作留给下一次治理作业。**把一个漂移源变成一个受约束的不变量，
比删掉它更稳妥，也不需要跨工作线的裁决权。**

### 9.5 政策层的失效模式变了：它现在是运行时代码的依赖

M1-019 之后，`src/aios_core/services/retention_worker.py` 的
`RetentionPolicy.from_runtime_policy()` 会**真的读** `governance/runtime_policy.json`，
任何键缺失直接 `raise AssertionError`（fail-closed）。

这改变了政策层的性质：**删掉一个键不再只是「法律少了一条」，而是 GC Worker 起不来。**
政策层从规范文档变成了运行时契约，守卫等级必须跟着升。

已加 `test_policy_satisfies_the_retention_worker_loader_contract`：
逐行复刻该 loader 的判定逻辑（不 import 它，因为那需要 pydantic，本环境没有），
使政策门能在零运行时依赖下守住这个契约。其中最有价值的一条是反向的：

```python
assert ttl_raw.get("revocation_free") is None   # 永存类不得有 TTL 数值
```

因为 loader 用 `isinstance(v, int)` 过滤表项 —— 如果有人给 `revocation_free` 写上 `365`，
loader **不会报错，会把它当成真 TTL 静默读进去**，于是 ADJ-004 吊销权外的永存类
（对象版本链 / 被引用观测 / DeletionLog）就有了死期。
`null` 才是「永存」的机器表达；写成整数看起来只是「保留一年」，实际是把永存类降级成了可吊销类。
已加 CASE-225 钉死。

### 9.6 版本号对撞的处置：升 1.2.0，任何一方都不「赢得」1.1.0

两条线各自产出一个「1.1.0」，内容不同、版本号相同。处置：

- 已提交的那条（`1bcf22f1…`，retention_ttl 入法）按规则②**原样封存**，状态改 SUPERSEDED；
- 未提交的那条（我的 ADJ 对齐）**不占版本号** —— 它从未进入 git 远端，不构成已发布历史，
  其内容已并入 1.2.0，过程记录在 git 与本报告；
- 合并后的工件升为 **1.2.0**，使任何一个版本号都不同时指代两份不同内容。

注册表已加多版本行阅读规则说明，并记明这次对撞的处置依据。

**我在政策层里写了 `id_namespace_registry` 专门防止编号漂移，然后在同一周里两次成为它的案例**：
第一次是设计书 C15/C16 模块编号对撞（§0），第二次就是这个版本号对撞。
上一轮我写下的教训是「命名冲突检测器不能只对着旧文档跑，它必须对着所有新文档跑，
包括它自己作者写的那一份」—— 这一轮证明它还得对着**版本号**跑，不只是模块号。

### 9.7 变异测试第四次证明：它的价值在于发现守卫无效

CASE-236 把 `policy_version` 从 `1.2.0` 改回 `1.1.0`，我原以为
`test_policy_is_versioned_and_bound_to_constitution` 会抓住。实测：**抓不到** ——
那条断言只检查「非空」。**一次版本号对撞在判决门下完全隐形。**

修法：新增 `test_policy_version_matches_its_live_registry_row`，钉三条子不变量 ——
活行版本号 == `policy_version`；POLICY-RUNTIME 版本号不得重复（一号一物）；
版本链必须单调递增（追加序即时间序，不得插入更旧版本）。并补 CASE-237 测反方向
（政策层自称 9.9.9 而注册表活行是 1.2.0）。

这是本项目第四次由「先写变异、发现抓不到、再回头改判决门」产生新断言。
前三次：CASE-217（放宽法律区间在纯算术下隐形）、CASE-215（守卫只对预期形状开火）、
上一轮的 VAD 边界声明错误。**每一次我以为某个断言「已经覆盖了」，
变异测试都有相当概率告诉我它没有。**

### 9.8 一次 rebase 事故：合并冲突解决会静默丢失补丁

解决 `hash_registry.py` 冲突时，我取他们的版本作基底、再用字符串替换重新贴上我的两处改动
（`fill()` 保排版、`Row.raw_cells`）。其中 `raw_cells` 的替换**静默失败了** ——
我的匹配模式假设 `hash_cell: str` 之后紧跟 `defstrip`，而他们的文件中间还夹着
`sha256_of()` 函数定义。

结果：`fill()` 里调用 `row.raw_cells`，而 `Row` 没有这个属性 ——
**`--fill` 一跑就 AttributeError**。`--check` 不用它，所以检查全绿，
我差点带着一个坏掉的 `--fill` 提交。

抓到它的是我在验证阶段随手跑的一句 `isinstance(m.Row.raw_cells, property)`。
教训值得写下来：**字符串替换式打补丁不会告诉你它没匹配上。**
冲突解决之后必须直接执行被改的函数，而不是只跑那些恰好不经过该路径的测试。
本轮 `--fill` 的实跑（以及它只改 2 行、不重排的输出）才是真正的验证。

### 9.9 第三轮交付与实测

| 产物 | 变化 |
|---|---|
| `governance/runtime_policy.json` | **v1.2.0**（两条线的 v1.1.0 合并）：并入 `ttl_days_by_retention_class` / `speaker_cluster_retire_days` / `stage1_quarantine_days`；声纹退休窗口改为引用而非复制；别名字段加 `$alias_warning` 并钉死相等；加 `$version_collision_note` |
| `tools/governance/hash_registry.py` | 采纳位置语义（他们的解法）+ 归组键修正为 `(spec_id, path)` + 末行占位判红 + 保留我的 `fill()` 排版修复 + 文档记载两条边界与作业顺序陷阱 |
| `governance/normative_versions/registry.md` | POLICY-RUNTIME 版本链 1.0.0 / 1.1.0 / **1.2.0**；PLAN-R4-B 版本链 R4 / **R4.1**；旧行状态改 SUPERSEDED（哈希格一字未动）；补多版本行阅读规则与对撞处置说明；修复被压扁的行排版 |
| `tests/policy/test_runtime_policy.py` | 126 → **130** 条断言：Worker 载入契约、别名不得漂移、窗口引用不得复制、版本号必须与注册表活行一致；漂移断言改为位置语义 |
| `tests/policy/test_hash_registry_versioning.py` | 14 → **16** 条，**整体重写**：从标记语义改为位置语义，新增 `(spec_id,path)` 归组、末行占位、宪基必须被校验、真实版本链完整性 |
| `tests/policy/test_policy_gate_regression.py` | 227 → **242** 个变异 case：CASE-223~237 |

```
$ python3 tools/governance/hash_registry.py --check
registry hash check green (18 rows verified, 0 placeholders)
  OK [CONST-v3.0.1] match a75a6db191bbb5c2…        ← 宪基重新回到校验范围内

$ python3 tests/policy/test_runtime_policy.py           130/130 passed, 0 failed
$ python3 tests/policy/test_policy_gate_regression.py   242/242 caught, 0 missed
$ python3 tests/policy/test_hash_registry_versioning.py  16/16 passed, 0 failed
$ python3 tests/policy/test_thresholds_baseline.py        8/8   （另一条工作线，复跑未受影响）
$ python3 tests/policy/test_traceability_matrix.py        4/4   （同上）
```

`tests/unit/test_retention_worker.py`（352 行）需要 pydantic + pytest，本环境无这两个依赖，
**未能实跑**。已用逐行复刻 loader 判定的方式在政策门里守住同一契约 ——
这不是等价替代：它守的是「政策层满足 loader」，守不到「loader 实现正确」。
后者需在装有依赖的环境跑一次，**这是一条已知的验证缺口，记录在案，不假装已覆盖**。

### 9.10 这一轮的判词

三轮下来，同一件事被证实了三次，每次的形态都不同：

| 轮次 | 我做了什么 | 现实怎么回答 |
|---|---|---|
| 第一轮 | 写了 20 域政策层，声明它是执法细则 | 12 条裁决，没有一条是「我对 ADJ 错」 |
| 第二轮 | 写下 `single_source_of_truth`，声明政策层不得重定义他人契约 | 同一个 JSON 对象里，我重新枚举了他人的词表 |
| 第三轮 | 提出标记语义解法，配了防滥用不变量，自认严谨 | 另一条线的位置语义更简单、且不需要防滥用不变量；而它落地后我先踩出了它的宪基豁免缺陷 |

第三轮的结论与前两轮不同，值得单独说：**这一次我不是唯一犯错的人，也不是唯一找对的人。**
死结是他们和我各自独立撞上的（说明它是真的），解法是他们的更好（说明我的不是最优），
而解法的缺陷是我先踩出来的（说明采纳别人的方案不等于不用负责）。

**合并的正确姿态不是「谁赢」，而是把两边的失效模式都钉进测试。**
本轮新增的 15 个变异 case 与 16 条版本化断言里，有一半在守的是**别人写的机制**，
另一半在守的是**我自己机制的失效**。这两半同等重要 ——
一套只守卫自己作者立场的测试，在第二个人接手的那天就会开始腐烂。
