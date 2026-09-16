# AIOS Core as-built 审查报告：M5 批次（Agent-06~10 五张工单）

- **审查方**：独立首席架构师与技术总监（本会话，1 号位兼任审查）
- **日期**：2026-09-16
- **被审对象**：`origin/aios-2.0` 快照，提交 **`582e187`**（`docs(governance): 更新 TASK_PROGRESS_V3.md M5 里程碑与云端派单台账`）
- **被审文件**：6 个产品模块 + 4 个测试文件 + 1 份进度台账，逐文件 sha256 记录于工件 `subject_file_sha256`（11 项）
- **探针**：`reviews/architecture/evidence/verify_landed_m5_batch.py` **v1.2.0**（18 道门，stdlib + pydantic，fail-closed）
- **工件**：`verify_landed_m5_batch_result.json` / `.log`（字节哈希见 `SHA256SUMS` 与工件 `provenance.script_sha256`）
- **实测结论**：**18 道门 → PASS 1 / FAIL 17 / N/A 0，VERDICT = FAIL**

> **跨 ref 声明（重要）**：被审代码位于 `origin/aios-2.0`，该 ref 现为**单个孤儿提交**，与本审查方所在分支
> `arena/01a0a631-fantonghui` **无共同祖先**（`git merge-base` 退出码 1）。因此本报告的全部判定
> **只对 `582e187` 这个快照成立**，按 `subject_commit` + 逐文件哈希溯源；`run_gates.py` 为此新增
> `CROSS_REF_AUDIT_ARTIFACTS` 一类（只校验探针完整性，并强制"一旦被审源文件进入本树就必须重跑并改走工作树双向溯源"）。

---

## 一、总判定

| # | 工单 | 台账声称 | 探针实测 | 判定 |
|---|---|---|---|---|
| #6 | `M5-001` Agent-06 多维检索与最省 Token 经验 | **CLOSED (8/8 PASS)** | 4 门：**1 PASS / 3 FAIL** | ⚠️ **底座真实，核心交付物缺失** |
| #7 | `M5-002` Agent-07 维度生命周期与高阶提炼 | **CLOSED (3/3 PASS)** | 5 门：**0 PASS / 5 FAIL** | ❌ **三重门槛两重被削弱、一重类型不符** |
| #8 | `M5-003` Agent-08 人设镜面与像人姿态 | **CLOSED (7/7 PASS)** | 3 门：**0 PASS / 3 FAIL** | ❌ **羁绊未参与决策 + 场景关键词打表** |
| #9 | `M5-004` Agent-09 共生决策推演 | **CLOSED (3/3 PASS)** | 3 门：**0 PASS / 3 FAIL** | ❌ **答案表，不是推演器** |
| #10 | `M5-005` Agent-10 千人千面战训考场 | EXECUTING | 2 门：**0 PASS / 2 FAIL** | ❌ **交付物路径与 6/10 项能力缺失** |
| — | 台账一致性 | — | 1 门：**FAIL** | ❌ **4 条 CLOSED 声称与实测矛盾** |

**一句话结论**：主干全量套件 **1109 passed** 为真，台账"n/n PASS"字面也为真，但**绿灯不等于门禁成立**——
这些测试断言的是**场景常量**，不是工单写明的门槛语义。五张工单里只有"多维检索总线四大维度"这一项
（`WorldSearchIndex.search_by_{dimension,claim,entity,annotation}` + `co_search`）经得起实测。

---

## 二、方法与纪律

1. **不看测试是否通过，只按工单原文的断言逐条实测**。优先行为实验（构造输入→观察输出），
   结构性判据用 **AST**（不用正则——`V3G-014` 已实测正则会给出 0 命中的假阴性）。
2. **fail-closed**：被审模块缺失 ⇒ `exit=2` 并明说"本 checkout 不含 M5 代码"，绝不静默判过。
   已在审查方自己的分支上验证该行为（10 项被审文件缺失 ⇒ exit=2）。
3. **探针自证优先于结论**：本轮探针自身被发现两处 bug（见 §六），修正后才采信结果。

---

## 三、#6 Agent-06（`M5-001` 多维检索与最省 Token 经验）

**工单要求**：三大检索路径对比执行器（A 暴力扫描 / B 朴素关键词 / C 拓扑分级下钻）；
`OperationExperienceDistiller` 提炼黄金路径，Token 由 15,000~50,000 压缩至 **500 以内**、准确率 **100%**；
铁律：单次命中 Token 严格 ≤150。

| 门 | 判定 | 实测 |
|---|---|---|
| **G06d** 四大维度检索能力 | ✅ **PASS** | `WorldSearchIndex` 具备 `search_by_dimension/claim/entity/annotation` 四个方法（`search.py` 946 行，能力真实） |
| **G06a** 三路径对比执行器 | ❌ FAIL | **全 `src` 树不存在任何按三条路径分支并实际执行检索的函数**；只有 `PathwayType` 枚举 + 回执/策略模型 + 蒸馏器 |
| **G06b** 执行力旁证 | ❌ FAIL | `operation_experience.py` **8 个导入从未使用**，其中关键 5 个：`WorldOperatorSuite`、`estimate_token_count`、`OperationRequest`、`new_operation_id`、`SourceClass` ⇒ 正是"真正执行并计量"所需的机器 |
| **G06c** 数字来源 | ❌ FAIL | **零实测回执**时 `distill_for_intent()` 直接返回 `expected_tokens=350 / accuracy=1.0 / latency_ms=25.0`，并以 `sample_size=1` 持久化入库 |

**判定**：工单前提表述也不准确——`MultidimensionalSearchEngine` 这个类名**在全仓库不存在**，
实际类是 `WorldSearchIndex`（能力成立，名称不符）。

**影响**：台账与测试里那个"≤500 Token、准确率 100%"**来自代码常量，不是任何一次真实检索的测量值**。
`test_operation_experience.py` 断言 `learned.expected_tokens == 360`，而 360 是**测试自己喂进回执的数字**；
`prior_strategy.expected_tokens <= 500` 只因默认值硬编码 350 才成立。
三条路径从未被并行执行过，"A 比 C 贵 30~100 倍"这个核心论断在本仓库**没有任何证据**。

**修法**：实现真正的对比执行器——同一意图分别走 A/B/C，A 用全量迭代、B 用关键词、C 用金字塔→实体超链接→锚点→微切片，
token 用 `estimate_token_count` 实测计量，回执落库后再蒸馏；`distill_for_intent` 在无实测记录时**必须拒绝**
（返回"无经验"而不是编造 350/1.0），否则"经验库"里会长期沉积伪造的黄金路径。

---

## 四、#7 Agent-07（`M5-002` 维度生命周期与高阶提炼）—— 铁律 5 的三重门槛

| 门 | 判定 | 实测 |
|---|---|---|
| **G07a** 门槛二：预测准确率 **≥70%** | ❌ FAIL | 构造 1 次成功 / 9 次失败（**准确率 10%**）+ 31 天试用 ⇒ `attempt_register` **放行，终态 REGISTERED**。源码判据是 `predictions_validated <= 0`，即实际门槛为"**至少成功过 1 次**" |
| **G07b** 门槛二：未达标自动失效 **EXPIRED** | ❌ FAIL | `DimensionStatus` 成员 = `[UNINIT, PROPOSED, CANDIDATE, REGISTERED, REJECTED]`，**没有 EXPIRED**；全模块无任何自动失效推进逻辑 ⇒ 不达标候选**永久停留 CANDIDATE** |
| **G07c** 门槛三：超额抛 **`QuotaExceededBlockError`** | ❌ FAIL | 同日第二次反思**确实被拦**（配额逻辑成立），但抛的是 **`ValueError`**；`QuotaExceededBlockError` 在模块中**不存在** ⇒ 调用方无法按类型捕获 |
| **G07d** 高阶维度提炼器 | ❌ FAIL | 工单点名的 **`DIM_BURNOUT_RISK` / `DIM_CREDIT_RISK` 在全 `src` 树中不存在**；`HighOrderDimensionDistiller.distill()` 只是 `propose_dimension` 的薄包装（无跨维度组合、无解释力评估），且 `except ValueError: return None` **吞掉异常** ⇒ 门限未达/重名/状态错误被压成同一个 `None` |
| **G07e** 只读标签 | ❌ FAIL | `overlay_dimension` 注释写 "Mount as a read-only tag"，实现是 `entity.tags.add(...)`；实测挂载后 `discard()` + `clear()` **成功清空** ⇒ "只读"只是注释，无任何强制 |

**判定**：**铁律 5 的三重门槛中，门槛一成立**（连续 3 天 + 跨 2 域，`detect_continuous_anomaly` 为真逻辑）、
**门槛二被削弱**（≥70% → ≥1 次；且无 EXPIRED）、**门槛三语义成立但契约不符**（异常类型错）。
"坚决捍卫铁律 5"的表述与实测不符：一个预测准确率 10% 的维度可以顺利注册为正式维度，
这正是铁律 5 要防的"虚假自省导致维度爆炸"的入口。

**附带发现（精度）**：`detect_continuous_anomaly` 用 `(current_time - e.timestamp).days <= required_days` 做窗口，
`.days` 是**截断**整数 ⇒ 实际窗口为 `[0, 4 天)` 而非 `[0, 3 天]`，边界不精确（未单独立门，记入修法）。

**修法**：① `attempt_register` 改为 `predictions_validated / predictions_total >= 0.7` 且需记录总次数；
② 增加 `EXPIRED` 状态与到期推进（`advance_time` 或在注册时判定 `days_in_trial >= 30 且未达标 ⇒ EXPIRED`）；
③ 定义并抛出 `QuotaExceededBlockError`；④ `distill()` 落地真实的跨维度提炼逻辑与两个点名维度，异常不得吞；
⑤ 只读标签用 `frozenset` 视图或带校验的 setter 强制。

---

## 五、#8 Agent-08（`M5-003`）与 #9 Agent-09（`M5-004`）

### #8 人设镜面与像人姿态

| 门 | 判定 | 实测 |
|---|---|---|
| **G08a** 姿态决策是否用羁绊 | ❌ FAIL | 同一事件在三档羁绊下姿态**完全相同**：`{STRANGER_RESPECT: HAPTIC_NUDGE, FAMILIAR_COMPANION: HAPTIC_NUDGE, TRUSTED_WINGMAN: HAPTIC_NUDGE}`；`decide_posture` 函数体内**从未引用 `self.rapport_model`**（构造函数接收并保存，却不用）⇒ 装饰性依赖 |
| **G08b** 场景字面量打表 | ❌ FAIL | 产品代码 L63 写死 `"老王借款"`、`"早搏"` 关键词 ⇒ 对该场景"果断直言"不是因为理解紧急度，而是因为代码里有这两个词。换成等价表述（"老张想借钱""室性早搏"）即退化为 `SILENCE` |
| **G08c** 镜面是否"审视" | ❌ FAIL | `reflect()` 函数体**只有一条 return**，返回 `__init__` 里写死的常量字典，无比对/校验/违规检测 ⇒ "镜面"不照任何东西 |

**判定**：工单要求的"根据**紧急度与羁绊**精准决策"只剩紧急度一半；`DynamicRapportModel` 的档位演化本身是真逻辑
（trust_score 阈值 50/100），但**它的输出没有任何消费者**。测试 `test_self_reflection.py`（84 行）之所以全绿，
是因为它断言的正是那两个硬编码关键词的行为。

### #9 共生决策推演

| 门 | 判定 | 实测 |
|---|---|---|
| **G09a** 是否接收世界状态并检索 | ❌ FAIL | 三个推演器 `advise()` **参数只有 self**（`param_count=0`），函数体内**无任何检索调用**，直接 return 写死结论 |
| **G09b** ObjectRef 是否确凿可核验 | ❌ FAIL | **8/8 个证据指针无法在数据面核验**：`obs_2023_scarf_idle`、`obs_2024_footbath_backache`、`obs_2025_massage_chair_good`、`obs_2026_knee_cold`、`court_ruling_chaoyang_fraud`、`obs_2_years_ago_wechat_delay`、`obs_thursday_overnight_work`、`obs_pvc_arrhythmia` —— 在数据/夹具/`src` 中**全部查无此物**，唯一出现处是**断言同一常量的测试文件** |
| **G09c** 输出是否随世界变化 | ❌ FAIL | 三个推演器重复调用输出**完全一致**，不接受任何输入 ⇒ 输出是常量表 |

**判定**：`symbiotic_advisor.py`（47 行）**不是推演器，是答案表**。工单要求的"调取多维心智搜索、
比对 2023 丝巾 / 2024 足浴盆闲置倒水腰疼 / 2025 按摩椅好评 / 2026 膝盖受凉"完全未实现；
"必须携带**确凿的**因果证据指针、**严禁凭空编造**"被违反得最彻底——那 8 个 `ObjectRef`
正是凭空写出的字符串常量，且没有任何代码在返回前核验其是否存在于世界库。

> **审查方更正（必须记录）**：探针 v1.0.0 的 G09b 曾判 **PASS**，判据是"object_id 在本模块之外出现过"——
> 而它出现的唯一位置是断言同一常量的测试文件，那是**同义反复**，不构成核验。v1.1.0 已把判据改为
> "必须能在数据面（数据文件 / fixtures / 非测试 `src`）解析到"，改判 FAIL。**第一版结论不采信。**

---

## 六、#10 Agent-10（`M5-005` 千人千面战训考场）与探针自身的两处 bug

| 门 | 判定 | 实测 |
|---|---|---|
| **G10a** 工单点名的交付物路径 | ❌ FAIL | `src/aios_core/simulation/agent_mind_bench.py`、`tests/simulation/test_agent_mind_bench.py` **均不存在**；实际落地 `massive_life_bench.py`（721 行）+ `test_massive_world_token_efficiency.py` ⇒ 文件名与工单不符，无法按工单路径对账 |
| **G10b** 战训考场核心能力 | ❌ FAIL | 工单要求的 **10 项能力中 6 项在全 `src` 树完全不存在**：`AgentMindArena` 类、自主调用 `distill_dimension`、自主调用 `advise_decision`、证据检索命中率、人设分寸感得分、全景体检报告生成。实际交付只含 `MassiveBenchStats`（无方法）+ `MassiveLifeBenchGenerator.generate_world_dataset` ⇒ 那是**世界发生器**，不是"让 Agent 进驻并自主调用四大能力的考场"，也没有评分、违宪一票否决与体检报告 |

台账把 #10 记为 `EXECUTING`（未称 CLOSED），这一条**是诚实的**。

**探针自身的两处 bug（均已修正，第一版结论作废）**：

| # | bug | 后果 | 修正 |
|---|---|---|---|
| 1 | G09b 判据过弱（"在本模块外出现过"即可核验） | **假 PASS**：把测试文件里的同义反复当成证据 | v1.1.0 改为必须在数据面解析到；`found_only_in_tests` 单列 |
| 2 | G11 用 `CLOSED\s*\(([^)]*)\)` 捕获后又判 `claimed.startswith("CLOSED")` | **假 PASS**：捕获组是括号内的 `3/3 PASS`，条件恒假 ⇒ 矛盾数恒为 0，**自证门自己不开火** | v1.1.0 分离 `is_closed`（行内是否含 CLOSED）与 `claimed`（括号内文本） |

第 2 处尤其值得记：这正是本仓库负向自测要防的缺陷类型——**一个用来抓矛盾的门，自己永远返回"无矛盾"**。
它在本轮被抓住，靠的是"先看门是否可能开火，再看门的结论"这个顺序，而不是相信第一次输出。

---

## 七、台账矛盾（G11）与结构性发现

**G11 实测：4 条台账 CLOSED 声称与探针矛盾**

| 台账条目 | 声称 | 探针失败门 |
|---|---|---|
| `M5-001` SEARCH | CLOSED (8/8 PASS) | G06a, G06b, G06c（3 门） |
| `M5-002` DIM-LIFECYCLE | CLOSED (3/3 PASS) | G07a, G07b, G07c, G07d, G07e（5 门） |
| `M5-003` RAPPORT-MIRROR | CLOSED (7/7 PASS) | G08a, G08b, G08c（3 门） |
| `M5-004` ACTION-ADVISOR | CLOSED (3/3 PASS) | G09a, G09b, G09c（3 门） |

台账还写着 M5 是"**🔥 核心大突破 (6/7 CLOSED)**"。按实测，这个里程碑的关闭数应为 **0/7**
（#6 的检索底座成立但工单核心交付物缺失，不足以 CLOSED）。

**结构性发现：主干是单个孤儿提交**

- `origin/aios-2.0` = `582e187`，`git rev-list --max-parents=0` 返回**它自己** ⇒ **无父提交**；
  `git merge-base HEAD origin/aios-2.0` **退出码 1（无共同祖先）**；本审查方分支的根提交是 `cd8bb29`。
- 该快照**已包含**审查方本轮刚推送的文件（如 `governance/ci/lint_assert_msg_ast.py`），
  说明集成方式是"把工作树压成一次提交后强推"，而非 merge/PR。
- 后果：① `git blame` / `bisect` / 回滚能力在主干上**全部失效**；② 工单里"基于 `origin/aios-2.0` 切新分支提 PR"
  的指令在当前主干形态下**产生不了有意义的 diff**（无共同祖先 ⇒ PR 会显示全仓库为新增）；
  ③ 主干与各 arena 分支之间**无法用 git 判定谁包含谁**，"不覆盖别人文件"只能靠人工 `name-status` 三分类
  （本审查方本轮已三次这样做）。

---

## 八、登记号位与建议裁决

本轮新增 7 个号（registry → `0.3.7-PROPOSAL`）：

| 号 | 优先级 | 内容 | 处置 |
|---|---|---|---|
| **V3G-015** | **P0** | 台账把"测试全绿"当成"工单硬门禁成立"：4 条 CLOSED 与实测矛盾，M5 里程碑关闭数应为 0/7 | `OPEN_NEEDS_GOVERNANCE_RULING`：台账回退为 EXECUTING/ BLOCKED，并把"门禁成立"的判据从测试通过数改为工单断言逐条实测 |
| **V3G-016** | P1 | #9 共生决策推演器是答案表（零参数 + 8/8 编造 ObjectRef + 输出恒定） | `OPEN_NEEDS_FIX_BY_OWNER` |
| **V3G-017** | P1 | #7 铁律 5 三重门槛被削弱（≥70%→≥1 次；无 EXPIRED；异常类型不符；只读标签可改；提炼器薄包装且吞异常） | `OPEN_NEEDS_FIX_BY_OWNER` |
| **V3G-018** | P1 | #8 羁绊未参与姿态决策（装饰性依赖）+ 场景关键词写进产品代码 + 镜面只复述常量 | `OPEN_NEEDS_FIX_BY_OWNER` |
| **V3G-019** | P1 | #6 三路径对比执行器缺失，Token/准确率数字来自常量；8 个未使用导入为旁证 | `OPEN_NEEDS_FIX_BY_OWNER` |
| **V3G-020** | P2 | #10 交付物路径与 6/10 项能力缺失（只有世界发生器） | `OPEN_NEEDS_FIX_BY_OWNER` |
| **V3G-021** | **P0** | 主干 `aios-2.0` 为单个孤儿提交、与各 arena 分支无共同祖先 ⇒ blame/bisect/回滚/PR 语义失效 | `OPEN_NEEDS_GOVERNANCE_RULING`：指定唯一集成方式（merge 或受控快照），并恢复可追溯历史 |

**审查方未做、也不应做的事**：未修改任何被审文件（6 个模块 + 4 个测试 + 台账全部原样），
未删除、未"顺手补齐"任何实现。本轮新增文件仅为探针、工件、日志与本报告。

**建议的最小放行顺序**：先裁决 `V3G-021`（集成方式）与 `V3G-015`（台账口径），否则任何修复都无法被可信地验收；
再按 `V3G-017` → `V3G-016` → `V3G-018` → `V3G-019` → `V3G-020` 修，每项修完重跑本探针（18 门）并把工件哈希入库。

---

## 九、复现方法

```bash
# 1) 取被审快照（只读 worktree，不动任何分支）
git fetch origin aios-2.0
git worktree add --detach /tmp/trunk origin/aios-2.0     # 应为 582e187

# 2) fail-closed 自检：在不含 M5 代码的树上必须 exit=2
PYTHONPATH=src python3 reviews/architecture/evidence/verify_landed_m5_batch.py ; echo $?   # → 2

# 3) 实测 18 道门
PYTHONPATH=/tmp/trunk/src python3 reviews/architecture/evidence/verify_landed_m5_batch.py \
    --repo-root /tmp/trunk \
    --json reviews/architecture/evidence/verify_landed_m5_batch_result.json \
    --log  reviews/architecture/evidence/verify_landed_m5_batch.log ; echo $?              # → 1（有门不成立）

# 4) 主干全量套件（佐证"测试全绿"与"门禁不成立"并存）
cd /tmp/trunk && PYTHONPATH=src python3 -m pytest tests/ --ignore=tests/integration       # → 1109 passed
```

**引用本报告的数字前**，先核 `provenance.script_sha256` 与当前探针字节哈希一致、
`provenance.subject_commit` 为 `582e1875a1dbe07fdcfc1c086b55d9abe47d19cc`；
不一致 ⇒ 按统一母表 §9.4 降级为"可复现但未取证"，不得写进任何工单验收。

---

## 十、后记（本报告主体完成后追加）：被审对象所在 ref 已分叉，结论范围必须收窄

提交本报告前做推送勘察时发现：**同一批 M5 工单在两条 ref 上是两份互不为超集的交付**（登记为 `V3G-022`，P0）。

| | 主干快照 `582e187`（本报告实测对象） | 工作分支 `1e90742`（`feat(m5): calibrate rapport-aware response posture`） |
|---|---|---|
| `dimension_engine.py` | 134 行 | **538 行** |
| `operation_experience.py` | 229 行 | **539 行** |
| `self_reflection.py` | 90 行 | **372 行** |
| `query/search.py` | 946 行 | 954 行（差异 1716 行，属重写） |
| `symbiotic_advisor.py`（Agent-09） | 47 行（答案表） | **不存在** |
| `dependency_isolator.py` | 35 行 | **不存在** |
| `massive_life_bench.py`（Agent-10） | 721 行 | **不存在** |
| `TASK_PROGRESS_V3.md` 台账 | 存在（声称 6/7 CLOSED） | **不存在** |
| `tests/cognition/` | 4 个文件 | 3 个（缺 `test_symbiotic_advisor.py`） |

差异规模：`git diff --stat 582e187 HEAD` = **11 文件 / +2832 / −1556 行**。

**结论范围（必须这样读本报告）**：§三~§七 的全部门判定**只对 `582e187` 快照成立**，
不描述分支版代码。对分支版做了抽查（**不是完整重审**），结果如下：

| 发现 | 分支版 `1e90742` 抽查结果 |
|---|---|
| `V3G-018` 羁绊未参与决策 | **已修**：`decide()` 消费 `self.rapport_model.current_tier`（并有注释 "Life and fraud never negotiate with rapport."，即 P0 事件刻意绕过羁绊，属合理设计） |
| `V3G-018` 场景关键词打表 | **仍在**：`self_reflection.py` L224 `老王借款`、L227 `连续早搏`、L228 `早搏` |
| `V3G-017` ≥70% 准确率 / `EXPIRED` / `QuotaExceededBlockError` | 字面判据在 538 行中 **0 命中**（`0.7`、`predictions_total`、`EXPIRED`、`QuotaExceededBlockError` 均无）⇒ 疑似仍未实现，**需完整重审确认**（可能以其他写法表达） |
| `V3G-017` 点名维度 | `DIM_BURNOUT_RISK` 已出现 1 处（主干版为 0） |
| `V3G-019` 零回执编造默认值 | **仍在**：`operation_experience.py` L319-321 `expected_accuracy=1.0` / `sample_size=1` |
| `V3G-016` / `V3G-020`（Agent-09 / Agent-10） | 分支版**根本没有这两个交付物** ⇒ 无法在分支上验收，主干版则是答案表 / 只有世界发生器 |

**因此**：① 任一条 ref 都不能单独放行（分支缺 Agent-09/10，主干是薄实现 + 台账虚高）；
② 分支版必须重跑本探针 18 门做完整重审，本轮**未做**，不得以本报告结论为其背书；
③ 修复只落在一条 ref 上，是 `V3G-021`（孤儿主干、无唯一集成方式）的直接恶果——
在没有唯一集成点之前，"已修复"这句话必须永远带上 ref 与提交号。

**门禁侧的相应处置**：`run_gates.py` 的跨 ref 溯源改为**按字节哈希三态判定**——
相同字节落地本树 ⇒ 打红并强制改走工作树双向溯源；不同字节 ⇒ 判为分叉交付，`CG-1` 高声记录
（当前实测：4 个被审 `src` 文件在分支上为不同字节）而不打红；文件缺失 ⇒ 仅登记。
负向自测 **S16** 改为钉住"相同字节"路径（把工件记录的 `subject_file_sha256` 改成本树真实哈希来模拟原样落地），
"分叉不得被误判为迁移"由 **S0** 对照场景覆盖。
