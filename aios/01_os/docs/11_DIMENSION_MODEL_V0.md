# Dimension Model V0 —— 多维可挂载曲线的对象模型与治理（契约冻结草案）

- 签发：2026-09-11 第二批，最高项目决策者 ｜ 上位依据：宪法 V1.4-r0 第三章（Dimension）、§3.2（Registry）、§3.4（方向与趋势）、§9.1（App 不得自建认知）、§5.5（知识状态）
- 施工单来源：指挥官表述——"App 只是专业方向的处理环境，底层数据共通；一个教育 App 入口里有数学/化学/英语多条曲线；化学没有这条曲线=证明还没学过；AI 看今天玩了一天没学习就主动提醒；兴趣 App 选了编程，AI 用数学+英语曲线决定怎么教；情绪/压力/思想这类没有外界接口的，AI 自己注册一条曲线量化；刚买了车，留好接口让汽车数据接进来"
- 效力：本文件冻结**对象结构与治理规则**；不含实现。实装见 `NEXT_TASK.md` 任务 I（Dimension Registry）。

---

## 1. 维度身份：一条曲线 = 四段式命名（这是"可挂载"的全部秘密）

```
dim_id = <producer>/<subject>/<family>/<axis>
           ↑谁供数   ↑谁的曲线  ↑哪个域    ↑测什么
```

| 段 | 取值规则 | 指挥官场景里的实例 |
|---|---|---|
| `producer` | 注册制枚举：`edu_app` `interest_app` `band` `phone` `chat` `vehicle_oem` `ai_self` `aios` … | 数学曲线供数方是 `edu_app`；情绪曲线是 `ai_self` |
| `subject` | `u_<id>`（用户）或 `ai_self`（AI 自己的曲线，与用户同轴不同命名空间，§1.2） | AI 的"我对用户的把握度"也是一条正经曲线 |
| `family` | 域：学科、健康、财务、社交、设备…；**App 入口 = 一个 family，不是一个维度** | `math` `english` `chemistry` `programming` `emotion` `car` |
| `axis` | 该域内可比较的测度：`knowledge_level` `practice_minutes` `vocab_size` `valence` `stress_load` `fuel_level` `fatigue_hours` | 一个 family 下挂多条 axis |

**四条硬规则**

1. `family` 与 App 是**一对多**：教育 App 一个入口 → `math`/`english`/`chemistry`… 全部挂在同一个 `producer=edu_app` 下。新增学科 = 新增 `family` 注册项，**曲线内核一行不改**（§3.2 注册制）。
2. `dim_id` 里**禁止**出现 App 私有 ID 之外的身份概念；曲线不得自带 Identity，只引用 `entity_id`（旧 NEXT_TASK 裁决沿用）。
3. 换 App 不换 subject：`interest_app` 读 `edu_app/u_001/math/knowledge_level` 是**同一份数据**，不允许复制副本或自建镜像（§9.1）。
4. 新数据源（汽车、体重秤、日历）= 新 `producer` 注册项。为接新数据而改曲线内核 = 违宪。

## 2. ★ 曲线状态机：缺曲线是一等信息（本文件最重要的一条）

每条曲线必须带 `state`，消费方（Trigger / AI Session / 其他 App）**必须**按状态分支：

| state | 含义 | 允许怎么用 | 禁止怎么用 |
|---|---|---|---|
| `ABSENT` | 这条曲线从未建立 | → 知识状态 `UNKNOWN`；→ 唯一合法表述"没有这项数据 / 还没学过"；→ **可触发**：问用户 / 注册新维度 / 提议接外部源 | ⛔ **不得当作 0 或"水平低"**。把"没测过"读成"不会"是最贵的一类 bug：AI 会因此给用户讲零基础 |
| `INSUFFICIENT` | 有源但样本不足（`n < min_n`） | 只可说"数据还不够"；不可出趋势与斜率 | ⛔ 不得据此调整阈值或做跨域迁移 |
| `LIVE` | 正常更新中 | 全部用途 | ⛔ 不得引用超过 `stale_after` 的点当"现在" |
| `STALE` | 超期未更新（源断供、设备没戴） | 只能作历史；必须显式声明"截至 X 日" | ⛔ 不得用旧值冒充当前（车不供数了还说油量 60%） |
| `SUSPENDED` | 用户在设置面关掉（§10 主权） | 不得读 | ⛔ 不得绕过；绕过即违反数据主权，进安全类审计 |

```jsonc
// CurveMeta（注册表里的一行，冻结字段）
{"dim_id":"edu_app/u_001/chemistry/knowledge_level","state":"ABSENT",
 "producer":"edu_app","rubric_id":null,"min_n":5,"sample_count":0,
 "stale_after_s":86400,"last_point_at":null,"created_by":"system","status":"registered"}
```

## 3. ★ 裁决：App 只报观测，AIOS 算曲线

**这是防"第二套认知"的关键一刀。** 若允许各 App 直接上报"用户是小学一年级"，那么三个 App 会有三套"年级"含义，跨域推理当场破产。

```
App 侧（只报事实）                 AIOS 侧（唯一算者）
  obs.attach: {                   rubric 打分 + 基线统计
    item_id, is_correct,          → CurvePoint（可比较、可跨 App 比）
    seconds_spent,                → 曲线、方向、趋势
    wrong_step: "carry_1"   }     → 供 Trigger / AI Session / Transfer 消费
```

- App 可提议 rubric（`rubric_proposal`），但**批准权在 AIOS + 用户**（见 §5）。
- 已存在的"App 自算分数"迁移：一次性换算成 rubric，换算前后打 `series_break` 断点标记。

## 4. CurvePoint（点结构）与方向趋势

```jsonc
{"point_id":"…","dim_id":"edu_app/u_001/math/knowledge_level","t":"2026-09-11T20:10:00+08:00",
 "value":2.0,"unit":"tier","quality":0.86,
 "rubric_id":"math_knowledge_rubric","rubric_version":3,
 "basis_obs":["obs_501","obs_508","obs_511"],        // 这个分数由哪些观测算出，必须可追
 "epistemic":"INFERRED",                              // 统计类可 KNOWN，AI 打分类必须 INFERRED
 "delta":+0.5,"direction":"RISING","slope":0.02,"span_s":604800,"volatility":0.11}
```

- 未知不填猜测值（旧 NEXT_TASK 第 3 条仍有效）；`value` 缺失就整条点不写，状态转 `INSUFFICIENT`。
- 趋势字段由 AIOS 统一算，禁止 App 与 UI 自算斜率。

## 5. ★ RubricSpec：换尺子必须留断点（AI 自造曲线的安全带）

AI 自己注册"情绪/压力/思想"这类无外界接口的维度，风险不是"能不能注册"，而是**同一个数昨天今天用的是不是同一把尺子**。因此：

```jsonc
{"rubric_id":"emotion_valence_v0","version":2,"producer":"ai_self",
 "kind":"statistical|llm_scored","input_fields":["chat_turn","sleep_minutes","hr_rest"],
 "scale":{"min":-5,"max":5,"zero":"平静"},
 "tiers":["危机","低落","平淡","良好","高涨"],
 "sql_or_prompt_ref":"rubrics/emotion_valence_v2.md",     // 口径正文，可 diff 可审计
 "recompute_on_break":true,                                // 改版后是否回溯重算
 "falsify_clause":{"deny_limit":5,"action":"suspend_and_report"} }  // 连续 5 次用户否认 → 自毁
```

**三条硬约束**

1. 每个 point 必须带 `rubric_version`。**跨版本不可比**：查询接口遇到版本边界必须返回 `series_break`，不得画成一条连续上升线。这是"用户情绪变好了其实是换了公式"的唯一防线。
2. `statistical` 类（做题量、错题率、油耗、睡眠时长）**必须 SQL 可复算**：给定同一批 obs，任何人都能算出同一个 value。复算不一致 = 数据缺陷，必须报错而不是取平均。
3. `llm_scored` 类（情绪、压力、思想、动机）永远 `INFERRED`，必须带 `basis_obs`，永不写 World State 事实槽位；且必须实现 `falsify_clause`——**不能被证伪的曲线就是装饰品**。

## 6. AI 自注册维度的治理（防爆、防幻觉、可回滚）

| 环节 | 规则 |
|---|---|
| 提案 | `dim_propose{family, axis, why, expected_producers[], rubric 草案, 预计打扰度, 退出条件}` —— 提案本身进时间轴，可回放 |
| 审批 | 用户可见（设置面"AI 给我建的档案"一栏），**一键否决 + 一键删除**；未批准的维度不得开始打分（可先 `shadow` 试运行只算不用于决策） |
| 版本 | 走 `evolutiond.strategy_versions`：可回滚、留痕；禁止第二套配置存储 |
| 防爆炸 | 每 subject 每季度新增 ≤ 6 条；总量 ≤ 40 条；超限必须先下线旧维度（按热值与建议理由） |
| 热值衰减 | 久无供数即降级为 `STALE → SUSPENDED`；**必须支持 `periodic_exempt`**（生日/纪念日/年检一类一年只活跃一次的维度，衰减会误杀最有价值的提醒） |
| 自毁 | 触发 §5 的 `falsify_clause` 或用户连续否证 → 下线并在下次 AI Session 里说明"我为什么放弃了这条判断" |

## 7. ★ Transfer Belief：跨域迁移是独立对象，不是曲线的属性

指挥官场景（兴趣 App 学编程 → AI 参考数学与英语水平决定教法）在模型上必须显式化：

```jsonc
{"transfer_id":"tr_0091","to_dim":"interest_app/u_001/programming/teaching_level",
 "from_dims":[{"dim_id":"edu_app/u_001/math/knowledge_level","state":"LIVE","value":2.0},
              {"dim_id":"edu_app/u_001/english/vocab_size","state":"LIVE","value":340},
              {"dim_id":"edu_app/u_001/chemistry/knowledge_level","state":"ABSENT"}],
 "claim":"可学编程；卡在单位换算与英文报错，需用中文对照 + 算术级例题起步",
 "confidence":0.62,"epistemic":"INFERRED","basis_obs":["obs_501","obs_777"],
 "expires_at":"2026-10-11T00:00:00+08:00","correctable_by":"user"}
```

- Transfer **只进认知树（INFERRED）**，绝不写回源/目标曲线的值，也不得被 Trigger 当事实用（Trigger 只读曲线，不读 Transfer）。
- 任一 `from_dim.state ∈ {ABSENT, INSUFFICIENT, STALE}` 时：`confidence` 必须**自动降档**且 UI 明示"依据不全"。上例里化学是 ABSENT → 不得参与"该不该报化学竞赛"这类判断。
- 必须可被用户纠正：`interact.feedback` → `evolutiond` 记 Regret（**安全类 Transfer 永久豁免学习**，与 §4.2-6 同规矩）。
- 呈现义务：AI 用 Transfer 做决定时，要说得出"我根据 A、B 两条曲线推断 C"（可解释性是验收 T 的内容）。

## 8. 外部数据源接入（"留好接口"的具体形状）

`SourceManifest` —— 汽车/家电/第三方健康平台等外部生产者接入的唯一入口：

```jsonc
{"producer_id":"vehicle_oem_x","transport":"push_http|pull_cron","auth_scope":["car/fuel_level","car/mileage"],
 "fields":[{"name":"fuel_level","unit":"%","freq_s":600,"retention_d":90,"redact":"none"},
           {"name":"trip_geo","unit":"geo","freq_s":60,"retention_d":7,"redact":"coarse"}],
 "grace_period_s":86400,"on_break":"state=STALE_then_ask_user","consent":"per_scope",
 "dims_to_create":["producer/subject/car/fuel_level","producer/subject/car/drive_hours_today"]}
```

- 授权粒度到 `scope`；断供进 `grace_period` 后自动 `STALE`，并**触发一次"要不要继续接/换个源"的对话**，禁止静默用旧值。
- 接入即注册维度（§1 第 4 条）：曲线内核不为任何新品牌改代码。
- 场景合法性自检（宪法第十章）：`drive_hours_today` 提醒休息 = 安全类，允许主动打断；"油耗高是不是该保养" = 建议类，走最低打扰通道，**不得**因为"数据有"就一直说。

## 9. 主动帮助的路径（"今天玩了一天，提醒他学习"）

```
edu_app 侧 obs：20:00 起只有娱乐 App 活动、无做题观测
 → dim study/practice_minutes = 0（今天）；dim entertainment/minutes 曲线 RISING
 → Trigger（§4.2-1 方向变化 + §4.2-3 与个人基线偏离）；非"晚于 21:00"这种全局硬编码
 → AI Session 按 §5.9 顺序进入：先读自我状态 → 读 attitude（今天已提醒过一次，用户明确说"今天不想学"）
 → 判断：Help-First 要求"帮得上"，而非"说得出"
 → 输出：不重复唠叨，改提最小可执行台阶（"先做 1 道 5 分钟的题，做完就停"）+ 若态度显示反感则选择沉默并留档
 → Outcome 回流：用户是否开始 → Evolution 调"提醒时机与措辞档位"（安全类不受影响）
```

三条约束：① 提醒阈值来自**个人基线**，不用全局固定值；② 沉默是合法输出（§5.9/§13.1）；③ 同一意图当天已明确拒绝 → 同情境签名内沉默（禁止全局拉黑该触发类型，也禁止复读机式骚扰）。

## 10. 与调用表/五层的对应（不新建第二套机制）

| 动作 | Syscall（10 号文档） | 归属 | 层 |
|---|---|---|---|
| App 上报观测（唯一写入口） | `obs.attach` | hublinkd | L1 |
| 注册/查询维度与状态 | `dim.register` / `dim.list` | dimensiond（待建） | L2 |
| 读曲线（带 series_break） | `curve.read` | dimensiond | L2 |
| AI 提案新维度 | `dim.propose` | dimensiond + settingsd 审批 | L2/L3 |
| 声明跨域迁移 | `transfer.declare` | cognitiond（写 INFERRED） | L2 |
| 外部源接入 | `source.register` | settingsd(consent) + dimensiond | L1/L3 |
| 用户否决/暂停/删除维度 | `settings.set` / `consent.revoke` | settingsd | L3 |

## 11. 验收挂钩（判据已写进 `docs/08_ACCEPTANCE_TESTS.md` V0.2 的 T/U/V/W）

U = ABSENT 不得当 0；T = Transfer 必须声明依据且缺数降档；V = rubric 改版必须出断点、可复算类必须复算一致、自注册必须可自毁；W = 外部源断供必须转 STALE 且不得用旧值冒充。

## 12. 本文件的边界

不实现、不改代码、不改宪法。以下留给实现任务：存储介质选型（复用 `world_state.db` 同库或独立 `dimensiond.db`）、窗口聚合的具体 SQL、rubric 正文仓库（`code/rubrics/`）。任何与本文件冲突的实现提案，先改本文件再写代码。
