# R4 政策层 × v3.0.1 裁决集（ADJ-001~012）对齐报告

> **日期**：2026-09-15
> **对齐双方**：
> - `governance/runtime_policy.json` v1.0.0（本会话产出，上位文档为 `AIOS_Core_任务规划与开发任务拆分重构方案_R4.md`）
> - `governance/v3.0.1_规范裁决集_ADJ-001-012.md`（并行会话产出，已按宪法第 115 条二级程序签发）
> **裁决规则**：裁决集明文「凡 v3.0 原文与本裁决集冲突处，以本裁决集为准」。政策层是裁决集的下位法，**凡冲突处改政策层，不改裁决集**。
> **产出**：`governance/runtime_policy.json` v1.1.0 + `tests/policy/`（118 条判决断言 / 206 个违宪变异回归）
> **结论摘要**：12 条裁决，**3 条我错了、6 条 ADJ 更锐利、2 条方向一致我做了编码、1 条编号对撞已上交**。没有一条是「我对 ADJ 错」。

---

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
| `governance/runtime_policy.json` | 396 行 / 20 域 | **~570 行 / 25 域** | 新增 `step0_safety_gate` / `retrospective_annotation` / `speaker_cluster_lifecycle` / `threshold_governance` / `retrieval_slo.semantic_firewall` / `adjudication_alignment`；重写 `retention_policy` / `mental_startup` / `heartbeat` / `latency_slo` / `style_constraints` |
| `tests/policy/test_runtime_policy.py` | 54 条断言 | **118 条断言** | 全部带 `constitution_stable_keys`；新增跨文件稳定键完整性检查、ADJ 执法点元断言、延迟物理边界断言 |
| `tests/policy/test_policy_gate_regression.py` | 113 个变异 case | **206 个变异 case** | 新增 CASE-112~201 覆盖 ADJ 新增政策面；新增 CASE-00c/00d 守卫 harness 自身 |
| 退化不变量 | 15 条 | **25 条** | 新增 10 条 ADJ 验收锚（round_trips / byte_hash_drift / reference_lock / tombstone_hit / cluster_resurrect / false_playback / safety_truncated / fusion_leak / rhythm_bomb / perceived_latency） |
| 工程硬门 | 6 条 | **6 + 10 条** | §16 六条原样继承；ADJ 追加十条，分区存放（变更门槛不同） |
| 退化注入 case | 6 个 | **12 个** | 覆盖全部新增退化类别 |

**实测（本机 Python 3.12，纯标准库，无 pytest / pydantic / pyyaml）**：

```
$ python3 tests/policy/test_runtime_policy.py
118/118 passed, 0 failed
policy:        governance/runtime_policy.json
trace matrix:  governance/traceability_matrix.csv (120 stable keys)

$ python3 tests/policy/test_policy_gate_regression.py
206/206 caught, 0 missed
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
